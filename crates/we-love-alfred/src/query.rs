//! Read-only SQLite queries behind `[[route]]`s with `db` and `sql`.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use rusqlite::types::ValueRef;
use rusqlite::{Connection, OpenFlags};
use tokio::fs;
use toml::{Table, Value};

use crate::cache::{cache_dir, replace};
use crate::route::{QuerySpec, expand};
use crate::{Error, ItemBuilder, Result};

/// The query text as SQL parameters. It only ever reaches SQLite bound, never spliced into SQL.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Params {
    /// `:query`: the text after the keyword, trimmed.
    query: String,
    /// `:fts`: every word as an FTS5 prefix match, `"heart"* "attack"*`.
    fts: String,
    /// `:words`: the words, lowercased and space-joined.
    words: String,
    /// `:first`: the first word, lowercased.
    first: String,
}

impl Params {
    pub(crate) fn new(text: &str) -> Self {
        // Letters, digits, `.` and `-` only, so a word can't break out of its FTS5 quotes.
        let words: Vec<&str> = text
            .split(|c: char| !(c.is_alphanumeric() || c == '.' || c == '-'))
            .filter(|w| !w.is_empty())
            .collect();
        Self {
            query: text.trim().to_owned(),
            fts: words
                .iter()
                .map(|w| format!("\"{w}\"*"))
                .collect::<Vec<_>>()
                .join(" "),
            words: words.join(" ").to_lowercase(),
            first: words.first().map(|w| w.to_lowercase()).unwrap_or_default(),
        }
    }

    pub(crate) fn is_empty(&self) -> bool {
        self.words.is_empty()
    }

    fn named(&self) -> [(&'static str, &str); 4] {
        [
            (":query", &self.query),
            (":fts", &self.fts),
            (":words", &self.words),
            (":first", &self.first),
        ]
    }
}

/// A matched query route, rendered for one query.
#[derive(Debug)]
pub(crate) struct QueryPlan<'a> {
    pub spec: &'a QuerySpec,
    pub vars: &'a Table,
    pub db: PathBuf,
    pub sql: String,
    /// Index of the route, for the background rebuild command.
    pub route: usize,
    pub params: Params,
    pub literals: BTreeMap<String, Value>,
}

impl QueryPlan<'_> {
    /// Run the query and render the route's items once per row, with columns bound as `{column}`.
    pub async fn run(self) -> Result<Vec<ItemBuilder>> {
        let db = if self.spec.cache_copy {
            local_copy(&self.db).await?
        } else {
            self.db.clone()
        };
        let (path, sql, params) = (db.clone(), self.sql.clone(), self.params.clone());
        let rows = match tokio::task::spawn_blocking(move || rows(&path, &sql, &params)).await? {
            Ok(rows) => rows,
            Err(e) => {
                // A copy torn by a killed run stays malformed; the next keystroke copies afresh.
                if self.spec.cache_copy {
                    let _ = fs::remove_file(db).await;
                }
                return Err(e);
            }
        };
        let mut items = Vec::new();
        for row in rows {
            let mut literals = self.literals.clone();
            literals.extend(row);
            items.extend(expand(&self.spec.items, self.vars, &literals)?);
        }
        Ok(items)
    }
}

/// Every row as column name → value; NULLs and blobs become empty strings.
fn rows(db: &Path, sql: &str, params: &Params) -> Result<Vec<BTreeMap<String, Value>>> {
    let connection = Connection::open_with_flags(
        db,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )?;
    let mut statement = connection.prepare(sql)?;
    for (name, value) in params.named() {
        // Bind only the parameters the SQL uses; unknown names are an error in SQLite.
        if let Some(index) = statement.parameter_index(name)? {
            statement.raw_bind_parameter(index, value)?;
        }
    }
    let columns: Vec<String> = statement.column_names().map(str::to_owned).collect();
    let mut out = Vec::new();
    let mut rows = statement.raw_query();
    while let Some(row) = rows.next()? {
        let mut record = BTreeMap::new();
        for (i, column) in columns.iter().enumerate() {
            let value = match row.get_ref(i)? {
                ValueRef::Integer(n) => Value::Integer(n),
                ValueRef::Real(n) => Value::Float(n),
                ValueRef::Text(text) => Value::String(String::from_utf8_lossy(text).into_owned()),
                ValueRef::Null | ValueRef::Blob(_) => Value::String(String::new()),
            };
            record.insert(column.clone(), value);
        }
        out.push(record);
    }
    Ok(out)
}

/// A copy of `db` in the cache dir, refreshed when the original is newer. iCloud can evict files
/// in a synced workflow folder, and reading an evicted file waits on a download.
async fn local_copy(db: &Path) -> Result<PathBuf> {
    let name = db
        .file_name()
        .ok_or_else(|| Error::Config(format!("db path {} has no file name", db.display())))?;
    let local = cache_dir().join("db").join(name);
    let modified = |m: std::io::Result<std::fs::Metadata>| {
        m.and_then(|m| m.modified())
            .unwrap_or(SystemTime::UNIX_EPOCH)
    };
    if !fs::try_exists(&local).await.unwrap_or(false)
        || modified(fs::metadata(db).await) > modified(fs::metadata(&local).await)
    {
        replace(&local, |temporary| async move {
            Ok(fs::copy(db, temporary).await.map(drop)?)
        })
        .await?;
    }
    Ok(local)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn words_become_bound_fts_prefixes() {
        let params = Params::new("  Heart  attack'); drop table x;-- ");
        assert_eq!(
            params.fts,
            r#""Heart"* "attack"* "drop"* "table"* "x"* "--"*"#
        );
        assert_eq!(params.words, "heart attack drop table x --");
        assert_eq!(params.first, "heart");
        assert!(Params::new(" ?! ").is_empty());
    }
}
