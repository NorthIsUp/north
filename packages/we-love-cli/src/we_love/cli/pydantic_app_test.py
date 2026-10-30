from __future__ import annotations

import argparse
from pathlib import Path
from types import ModuleType
from typing import Annotated, ClassVar, Literal, override

from pydantic import AliasChoices, AliasPath, BeforeValidator, ConfigDict, Field
from we_love.cli.pydantic_app import BaseSettings, CliApp, CliFlag, CliParser, CliPositionalArg, Group, SettingsConfigDict
from we_love.pydantic import cli as legacy


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


def test_legacy_cli_imports_are_the_canonical_objects() -> None:
    assert legacy.CliApp is CliApp
    assert legacy.CliParser is CliParser
    assert legacy.BaseSettings is BaseSettings


def test_model_config_and_class_keywords_share_one_configuration() -> None:
    class Named(CliApp):
        model_config: ClassVar[ConfigDict] = SettingsConfigDict(cli_prog_name="configured")

    class Child(Named, cli_prog_name="child-command"):
        pass

    assert Named.cli_name() == "configured"
    assert Child.cli_name() == "child-command"
    assert Child.model_config.get("cli_prog_name") == "child-command"
    assert Named.model_config.get("cli_prog_name") == "configured"


def test_default_command_names_use_kebab_case() -> None:
    class RunExampleCommand(CliApp):
        pass

    assert RunExampleCommand.cli_name() == "example-command"


def test_parser_reuses_one_group_for_related_fields() -> None:
    group = Group("shared")

    class Grouped(BaseSettings):
        first: Annotated[str, group] = "first"
        second: Annotated[str, group] = "second"

    parser = argparse.ArgumentParser()
    CliParser(app_discovery_packages=(), cli_prog_name="example").build_parser_from_settings(Grouped, parser)
    assert parser.format_help().count("shared:") == 1


def test_sync_and_async_commands_have_the_same_execution_contract() -> None:
    called: list[str] = []

    class SyncCommand(CliApp):
        @override
        def cli_cmd(self) -> None:
            called.append("sync")

    class AsyncCommand(CliApp):
        @override
        async def cli_cmd(self) -> None:
            called.append("async")

    SyncCommand(pydantic_detailed_output=False).run_cli_cmd()
    AsyncCommand(pydantic_detailed_output=False).run_cli_cmd()
    assert called == ["sync", "async"]


def test_discovery_skips_abstract_command_classes() -> None:
    class Incomplete(CliApp):
        pass

    class RunComplete(CliApp):
        @override
        def cli_cmd(self) -> None:
            pass

    module = ModuleType("commands")
    module.__dict__.update(Incomplete=Incomplete, RunComplete=RunComplete)
    assert CliApp.from_module(module) == [RunComplete]


def test_parser_preserves_union_variants_and_field_validators() -> None:
    def hexadecimal(value: object) -> object:
        return int(value, 16) if isinstance(value, str) else value

    class Values(BaseSettings):
        number: int | float
        decoded: Annotated[int, BeforeValidator(hexadecimal)]

    parser = argparse.ArgumentParser()
    CliParser(app_discovery_packages=(), cli_prog_name="example").build_parser_from_settings(Values, parser)
    result = Values.model_validate(vars(parser.parse_args(["--number", "1.5", "--decoded", "ff"])))
    assert result.number == 1.5
    assert result.decoded == 255


def test_positional_aliases_use_one_destination() -> None:
    class Aliased(BaseSettings):
        value: CliPositionalArg[str] = Field(validation_alias=AliasChoices("PrimaryName", "SecondaryName"))

    parser = argparse.ArgumentParser()
    CliParser(app_discovery_packages=(), cli_prog_name="example").build_parser_from_settings(Aliased, parser)
    result = Aliased.model_validate(vars(parser.parse_args(["example"])))
    assert result.value == "example"


def test_parser_aliases_share_canonical_field_destinations() -> None:
    class Aliased(BaseSettings):
        preferred: str = Field(alias="legacy", validation_alias=AliasChoices("current", "alternate"))
        nested: str = Field(validation_alias=AliasPath("payload", "value"))

    parser = argparse.ArgumentParser()
    CliParser(app_discovery_packages=(), cli_prog_name="example").build_parser_from_settings(Aliased, parser)
    arguments = vars(parser.parse_args(["--legacy", "one", "--payload", "two"]))
    assert arguments == {"preferred": "one", "nested": "two"}
    assert Aliased.model_validate(arguments).nested == "two"
