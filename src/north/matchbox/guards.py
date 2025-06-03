from __future__ import annotations

import builtins
from collections.abc import Collection, Sequence
from types import GenericAlias
from typing import Any, TypeGuard


def is_dict_of[T](val: dict[str, object], cls: type[T]) -> TypeGuard[dict[str, T]]:
    return isinstance(val, dict) and match_type(val, dict[str, cls])


def is_list_of[T](val: list[object], cls: type[T]) -> TypeGuard[list[T]]:
    return isinstance(val, list) and match_type(val, list[cls])


def is_tuple_of[T](val: tuple[object, ...], cls: type[T]) -> TypeGuard[tuple[T, ...]]:
    return isinstance(val, tuple) and match_type(val, tuple[cls, ...])


def is_set_of[T](val: set[object], cls: type[T]) -> TypeGuard[set[T]]:
    return isinstance(val, set) and match_type(val, set[cls])


def is_frozenset_of[T](val: frozenset[object], cls: type[T]) -> TypeGuard[frozenset[T]]:
    return isinstance(val, frozenset) and match_type(val, frozenset[cls])


def is_sequence_of[T](val: Sequence[object], cls: type[T]) -> TypeGuard[Sequence[T]]:
    return isinstance(val, Sequence) and match_type(val, Sequence[cls])


def is_collection_of[T](
    val: Collection[object], cls: type[T]
) -> TypeGuard[Collection[T]]:
    return isinstance(val, Collection) and match_type(val, Collection[cls])


def match_type[T](val: Any, cls: T) -> TypeGuard[T]:
    """Check if val matches the type specification cls.

    Supports:
    - Simple types: str, int, float, etc.
    - Generic types: list[str], dict[str, int], tuple[int, ...], etc.
    """
    match cls:
        case builtins.type():
            # Simple type check
            return isinstance(val, cls)
        case GenericAlias(__origin__=origin, __args__=args):
            # First check if val is an instance of the origin type
            print(f"val: {val}, origin: {origin}, args: {args}")
            if not isinstance(val, origin):
                return False

            # Validate args are valid type specifications
            if not all(
                isinstance(v, builtins.type) or isinstance(v, GenericAlias) or v is ...
                for v in args
            ):
                raise ValueError(f"Invalid type arguments: {args}")

            match origin:
                case builtins.tuple:
                    print(f"val: {val}, args: {args}")
                    # Special handling for tuples
                    if len(args) == 2 and args[1] is ...:
                        # tuple[T, ...] - homogeneous tuple of any length
                        print("homogeneous tuple of any length")
                        return all(match_type(item, args[0]) for item in val)
                    # tuple[T1, T2, ...] - fixed length tuple
                    if len(val) != len(args):
                        return False
                    print(f"val: {val}, args: {args}")
                    return all(
                        match_type(v, arg) for v, arg in zip(val, args, strict=False)
                    )

                case builtins.list | builtins.set | builtins.frozenset:
                    # For these collections, there should be exactly one type arg
                    if len(args) != 1:
                        raise ValueError(
                            f"{origin.__name__} should have exactly 1 type argument, got {len(args)}"
                        )
                    element_type = args[0]
                    return all(match_type(v, element_type) for v in val)

                case builtins.dict:
                    # Dict should have exactly 2 type args (key, value)
                    if len(args) != 2:
                        raise ValueError(
                            f"dict should have exactly 2 type arguments, got {len(args)}"
                        )
                    key_type, value_type = args
                    return all(
                        match_type(k, key_type) and match_type(v, value_type)
                        for k, v in val.items()
                    )

                case _:
                    raise ValueError(f"Unsupported generic origin: {origin}")

        case _:
            raise ValueError(f"Invalid type specification: {cls} (type: {type(cls)})")
