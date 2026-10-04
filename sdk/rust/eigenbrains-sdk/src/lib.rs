//! EigenBrains Rust SDK.
//!
//! [`Bridge`] talks to the authoritative Python runtime through the versioned
//! JSON-lines protocol (a Python sidecar process is required). [`contracts`]
//! holds typed, validated evidence specs with builders; [`kernels`] contains
//! dependency-free native implementations for high-volume telemetry paths;
//! [`npy`] reads the float64 arrays the Python runtime emits.

pub mod contracts;
pub mod kernels;
pub mod npy;

pub use contracts::{
    is_valid_name, ArtifactSchema, FieldSchema, MetricSpec, ResearchExperimentSpec,
    ResearchExperimentSpecBuilder, ResourceBudget,
};

use serde_json::{json, Map, Value};
use std::fmt::{Display, Formatter};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};

pub const PROTOCOL_VERSION: &str = "1.0";

/// Every protocol-v1 method this client implements (checked against the
/// schema and the shared contract fixtures in the test suite).
pub const METHODS: &[&str] = &[
    "describe",
    "initialize",
    "state",
    "events",
    "propose",
    "score",
    "select",
    "run",
    "abort",
    "result",
    "analyze",
    "decide",
    "register_hypothesis",
    "research.begin",
    "research.emit",
    "research.metric",
    "research.consume",
    "research.checkpoint",
    "research.resume",
    "research.fail",
    "research.finalize",
    "research.inspect",
    "research.validate",
    "research.list",
    "research.compare",
    "research.accept",
    "research.reject",
    "research.reproduce",
    "research.lineage",
    "research.export_bundle",
    "research.verify_bundle",
];

#[derive(Debug, Clone)]
pub struct ArtifactEmission {
    pub name: String,
    pub kind: String,
    pub value: Value,
    pub schema: String,
    pub stage: String,
    pub parents: Vec<String>,
}

impl ArtifactEmission {
    fn of(kind: &str, name: impl Into<String>, schema_id: impl Into<String>, value: Value) -> Self {
        Self {
            name: name.into(),
            kind: kind.into(),
            value,
            schema: schema_id.into(),
            stage: "raw".into(),
            parents: Vec::new(),
        }
    }
    pub fn table(name: impl Into<String>, schema_id: impl Into<String>, rows: Value) -> Self {
        Self::of("table", name, schema_id, rows)
    }
    pub fn json(name: impl Into<String>, schema_id: impl Into<String>, value: Value) -> Self {
        Self::of("json", name, schema_id, value)
    }
    pub fn array(name: impl Into<String>, schema_id: impl Into<String>, value: Value) -> Self {
        Self::of("array", name, schema_id, value)
    }
    /// `derived` or `analysis` artifacts must name their parents.
    pub fn stage(mut self, stage: impl Into<String>) -> Self {
        self.stage = stage.into();
        self
    }
    pub fn parent(mut self, parent: impl Into<String>) -> Self {
        self.parents.push(parent.into());
        self
    }
}

/// Filters for `research.list`; times are ISO-8601 strings (inclusive bounds).
#[derive(Debug, Clone, Default)]
pub struct RunFilter {
    pub capability: Option<String>,
    pub status: Option<String>,
    pub seed: Option<i64>,
    pub created_after: Option<String>,
    pub created_before: Option<String>,
}

impl RunFilter {
    fn to_json(&self) -> Value {
        let mut map = Map::new();
        let mut put = |key: &str, value: Value| {
            if !value.is_null() {
                map.insert(key.into(), value);
            }
        };
        put("capability", json!(self.capability));
        put("status", json!(self.status));
        put("seed", json!(self.seed));
        put("created_after", json!(self.created_after));
        put("created_before", json!(self.created_before));
        Value::Object(map)
    }
}

#[derive(Debug)]
pub enum SdkError {
    Io(std::io::Error),
    Json(serde_json::Error),
    Protocol(String),
    /// Rejected locally before anything was sent (contract validation).
    Invalid(String),
    Remote {
        code: String,
        message: String,
    },
}

impl SdkError {
    /// Error type name recorded when a scoped run fails.
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Io(_) => "RustIoError",
            Self::Json(_) => "RustJsonError",
            Self::Protocol(_) => "RustProtocolError",
            Self::Invalid(_) => "RustValidationError",
            Self::Remote { .. } => "RemoteError",
        }
    }
}

impl Display for SdkError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "I/O error: {e}"),
            Self::Json(e) => write!(f, "JSON error: {e}"),
            Self::Protocol(e) => write!(f, "EigenBrains protocol error: {e}"),
            Self::Invalid(e) => write!(f, "invalid evidence contract: {e}"),
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

/// How to start the Python sidecar.
#[derive(Debug, Clone)]
pub struct BridgeConfig {
    python: String,
    root: PathBuf,
    actor: String,
    python_path: Option<PathBuf>,
    allowed_runner_modules: Vec<String>,
}

impl BridgeConfig {
    pub fn new(root: impl AsRef<Path>) -> Self {
        Self {
            python: std::env::var("PYTHON").unwrap_or_else(|_| "python".to_owned()),
            root: root.as_ref().to_path_buf(),
            actor: "rust-sdk".into(),
            python_path: None,
            allowed_runner_modules: Vec::new(),
        }
    }
    pub fn python(mut self, python: impl Into<String>) -> Self {
        self.python = python.into();
        self
    }
    pub fn actor(mut self, actor: impl Into<String>) -> Self {
        self.actor = actor.into();
        self
    }
    /// Import root for source checkouts where `discolab` is not installed.
    pub fn python_path(mut self, path: impl AsRef<Path>) -> Self {
        self.python_path = Some(path.as_ref().to_path_buf());
        self
    }
    /// Permit runs that name a Python runner in this module (default: none).
    pub fn allow_runner_module(mut self, module: impl Into<String>) -> Self {
        self.allowed_runner_modules.push(module.into());
        self
    }
    pub fn spawn(self) -> Result<Bridge, SdkError> {
        let mut command = Command::new(&self.python);
        if let Some(path) = &self.python_path {
            command.env("PYTHONPATH", path);
        }
        command
            .args(["-m", "discolab.rpc", "--root"])
            .arg(&self.root)
            .args(["--actor", &self.actor]);
        for module in &self.allowed_runner_modules {
            command.args(["--allow-runner-module", module]);
        }
        let mut child = command
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
        Ok(Bridge {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            next_id: 1,
        })
    }
}

pub struct Bridge {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

/// An open evidence run borrowed from a [`Bridge`] inside
/// [`Bridge::with_research_run`] / [`Bridge::with_resumed_research_run`].
pub struct ResearchRun<'a> {
    bridge: &'a mut Bridge,
    run_id: String,
}

impl ResearchRun<'_> {
    pub fn id(&self) -> &str {
        &self.run_id
    }
    pub fn emit(&mut self, artifact: &ArtifactEmission) -> Result<Value, SdkError> {
        self.bridge.emit_research_artifact(&self.run_id, artifact)
    }
    pub fn metric(&mut self, name: &str, value: f64) -> Result<Value, SdkError> {
        self.bridge
            .record_research_metric(&self.run_id, name, value, None)
    }
    pub fn metric_with_spec(&mut self, spec: &MetricSpec, value: f64) -> Result<Value, SdkError> {
        self.bridge
            .record_research_metric(&self.run_id, &spec.name, value, Some(spec))
    }
    pub fn consume(&mut self, evaluations: u64) -> Result<Value, SdkError> {
        self.bridge
            .consume_research_budget(&self.run_id, evaluations)
    }
    pub fn checkpoint(&mut self, state: Value) -> Result<Value, SdkError> {
        self.bridge.checkpoint_research_run(&self.run_id, state)
    }
}

impl Bridge {
    pub fn spawn(python: &str, lab_root: impl AsRef<Path>, actor: &str) -> Result<Self, SdkError> {
        BridgeConfig::new(lab_root)
            .python(python)
            .actor(actor)
            .spawn()
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
        BridgeConfig::new(lab_root)
            .python(python)
            .actor(actor)
            .python_path(python_path)
            .spawn()
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

    pub fn describe(&mut self) -> Result<Value, SdkError> {
        self.call("describe", json!({}))
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

    /// Validates the spec locally, then opens a run in the sidecar.
    pub fn begin_research_run(&mut self, spec: &ResearchExperimentSpec) -> Result<Value, SdkError> {
        spec.validate()?;
        self.call("research.begin", json!({"spec": spec.to_json()}))
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
                "spec": spec.map(MetricSpec::to_json),
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

    pub fn checkpoint_research_run(
        &mut self,
        run_id: &str,
        state: Value,
    ) -> Result<Value, SdkError> {
        self.call(
            "research.checkpoint",
            json!({"run_id": run_id, "state": state}),
        )
    }

    pub fn resume_research_run(&mut self, run_id: &str) -> Result<Value, SdkError> {
        self.call("research.resume", json!({"run_id": run_id}))
    }

    pub fn fail_research_run(
        &mut self,
        run_id: &str,
        error_type: &str,
        message: &str,
    ) -> Result<Value, SdkError> {
        self.call(
            "research.fail",
            json!({"run_id": run_id, "error_type": error_type, "message": message}),
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

    pub fn list_research_runs(&mut self, filter: &RunFilter) -> Result<Value, SdkError> {
        self.call("research.list", filter.to_json())
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

    pub fn reject_research_run(&mut self, run_id: &str, reason: &str) -> Result<Value, SdkError> {
        self.call(
            "research.reject",
            json!({"run_id": run_id, "reason": reason}),
        )
    }

    pub fn reproduce_research_run(&mut self, run_id: &str) -> Result<Value, SdkError> {
        self.call("research.reproduce", json!({"run_id": run_id}))
    }

    pub fn research_lineage(&mut self) -> Result<Value, SdkError> {
        self.call("research.lineage", json!({}))
    }

    /// Writes `<lab root>/bundles/<name>.zip`; `name` must be a plain name.
    pub fn export_research_bundle(
        &mut self,
        run_ids: &[&str],
        name: &str,
    ) -> Result<Value, SdkError> {
        self.call(
            "research.export_bundle",
            json!({"run_ids": run_ids, "name": name}),
        )
    }

    pub fn verify_research_bundle(&mut self, name: &str) -> Result<Value, SdkError> {
        self.call("research.verify_bundle", json!({"name": name}))
    }

    /// Open a run, give it to `body`, and finalize it when `body` succeeds.
    /// Any error from `body` or from finalization records the run as failed
    /// before being returned (the Rust counterpart of Python's
    /// `with store.begin(spec) as run:`). Returns `body`'s value and the
    /// validation report.
    pub fn with_research_run<T, F>(
        &mut self,
        spec: &ResearchExperimentSpec,
        body: F,
    ) -> Result<(T, Value), SdkError>
    where
        F: FnOnce(&mut ResearchRun<'_>) -> Result<T, SdkError>,
    {
        let opened = self.begin_research_run(spec)?;
        let run_id = opened["run_id"]
            .as_str()
            .ok_or_else(|| SdkError::Protocol("research.begin returned no run id".into()))?
            .to_owned();
        self.drive(run_id, |run| body(run))
    }

    /// Reopen an interrupted run from its last checkpoint and continue it in
    /// `body`, which receives the restored state saved by `checkpoint`.
    pub fn with_resumed_research_run<T, F>(
        &mut self,
        run_id: &str,
        body: F,
    ) -> Result<(T, Value), SdkError>
    where
        F: FnOnce(&mut ResearchRun<'_>, Value) -> Result<T, SdkError>,
    {
        let resumed = self.resume_research_run(run_id)?;
        let state = resumed.get("state").cloned().unwrap_or(Value::Null);
        self.drive(run_id.to_owned(), |run| body(run, state))
    }

    fn drive<T, F>(&mut self, run_id: String, body: F) -> Result<(T, Value), SdkError>
    where
        F: FnOnce(&mut ResearchRun<'_>) -> Result<T, SdkError>,
    {
        let outcome = {
            let mut run = ResearchRun {
                bridge: self,
                run_id: run_id.clone(),
            };
            body(&mut run)
        };
        let value = match outcome {
            Ok(value) => value,
            Err(error) => {
                let _ = self.fail_research_run(&run_id, error.kind(), &error.to_string());
                return Err(error);
            }
        };
        match self.finalize_research_run(&run_id) {
            Ok(report) => Ok((value, report)),
            Err(error) => {
                let _ = self.fail_research_run(&run_id, error.kind(), &error.to_string());
                Err(error)
            }
        }
    }
}

impl Drop for Bridge {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[cfg(test)]
mod tests {
    use super::kernels::*;
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    const SCHEMA: &str = include_str!("../../../protocol/v1/schema.json");
    const CONTRACTS: &str = include_str!("../../../protocol/v1/contract-fixtures.json");
    const PARITY: &str = include_str!("../../../protocol/v1/parity-fixtures.json");

    fn temp_root(tag: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!(
            "eigenbrains-rust-{tag}-{}-{nonce}",
            std::process::id()
        ))
    }

    fn bridge(root: &Path) -> Bridge {
        let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let python_path = manifest.join("../../../discolab").canonicalize().unwrap();
        BridgeConfig::new(root)
            .actor("rust-sdk-test")
            .python_path(python_path)
            .spawn()
            .unwrap()
    }

    fn observation_spec(seed: i64) -> ResearchExperimentSpec {
        ResearchExperimentSpec::builder(
            "simulation",
            "The native client records validated evidence.",
            "rust-inline-protocol",
        )
        .seed(seed)
        .parameter("iterations", json!(1))
        .output(
            ArtifactSchema::table("observations", 1).field(
                FieldSchema::number("value")
                    .unit("score")
                    .role("observation")
                    .minimum(0.0),
            ),
        )
        .primary_metric(MetricSpec::new("runtime", "seconds").primary().minimum(0.0))
        .max_evaluations(4)
        .build()
        .unwrap()
    }

    #[test]
    fn entropy_extremes_and_parity_fixture() {
        assert_eq!(
            normalized_histogram_entropy(&[0.0; 8], 4, 2, -1.0, 1.0, 4).unwrap(),
            0.0
        );
        let fixture: Value = serde_json::from_str(PARITY).unwrap();
        let e = &fixture["entropy"];
        let points: Vec<f64> = e["points_row_major"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_f64().unwrap())
            .collect();
        let got = normalized_histogram_entropy(
            &points,
            e["rows"].as_u64().unwrap() as usize,
            e["cols"].as_u64().unwrap() as usize,
            e["lower"].as_f64().unwrap(),
            e["upper"].as_f64().unwrap(),
            e["bins"].as_u64().unwrap() as usize,
        )
        .unwrap();
        assert!((got - e["expected"].as_f64().unwrap()).abs() < 1e-12);
    }

    #[test]
    fn pairwise_sum_matches_reference_blocks() {
        let values: Vec<f64> = (0..300).map(|i| 1.0 / (i as f64 + 1.0)).collect();
        let naive: f64 = values.iter().sum();
        assert!((pairwise_sum(&values) - naive).abs() < 1e-12);
        assert_eq!(pairwise_sum(&[1.0, 2.0, 3.0]), 6.0);
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
    fn npy_reader_parses_numpy_v1_headers_and_refuses_other_dtypes() {
        let mut header = "{'descr': '<f8', 'fortran_order': False, 'shape': (2, 3), }".to_string();
        while !(10 + header.len() + 1).is_multiple_of(64) {
            header.push(' ');
        }
        header.push('\n');
        let mut bytes = b"\x93NUMPY\x01\x00".to_vec();
        bytes.extend_from_slice(&(header.len() as u16).to_le_bytes());
        bytes.extend_from_slice(header.as_bytes());
        for v in [1.0f64, 2.0, 3.0, 4.0, 5.0, 6.5] {
            bytes.extend_from_slice(&v.to_le_bytes());
        }
        let array = npy::parse_f64(&bytes).unwrap();
        assert_eq!(array.shape, vec![2, 3]);
        assert_eq!(array.data[5], 6.5);
        let mut wrong = bytes.clone();
        let at = wrong.windows(3).position(|w| w == b"<f8").unwrap();
        wrong[at + 2] = b'4';
        assert!(npy::parse_f64(&wrong).is_err());
        assert!(npy::parse_f64(&bytes[..bytes.len() - 1]).is_err());
    }

    #[test]
    fn client_methods_match_schema_and_contract_fixtures() {
        let schema: Value = serde_json::from_str(SCHEMA).unwrap();
        let declared: Vec<&str> = schema["$defs"]["request"]["properties"]["method"]["enum"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        assert_eq!(declared, METHODS);
        let contracts: Value = serde_json::from_str(CONTRACTS).unwrap();
        let methods: Vec<&str> = contracts["methods"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_str().unwrap())
            .collect();
        assert_eq!(methods, METHODS);
    }

    #[test]
    fn canonical_spec_round_trips_and_builder_matches_python() {
        let contracts: Value = serde_json::from_str(CONTRACTS).unwrap();
        let canonical = &contracts["canonical_spec"];
        let parsed = ResearchExperimentSpec::from_json(canonical).unwrap();
        assert_eq!(&parsed.to_json(), canonical);

        let built = ResearchExperimentSpec::builder(
            "optimization",
            "Population entropy adds early-warning information beyond fitness history.",
            "protocols/early-warning-v1.yaml",
        )
        .seed(2026)
        .parameter("population", json!(50))
        .parameter("landscape", json!("rastrigin"))
        .parameter("rates", json!([0.5, 1.0, 2.0]))
        .parameter("nested", json!({"horizon": 10}))
        .output(
            ArtifactSchema::table("trajectory", 1)
                .field(
                    FieldSchema::integer("generation")
                        .unit("generations")
                        .role("index")
                        .minimum(0.0),
                )
                .field(
                    FieldSchema::number("best_error")
                        .unit("objective")
                        .role("observation")
                        .minimum(0.0),
                )
                .field(
                    FieldSchema::number("entropy")
                        .unit("normalized_entropy")
                        .role("observation")
                        .minimum(0.0)
                        .maximum(1.0),
                )
                .field(
                    FieldSchema::number("recovery")
                        .unit("generations")
                        .role("outcome")
                        .nullable(true)
                        .minimum(0.0)
                        .censoring("right"),
                )
                .field(FieldSchema::string("landscape").role("stratum"))
                .field(FieldSchema::boolean("improved").role("label")),
        )
        .output(
            ArtifactSchema::array("populations", 2, "float64")
                .ndim(3)
                .unit("decision_space")
                .role("state"),
        )
        .output(ArtifactSchema::json("summary", 1).role("analysis"))
        .primary_metric(
            MetricSpec::new("delta_auroc", "auroc")
                .primary()
                .minimum(-1.0)
                .maximum(1.0),
        )
        .budget(ResourceBudget::default().evaluations(100000).seconds(600.0))
        .build()
        .unwrap();
        assert_eq!(&built.to_json(), canonical);
    }

    #[test]
    fn every_invalid_contract_case_is_rejected_like_python() {
        let contracts: Value = serde_json::from_str(CONTRACTS).unwrap();
        for case in contracts["invalid_specs"].as_array().unwrap() {
            let mut spec = contracts["canonical_spec"].clone();
            let path = case["path"].as_array().unwrap();
            let mut node = &mut spec;
            for key in &path[..path.len() - 1] {
                node = match key {
                    Value::String(k) => node.get_mut(k.as_str()).unwrap(),
                    Value::Number(i) => node.get_mut(i.as_u64().unwrap() as usize).unwrap(),
                    _ => unreachable!(),
                };
            }
            match path.last().unwrap() {
                Value::String(k) => node[k.as_str()] = case["value"].clone(),
                Value::Number(i) => node[i.as_u64().unwrap() as usize] = case["value"].clone(),
                _ => unreachable!(),
            }
            assert!(
                ResearchExperimentSpec::from_json(&spec).is_err(),
                "accepted invalid case: {}",
                case["case"]
            );
        }
        assert!(matches!(
            ResearchExperimentSpec::builder("x", "h", "p").build(),
            Err(SdkError::Invalid(_))
        ));
    }

    #[test]
    fn python_bridge_round_trip_preserves_remote_errors() {
        let lab_root = temp_root("lab");
        let mut bridge = bridge(&lab_root);
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
        let described = bridge.describe().unwrap();
        assert_eq!(described["runner_policy"], "none");
        assert_eq!(
            described["methods"].as_array().unwrap().len(),
            METHODS.len()
        );

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

    #[test]
    fn scoped_runs_lifecycle_checkpoint_resume_and_bundles() {
        let root = temp_root("evidence");
        let mut bridge = bridge(&root);

        let (rows, report) = bridge
            .with_research_run(&observation_spec(7), |run| {
                run.consume(1)?;
                run.emit(&ArtifactEmission::table(
                    "observations",
                    "observations.v1",
                    json!([{"value": 1.0}]),
                ))?;
                run.metric("runtime", 0.01)?;
                Ok(1)
            })
            .unwrap();
        assert_eq!(rows, 1);
        assert_eq!(report["valid"], true);
        let accepted_id = report["run_id"].as_str().unwrap().to_owned();

        let failed = bridge.with_research_run(&observation_spec(8), |run| {
            run.consume(1)?;
            Err::<(), _>(SdkError::Invalid("simulated client failure".into()))
        });
        assert!(matches!(failed, Err(SdkError::Invalid(_))));
        let failed_runs = bridge
            .list_research_runs(&RunFilter {
                status: Some("failed".into()),
                ..RunFilter::default()
            })
            .unwrap();
        assert_eq!(failed_runs.as_array().unwrap().len(), 1);
        assert_eq!(failed_runs[0]["seed"], 8);

        // Interrupt a run after a checkpoint, then continue it from a new bridge process.
        let opened = bridge.begin_research_run(&observation_spec(9)).unwrap();
        let interrupted = opened["run_id"].as_str().unwrap().to_owned();
        bridge.consume_research_budget(&interrupted, 2).unwrap();
        bridge
            .checkpoint_research_run(&interrupted, json!({"cursor": 2}))
            .unwrap();
        drop(bridge);
        let mut bridge = super::tests::bridge(&root);
        let (cursor, resumed) = bridge
            .with_resumed_research_run(&interrupted, |run, state| {
                run.emit(&ArtifactEmission::table(
                    "observations",
                    "observations.v1",
                    json!([{"value": 2.0}]),
                ))?;
                run.metric("runtime", 0.02)?;
                Ok(state["cursor"].as_i64().unwrap())
            })
            .unwrap();
        assert_eq!(cursor, 2);
        assert_eq!(resumed["status"], "validated");

        bridge
            .accept_research_run(&accepted_id, "registered checks passed")
            .unwrap();
        let rejected = bridge
            .reject_research_run(&interrupted, "exercise rejection")
            .unwrap();
        assert_eq!(rejected["status"], "rejected_as_evidence");
        match bridge.accept_research_run(&interrupted, "too late") {
            Err(SdkError::Remote { code, .. }) => assert_eq!(code, "EvidenceError"),
            other => panic!("decisions must be terminal, got {other:?}"),
        }
        let bundle = bridge
            .export_research_bundle(&[accepted_id.as_str(), interrupted.as_str()], "rust-test")
            .unwrap();
        let verified = bridge.verify_research_bundle("rust-test").unwrap();
        assert_eq!(verified["valid"], true);
        assert_eq!(verified["content_sha256"], bundle["content_sha256"]);
        assert!(bridge
            .export_research_bundle(&[accepted_id.as_str()], "../escape")
            .is_err());
        drop(bridge);
        std::fs::remove_dir_all(root).unwrap();
    }
}
