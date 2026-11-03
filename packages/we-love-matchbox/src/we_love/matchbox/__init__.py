"""Guards and regex value patterns for structural match statements."""

from .guards import is_collection_of, is_dict_of, is_frozenset_of, is_list_of, is_sequence_of, is_set_of, is_tuple_of, match_type
from .json import (
    JsonArray,
    JsonBool,
    JsonNull,
    JsonNumber,
    JsonObject,
    JsonString,
    JsonValue,
    is_json_array,
    is_json_bool,
    is_json_null,
    is_json_number,
    is_json_object,
    is_json_string,
    is_json_value,
)
from .regex import ReFullmatch, RegexMatch, ReMatch, ReSearch
from .type_pattern import InvalidTypeSpecificationError

__all__ = [
    "InvalidTypeSpecificationError",
    "JsonArray",
    "JsonBool",
    "JsonNull",
    "JsonNumber",
    "JsonObject",
    "JsonString",
    "JsonValue",
    "ReFullmatch",
    "ReMatch",
    "ReSearch",
    "RegexMatch",
    "is_collection_of",
    "is_dict_of",
    "is_frozenset_of",
    "is_json_array",
    "is_json_bool",
    "is_json_null",
    "is_json_number",
    "is_json_object",
    "is_json_string",
    "is_json_value",
    "is_list_of",
    "is_sequence_of",
    "is_set_of",
    "is_tuple_of",
    "match_type",
]
