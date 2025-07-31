from __future__ import annotations

from base64 import b32decode, b32encode
from functools import cached_property
from typing import ClassVar, Literal, Self, _LiteralGenericAlias, get_args

import uuid6


class TypeId[Prefix: _LiteralGenericAlias](str):
    __typeid_prefix__: ClassVar[_LiteralGenericAlias]
    __typeid_prefix_str__: ClassVar[str]

    def __new__(cls, id: str | uuid6.UUID) -> Self:
        match id:
            case str() as s:
                pass
            case uuid6.UUID() as u:
                s = cls._convert_uuid_to_b32(u)
            case _:
                raise ValueError(f"Invalid id: {id}")

        return super().__new__(cls, f"{cls.__typeid_prefix_str__}_{s}")

    def __repr__(self) -> str:
        return f"TypeId[{self.prefix}]({self.suffix!r})"

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

    @staticmethod
    def _convert_uuid_to_b32(uuid_instance: uuid6.UUID) -> str:
        return b32encode(uuid_instance.bytes).decode("utf-8")

    @staticmethod
    def _convert_b32_to_uuid(b32: str) -> uuid6.UUID:
        uuid_bytes = b32decode(b32)
        uuid_int = int.from_bytes(uuid_bytes, byteorder="big")
        return uuid6.UUID(int=uuid_int, version=7)
