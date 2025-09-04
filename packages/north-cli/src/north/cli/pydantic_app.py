from __future__ import annotations

import argparse
import asyncio
import logging
import os
import pathlib
import sys
import types
import typing
from argparse import ArgumentParser, _ArgumentGroup
from asyncio import iscoroutinefunction
from collections.abc import Collection, Sequence
from datetime import timedelta
from functools import cached_property
from pathlib import Path
from typing import (
    Annotated,
    Any,
    ClassVar,
    Self,
    TypeVar,
    cast,
    get_args,
    get_origin,
)

import argcomplete
from coding_agent.lib.autodiscovery import autodiscover_iter
from coding_agent.lib.pydantic.models import Singleton
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from rich import console
from rich.panel import Panel
from rich.pretty import pprint
from stringcase import spinalcase

logger = logging.getLogger(__name__)

_DEFAULT_VERBOSITY = 2


# Supports the inherited settings pattern that we are using in the coding agent
class _GlobalSettingsStore(metaclass=Singleton):
    """Thread-safe singleton for storing global settings"""

    def set(self, settings: GlobalSettings) -> None:
        self._settings = settings

    def get(self) -> GlobalSettings:
        if self._settings is None:
            raise LookupError(
                "Global settings not initialized. Call settings.set() first."
            )
        return self._settings

    def clear(self) -> None:
        self._settings = None


# Typing for cli flags
# These are annotations for the cli parser, they are used to tell the cli parser
# what kind of argument the field is, flag, count, etc.
#
# the _CliBlahBlah types are for CliParser.build_parser_from_settings, they
# allow the match statement to easily find annotations markers
T = TypeVar("T")


def _t(name: str) -> type:
    return type(name, (), {})


Group = type("Group", (str,), {})

# for subcommands
CliSubCommand = Annotated[T | None, _CliSubCommand := _t("_CliSubCommand")]

# for required positional args
CliPositionalArg = Annotated[T, _CliPositionalArg := _t("_CliPositionalArg")]

# for optional implicit flags, --flag --no-flag true/false flags
_CliBoolFlag = TypeVar("_CliBoolFlag", bound=bool)
CliImplicitFlag = Annotated[_CliBoolFlag, _CliImplicitFlag := _t("_CliImplicitFlag")]

# for optional flags, --flag true/None flags flags
CliFlag = Annotated[_CliBoolFlag, _CliFlag := _t("_CliFlag")]

# for optional explicit flags --flag=true (flag must have a value)
CliExplicitFlag = Annotated[_CliBoolFlag, _CliExplicitFlag := _t("_CliExplicitFlag")]

# for not showing in help
CLI_SUPPRESS = argparse.SUPPRESS
CliSuppress = Annotated[T, CLI_SUPPRESS]

# for unknown args
CliUnknownArgs = Annotated[
    list[str], Field(default=[]), _CliUnknownArgs := _t("_CliUnknownArgs")
]

# for counting flags
_Int = TypeVar("_Int", bound=int)
CliCount = Annotated[_Int, Field(default=0), _CliCountingFlag := _t("_CliCountingFlag")]

# for store-const
_StoreConst = TypeVar("_StoreConst", bound=Any)
CliStoreConst = Annotated[_StoreConst, _CliStoreConst := _t("_CliStoreConst")]

# for appending to a list
CliAppend = Annotated[
    list[str], Field(default_factory=list), _CliAppend := _t("_CliAppend")
]


# for marking the verbosity arg, generally this doesn't need to be used by users
_logging_group = Group("logging")
_default_verbosity = (
    object()
)  # sentinel value for the default verbosity. 2 if unset, 0 if set
CliVerbosity = Annotated[
    int | None,
    Field(default=None, description="The verbosity of the logging"),
    _CliVerbosity := type("_CliVerbosity", (), {}),
    _logging_group,
]


class SettingsConfigDict(ConfigDict, total=False):
    cli_prog_name: str
    """the name of the cli program, defaults to the class name"""

    cli_ignore_unknown_args: bool
    """whether to ignore unknown arguments"""

    cli_kebab_case: bool
    """whether to use kebab case for the cli program and app names"""

    cli_group_name: str
    """the name of the cli group, defaults to the class name"""


class CliHelpFormatter(argparse.HelpFormatter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # widen the help position to make the help more readable
        kwargs["max_help_position"] = 48
        super().__init__(*args, **kwargs)

    def _get_default_metavar_for_optional(self, action: argparse.Action) -> str:
        # trim the prefix from the dest for brevity
        return action.dest.split("__")[-1].upper()

    def _get_default_metavar_for_positional(self, action: argparse.Action) -> str:
        # trim the prefix from the dest for brevity
        return action.dest.split("__")[-1]


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

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict()

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

    cli_selected_command: str = Field(
        default="", description="the name of the selected sub command"
    )
    cli_commands: dict[str, type[CliApp]] = Field(
        default_factory=dict, description="The cli app classes that are discovered"
    )
    cli_parsers: dict[str, ArgumentParser] = Field(
        default_factory=dict, description="the argparsers for the cli app classes"
    )
    cli_app_cls: type[CliApp] | None = None
    cli_app: CliApp | None = None
    cli_args: dict[str, Any] = Field(default_factory=dict)

    @cached_property
    def _env_prefix(self) -> str:
        """some-name -> SOME_NAME"""
        return self.cli_env_prefix.upper().replace("-", "_")

    def model_post_init(self, context: Any) -> None:
        super().model_post_init(context)

        if isinstance(self.app_discovery_packages, str):
            self.app_discovery_packages = [self.app_discovery_packages]

        self.cli_env_prefix = self.cli_env_prefix or self.cli_prog_name.replace(
            "-", "_"
        )

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
                autodiscover_iter(self.app_discovery_packages, key=CliApp),
                key=lambda x: x.cli_name(),
            )
            if command is not CliApp
        }

    def build_parsers(self) -> None:
        """
        build the argument parsers for the commands
        """

        subparsers = self.parser.add_subparsers(
            dest=self.cli_command_dest, help="Available subcommands"
        )

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
            self.cli_app = self.cli_app_cls.model_validate(self.cli_args)
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

        self.cli_app._run_cli_cmd()

    def build_parser_from_settings(
        self,
        settings_cls: type[BaseSettings],
        parser: ArgumentParser,
        dest: str | None = None,
    ) -> None:
        """
        build the argument parser for a given settings class
        """
        import builtins as b

        parser.argument_default = argparse.SUPPRESS

        # if there are nested settings, we need to add a subparser for each nested settings
        subparsers: argparse._SubParsersAction | None = None
        groups: dict[Group | None, _ArgumentGroup | ArgumentParser] = {}

        for name, field in settings_cls.model_fields.items():
            # for each field in the settings class

            # get the names for the argument (both dash and undash versions)
            dash_names, undash_names = self._get_arg_names(name, field)
            names = dash_names  # by default we use the dash names

            # get the alias names for the argument
            (alias, *_rest), _ = self._get_alias_names(name, field)

            # get the destination for the argument
            destination = self._join_dest(dest, alias) if dest else alias

            # kwargs for the argument
            kwargs: dict[str, Any] = {
                "dest": destination,
                "help": field.description,
                # "default": Don't set this, model_validate will do it
            }

            # the field must have an annotation
            assert field.annotation is not None, f"field {name} has no annotation"

            # if the field has a group, add it to the groups dict
            found_groups = {g for g in field.metadata if isinstance(g, Group)}
            if len(found_groups) > 1:
                raise ValueError(f"field {name} has multiple groups: {found_groups}")

            if group := next(iter(found_groups), None):
                groups.setdefault(group, parser.add_argument_group(str(group)))

            # first handle the annotations that are on the field
            if field.metadata:
                # handle subcommands
                if _CliSubCommand in field.metadata:
                    subparsers = subparsers or parser.add_subparsers(dest="command")

                    match field.annotation:
                        case object(
                            __origin__=typing.Union, __args__=(subcommand_cls, *_)
                        ):
                            # field is a subcommand
                            self.build_parser_from_settings(
                                subcommand_cls,
                                subparsers.add_parser(
                                    spinalcase(name),
                                    description=subcommand_cls.__doc__,
                                    epilog="and so it goes",
                                ),
                                dest=destination,
                            )
                        case _:
                            raise NotImplementedError(
                                f"field {name} has an unknown annotation: {field.annotation}"
                            )

                # suppress fields, do not add them to the parser
                if CLI_SUPPRESS in field.metadata:
                    # skip suppresed fields
                    continue

                # handle positional args
                if _CliPositionalArg in field.metadata:
                    # add required positional args
                    names = undash_names
                    kwargs["type"] = field.annotation

                # handle counting flags
                if _CliCountingFlag in field.metadata:
                    kwargs["action"] = "count"

                # handle implicit flags
                if _CliImplicitFlag in field.metadata:
                    kwargs["action"] = argparse.BooleanOptionalAction

                # handle flags
                if _CliFlag in field.metadata:
                    kwargs["action"] = "store_true"

                # handle appending to a list
                if _CliAppend in field.metadata:
                    kwargs["action"] = "append"

                # handle verbosity flags
                if _CliVerbosity in field.metadata:
                    if len(dash_names) == 1:
                        names = f"-{dash_names[0][2]}", *names

                    kwargs["action"] = "count"

            if "action" not in kwargs:
                annotation = field.annotation

                match annotation:
                    # unwrap optional types before we match on the annotation
                    case (
                        object(
                            __origin__=typing.Union,
                            __args__=(annotation_cls, types.NoneType),
                        )
                        | types.UnionType(__args__=(annotation_cls, types.NoneType))
                    ):
                        annotation = get_args(annotation)[0]

                        # unwrap Annotated types before we match on the annotation
                        if get_origin(annotation) == typing.Annotated:
                            args = [
                                _
                                for _ in get_args(annotation)
                                if not isinstance(_, Group)
                            ]
                            if not args:
                                raise ValueError(f"field {name} has no annotation")
                            annotation = args[0]

                    case _:
                        pass

                match annotation:
                    # handle simple types
                    case b.str | b.int | b.float | b.bool:
                        kwargs["type"] = annotation

                    # handle sequences for list[str|whatever] or tuple[str, ...]
                    case types.GenericAlias(
                        __origin__=type() as origin,
                        __args__=(annotation_cls,)
                        | (annotation_cls, types.EllipsisType()),
                    ) if issubclass(origin, Collection):
                        kwargs["type"] = annotation_cls
                        kwargs["action"] = "append"

                    # handle tuple types for tuple[str, whatever]
                    case types.GenericAlias(__origin__=b.tuple, __args__=args):
                        raise NotImplementedError(
                            f"mixed tuple types are not supported yet, got {args}"
                        )

                    # handle unhandled types, this will have a breakpoint to figure it out
                    case types.GenericAlias() as g:
                        raise NotImplementedError(
                            f"unknown generic alias for '{name}': {g}"
                        )

                    # handle Optional types
                    case (
                        object(
                            __origin__=typing.Union,
                            __args__=(annotation_cls, types.NoneType),
                        )
                        | types.UnionType(__args__=(annotation_cls, types.NoneType))
                    ):
                        kwargs["type"] = annotation_cls

                    # handle pathlib.Path types
                    case pathlib.Path:
                        kwargs["type"] = lambda s: Path(s).expanduser().resolve()

                    # handle Literal types
                    case typing._LiteralGenericAlias() as lit:  # type: ignore[name-defined]
                        lit = get_args(lit)
                        kwargs["type"] = type(lit[0])
                        kwargs["choices"] = lit

                    # handle unhandled types
                    case _:
                        raise NotImplementedError(
                            f"unknown annotation alias for '{name}': {field.annotation} (parsed to {annotation})"
                        )

            # set the default from the environment if it exists
            if (envvar := self._dest_to_env_var(destination)) in os.environ:
                kwargs.setdefault("default", os.environ[envvar])

            groups.get(group, parser).add_argument(*names, **kwargs)

    def _join_dest(self, dest: str, name: str) -> str:
        """dest.foo, bar -> dest.foo.bar"""
        return self.cli_dest_separator.join((dest, name))

    def _dest_to_env_var(self, dest: str) -> str:
        """SOME_NAME.dest.name -> SOME_NAME__DEST__NAME"""
        return (
            dest.replace(self.cli_dest_separator, self.cli_env_separator)
            .replace("-", "_")
            .upper()
        )

    def _ns_to_command_dict(
        self, ns: argparse.Namespace, command_only: bool = False
    ) -> tuple[str, dict[str, Any]]:
        """
        convert an argparse.Namespace to a nested dict by . separated keys

        command_only will return the dict specified by the "command" key
        """
        result = {}

        for key_path, v in vars(ns).items():
            d = result
            *path, leaf = key_path.split(self.cli_env_separator)

            for kp in path:
                d = d.setdefault(kp, {})

            d[leaf] = v

        # remove the env prefix layer from the config result if it exists
        if self._env_prefix.lower() in result:
            result.update(result.pop(self._env_prefix.lower()))

        if command := result.get(self.cli_command_dest, ""):
            # find the selected command in the result
            result = result.get(command, {})

        # filter out any None values and return the command and the result
        result = {k: v for k, v in result.items() if v is not None}
        return command, result

    @staticmethod
    def _get_alias_names(
        field_name: str,
        field_info: Any,
        alias_path_args: dict[str, str] | None = None,
        case_sensitive: bool = True,
    ) -> tuple[tuple[str, ...], bool]:
        """Get alias names for a field, handling alias paths and case sensitivity."""
        from pydantic import AliasPath

        alias_path_args = alias_path_args or {}

        alias_names: list[str] = []
        is_alias_path_only: bool = True
        if not any((field_info.alias, field_info.validation_alias)):
            alias_names += [field_name]
            is_alias_path_only = False
        else:
            new_alias_paths: list[AliasPath] = []
            for alias in (field_info.alias, field_info.validation_alias):
                if alias is None:
                    continue
                if isinstance(alias, str):
                    alias_names.append(alias)
                    is_alias_path_only = False
                elif isinstance(alias, AliasChoices):
                    for name in alias.choices:
                        if isinstance(name, str):
                            alias_names.append(name)
                            is_alias_path_only = False
                        else:
                            new_alias_paths.append(name)
                else:
                    new_alias_paths.append(alias)
            for alias_path in new_alias_paths:
                name = cast(str, alias_path.path[0])
                name = name.lower() if not case_sensitive else name
                alias_path_args[name] = "dict" if len(alias_path.path) > 2 else "list"
                if not alias_names and is_alias_path_only:
                    alias_names.append(name)
        if not case_sensitive:
            alias_names = [alias_name.lower() for alias_name in alias_names]
        return tuple(dict.fromkeys(alias_names)), is_alias_path_only

    @classmethod
    def _get_arg_names(
        cls, field_name: str, field_info: Any
    ) -> tuple[Sequence[str], Sequence[str]]:
        """get the dashed and undashed version of the argument names"""
        names, _is_alias_path_only = cls._get_alias_names(field_name, field_info)
        names = [spinalcase(name) for name in names]

        return [f"--{name}" if len(name) > 1 else f"-{name}" for name in names], names

    @classmethod
    def _get_command_cls(
        cls, settings_cls: type[BaseSettings], command: str
    ) -> type[BaseSettings]:
        """get a subcommand class from the settings class"""
        if command not in settings_cls.model_fields:
            raise ValueError(f"command '{command}' not found")

        match settings_cls.model_fields[command].annotation:
            case object(__origin__=typing.Union, __args__=(command_cls, *_)):
                return command_cls
            case _:
                raise ValueError(f"command '{command}' is not a subcommand")


class BaseSettings(BaseModel):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        frozen=True,
        validate_assignment=True,
        validate_default=True,
    )

    def __init_subclass__(
        cls,
        cli_group_name: str | None = None,
        cli_ignore_unknown_args: bool | None = None,
        cli_kebab_case: bool | None = None,
        cli_prog_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        update the model config with the given kwargs
        """

        if cli_group_name is not None:
            cls.model_config.update(cli_group_name=cli_group_name)
        if cli_ignore_unknown_args is not None:
            cls.model_config.update(cli_ignore_unknown_args=cli_ignore_unknown_args)
        if cli_kebab_case is not None:
            cls.model_config.update(cli_kebab_case=cli_kebab_case)
        if cli_prog_name is not None:
            cls.model_config.update(cli_prog_name=cli_prog_name)

        super().__init_subclass__(**kwargs)


_debug_group = Group("debug")


class DebugSettings(BaseSettings):
    pdb: Annotated[CliImplicitFlag[bool], _debug_group] = Field(
        default=False,
        description="Enable Python debugger post-mortem on exceptions",
    )

    debugpy: Annotated[CliImplicitFlag[bool], _debug_group] = Field(
        default=False,
        description="Enable vscode debugger on exceptions",
    )
    debugpy_port: Annotated[int, _debug_group] = Field(
        default=5678,
        description="The port to listen for remote debugger connections",
    )

    @classmethod
    def enable_postmortem(cls) -> None:
        """Enable post-mortem debugging on exceptions"""

        def _enter_post_mortem(type: Any, value: Any, traceback: Any) -> None:
            from pdb import post_mortem

            post_mortem(traceback)

        sys.excepthook = _enter_post_mortem

    def enable_debugpy(self) -> None:
        """Enable vscode debugger on exceptions"""
        import debugpy

        debugpy.listen(("0.0.0.0", self.debugpy_port))

        console.Console().print(
            Panel(f"Waiting for vscode debugger to attach on port {self.debugpy_port}")
        )

        logger.info("Waiting for vscode debugger to attach")
        debugpy.wait_for_client()
        logger.info("vscode debugger attached")

    @model_validator(mode="after")
    def validate_pdb(self) -> Self:
        if self.pdb:
            self.enable_postmortem()
        return self

    @model_validator(mode="after")
    def validate_vscode_debugger(self) -> Self:
        if self.debugpy:
            self.enable_debugpy()
        return self


class LoggingSettings(BaseSettings):
    """global logging settings, access via coding_agent.appconfig.settings"""

    verbosity: Annotated[CliVerbosity, _logging_group] = None

    litellm_debug: Annotated[CliFlag[bool], _logging_group] = Field(
        default=False,
        description="Enable debug logging for litellm library",
    )
    conversation_debug: Annotated[CliFlag[bool], _logging_group] = Field(
        default=False,
        description="Enable debug logging for conversation flows",
    )
    agent_streaming_debug: Annotated[CliFlag[bool], _logging_group] = Field(
        default=False,
        description="Enable debug logging for agent streaming",
    )
    interactive_terminal: Annotated[CliImplicitFlag[bool], _logging_group] = Field(
        default=sys.stdout.isatty(),
        description="Enable interactive terminal mode (default: True if stdout is a terminal)",
    )

    @field_validator("verbosity", mode="before")
    @classmethod
    def validate_verbosity(cls, v: Any) -> int:
        """Handle -v, -vv, -vvv style flags"""
        match v:
            case None:
                verbosity = 2
            case str() as v if v.isdigit():
                verbosity = int(v)
            case int() as v:
                verbosity = v
            case _:
                raise ValueError(f"Verbosity must be an integer, got {v!r}")

        if verbosity > 5:
            raise ValueError("Verbosity cannot be greater than 5")

        if verbosity < 0:
            raise ValueError("Verbosity cannot be less than 0")

        return verbosity

    @model_validator(mode="after")
    def validate_logging(self) -> Self:
        """done as a validator to ensure the settings are changed any time the settings are changed"""
        from coding_agent.lib.logging import configure_logging

        assert self.verbosity is not None

        configure_logging(
            verbosity=self.verbosity,
            litellm_debug=self.litellm_debug,
            conversation_debug=self.conversation_debug,
            agent_streaming_debug=self.agent_streaming_debug,
            interactive_terminal=self.interactive_terminal,
        )
        return self


_group = Group("cache")


class CacheSettings(BaseSettings):
    litellm_cache: Annotated[bool, _group] = Field(
        default=False,
        description="Use the litellm cache to store and retrieve responses from the cache before sending requests to the Model API.",
    )
    litellm_cache_ttl: Annotated[int, _group] = Field(
        default=int(timedelta(hours=6).total_seconds()),
        ge=0,
        description="The time to live for the litellm cache.",
    )
    litellm_cache_namespace: Annotated[str, _group] = Field(
        default="coding_agent",
        description="The namespace for the litellm cache.",
    )
    litellm_cache_s_maxage: Annotated[int, _group] | None = Field(
        default=None,
        ge=0,
        description="do not use cached items older than this age",
    )
    litellm_cache_no_cache: Annotated[bool, _group] | None = Field(
        default=None,
        description="Do not cache the litellm response.",
    )
    litellm_cache_no_store: Annotated[bool, _group] | None = Field(
        default=None,
        description="Do not store the litellm response.",
    )


class GlobalSettings(LoggingSettings, CacheSettings, DebugSettings):
    """global settings, access via coding_agent.appconfig.settings"""

    model_config = SettingsConfigDict(
        frozen=True,
        validate_assignment=True,
        validate_default=True,
    )

    def model_post_init(self, context: Any) -> None:
        """
        set the global settings in thread-safe storage
        """
        super().model_post_init(context)

        logger.info(f"setting the global settings to {self.__class__.__name__}")
        settings.set(self)

    def cast_to[T: BaseModel](self, cls: type[T]) -> T:
        """
        cast the settings to a given settings class, will raise a ValueError if
        the settings are not of the given class
        """
        if isinstance(self, cls):
            return self
        raise ValueError(
            f"cannot cast '{self.__class__.__name__} ({id(self.__class__)})' to '{cls.__name__} ({id(cls)})'"
        )


_debug_group = Group("debug")


class CliApp(GlobalSettings):
    """
    This class is a wrapper around the AppConfig class that adds the ability to
    parse CLI arguments and environment variables. All cli classes should be a subclass of this class.
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        cli_ignore_unknown_args=False,
        cli_kebab_case=True,
    )

    inspect_settings: Annotated[CliFlag[bool], _debug_group] = Field(
        default=False,
        description="Print the parsed settings to the console and exit",
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        if not hasattr(cls, "cli_cmd"):
            e = NotImplementedError(
                f"cli_cmd is required for all subclasses of CliApp: {cls.__name__}"
            )
            if hasattr(cls, "cl_run"):
                e.add_note(
                    f"found '{cls.__name__}.cli_run()', you probably want to rename it 'cli_cmd' instead"
                )
            raise e

    def _run_cli_cmd(self) -> None:
        """run the cli cmd entrypoint, if it is a coroutine, run it async"""

        cli_cmd = getattr(self, "cli_cmd", None)
        assert cli_cmd is not None

        if iscoroutinefunction(cli_cmd):
            asyncio.run(cli_cmd())
        else:
            cli_cmd()

    @classmethod
    def cli_name(cls, _cache: dict[str, Any] = {}) -> str:  # noqa: B006
        """
        The name of the CLI app.
        """
        if cls.__name__ not in _cache:
            tr = spinalcase if cls.model_config.get("cli_kebab_case") else str
            _cache[cls.__name__] = cls.model_config.get("cli_prog_name") or tr(
                cls.__name__
            ).removeprefix("run-")
        return _cache[cls.__name__]

    @classmethod
    def current_settings(cls) -> Self:
        """get the settings object for the given class"""
        return settings.get().cast_to(cls)


settings = _GlobalSettingsStore()
