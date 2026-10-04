use eigenbrains_sdk::{
    ArtifactEmission, ArtifactSchema, Bridge, FieldSchema, MetricSpec, ResearchExperimentSpec,
    ResourceBudget,
};
use serde_json::json;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let root = std::env::args().nth(1).unwrap_or_else(|| "study".into());
    let mut client = Bridge::spawn("python", root, "rust-example")?;
    let metric = MetricSpec {
        name: "runtime".into(),
        unit: "seconds".into(),
        role: "primary".into(),
        minimum: Some(0.0),
        maximum: None,
        censoring: None,
    };
    let spec = ResearchExperimentSpec {
        capability: "simulation".into(),
        hypothesis: "The Rust client records validated evidence.".into(),
        protocol: "protocols/simulation-v1.md".into(),
        parameters: json!({"samples": 2}),
        seed: 2026,
        outputs: vec![ArtifactSchema {
            name: "observations".into(),
            version: 1,
            kind: "table".into(),
            fields: vec![FieldSchema {
                name: "value".into(),
                dtype: "number".into(),
                unit: Some("score".into()),
                role: Some("observation".into()),
                nullable: false,
                minimum: None,
                maximum: None,
                censoring: None,
            }],
            dtype: None,
            ndim: None,
            unit: None,
            role: None,
            allow_extra_fields: false,
        }],
        primary_metric: metric,
        budget: ResourceBudget {
            max_evaluations: Some(2),
            max_seconds: Some(30.0),
        },
        runner: None,
        inputs: json!({}),
        reproduction_of: None,
    };
    let opened = client.begin_research_run(&spec)?;
    let run_id = opened["run_id"].as_str().expect("run id");
    client.consume_research_budget(run_id, 2)?;
    client.emit_research_artifact(
        run_id,
        &ArtifactEmission {
            name: "observations".into(),
            kind: "table".into(),
            value: json!([{"value": 0.25}, {"value": 0.75}]),
            schema: "observations.v1".into(),
            stage: "raw".into(),
            parents: vec![],
        },
    )?;
    client.record_research_metric(run_id, "runtime", 0.01, None)?;
    println!("{}", client.finalize_research_run(run_id)?);
    Ok(())
}
