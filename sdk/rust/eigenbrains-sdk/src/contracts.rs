//! Typed evidence contracts mirroring Python's `ExperimentSpecV2`.
//!
//! Every type has a fluent builder and `validate()` applies the same rules as
//! the authoritative Python dataclasses, so an invalid spec is rejected before
//! it reaches the bridge. `to_json`/`from_json` round-trip the canonical JSON
//! form checked against `sdk/protocol/v1/contract-fixtures.json`.

use crate::SdkError;
use serde_json::{json, Map, Value};

pub const FIELD_DTYPES: &[&str] = &["number", "integer", "string", "boolean"];
pub const ARTIFACT_KINDS: &[&str] = &["table", "array", "json"];
pub const METRIC_ROLES: &[&str] = &["primary", "secondary", "diagnostic"];
pub const CENSORING: &[&str] = &["right", "left", "interval"];
pub const STAGES: &[&str] = &["raw", "derived", "analysis"];

/// `^[A-Za-z][A-Za-z0-9_.-]{0,127}$`, the protocol's name pattern.
pub fn is_valid_name(value: &str) -> bool {
    let mut chars = value.chars();
    match chars.next() {
        Some(first) if first.is_ascii_alphabetic() => {}
        _ => return false,
    }
    value.len() <= 128
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '.' || c == '-')
}

fn invalid(message: impl Into<String>) -> SdkError {
    SdkError::Invalid(message.into())
}

fn check_name(value: &str, kind: &str) -> Result<(), SdkError> {
    if is_valid_name(value) {
        Ok(())
    } else {
        Err(invalid(format!("invalid {kind} name {value:?}")))
    }
}

fn check_range(min: Option<f64>, max: Option<f64>, label: &str) -> Result<(), SdkError> {
    if let (Some(lo), Some(hi)) = (min, max) {
        if lo > hi {
            return Err(invalid(format!("{label}: minimum exceeds maximum")));
        }
    }
    Ok(())
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct ResourceBudget {
    pub max_evaluations: Option<u64>,
    pub max_seconds: Option<f64>,
}

impl ResourceBudget {
    pub fn evaluations(mut self, value: u64) -> Self {
        self.max_evaluations = Some(value);
        self
    }
    pub fn seconds(mut self, value: f64) -> Self {
        self.max_seconds = Some(value);
        self
    }
    pub fn validate(&self) -> Result<(), SdkError> {
        if self.max_evaluations == Some(0) {
            return Err(invalid("max_evaluations must be positive"));
        }
        if matches!(self.max_seconds, Some(s) if s.is_nan() || s <= 0.0) {
            return Err(invalid("max_seconds must be positive"));
        }
        Ok(())
    }
    fn to_json(&self) -> Value {
        json!({"max_evaluations": self.max_evaluations, "max_seconds": self.max_seconds})
    }
}

#[derive(Debug, Clone, PartialEq)]
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

impl FieldSchema {
    pub fn new(name: impl Into<String>, dtype: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            dtype: dtype.into(),
            unit: None,
            role: None,
            nullable: false,
            minimum: None,
            maximum: None,
            censoring: None,
        }
    }
    pub fn number(name: impl Into<String>) -> Self {
        Self::new(name, "number")
    }
    pub fn integer(name: impl Into<String>) -> Self {
        Self::new(name, "integer")
    }
    pub fn string(name: impl Into<String>) -> Self {
        Self::new(name, "string")
    }
    pub fn boolean(name: impl Into<String>) -> Self {
        Self::new(name, "boolean")
    }
    pub fn unit(mut self, unit: impl Into<String>) -> Self {
        self.unit = Some(unit.into());
        self
    }
    pub fn role(mut self, role: impl Into<String>) -> Self {
        self.role = Some(role.into());
        self
    }
    pub fn nullable(mut self, nullable: bool) -> Self {
        self.nullable = nullable;
        self
    }
    pub fn minimum(mut self, value: f64) -> Self {
        self.minimum = Some(value);
        self
    }
    pub fn maximum(mut self, value: f64) -> Self {
        self.maximum = Some(value);
        self
    }
    pub fn censoring(mut self, censoring: impl Into<String>) -> Self {
        self.censoring = Some(censoring.into());
        self
    }
    pub fn validate(&self) -> Result<(), SdkError> {
        check_name(&self.name, "field")?;
        if !FIELD_DTYPES.contains(&self.dtype.as_str()) {
            return Err(invalid(format!(
                "field {}: unknown dtype {:?}",
                self.name, self.dtype
            )));
        }
        let numeric = self.dtype == "number" || self.dtype == "integer";
        if !numeric
            && (self.minimum.is_some() || self.maximum.is_some() || self.censoring.is_some())
        {
            return Err(invalid(format!(
                "field {}: ranges and censoring require a numeric dtype",
                self.name
            )));
        }
        check_range(self.minimum, self.maximum, &format!("field {}", self.name))?;
        if let Some(c) = &self.censoring {
            if !CENSORING.contains(&c.as_str()) {
                return Err(invalid(format!(
                    "field {}: unknown censoring {c:?}",
                    self.name
                )));
            }
        }
        Ok(())
    }
    fn to_json(&self) -> Value {
        json!({
            "name": self.name, "dtype": self.dtype, "unit": self.unit, "role": self.role,
            "nullable": self.nullable, "minimum": self.minimum, "maximum": self.maximum,
            "censoring": self.censoring,
        })
    }
}

#[derive(Debug, Clone, PartialEq)]
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

impl ArtifactSchema {
    fn with_kind(name: impl Into<String>, version: u32, kind: &str) -> Self {
        Self {
            name: name.into(),
            version,
            kind: kind.into(),
            fields: Vec::new(),
            dtype: None,
            ndim: None,
            unit: None,
            role: None,
            allow_extra_fields: false,
        }
    }
    pub fn table(name: impl Into<String>, version: u32) -> Self {
        Self::with_kind(name, version, "table")
    }
    pub fn array(name: impl Into<String>, version: u32, dtype: impl Into<String>) -> Self {
        let mut schema = Self::with_kind(name, version, "array");
        schema.dtype = Some(dtype.into());
        schema
    }
    pub fn json(name: impl Into<String>, version: u32) -> Self {
        Self::with_kind(name, version, "json")
    }
    pub fn field(mut self, field: FieldSchema) -> Self {
        self.fields.push(field);
        self
    }
    pub fn ndim(mut self, ndim: u32) -> Self {
        self.ndim = Some(ndim);
        self
    }
    pub fn unit(mut self, unit: impl Into<String>) -> Self {
        self.unit = Some(unit.into());
        self
    }
    pub fn role(mut self, role: impl Into<String>) -> Self {
        self.role = Some(role.into());
        self
    }
    pub fn allow_extra_fields(mut self, allow: bool) -> Self {
        self.allow_extra_fields = allow;
        self
    }
    /// Identifier used when emitting an artifact: `name.v<version>`.
    pub fn id(&self) -> String {
        format!("{}.v{}", self.name, self.version)
    }
    pub fn validate(&self) -> Result<(), SdkError> {
        check_name(&self.name, "schema")?;
        if self.version == 0 {
            return Err(invalid("schema version must be positive"));
        }
        if !ARTIFACT_KINDS.contains(&self.kind.as_str()) {
            return Err(invalid(format!(
                "schema {}: unknown kind {:?}",
                self.name, self.kind
            )));
        }
        if self.kind == "table" && self.fields.is_empty() {
            return Err(invalid("table schemas require at least one field"));
        }
        if self.kind == "array" && self.dtype.as_deref().is_none_or(str::is_empty) {
            return Err(invalid("array schemas require dtype"));
        }
        let mut seen = std::collections::HashSet::new();
        for field in &self.fields {
            field.validate()?;
            if !seen.insert(field.name.as_str()) {
                return Err(invalid(format!(
                    "schema {}: field names must be unique",
                    self.name
                )));
            }
        }
        Ok(())
    }
    fn to_json(&self) -> Value {
        json!({
            "name": self.name, "version": self.version, "kind": self.kind,
            "fields": self.fields.iter().map(FieldSchema::to_json).collect::<Vec<_>>(),
            "dtype": self.dtype, "ndim": self.ndim, "unit": self.unit, "role": self.role,
            "allow_extra_fields": self.allow_extra_fields, "id": self.id(),
        })
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct MetricSpec {
    pub name: String,
    pub unit: String,
    pub role: String,
    pub minimum: Option<f64>,
    pub maximum: Option<f64>,
    pub censoring: Option<String>,
}

impl MetricSpec {
    pub fn new(name: impl Into<String>, unit: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            unit: unit.into(),
            role: "secondary".into(),
            minimum: None,
            maximum: None,
            censoring: None,
        }
    }
    pub fn role(mut self, role: impl Into<String>) -> Self {
        self.role = role.into();
        self
    }
    pub fn primary(self) -> Self {
        self.role("primary")
    }
    pub fn minimum(mut self, value: f64) -> Self {
        self.minimum = Some(value);
        self
    }
    pub fn maximum(mut self, value: f64) -> Self {
        self.maximum = Some(value);
        self
    }
    pub fn censoring(mut self, censoring: impl Into<String>) -> Self {
        self.censoring = Some(censoring.into());
        self
    }
    pub fn validate(&self) -> Result<(), SdkError> {
        check_name(&self.name, "metric")?;
        if self.unit.is_empty() {
            return Err(invalid(format!("metric {} requires a unit", self.name)));
        }
        if !METRIC_ROLES.contains(&self.role.as_str()) {
            return Err(invalid(format!(
                "metric {}: unknown role {:?}",
                self.name, self.role
            )));
        }
        check_range(self.minimum, self.maximum, &format!("metric {}", self.name))
    }
    pub(crate) fn to_json(&self) -> Value {
        json!({
            "name": self.name, "unit": self.unit, "role": self.role,
            "minimum": self.minimum, "maximum": self.maximum, "censoring": self.censoring,
        })
    }
}

#[derive(Debug, Clone, PartialEq)]
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

impl ResearchExperimentSpec {
    pub fn builder(
        capability: impl Into<String>,
        hypothesis: impl Into<String>,
        protocol: impl Into<String>,
    ) -> ResearchExperimentSpecBuilder {
        ResearchExperimentSpecBuilder {
            capability: capability.into(),
            hypothesis: hypothesis.into(),
            protocol: protocol.into(),
            parameters: Map::new(),
            seed: 0,
            outputs: Vec::new(),
            primary_metric: None,
            budget: ResourceBudget::default(),
            runner: None,
            inputs: Map::new(),
            reproduction_of: None,
        }
    }

    pub fn validate(&self) -> Result<(), SdkError> {
        check_name(&self.capability, "capability")?;
        if self.hypothesis.trim().is_empty() {
            return Err(invalid("hypothesis cannot be empty"));
        }
        if self.protocol.trim().is_empty() {
            return Err(invalid("protocol cannot be empty"));
        }
        if self.seed < 0 {
            return Err(invalid("seed must be a non-negative integer"));
        }
        if self.outputs.is_empty() {
            return Err(invalid("at least one output schema is required"));
        }
        let mut ids = std::collections::HashSet::new();
        for output in &self.outputs {
            output.validate()?;
            if !ids.insert(output.id()) {
                return Err(invalid("output schema ids must be unique"));
            }
        }
        self.primary_metric.validate()?;
        self.budget.validate()?;
        if !self.parameters.is_object() {
            return Err(invalid("parameters must be a JSON object"));
        }
        let inputs = self
            .inputs
            .as_object()
            .ok_or_else(|| invalid("inputs must be a JSON object"))?;
        for (name, path) in inputs {
            check_name(name, "input")?;
            if !path.is_string() {
                return Err(invalid(format!("input {name} must be a path string")));
            }
        }
        Ok(())
    }

    /// Canonical protocol JSON (`spec_version` 2).
    pub fn to_json(&self) -> Value {
        json!({
            "spec_version": 2,
            "capability": self.capability, "hypothesis": self.hypothesis,
            "protocol": self.protocol, "parameters": self.parameters, "seed": self.seed,
            "outputs": self.outputs.iter().map(ArtifactSchema::to_json).collect::<Vec<_>>(),
            "primary_metric": self.primary_metric.to_json(),
            "budget": self.budget.to_json(),
            "runner": self.runner, "inputs": self.inputs,
            "reproduction_of": self.reproduction_of,
        })
    }

    /// Parse and validate canonical JSON produced by any SDK language.
    pub fn from_json(value: &Value) -> Result<Self, SdkError> {
        let version = value
            .get("spec_version")
            .and_then(Value::as_i64)
            .unwrap_or(2);
        if version != 2 {
            return Err(invalid(format!(
                "ExperimentSpecV2 requires spec_version 2, received {version}"
            )));
        }
        let outputs = req(value, "outputs")?
            .as_array()
            .ok_or_else(|| invalid("outputs must be an array"))?
            .iter()
            .map(schema_from_json)
            .collect::<Result<Vec<_>, _>>()?;
        let budget = value.get("budget").cloned().unwrap_or_else(|| json!({}));
        let spec = Self {
            capability: req_str(value, "capability")?,
            hypothesis: req_str(value, "hypothesis")?,
            protocol: req_str(value, "protocol")?,
            parameters: value
                .get("parameters")
                .cloned()
                .unwrap_or_else(|| json!({})),
            seed: req(value, "seed")?
                .as_i64()
                .ok_or_else(|| invalid("seed must be an integer"))?,
            outputs,
            primary_metric: metric_from_json(req(value, "primary_metric")?)?,
            budget: ResourceBudget {
                max_evaluations: opt_u64(&budget, "max_evaluations")?,
                max_seconds: opt_f64(&budget, "max_seconds")?,
            },
            runner: opt_str(value, "runner")?,
            inputs: match value.get("inputs") {
                None | Some(Value::Null) => json!({}),
                Some(v) => v.clone(),
            },
            reproduction_of: opt_str(value, "reproduction_of")?,
        };
        spec.validate()?;
        Ok(spec)
    }
}

fn req<'a>(value: &'a Value, key: &str) -> Result<&'a Value, SdkError> {
    value
        .get(key)
        .ok_or_else(|| invalid(format!("missing {key}")))
}
fn req_str(value: &Value, key: &str) -> Result<String, SdkError> {
    req(value, key)?
        .as_str()
        .map(str::to_owned)
        .ok_or_else(|| invalid(format!("{key} must be a string")))
}
fn opt_str(value: &Value, key: &str) -> Result<Option<String>, SdkError> {
    match value.get(key) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(s)) => Ok(Some(s.clone())),
        Some(_) => Err(invalid(format!("{key} must be a string or null"))),
    }
}
fn opt_f64(value: &Value, key: &str) -> Result<Option<f64>, SdkError> {
    match value.get(key) {
        None | Some(Value::Null) => Ok(None),
        Some(v) => v
            .as_f64()
            .map(Some)
            .ok_or_else(|| invalid(format!("{key} must be a number or null"))),
    }
}
fn opt_u64(value: &Value, key: &str) -> Result<Option<u64>, SdkError> {
    match value.get(key) {
        None | Some(Value::Null) => Ok(None),
        Some(v) => match v.as_i64() {
            Some(n) if n >= 0 => Ok(Some(n as u64)),
            Some(_) => Err(invalid(format!("{key} must be positive"))),
            None => Err(invalid(format!("{key} must be an integer or null"))),
        },
    }
}
fn opt_u32(value: &Value, key: &str) -> Result<Option<u32>, SdkError> {
    Ok(match opt_u64(value, key)? {
        None => None,
        Some(n) => Some(u32::try_from(n).map_err(|_| invalid(format!("{key} is too large")))?),
    })
}
fn bool_or(value: &Value, key: &str, default: bool) -> Result<bool, SdkError> {
    match value.get(key) {
        None | Some(Value::Null) => Ok(default),
        Some(Value::Bool(b)) => Ok(*b),
        Some(_) => Err(invalid(format!("{key} must be a boolean"))),
    }
}

fn field_from_json(value: &Value) -> Result<FieldSchema, SdkError> {
    Ok(FieldSchema {
        name: req_str(value, "name")?,
        dtype: req_str(value, "dtype")?,
        unit: opt_str(value, "unit")?,
        role: opt_str(value, "role")?,
        nullable: bool_or(value, "nullable", false)?,
        minimum: opt_f64(value, "minimum")?,
        maximum: opt_f64(value, "maximum")?,
        censoring: opt_str(value, "censoring")?,
    })
}

fn schema_from_json(value: &Value) -> Result<ArtifactSchema, SdkError> {
    let fields = match value.get("fields") {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::Array(items)) => items
            .iter()
            .map(field_from_json)
            .collect::<Result<Vec<_>, _>>()?,
        Some(_) => return Err(invalid("fields must be an array")),
    };
    let version = opt_u32(value, "version")?.ok_or_else(|| invalid("missing version"))?;
    Ok(ArtifactSchema {
        name: req_str(value, "name")?,
        version,
        kind: req_str(value, "kind")?,
        fields,
        dtype: opt_str(value, "dtype")?,
        ndim: opt_u32(value, "ndim")?,
        unit: opt_str(value, "unit")?,
        role: opt_str(value, "role")?,
        allow_extra_fields: bool_or(value, "allow_extra_fields", false)?,
    })
}

fn metric_from_json(value: &Value) -> Result<MetricSpec, SdkError> {
    Ok(MetricSpec {
        name: req_str(value, "name")?,
        unit: req_str(value, "unit")?,
        role: opt_str(value, "role")?.unwrap_or_else(|| "secondary".into()),
        minimum: opt_f64(value, "minimum")?,
        maximum: opt_f64(value, "maximum")?,
        censoring: opt_str(value, "censoring")?,
    })
}

/// Fluent construction of a validated [`ResearchExperimentSpec`].
#[derive(Debug, Clone)]
pub struct ResearchExperimentSpecBuilder {
    capability: String,
    hypothesis: String,
    protocol: String,
    parameters: Map<String, Value>,
    seed: i64,
    outputs: Vec<ArtifactSchema>,
    primary_metric: Option<MetricSpec>,
    budget: ResourceBudget,
    runner: Option<String>,
    inputs: Map<String, Value>,
    reproduction_of: Option<String>,
}

impl ResearchExperimentSpecBuilder {
    pub fn seed(mut self, seed: i64) -> Self {
        self.seed = seed;
        self
    }
    pub fn parameter(mut self, key: impl Into<String>, value: Value) -> Self {
        self.parameters.insert(key.into(), value);
        self
    }
    pub fn output(mut self, schema: ArtifactSchema) -> Self {
        self.outputs.push(schema);
        self
    }
    pub fn primary_metric(mut self, metric: MetricSpec) -> Self {
        self.primary_metric = Some(metric);
        self
    }
    pub fn budget(mut self, budget: ResourceBudget) -> Self {
        self.budget = budget;
        self
    }
    pub fn max_evaluations(mut self, value: u64) -> Self {
        self.budget.max_evaluations = Some(value);
        self
    }
    pub fn max_seconds(mut self, value: f64) -> Self {
        self.budget.max_seconds = Some(value);
        self
    }
    pub fn runner(mut self, reference: impl Into<String>) -> Self {
        self.runner = Some(reference.into());
        self
    }
    /// Declare an input file; the Python runtime records its SHA-256.
    pub fn input(mut self, name: impl Into<String>, path: impl Into<String>) -> Self {
        self.inputs.insert(name.into(), Value::String(path.into()));
        self
    }
    pub fn reproduction_of(mut self, run_id: impl Into<String>) -> Self {
        self.reproduction_of = Some(run_id.into());
        self
    }
    pub fn build(self) -> Result<ResearchExperimentSpec, SdkError> {
        let spec = ResearchExperimentSpec {
            capability: self.capability,
            hypothesis: self.hypothesis,
            protocol: self.protocol,
            parameters: Value::Object(self.parameters),
            seed: self.seed,
            outputs: self.outputs,
            primary_metric: self
                .primary_metric
                .ok_or_else(|| invalid("a primary metric is required"))?,
            budget: self.budget,
            runner: self.runner,
            inputs: Value::Object(self.inputs),
            reproduction_of: self.reproduction_of,
        };
        spec.validate()?;
        Ok(spec)
    }
}
