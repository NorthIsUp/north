# we-love-alfred

Alfred Script Filters in async Rust, mostly configured in TOML.

Each keystroke is answered from a cached menu. A detached copy of the binary
rebuilds the menu in the background, so only the very first run waits for the
network.

```rust,no_run
use we_love_alfred::{Item, Menu, Workflow};

#[tokio::main(flavor = "current_thread")]
async fn main() -> we_love_alfred::Result<()> {
    Workflow::load("workflow.toml")
        .await?
        // Extra items for the cached menu, gathered concurrently with the built-in ones.
        .provider(|| async { Ok(vec![Item::url("Status", "https://status.example.com")]) })
        // Live answers for `deploy …`, bypassing the cache.
        .keyword("deploy", |rest| async move { Ok(Menu::default().or_message(&format!("no deploys for {rest:?}"))) })
        .run(std::env::args().skip(1))
        .await
}
```

`run` dispatches one invocation, checking these in order:

1. Internal commands: `--no-cache` (rebuild), `github-refresh`, `okta-login`,
   `self-update` and `self-update-now`.
2. `[[route]]`s, keyword handlers, the update keyword, and PR searches. These
   are answered live.
3. Everything else is filtered from the cached menu. A cache miss builds the
   menu first.

## Config

Every string is a template:
- `{name}` reads `[vars]` or a loop binding.
- `{name.field}` reaches into a table.
- `{env.NAME}` reads the environment.
- `{{` and `}}` are literal braces.

```toml
cache = "my-workflow"          # default: $alfred_workflow_bundleid

[vars]
user = "{env.USER}"
aws = "123456789012.signin.aws.amazon.com"
region = "us-east-1"

# Items: exactly one of url / exec / arg.
[[item]]
title = "Errors"
subtitle = "Sentry"
url = "https://example.sentry.io"
icon = { clearbit = "sentry.io" }

[[item]]
title = "Update"
exec = ["osascript", "-e", 'tell application id "com.runningwithcrayons.Alfred" to search "my update"']
match = "update upgrade"

# `each` repeats an item for every combination of its lists.
[[item]]
title = "{account.name} — {service}"
url = "https://{aws}/start/#/console?account_id={account.id}&destination=https://{region}.console.aws.amazon.com/{service}"
icon = [{ path = "./icons/Arch_*{service}*" }, { path = "./icons/aws.png" }]   # first that resolves
each.account = [{ id = "123456789012", name = "prod" }]
each.service = ["s3", "rds", "iam"]

# Routes answer matching queries live: replace the process...
[[route]]
keywords = { icd10 = "icd10", rx = "rxnorm" }      # first word -> {keyword}, {value}, {rest}
exec = ["/bin/zsh", "--no-rcs", "-c", 'source ./codes.zsh "$1" "$2"', "_", "{value}", "{rest}"]
env = { codes_arg_prefix = "copy:" }

# ...or show items, with regex captures as {0}, {1}, … and named groups.
[[route]]
pattern = '(?i)^mrn-?(\d{10})$'
[[route.item]]
title = "Open MRN-{1}"
url = "https://ehr.example.com/patients/MRN-{1}"

[github]                       # `prs [@author] [terms]`, `#<number|text>`, a bare number
repo = "owner/app"

[update]                       # background checks + `update` live progress view
repo = "owner/my-workflow"
asset = "MyWorkflow.alfredworkflow"

[okta]                         # app tiles; a connect item until signed in
org = "https://example.okta.com"
client_id = "0oa..."

[tailscale]                    # tagged peers that answer, plus subnet routers
tag = "tag:k8s"
routes = true

[sources]                      # one item per path and installed editor
paths = ["~/src/app", "~/src/libs/*"]
```

Icon sources:

| key | resolves to |
| --- | --- |
| `path` | a file; with `*`, the first case-insensitive match |
| `glyph` | an SF Pro glyph rendered with ImageMagick |
| `app` | an app's icon, converted with `sips` |
| `clearbit` | a domain's Clearbit logo |
| `url` | a downloaded image |
| `favicon` | the page's favicon |
| `filetype` | the icon for a UTI |
| `fileicon` | the icon of a file |

URL items default to `favicon`, and exec items to the `terminal` glyph.

## Building blocks

Everything `Workflow` does is available on its own:

| piece | what it does |
| --- | --- |
| `Item::url`, `Item::exec`, `Item::new` | builders for menu items |
| `Menu::build(items, &icons)` | resolves icons concurrently |
| `Menu::filter(query)` | Alfred-style ranking |
| `Cache` | `read`, atomic `write`, throttled background `refresh` |
| `github::PullRequestCache` | open PRs from `gh` |
| `update::Updater` | updates from GitHub releases |
| `okta::Okta` | Okta app tiles |
| `tailscale::Tailscale` | tailnet services |

```rust
use we_love_alfred::{Item, Menu};

let item = |title: &str| Item { title: title.into(), ..Item::default() };
let menu = Menu::from_iter([item("Hello"), item("Other")]);
assert_eq!(menu.filter("hello").items, [item("Hello")]);
```

**Query filtering.** Every query token must be a case-insensitive subsequence
of an item's `match` text, or of its `title` when there's no `match`. Results
rank by title word prefix, then title substring, then `match` substring, then
scattered letters. Filtered output drops Alfred's `cache` field, so Alfred
never reuses one query's results for another.

**Cache location.** Caches live in `$XDG_CACHE_HOME/alfred/`. Without that
variable they go in `~/.cache/alfred/` if `~/.cache` exists, otherwise
`/tmp/alfred/`.

**Background refresh.** A file lock and the `<cache>.refresh.pid` marker allow
at most one rebuild launch per minute, counting failed launches. The
"clear cache" item stops a pending refresh and deletes:
- the menu cache
- the icon cache
- this workflow's Alfred cache directory
- `*.cache` files in this workflow's data directory

It leaves settings and other workflows alone.
