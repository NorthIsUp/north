//! Build a query route's database: with a registered Rust function, or from JSON (a file or a
//! URL) through a jq filter whose output objects become rows.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::time::Duration;

use futures_util::future::{self, BoxFuture};
use jaq_core::load::{Arena, File, Loader};
use jaq_core::{Compiler, Ctx, Vars, data, unwrap_valr};
use reqwest::Client;
use rusqlite::{Connection, params_from_iter};
use serde::Deserialize;
use serde_json::{Map, Value};
use tokio::fs;

use crate::cache::{expand_home, replace};
use crate::shell::{output, tool};
use crate::{Error, Result};

/// A Rust function that writes a database at the path it's given.
pub type Populator = Box<dyn Fn(PathBuf) -> BoxFuture<'static, Result<()>> + Send + Sync>;

/// A route's `populate`: a function name, a data source, or a list of sources.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(untagged)]
pub enum Populate {
    Function(String),
    Data(DataSource),
    /// Fetched concurrently; rows for the same table are appended together. A failing source is
    /// skipped, so one missing tool doesn't empty the database, unless every source fails.
    Sources(Vec<DataSource>),
}

/// JSON from a `file`, `url` or `command`, filtered by `jq` into row objects, loaded into `table`.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(try_from = "RawDataSource")]
pub struct DataSource {
    pub from: Origin,
    /// Each output object is one row; its keys become columns, in order of first appearance.
    pub jq: String,
    pub table: String,
    /// An FTS5 table, so routes can `match` it.
    pub fts: bool,
}

/// Where a [`DataSource`] reads its JSON.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Origin {
    File(String),
    Url(String),
    /// An argv whose stdout is the JSON, run with Alfred's tool PATH.
    Command(Vec<String>),
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawDataSource {
    file: Option<String>,
    url: Option<String>,
    command: Option<Vec<String>>,
    #[serde(default = "every_element")]
    jq: String,
    table: String,
    #[serde(default)]
    fts: bool,
}

impl TryFrom<RawDataSource> for DataSource {
    type Error = String;

    fn try_from(raw: RawDataSource) -> Result<Self, String> {
        let from = match (raw.file, raw.url, raw.command) {
            (Some(file), None, None) => Origin::File(file),
            (None, Some(url), None) => Origin::Url(url),
            (None, None, Some(command)) if !command.is_empty() => Origin::Command(command),
            _ => {
                return Err(
                    "populate needs exactly one of file, url, command (a non-empty argv)".into(),
                );
            }
        };
        Ok(Self {
            from,
            jq: raw.jq,
            table: raw.table,
            fts: raw.fts,
        })
    }
}

const COMMAND_TIMEOUT: Duration = Duration::from_secs(120);

fn every_element() -> String {
    ".[]".into()
}

/// Build the database at `db` atomically: readers keep the old file until the new one is complete.
pub(crate) async fn build(
    populate: &Populate,
    db: &Path,
    functions: &BTreeMap<String, Populator>,
) -> Result<()> {
    replace(db, |temporary| async move {
        match populate {
            Populate::Function(name) => {
                let function = functions
                    .get(name)
                    .ok_or_else(|| Error::Config(format!("no populate function named {name:?}")))?;
                function(temporary).await
            }
            Populate::Data(source) => from_sources(std::slice::from_ref(source), &temporary).await,
            Populate::Sources(sources) => from_sources(sources, &temporary).await,
        }
    })
    .await
}

async fn from_sources(sources: &[DataSource], db: &Path) -> Result<()> {
    let fetched = future::join_all(
        sources
            .iter()
            .map(|source| async move { Ok::<_, Error>((source, rows(source).await?)) }),
    )
    .await;
    let mut tables: BTreeMap<String, (bool, Vec<Map<String, Value>>)> = BTreeMap::new();
    let mut first_error = None;
    for result in fetched {
        match result {
            Ok((source, rows)) => {
                let (fts, table) = tables.entry(source.table.clone()).or_default();
                *fts |= source.fts;
                table.extend(rows);
            }
            Err(e) => {
                log::warn!("populate source failed: {e}");
                first_error.get_or_insert(e);
            }
        }
    }
    if tables.is_empty() {
        return Err(first_error.unwrap_or_else(|| Error::Config("populate has no sources".into())));
    }
    let db = db.to_owned();
    tokio::task::spawn_blocking(move || {
        tables
            .iter()
            .try_for_each(|(table, (fts, rows))| write_table(&db, table, *fts, rows))
    })
    .await?
}

/// A source's rows: its JSON through its jq filter.
async fn rows(source: &DataSource) -> Result<Vec<Map<String, Value>>> {
    let json = match &source.from {
        Origin::File(file) => fs::read(expand_home(file)).await?,
        Origin::Url(url) => {
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
        Origin::Command(command) => {
            let (program, rest) = command
                .split_first()
                .ok_or_else(|| Error::Config("empty populate command".into()))?;
            output(tool(program).args(rest), COMMAND_TIMEOUT)
                .await?
                .into_bytes()
        }
    };
    jq(&source.jq, &json)
}

/// Run `filter` over `input`; every output must be an object.
fn jq(filter: &str, input: &[u8]) -> Result<Vec<Map<String, Value>>> {
    let jq_error = |what: &str, detail: String| Error::Jq(format!("{what} {filter:?}: {detail}"));
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
        return Err(Error::Jq(format!("rows for {table:?} have no columns")));
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

    #[tokio::test]
    async fn appends_sources_into_one_table_and_skips_failures() {
        let _serial = crate::serial().await;
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join("a.json"),
            r#"[{"tool": "a", "code": "A1"}]"#,
        )
        .unwrap();
        std::fs::write(
            dir.path().join("b.json"),
            r#"[{"tool": "b", "code": "B1", "url": "u"}]"#,
        )
        .unwrap();
        let populate: Populate = toml::from_str::<toml::Table>(&format!(
            r#"populate = [
                {{ file = "{dir}/a.json", table = "rules", fts = true }},
                {{ command = ["cat", "{dir}/b.json"], table = "rules" }},
                {{ file = "{dir}/missing.json", table = "rules" }},
            ]"#,
            dir = dir.path().display()
        ))
        .unwrap()["populate"]
            .clone()
            .try_into()
            .unwrap();
        let db = dir.path().join("all.db");
        build(&populate, &db, &BTreeMap::new()).await.unwrap();
        let connection = Connection::open(&db).unwrap();
        let tools: Vec<String> = connection
            .prepare("select tool || code || coalesce(url, '') from rules order by tool")
            .unwrap()
            .query_map([], |r| r.get(0))
            .unwrap()
            .map(Result::unwrap)
            .collect();
        assert_eq!(
            tools,
            ["aA1", "bB1u"],
            "columns are the union; the missing file is skipped"
        );
        let all_missing = Populate::Sources(vec![DataSource {
            from: Origin::File("/nonexistent.json".into()),
            jq: ".[]".into(),
            table: "t".into(),
            fts: false,
        }]);
        assert!(
            build(&all_missing, &dir.path().join("none.db"), &BTreeMap::new())
                .await
                .is_err()
        );
    }

    #[tokio::test]
    async fn builds_from_a_command() {
        let _serial = crate::serial().await;
        let dir = tempfile::tempdir().unwrap();
        let source: DataSource = toml::from_str(
            r#"command = ["/bin/sh", "-c", "printf '[{\"code\": \"TID251\", \"name\": \"banned-api\"}]'"]
               table = "rules""#,
        )
        .unwrap();
        let db = dir.path().join("rules.db");
        build(&Populate::Data(source), &db, &BTreeMap::new())
            .await
            .unwrap();
        let name: String = Connection::open(&db)
            .unwrap()
            .query_row("select name from rules where code = 'TID251'", [], |r| {
                r.get(0)
            })
            .unwrap();
        assert_eq!(name, "banned-api");
        assert!(toml::from_str::<DataSource>("command = []\ntable = 't'").is_err());
        assert!(toml::from_str::<DataSource>("file = 'a'\ncommand = ['x']\ntable = 't'").is_err());
    }

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
            from: Origin::File(dir.path().join("data.json").display().to_string()),
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
