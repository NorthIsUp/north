/// Same rules as Python's `shlex.quote`: safe strings pass through unquoted.
pub(crate) fn quote(s: &str) -> String {
    let safe = |c: char| c.is_ascii_alphanumeric() || "@%+=:,./_-".contains(c);
    if !s.is_empty() && s.chars().all(safe) {
        s.to_owned()
    } else {
        format!("'{}'", s.replace('\'', r#"'"'"'"#))
    }
}

pub(crate) fn join<S: AsRef<str>>(parts: impl IntoIterator<Item = S>) -> String {
    parts
        .into_iter()
        .map(|part| quote(part.as_ref()))
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quotes_like_shlex() {
        assert_eq!(quote("plain/path-1.json"), "plain/path-1.json");
        assert_eq!(quote(""), "''");
        assert_eq!(quote("it's here"), r#"'it'"'"'s here'"#);
        assert_eq!(join(["open", "a b"]), "open 'a b'");
    }
}
