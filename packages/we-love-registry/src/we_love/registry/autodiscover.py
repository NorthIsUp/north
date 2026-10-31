"""
auto-loaded config for all pytest runs

- add any cli args
- setup any plugins
- import global fixtures
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType


R = TypeVar("R")


logger = logging.getLogger(__name__)


def module_key(module: ModuleType) -> Iterable[ModuleType]:
    yield module


def paths_key(module: ModuleType) -> Iterable[Path]:
    if module.__file__ is None:
        return

    yield Path(module.__file__)


@overload
def autodiscover(package: ModuleType | str | Iterable[ModuleType | str], recursive: bool = True) -> Iterable[ModuleType]: ...


@overload
def autodiscover[R](
    package: ModuleType | str | Iterable[ModuleType | str], recursive: bool = True, *, key: Callable[[ModuleType], Iterable[R]]
) -> Iterable[R]: ...


def autodiscover[R](
    package: ModuleType | str | Iterable[ModuleType | str],
    recursive: bool = True,
    key: Callable[[ModuleType], Iterable[R]] | None = None,
) -> Iterable[R | ModuleType]:
    return list(autodiscover_iter(package, recursive, key=key)) if key is not None else list(autodiscover_iter(package, recursive))


@overload
def autodiscover_iter(package: ModuleType | str | Iterable[ModuleType | str], recursive: bool = True) -> Iterable[ModuleType]: ...


@overload
def autodiscover_iter[R](
    package: ModuleType | str | Iterable[ModuleType | str], recursive: bool = True, *, key: Callable[[ModuleType], Iterable[R]]
) -> Iterable[R]: ...


def autodiscover_iter[R](
    package: ModuleType | str | Iterable[ModuleType | str],
    recursive: bool = True,
    key: Callable[[ModuleType], Iterable[R]] | None = None,
) -> Iterable[R | ModuleType]:
    """Recursively import all submodules of a package.

    Args:
        package: Package module or string name of package
        recursive: Whether to recursively import submodules

    Returns:
        Imported submodules, or values produced by key. Import failures propagate.
    """

    match package:
        case str():
            yield from (
                autodiscover_iter(importlib.import_module(package), recursive, key=key)
                if key is not None
                else autodiscover_iter(importlib.import_module(package), recursive)
            )
            return
        case Iterable():
            for p in package:
                yield from autodiscover_iter(p, recursive, key=key) if key is not None else autodiscover_iter(p, recursive)
            return
        case _:
            pass

    if not hasattr(package, "__path__"):
        return

    for _loader, full_name, is_pkg in pkgutil.iter_modules(package.__path__, prefix=f"{package.__name__}."):
        module = importlib.import_module(full_name)
        yield from key(module) if key is not None else (module,)
        if recursive and is_pkg:
            yield from autodiscover_iter(module, recursive, key=key) if key is not None else autodiscover_iter(module, recursive)
