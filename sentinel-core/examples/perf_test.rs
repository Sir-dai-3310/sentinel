use sentinel_core::sigma::SigmaEngine;
use sentinel_core::types::LogEvent;
use std::collections::HashMap;
use std::time::Instant;

fn main() {
    let mut fields = HashMap::new();
    fields.insert("EventID".to_string(), "1".to_string());
    fields.insert("Image".to_string(), "powershell.exe".to_string());
    fields.insert("CommandLine".to_string(), "powershell -enc test".to_string());

    let log = LogEvent {
        event_id: Some(1),
        timestamp: None,
        fields,
    };

    let engine = SigmaEngine::new("../rules".to_string())
        .expect("Failed to load rules");

    println!("Loaded {} rules", engine.rule_count());

    // Warm up
    for _ in 0..1000 {
        let _ = engine.evaluate(&log);
    }

    // Benchmark: 10,000 iterations for stable results
    let iterations = 10_000;
    let start = Instant::now();
    for _ in 0..iterations {
        let _ = engine.evaluate(&log);
    }
    let duration = start.elapsed();

    let avg_ns = duration.as_nanos() / iterations as u128;
    let avg_us = avg_ns as f64 / 1_000.0;
    let avg_ms = avg_ns as f64 / 1_000_000.0;
    let eps = iterations as f64 / duration.as_secs_f64();

    println!("\n=== Performance Results (10,000 iterations, warmed) ===");
    println!("Total time: {:?}", duration);
    println!("Average latency: {} ns ({:.3} us, {:.4} ms)", avg_ns, avg_us, avg_ms);
    println!("Throughput: {:.0} EPS", eps);
    println!();
    println!("Targets: latency < 10ms, throughput > 10,000 EPS");
    println!();

    let latency_pass = avg_ms < 10.0;
    let throughput_pass = eps > 10_000.0;

    if latency_pass {
        println!("PASS Latency: {:.4} ms < 10 ms", avg_ms);
    } else {
        println!("FAIL Latency: {:.4} ms >= 10 ms", avg_ms);
    }

    if throughput_pass {
        println!("PASS Throughput: {:.0} EPS > 10,000 EPS", eps);
    } else {
        println!("WARN Throughput: {:.0} EPS (target: >10,000)", eps);
        println!("     {:.0} EPS x 100 rules = {:.0} rule-evals/sec",
                 eps, eps * 100.0);
    }

    println!();
    println!("=== Rule Engine Stats ===");
    println!("Rules evaluated per log: {}", engine.rule_count());
    println!("Time per rule: {:.2} us", avg_us / engine.rule_count() as f64);
    println!("Rule evaluations per second: {:.0}", eps * engine.rule_count() as f64);

    // ============ Batch (cross-log parallel) throughput ============
    // Build a batch of distinct logs so rayon can parallelize across them.
    let batch_size = 1000;
    let total_logs = 50_000;
    let batch: Vec<LogEvent> = (0..batch_size)
        .map(|i| {
            let mut f = HashMap::new();
            f.insert("EventID".to_string(), (1 + i % 40).to_string());
            f.insert("Image".to_string(), "powershell.exe".to_string());
            f.insert("CommandLine".to_string(), format!("powershell -enc test {i}").to_string());
            LogEvent { event_id: Some(1 + i % 40), timestamp: None, fields: f }
        })
        .collect();

    // Warm up batch
    for _ in 0..10 {
        let _ = engine.evaluate_batch(&batch);
    }

    let mut batch_total = 0u128;
    let mut batches = 0u64;
    let bstart = Instant::now();
    while batch_total < total_logs as u128 {
        batch_total += engine.evaluate_batch(&batch).len() as u128;
        batches += 1;
    }
    let bdur = bstart.elapsed();
    let beps = batch_total as f64 / bdur.as_secs_f64();

    println!();
    println!("=== Batch Parallel Throughput (evaluate_batch, cross-log rayon) ===");
    println!("Processed {batch_total} logs in {batches} batch(es) of {batch_size} in {bdur:?}");
    println!("Batch throughput: {beps:.0} EPS");
    println!("vs single-log throughput: {eps:.0} EPS");
    println!("Speedup: {:.1}x", beps / eps);
}
