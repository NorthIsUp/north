//! `{name}` / `{name.field}` substitution for config strings.

use std::collections::BTreeMap;
use std::env;

use toml::{Table, Value};

use crate::{Error, Result};

/// Values a template can reference, innermost first: loop bindings, then `[vars]`.
/// `{env.NAME}` reads the environment, `{name:-fallback}` defaults a missing or empty value,
/// and `{{` and `}}` are literal braces.
#[derive(Debug, Clone, Copy)]
pub(crate) struct Scope<'a> {
    pub vars: &'a Table,
    pub bindings: &'a BTreeMap<String, Value>,
    /// Runtime values (query text, regex captures, database rows), inserted verbatim: braces in
    /// them are text, never templates.
    pub literals: &'a BTreeMap<String, Value>,
}

const MAX_DEPTH: usize = 8;

impl Scope<'_> {
    pub fn render(&self, template: &str) -> Result<String> {
        self.render_at(template, 0)
    }

    fn render_at(&self, template: &str, depth: usize) -> Result<String> {
        let mut out = String::with_capacity(template.len());
        let mut rest = template;
        while let Some(i) = rest.find(['{', '}']) {
            out.push_str(&rest[..i]);
            let tail = &rest[i..];
            if let Some(after) = tail.strip_prefix("{{").or_else(|| tail.strip_prefix("}}")) {
                out.push_str(&tail[..1]);
                rest = after;
                continue;
            }
            let end = tail
                .find('}')
                .filter(|_| tail.starts_with('{'))
                .ok_or_else(|| unbalanced(template))?;
            out.push_str(&self.lookup(template, tail[1..end].trim(), depth)?);
            rest = &tail[end + 1..];
        }
        out.push_str(rest);
        Ok(out)
    }

    fn lookup(&self, template: &str, name: &str, depth: usize) -> Result<String> {
        // `{name:-fallback}`: shell-style default when the value is missing or empty.
        if let Some((name, fallback)) = name.split_once(":-") {
            return match self.lookup(template, name.trim(), depth) {
                Ok(value) if !value.is_empty() => Ok(value),
                Ok(_) | Err(Error::Template { .. }) => self.render_at(fallback, depth + 1),
                Err(e) => Err(e),
            };
        }
        let missing = || Error::Template {
            template: template.into(),
            name: name.into(),
        };
        let mut path = name.split('.');
        let root = path.next().unwrap_or_default();
        if root == "env" {
            return env::var(path.next().ok_or_else(missing)?).map_err(|_| missing());
        }
        let literal = self.literals.get(root);
        let mut value = literal
            .or_else(|| self.bindings.get(root))
            .or_else(|| self.vars.get(root))
            .ok_or_else(missing)?;
        for key in path {
            value = value.get(key).ok_or_else(missing)?;
        }
        match value {
            Value::String(s) if literal.is_some() => Ok(s.clone()),
            // Variables may reference other variables.
            Value::String(s) if depth < MAX_DEPTH => self.render_at(s, depth + 1),
            Value::String(s) => Ok(s.clone()),
            Value::Integer(n) => Ok(n.to_string()),
            Value::Float(n) => Ok(n.to_string()),
            Value::Boolean(b) => Ok(b.to_string()),
            _ => Err(missing()),
        }
    }
}

fn unbalanced(template: &str) -> Error {
    Error::Config(format!("unbalanced braces in {template:?}"))
}

/// Every combination of one value from each named list, in order (last name varies fastest).
pub(crate) fn product(each: &BTreeMap<String, Vec<Value>>) -> Vec<BTreeMap<String, Value>> {
    each.iter()
        .fold(vec![BTreeMap::new()], |combos, (name, values)| {
            combos
                .iter()
                .flat_map(|combo| {
                    values.iter().map(move |value| {
                        let mut next = combo.clone();
                        next.insert(name.clone(), value.clone());
                        next
                    })
                })
                .collect()
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn table(raw: &str) -> Table {
        raw.parse().unwrap()
    }

    #[test]
    fn renders_vars_bindings_nested_fields_and_escapes() {
        let vars = table(
            r#"
            domain = "example.com"
            base = "https://{domain}"
            port = 8080
        "#,
        );
        let bindings =
            BTreeMap::from([("svc".to_owned(), Value::Table(table(r#"path = "logs""#)))]);
        let literals = BTreeMap::from([("typed".to_owned(), Value::from("{not a var}"))]);
        let scope = Scope {
            vars: &vars,
            bindings: &bindings,
            literals: &literals,
        };
        assert_eq!(
            scope.render("{base}:{port}/{svc.path} {{x}}").unwrap(),
            "https://example.com:8080/logs {x}"
        );
        assert!(matches!(
            scope.render("{nope}"),
            Err(Error::Template { .. })
        ));
        assert!(matches!(scope.render("{open"), Err(Error::Config(_))));
        assert_eq!(
            scope.render("[{typed}]").unwrap(),
            "[{not a var}]",
            "literals are never templates"
        );
        assert_eq!(
            scope.render("{env.HOME}").unwrap(),
            env::var("HOME").unwrap()
        );
    }

    #[test]
    fn product_varies_last_name_fastest() {
        let each = BTreeMap::from([
            ("a".to_owned(), vec![Value::from(1), Value::from(2)]),
            ("b".to_owned(), vec![Value::from("x"), Value::from("y")]),
        ]);
        let combos: Vec<String> = product(&each)
            .iter()
            .map(|c| format!("{}{}", c["a"], c["b"].as_str().unwrap()))
            .collect();
        assert_eq!(combos, ["1x", "1y", "2x", "2y"]);
        assert_eq!(product(&BTreeMap::new()).len(), 1);
    }
}
