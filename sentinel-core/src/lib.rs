//! Sentinel Core - High-performance security log analysis engine
//!
//! This is the Rust core of Sentinel, providing:
//! - Sigma rule engine (compatible with official Sigma YAML syntax)
//! - High-performance log parsing (Sysmon/JSON/CEF)
//! - Parallel rule matching

pub mod metrics;
pub mod parser;
pub mod sigma;
pub mod types;

// Python bindings (requires pyo3 feature)
#[cfg(feature = "pyo3")]
use pyo3::prelude::*;
#[cfg(feature = "pyo3")]
use pyo3::types::PyModuleMethods;

/// Python module initialization
#[cfg(feature = "pyo3")]
#[pymodule]
fn sentinel_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<sigma::SigmaEngine>()?;
    m.add_class::<types::LogEvent>()?;
    m.add_class::<types::RuleHit>()?;
    m.add_function(pyo3::wrap_pyfunction!(metrics_text, m)?)?;
    Ok(())
}

/// Export the global engine metrics in Prometheus text format.
#[cfg(feature = "pyo3")]
#[pyfunction]
fn metrics_text() -> String {
    metrics::global().export_prometheus()
}
