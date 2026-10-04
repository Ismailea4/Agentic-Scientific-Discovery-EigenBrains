//! Minimal reader for the NumPy `.npy` arrays the Python runtime emits.
//!
//! Supports format versions 1-3, little-endian float64 (`<f8`), C order -
//! exactly what `ArtifactEmitter.array` writes for float64 schemas. Anything
//! else is refused rather than guessed.

use crate::SdkError;
use std::path::Path;

const MAGIC: &[u8] = b"\x93NUMPY";

#[derive(Debug, Clone, PartialEq)]
pub struct NpyArray {
    pub shape: Vec<usize>,
    pub data: Vec<f64>,
}

fn bad(message: impl Into<String>) -> SdkError {
    SdkError::Invalid(format!("npy: {}", message.into()))
}

fn header_value<'a>(header: &'a str, key: &str) -> Result<&'a str, SdkError> {
    let tag = format!("'{key}':");
    let start = header
        .find(&tag)
        .ok_or_else(|| bad(format!("header lacks {key}")))?
        + tag.len();
    Ok(header[start..].trim_start())
}

pub fn parse_f64(bytes: &[u8]) -> Result<NpyArray, SdkError> {
    if bytes.len() < 10 || &bytes[..6] != MAGIC {
        return Err(bad("not an .npy file"));
    }
    let (header_len, offset) = match bytes[6] {
        1 => (u16::from_le_bytes([bytes[8], bytes[9]]) as usize, 10),
        2 | 3 if bytes.len() >= 12 => (
            u32::from_le_bytes([bytes[8], bytes[9], bytes[10], bytes[11]]) as usize,
            12,
        ),
        major => return Err(bad(format!("unsupported format version {major}"))),
    };
    let end = offset + header_len;
    if bytes.len() < end {
        return Err(bad("truncated header"));
    }
    let header = std::str::from_utf8(&bytes[offset..end]).map_err(|_| bad("header is not text"))?;
    if !header_value(header, "descr")?.starts_with("'<f8'") {
        return Err(bad("only little-endian float64 ('<f8') is supported"));
    }
    if !header_value(header, "fortran_order")?.starts_with("False") {
        return Err(bad("only C-order arrays are supported"));
    }
    let shape_text = header_value(header, "shape")?;
    let close = shape_text.find(')').ok_or_else(|| bad("malformed shape"))?;
    let shape = shape_text[1..close]
        .split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(|s| s.parse::<usize>().map_err(|_| bad("malformed shape")))
        .collect::<Result<Vec<_>, _>>()?;
    let count: usize = shape.iter().product();
    let body = &bytes[end..];
    if body.len() != count * 8 {
        return Err(bad(format!(
            "expected {} data bytes, found {}",
            count * 8,
            body.len()
        )));
    }
    let data = body
        .as_chunks::<8>()
        .0
        .iter()
        .map(|c| f64::from_le_bytes(*c))
        .collect();
    Ok(NpyArray { shape, data })
}

pub fn read_f64(path: impl AsRef<Path>) -> Result<NpyArray, SdkError> {
    parse_f64(&std::fs::read(path)?)
}
