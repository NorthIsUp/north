"""Canonical prefixed identifiers with lossless UUID conversion.

>>> TypeId.convert_uuid_to_b32("01958668-d7e4-7ee9-ba11-70720a9b2cb8")
'01jp36hnz4fvmvm4bge859pb5r'
>>> from typing import Literal
>>> UserId = TypeId[Literal["user"]]
>>> item = UserId("01jp36hnz4fvmvm4bge859pb5r")
>>> item.uuid_str
'01958668-d7e4-7ee9-ba11-70720a9b2cb8'
"""

from .typeid import TypeId

__all__ = ["TypeId"]
