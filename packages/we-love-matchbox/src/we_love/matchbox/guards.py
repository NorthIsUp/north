from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import TypeGuard, TypeIs

from .type_pattern import InvalidTypeSpecificationError, TypePattern

__all__ = [
    "InvalidTypeSpecificationError",
    "is_collection_of",
    "is_dict_of",
    "is_frozenset_of",
    "is_list_of",
    "is_mapping",
    "is_objects",
    "is_sequence_of",
    "is_set_of",
    "is_tuple_of",
    "match_type",
]


def is_dict_of[T](val: object, cls: type[T]) -> TypeGuard[dict[str, T]]:
    pattern = TypePattern.from_spec(cls)
    return is_mapping(val) and all(isinstance(key, str) and pattern.matches(value) for key, value in val.items())


def is_list_of[T](val: object, cls: type[T]) -> TypeGuard[list[T]]:
    pattern = TypePattern.from_spec(cls)
    return is_objects(val) and isinstance(val, list) and all(pattern.matches(item) for item in val)


def is_tuple_of[T](val: object, cls: type[T]) -> TypeGuard[tuple[T, ...]]:
    pattern = TypePattern.from_spec(cls)
    return is_objects(val) and isinstance(val, tuple) and all(pattern.matches(item) for item in val)


def is_set_of[T](val: object, cls: type[T]) -> TypeGuard[set[T]]:
    pattern = TypePattern.from_spec(cls)
    return is_objects(val) and isinstance(val, set) and all(pattern.matches(item) for item in val)


def is_frozenset_of[T](val: object, cls: type[T]) -> TypeGuard[frozenset[T]]:
    pattern = TypePattern.from_spec(cls)
    return is_objects(val) and isinstance(val, frozenset) and all(pattern.matches(item) for item in val)


def is_sequence_of[T](val: object, cls: type[T]) -> TypeGuard[Sequence[T]]:
    pattern = TypePattern.from_spec(cls)
    return is_objects(val) and isinstance(val, Sequence) and all(pattern.matches(item) for item in val)


def is_collection_of[T](val: object, cls: type[T]) -> TypeGuard[Collection[T]]:
    pattern = TypePattern.from_spec(cls)
    return is_objects(val) and all(pattern.matches(item) for item in val)


def is_objects(value: object) -> TypeIs[Collection[object]]:
    return isinstance(value, Collection)


def is_mapping(value: object) -> TypeIs[dict[object, object]]:
    return isinstance(value, dict)


def match_type(val: object, cls: object) -> bool:
    """Validate supported runtime types without coercion.

    Guards make structural match cases more selective:

    >>> value: object = {"count": 3}
    >>> match value:
    ...     case dict() as counts if is_dict_of(counts, int):
    ...         print(sum(counts.values()))
    ...     case _:
    ...         print("not integer counts")
    3

    Nested containers and unions work in ordinary guards too:

    >>> match_type([{"count": None}, {"count": 3}], list[dict[str, int | None]])
    True
    >>> match_type(["3"], list[int])
    False
    """
    return TypePattern.from_spec(cls).matches(val)
