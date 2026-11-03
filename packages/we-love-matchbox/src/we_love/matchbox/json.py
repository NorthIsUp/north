"""JSON types and guards for decoded Python values.

>>> def describe(payload: object) -> str:
...     match payload:
...         case _ if is_json_object(payload):
...             return f"object with {len(payload)} fields"
...         case _ if is_json_array(payload):
...             return f"array with {len(payload)} items"
...         case _ if is_json_value(payload):
...             return "JSON scalar"
...         case _:
...             return "not JSON"
>>> describe({"items": [True, None, 3.5]})
'object with 1 fields'
>>> describe(["hello", 42])
'array with 2 items'
>>> describe({"invalid": float("nan")})
'not JSON'
>>> is_json_number(True), is_json_bool(True), is_json_string("hello")
(False, True, True)
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Iterable

type JsonNull = None
type JsonBool = bool
type JsonNumber = int | float
type JsonString = str
type JsonObject = dict[str, JsonValue]
type JsonArray = list[JsonValue]
type JsonValue = JsonNull | JsonBool | JsonNumber | JsonString | JsonObject | JsonArray

__all__ = [
    "JsonArray",
    "JsonBool",
    "JsonNull",
    "JsonNumber",
    "JsonObject",
    "JsonString",
    "JsonValue",
    "is_json_array",
    "is_json_bool",
    "is_json_null",
    "is_json_number",
    "is_json_object",
    "is_json_string",
    "is_json_value",
]


def is_json_null(value: object) -> TypeGuard[JsonNull]:
    return value is None


def is_json_bool(value: object) -> TypeGuard[JsonBool]:
    return isinstance(value, bool)


def is_json_number(value: object) -> TypeGuard[JsonNumber]:
    return (isinstance(value, int) and not isinstance(value, bool)) or (isinstance(value, float) and math.isfinite(value))


def is_json_string(value: object) -> TypeGuard[JsonString]:
    return isinstance(value, str)


def _is_dictionary(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Check string keys and recursively valid values, without copying or coercion."""
    return _is_dictionary(value) and is_json_value(value)


def is_json_array(value: object) -> TypeGuard[JsonArray]:
    """Check a list's recursively valid values, without copying or coercion."""
    return _is_list(value) and is_json_value(value)


def is_json_value(value: object) -> TypeGuard[JsonValue]:
    """Reject unsupported values, non-finite floats, and cycles at any depth."""
    pending: list[tuple[object, bool]] = [(value, False)]
    ancestors: set[int] = set()
    while pending:
        current, exiting = pending.pop()
        if exiting:
            ancestors.remove(id(current))
            continue
        children: Iterable[object]
        match current:
            case None | bool() | int() | str():
                continue
            case float():
                if not math.isfinite(current):
                    return False
                continue
            case _ if _is_dictionary(current):
                if any(not isinstance(key, str) for key in current):
                    return False
                children = current.values()
            case _ if _is_list(current):
                children = current
            case _:
                return False
        if id(current) in ancestors:
            return False
        ancestors.add(id(current))
        pending.append((current, True))
        pending.extend((item, False) for item in children)
    return True
