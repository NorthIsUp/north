# we-love-cli

Pydantic command-line applications and typed settings.

Install with `uv add we-love-cli`. Requires Python 3.13+.

## Executable example

```pycon
>>> class Options(BaseSettings, cli_prog_name="demo"):
...     count: int = 1
>>> Options(count=2).count
2
>>> from we_love.cli.converters import IntConverter, FloatConverter
>>> IntConverter().decode("-42")
-42
>>> FloatConverter().decode("1.5e2")
150.0
```

Subclass `CliApp` with typed fields and a `cli_cmd` implementation; `run_cli_cmd()` parses and executes it. CLI annotations such as CliFlag, CliPositionalArg and CliSubCommand shape arguments. Sync and async commands are supported. Configuration lives in model_config or class keywords. Numeric converters accept signed/scientific notation; failed conversions raise ConversionError with the input value.

Examples run in ordinary pytest discovery through `examples_test.py`. The distribution ships a `py.typed` marker.
