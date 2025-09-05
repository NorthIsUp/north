from __future__ import annotations

from functools import cached_property
from typing import ClassVar, Literal, Self, _LiteralGenericAlias, get_args

import uuid6

from .base32 import decode as b32decode
from .base32 import encode as b32encode


class TypeId[Prefix: _LiteralGenericAlias](str):
    __typeid_prefix__: ClassVar[_LiteralGenericAlias]
    __typeid_prefix_str__: ClassVar[str]

    def __new__(cls, id: str | uuid6.UUID) -> Self:
        match id:
            case str() as s:
                if "_" in s:
                    prefix, s = s.split("_")
                    if prefix != cls.__typeid_prefix_str__:
                        raise ValueError(f"Invalid prefix for {cls.__name__}: {prefix}")

            case uuid6.UUID() as u:
                s = cls._convert_uuid_to_b32(u)
            case _:
                raise ValueError(f"Invalid id: {id}")

        # For base TypeId class, use the string as-is
        if cls is TypeId:
            return super().__new__(cls, s)

        return super().__new__(cls, f"{cls.__typeid_prefix_str__}_{s}")

    def __repr__(self) -> str:
        return f"TypeId['{self.prefix_str}']({self.suffix!r})"

    @classmethod
    def __class_getitem__(cls, prefix: Prefix) -> type[TypeId[Prefix]]:
        # ensure prefix is a Literal
        match prefix:
            case str() as literal_value:
                literal_type = Literal[prefix]
            case literal_type:  # already a Literal or TypeVar
                literal_value = get_args(prefix)[0]

        # Create a specialized subclass with that prefix
        return type(
            f"{literal_value.title()}Id",
            (cls,),
            {
                "__typeid_prefix__": literal_type,
                "__typeid_prefix_str__": literal_value,
            },
        )

    @property
    def prefix(self) -> str:
        return self.__typeid_prefix__

    @cached_property
    def prefix_str(self) -> str:
        return self.__typeid_prefix_str__

    @cached_property
    def suffix(self) -> str:
        return self.split("_")[1]

    @cached_property
    def uuid(self) -> uuid6.UUID:
        return self._convert_b32_to_uuid(self.suffix)

    @property
    def uuid_str(self) -> str:
        return str(self.uuid)

    @property
    def uuid_int(self) -> int:
        return self._convert_b32_to_int(self.suffix)

    @staticmethod
    def _convert_uuid_to_b32(uuid_instance: str | uuid6.UUID) -> str:
        if isinstance(uuid_instance, str):
            uuid_instance = uuid6.UUID(uuid_instance)
        return b32encode(uuid_instance.bytes)

    @staticmethod
    def _convert_b32_to_int(b32: str) -> int:
        return int.from_bytes(b32decode(b32), byteorder="big")

    @staticmethod
    def _convert_b32_to_uuid(b32: str) -> uuid6.UUID:
        uuid_int = int.from_bytes(b32decode(b32), byteorder="big")
        return uuid6.UUID(int=uuid_int, version=7)
