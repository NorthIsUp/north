"""Runtime boundaries and static narrowing for JSON match cases."""

from __future__ import annotations

from decimal import Decimal
from typing import assert_type

import pytest
from we_love.matchbox import (
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

__all__ = []


@pytest.mark.parametrize(
    "value", [None, True, False, 0, -42, 1.5, "hello", "", [], {}, {"items": [None, True, 3.5, dict[str, JsonValue]()]}]
)
def test_valid_json_values(value: object) -> None:
    """Decoded JSON scalars and nested containers all pass without conversion."""
    assert is_json_value(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), (1, 2), {1, 2}, b"hello", Decimal(1), object(), {1: "bad"}])
def test_invalid_values_are_rejected_at_every_depth(value: object) -> None:
    """A bad leaf or object key cannot hide inside an otherwise valid container."""
    assert not is_json_value(value)
    assert not is_json_array([value])
    assert not is_json_object({"nested": [value]})


@pytest.mark.parametrize("value", [0, -42, 2**1024, 0.5, -0.0])
def test_numbers_accept_integers_and_finite_floats(value: object) -> None:
    """Large Python integers remain valid without being converted to overflowing floats."""
    assert is_json_number(value)


@pytest.mark.parametrize("value", [True, False, None, "1", float("nan"), float("inf"), float("-inf")])
def test_numbers_exclude_bool_and_nonfinite_values(value: object) -> None:
    """Python's bool subclass relationship must not turn JSON booleans into numbers."""
    assert not is_json_number(value)


@pytest.mark.parametrize("value", [None, True, 1, "hello", [], {}, [1], {"a": 1}])
def test_container_guards_require_the_right_shape(value: object) -> None:
    """Object and array guards accept their own valid shape, including empty containers."""
    assert is_json_object(value) is isinstance(value, dict)
    assert is_json_array(value) is isinstance(value, list)


def test_cycles_are_rejected_without_recursion_errors() -> None:
    """Direct and indirect self-reference cannot be represented as JSON trees."""
    array: list[object] = []
    array.append(array)
    assert not is_json_array(array)
    mapping: dict[str, object] = {}
    mapping["self"] = mapping
    assert not is_json_object(mapping)
    mixed: list[object] = []
    parent: dict[str, object] = {"items": mixed}
    mixed.append(parent)
    assert not is_json_value(parent)


def test_shared_containers_are_not_cycles() -> None:
    """Repeated references to one valid container are legal when no ancestor is revisited."""
    shared: list[object] = [1, None]
    value: object = {"first": shared, "second": [shared]}
    assert is_json_object(value)


def test_deeply_nested_values_do_not_use_python_recursion() -> None:
    """Valid or invalid leaves beyond the interpreter recursion limit yield a boolean."""
    valid: object = None
    invalid: object = object()
    for _ in range(2000):
        valid = [valid]
        invalid = {"nested": invalid}
    assert is_json_value(valid)
    assert not is_json_value(invalid)


@pytest.mark.parametrize("value", [None, True, 1, 1.5, "hello", [], {}])
def test_guards_narrow_to_every_public_alias(value: object) -> None:
    """Both strict type checkers verify the useful types inside guarded case bodies."""
    if is_json_null(value):
        assert_type(value, JsonNull)
    if is_json_bool(value):
        assert_type(value, JsonBool)
    if is_json_number(value):
        assert_type(value, JsonNumber)
    if is_json_string(value):
        assert_type(value, JsonString)
    match value:
        case _ if is_json_object(value):
            assert_type(value, JsonObject)
        case _ if is_json_array(value):
            assert_type(value, JsonArray)
        case _:
            pass
    if is_json_value(value):
        assert_type(value, JsonValue)


def test_scalar_guards_do_not_coerce() -> None:
    """Each scalar guard rejects other JSON scalar categories rather than coercing them."""
    assert is_json_null(None)
    assert not is_json_null(False)
    assert is_json_bool(False)
    assert not is_json_bool(0)
    assert is_json_string("1")
    assert not is_json_string(1)
