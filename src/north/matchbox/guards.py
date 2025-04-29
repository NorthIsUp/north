from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any, TypeGuard


def is_dict_of[T](val: dict[str, Any], cls: type[T]) -> TypeGuard[dict[str, T]]:
    return isinstance(val, dict) and all(isinstance(v, cls) for v in val.values())


def is_list_of[T](val: list[Any], cls: type[T]) -> TypeGuard[list[T]]:
    return isinstance(val, list) and all(isinstance(v, cls) for v in val)


def is_tuple_of[T](val: tuple[Any, ...], cls: type[T]) -> TypeGuard[tuple[T, ...]]:
    return isinstance(val, tuple) and all(isinstance(v, cls) for v in val)


def is_set_of[T](val: set[Any], cls: type[T]) -> TypeGuard[set[T]]:
    return isinstance(val, set) and all(isinstance(v, cls) for v in val)


def is_frozenset_of[T](val: frozenset[Any], cls: type[T]) -> TypeGuard[frozenset[T]]:
    return isinstance(val, frozenset) and all(isinstance(v, cls) for v in val)


def is_sequence_of[T](val: Sequence[Any], cls: type[T]) -> TypeGuard[Sequence[T]]:
    return isinstance(val, Sequence) and all(isinstance(v, cls) for v in val)


def is_collection_of[T](val: Collection[Any], cls: type[T]) -> TypeGuard[Collection[T]]:
    return isinstance(val, Collection) and all(isinstance(v, cls) for v in val)
