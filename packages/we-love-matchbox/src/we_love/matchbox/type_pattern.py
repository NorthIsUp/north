"""Compile runtime type specifications before examining collection contents."""

from __future__ import annotations

from collections.abc import Collection, Mapping, MutableMapping, MutableSequence, MutableSet, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from types import UnionType
from typing import Any, Literal, TypeIs, Union, get_args, get_origin


class InvalidTypeSpecificationError(ValueError, TypeError):
    """The specification is outside matchbox's supported runtime type language."""


def _is_mapping(value: object) -> TypeIs[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_collection(value: object) -> TypeIs[Collection[object]]:
    return isinstance(value, Collection)


@dataclass(frozen=True)
class TypePattern:
    origin: type[object]
    mode: Literal["instance", "union", "mapping", "tuple", "collection"] = "instance"
    arguments: tuple[TypePattern, ...] = ()

    @classmethod
    def from_spec(cls, spec: object) -> TypePattern:
        if spec is None:
            return cls(type(None))
        # Any is a typing sentinel, not a runtime class that isinstance can check.
        if spec is Any:
            raise InvalidTypeSpecificationError("Use object instead of Any")
        origin: object = get_origin(spec)
        arguments: tuple[object, ...] = get_args(spec)
        if origin is UnionType or origin is Union:
            return cls(object, "union", tuple(cls.from_spec(arg) for arg in arguments))
        if origin is None and isinstance(spec, type):
            try:
                isinstance(None, spec)
            except TypeError as exc:
                raise InvalidTypeSpecificationError(f"Not a runtime-checkable type: {spec}") from exc
            return cls(spec)
        if isinstance(origin, type) and origin in {dict, Mapping, MutableMapping}:
            if len(arguments) != 2:
                raise InvalidTypeSpecificationError("Mappings require two type arguments")
            return cls(origin, "mapping", tuple(cls.from_spec(arg) for arg in arguments))
        if origin is tuple:
            if len(arguments) == 2 and arguments[1] is Ellipsis:
                return cls(tuple, "collection", (cls.from_spec(arguments[0]),))
            return cls(tuple, "tuple", tuple(cls.from_spec(arg) for arg in arguments))
        if isinstance(origin, type) and origin in {list, set, frozenset, Collection, Sequence, MutableSequence, AbstractSet, MutableSet}:
            if len(arguments) != 1:
                raise InvalidTypeSpecificationError("Collections require one type argument")
            return cls(origin, "collection", (cls.from_spec(arguments[0]),))
        raise InvalidTypeSpecificationError(f"Invalid type specification: {spec}")

    def matches(self, value: object) -> bool:
        if self.mode == "union":
            return any(pattern.matches(value) for pattern in self.arguments)
        if not isinstance(value, self.origin):
            return False
        if self.mode == "instance":
            return True
        if self.mode == "mapping":
            return _is_mapping(value) and all(
                self.arguments[0].matches(key) and self.arguments[1].matches(item) for key, item in value.items()
            )
        if not _is_collection(value):
            return False
        if self.mode == "tuple":
            return len(value) == len(self.arguments) and all(
                pattern.matches(item) for item, pattern in zip(value, self.arguments, strict=True)
            )
        return all(self.arguments[0].matches(item) for item in value)
