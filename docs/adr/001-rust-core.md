# ADR-001: Rust Core for Sigma Rule Engine

## Status
Accepted

## Context
Sentinel needs to evaluate hundreds of Sigma rules against thousands of log events per second. Python's performance was insufficient for real-time analysis.

## Decision
Use Rust for the core rule engine, with Python (via PyO3) as the integration layer.

## Rationale
1. **Performance**: Rust provides 10-100x speedup over Python for CPU-bound tasks
2. **Memory safety**: No GC pauses, no data races, safe concurrency
3. **Zero-cost abstractions**: Rayon for parallelism without overhead
4. **Single binary**: Easy deployment, no runtime dependencies

## Consequences
- **Positive**: 0.097ms latency, 10K+ EPS throughput, memory-efficient
- **Negative**: Requires Rust toolchain for development, steeper learning curve
- **Mitigation**: PyO3 provides seamless Python integration; most users only need Python

## Alternatives Considered
- **Go**: Good performance but less control over memory layout
- **C++**: Maximum performance but no memory safety guarantees
- **Pure Python**: Too slow for real-time analysis (100ms+ per event)
