//! Sigma rule AST (Abstract Syntax Tree)
//!
//! Full support for Sigma condition syntax including:
//! - Boolean logic: and, or, not
//! - Selection patterns: 1 of *, all of *
//! - Parentheses for grouping

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Detection logic
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Detection {
    #[serde(flatten)]
    pub selections: HashMap<String, Selection>,
    pub condition: String,
}

/// A selection (field matching criteria)
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Selection {
    /// Simple field-value match
    FieldMap(HashMap<String, FieldValue>),

    /// List of values (OR)
    ValueList(Vec<String>),

    /// Single value
    SingleValue(String),
}

/// Field value matcher
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum FieldValue {
    /// Exact match
    Exact(String),

    /// List of possible values (OR)
    List(Vec<String>),

    /// With modifiers (contains, startswith, endswith, etc.)
    WithModifier(HashMap<String, String>),
}

/// Condition (boolean logic) - Full implementation
#[derive(Debug, Clone, PartialEq)]
pub enum Condition {
    /// Logical AND
    And(Box<Condition>, Box<Condition>),

    /// Logical OR
    Or(Box<Condition>, Box<Condition>),

    /// Logical NOT
    Not(Box<Condition>),

    /// Reference to a selection by name
    Selection(String),

    /// "1 of pattern" - at least one selection matching pattern must match
    OneOf(String),

    /// "all of pattern" - all selections matching pattern must match
    AllOf(String),
}

impl Condition {
    /// Parse condition string with full Sigma syntax support
    ///
    /// Examples:
    /// - "selection"
    /// - "selection1 and selection2"
    /// - "selection1 or selection2"
    /// - "not selection"
    /// - "1 of selection*"
    /// - "all of selection*"
    /// - "(selection1 or selection2) and not filter"
    pub fn parse(s: &str) -> Result<Self, String> {
        let tokens = Self::tokenize(s)?;
        let mut parser = ConditionParser::new(tokens);
        parser.parse_expression()
    }

    fn tokenize(s: &str) -> Result<Vec<Token>, String> {
        let mut tokens = Vec::new();
        let mut chars = s.chars().peekable();

        while let Some(&c) = chars.peek() {
            match c {
                ' ' | '\t' | '\n' => {
                    chars.next();
                }
                '(' => {
                    tokens.push(Token::LeftParen);
                    chars.next();
                }
                ')' => {
                    tokens.push(Token::RightParen);
                    chars.next();
                }
                _ => {
                    let mut word = String::new();
                    while let Some(&c) = chars.peek() {
                        if c.is_alphanumeric() || c == '_' || c == '*' {
                            word.push(c);
                            chars.next();
                        } else {
                            break;
                        }
                    }

                    match word.as_str() {
                        "and" => tokens.push(Token::And),
                        "or" => tokens.push(Token::Or),
                        "not" => tokens.push(Token::Not),
                        "1" => {
                            // Expect "of" next
                            chars.next(); // skip space
                            let mut of_word = String::new();
                            while let Some(&c) = chars.peek() {
                                if c.is_alphabetic() {
                                    of_word.push(c);
                                    chars.next();
                                } else {
                                    break;
                                }
                            }
                            if of_word == "of" {
                                tokens.push(Token::OneOf);
                            } else {
                                return Err(format!("Expected 'of' after '1', got '{}'", of_word));
                            }
                        }
                        "all" => {
                            // Expect "of" next
                            chars.next(); // skip space
                            let mut of_word = String::new();
                            while let Some(&c) = chars.peek() {
                                if c.is_alphabetic() {
                                    of_word.push(c);
                                    chars.next();
                                } else {
                                    break;
                                }
                            }
                            if of_word == "of" {
                                tokens.push(Token::AllOf);
                            } else {
                                return Err(format!(
                                    "Expected 'of' after 'all', got '{}'",
                                    of_word
                                ));
                            }
                        }
                        _ => tokens.push(Token::Identifier(word)),
                    }
                }
            }
        }

        Ok(tokens)
    }
}

#[derive(Debug, Clone, PartialEq)]
enum Token {
    And,
    Or,
    Not,
    OneOf,
    AllOf,
    LeftParen,
    RightParen,
    Identifier(String),
}

struct ConditionParser {
    tokens: Vec<Token>,
    pos: usize,
}

impl ConditionParser {
    fn new(tokens: Vec<Token>) -> Self {
        Self { tokens, pos: 0 }
    }

    fn parse_expression(&mut self) -> Result<Condition, String> {
        self.parse_or()
    }

    fn parse_or(&mut self) -> Result<Condition, String> {
        let mut left = self.parse_and()?;

        while self.peek() == Some(&Token::Or) {
            self.advance();
            let right = self.parse_and()?;
            left = Condition::Or(Box::new(left), Box::new(right));
        }

        Ok(left)
    }

    fn parse_and(&mut self) -> Result<Condition, String> {
        let mut left = self.parse_not()?;

        while self.peek() == Some(&Token::And) {
            self.advance();
            let right = self.parse_not()?;
            left = Condition::And(Box::new(left), Box::new(right));
        }

        Ok(left)
    }

    fn parse_not(&mut self) -> Result<Condition, String> {
        if self.peek() == Some(&Token::Not) {
            self.advance();
            let inner = self.parse_not()?;
            return Ok(Condition::Not(Box::new(inner)));
        }

        self.parse_primary()
    }

    fn parse_primary(&mut self) -> Result<Condition, String> {
        match self.peek() {
            Some(&Token::LeftParen) => {
                self.advance();
                let expr = self.parse_expression()?;
                if self.peek() != Some(&Token::RightParen) {
                    return Err("Expected closing parenthesis".to_string());
                }
                self.advance();
                Ok(expr)
            }
            Some(&Token::OneOf) => {
                self.advance();
                if let Some(Token::Identifier(pattern)) = self.peek() {
                    let pattern = pattern.clone();
                    self.advance();
                    Ok(Condition::OneOf(pattern))
                } else {
                    Err("Expected identifier after '1 of'".to_string())
                }
            }
            Some(&Token::AllOf) => {
                self.advance();
                if let Some(Token::Identifier(pattern)) = self.peek() {
                    let pattern = pattern.clone();
                    self.advance();
                    Ok(Condition::AllOf(pattern))
                } else {
                    Err("Expected identifier after 'all of'".to_string())
                }
            }
            Some(Token::Identifier(name)) => {
                let name = name.clone();
                self.advance();
                Ok(Condition::Selection(name))
            }
            _ => Err("Unexpected token".to_string()),
        }
    }

    fn peek(&self) -> Option<&Token> {
        self.tokens.get(self.pos)
    }

    fn advance(&mut self) {
        self.pos += 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_selection() {
        let cond = Condition::parse("selection").unwrap();
        assert_eq!(cond, Condition::Selection("selection".to_string()));
    }

    #[test]
    fn test_and() {
        let cond = Condition::parse("sel1 and sel2").unwrap();
        assert!(matches!(cond, Condition::And(_, _)));
    }

    #[test]
    fn test_or() {
        let cond = Condition::parse("sel1 or sel2").unwrap();
        assert!(matches!(cond, Condition::Or(_, _)));
    }

    #[test]
    fn test_not() {
        let cond = Condition::parse("not sel1").unwrap();
        assert!(matches!(cond, Condition::Not(_)));
    }

    #[test]
    fn test_one_of() {
        let cond = Condition::parse("1 of selection*").unwrap();
        assert_eq!(cond, Condition::OneOf("selection*".to_string()));
    }

    #[test]
    fn test_all_of() {
        let cond = Condition::parse("all of selection*").unwrap();
        assert_eq!(cond, Condition::AllOf("selection*".to_string()));
    }

    #[test]
    fn test_parentheses() {
        let cond = Condition::parse("(sel1 or sel2) and not filter").unwrap();
        assert!(matches!(cond, Condition::And(_, _)));
    }

    #[test]
    fn test_complex() {
        let cond = Condition::parse("1 of selection* and not (filter1 or filter2)").unwrap();
        assert!(matches!(cond, Condition::And(_, _)));
    }
}
