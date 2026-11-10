//! Build a query route's database: with a registered Rust function, or from JSON (a file or a
//! URL) through a jq filter whose output objects become rows.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::time::Duration;

use futures_util::future::BoxFuture;
use jaq_core::load::{Arena, File, Loader};
use jaq_core::{Compiler, Ctx, Vars, data, unwrap_valr};
use reqwest::Client;
use rusqlite::{Connection, params_from_iter};
use serde::Deserialize;
use serde_json::{Map, Value};
use tokio::fs;

use crate::cache::{expand_home, with_suffix};
use crate::{Error, Result};

/// A Rust function that writes a database at the path it's given.
pub type Populator = Box<dyn Fn(PathBuf) -> BoxFuture<'static, Result<()>> + Send + Sync>;

/// A route's `populate`: a function name, or a data source table.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(untagged)]
pub enum Populate {
    Function(String),
    Data(DataSource),
}

/// JSON from a `file` or `url`, filtered by `jq` into row objects, loaded into `table`.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DataSource {
    pub file: Option<String>,
    pub url: Option<String>,
    /// Each output object is one row; its keys become columns, in order of first appearance.
    #[serde(default = "every_element")]
    pub jq: String,
    pub table: String,
    /// An FTS5 table, so routes can `match` it.
    #[serde(default)]
    pub fts: bool,
}

fn every_element() -> String {
    ".[]".into()
}

/// Build the database at `db` into a temporary file, renamed into place only once complete.
pub(crate) async fn build(
    populate: &Populate,
    db: &Path,
    functions: &BTreeMap<String, Populator>,
) -> Result<()> {
    if let Some(parent) = db.parent() {
        fs::create_dir_all(parent).await?;
    }
    let partial = with_suffix(db, &format!(".{}.partial", std::process::id()));
    let _ = fs::remove_file(&partial).await;
    let built = match populate {
        Populate::Function(name) => match functions.get(name) {
            Some(function) => function(partial.clone()).await,
            None => Err(Error::Config(format!(
                "no populate function named {name:?}"
            ))),
        },
        Populate::Data(source) => from_data(source, &partial).await,
    };
    match built {
        Ok(()) => Ok(fs::rename(&partial, db).await?),
        Err(e) => {
            let _ = fs::remove_file(&partial).await;
            Err(e)
        }
    }
}

async fn from_data(source: &DataSource, db: &Path) -> Result<()> {
    let json = match (&source.file, &source.url) {
        (Some(file), None) => fs::read(expand_home(file)).await?,
        (None, Some(url)) => {
            let client = Client::builder()
                .timeout(Duration::from_secs(120))
                .build()?;
            client
                .get(url)
                .send()
                .await?
                .error_for_status()?
                .bytes()
                .await?
                .to_vec()
        }
        _ => {
            return Err(Error::Config(
                "populate needs exactly one of file, url".into(),
            ));
        }
    };
    let rows = jq(&source.jq, &json)?;
    let (db, table, fts) = (db.to_owned(), source.table.clone(), source.fts);
    tokio::task::spawn_blocking(move || write_table(&db, &table, fts, &rows))
        .await
        .map_err(|e| Error::Config(format!("populate task failed: {e}")))?
}

/// Run `filter` over `input`; every output must be an object.
fn jq(filter: &str, input: &[u8]) -> Result<Vec<Map<String, Value>>> {
    let jq_error =
        |what: &str, detail: String| Error::Config(format!("jq {what} {filter:?}: {detail}"));
    let input =
        jaq_json::read::parse_single(input).map_err(|e| jq_error("input for", e.to_string()))?;
    let defs = jaq_core::defs()
        .chain(jaq_std::defs())
        .chain(jaq_json::defs());
    let funs = jaq_core::funs()
        .chain(jaq_std::funs())
        .chain(jaq_json::funs());
    let arena = Arena::default();
    let modules = Loader::new(defs)
        .load(
            &arena,
            File {
                code: filter,
                path: (),
            },
        )
        .map_err(|e| jq_error("parse", format!("{e:?}")))?;
    let compiled = Compiler::default()
        .with_funs(funs)
        .compile(modules)
        .map_err(|e| jq_error("compile", format!("{e:?}")))?;
    let ctx = Ctx::<data::JustLut<jaq_json::Val>>::new(&compiled.lut, Vars::new([]));
    compiled
        .id
        .run((ctx, input))
        .map(unwrap_valr)
        .map(|out| {
            let out = out.map_err(|e| jq_error("run", e.to_string()))?;
            match serde_json::from_str(&out.to_string())? {
                Value::Object(row) => Ok(row),
                other => Err(jq_error(
                    "output of",
                    format!("expected objects, got {other}"),
                )),
            }
        })
        .collect()
}

/// `table` with a column per key, every row inserted in one transaction.
fn write_table(db: &Path, table: &str, fts: bool, rows: &[Map<String, Value>]) -> Result<()> {
    let mut columns: Vec<&str> = Vec::new();
    for key in rows.iter().flat_map(Map::keys) {
        if !columns.contains(&key.as_str()) {
            columns.push(key);
        }
    }
    if columns.is_empty() {
        return Err(Error::Config(format!(
            "populate for {table:?} produced no columns"
        )));
    }
    // Keys come from downloaded data, so every identifier is quoted.
    let list = columns
        .iter()
        .map(|c| quote(c))
        .collect::<Vec<_>>()
        .join(", ");
    let create = if fts {
        format!("create virtual table {} using fts5({list})", quote(table))
    } else {
        format!("create table {} ({list})", quote(table))
    };
    let mut connection = Connection::open(db)?;
    let transaction = connection.transaction()?;
    transaction.execute(&create, [])?;
    {
        let placeholders = vec!["?"; columns.len()].join(", ");
        let mut insert = transaction.prepare(&format!(
            "insert into {} ({list}) values ({placeholders})",
            quote(table)
        ))?;
        for row in rows {
            insert.execute(params_from_iter(
                columns.iter().map(|c| sql_value(row.get(*c))),
            ))?;
        }
    }
    transaction.commit()?;
    Ok(())
}

fn quote(identifier: &str) -> String {
    format!("\"{}\"", identifier.replace('"', "\"\""))
}

fn sql_value(value: Option<&Value>) -> rusqlite::types::Value {
    use rusqlite::types::Value as Sql;
    match value {
        None | Some(Value::Null) => Sql::Null,
        Some(Value::Bool(b)) => Sql::Integer(i64::from(*b)),
        Some(Value::Number(n)) => n
            .as_i64()
            .map_or_else(|| Sql::Real(n.as_f64().unwrap_or_default()), Sql::Integer),
        Some(Value::String(s)) => Sql::Text(s.clone()),
        Some(nested) => Sql::Text(nested.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const DATA: &str = r#"{"results": [
        {"name": "Heart attack", "id": 22298006, "tags": ["cardiac"]},
        {"name": "Odd \"column\"", "id": 1, "weird key\"": true}
    ]}"#;

    #[test]
    fn jq_turns_json_into_rows() {
        let rows = jq(".results[] | {title: .name, code: .id}", DATA.as_bytes()).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0]["title"], "Heart attack");
        assert!(
            jq(".results[].id", DATA.as_bytes()).is_err(),
            "rows must be objects"
        );
        assert!(
            jq(".results[", DATA.as_bytes()).is_err(),
            "parse errors are reported"
        );
    }

    #[tokio::test]
    async fn builds_fts_tables_from_files_and_functions() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("data.json"), DATA).unwrap();
        let source = DataSource {
            file: Some(dir.path().join("data.json").display().to_string()),
            url: None,
            jq: ".results[]".into(),
            table: "codes".into(),
            fts: true,
        };
        let db = dir.path().join("out/codes.db");
        build(&Populate::Data(source), &db, &BTreeMap::new())
            .await
            .unwrap();
        let connection = Connection::open(&db).unwrap();
        let hit: String = connection
            .query_row(
                "select name from codes where codes match 'heart'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(hit, "Heart attack");
        let quoted: i64 = connection
            .query_row(r#"select "weird key""" from codes where id = 1"#, [], |r| {
                r.get(0)
            })
            .unwrap();
        assert_eq!(
            quoted, 1,
            "hostile keys are quoted, booleans stored as integers"
        );
        assert_eq!(
            std::fs::read_dir(dir.path().join("out")).unwrap().count(),
            1,
            "no partial file left"
        );

        let mut functions: BTreeMap<String, Populator> = BTreeMap::new();
        functions.insert(
            "one".into(),
            Box::new(|path: PathBuf| {
                Box::pin(async move {
                    Connection::open(path)?
                        .execute_batch("create table t(x); insert into t values (1);")?;
                    Ok(())
                })
            }),
        );
        build(&Populate::Function("one".into()), &db, &functions)
            .await
            .unwrap();
        let x: i64 = Connection::open(&db)
            .unwrap()
            .query_row("select x from t", [], |r| r.get(0))
            .unwrap();
        assert_eq!(x, 1, "a function rebuild replaces the file");
        assert!(matches!(
            build(&Populate::Function("nope".into()), &db, &functions).await,
            Err(Error::Config(_))
        ));
        assert!(db.exists(), "a failed rebuild keeps the old database");
    }
}
