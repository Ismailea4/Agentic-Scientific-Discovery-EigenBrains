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

#[derive(Debug)]
pub enum SdkError {
    Io(std::io::Error),
    Json(serde_json::Error),
    Protocol(String),
}

impl Display for SdkError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "I/O error: {e}"),
            Self::Json(e) => write!(f, "JSON error: {e}"),
            Self::Protocol(e) => write!(f, "EigenBrains protocol error: {e}"),
        }
    }
}

impl std::error::Error for SdkError {}
impl From<std::io::Error> for SdkError { fn from(value: std::io::Error) -> Self { Self::Io(value) } }
impl From<serde_json::Error> for SdkError { fn from(value: serde_json::Error) -> Self { Self::Json(value) } }

pub struct Bridge {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

impl Bridge {
    pub fn spawn(python: &str, lab_root: impl AsRef<Path>, actor: &str) -> Result<Self, SdkError> {
        let mut child = Command::new(python)
            .args(["-m", "discolab.rpc", "--root"])
            .arg(lab_root.as_ref())
            .args(["--actor", actor])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()?;
        let stdin = child.stdin.take().ok_or_else(|| SdkError::Protocol("bridge stdin unavailable".into()))?;
        let stdout = child.stdout.take().ok_or_else(|| SdkError::Protocol("bridge stdout unavailable".into()))?;
        Ok(Self { child, stdin, stdout: BufReader::new(stdout), next_id: 1 })
    }

    pub fn call(&mut self, method: &str, params: Value) -> Result<Value, SdkError> {
        let id = self.next_id;
        self.next_id += 1;
        let request = json!({"id": id, "version": PROTOCOL_VERSION, "method": method, "params": params});
        serde_json::to_writer(&mut self.stdin, &request)?;
        self.stdin.write_all(b"\n")?;
        self.stdin.flush()?;
        let mut line = String::new();
        if self.stdout.read_line(&mut line)? == 0 {
            return Err(SdkError::Protocol("bridge closed before replying".into()));
        }
        let response: Value = serde_json::from_str(&line)?;
        if response.get("id").and_then(Value::as_u64) != Some(id) {
            return Err(SdkError::Protocol("response id does not match request".into()));
        }
        if response.get("ok").and_then(Value::as_bool) != Some(true) {
            let message = response.pointer("/error/message").and_then(Value::as_str).unwrap_or("unknown error");
            return Err(SdkError::Protocol(message.to_owned()));
        }
        Ok(response.get("result").cloned().unwrap_or(Value::Null))
    }

    pub fn initialize(&mut self) -> Result<Value, SdkError> { self.call("initialize", json!({})) }
    pub fn state(&mut self) -> Result<Value, SdkError> { self.call("state", json!({})) }
    pub fn propose(&mut self, experiment: Value) -> Result<Value, SdkError> {
        self.call("propose", json!({"experiment": experiment}))
    }
    pub fn score(&mut self) -> Result<Value, SdkError> { self.call("score", json!({})) }
    pub fn select(&mut self, experiment_id: &str, justification: &str) -> Result<Value, SdkError> {
        self.call("select", json!({"experiment_id": experiment_id, "justification": justification}))
    }
    pub fn run(&mut self, confirm_heldout: bool) -> Result<Value, SdkError> {
        self.call("run", json!({"confirm_heldout": confirm_heldout}))
    }
}

impl Drop for Bridge {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

pub mod kernels {
    use std::f64::consts::E;

    /// Mean fixed-bin Shannon entropy across columns, normalized to [0, 1].
    pub fn normalized_histogram_entropy(
        points: &[f64], rows: usize, cols: usize, lower: f64, upper: f64, bins: usize,
    ) -> Result<f64, &'static str> {
        if rows == 0 || cols == 0 || points.len() != rows * cols { return Err("invalid matrix shape"); }
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
                if !x.is_finite() { return Err("non-finite sample"); }
                let idx = if x <= lower { 0 } else if x >= upper { bins - 1 }
                          else { ((x - lower) / width).floor() as usize };
                counts[idx] += 1;
            }
            let h = counts.iter().filter(|&&n| n > 0).map(|&n| {
                let p = n as f64 / rows as f64;
                -p * p.ln()
            }).sum::<f64>();
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
        if sorted.iter().any(|x| !x.is_finite()) { return Err("non-finite sample"); }
        sorted.sort_by(|a, b| b.total_cmp(a));
        let n = ((sorted.len() as f64 * tail_probability).ceil() as usize).max(1);
        Ok(sorted[..n].iter().sum::<f64>() / n as f64)
    }

    /// Wilson score interval for a binomial proportion.
    pub fn wilson_interval(successes: u64, trials: u64, z: f64) -> Result<(f64, f64, f64), &'static str> {
        if trials == 0 || successes > trials || !z.is_finite() || z <= 0.0 { return Err("invalid Wilson input"); }
        let n = trials as f64;
        let p = successes as f64 / n;
        let z2 = z * z;
        let center = (p + z2 / (2.0 * n)) / (1.0 + z2 / n);
        let half = z * ((p * (1.0 - p) / n + z2 / (4.0 * n * n)).sqrt()) / (1.0 + z2 / n);
        Ok((p, (center - half).max(0.0), (center + half).min(1.0)))
    }

    #[allow(dead_code)]
    fn _base() -> f64 { E }
}

#[cfg(test)]
mod tests {
    use super::kernels::*;

    #[test]
    fn entropy_extremes() {
        assert_eq!(normalized_histogram_entropy(&[0.0; 8], 4, 2, -1.0, 1.0, 4).unwrap(), 0.0);
        let spread = [-0.9, -0.9, -0.3, -0.3, 0.3, 0.3, 0.9, 0.9];
        assert!((normalized_histogram_entropy(&spread, 4, 2, -1.0, 1.0, 4).unwrap() - 1.0).abs() < 1e-12);
    }

    #[test]
    fn cvar_and_wilson_are_bounded() {
        assert_eq!(cvar_upper(&[1.0, 2.0, 3.0, 4.0], 0.5).unwrap(), 3.5);
        let (p, lo, hi) = wilson_interval(7, 10, 1.959963984540054).unwrap();
        assert!((p - 0.7).abs() < 1e-12);
        assert!((lo - 0.39677814746114537).abs() < 1e-12);
        assert!((hi - 0.8922087325936989).abs() < 1e-12);
    }
}
