from __future__ import annotations

import re
from typing import ClassVar, Self, get_args, override

import uuid6

from .base32 import decode as b32decode
from .base32 import encode as b32encode


class TypeId[Prefix: str = str](str):
    __slots__ = ()

    __test__: ClassVar[bool] = False
    __typeid_prefix__: ClassVar[object]
    __typeid_prefix_str__: ClassVar[str]

    def __new__(cls, id: str | uuid6.UUID) -> Self:
        value_type: type[Self] = cls
        input_prefix = ""
        match id:
            case str() as suffix:
                if "_" in suffix:
                    input_prefix, suffix = suffix.rsplit("_", 1)
                    if not input_prefix:
                        raise ValueError("An empty prefix must not have a separator")
                    cls._validate_prefix(input_prefix)
                    if cls is not TypeId and input_prefix != cls.__typeid_prefix_str__:
                        raise ValueError(f"Invalid prefix for {cls.__name__}: {input_prefix}")
            case uuid6.UUID() as value:
                suffix = cls.convert_uuid_to_b32(value)
            case _:
                raise ValueError(f"Invalid id: {id}")
        b32decode(suffix)
        prefix = input_prefix if cls is TypeId else cls.__typeid_prefix_str__
        return str.__new__(value_type, f"{prefix}_{suffix}" if prefix else suffix)

    @override
    def __repr__(self) -> str:
        return f"TypeId['{self.prefix_str}']({self.suffix!r})"

    @classmethod
    def __class_getitem__(cls, prefix: object) -> type[TypeId[Prefix]]:
        # ensure prefix is a Literal
        match prefix:
            case str() as literal_value:
                literal_type = prefix
            case literal_type:  # already a Literal or TypeVar
                arguments: tuple[object, ...] = get_args(prefix)
                if len(arguments) != 1 or not isinstance(arguments[0], str):
                    raise TypeError("TypeId prefix must be a string Literal")
                literal_value = arguments[0]

        cls._validate_prefix(literal_value)

        specialized = type.__new__(type, f"{literal_value.title()}Id", (cls,), {"__slots__": ()})
        if not issubclass(specialized, cls):
            raise TypeError("TypeId specialization must inherit its base")
        specialized.__typeid_prefix__ = literal_type
        specialized.__typeid_prefix_str__ = literal_value
        return specialized

    @staticmethod
    def _validate_prefix(prefix: str) -> str:
        if len(prefix) > 63 or (prefix and re.fullmatch(r"[a-z](?:[a-z_]*[a-z])?", prefix) is None):
            raise ValueError("TypeId prefixes must be at most 63 lowercase letters with internal underscores")
        return prefix

    @property
    def prefix(self) -> object:
        return self.__typeid_prefix__ if type(self) is not TypeId else self.prefix_str

    @property
    def prefix_str(self) -> str:
        return self.__typeid_prefix_str__ if type(self) is not TypeId else self.rsplit("_", 1)[0] if "_" in self else ""

    @property
    def suffix(self) -> str:
        return self.rsplit("_", 1)[-1]

    @property
    def uuid(self) -> uuid6.UUID:
        return self.convert_b32_to_uuid(self.suffix)

    @property
    def uuid_str(self) -> str:
        return str(self.uuid)

    @property
    def uuid_int(self) -> int:
        return self.convert_b32_to_int(self.suffix)

    @staticmethod
    def convert_uuid_to_b32(uuid_instance: str | uuid6.UUID) -> str:
        if isinstance(uuid_instance, str):
            uuid_instance = uuid6.UUID(uuid_instance)
        return b32encode(list(uuid_instance.bytes))

    @staticmethod
    def convert_b32_to_int(b32: str) -> int:
        return int.from_bytes(b32decode(b32), byteorder="big")

    @staticmethod
    def convert_b32_to_uuid(b32: str) -> uuid6.UUID:
        uuid_int = int.from_bytes(b32decode(b32), byteorder="big")
        return uuid6.UUID(int=uuid_int)
