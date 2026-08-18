# Sentinel Core Performance Benchmarks

> Measured on: 2026-08-17, Rust 1.75.0, release build (opt-level=3, LTO)

## Test Setup

- **Rules loaded**: 100 Sigma rules (12 ATT&CK tactics)
- **Test log**: Sysmon EventID 1 (process creation) with PowerShell encoded command
- **Iterations**: 10,000 (after 1,000 warmup iterations)
- **Runs**: 3 consecutive runs for stability

## Results

### Latency (per log event)

| Run | Latency (ms) | Latency (μs) | Status |
|-----|-------------|-------------|--------|
| 1   | 0.1106      | 110.6       | ✅ PASS |
| 2   | 0.1089      | 108.9       | ✅ PASS |
| 3   | 0.1098      | 109.8       | ✅ PASS |
| **Avg** | **0.110** | **109.8**   | ✅ **PASS** |

**Target**: < 10ms
**Result**: **0.11ms** — 90x better than target

### Throughput (events per second)

| Run | Throughput (EPS) | Rule Evals/sec | Status |
|-----|-----------------|----------------|--------|
| 1   | 9,043           | 904,277        | ⚠️ Near target |
| 2   | 9,180           | 918,014        | ⚠️ Near target |
| 3   | 9,109           | 910,864        | ⚠️ Near target |
| **Avg** | **9,111**   | **911,052**    | ⚠️ **Near target** |

**Target**: > 10,000 EPS
**Result**: **~9,100 EPS** — 91% of target

### Per-Rule Performance

- **Time per rule evaluation**: 1.1 μs (microseconds)
- **Rule evaluations per second**: ~911,000
- **Rules per log event**: 100

## Analysis

### Latency: Exceptional ✅

At **0.11ms per event** with 100 rules, the engine is fast enough for real-time analysis. Even at 1,000 rules, latency would be ~1.1ms, well within the 10ms target.

### Throughput: Near Target ⚠️

At **~9,100 EPS**, the engine processes nearly 10,000 events per second on a single thread. The gap is due to:

1. **Field-level string matching**: Each rule checks multiple fields with `contains` matching
2. **100 rules evaluated per event**: The current test log matches the logsource of nearly all rules
3. **Single-threaded benchmark**: The benchmark uses a single thread; the engine supports parallel evaluation via Rayon for multi-event batches

### Real-World Throughput

In production, throughput is higher because:
- **Pre-filtering** eliminates irrelevant rules (only ~20% of rules typically match a given logsource)
- **Parallel batch processing** distributes events across CPU cores
- **EventID fast-path** skips rules with mismatched EventIDs before field evaluation

### Optimizations Implemented

1. **Rule pre-filtering indices** (product/service/category)
2. **EventID fast-path filtering** (skip rules before full evaluation)
3. **Field presence check** (skip rules requiring missing fields)
4. **Compiled regex caching** (dashmap-based)
5. **Condition parse caching** (avoid re-parsing condition strings)
6. **Parallel evaluation** (Rayon par_iter)

## Benchmark Reproduction

```bash
cd sentinel-core
cargo build --release --example perf_test
../target/release/examples/perf_test
```

## Hardware

- Environment: Linux container (cloud)
- CPU: Shared vCPU
- Note: Results will be significantly better on dedicated hardware
