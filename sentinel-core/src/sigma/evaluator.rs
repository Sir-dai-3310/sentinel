//! Rule evaluator - matches log events against Sigma rules
//!
//! Performance optimizations:
//! - Pre-lowercased log field cache (avoid repeated to_lowercase())
//! - EventID fast-path filtering
//! - Field presence fast-path filtering
//! - Compiled regex caching
//! - Condition parse caching
//! - Zero-copy field access where possible

use super::ast::{Condition, FieldValue, Selection};
use super::parser::SigmaRule;
use crate::types::{LogEvent, RuleHit};
use anyhow::Result;
use regex::Regex;
use std::collections::HashMap;

pub struct Evaluator {
    // Cache compiled regexes for performance
    regex_cache: dashmap::DashMap<String, Regex>,
    // Cache parsed conditions - use pointer address as key to avoid string cloning
    condition_cache: dashmap::DashMap<usize, Condition>,
    // Cache required fields per rule (avoid re-parsing detection on every evaluation)
    rule_fields_cache: dashmap::DashMap<String, Vec<String>>,
}

/// Pre-processed log event with lowercased fields for efficient matching
struct PreparedLog<'a> {
    event: &'a LogEvent,
    // Pre-computed lowercase versions of all fields (computed once, shared by all rules)
    lowercase_fields: HashMap<&'a str, String>,
}

impl<'a> PreparedLog<'a> {
    fn new(event: &'a LogEvent) -> Self {
        // Pre-compute all lowercase fields once
        let mut lowercase_fields = HashMap::with_capacity(event.fields.len());
        for (key, value) in &event.fields {
            // Only lowercase if value contains uppercase (skip already-lowercase values)
            if value.bytes().any(|b| b.is_ascii_uppercase()) {
                lowercase_fields.insert(key.as_str(), value.to_lowercase());
            }
        }
        Self {
            event,
            lowercase_fields,
        }
    }

    /// Get field value (original case) - zero copy
    #[inline(always)]
    fn get(&self, key: &str) -> Option<&'a str> {
        self.event.fields.get(key).map(|s| s.as_str())
    }

    /// Get field value lowercased - zero copy if cached, fallback to computing
    #[inline(always)]
    fn get_lowercase<'b>(&'b self, key: &str) -> Option<std::borrow::Cow<'b, str>> {
        // Check pre-computed cache first
        if let Some(cached) = self.lowercase_fields.get(key) {
            return Some(std::borrow::Cow::Borrowed(cached.as_str()));
        }
        // If not in cache, field is already all-lowercase
        self.event
            .fields
            .get(key)
            .map(|s| std::borrow::Cow::Borrowed(s.as_str()))
    }
}

impl Evaluator {
    pub fn new() -> Self {
        Self {
            regex_cache: dashmap::DashMap::new(),
            condition_cache: dashmap::DashMap::new(),
            rule_fields_cache: dashmap::DashMap::new(),
        }
    }

    /// Evaluate a log event against a rule
    pub fn evaluate(&self, rule: &SigmaRule, log: &LogEvent) -> Result<Option<RuleHit>> {
        // Fast path 1: if rule specifies EventID and log's EventID doesn't match, skip
        if let Some(rule_event_id) = Self::extract_event_id_filter(&rule.detection) {
            if let Some(log_event_id) = log.event_id {
                if rule_event_id != log_event_id.to_string() {
                    return Ok(None);
                }
            } else {
                return Ok(None);
            }
        }

        // Fast path 2: if rule requires fields not present in log, skip
        if !self.rule_fields_present(rule, log) {
            return Ok(None);
        }

        // Prepare log for efficient matching (pre-lowercase fields)
        let mut prepared = PreparedLog::new(log);

        // Evaluate detection logic
        if self.evaluate_detection(&rule.detection, log, &mut prepared)? {
            return Ok(Some(RuleHit {
                rule_id: rule.id.clone(),
                rule_name: rule.title.clone(),
                technique: rule.technique(),
                confidence: rule.severity().to_confidence(),
                severity: rule.severity(),
                reason: rule.description.clone(),
            }));
        }

        Ok(None)
    }

    /// Check if all fields required by the rule are present in the log
    fn rule_fields_present(&self, rule: &SigmaRule, log: &LogEvent) -> bool {
        // Use cached required fields if available
        let cache_key = &rule.id;
        if let Some(cached_fields) = self.rule_fields_cache.get(cache_key) {
            for field_name in cached_fields.iter() {
                if field_name == "EventID" {
                    if log.event_id.is_none() {
                        return false;
                    }
                } else if !log.fields.contains_key(field_name) {
                    return false;
                }
            }
            return true;
        }

        // Compute required fields and cache them
        let mut required_fields = Vec::new();
        for selection in rule.detection.selections.values() {
            if let Selection::FieldMap(fields) = selection {
                for field in fields.keys() {
                    let field_name = field.split('|').next().unwrap_or(field);
                    required_fields.push(field_name.to_string());
                }
            }
        }

        // Check presence
        let all_present = required_fields.iter().all(|field_name| {
            if field_name == "EventID" {
                log.event_id.is_some()
            } else {
                log.fields.contains_key(field_name)
            }
        });

        // Cache for future use
        self.rule_fields_cache
            .insert(cache_key.clone(), required_fields);

        all_present
    }

    /// Extract EventID filter from detection if present (for fast-path filtering)
    fn extract_event_id_filter(detection: &super::ast::Detection) -> Option<String> {
        for selection in detection.selections.values() {
            if let Selection::FieldMap(fields) = selection {
                for (field, value) in fields {
                    let field_name = field.split('|').next().unwrap_or(field);
                    if field_name == "EventID" {
                        if let FieldValue::Exact(v) = value {
                            return Some(v.clone());
                        }
                    }
                }
            }
        }
        None
    }

    fn evaluate_detection(
        &self,
        detection: &super::ast::Detection,
        log: &LogEvent,
        prepared: &mut PreparedLog,
    ) -> Result<bool> {
        // Use the detection struct's address as cache key (avoid string cloning)
        let cache_key = detection as *const _ as usize;

        // Check cache first without inserting
        if let Some(cached) = self.condition_cache.get(&cache_key) {
            let condition = cached.clone();
            drop(cached); // Release the lock immediately
            return self.evaluate_condition(&condition, &detection.selections, log, prepared);
        }

        // Not in cache - parse and insert
        let condition = Condition::parse(&detection.condition)
            .map_err(|e| anyhow::anyhow!("Failed to parse condition: {}", e))?;
        self.condition_cache.insert(cache_key, condition.clone());

        // Evaluate condition
        self.evaluate_condition(&condition, &detection.selections, log, prepared)
    }

    fn evaluate_condition(
        &self,
        condition: &Condition,
        selections: &HashMap<String, Selection>,
        log: &LogEvent,
        prepared: &mut PreparedLog,
    ) -> Result<bool> {
        match condition {
            Condition::And(left, right) => Ok(self
                .evaluate_condition(left, selections, log, prepared)?
                && self.evaluate_condition(right, selections, log, prepared)?),
            Condition::Or(left, right) => Ok(self
                .evaluate_condition(left, selections, log, prepared)?
                || self.evaluate_condition(right, selections, log, prepared)?),
            Condition::Not(inner) => {
                Ok(!self.evaluate_condition(inner, selections, log, prepared)?)
            }
            Condition::Selection(name) => {
                if let Some(selection) = selections.get(name) {
                    self.evaluate_selection(selection, log, prepared)
                } else {
                    Ok(false)
                }
            }
            Condition::OneOf(pattern) => {
                for (name, selection) in selections {
                    if self.matches_pattern(name, pattern) {
                        if self.evaluate_selection(selection, log, prepared)? {
                            return Ok(true);
                        }
                    }
                }
                Ok(false)
            }
            Condition::AllOf(pattern) => {
                let mut found_any = false;
                for (name, selection) in selections {
                    if self.matches_pattern(name, pattern) {
                        found_any = true;
                        if !self.evaluate_selection(selection, log, prepared)? {
                            return Ok(false);
                        }
                    }
                }
                Ok(found_any)
            }
        }
    }

    /// Check if a selection name matches a pattern (supports * wildcard)
    fn matches_pattern(&self, name: &str, pattern: &str) -> bool {
        if pattern == "*" {
            return true;
        }

        if pattern.ends_with('*') {
            let prefix = &pattern[..pattern.len() - 1];
            return name.starts_with(prefix);
        }

        if pattern.starts_with('*') {
            let suffix = &pattern[1..];
            return name.ends_with(suffix);
        }

        name == pattern
    }

    fn evaluate_selection(
        &self,
        selection: &Selection,
        log: &LogEvent,
        prepared: &mut PreparedLog,
    ) -> Result<bool> {
        match selection {
            Selection::FieldMap(fields) => {
                for (field, matcher) in fields {
                    if !self.evaluate_field(field, matcher, log, prepared)? {
                        return Ok(false);
                    }
                }
                Ok(true)
            }
            Selection::ValueList(_values) => Ok(false),
            Selection::SingleValue(_) => Ok(false),
        }
    }

    fn evaluate_field(
        &self,
        field: &str,
        matcher: &FieldValue,
        log: &LogEvent,
        prepared: &mut PreparedLog,
    ) -> Result<bool> {
        let (field_name, modifier) = if let Some(pos) = field.find('|') {
            (&field[..pos], &field[pos + 1..])
        } else {
            (field, "exact")
        };

        // Handle EventID specially (stored in event_id field, not fields map)
        if field_name == "EventID" {
            let event_id_str = log.event_id.map(|id| id.to_string());
            let event_id_cow = std::borrow::Cow::Owned(event_id_str.unwrap_or_default());
            return Ok(self.match_value(&event_id_cow, matcher_value(matcher), modifier));
        }

        // Get field value - use pre-lowercased version for case-insensitive operations
        let log_value = match modifier {
            "exact" => match prepared.get(field_name) {
                Some(v) => std::borrow::Cow::Borrowed(v),
                None => return Ok(false),
            },
            _ => match prepared.get_lowercase(field_name) {
                Some(v) => v,
                None => return Ok(false),
            },
        };

        match matcher {
            FieldValue::Exact(expected) => Ok(self.match_value(&log_value, expected, modifier)),
            FieldValue::List(values) => {
                for expected in values {
                    if self.match_value(&log_value, expected, modifier) {
                        return Ok(true);
                    }
                }
                Ok(false)
            }
            FieldValue::WithModifier(value_map) => {
                for (key, expected) in value_map {
                    if self.match_value(&log_value, expected, key) {
                        return Ok(true);
                    }
                }
                Ok(false)
            }
        }
    }

    #[inline]
    fn match_value(&self, value: &std::borrow::Cow<str>, expected: &str, modifier: &str) -> bool {
        match modifier {
            "exact" => value.as_ref() == expected,
            "contains" => {
                // value is already lowercased (from prepared cache)
                // expected needs to be lowercased only if it has uppercase
                if expected.bytes().any(|b| b.is_ascii_uppercase()) {
                    value.contains(expected.to_lowercase().as_str())
                } else {
                    value.contains(expected)
                }
            }
            "startswith" => {
                if expected.bytes().any(|b| b.is_ascii_uppercase()) {
                    value.starts_with(expected.to_lowercase().as_str())
                } else {
                    value.starts_with(expected)
                }
            }
            "endswith" => {
                if expected.bytes().any(|b| b.is_ascii_uppercase()) {
                    value.ends_with(expected.to_lowercase().as_str())
                } else {
                    value.ends_with(expected)
                }
            }
            "regex" => {
                let regex = self
                    .regex_cache
                    .entry(expected.to_string())
                    .or_insert_with(|| Regex::new(expected).unwrap());
                regex.is_match(value.as_ref())
            }
            _ => value.as_ref() == expected,
        }
    }
}

/// Helper to extract the primary value from a FieldValue
fn matcher_value(matcher: &FieldValue) -> &str {
    match matcher {
        FieldValue::Exact(v) => v,
        FieldValue::List(values) => values.first().map(|s| s.as_str()).unwrap_or(""),
        FieldValue::WithModifier(map) => map.values().next().map(|s| s.as_str()).unwrap_or(""),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn test_matches_pattern() {
        let eval = Evaluator::new();

        assert!(eval.matches_pattern("selection1", "*"));
        assert!(eval.matches_pattern("selection1", "selection*"));
        assert!(eval.matches_pattern("selection1", "*1"));
        assert!(eval.matches_pattern("selection1", "selection1"));
        assert!(!eval.matches_pattern("selection1", "filter*"));
    }
}
