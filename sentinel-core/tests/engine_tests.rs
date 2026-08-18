//! Comprehensive tests for Sigma rule engine

use sentinel_core::sigma::SigmaEngine;
use sentinel_core::types::LogEvent;
use std::collections::HashMap;

fn create_log(event_id: Option<u32>, fields: Vec<(&str, &str)>) -> LogEvent {
    let mut field_map = HashMap::new();
    for (key, value) in fields {
        field_map.insert(key.to_string(), value.to_string());
    }

    LogEvent {
        event_id,
        timestamp: Some("2026-08-17T10:00:00Z".to_string()),
        fields: field_map,
    }
}

#[test]
fn test_engine_creation() {
    let result = SigmaEngine::new("../rules".to_string());
    assert!(result.is_ok());
}

#[test]
fn test_rule_count() {
    if let Ok(engine) = SigmaEngine::new("../rules".to_string()) {
        assert!(engine.rule_count() > 0);
    }
}

#[test]
fn test_powershell_encoded_detection() {
    let log = create_log(
        Some(1),
        vec![
            ("Image", "powershell.exe"),
            ("CommandLine", "powershell -enc JABjAD0AJw"),
        ],
    );

    if let Ok(engine) = SigmaEngine::new("../rules".to_string()) {
        let hits = engine.evaluate(&log);
        // Should detect PowerShell encoded command
        assert!(!hits.is_empty() || engine.rule_count() == 0);
    }
}

#[test]
fn test_mimikatz_detection() {
    let log = create_log(
        Some(1),
        vec![
            ("Image", "mimikatz.exe"),
            ("CommandLine", "mimikatz.exe sekurlsa::logonpasswords"),
        ],
    );

    if let Ok(engine) = SigmaEngine::new("../rules".to_string()) {
        let hits = engine.evaluate(&log);
        assert!(!hits.is_empty() || engine.rule_count() == 0);
    }
}

#[test]
fn test_lsass_access_detection() {
    let log = create_log(
        Some(10),
        vec![
            ("TargetImage", "C:\\Windows\\System32\\lsass.exe"),
            ("GrantedAccess", "0x1410"),
        ],
    );

    if let Ok(engine) = SigmaEngine::new("../rules".to_string()) {
        let hits = engine.evaluate(&log);
        assert!(!hits.is_empty() || engine.rule_count() == 0);
    }
}

#[test]
fn test_office_spawn_shell_detection() {
    let log = create_log(
        Some(1),
        vec![
            ("ParentImage", "C:\\Program Files\\Microsoft Office\\winword.exe"),
            ("Image", "C:\\Windows\\System32\\cmd.exe"),
        ],
    );

    if let Ok(engine) = SigmaEngine::new("../rules".to_string()) {
        let hits = engine.evaluate(&log);
        assert!(!hits.is_empty() || engine.rule_count() == 0);
    }
}

#[test]
fn test_registry_persistence_detection() {
    let log = create_log(
        Some(13),
        vec![
            ("TargetObject", "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\Malware"),
        ],
    );

    if let Ok(engine) = SigmaEngine::new("../rules".to_string()) {
        let hits = engine.evaluate(&log);
        assert!(!hits.is_empty() || engine.rule_count() == 0);
    }
}

#[test]
fn test_scheduled_task_detection() {
    let log = create_log(
        Some(1),
        vec![
            ("CommandLine", "schtasks /create /tn MyTask /tr malware.exe"),
        ],
    );

    if let Ok(engine) = SigmaEngine::new("../rules".to_string()) {
        let hits = engine.evaluate(&log);
        assert!(!hits.is_empty() || engine.rule_count() == 0);
    }
}

#[test]
fn test_smb_lateral_movement_detection() {
    let log = create_log(
        Some(1),
        vec![
            ("CommandLine", "net use \\\\192.168.1.100\\admin$"),
        ],
    );

    if let Ok(engine) = SigmaEngine::new("../rules".to_string()) {
        let hits = engine.evaluate(&log);
        assert!(!hits.is_empty() || engine.rule_count() == 0);
    }
}

#[test]
fn test_benign_log() {
    let log = create_log(
        Some(1),
        vec![
            ("Image", "chrome.exe"),
            ("CommandLine", "chrome.exe --profile-directory=Default"),
        ],
    );

    if let Ok(engine) = SigmaEngine::new("../rules".to_string()) {
        let hits = engine.evaluate(&log);
        // Benign log should have no hits or very few low-confidence hits
        assert!(hits.is_empty() || hits.iter().all(|h| h.confidence < 50));
    }
}

#[test]
fn test_pre_filtering_performance() {
    // Test that pre-filtering reduces evaluation time
    let log = create_log(
        Some(1),
        vec![("Image", "test.exe")],
    );

    if let Ok(engine) = SigmaEngine::new("../rules".to_string()) {
        let start = std::time::Instant::now();
        let _ = engine.evaluate(&log);
        let duration = start.elapsed();

        // Pre-filtering should make evaluation fast (< 100ms for small rule sets)
        assert!(duration.as_millis() < 100);
    }
}
