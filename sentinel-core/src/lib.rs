//! Sentinel Core - High-performance security log analysis engine
//!
//! This is the Rust core of Sentinel, providing:
//! - Sigma rule engine (compatible with official Sigma YAML syntax)
//! - High-performance log parsing (Sysmon/JSON/CEF)
//! - Parallel rule matching

pub mod sigma;
pub mod parser;
pub mod types;
pub mod metrics;

// Python bindings (requires pyo3 feature)
#[cfg(feature = "pyo3")]
use pyo3::prelude::*;

/// Python module initialization
#[cfg(feature = "pyo3")]
#[pymodule]
fn sentinel_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<sigma::SigmaEngine>()?;
    m.add_class::<types::LogEvent>()?;
    m.add_class::<types::RuleHit>()?;
    Ok(())
}
