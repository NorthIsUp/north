from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import typing
from abc import abstractmethod
from argparse import ArgumentParser
from collections.abc import Coroutine, Sequence
from functools import cached_property
from inspect import getmembers, isabstract
from typing import Annotated, ClassVar, Self, get_args, override

import argcomplete
from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError
from rich.pretty import pprint
from we_love.registry.autodiscover import autodiscover_iter

from .arguments import (
    CLI_SUPPRESS,
    ArgumentContainer,
    ArgumentOptions,
    BaseSettings,
    CliAppend,
    CliCount,
    CliExplicitFlag,
    CliFlag,
    CliHelpFormatter,
    CliImplicitFlag,
    CliMetadata,
    CliPositionalArg,
    CliStoreConst,
    CliSubCommand,
    CliSuppress,
    CliUnknownArgs,
    CliVerbosity,
    Group,
    SettingsConfigDict,
    kebab_case,
)
from .debugging import DEBUG_GROUP, DebugSettings
from .settings import CacheSettings, GlobalSettings, LoggingSettings, settings

if typing.TYPE_CHECKING:
    from types import ModuleType


logger = logging.getLogger(__name__)


class CliParser(BaseModel, arbitrary_types_allowed=True):
    """
    Entrypoint for a cli app.

    This class is used to build the entrypoint and does autodiscovery of commands.

    To add a new command create a new class in the appropriate 'commands' package.

    Some rules:

    The commands MUST:
    - be a subclass of 'CliApp'
    - implement a 'cli_cmd' method
    - be named 'Run<CommandName>'
    - be in a module named 'run_<command_name>'
    - minimize top level imports (keep the cli fast!)
    - NOT import slow modules e.g. litellm or any coding_agent modules that do autodiscovery

    commands that start or end with 'Base' will be ignored
    """

    app_discovery_packages: str | Sequence[str]

    parser: ArgumentParser = Field(
        default_factory=lambda: ArgumentParser(
            argument_default=argparse.SUPPRESS,
            formatter_class=CliHelpFormatter,
        ),
        description="the root parser for the cli app",
    )

    cli_prog_name: str
    cli_env_prefix: str = ""
    cli_env_separator: str = "__"
    cli_dest_separator: str = "__"
    cli_command_dest: str = "commands"

    cli_selected_command: str = Field(default="", description="the name of the selected sub command")
    cli_commands: dict[str, type[CliApp]] = Field(default_factory=dict, description="The cli app classes that are discovered")
    cli_parsers: dict[str, ArgumentParser] = Field(
        default_factory=dict[str, ArgumentParser], description="the argparsers for the cli app classes"
    )
    cli_app_cls: type[CliApp] | None = None
    cli_app: CliApp | None = None
    cli_args: dict[str, object] = Field(default_factory=dict[str, object])

    @cached_property
    def _env_prefix(self) -> str:
        """some-name -> SOME_NAME"""
        return self.cli_env_prefix.upper().replace("-", "_")

    @override
    def model_post_init(self, context: object) -> None:
        super().model_post_init(context)

        if isinstance(self.app_discovery_packages, str):
            self.app_discovery_packages = [self.app_discovery_packages]

        self.cli_env_prefix = self.cli_env_prefix or self.cli_prog_name.replace("-", "_")

    def run(self) -> None:
        """
        run the cli app

        this is the main entrypoint for the cli app
        """
        try:
            self.discover_commands()
            self.build_parsers()
            self.parse_args_to_settings()
            self.validate_args_to_model()
            self.run_selected_command()
        except ValidationError as e:
            zero = sys.argv[0].split("/")[-1]
            print(f"{zero}: {e}")

    def discover_commands(self) -> None:
        """
        discover commands in the autodiscovery packages and populate the
        cli_commands dict
        """
        self.cli_commands = {
            command.cli_name(): command
            for command in sorted(
                autodiscover_iter(self.app_discovery_packages, key=CliApp.from_module), key=lambda candidate: candidate.cli_name()
            )
            if command is not CliApp
        }

    def build_parsers(self) -> None:
        """
        build the argument parsers for the commands
        """

        subparsers = self.parser.add_subparsers(dest=self.cli_command_dest, help="Available subcommands")

        for name, command in self.cli_commands.items():
            dest = self._join_dest(self.cli_env_prefix, name)
            self.cli_parsers[name] = subparsers.add_parser(
                command.cli_name(),
                help=command.__doc__,
                description=command.__doc__,
                epilog=f"Note: Options can also be set via environment variables via: {self._dest_to_env_var(dest)}{self.cli_env_separator}<OPTION_NAME>",
                argument_default=argparse.SUPPRESS,
                formatter_class=CliHelpFormatter,
            )
            self.build_parser_from_settings(
                command,
                self.cli_parsers[name],
                dest,
            )

        argcomplete.autocomplete(self.parser)

    def parse_args_to_settings(self) -> None:
        """
        parse the arguments and populate the cli_command_name and cli_args
        """
        args = self.parser.parse_args()
        self.cli_selected_command, self.cli_args = self._ns_to_command_dict(args)

        if not self.cli_selected_command:
            self.parser.error("no command specified")

        if self.cli_selected_command not in self.cli_commands:
            raise ValueError(f"command '{self.cli_selected_command}' not found")

        self.cli_app_cls = self.cli_commands[self.cli_selected_command]

    def validate_args_to_model(self) -> None:
        """
        Use the parsed args to populate the settings class and run model_validation
        """
        if self.cli_app_cls is None:
            raise ValueError("cli_app_cls is not set")

        if self.cli_args.get("inspect_settings"):
            # allow for the inspection of the parsed settings
            print(f"parsed settigns for {self.cli_selected_command}")
            pprint(self.cli_args)

        try:
            self.cli_app = self.cli_app_cls.model_validate(self.cli_args, by_name=True)
        except ValidationError as e:
            parser = self.cli_parsers.get(self.cli_selected_command, self.parser)
            parser.print_help()
            print("\n\n" + str(e))

            if not self.cli_args.get("inspect_settings"):
                # only print the args if not already inspecting
                pprint(self.cli_args)

            parser.exit(2)

    def run_selected_command(self) -> None:
        """
        run the cli_cmd method of the selected command
        """
        if self.cli_app is None:
            raise ValueError("cli_app is not set")

        if self.cli_app.inspect_settings:
            pprint(self.cli_app)
            sys.exit(1)

        self.cli_app.run_cli_cmd()

    def build_parser_from_settings(
        self,
        settings_cls: type[BaseSettings],
        parser: ArgumentParser,
        dest: str | None = None,
    ) -> None:
        """
        build the argument parser for a given settings class
        """
        parser.argument_default = argparse.SUPPRESS
        subparsers = (
            parser.add_subparsers(dest="command")
            if any(CliMetadata.SUBCOMMAND in f.metadata for f in settings_cls.model_fields.values())
            else None
        )
        groups: dict[str, ArgumentContainer] = {}
        for name, field in settings_cls.model_fields.items():
            if CLI_SUPPRESS in field.metadata:
                continue
            destination = self._join_dest(dest, name) if (dest is not None and dest) else name
            if CliMetadata.SUBCOMMAND in field.metadata:
                command_cls = self._get_command_cls(settings_cls, name)
                assert subparsers is not None
                self.build_parser_from_settings(
                    command_cls, subparsers.add_parser(kebab_case(name), description=command_cls.__doc__), destination
                )
                continue
            options = ArgumentOptions.from_field(name, field, destination)
            envvar = self._dest_to_env_var(destination)
            if envvar in os.environ:
                options.default = os.environ[envvar]
            if options.group is None:
                options.add_to(parser)
            else:
                if options.group not in groups:
                    groups[options.group] = parser.add_argument_group(options.group)
                options.add_to(groups[options.group])

    def _join_dest(self, dest: str, name: str) -> str:
        """dest.foo, bar -> dest.foo.bar"""
        return self.cli_dest_separator.join((dest, name))

    def _dest_to_env_var(self, dest: str) -> str:
        """SOME_NAME.dest.name -> SOME_NAME__DEST__NAME"""
        return dest.replace(self.cli_dest_separator, self.cli_env_separator).replace("-", "_").upper()

    def _ns_to_command_dict(self, ns: argparse.Namespace) -> tuple[str, dict[str, object]]:
        values = RootModel[dict[str, object]].model_validate(vars(ns)).root
        command_value = values.get(self.cli_command_dest, "")
        command = command_value if isinstance(command_value, str) else ""
        result: dict[str, object] = {}
        prefix = self._join_dest(self.cli_env_prefix, command) + self.cli_dest_separator
        for key, value in values.items():
            if key == self.cli_command_dest or value is None:
                continue
            relative_key = key.removeprefix(prefix)
            destination = result
            *parents, leaf = relative_key.split(self.cli_env_separator)
            for parent in parents:
                child: dict[str, object] = {}
                existing = destination.get(parent)
                if isinstance(existing, dict):
                    child = RootModel[dict[str, object]].model_validate(existing).root
                destination[parent] = child
                destination = child
            destination[leaf] = value
        return command, result

    @classmethod
    def _get_command_cls(cls, settings_cls: type[BaseSettings], command: str) -> type[BaseSettings]:
        """get a subcommand class from the settings class"""
        if command not in settings_cls.model_fields:
            raise ValueError(f"command '{command}' not found")

        annotation = settings_cls.model_fields[command].annotation
        candidates: tuple[object, ...] = get_args(annotation) or (annotation,)
        for candidate in candidates:
            if isinstance(candidate, type) and issubclass(candidate, BaseSettings):
                return candidate
        raise ValueError(f"command '{command}' is not a subcommand")


class CliApp(GlobalSettings):
    """
    This class is a wrapper around the AppConfig class that adds the ability to
    parse CLI arguments and environment variables. All cli classes should be a subclass of this class.
    """

    model_config: ClassVar[ConfigDict] = SettingsConfigDict(
        cli_ignore_unknown_args=False,
        cli_kebab_case=True,
    )

    inspect_settings: Annotated[CliFlag[bool], DEBUG_GROUP] = Field(
        default=False,
        description="Print the parsed settings to the console and exit",
    )

    def run_cli_cmd(self) -> None:
        """run the cli cmd entrypoint, if it is a coroutine, run it async"""
        result = self.cli_cmd()
        if result is not None:
            asyncio.run(result)

    @abstractmethod
    def cli_cmd(self) -> Coroutine[object, object, None] | None:
        raise NotImplementedError("Subclasses must implement cli_cmd")

    @classmethod
    def cli_name(cls) -> str:
        configured_name: object = cls.model_config.get("cli_prog_name")
        if isinstance(configured_name, str):
            return configured_name
        if configured_name is not None:
            raise TypeError("cli_prog_name must be a string")
        return kebab_case(cls.__name__).removeprefix("run-") if cls.model_config.get("cli_kebab_case") is True else cls.__name__

    @classmethod
    def from_module(cls, module: ModuleType) -> Sequence[type[CliApp]]:
        return [
            candidate
            for _, candidate in getmembers(module)
            if isinstance(candidate, type) and issubclass(candidate, cls) and not isabstract(candidate)
        ]

    @classmethod
    def current_settings(cls) -> Self:
        """get the settings object for the given class"""
        return settings.get().cast_to(cls)


__all__ = [
    "CLI_SUPPRESS",
    "ArgumentOptions",
    "BaseSettings",
    "CacheSettings",
    "CliApp",
    "CliAppend",
    "CliCount",
    "CliExplicitFlag",
    "CliFlag",
    "CliHelpFormatter",
    "CliImplicitFlag",
    "CliParser",
    "CliPositionalArg",
    "CliStoreConst",
    "CliSubCommand",
    "CliSuppress",
    "CliUnknownArgs",
    "CliVerbosity",
    "DebugSettings",
    "GlobalSettings",
    "Group",
    "LoggingSettings",
    "SettingsConfigDict",
    "kebab_case",
    "settings",
]
