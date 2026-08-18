//! Sigma rule parser (YAML)

use super::ast::Detection;
use crate::types::Severity;
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

/// A Sigma rule
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SigmaRule {
    pub title: String,

    #[serde(default)]
    pub id: String,

    #[serde(default)]
    pub status: String,

    #[serde(default)]
    pub description: String,

    #[serde(default)]
    pub author: String,

    #[serde(default)]
    pub logsource: LogSource,

    pub detection: Detection,

    #[serde(default = "default_level")]
    pub level: String,

    #[serde(default)]
    pub tags: Vec<String>,

    #[serde(default)]
    pub falsepositives: Vec<String>,

    #[serde(flatten)]
    pub extra: HashMap<String, serde_yaml::Value>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LogSource {
    #[serde(default)]
    pub product: String,

    #[serde(default)]
    pub service: String,

    #[serde(default)]
    pub category: String,
}

fn default_level() -> String {
    "medium".to_string()
}

impl SigmaRule {
    /// Load a rule from a YAML file
    pub fn from_file(path: &Path) -> Result<Self> {
        let content = std::fs::read_to_string(path)
            .context(format!("Failed to read rule file: {}", path.display()))?;

        let rule: SigmaRule = serde_yaml::from_str(&content)
            .context(format!("Failed to parse YAML: {}", path.display()))?;

        Ok(rule)
    }

    /// Get severity level
    pub fn severity(&self) -> Severity {
        Severity::from_str(&self.level)
    }

    /// Get MITRE ATT&CK technique from tags
    pub fn technique(&self) -> String {
        self.tags
            .iter()
            .find(|t| t.starts_with("attack.t"))
            .map(|t| t.trim_start_matches("attack.").to_uppercase())
            .unwrap_or_else(|| "Unknown".to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_rule() {
        let yaml = r#"
title: Test Rule
id: TEST001
detection:
  selection:
    CommandLine|contains:
      - 'malicious'
  condition: selection
level: high
"#;

        let rule: SigmaRule = serde_yaml::from_str(yaml).unwrap();
        assert_eq!(rule.title, "Test Rule");
        assert_eq!(rule.id, "TEST001");
    }
}
