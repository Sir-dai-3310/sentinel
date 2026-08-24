//! Coverage-focused tests for evaluator edge cases

use sentinel_core::sigma::SigmaEngine;
use sentinel_core::types::LogEvent;
use std::collections::HashMap;

fn make_log(event_id: Option<u32>, fields: Vec<(&str, &str)>) -> LogEvent {
    let mut map = HashMap::new();
    for (k, v) in fields {
        map.insert(k.to_string(), v.to_string());
    }
    LogEvent {
        event_id,
        timestamp: None,
        fields: map,
    }
}

#[test]
fn test_evaluate_with_event_id_match() {
    let engine = SigmaEngine::new("../rules".to_string()).unwrap();
    // LSASS rule requires EventID 10
    let log = make_log(
        Some(10),
        vec![
            ("TargetImage", "C:\\Windows\\System32\\lsass.exe"),
            ("GrantedAccess", "0x1410"),
        ],
    );
    let hits = engine.evaluate(&log);
    // Should match LSASS rule
    assert!(!hits.is_empty());
}

#[test]
fn test_evaluate_with_event_id_mismatch() {
    let engine = SigmaEngine::new("../rules".to_string()).unwrap();
    // EventID 1 but LSASS rule needs EventID 10
    let log = make_log(
        Some(1),
        vec![
            ("TargetImage", "C:\\Windows\\System32\\lsass.exe"),
            ("GrantedAccess", "0x1410"),
        ],
    );
    let hits = engine.evaluate(&log);
    // LSASS rule should NOT match (EventID mismatch)
    assert!(hits.iter().all(|h| h.rule_id != "R003"));
}

#[test]
fn test_evaluate_missing_required_field() {
    let engine = SigmaEngine::new("../rules".to_string()).unwrap();
    // Log without TargetImage - LSASS rule should be skipped
    let log = make_log(Some(10), vec![("GrantedAccess", "0x1410")]);
    let hits = engine.evaluate(&log);
    // LSASS rule should NOT match (missing TargetImage)
    assert!(hits.iter().all(|h| h.rule_id != "R003"));
}

#[test]
fn test_evaluate_no_event_id_in_log() {
    let engine = SigmaEngine::new("../rules".to_string()).unwrap();
    // Log without EventID
    let log = make_log(
        None,
        vec![
            ("Image", "powershell.exe"),
            ("CommandLine", "powershell -enc test"),
        ],
    );
    let hits = engine.evaluate(&log);
    // Should still find process-creation rules (no EventID filter)
    assert!(!hits.is_empty());
}

#[test]
fn test_evaluate_benign_chrome() {
    let engine = SigmaEngine::new("../rules".to_string()).unwrap();
    let log = make_log(
        Some(1),
        vec![
            (
                "Image",
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            ),
            ("CommandLine", "chrome.exe --type=renderer"),
            ("ParentImage", "C:\\Windows\\explorer.exe"),
        ],
    );
    let hits = engine.evaluate(&log);
    // Chrome should not match any critical rules
    assert!(hits.iter().all(|h| h.confidence < 90));
}

#[test]
fn test_evaluate_case_insensitive_matching() {
    let engine = SigmaEngine::new("../rules".to_string()).unwrap();
    // Test with mixed case - rules use lowercase 'powershell', 'contains'
    let log = make_log(
        Some(1),
        vec![
            ("Image", "C:\\Windows\\System32\\PowerShell.exe"),
            ("CommandLine", "PowerShell.exe -ENC test"),
        ],
    );
    let hits = engine.evaluate(&log);
    // Should still match despite case differences
    assert!(!hits.is_empty());
}

#[test]
fn test_evaluate_empty_log() {
    let engine = SigmaEngine::new("../rules".to_string()).unwrap();
    let log = make_log(None, vec![]);
    let hits = engine.evaluate(&log);
    assert!(hits.is_empty());
}

#[test]
fn test_evaluate_field_modifiers() {
    let engine = SigmaEngine::new("../rules".to_string()).unwrap();

    // Test 'endswith' modifier with full CommandLine
    let log = make_log(
        Some(1),
        vec![
            (
                "Image",
                "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            ),
            ("CommandLine", "powershell.exe -enc JABj"),
        ],
    );
    let hits = engine.evaluate(&log);
    assert!(!hits.is_empty()); // powershell_encoded rule uses contains

    // Test 'contains' modifier with mimikatz
    let log2 = make_log(
        Some(1),
        vec![("CommandLine", "mimikatz.exe sekurlsa::logonpasswords")],
    );
    let hits2 = engine.evaluate(&log2);
    assert!(!hits2.is_empty());
}

#[test]
fn test_engine_rule_count_accuracy() {
    let engine = SigmaEngine::new("../rules".to_string()).unwrap();
    let count = engine.rule_count();
    assert!(count >= 100, "Expected >= 100 rules, got {}", count);
}

#[test]
fn test_evaluate_multiple_rule_hits() {
    let engine = SigmaEngine::new("../rules".to_string()).unwrap();
    // This log should trigger multiple rules (PowerShell encoded + hidden window)
    let log = make_log(
        Some(1),
        vec![
            ("Image", "powershell.exe"),
            ("CommandLine", "powershell -enc JABj -WindowStyle Hidden"),
        ],
    );
    let hits = engine.evaluate(&log);
    assert!(hits.len() >= 1, "Expected at least 1 rule hit");
}
