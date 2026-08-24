//! Benchmark for Sigma rule engine

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use sentinel_core::sigma::SigmaEngine;
use sentinel_core::types::LogEvent;
use std::collections::HashMap;

fn create_test_log() -> LogEvent {
    let mut fields = HashMap::new();
    fields.insert("EventID".to_string(), "1".to_string());
    fields.insert("Image".to_string(), "powershell.exe".to_string());
    fields.insert(
        "CommandLine".to_string(),
        "powershell -enc JABjAD0AJw".to_string(),
    );

    LogEvent {
        event_id: Some(1),
        timestamp: Some("2026-08-17T10:00:00Z".to_string()),
        fields,
    }
}

fn benchmark_evaluation(c: &mut Criterion) {
    // Note: This benchmark requires rules to be present in ../rules/
    // If rules are missing, it will benchmark with 0 rules
    let engine = SigmaEngine::new("../rules".to_string()).expect("Failed to load rules");

    let log = create_test_log();

    c.bench_function("evaluate_single_log", |b| {
        b.iter(|| {
            black_box(engine.evaluate(black_box(&log)));
        });
    });
}

criterion_group!(benches, benchmark_evaluation);
criterion_main!(benches);
