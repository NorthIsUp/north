# Fast Alfred Script Filters

Use Python 3.15 or newer. Keep the cached entry point separate from the full
builder: subclassing `AlfredWorkflow` loads Pydantic even with lazy imports.

A small entry script can serve cached results without loading Pydantic or HTTPX:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.15"
# dependencies = ["we-love-alfred"]
# ///
import sys
from pathlib import Path

from we_love.alfred.fast import serve

__lazy_modules__ = ("builder",)
from builder import main

if not serve(" ".join(sys.argv[1:]), script=Path(__file__).with_name("builder.py")):
    main()
```

`builder.py` is a regular Python module using the same interpreter and installed
dependencies as the entry script. Its `main()` should build and print the menu.
When launched with `--no-cache`, it must rebuild instead of reading the cache.
The detached refresh uses `sys.executable`, passes arguments directly without a
shell, and sets `PYDANTIC_DISABLE_PLUGINS=__all__` in the child environment.
Only use that setting when the builder does not need Pydantic plugins.

`serve()` returns `False` for a missing, malformed, or unreadable cache. For a
valid cache it filters each query token as a case-insensitive subsequence of the
item's `match` value, falling back to `title`, prints the result, and returns
`True`. It omits Alfred's `cache` field from filtered responses so Alfred cannot
reuse one query's results for another query. It keeps serving stale data while
refreshing; the `.refresh.pid` file throttles attempts to once per minute,
including failed launches. A file lock prevents simultaneous launches.

Caches live under `$XDG_CACHE_HOME/alfred/`, otherwise `~/.cache/alfred/` when
`~/.cache` exists, otherwise `/tmp/alfred/`.
The filename uses `alfred_workflow_bundleid`; outside Alfred the compatibility
fallback is `maxcare-menu.json`. Use `serve(name="my-workflow")` with
`AlfredWorkflow(cache_name="my-workflow")` and
`AlfredWorkflow.read_cache("my-workflow")` to select a name explicitly.
The builder's clear-cache action uses the same cache and refresh marker paths.

Both the fast writer and the builder replace completed cache files atomically.
The fast path validates the menu envelope and item titles with the stdlib;
the full builder validates the complete menu with Pydantic.

Do not add `--refresh-package` to a Script Filter shebang: it reinstalls the
package on every keystroke. Use it once from a terminal after changing a local
package. HTTPX and editor discovery are lazy imports; favicon discovery uses
async HTTPX without `favicon`, Requests, or Beautiful Soup.

`we_love.alfred.github.PullRequestCache.load()` also stays on the cached path:
it serves stale data while refreshing and returns an empty list on a cache miss
or malformed data. All automatic retries use the same warming throttle.
Call `fetch()` explicitly when a caller needs to wait for current PR data.

The clear-cache action also clears Alfred's own cache directory for this workflow
and `.cache` files in its data directory, while preserving settings and other
workflow data. Paths are resolved when building the menu, before `zsh://` dispatch.
Without a bundle ID or explicit workflow paths, shared workflow roots are never
selected for deletion.

## Okta app tiles (opt-in)

`we_love.alfred.okta.OktaAppsMixin` lists the signed-in user's Okta app tiles,
each opening its Okta SSO link. Mix it into the builder's workflow, set
`okta_org` and a client ID, pass `add_okta_items` to `builder()`, and handle
`okta-login` in the script by awaiting `okta_login()` before rebuilding:

```python
class MyWorkflow(OktaAppsMixin, AlfredWorkflow):
    okta_org: str = "https://example.okta.com"
    okta_client_id: str = "0oa..."
```

The Okta app must be a public native OIDC app with the device authorization
and refresh token grants and the `okta.users.read.self` API scope granted.
Until the user connects, the menu shows one connect item that runs the device
flow. The rotating refresh token is stored in the macOS Keychain under
`okta_keychain_service`, and the app list is refetched once `okta_apps_ttl`
(one day) has passed, keeping the old tiles through an Okta outage. Override
`resolve_okta_client_id()` to read the client ID from somewhere else.
