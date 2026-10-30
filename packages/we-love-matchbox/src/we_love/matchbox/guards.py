from __future__ import annotations

from collections.abc import Collection, Sequence
from itertools import starmap
from types import GenericAlias
from typing import TypeGuard, TypeIs


class InvalidTypeSpecificationError(ValueError, TypeError):
    """Invalid runtime type specification."""


def is_dict_of[T](val: object, cls: type[T]) -> TypeGuard[dict[str, T]]:
    return is_objects(val) and isinstance(val, dict) and all(match_type(item, cls) for item in val)


def is_list_of[T](val: object, cls: type[T]) -> TypeGuard[list[T]]:
    return is_objects(val) and isinstance(val, list) and all(match_type(item, cls) for item in val)


def is_tuple_of[T](val: object, cls: type[T]) -> TypeGuard[tuple[T, ...]]:
    return is_objects(val) and isinstance(val, tuple) and all(match_type(item, cls) for item in val)


def is_set_of[T](val: object, cls: type[T]) -> TypeGuard[set[T]]:
    return is_objects(val) and isinstance(val, set) and all(match_type(item, cls) for item in val)


def is_frozenset_of[T](val: object, cls: type[T]) -> TypeGuard[frozenset[T]]:
    return is_objects(val) and isinstance(val, frozenset) and all(match_type(item, cls) for item in val)


def is_sequence_of[T](val: object, cls: type[T]) -> TypeGuard[Sequence[T]]:
    return is_objects(val) and isinstance(val, Sequence) and all(match_type(item, cls) for item in val)


def is_collection_of[T](val: object, cls: type[T]) -> TypeGuard[Collection[T]]:
    return is_objects(val) and all(match_type(item, cls) for item in val)


def is_objects(value: object) -> TypeIs[Collection[object]]:
    return isinstance(value, Collection)


def is_mapping(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)


def match_type(val: object, cls: object) -> bool:
    """Validate simple and parameterized runtime types recursively."""
    if isinstance(cls, type):
        return isinstance(val, cls)
    if not isinstance(cls, GenericAlias):
        raise InvalidTypeSpecificationError(f"Invalid type specification: {cls}")
    origin: object = cls.__origin__
    args: tuple[object, ...] = cls.__args__
    if not isinstance(origin, type):
        raise TypeError(f"Invalid generic origin: {origin}")
    if not isinstance(val, origin):
        return False
    if origin is dict:
        if len(args) != 2:
            raise ValueError("dict requires two type arguments")
        return is_mapping(val) and all(match_type(key, args[0]) and match_type(value, args[1]) for key, value in val.items())
    if not is_objects(val):
        raise TypeError(f"Unsupported collection: {origin}")
    if origin is tuple:
        if len(args) == 2 and args[1] is ...:
            return all(match_type(item, args[0]) for item in val)
        return len(val) == len(args) and all(starmap(match_type, zip(val, args, strict=False)))
    if len(args) != 1:
        raise ValueError("Collection requires one type argument")
    return all(match_type(item, args[0]) for item in val)
