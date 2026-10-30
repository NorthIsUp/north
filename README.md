
## Development checks

The repository uses one uv workspace and root lockfile. Development runs on
Python 3.15; Alfred requires 3.15, while the other distributions retain their
published Python minimums.

```sh
uv sync --all-packages --frozen
hk check
uv run --all-packages --frozen pytest
```

Ruff checks every package, script, test, and example with `ALL` rules and
explicit exceptions for formatting, generated schemas, public APIs, and CLI
behavior. Pyright runs in strict mode; ty treats every rule as an error.
The same hk checks run on commit, push, and in CI. Each distribution includes
`py.typed` so downstream checkers can use its annotations.

See [the Alfred fast-path guide](packages/we-love-alfred/README.md) for cached
Script Filters and background refreshes.
