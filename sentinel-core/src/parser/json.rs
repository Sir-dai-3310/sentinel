//! JSON log parser

use crate::types::LogEvent;
use anyhow::{Context, Result};
use std::collections::HashMap;

pub fn parse(input: &str) -> Result<LogEvent> {
    let value: serde_json::Value = serde_json::from_str(input).context("Failed to parse JSON")?;

    let mut fields = HashMap::new();
    let mut event_id = None;
    let mut timestamp = None;

    if let Some(obj) = value.as_object() {
        for (key, val) in obj {
            match key.as_str() {
                "EventID" | "event_id" => {
                    if let Some(id) = val.as_u64() {
                        event_id = Some(id as u32);
                    }
                }
                "TimeCreated" | "timestamp" | "@timestamp" => {
                    if let Some(ts) = val.as_str() {
                        timestamp = Some(ts.to_string());
                    }
                }
                _ => {
                    if let Some(s) = val.as_str() {
                        fields.insert(key.clone(), s.to_string());
                    } else if let Some(n) = val.as_u64() {
                        fields.insert(key.clone(), n.to_string());
                    }
                }
            }
        }
    }

    Ok(LogEvent {
        event_id,
        timestamp,
        fields,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_simple_json() {
        let json = r#"{"EventID": 1, "Image": "powershell.exe"}"#;
        let event = parse(json).unwrap();
        assert_eq!(event.event_id, Some(1));
        assert_eq!(event.get("Image"), Some("powershell.exe".to_string()));
    }
}
