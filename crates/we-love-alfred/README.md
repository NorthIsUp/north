# we-love-alfred

Fast, cached Alfred Script Filters in Rust. A Rust port of the `we-love-alfred` Python package.

A Script Filter binary serves the cached menu on every keystroke and rebuilds
it in a detached copy of itself when stale. Only the very first run waits for
the full build.

```rust,no_run
use std::env;
use std::process::Command;

use we_love_alfred::{fast, IconSource, Item, Workflow};

fn main() -> we_love_alfred::Result<()> {
    let args: Vec<String> = env::args().skip(1).collect();
    let rebuild = args.first().is_some_and(|a| a == "--no-cache");
    if !rebuild {
        // Rebuilds in the background, at most once a minute.
        let mut refresh = Command::new(env::current_exe()?);
        refresh.arg("--no-cache");
        if fast::serve(&args.join(" "), Some("my-workflow"), Some(refresh))? {
            return Ok(());
        }
    }

    let mut workflow = Workflow::with_cache_name("my-workflow");
    workflow.add(Item::url("GitHub", "https://github.com"));
    workflow.add(Item::exec("Uptime", "uptime").icon(IconSource::Glyph("terminal".into())));
    workflow.add(Item::easy("Copy greeting", "copies hello", "hello"));
    workflow.build()?; // adds "clear cache", resolves icons in parallel, writes the cache
    if !rebuild {
        workflow.print_menu();
    }
    Ok(())
}
```

`fast::serve` returns `Ok(false)` for a missing or malformed cache. A valid
cache is served even when stale. Each query token must be a case-insensitive
subsequence of an item's `match` text (else its `title`). Results are ranked
by title word prefix, then title substring, then `match` substring, then
scattered letters. The filtered response drops Alfred's `cache` field, so
Alfred never reuses one query's results for another.

```rust
use we_love_alfred::{Menu, MenuItem};

let item = |title: &str| MenuItem { title: title.into(), ..Default::default() };
let menu = Menu { items: vec![item("Hello"), item("Other")], ..Default::default() };
assert_eq!(menu.filter("hello").items, [item("Hello")]);
```

Caches live in `$XDG_CACHE_HOME/alfred/`. Without that variable they go in
`~/.cache/alfred/` when `~/.cache` exists, otherwise `/tmp/alfred/`. The
filename comes from the cache name, then `alfred_workflow_bundleid`, then
`maxcare-menu.json`. These are the same paths the Python package uses, so the
two can share a cache. Writes are atomic. The `<cache>.refresh.pid` marker,
together with a file lock, allows at most one refresh launch per minute,
including failed launches.

The "clear cache" item stops a pending refresh. It deletes the menu cache, the
icon cache, Alfred's cache directory for this workflow, and `*.cache` files in
the workflow's data directory. Settings and other workflows are left alone.
Without a bundle ID or explicit workflow paths, it never selects the shared
roots.

## GitHub PRs

`github::PullRequestCache` lists open PRs from `gh pr list`. Use
`search_items("@author terms", "prs")` for searches and `number_items("123")`
to look up a PR number. It serves stale data while it refreshes, and returns
nothing on a miss. It never waits on `gh`. The refresh runs your binary with
`github-refresh …`, so forward arguments to `github::dispatch` first thing in
`main`:

```rust,no_run
fn main() -> we_love_alfred::Result<()> {
    if let Some(refreshed) = we_love_alfred::github::dispatch(std::env::args().skip(1)) {
        return refreshed;
    }
    Ok(())
}
```

## Okta app tiles

`okta::Okta::new(org, client_id).add_items(&mut workflow)` lists the signed-in
user's Okta app tiles. Each tile opens its SSO link. Until the user connects,
the menu shows a connect item that runs `<binary> okta-login`. Handle that
argument by calling `Okta::login()`, which runs the RFC 8628 device flow, then
rebuild. The Okta app must be a public native OIDC app with the device
authorization and refresh token grants and the `okta.users.read.self` scope.
The rotating refresh token is stored in the macOS Keychain. Tiles are
refetched once `apps_ttl` (one day) has passed, and the old tiles stay through
an Okta outage.
