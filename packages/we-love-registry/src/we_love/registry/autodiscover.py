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
        Dictionary of module names to imported modules
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

    logger.info("Walking packages for %s", package.__path__)
    for _loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
        full_name = f"{package.__name__}.{name}"
        logger.debug("Importing module: %s", full_name)
        try:
            module = importlib.import_module(full_name)
        except ModuleNotFoundError:
            logger.exception("Error importing module: %s", full_name)
            continue

        logger.info("Found module: %s at %s", full_name, module.__file__)
        yield from key(module) if key is not None else (module,)

        if recursive and is_pkg:
            yield from autodiscover_iter(full_name, recursive, key=key) if key is not None else autodiscover_iter(full_name, recursive)
