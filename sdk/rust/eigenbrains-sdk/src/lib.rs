//! EigenBrains Rust SDK.
//!
//! [`Bridge`] talks to the authoritative Python laboratory through the
//! versioned JSON-lines protocol. [`kernels`] contains dependency-free native
//! implementations intended for high-volume telemetry paths.

use serde_json::{json, Value};
use std::fmt::{Display, Formatter};
use std::io::{BufRead, BufReader, Write};
use std::path::Path;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};

pub const PROTOCOL_VERSION: &str = "1.0";

#[derive(Debug, Clone, Default)]
pub struct ResourceBudget {
    pub max_evaluations: Option<u64>,
    pub max_seconds: Option<f64>,
}

#[derive(Debug, Clone)]
pub struct FieldSchema {
    pub name: String,
    pub dtype: String,
    pub unit: Option<String>,
    pub role: Option<String>,
    pub nullable: bool,
    pub minimum: Option<f64>,
    pub maximum: Option<f64>,
    pub censoring: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ArtifactSchema {
    pub name: String,
    pub version: u32,
    pub kind: String,
    pub fields: Vec<FieldSchema>,
    pub dtype: Option<String>,
    pub ndim: Option<u32>,
    pub unit: Option<String>,
    pub role: Option<String>,
    pub allow_extra_fields: bool,
}

#[derive(Debug, Clone)]
pub struct MetricSpec {
    pub name: String,
    pub unit: String,
    pub role: String,
    pub minimum: Option<f64>,
    pub maximum: Option<f64>,
    pub censoring: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ResearchExperimentSpec {
    pub capability: String,
    pub hypothesis: String,
    pub protocol: String,
    pub parameters: Value,
    pub seed: i64,
    pub outputs: Vec<ArtifactSchema>,
    pub primary_metric: MetricSpec,
    pub budget: ResourceBudget,
    pub runner: Option<String>,
    pub inputs: Value,
    pub reproduction_of: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ArtifactEmission {
    pub name: String,
    pub kind: String,
    pub value: Value,
    pub schema: String,
    pub stage: String,
    pub parents: Vec<String>,
}

impl FieldSchema {
    fn as_json(&self) -> Value {
        json!({
            "name": self.name, "dtype": self.dtype, "unit": self.unit, "role": self.role,
            "nullable": self.nullable, "minimum": self.minimum, "maximum": self.maximum,
            "censoring": self.censoring,
        })
    }
}

impl ArtifactSchema {
    fn as_json(&self) -> Value {
        json!({
            "name": self.name, "version": self.version, "kind": self.kind,
            "fields": self.fields.iter().map(FieldSchema::as_json).collect::<Vec<_>>(),
            "dtype": self.dtype, "ndim": self.ndim, "unit": self.unit, "role": self.role,
            "allow_extra_fields": self.allow_extra_fields,
        })
    }
}

impl MetricSpec {
    fn as_json(&self) -> Value {
        json!({
            "name": self.name, "unit": self.unit, "role": self.role,
            "minimum": self.minimum, "maximum": self.maximum, "censoring": self.censoring,
        })
    }
}

impl ResearchExperimentSpec {
    fn as_json(&self) -> Value {
        json!({
            "capability": self.capability, "hypothesis": self.hypothesis,
            "protocol": self.protocol, "parameters": self.parameters, "seed": self.seed,
            "outputs": self.outputs.iter().map(ArtifactSchema::as_json).collect::<Vec<_>>(),
            "primary_metric": self.primary_metric.as_json(),
            "budget": {"max_evaluations": self.budget.max_evaluations,
                       "max_seconds": self.budget.max_seconds},
            "runner": self.runner, "inputs": self.inputs,
            "reproduction_of": self.reproduction_of,
        })
    }
}

#[derive(Debug)]
pub enum SdkError {
    Io(std::io::Error),
    Json(serde_json::Error),
    Protocol(String),
    Remote { code: String, message: String },
}

impl Display for SdkError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "I/O error: {e}"),
            Self::Json(e) => write!(f, "JSON error: {e}"),
            Self::Protocol(e) => write!(f, "EigenBrains protocol error: {e}"),
            Self::Remote { code, message } => {
                write!(f, "EigenBrains remote error {code}: {message}")
            }
        }
    }
}

impl std::error::Error for SdkError {}
impl From<std::io::Error> for SdkError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}
impl From<serde_json::Error> for SdkError {
    fn from(value: serde_json::Error) -> Self {
        Self::Json(value)
    }
}

pub struct Bridge {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

impl Bridge {
    pub fn spawn(python: &str, lab_root: impl AsRef<Path>, actor: &str) -> Result<Self, SdkError> {
        Self::spawn_command(Command::new(python), lab_root, actor)
    }

    /// Start the bridge with an explicit Python import root.
    ///
    /// This is useful for source checkouts and embedded applications where
    /// `discolab` has not been installed into the selected Python environment.
    pub fn spawn_with_python_path(
        python: &str,
        lab_root: impl AsRef<Path>,
        actor: &str,
        python_path: impl AsRef<Path>,
    ) -> Result<Self, SdkError> {
        let mut command = Command::new(python);
        command.env("PYTHONPATH", python_path.as_ref());
        Self::spawn_command(command, lab_root, actor)
    }

    fn spawn_command(
        mut command: Command,
        lab_root: impl AsRef<Path>,
        actor: &str,
    ) -> Result<Self, SdkError> {
        let mut child = command
            .args(["-m", "discolab.rpc", "--root"])
            .arg(lab_root.as_ref())
            .args(["--actor", actor])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| SdkError::Protocol("bridge stdin unavailable".into()))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| SdkError::Protocol("bridge stdout unavailable".into()))?;
        Ok(Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            next_id: 1,
        })
    }

    pub fn call(&mut self, method: &str, params: Value) -> Result<Value, SdkError> {
        let id = self.next_id;
        self.next_id += 1;
        let request =
            json!({"id": id, "version": PROTOCOL_VERSION, "method": method, "params": params});
        serde_json::to_writer(&mut self.stdin, &request)?;
        self.stdin.write_all(b"\n")?;
        self.stdin.flush()?;
        let mut line = String::new();
        if self.stdout.read_line(&mut line)? == 0 {
            return Err(SdkError::Protocol("bridge closed before replying".into()));
        }
        let response: Value = serde_json::from_str(&line)?;
        if response.get("id").and_then(Value::as_u64) != Some(id) {
            return Err(SdkError::Protocol(
                "response id does not match request".into(),
            ));
        }
        if response.get("version").and_then(Value::as_str) != Some(PROTOCOL_VERSION) {
            return Err(SdkError::Protocol(
                "response protocol version does not match client".into(),
            ));
        }
        if response.get("ok").and_then(Value::as_bool) != Some(true) {
            let code = response
                .pointer("/error/code")
                .and_then(Value::as_str)
                .unwrap_or("UnknownError");
            let message = response
                .pointer("/error/message")
                .and_then(Value::as_str)
                .unwrap_or("unknown error");
            return Err(SdkError::Remote {
                code: code.to_owned(),
                message: message.to_owned(),
            });
        }
        response
            .get("result")
            .cloned()
            .ok_or_else(|| SdkError::Protocol("successful response omitted result".into()))
    }

    pub fn initialize(&mut self) -> Result<Value, SdkError> {
        self.call("initialize", json!({}))
    }
    pub fn state(&mut self) -> Result<Value, SdkError> {
        self.call("state", json!({}))
    }
    pub fn events(&mut self) -> Result<Value, SdkError> {
        self.call("events", json!({}))
    }
    pub fn propose(&mut self, experiment: Value) -> Result<Value, SdkError> {
        self.call("propose", json!({"experiment": experiment}))
    }
    pub fn score(&mut self) -> Result<Value, SdkError> {
        self.call("score", json!({}))
    }
    pub fn select(&mut self, experiment_id: &str, justification: &str) -> Result<Value, SdkError> {
        self.call(
            "select",
            json!({"experiment_id": experiment_id, "justification": justification}),
        )
    }
    pub fn run(&mut self, confirm_heldout: bool) -> Result<Value, SdkError> {
        self.call("run", json!({"confirm_heldout": confirm_heldout}))
    }
    pub fn abort(&mut self, experiment_id: &str, reason: &str) -> Result<Value, SdkError> {
        self.call(
            "abort",
            json!({"experiment_id": experiment_id, "reason": reason}),
        )
    }
    pub fn result(&mut self, experiment_id: &str) -> Result<Value, SdkError> {
        self.call("result", json!({"experiment_id": experiment_id}))
    }
    pub fn analyze<I, S>(
        &mut self,
        experiment_id: &str,
        interpretation: &str,
        threats_to_validity: I,
    ) -> Result<Value, SdkError>
    where
        I: IntoIterator<Item = S>,
        S: AsRef<str>,
    {
        let threats: Vec<String> = threats_to_validity
            .into_iter()
            .map(|item| item.as_ref().to_owned())
            .collect();
        self.call(
            "analyze",
            json!({
                "experiment_id": experiment_id,
                "interpretation": interpretation,
                "threats_to_validity": threats,
            }),
        )
    }
    pub fn decide(
        &mut self,
        decision: &str,
        rationale: &str,
        next_experiment: Option<&str>,
    ) -> Result<Value, SdkError> {
        self.call(
            "decide",
            json!({
                "decision": decision,
                "rationale": rationale,
                "next_experiment": next_experiment,
            }),
        )
    }
    pub fn register_hypothesis(&mut self, hypothesis: Value) -> Result<Value, SdkError> {
        self.call("register_hypothesis", hypothesis)
    }

    pub fn begin_research_run(&mut self, spec: &ResearchExperimentSpec) -> Result<Value, SdkError> {
        self.call("research.begin", json!({"spec": spec.as_json()}))
    }

    pub fn emit_research_artifact(
        &mut self,
        run_id: &str,
        artifact: &ArtifactEmission,
    ) -> Result<Value, SdkError> {
        self.call(
            "research.emit",
            json!({
                "run_id": run_id, "name": artifact.name, "kind": artifact.kind,
                "value": artifact.value, "schema": artifact.schema,
                "stage": artifact.stage, "parents": artifact.parents,
            }),
        )
    }

    pub fn record_research_metric(
        &mut self,
        run_id: &str,
        name: &str,
        value: f64,
        spec: Option<&MetricSpec>,
    ) -> Result<Value, SdkError> {
        self.call(
            "research.metric",
            json!({
                "run_id": run_id, "name": name, "value": value,
                "spec": spec.map(MetricSpec::as_json),
            }),
        )
    }

    pub fn consume_research_budget(
        &mut self,
        run_id: &str,
        evaluations: u64,
    ) -> Result<Value, SdkError> {
        self.call(
            "research.consume",
            json!({"run_id": run_id, "evaluations": evaluations}),
        )
    }

    pub fn finalize_research_run(&mut self, run_id: &str) -> Result<Value, SdkError> {
        self.call("research.finalize", json!({"run_id": run_id}))
    }

    pub fn inspect_research_run(&mut self, run_id: &str) -> Result<Value, SdkError> {
        self.call("research.inspect", json!({"run_id": run_id}))
    }

    pub fn validate_research_run(&mut self, run_id: &str) -> Result<Value, SdkError> {
        self.call("research.validate", json!({"run_id": run_id}))
    }

    pub fn compare_research_runs(&mut self, left: &str, right: &str) -> Result<Value, SdkError> {
        self.call("research.compare", json!({"left": left, "right": right}))
    }

    pub fn accept_research_run(
        &mut self,
        run_id: &str,
        rationale: &str,
    ) -> Result<Value, SdkError> {
        self.call(
            "research.accept",
            json!({"run_id": run_id, "rationale": rationale}),
        )
    }

    pub fn reproduce_research_run(&mut self, run_id: &str) -> Result<Value, SdkError> {
        self.call("research.reproduce", json!({"run_id": run_id}))
    }
}

impl Drop for Bridge {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

pub mod kernels {
    /// Mean fixed-bin Shannon entropy across columns, normalized to [0, 1].
    pub fn normalized_histogram_entropy(
        points: &[f64],
        rows: usize,
        cols: usize,
        lower: f64,
        upper: f64,
        bins: usize,
    ) -> Result<f64, &'static str> {
        if rows == 0 || cols == 0 || points.len() != rows * cols {
            return Err("invalid matrix shape");
        }
        if bins < 2 || !lower.is_finite() || !upper.is_finite() || upper <= lower {
            return Err("invalid entropy bounds");
        }
        let width = (upper - lower) / bins as f64;
        let mut total = 0.0;
        let mut counts = vec![0usize; bins];
        for col in 0..cols {
            counts.fill(0);
            for row in 0..rows {
                let x = points[row * cols + col];
                if !x.is_finite() {
                    return Err("non-finite sample");
                }
                let idx = if x <= lower {
                    0
                } else if x >= upper {
                    bins - 1
                } else {
                    ((x - lower) / width).floor() as usize
                };
                counts[idx] += 1;
            }
            let h = counts
                .iter()
                .filter(|&&n| n > 0)
                .map(|&n| {
                    let p = n as f64 / rows as f64;
                    -p * p.ln()
                })
                .sum::<f64>();
            total += h / (bins as f64).ln();
        }
        Ok(total / cols as f64)
    }

    /// Mean of the worst `tail_probability` fraction (upper tail).
    pub fn cvar_upper(values: &[f64], tail_probability: f64) -> Result<f64, &'static str> {
        if values.is_empty() || !(0.0 < tail_probability && tail_probability <= 1.0) {
            return Err("invalid CVaR input");
        }
        let mut sorted = values.to_vec();
        if sorted.iter().any(|x| !x.is_finite()) {
            return Err("non-finite sample");
        }
        sorted.sort_by(|a, b| b.total_cmp(a));
        let n = ((sorted.len() as f64 * tail_probability).ceil() as usize).max(1);
        Ok(sorted[..n].iter().sum::<f64>() / n as f64)
    }

    /// Wilson score interval for a binomial proportion.
    pub fn wilson_interval(
        successes: u64,
        trials: u64,
        z: f64,
    ) -> Result<(f64, f64, f64), &'static str> {
        if trials == 0 || successes > trials || !z.is_finite() || z <= 0.0 {
            return Err("invalid Wilson input");
        }
        let n = trials as f64;
        let p = successes as f64 / n;
        let z2 = z * z;
        let center = (p + z2 / (2.0 * n)) / (1.0 + z2 / n);
        let half = z * ((p * (1.0 - p) / n + z2 / (4.0 * n * n)).sqrt()) / (1.0 + z2 / n);
        Ok((p, (center - half).max(0.0), (center + half).min(1.0)))
    }
}

#[cfg(test)]
mod tests {
    use super::{
        kernels::*, ArtifactEmission, ArtifactSchema, Bridge, FieldSchema, MetricSpec,
        ResearchExperimentSpec, ResourceBudget, SdkError,
    };
    use serde_json::{json, Value};
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn entropy_extremes() {
        assert_eq!(
            normalized_histogram_entropy(&[0.0; 8], 4, 2, -1.0, 1.0, 4).unwrap(),
            0.0
        );
        let spread = [-0.9, -0.9, -0.3, -0.3, 0.3, 0.3, 0.9, 0.9];
        assert!(
            (normalized_histogram_entropy(&spread, 4, 2, -1.0, 1.0, 4).unwrap() - 1.0).abs()
                < 1e-12
        );
    }

    #[test]
    fn cvar_and_wilson_are_bounded() {
        assert_eq!(cvar_upper(&[1.0, 2.0, 3.0, 4.0], 0.5).unwrap(), 3.5);
        let (p, lo, hi) = wilson_interval(7, 10, 1.959963984540054).unwrap();
        assert!((p - 0.7).abs() < 1e-12);
        assert!((lo - 0.39677814746114537).abs() < 1e-12);
        assert!((hi - 0.8922087325936989).abs() < 1e-12);
    }

    #[test]
    fn python_bridge_round_trip_preserves_remote_errors() {
        let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let python_path = manifest.join("../../../discolab").canonicalize().unwrap();
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let lab_root = std::env::temp_dir().join(format!(
            "eigenbrains-rust-sdk-{}-{nonce}",
            std::process::id(),
        ));
        let python = std::env::var("PYTHON").unwrap_or_else(|_| "python".to_owned());
        let mut bridge =
            Bridge::spawn_with_python_path(&python, &lab_root, "rust-sdk-test", &python_path)
                .unwrap();

        bridge.initialize().unwrap();
        let proposed = bridge
            .propose(json!({
                "kind": "prediction",
                "title": "Rust bridge contract",
                "rationale": "Exercise validated lifecycle transitions.",
                "hypotheses": ["H1"],
                "landscapes": ["rastrigin", "ackley"],
                "n_seeds": 4,
                "feature_sets": ["fitness", "fitness+entropy"],
                "controllers": null,
            }))
            .unwrap();
        let experiment_id = proposed.get("id").and_then(Value::as_str).unwrap();
        bridge.score().unwrap();
        bridge
            .select(experiment_id, "highest deterministic utility")
            .unwrap();
        assert_eq!(bridge.state().unwrap()["selected"], experiment_id);
        assert!(!bridge.events().unwrap().as_array().unwrap().is_empty());

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
            hypothesis: "The native client records validated evidence.".into(),
            protocol: "rust-inline-protocol".into(),
            parameters: json!({"iterations": 1}),
            seed: 7,
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
                    minimum: Some(0.0),
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
                max_evaluations: Some(1),
                max_seconds: None,
            },
            runner: None,
            inputs: json!({}),
            reproduction_of: None,
        };
        let opened = bridge.begin_research_run(&spec).unwrap();
        let research_id = opened["run_id"].as_str().unwrap();
        bridge.consume_research_budget(research_id, 1).unwrap();
        bridge
            .emit_research_artifact(
                research_id,
                &ArtifactEmission {
                    name: "observations".into(),
                    kind: "table".into(),
                    value: json!([{"value": 1.0}]),
                    schema: "observations.v1".into(),
                    stage: "raw".into(),
                    parents: vec![],
                },
            )
            .unwrap();
        bridge
            .record_research_metric(research_id, "runtime", 0.01, None)
            .unwrap();
        let validation = bridge.finalize_research_run(research_id).unwrap();
        assert_eq!(validation["valid"], true);

        match bridge.call("not-a-method", json!({})) {
            Err(SdkError::Remote { code, message }) => {
                assert_eq!(code, "ValueError");
                assert!(message.contains("unknown SDK method"));
            }
            other => panic!("expected structured remote error, got {other:?}"),
        }

        drop(bridge);
        std::fs::remove_dir_all(lab_root).unwrap();
    }
}
