//! Sigma rule engine - compatible with official Sigma YAML syntax
//!
//! Performance optimizations:
//! - Rule pre-filtering by logsource (product/service/category)
//! - Parallel evaluation with Rayon
//! - Compiled regex caching

use crate::types::{LogEvent, RuleHit};
use anyhow::Result;
use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;

mod ast;
mod evaluator;
mod parser;

pub use ast::{Condition, Detection, Selection};
pub use parser::SigmaRule;

/// Sigma rule engine with pre-filtering index
#[cfg_attr(feature = "pyo3", pyo3::prelude::pyclass)]
pub struct SigmaEngine {
    rules: Vec<SigmaRule>,
    evaluator: Arc<evaluator::Evaluator>,
    // Index: product -> rule indices
    product_index: HashMap<String, Vec<usize>>,
    // Index: service -> rule indices
    service_index: HashMap<String, Vec<usize>>,
    // Index: category -> rule indices
    #[allow(dead_code)] // Reserved for future category-based filtering
    category_index: HashMap<String, Vec<usize>>,
    // Rules with no logsource filter (always evaluate)
    always_evaluate: Vec<usize>,
}

impl SigmaEngine {
    /// Create a new Sigma engine by loading rules from a directory
    pub fn new(rules_dir: String) -> Result<Self> {
        let path = Path::new(&rules_dir);
        let rules = Self::load_rules(path)?;

        let (product_index, service_index, category_index, always_evaluate) =
            Self::build_indices(&rules);

        Ok(Self {
            evaluator: Arc::new(evaluator::Evaluator::new()),
            rules,
            product_index,
            service_index,
            category_index,
            always_evaluate,
        })
    }

    /// Evaluate a log event against relevant rules (with pre-filtering)
    pub fn evaluate(&self, log: &LogEvent) -> Vec<RuleHit> {
        // Pre-filter rules based on log characteristics
        let candidate_indices = self.get_candidate_rules(log);

        // Evaluate only candidate rules in parallel
        self.evaluate_candidates_parallel(log, &candidate_indices)
    }

    /// Evaluate a batch of log events concurrently.
    ///
    /// Parallelism is across logs (each log independently evaluated against its
    /// candidate rules), which amortizes per-log rayon scheduling overhead and
    /// dramatically improves throughput for bulk/streaming ingestion.
    pub fn evaluate_batch(&self, logs: &[LogEvent]) -> Vec<Vec<RuleHit>> {
        use crate::metrics::global as metrics;
        use rayon::prelude::*;
        use std::sync::atomic::Ordering;

        let start = std::time::Instant::now();

        let results: Vec<Vec<RuleHit>> = logs
            .par_iter()
            .map(|log| {
                let candidates = self.get_candidate_rules(log);
                self.evaluate_candidates_parallel(log, &candidates)
            })
            .collect();

        let elapsed_us = start.elapsed().as_micros() as u64;
        let m = metrics();
        m.batches_total.fetch_add(1, Ordering::Relaxed);
        m.batch_events_total
            .fetch_add(logs.len() as u64, Ordering::Relaxed);
        m.batch_time_us_total
            .fetch_add(elapsed_us, Ordering::Relaxed);
        m.eval_time_us_total
            .fetch_add(elapsed_us, Ordering::Relaxed);

        results
    }

    /// Get number of loaded rules
    pub fn rule_count(&self) -> usize {
        self.rules.len()
    }
}

// Python bindings (requires pyo3 feature)
#[cfg(feature = "pyo3")]
#[pyo3::prelude::pymethods]
impl SigmaEngine {
    #[new]
    pub fn py_new(rules_dir: String) -> pyo3::PyResult<Self> {
        Self::new(rules_dir).map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))
    }

    /// Number of loaded rules (Python-accessible).
    #[pyo3(name = "rule_count")]
    pub fn py_rule_count(&self) -> usize {
        self.rule_count()
    }

    /// Evaluate a single log (Python dict) against all relevant rules.
    ///
    /// Returns a list of hit dicts:
    /// `{rule_id, rule_name, technique, confidence, severity, reason}`.
    #[pyo3(name = "evaluate")]
    pub fn py_evaluate<'py>(
        &self,
        py: pyo3::Python<'py>,
        log: &pyo3::Bound<'py, pyo3::types::PyDict>,
    ) -> pyo3::PyResult<pyo3::Bound<'py, pyo3::types::PyList>> {
        let event = py_dict_to_log_event(log)?;
        let hits = self.evaluate(&event);
        rule_hits_to_pylist(py, &hits)
    }

    /// Evaluate a batch of logs (list of Python dicts) in parallel.
    ///
    /// Returns a list (per input log) of lists of hit dicts.
    #[pyo3(name = "evaluate_batch")]
    pub fn py_evaluate_batch<'py>(
        &self,
        py: pyo3::Python<'py>,
        logs: &pyo3::Bound<'py, pyo3::types::PyList>,
    ) -> pyo3::PyResult<pyo3::Bound<'py, pyo3::types::PyList>> {
        use pyo3::types::PyDictMethods;
        use pyo3::types::PyListMethods;
        let mut events = Vec::with_capacity(logs.len());
        for item in logs.iter() {
            let d = item.downcast_into::<pyo3::types::PyDict>()?;
            events.push(py_dict_to_log_event(&d)?);
        }
        let batch = self.evaluate_batch(&events);
        let out = pyo3::types::PyList::empty_bound(py);
        for hits in &batch {
            out.append(rule_hits_to_pylist(py, hits)?)?;
        }
        Ok(out)
    }
}

/// Convert a Python dict into a normalized `LogEvent`.
///
/// `EventID` (case-insensitive) is parsed into the typed `event_id` field;
/// `timestamp` is preserved; every other key becomes a string field.
#[cfg(feature = "pyo3")]
fn py_dict_to_log_event(dict: &pyo3::Bound<'_, pyo3::types::PyDict>) -> pyo3::PyResult<LogEvent> {
    use pyo3::types::PyAnyMethods;
    use pyo3::types::PyDictMethods;
    let mut event = LogEvent::new();
    for (k, v) in dict.iter() {
        let key: String = k.extract()?;
        let val: String = match v.extract::<String>() {
            Ok(s) => s,
            Err(_) => v.str()?.to_string(),
        };
        if key.eq_ignore_ascii_case("EventID") {
            event.event_id = val.parse::<u32>().ok();
        } else if key.eq_ignore_ascii_case("timestamp") {
            event.timestamp = Some(val);
        } else {
            event.set(key, val);
        }
    }
    Ok(event)
}

/// Convert `RuleHit`s into a Python list of dicts.
#[cfg(feature = "pyo3")]
fn rule_hits_to_pylist<'py>(
    py: pyo3::Python<'py>,
    hits: &[RuleHit],
) -> pyo3::PyResult<pyo3::Bound<'py, pyo3::types::PyList>> {
    use crate::types::Severity;
    use pyo3::types::PyDictMethods;
    use pyo3::types::PyListMethods;
    let list = pyo3::types::PyList::empty_bound(py);
    for hit in hits {
        let d = pyo3::types::PyDict::new_bound(py);
        d.set_item("rule_id", &hit.rule_id)?;
        d.set_item("rule_name", &hit.rule_name)?;
        d.set_item("technique", &hit.technique)?;
        d.set_item("confidence", hit.confidence)?;
        let severity = match hit.severity {
            Severity::Low => "low",
            Severity::Medium => "medium",
            Severity::High => "high",
            Severity::Critical => "critical",
        };
        d.set_item("severity", severity)?;
        d.set_item("reason", &hit.reason)?;
        list.append(d)?;
    }
    Ok(list)
}

impl SigmaEngine {
    /// Load all Sigma rules from a directory
    fn load_rules(dir: &Path) -> Result<Vec<SigmaRule>> {
        let mut rules = Vec::new();

        for entry in walkdir::WalkDir::new(dir)
            .follow_links(true)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let path = entry.path();
            if path.extension().and_then(|s| s.to_str()) == Some("yml")
                || path.extension().and_then(|s| s.to_str()) == Some("yaml")
            {
                match SigmaRule::from_file(path) {
                    Ok(rule) => rules.push(rule),
                    Err(e) => {
                        eprintln!("Failed to load rule {}: {}", path.display(), e);
                    }
                }
            }
        }

        Ok(rules)
    }

    /// Build pre-filtering indices
    fn build_indices(
        rules: &[SigmaRule],
    ) -> (
        HashMap<String, Vec<usize>>,
        HashMap<String, Vec<usize>>,
        HashMap<String, Vec<usize>>,
        Vec<usize>,
    ) {
        let mut product_index: HashMap<String, Vec<usize>> = HashMap::new();
        let mut service_index: HashMap<String, Vec<usize>> = HashMap::new();
        let mut category_index: HashMap<String, Vec<usize>> = HashMap::new();
        let mut always_evaluate = Vec::new();

        for (idx, rule) in rules.iter().enumerate() {
            let has_product = !rule.logsource.product.is_empty();
            let has_service = !rule.logsource.service.is_empty();
            let has_category = !rule.logsource.category.is_empty();

            if !has_product && !has_service && !has_category {
                always_evaluate.push(idx);
                continue;
            }

            if has_product {
                product_index
                    .entry(rule.logsource.product.to_lowercase())
                    .or_insert_with(Vec::new)
                    .push(idx);
            }

            if has_service {
                service_index
                    .entry(rule.logsource.service.to_lowercase())
                    .or_insert_with(Vec::new)
                    .push(idx);
            }

            if has_category {
                category_index
                    .entry(rule.logsource.category.to_lowercase())
                    .or_insert_with(Vec::new)
                    .push(idx);
            }
        }

        (
            product_index,
            service_index,
            category_index,
            always_evaluate,
        )
    }

    /// Get candidate rule indices based on log characteristics
    fn get_candidate_rules(&self, log: &LogEvent) -> Vec<usize> {
        let mut candidates = std::collections::HashSet::new();

        // Always include rules with no filter
        candidates.extend(self.always_evaluate.iter().copied());

        // Try to match logsource
        // For Windows/Sysmon logs, we can infer product/service from EventID
        if let Some(event_id) = log.event_id {
            // Sysmon events (EventID 1-25)
            if event_id <= 25 {
                if let Some(indices) = self.service_index.get("sysmon") {
                    candidates.extend(indices.iter().copied());
                }
            }

            // Windows events
            if let Some(indices) = self.product_index.get("windows") {
                candidates.extend(indices.iter().copied());
            }
        }

        // If no matches, evaluate all rules (fallback)
        if candidates.is_empty() {
            return (0..self.rules.len()).collect();
        }

        candidates.into_iter().collect()
    }

    /// Evaluate candidate rules in parallel
    fn evaluate_candidates_parallel(&self, log: &LogEvent, indices: &[usize]) -> Vec<RuleHit> {
        use crate::metrics::global as metrics;
        use rayon::prelude::*;

        let start = std::time::Instant::now();

        let hits: Vec<RuleHit> = indices
            .par_iter()
            .filter_map(|&idx| {
                self.evaluator
                    .evaluate(&self.rules[idx], log)
                    .ok()
                    .flatten()
            })
            .collect();

        // Record metrics once per log event (not per rule)
        let elapsed_us = start.elapsed().as_micros() as u64;
        let m = metrics();
        m.evaluations_total
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        m.eval_time_us_total
            .fetch_add(elapsed_us, std::sync::atomic::Ordering::Relaxed);
        if !hits.is_empty() {
            m.hits_total
                .fetch_add(hits.len() as u64, std::sync::atomic::Ordering::Relaxed);
        }

        hits
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::Ordering;

    #[test]
    fn test_engine_creation() {
        // Test will be implemented with sample rules
    }

    #[test]
    fn test_pre_filtering() {
        // Test that pre-filtering reduces candidate count
    }

    #[test]
    fn test_evaluate_batch_parallel() {
        use crate::types::LogEvent;
        use std::collections::HashMap;

        // Engine needs real rules on disk; if unavailable, skip gracefully.
        let engine = match SigmaEngine::new("../rules".to_string()) {
            Ok(e) if e.rule_count() > 0 => e,
            _ => return, // rules dir not present / empty in this environment
        };

        let make_log = |i: u32| {
            let mut f = HashMap::new();
            f.insert("EventID".to_string(), "1".to_string());
            f.insert("Image".to_string(), "powershell.exe".to_string());
            f.insert(
                "CommandLine".to_string(),
                format!("powershell -enc test {i}"),
            );
            LogEvent {
                event_id: Some(1),
                timestamp: None,
                fields: f,
            }
        };

        let logs: Vec<LogEvent> = (0..16).map(make_log).collect();
        let results = engine.evaluate_batch(&logs);

        // One result vector per input log
        assert_eq!(results.len(), 16);

        // Batch evaluation must produce the same verdicts as per-log evaluation
        for (log, batch_hits) in logs.iter().zip(results.iter()) {
            let single = engine.evaluate(log);
            assert_eq!(batch_hits.len(), single.len());
        }

        // At least the encoded-powershell logs produce hits
        let total_hits: usize = results.iter().map(|h| h.len()).sum();
        assert!(total_hits > 0);

        // Batch metrics were recorded
        assert!(
            crate::metrics::global()
                .batches_total
                .load(Ordering::Relaxed)
                >= 1
        );
    }
}
