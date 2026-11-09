//! A Script Filter driven by `$WE_LOVE_ALFRED_CONFIG`, else `./workflow.toml` (Alfred runs
//! scripts in the workflow folder). Background refreshes inherit both, so they find it too.

use we_love_alfred::{Item, Workflow};

#[tokio::main(flavor = "current_thread")]
async fn main() -> we_love_alfred::Result<()> {
    let config = std::env::var("WE_LOVE_ALFRED_CONFIG").unwrap_or_else(|_| "workflow.toml".into());
    Workflow::load(config)
        .await?
        .provider(|| async {
            Ok(vec![
                Item::arg("Hello from Rust", "hello").subtitle("a provider item"),
            ])
        })
        .run(std::env::args().skip(1))
        .await
}
