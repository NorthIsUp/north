from __future__ import annotations

import argparse
import re
import types
import typing
from collections import UserString
from collections.abc import Callable
from enum import Enum, auto
from typing import Annotated, Protocol, Self, TypeVar, Unpack, get_args, get_origin, override

from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field, TypeAdapter

if typing.TYPE_CHECKING:
    from pydantic.fields import FieldInfo


class ArgumentContainer(Protocol):
    def add_argument(
        self,
        *names: str,
        dest: str | None = None,
        help: str | None = None,
        action: str | type[argparse.Action] = "store",
        type: Callable[[str], object] = str,
        default: object = argparse.SUPPRESS,
        metavar: str | None = None,
    ) -> argparse.Action: ...


class ArgumentOptions(BaseModel, arbitrary_types_allowed=True):
    dest: str
    names: tuple[str, ...]
    positional: bool = False
    group: str | None = None
    help: str | None = None
    action: str | type[argparse.Action] = "store"
    converter: Callable[[str], object] | None = None
    default: object = argparse.SUPPRESS

    @classmethod
    def from_field(cls, field_name: str, field: FieldInfo, dest: str) -> Self:
        choices: list[str | AliasPath] = []
        for alias in (field.validation_alias, field.alias):
            match alias:
                case AliasChoices():
                    choices.extend(alias.choices)
                case str() | AliasPath():
                    choices.append(alias)
                case None:
                    pass
        aliases = tuple(dict.fromkeys(choice if isinstance(choice, str) else str(choice.path[0]) for choice in choices)) or (field_name,)
        positional = CliMetadata.POSITIONAL in field.metadata
        names = tuple(kebab_case(alias) for alias in aliases)
        names = (names[0],) if positional else tuple(f"--{name}" if len(name) > 1 else f"-{name}" for name in names)
        group = next((str(value) for value in field.metadata if isinstance(value, Group)), None)
        options = cls(dest=dest, names=names, positional=positional, group=group, help=field.description)
        if CliMetadata.COUNT in field.metadata or CliMetadata.VERBOSITY in field.metadata:
            options.action = "count"
            if CliMetadata.VERBOSITY in field.metadata and len(names) == 1:
                options.names = (f"-{names[0].lstrip('-')[0]}", *names)
        elif CliMetadata.IMPLICIT_FLAG in field.metadata:
            options.action = argparse.BooleanOptionalAction
        elif CliMetadata.FLAG in field.metadata:
            options.action = "store_true"
        else:
            annotation = field.annotation
            if get_origin(annotation) in {typing.Union, types.UnionType}:
                members = tuple(argument for argument in get_args(annotation) if argument is not types.NoneType)
                if len(members) == 1:
                    annotation = members[0]
            while get_origin(annotation) is typing.Annotated:
                annotation = get_args(annotation)[0]
            if get_origin(annotation) in {list, tuple, set} or CliMetadata.APPEND in field.metadata:
                arguments = get_args(annotation)
                adapter = TypeAdapter[object](arguments[0] if arguments else str)
                options.action = "append"
            else:
                adapter = TypeAdapter[object](field.rebuild_annotation())
            options.converter = adapter.validate_python
        return options

    def add_to(self, container: ArgumentContainer) -> None:
        if self.positional:
            container.add_argument(self.dest, help=self.help, type=self.converter or str, default=self.default, metavar=self.names[0])
        elif self.converter is None:
            container.add_argument(*self.names, dest=self.dest, help=self.help, action=self.action, default=self.default)
        else:
            container.add_argument(
                *self.names, dest=self.dest, help=self.help, action=self.action, type=self.converter, default=self.default
            )


def kebab_case(s: str) -> str:
    s = re.sub(r"[_\s]+", "-", s)  # underscores/spaces → hyphens
    s = re.sub(r"(?<!^)(?=[A-Z])", "-", s)  # camel humps → hyphens
    return s.lower().strip("-")


# Typing for cli flags
# These are annotations for the cli parser, they are used to tell the cli parser
# what kind of argument the field is, flag, count, etc.
#
# the _CliBlahBlah types are for CliParser.build_parser_from_settings, they
# allow the match statement to easily find annotations markers
T = TypeVar("T")


class CliMetadata(Enum):
    SUBCOMMAND = auto()
    POSITIONAL = auto()
    IMPLICIT_FLAG = auto()
    FLAG = auto()
    EXPLICIT_FLAG = auto()
    UNKNOWN = auto()
    COUNT = auto()
    STORE_CONST = auto()
    APPEND = auto()
    VERBOSITY = auto()


class Group(UserString):
    pass


# for subcommands
CliSubCommand = Annotated[T | None, CliMetadata.SUBCOMMAND]

# for required positional args
CliPositionalArg = Annotated[T, CliMetadata.POSITIONAL]

# for optional implicit flags, --flag --no-flag true/false flags
_CliBoolFlag = TypeVar("_CliBoolFlag", bound=bool)
CliImplicitFlag = Annotated[_CliBoolFlag, CliMetadata.IMPLICIT_FLAG]

# for optional flags, --flag true/None flags flags
CliFlag = Annotated[_CliBoolFlag, CliMetadata.FLAG]

# for optional explicit flags --flag=true (flag must have a value)
CliExplicitFlag = Annotated[_CliBoolFlag, CliMetadata.EXPLICIT_FLAG]

# for not showing in help
CLI_SUPPRESS = argparse.SUPPRESS
CliSuppress = Annotated[T, CLI_SUPPRESS]

# for unknown args
CliUnknownArgs = Annotated[list[str], Field(default=[]), CliMetadata.UNKNOWN]

# for counting flags
_Int = TypeVar("_Int", bound=int)
CliCount = Annotated[_Int, Field(default=0), CliMetadata.COUNT]

# for store-const
_StoreConst = TypeVar("_StoreConst", bound=object)
CliStoreConst = Annotated[_StoreConst, CliMetadata.STORE_CONST]

# for appending to a list
CliAppend = Annotated[list[str], Field(default_factory=list), CliMetadata.APPEND]


# for marking the verbosity arg, generally this doesn't need to be used by users
LOGGING_GROUP = Group("logging")
CliVerbosity = Annotated[
    int | None,
    Field(default=None, description="The verbosity of the logging"),
    CliMetadata.VERBOSITY,
    LOGGING_GROUP,
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


class BaseSettings(BaseModel):
    model_config = ConfigDict(frozen=True, validate_assignment=True, validate_default=True, populate_by_name=True)

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

        options: SettingsConfigDict = {**cls.model_config}
        if cli_group_name is not None:
            options.update(cli_group_name=cli_group_name)
        if cli_ignore_unknown_args is not None:
            options.update(cli_ignore_unknown_args=cli_ignore_unknown_args)
        if cli_kebab_case is not None:
            options.update(cli_kebab_case=cli_kebab_case)
        if cli_prog_name is not None:
            options.update(cli_prog_name=cli_prog_name)

        cls.model_config = options
        super().__init_subclass__(**kwargs)
