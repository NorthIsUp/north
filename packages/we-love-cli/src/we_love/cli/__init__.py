"""Pydantic command-line applications and typed settings.

>>> class Options(BaseSettings, cli_prog_name="demo"):
...     count: int = 1
>>> Options(count=2).count
2
>>> from we_love.cli.converters import IntConverter, FloatConverter
>>> IntConverter().decode("-42")
-42
>>> FloatConverter().decode("1.5e2")
150.0
"""

from .arguments import (
    BaseSettings,
    CliAppend,
    CliCount,
    CliExplicitFlag,
    CliFlag,
    CliImplicitFlag,
    CliPositionalArg,
    CliSubCommand,
    CliSuppress,
    CliUnknownArgs,
    Group,
    SettingsConfigDict,
)
from .pydantic_app import CliApp, CliParser

__all__ = [
    "BaseSettings",
    "CliApp",
    "CliAppend",
    "CliCount",
    "CliExplicitFlag",
    "CliFlag",
    "CliImplicitFlag",
    "CliParser",
    "CliPositionalArg",
    "CliSubCommand",
    "CliSuppress",
    "CliUnknownArgs",
    "Group",
    "SettingsConfigDict",
]
