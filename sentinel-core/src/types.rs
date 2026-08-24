//! Core type definitions

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// A log event (normalized from various sources)
#[cfg_attr(feature = "pyo3", pyo3::prelude::pyclass)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogEvent {
    /// Event ID (e.g., Sysmon EventID 1, 3, 10)
    pub event_id: Option<u32>,

    /// Timestamp (ISO 8601)
    pub timestamp: Option<String>,

    /// All fields as key-value pairs
    pub fields: HashMap<String, String>,
}

impl LogEvent {
    pub fn new() -> Self {
        Self {
            event_id: None,
            timestamp: None,
            fields: HashMap::new(),
        }
    }

    /// Get a field value
    pub fn get(&self, key: &str) -> Option<String> {
        // Special case: EventID is stored in event_id field (u32), not in fields HashMap
        if key == "EventID" {
            return self.event_id.map(|id| id.to_string());
        }
        self.fields.get(key).cloned()
    }

    /// Set a field value
    pub fn set(&mut self, key: String, value: String) {
        self.fields.insert(key, value);
    }
}

/// A rule hit (match result)
#[cfg_attr(feature = "pyo3", pyo3::prelude::pyclass)]
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuleHit {
    pub rule_id: String,
    pub rule_name: String,
    pub technique: String, // MITRE ATT&CK technique (e.g., T1003.001)
    pub confidence: u8,    // 0-100
    pub severity: Severity,
    pub reason: String,
}

#[cfg_attr(feature = "pyo3", pyo3::prelude::pyclass)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum Severity {
    Low,
    Medium,
    High,
    Critical,
}

impl Severity {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "low" => Severity::Low,
            "medium" => Severity::Medium,
            "high" => Severity::High,
            "critical" => Severity::Critical,
            _ => Severity::Medium,
        }
    }

    pub fn to_confidence(&self) -> u8 {
        match self {
            Severity::Low => 50,
            Severity::Medium => 70,
            Severity::High => 85,
            Severity::Critical => 95,
        }
    }
}
