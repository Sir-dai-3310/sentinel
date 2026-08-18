//! Log parser module
//!
//! Supports parsing various log formats into LogEvent

use crate::types::LogEvent;
use anyhow::Result;

pub mod json;
pub mod sysmon;

/// Parse a JSON log string into LogEvent
pub fn parse_json(input: &str) -> Result<LogEvent> {
    json::parse(input)
}

/// Parse a Sysmon XML log into LogEvent
pub fn parse_sysmon(input: &str) -> Result<LogEvent> {
    sysmon::parse(input)
}

/// Auto-detect format and parse
pub fn parse_auto(input: &str) -> Result<LogEvent> {
    // Try JSON first
    if let Ok(event) = parse_json(input) {
        return Ok(event);
    }

    // Try Sysmon XML
    if input.trim().starts_with('<') {
        return parse_sysmon(input);
    }

    Err(anyhow::anyhow!("Unable to detect log format"))
}
