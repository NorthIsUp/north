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
from typing import TYPE_CHECKING, TypeVar

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


def autodiscover(
    package: ModuleType | str | Iterable[ModuleType | str],
    recursive: bool = True,
    key: Callable[[ModuleType], Iterable[R]] = module_key,
) -> Iterable[R]:
    return list(autodiscover_iter(package, recursive, key))


def autodiscover_iter(
    package: ModuleType | str | Iterable[ModuleType | str],
    recursive: bool = True,
    key: Callable[[ModuleType], Iterable[R]] = module_key,
) -> Iterable[R]:
    """Recursively import all submodules of a package.

    Args:
        package: Package module or string name of package
        recursive: Whether to recursively import submodules

    Returns:
        Dictionary of module names to imported modules
    """

    match package:
        case str():
            yield from autodiscover(importlib.import_module(package), key=key)
            return
        case Iterable():
            for p in package:
                yield from autodiscover(p, key=key)
            return

    if not hasattr(package, "__path__"):
        return

    logger.info(f"Walking packages for {package.__path__}")
    for _loader, name, is_pkg in pkgutil.walk_packages(package.__path__):
        full_name = f"{package.__name__}.{name}"
        logger.debug(f"Importing module: {full_name}")
        try:
            module = importlib.import_module(full_name)
        except ModuleNotFoundError as e:
            logger.error(f"Error importing module: {full_name} - {e}")
            continue

        logger.info(f"Found module: {full_name} at {module.__file__}")
        yield from key(module)

        if recursive and is_pkg:
            yield from autodiscover(full_name, key=key)
