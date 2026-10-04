//! Record one validated evidence run from Rust:
//! `cargo run --example evidence -- <lab root>` (needs `discolab` importable by Python).
use eigenbrains_sdk::{
    ArtifactEmission, ArtifactSchema, BridgeConfig, FieldSchema, MetricSpec, ResearchExperimentSpec,
};
use serde_json::json;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let root = std::env::args().nth(1).unwrap_or_else(|| "study".into());
    let mut client = BridgeConfig::new(root).actor("rust-example").spawn()?;
    let spec = ResearchExperimentSpec::builder(
        "simulation",
        "The Rust client records validated evidence.",
        "protocols/simulation-v1.md",
    )
    .seed(2026)
    .parameter("samples", json!(2))
    .output(
        ArtifactSchema::table("observations", 1).field(
            FieldSchema::number("value")
                .unit("score")
                .role("observation"),
        ),
    )
    .primary_metric(MetricSpec::new("runtime", "seconds").primary().minimum(0.0))
    .max_evaluations(2)
    .max_seconds(30.0)
    .build()?;
    let (_, report) = client.with_research_run(&spec, |run| {
        run.consume(2)?;
        run.emit(&ArtifactEmission::table(
            "observations",
            "observations.v1",
            json!([{"value": 0.25}, {"value": 0.75}]),
        ))?;
        run.metric("runtime", 0.01)
    })?;
    println!("{report}");
    Ok(())
}
