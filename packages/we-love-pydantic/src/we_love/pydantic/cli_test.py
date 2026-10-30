from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

from pydantic import Field
from we_love.pydantic.cli import BaseSettings, CliFlag, CliParser, CliPositionalArg


class Options(BaseSettings):
    count: int = 1
    enabled: CliFlag[bool] = False
    mode: Literal["fast", "full"] = "fast"
    path: Path = Path()
    names: list[str] = Field(default_factory=list[str])


def test_parser_converts_literals_paths_and_lists(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser()
    cli = CliParser(app_discovery_packages=(), cli_prog_name="example")
    cli.build_parser_from_settings(Options, parser)
    result = parser.parse_args([
        "--count",
        "2",
        "--enabled",
        "--mode",
        "full",
        "--path",
        str(tmp_path),
        "--names",
        "first",
        "--names",
        "second",
    ])
    options = Options.model_validate(vars(result))
    assert options.count == 2
    assert options.enabled
    assert options.mode == "full"
    assert options.path == tmp_path
    assert options.names == ["first", "second"]


def test_parser_supports_positional_arguments() -> None:
    class Positional(BaseSettings):
        name: CliPositionalArg[str]

    parser = argparse.ArgumentParser()
    cli = CliParser(app_discovery_packages=(), cli_prog_name="example")
    cli.build_parser_from_settings(Positional, parser)
    assert parser.parse_args(["example"]).name == "example"
