//! Independently recompute a Python-produced entropy artifact and record the
//! result through the shared protocol-v1 evidence store.

use eigenbrains_sdk::kernels::normalized_histogram_entropy;
use eigenbrains_sdk::npy::read_f64;
use eigenbrains_sdk::{
    ArtifactEmission, ArtifactSchema, BridgeConfig, MetricSpec, ResearchExperimentSpec,
};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::time::Instant;

fn argument(index: usize, label: &str) -> Result<PathBuf, Box<dyn std::error::Error>> {
    std::env::args()
        .nth(index)
        .map(PathBuf::from)
        .ok_or_else(|| format!("missing {label} argument").into())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let root = argument(1, "evidence root")?;
    let population_path = argument(2, "population .npy")?;
    let reference_path = argument(3, "Python reference JSON")?;
    let protocol_path = argument(4, "protocol")?;
    let python_path = argument(5, "discolab source path")?;

    let reference: Value = serde_json::from_str(&std::fs::read_to_string(&reference_path)?)?;
    let population = read_f64(&population_path)?;
    if population.shape.len() != 2 {
        return Err("population must be a two-dimensional float64 array".into());
    }
    let rows = population.shape[0];
    let columns = population.shape[1];
    let details = &reference["population"];
    if rows != details["rows"].as_u64().unwrap_or_default() as usize
        || columns != details["columns"].as_u64().unwrap_or_default() as usize
    {
        return Err("population shape does not match the Python reference".into());
    }
    let lower = details["lower"]
        .as_f64()
        .ok_or("reference lacks lower bound")?;
    let upper = details["upper"]
        .as_f64()
        .ok_or("reference lacks upper bound")?;
    let bins = details["bins"]
        .as_u64()
        .ok_or("reference lacks bin count")? as usize;

    let started = Instant::now();
    let entropy =
        normalized_histogram_entropy(&population.data, rows, columns, lower, upper, bins)?;
    let compute_seconds = started.elapsed().as_secs_f64();
    let python_entropy = reference["entropy"]
        .as_f64()
        .ok_or("reference lacks entropy")?;
    let difference = (entropy - python_entropy).abs();

    let output = json!({
        "language": "rust",
        "implementation": "eigenbrains_sdk::kernels::normalized_histogram_entropy",
        "entropy": entropy,
        "python_reference": python_entropy,
        "abs_difference": difference,
        "native_compute_seconds": compute_seconds,
        "shape": [rows, columns],
        "bins": bins,
    });
    let spec = ResearchExperimentSpec::builder(
        "native-entropy-audit",
        "Rust independently reproduces entropy from the Python NumPy artifact.",
        protocol_path.to_string_lossy(),
    )
    .seed(2026)
    .input("population", population_path.to_string_lossy())
    .input("python_reference", reference_path.to_string_lossy())
    .output(ArtifactSchema::json("rust_entropy", 1).role("analysis"))
    .primary_metric(
        MetricSpec::new("native_compute_seconds", "seconds")
            .primary()
            .minimum(0.0),
    )
    .max_evaluations(1)
    .max_seconds(30.0)
    .build()?;

    let mut client = BridgeConfig::new(root)
        .actor("rust-interop-auditor")
        .python_path(python_path)
        .spawn()?;
    let ((), report) = client.with_research_run(&spec, |run| {
        run.consume(1)?;
        run.emit(&ArtifactEmission::json(
            "rust_entropy",
            "rust_entropy.v1",
            output.clone(),
        ))?;
        run.metric("native_compute_seconds", compute_seconds)?;
        Ok(())
    })?;
    let run_id = report["run_id"]
        .as_str()
        .ok_or("validation report omitted run_id")?;
    println!(
        "{}",
        json!({"language": "rust", "run_id": run_id, "entropy": entropy,
               "abs_difference": difference, "native_compute_seconds": compute_seconds})
    );
    Ok(())
}
