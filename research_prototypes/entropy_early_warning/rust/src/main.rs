//! Independent native audit of the study's population-entropy telemetry.
//!
//! Reads the hashed `population_snapshots` and `snapshot_bounds` arrays written
//! by the Python simulation run, recomputes normalized entropy for every
//! snapshot with the Rust kernel, times repeated batch computations (in-memory
//! only; file reading is excluded), and records the result as its own evidence
//! run in the same store through the Python sidecar.
//!
//! Usage (from the study directory):
//!   entropy-audit --root <store> --snapshots <npy> --bounds <npy>
//!                 [--bins 10] [--warmup 3] [--repeats 30] [--seed 0]
//!                 [--protocol protocol.yaml] [--python-path <dir>]

use eigenbrains_sdk::kernels::{normalized_histogram_entropy, quantile};
use eigenbrains_sdk::npy::read_f64;
use eigenbrains_sdk::{
    ArtifactEmission, ArtifactSchema, BridgeConfig, FieldSchema, MetricSpec,
    ResearchExperimentSpec, SdkError,
};
use serde_json::json;
use std::collections::HashMap;
use std::time::Instant;

fn args() -> Result<HashMap<String, String>, SdkError> {
    let raw: Vec<String> = std::env::args().skip(1).collect();
    if !raw.len().is_multiple_of(2) {
        return Err(SdkError::Invalid(
            "arguments must be --name value pairs".into(),
        ));
    }
    raw.chunks(2)
        .map(|pair| match pair[0].strip_prefix("--") {
            Some(name) => Ok((name.to_owned(), pair[1].clone())),
            None => Err(SdkError::Invalid(format!(
                "unexpected argument {}",
                pair[0]
            ))),
        })
        .collect()
}

fn get<'a>(map: &'a HashMap<String, String>, key: &str, default: &'a str) -> &'a str {
    map.get(key).map(String::as_str).unwrap_or(default)
}

fn number<T: std::str::FromStr>(
    map: &HashMap<String, String>,
    key: &str,
    default: &str,
) -> Result<T, SdkError> {
    get(map, key, default)
        .parse()
        .map_err(|_| SdkError::Invalid(format!("--{key} is not a valid number")))
}

fn batch(
    data: &[f64],
    bounds: &[f64],
    n: usize,
    rows: usize,
    cols: usize,
    bins: usize,
) -> Result<Vec<f64>, SdkError> {
    let size = rows * cols;
    (0..n)
        .map(|i| {
            normalized_histogram_entropy(
                &data[i * size..(i + 1) * size],
                rows,
                cols,
                bounds[2 * i],
                bounds[2 * i + 1],
                bins,
            )
            .map_err(|e| SdkError::Invalid(e.into()))
        })
        .collect()
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a = args()?;
    let root = a
        .get("root")
        .ok_or_else(|| SdkError::Invalid("--root is required".into()))?;
    let snapshots_path = a
        .get("snapshots")
        .ok_or_else(|| SdkError::Invalid("--snapshots is required".into()))?;
    let bounds_path = a
        .get("bounds")
        .ok_or_else(|| SdkError::Invalid("--bounds is required".into()))?;
    let bins: usize = number(&a, "bins", "10")?;
    let warmup: usize = number(&a, "warmup", "3")?;
    let repeats: usize = number(&a, "repeats", "30")?;
    let seed: i64 = number(&a, "seed", "0")?;

    let snapshots = read_f64(snapshots_path)?;
    let bounds = read_f64(bounds_path)?;
    if snapshots.shape.len() != 3 || bounds.shape != vec![snapshots.shape[0], 2] {
        return Err(SdkError::Invalid(
            "snapshots must be (n, rows, cols) and bounds (n, 2)".into(),
        )
        .into());
    }
    let (n, rows, cols) = (snapshots.shape[0], snapshots.shape[1], snapshots.shape[2]);

    let spec = ResearchExperimentSpec::builder(
        "telemetry-audit",
        "An independent native implementation reproduces the Python population-entropy telemetry \
         on the study's snapshots within 1e-12, and its batch cost is measured.",
        get(&a, "protocol", "protocol.yaml"),
    )
    .seed(seed)
    .parameter("bins", json!(bins))
    .parameter("warmup", json!(warmup))
    .parameter("repeats", json!(repeats))
    .parameter(
        "build",
        json!(if cfg!(debug_assertions) {
            "debug"
        } else {
            "release"
        }),
    )
    .input("population_snapshots", snapshots_path.as_str())
    .input("snapshot_bounds", bounds_path.as_str())
    .output(
        ArtifactSchema::table("rust_entropy", 1)
            .role("observation")
            .field(FieldSchema::integer("snapshot").role("index").minimum(0.0))
            .field(
                FieldSchema::number("entropy")
                    .unit("normalized_entropy")
                    .role("observation")
                    .minimum(0.0)
                    .maximum(1.0),
            ),
    )
    .output(ArtifactSchema::json("rust_timing", 1).role("benchmark"))
    .primary_metric(
        MetricSpec::new("rust_median_batch_seconds", "seconds")
            .primary()
            .minimum(0.0),
    )
    .max_evaluations(((warmup + repeats + 1) * n) as u64)
    .build()?;

    let mut config = BridgeConfig::new(root).actor("rust-entropy-audit");
    if let Some(path) = a.get("python-path") {
        config = config.python_path(path);
    }
    let mut bridge = config.spawn()?;
    let (_, report) = bridge.with_research_run(&spec, |run| {
        let values = batch(&snapshots.data, &bounds.data, n, rows, cols, bins)?;
        run.consume(n as u64)?;
        for _ in 0..warmup {
            std::hint::black_box(batch(&snapshots.data, &bounds.data, n, rows, cols, bins)?);
            run.consume(n as u64)?;
        }
        let mut samples = Vec::with_capacity(repeats);
        for _ in 0..repeats {
            let start = Instant::now();
            std::hint::black_box(batch(&snapshots.data, &bounds.data, n, rows, cols, bins)?);
            samples.push(start.elapsed().as_secs_f64());
            run.consume(n as u64)?;
        }
        let mut sorted = samples.clone();
        sorted.sort_by(f64::total_cmp);
        let median = quantile(&sorted, 0.5);
        let rows_json: Vec<_> = values
            .iter()
            .enumerate()
            .map(|(i, h)| json!({"snapshot": i, "entropy": h}))
            .collect();
        run.emit(&ArtifactEmission::table(
            "rust_entropy",
            "rust_entropy.v1",
            json!(rows_json),
        ))?;
        run.emit(&ArtifactEmission::json(
            "rust_timing",
            "rust_timing.v1",
            json!({
                "implementation": "eigenbrains_sdk::kernels::normalized_histogram_entropy (Rust)",
                "build": if cfg!(debug_assertions) { "debug" } else { "release" },
                "snapshots": n, "warmup": warmup, "repeats": repeats,
                "samples_seconds": samples, "median": median,
                "q25": quantile(&sorted, 0.25), "q75": quantile(&sorted, 0.75),
                "min": sorted[0], "max": sorted[sorted.len() - 1],
            }),
        ))?;
        run.metric("rust_median_batch_seconds", median)
    })?;
    println!(
        "{}",
        json!({"run_id": report["run_id"], "status": report["status"]})
    );
    Ok(())
}
