//! Prometheus metrics for Sentinel Core
//!
//! Exposes key performance and operational metrics for monitoring.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Instant;

/// Global metrics registry (thread-safe, lock-free)
pub struct Metrics {
    /// Total rule evaluations performed
    pub evaluations_total: AtomicU64,
    /// Total rule hits (matches)
    pub hits_total: AtomicU64,
    /// Total evaluation time in microseconds
    pub eval_time_us_total: AtomicU64,
    /// Number of rules loaded
    pub rules_loaded: AtomicU64,
    /// Cache hits (condition cache)
    pub condition_cache_hits: AtomicU64,
    /// Cache misses (condition cache)
    pub condition_cache_misses: AtomicU64,
    /// Regex cache hits
    pub regex_cache_hits: AtomicU64,
    /// Regex cache misses
    pub regex_cache_misses: AtomicU64,
    /// Field presence fast-path skips
    pub field_presence_skips: AtomicU64,
    /// EventID fast-path skips
    pub event_id_skips: AtomicU64,
    /// Total batch evaluations performed
    pub batches_total: AtomicU64,
    /// Total events processed in batches
    pub batch_events_total: AtomicU64,
    /// Total batch evaluation time in microseconds
    pub batch_time_us_total: AtomicU64,
}

impl Metrics {
    pub fn new() -> Self {
        Self {
            evaluations_total: AtomicU64::new(0),
            hits_total: AtomicU64::new(0),
            eval_time_us_total: AtomicU64::new(0),
            rules_loaded: AtomicU64::new(0),
            condition_cache_hits: AtomicU64::new(0),
            condition_cache_misses: AtomicU64::new(0),
            regex_cache_hits: AtomicU64::new(0),
            regex_cache_misses: AtomicU64::new(0),
            field_presence_skips: AtomicU64::new(0),
            event_id_skips: AtomicU64::new(0),
            batches_total: AtomicU64::new(0),
            batch_events_total: AtomicU64::new(0),
            batch_time_us_total: AtomicU64::new(0),
        }
    }

    /// Record a rule evaluation
    pub fn record_evaluation(&self, elapsed_us: u64, hit: bool) {
        self.evaluations_total.fetch_add(1, Ordering::Relaxed);
        self.eval_time_us_total.fetch_add(elapsed_us, Ordering::Relaxed);
        if hit {
            self.hits_total.fetch_add(1, Ordering::Relaxed);
        }
    }

    /// Get current EPS (events per second) estimate
    pub fn current_eps(&self) -> f64 {
        let total_evals = self.evaluations_total.load(Ordering::Relaxed);
        let total_time_us = self.eval_time_us_total.load(Ordering::Relaxed);
        if total_time_us == 0 {
            return 0.0;
        }
        total_evals as f64 / (total_time_us as f64 / 1_000_000.0)
    }

    /// Get average latency in microseconds
    pub fn avg_latency_us(&self) -> f64 {
        let total_evals = self.evaluations_total.load(Ordering::Relaxed);
        if total_evals == 0 {
            return 0.0;
        }
        self.eval_time_us_total.load(Ordering::Relaxed) as f64 / total_evals as f64
    }

    /// Export metrics in Prometheus text format
    pub fn export_prometheus(&self) -> String {
        let mut out = String::new();

        out.push_str("# HELP sentinel_evaluations_total Total rule evaluations performed\n");
        out.push_str("# TYPE sentinel_evaluations_total counter\n");
        out.push_str(&format!("sentinel_evaluations_total {}\n", self.evaluations_total.load(Ordering::Relaxed)));

        out.push_str("# HELP sentinel_hits_total Total rule hits\n");
        out.push_str("# TYPE sentinel_hits_total counter\n");
        out.push_str(&format!("sentinel_hits_total {}\n", self.hits_total.load(Ordering::Relaxed)));

        out.push_str("# HELP sentinel_eval_time_us_total Total evaluation time in microseconds\n");
        out.push_str("# TYPE sentinel_eval_time_us_total counter\n");
        out.push_str(&format!("sentinel_eval_time_us_total {}\n", self.eval_time_us_total.load(Ordering::Relaxed)));

        out.push_str("# HELP sentinel_avg_latency_us Average evaluation latency in microseconds\n");
        out.push_str("# TYPE sentinel_avg_latency_us gauge\n");
        out.push_str(&format!("sentinel_avg_latency_us {:.2}\n", self.avg_latency_us()));

        out.push_str("# HELP sentinel_current_eps Current events per second\n");
        out.push_str("# TYPE sentinel_current_eps gauge\n");
        out.push_str(&format!("sentinel_current_eps {:.0}\n", self.current_eps()));

        out.push_str("# HELP sentinel_rules_loaded Number of rules currently loaded\n");
        out.push_str("# TYPE sentinel_rules_loaded gauge\n");
        out.push_str(&format!("sentinel_rules_loaded {}\n", self.rules_loaded.load(Ordering::Relaxed)));

        out.push_str("# HELP sentinel_condition_cache_hits_total Condition cache hits\n");
        out.push_str("# TYPE sentinel_condition_cache_hits_total counter\n");
        out.push_str(&format!("sentinel_condition_cache_hits_total {}\n", self.condition_cache_hits.load(Ordering::Relaxed)));

        out.push_str("# HELP sentinel_condition_cache_misses_total Condition cache misses\n");
        out.push_str("# TYPE sentinel_condition_cache_misses_total counter\n");
        out.push_str(&format!("sentinel_condition_cache_misses_total {}\n", self.condition_cache_misses.load(Ordering::Relaxed)));

        out.push_str("# HELP sentinel_regex_cache_hits_total Regex cache hits\n");
        out.push_str("# TYPE sentinel_regex_cache_hits_total counter\n");
        out.push_str(&format!("sentinel_regex_cache_hits_total {}\n", self.regex_cache_hits.load(Ordering::Relaxed)));

        out.push_str("# HELP sentinel_regex_cache_misses_total Regex cache misses\n");
        out.push_str("# TYPE sentinel_regex_cache_misses_total counter\n");
        out.push_str(&format!("sentinel_regex_cache_misses_total {}\n", self.regex_cache_misses.load(Ordering::Relaxed)));

        out.push_str("# HELP sentinel_field_presence_skips_total Field presence fast-path skips\n");
        out.push_str("# TYPE sentinel_field_presence_skips_total counter\n");
        out.push_str(&format!("sentinel_field_presence_skips_total {}\n", self.field_presence_skips.load(Ordering::Relaxed)));

        out.push_str("# HELP sentinel_event_id_skips_total EventID fast-path skips\n");
        out.push_str("# TYPE sentinel_event_id_skips_total counter\n");
        out.push_str(&format!("sentinel_event_id_skips_total {}\n", self.event_id_skips.load(Ordering::Relaxed)));

        out
    }
}

impl Default for Metrics {
    fn default() -> Self {
        Self::new()
    }
}

/// Global metrics instance
static METRICS: once_cell::sync::Lazy<Arc<Metrics>> =
    once_cell::sync::Lazy::new(|| Arc::new(Metrics::new()));

/// Get the global metrics instance
pub fn global() -> Arc<Metrics> {
    METRICS.clone()
}

/// Timer for measuring evaluation duration
pub struct EvalTimer {
    start: Instant,
    hit: bool,
}

impl EvalTimer {
    pub fn start() -> Self {
        Self {
            start: Instant::now(),
            hit: false,
        }
    }

    pub fn set_hit(&mut self, hit: bool) {
        self.hit = hit;
    }

    /// Finish and record the evaluation
    pub fn finish(self) {
        let elapsed_us = self.start.elapsed().as_micros() as u64;
        global().record_evaluation(elapsed_us, self.hit);
    }
}

impl Drop for EvalTimer {
    fn drop(&mut self) {
        // Auto-finish on drop if not explicitly finished
        let elapsed_us = self.start.elapsed().as_micros() as u64;
        global().record_evaluation(elapsed_us, self.hit);
    }
}
