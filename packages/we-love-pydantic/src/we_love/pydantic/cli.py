from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
import types
import typing
from argparse import ArgumentParser
from collections import UserString
from collections.abc import Callable, Sequence
from datetime import timedelta
from functools import cached_property
from inspect import getmembers, iscoroutinefunction
from pdb import post_mortem
from types import ModuleType, TracebackType
from typing import (
    Annotated,
    ClassVar,
    Protocol,
    Self,
    TypeVar,
    Unpack,
    get_args,
    get_origin,
    override,
)

import debugpy
from pydantic import (
    AliasChoices,
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    RootModel,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from rich import console
from rich.panel import Panel
from rich.pretty import pprint, pretty_repr
from we_love.registry.autodiscover import autodiscover_iter
from we_love.string.case import spinalcase

if typing.TYPE_CHECKING:
    from pydantic.fields import FieldInfo

try:
    import argcomplete
except ImportError:
    argcomplete = None


class ArgumentContainer(Protocol):
    def add_argument(
        self,
        *names: str,
        dest: str | None = None,
        help: str | None = None,
        action: str | type[argparse.Action] = "store",
        type: Callable[[str], object] = str,
        default: object = argparse.SUPPRESS,
    ) -> argparse.Action: ...


class ArgumentOptions(BaseModel, arbitrary_types_allowed=True):
    dest: str
    help: str | None = None
    action: str | type[argparse.Action] = "store"
    converter: Callable[[str], object] | None = None
    default: object = argparse.SUPPRESS

    def add_to(self, container: ArgumentContainer, names: Sequence[str], *, positional: bool = False) -> None:
        if positional:
            container.add_argument(*names, help=self.help, type=self.converter or str, default=self.default)
        elif self.converter is None:
            container.add_argument(*names, dest=self.dest, help=self.help, action=self.action, default=self.default)
        else:
            container.add_argument(*names, dest=self.dest, help=self.help, action=self.action, type=self.converter, default=self.default)


logger = logging.getLogger(__name__)

WE_LOVE_OPTIONAL_WARNINGS = True
_DEFAULT_VERBOSITY = 2


def kebab_case(s: str) -> str:
    s = re.sub(r"[_\s]+", "-", s)  # underscores/spaces → hyphens
    s = re.sub(r"(?<!^)(?=[A-Z])", "-", s)  # camel humps → hyphens
    return s.lower().strip("-")


# Supports the inherited settings pattern that we are using in the coding agent
class _GlobalSettingsStore:
    """Thread-safe singleton for storing global settings"""

    _settings: GlobalSettings | None = None

    def set(self, settings: GlobalSettings) -> None:
        self._settings = settings

    def get(self) -> GlobalSettings:
        if self._settings is None:
            raise LookupError("Global settings not initialized. Call settings.set() first.")
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


class Group(UserString):
    pass


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
CliUnknownArgs = Annotated[list[str], Field(default=[]), _CliUnknownArgs := _t("_CliUnknownArgs")]

# for counting flags
_Int = TypeVar("_Int", bound=int)
CliCount = Annotated[_Int, Field(default=0), _CliCountingFlag := _t("_CliCountingFlag")]

# for store-const
_StoreConst = TypeVar("_StoreConst", bound=object)
CliStoreConst = Annotated[_StoreConst, _CliStoreConst := _t("_CliStoreConst")]

# for appending to a list
CliAppend = Annotated[list[str], Field(default_factory=list), _CliAppend := _t("_CliAppend")]


# for marking the verbosity arg, generally this doesn't need to be used by users
_logging_group = Group("logging")
_default_verbosity = object()  # sentinel value for the default verbosity. 2 if unset, 0 if set
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
    def __init__(self, prog: str, indent_increment: int = 2, max_help_position: int = 48, width: int | None = None) -> None:
        super().__init__(prog, indent_increment, max_help_position, width)

    @override
    def _get_default_metavar_for_optional(self, action: argparse.Action) -> str:
        # trim the prefix from the dest for brevity
        return action.dest.split("__")[-1].upper()

    @override
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

    cli_config: ClassVar[SettingsConfigDict] = SettingsConfigDict()

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

        if argcomplete:
            argcomplete.autocomplete(self.parser)
        else:
            logger.warning("the packages 'argcomplete' is not available, autocomplete will not be enabled")

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
            parser.add_subparsers(dest="command") if any(_CliSubCommand in f.metadata for f in settings_cls.model_fields.values()) else None
        )
        for name, field in settings_cls.model_fields.items():
            if CLI_SUPPRESS in field.metadata:
                continue
            dash_names, undash_names = self._get_arg_names(name, field)
            aliases, _ = self._get_alias_names(name, field)
            destination = self._join_dest(dest, aliases[0]) if (dest is not None and dest) else aliases[0]
            annotation = field.annotation
            if _CliSubCommand in field.metadata:
                command_cls = self._get_command_cls(settings_cls, name)
                assert subparsers is not None
                self.build_parser_from_settings(
                    command_cls, subparsers.add_parser(kebab_case(name), description=command_cls.__doc__), destination
                )
                continue
            names = undash_names if _CliPositionalArg in field.metadata else dash_names
            options = ArgumentOptions(dest=destination, help=field.description)
            if _CliCountingFlag in field.metadata or _CliVerbosity in field.metadata:
                options.action = "count"
                if _CliVerbosity in field.metadata and len(dash_names) == 1:
                    names = (f"-{dash_names[0][2]}", *names)
            elif _CliImplicitFlag in field.metadata:
                options.action = argparse.BooleanOptionalAction
            elif _CliFlag in field.metadata:
                options.action = "store_true"
            else:
                if get_origin(annotation) in {typing.Union, types.UnionType}:
                    annotation = next((argument for argument in get_args(annotation) if argument is not types.NoneType), str)
                origin = get_origin(annotation)
                if origin in {list, tuple, set} or _CliAppend in field.metadata:
                    arguments = get_args(annotation)
                    annotation = arguments[0] if arguments else str
                    options.action = "append"
                adapter = TypeAdapter[object](annotation if annotation is not None else str)
                options.converter = adapter.validate_python
            envvar = self._dest_to_env_var(destination)
            if envvar in os.environ:
                options.default = os.environ[envvar]
            group = next((metadata for metadata in field.metadata if isinstance(metadata, Group)), None)
            if group is None:
                options.add_to(parser, names, positional=_CliPositionalArg in field.metadata)
            else:
                options.add_to(parser.add_argument_group(str(group)), names, positional=_CliPositionalArg in field.metadata)

    def _join_dest(self, dest: str, name: str) -> str:
        """dest.foo, bar -> dest.foo.bar"""
        return self.cli_dest_separator.join((dest, name))

    def _dest_to_env_var(self, dest: str) -> str:
        """SOME_NAME.dest.name -> SOME_NAME__DEST__NAME"""
        return dest.replace(self.cli_dest_separator, self.cli_env_separator).replace("-", "_").upper()

    def _ns_to_command_dict(self, ns: argparse.Namespace, command_only: bool = False) -> tuple[str, dict[str, object]]:
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

    @staticmethod
    def _get_alias_names(
        field_name: str,
        field_info: FieldInfo,
        alias_path_args: dict[str, str] | None = None,
        case_sensitive: bool = True,
    ) -> tuple[tuple[str, ...], bool]:
        """Get alias names for a field, handling alias paths and case sensitivity."""

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
                name = str(alias_path.path[0])
                name = name.lower() if not case_sensitive else name
                alias_path_args[name] = "dict" if len(alias_path.path) > 2 else "list"
                if not alias_names and is_alias_path_only:
                    alias_names.append(name)
        if not case_sensitive:
            alias_names = [alias_name.lower() for alias_name in alias_names]
        return tuple(dict.fromkeys(alias_names)), is_alias_path_only

    @classmethod
    def _get_arg_names(cls, field_name: str, field_info: FieldInfo) -> tuple[Sequence[str], Sequence[str]]:
        """get the dashed and undashed version of the argument names"""
        names, _is_alias_path_only = cls._get_alias_names(field_name, field_info)
        names = [spinalcase(name) for name in names]

        return [f"--{name}" if len(name) > 1 else f"-{name}" for name in names], names

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


class BaseSettings(BaseModel):
    model_config = ConfigDict(frozen=True, validate_assignment=True, validate_default=True)
    cli_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
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
        **kwargs: Unpack[ConfigDict],
    ) -> None:
        """
        update the model config with the given kwargs
        """

        cls.cli_config = cls.cli_config.copy()
        if cli_group_name is not None:
            cls.cli_config.update(cli_group_name=cli_group_name)
        if cli_ignore_unknown_args is not None:
            cls.cli_config.update(cli_ignore_unknown_args=cli_ignore_unknown_args)
        if cli_kebab_case is not None:
            cls.cli_config.update(cli_kebab_case=cli_kebab_case)
        if cli_prog_name is not None:
            cls.cli_config.update(cli_prog_name=cli_prog_name)

        super().__init_subclass__(**kwargs)


_debug_group = Group("debug")


class DebugSettings(BaseSettings):
    pdb: Annotated[CliImplicitFlag[bool], _debug_group] = Field(
        default=False,
        description="Enable Python debugger post-mortem on exceptions",
    )
    pydantic_detailed_output: Annotated[CliImplicitFlag[bool], _debug_group] = Field(
        default=True,
        description="Enable detailed output for pydantic validation errors",
    )

    debugpy: Annotated[CliImplicitFlag[bool], _debug_group] = Field(
        default=False,
        description="Enable vscode debugger on exceptions",
    )
    debugpy_port: Annotated[int, _debug_group] = Field(
        default=5678,
        description="The port to listen for remote debugger connections",
    )

    _excepthooks: list[Callable[[type[BaseException], BaseException, types.TracebackType | None], None]] = PrivateAttr(
        default_factory=list[Callable[[type[BaseException], BaseException, types.TracebackType | None], None]]
    )

    @override
    def model_post_init(self, context: object) -> None:
        super().model_post_init(context)
        if self.pydantic_detailed_output:
            self.enable_pydantic_detailed_output_excepthook()
        if self.pdb:
            self.enable_postmortem()
        if self.debugpy:
            self.enable_debugpy()

    def add_excepthook(
        self,
        hook: Callable[[type[BaseException], BaseException, types.TracebackType | None], None],
        exec_type: type[BaseException] | tuple[type[BaseException], ...] | None = None,
    ) -> None:
        """add an excepthook for pydantic validation errors"""

        self._excepthooks.append(hook)
        sys.excepthook = self._excepthook

    def _excepthook(self, exc_type: type[BaseException], exc: BaseException, tb: types.TracebackType | None) -> None:
        for hook in self._excepthooks:
            hook(exc_type, exc, tb)

    def enable_pydantic_detailed_output_excepthook(self) -> None:
        """Enable pydantic detailed output on exceptions"""

        def _pydantic_detailed_output_excepthook(exc_type: type[BaseException], exc: BaseException, tb: types.TracebackType | None) -> None:
            if isinstance(exc, ValidationError):
                payload = exc.errors(include_url=True)
                sys.stderr.write(pretty_repr(payload))
                sys.stderr.write("\n")
                sys.stderr.flush()

        self.add_excepthook(_pydantic_detailed_output_excepthook)

    def enable_postmortem(self) -> None:
        """Enable post-mortem debugging on exceptions"""

        def _enter_post_mortem(exc_type: type[BaseException], value: BaseException, traceback: TracebackType | None) -> None:

            post_mortem(traceback)

        self.add_excepthook(_enter_post_mortem)

        sys.excepthook = _enter_post_mortem

    def enable_debugpy(self) -> None:
        """Enable vscode debugger on exceptions"""

        debugpy.listen(("127.0.0.1", self.debugpy_port))

        console.Console().print(Panel(f"Waiting for vscode debugger to attach on port {self.debugpy_port}"))

        logger.info("Waiting for vscode debugger to attach")
        debugpy.wait_for_client()
        logger.info("vscode debugger attached")


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
    def validate_verbosity(cls, v: object) -> int:
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

        assert self.verbosity is not None

        logging.basicConfig(level=max(logging.DEBUG, logging.WARNING - 10 * (self.verbosity - 1)))

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

    model_config = ConfigDict(
        frozen=True,
        validate_assignment=True,
        validate_default=True,
    )

    @override
    def model_post_init(self, context: object) -> None:
        """
        set the global settings in thread-safe storage
        """
        super().model_post_init(context)

        logger.info("setting the global settings to %s", self.__class__.__name__)
        settings.set(self)

    def cast_to[T: BaseModel](self, cls: type[T]) -> T:
        """
        cast the settings to a given settings class, will raise a ValueError if
        the settings are not of the given class
        """
        if isinstance(self, cls):
            return self
        raise ValueError(f"cannot cast '{self.__class__.__name__} ({id(self.__class__)})' to '{cls.__name__} ({id(cls)})'")


_debug_group = Group("debug")
CONTINUE = object()


class CliApp(GlobalSettings):
    """
    This class is a wrapper around the AppConfig class that adds the ability to
    parse CLI arguments and environment variables. All cli classes should be a subclass of this class.
    """

    cli_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        cli_ignore_unknown_args=False,
        cli_kebab_case=True,
    )

    inspect_settings: Annotated[CliFlag[bool], _debug_group] = Field(
        default=False,
        description="Print the parsed settings to the console and exit",
    )

    def __init_subclass__(cls, **kwargs: Unpack[ConfigDict]) -> None:
        super().__init_subclass__(**kwargs)

        if not hasattr(cls, "cli_cmd"):
            e = NotImplementedError(f"cli_cmd is required for all subclasses of CliApp: {cls.__name__}")
            if hasattr(cls, "cl_run"):
                e.add_note(f"found '{cls.__name__}.cli_run()', you probably want to rename it 'cli_cmd' instead")
            raise e

    def run_cli_cmd(self) -> None:
        """run the cli cmd entrypoint, if it is a coroutine, run it async"""
        try:
            cli_cmd = getattr(self, "cli_cmd", None)
            assert cli_cmd is not None

            if iscoroutinefunction(cli_cmd):
                asyncio.run(cli_cmd())
            else:
                cli_cmd()
        except Exception:
            logger.exception("Error running cli command")
            raise

    @classmethod
    def cli_name(cls) -> str:
        transform = spinalcase if cls.cli_config.get("cli_kebab_case") is True else str
        return cls.cli_config.get("cli_prog_name") or transform(cls.__name__).removeprefix("run-")

    @classmethod
    def from_module(cls, module: ModuleType) -> Sequence[type[CliApp]]:
        return [candidate for _, candidate in getmembers(module) if isinstance(candidate, type) and issubclass(candidate, cls)]

    @classmethod
    def current_settings(cls) -> Self:
        """get the settings object for the given class"""
        return settings.get().cast_to(cls)


settings = _GlobalSettingsStore()
