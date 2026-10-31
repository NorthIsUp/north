# we-love

Typed Python packages with executable usage examples.

| Package | Python |
| --- | --- |
| [we-love-alfred](packages/we-love-alfred/README.md) | 3.15+ |
| [we-love-avatars](packages/we-love-avatars/README.md) | 3.13+ |
| [we-love-cli](packages/we-love-cli/README.md) | 3.13+ |
| [we-love-funcy](packages/we-love-funcy/README.md) | 3.13+ |
| [we-love-fzf](packages/we-love-fzf/README.md) | 3.13+ |
| [we-love-matchbox](packages/we-love-matchbox/README.md) | 3.13+ |
| [we-love-pydantic](packages/we-love-pydantic/README.md) | 3.13+ |
| [we-love-pyproject](packages/we-love-pyproject/README.md) | 3.13+ |
| [we-love-registry](packages/we-love-registry/README.md) | 3.13+ |
| [we-love-string](packages/we-love-string/README.md) | 3.13+ |
| [we-love-typeid](packages/we-love-typeid/README.md) | 3.13+ |

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

## Compatibility notes

The canonical CLI implementation lives in `we_love.cli.pydantic_app`.
`we_love.pydantic.cli` retains the same public imports. CLI-specific configuration
continues to live in `model_config = SettingsConfigDict(...)`; class keywords
update that same configuration without changing parent classes. Install
`we-love-cli[debug]` only when using the debugpy integration.

`Registry` is a Pydantic model again, including nested validation and serialization.
Its normal model iteration follows Pydantic's field-pair contract. Iterate
registered objects with `registry.entries.values()` or `registry.all()`.

GitHub menu cache reads never execute `gh`. A missing or malformed cache returns
an empty result and schedules a throttled background refresh; use `fetch()` for
an explicit blocking refresh. The FZF picker retains its pure-Python `pzp`
fallback when the executable is unavailable.

String 0.3.0 unifies alias word boundaries. TypeId 0.3.0 validates canonical suffixes at construction and preserves UUID version/variant bits; short placeholder suffixes are no longer accepted. See each package README for its contract and migration notes.
