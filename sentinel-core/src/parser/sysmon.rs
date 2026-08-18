//! Sysmon XML parser using quick-xml

use crate::types::LogEvent;
use anyhow::{Context, Result};
use quick_xml::de::from_str;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Sysmon Event XML structure
#[derive(Debug, Deserialize, Serialize)]
#[serde(rename = "Event")]
struct SysmonEvent {
    #[serde(rename = "System")]
    system: System,

    #[serde(rename = "EventData")]
    event_data: Option<EventData>,
}

#[derive(Debug, Deserialize, Serialize)]
struct System {
    #[serde(rename = "EventID")]
    event_id: EventID,

    #[serde(rename = "TimeCreated")]
    time_created: Option<TimeCreated>,

    #[serde(rename = "Computer")]
    computer: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
struct EventID {
    #[serde(rename = "$value")]
    value: Option<u32>,
}

#[derive(Debug, Deserialize, Serialize)]
struct TimeCreated {
    #[serde(rename = "@SystemTime")]
    system_time: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
struct EventData {
    #[serde(rename = "Data", default)]
    data: Vec<Data>,
}

#[derive(Debug, Deserialize, Serialize)]
struct Data {
    #[serde(rename = "@Name")]
    name: String,

    #[serde(rename = "$value")]
    value: Option<String>,
}

/// Parse Sysmon XML event into LogEvent
pub fn parse(input: &str) -> Result<LogEvent> {
    // Parse XML
    let event: SysmonEvent = from_str(input).context("Failed to parse Sysmon XML")?;

    // Extract event ID
    let event_id = event.system.event_id.value;

    // Extract timestamp
    let timestamp = event
        .system
        .time_created
        .and_then(|tc| tc.system_time);

    // Extract event data fields
    let mut fields = HashMap::new();

    if let Some(computer) = event.system.computer {
        fields.insert("Computer".to_string(), computer);
    }

    if let Some(event_data) = event.event_data {
        for data in event_data.data {
            if let Some(value) = data.value {
                fields.insert(data.name, value);
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
    fn test_parse_sysmon_event() {
        let xml = r#"
<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
  <System>
    <EventID>1</EventID>
    <TimeCreated SystemTime="2026-08-17T10:00:00.000Z" />
    <Computer>WORKSTATION01</Computer>
  </System>
  <EventData>
    <Data Name="Image">C:\Windows\System32\powershell.exe</Data>
    <Data Name="CommandLine">powershell.exe -enc JABjAD0AJw</Data>
    <Data Name="ParentImage">C:\Windows\explorer.exe</Data>
  </EventData>
</Event>
"#;

        let result = parse(xml);
        assert!(result.is_ok());

        let event = result.unwrap();
        assert_eq!(event.event_id, Some(1));
        assert_eq!(
            event.timestamp,
            Some("2026-08-17T10:00:00.000Z".to_string())
        );
        assert_eq!(
            event.get("Image"),
            Some("C:\\Windows\\System32\\powershell.exe".to_string())
        );
        assert_eq!(
            event.get("CommandLine"),
            Some("powershell.exe -enc JABjAD0AJw".to_string())
        );
        assert_eq!(
            event.get("Computer"),
            Some("WORKSTATION01".to_string())
        );
    }

    #[test]
    fn test_parse_invalid_xml() {
        let xml = "<Invalid>XML</Invalid>";
        let result = parse(xml);
        assert!(result.is_err());
    }

    #[test]
    fn test_parse_empty_event_data() {
        let xml = r#"
<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
  <System>
    <EventID>3</EventID>
    <TimeCreated SystemTime="2026-08-17T10:00:00.000Z" />
    <Computer>WORKSTATION01</Computer>
  </System>
</Event>
"#;

        let result = parse(xml);
        assert!(result.is_ok());

        let event = result.unwrap();
        assert_eq!(event.event_id, Some(3));
        assert!(event.fields.contains_key("Computer"));
    }
}
