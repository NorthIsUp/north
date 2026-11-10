//! Read-only SQLite queries behind `[[route]]`s with `db` and `sql`.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

use rusqlite::types::ValueRef;
use rusqlite::{Connection, OpenFlags};
use tokio::fs;
use toml::{Table, Value};

use crate::cache::{cache_dir, with_suffix};
use crate::config::ItemConfig;
use crate::populate::Populate;
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

/// A matched query route, ready to run.
#[derive(Debug)]
pub struct QueryPlan {
    pub(crate) db: PathBuf,
    pub(crate) sql: String,
    pub(crate) params: Params,
    pub(crate) cache_copy: bool,
    /// Index of the route in the config, for the background rebuild command.
    pub(crate) route: usize,
    pub(crate) populate: Option<Populate>,
    pub(crate) refresh_every: Option<Duration>,
    pub(crate) error: Option<String>,
    pub(crate) items: Vec<ItemConfig>,
    pub(crate) vars: Table,
    pub(crate) literals: BTreeMap<String, Value>,
}

impl QueryPlan {
    /// Run the query and render the route's items once per row, with columns bound as `{column}`.
    ///
    /// # Errors
    ///
    /// [`Error::Sqlite`] when the database can't be opened or the SQL fails, I/O errors copying it
    /// into the cache, and template errors rendering the items.
    pub async fn run(self) -> Result<Vec<ItemBuilder>> {
        let db = if self.cache_copy {
            local_copy(&self.db).await?
        } else {
            self.db.clone()
        };
        let (sql, params) = (self.sql.clone(), self.params.clone());
        let read =
            tokio::task::spawn_blocking(move || rows(&db, &sql, &params).map_err(|e| (e, db)))
                .await
                .map_err(|e| Error::Config(format!("query task failed: {e}")))?;
        let rows = match read {
            Ok(rows) => rows,
            Err((e, db)) => {
                // A copy torn by a killed run stays malformed; the next keystroke copies afresh.
                if self.cache_copy {
                    let _ = fs::remove_file(db).await;
                }
                return Err(e);
            }
        };
        let mut items = Vec::new();
        for row in rows {
            let mut literals = self.literals.clone();
            literals.extend(row);
            for item in &self.items {
                items.extend(item.expand(&self.vars, &literals)?);
            }
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
        fs::create_dir_all(local.parent().unwrap_or(Path::new("."))).await?;
        // Copy then rename: a run killed mid-copy must not leave a half-written database behind.
        let partial = with_suffix(&local, &format!(".{}.partial", std::process::id()));
        fs::copy(db, &partial).await?;
        fs::rename(&partial, &local).await?;
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
