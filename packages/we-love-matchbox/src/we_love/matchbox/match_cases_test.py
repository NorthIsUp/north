"""Behavior and static narrowing for matchbox's structural match helpers."""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping, Sequence
from types import GenericAlias
from typing import Annotated, Literal, assert_type

import pytest
from we_love.matchbox import (
    InvalidTypeSpecificationError,
    ReFullmatch,
    RegexMatch,
    ReMatch,
    ReSearch,
    is_collection_of,
    is_dict_of,
    is_frozenset_of,
    is_list_of,
    is_sequence_of,
    is_set_of,
    is_tuple_of,
    match_type,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [({"count": 3}, True), ({"count": "bad"}, False), ({1: 3}, False), ({1: "bad"}, False), ({}, True), ([], False)],
)
def test_dictionary_guard_checks_both_keys_and_values(value: object, expected: bool) -> None:
    """A guarded case must never treat non-string keys or wrong values as counts."""
    assert is_dict_of(value, int) is expected


@pytest.mark.parametrize(
    ("guard", "valid", "invalid"),
    [
        (is_list_of, [1, 2], [1, "bad"]),
        (is_tuple_of, (1, 2), (1, "bad")),
        (is_set_of, {1, 2}, {1, "bad"}),
        (is_frozenset_of, frozenset({1, 2}), frozenset({1, "bad"})),
        (is_sequence_of, (1, 2), (1, "bad")),
        (is_collection_of, {1, 2}, {1, "bad"}),
    ],
)
def test_every_guard_checks_every_element(guard: Callable[[object, type[object]], bool], valid: object, invalid: object) -> None:
    """Each public guard accepts homogeneous containers and rejects mixed contents."""
    assert guard(valid, int)
    assert not guard(invalid, int)
    assert not guard(None, int)


def test_match_case_narrows_dictionary_values() -> None:
    """A case body can sum values without casts, as both checkers verify."""
    value: object = {"count": 3}
    match value:
        case _ if is_dict_of(value, int):
            assert_type(value, dict[str, int])
            assert sum(value.values()) == 3
        case _:
            pytest.fail("A dictionary of integer counts must match")


@pytest.mark.parametrize("value", [[], (), set[int](), frozenset[int](), "abc"])
def test_all_guards_narrow_static_types(value: object) -> None:
    """Both strict checkers verify every guard's advertised result type."""
    if is_list_of(value, int):
        assert_type(value, list[int])
    if is_tuple_of(value, int):
        assert_type(value, tuple[int, ...])
    if is_set_of(value, int):
        assert_type(value, set[int])
    if is_frozenset_of(value, int):
        assert_type(value, frozenset[int])
    if is_sequence_of(value, int):
        assert_type(value, Sequence[int])
    if is_collection_of(value, int):
        assert_type(value, Collection[int])


@pytest.mark.parametrize(
    ("value", "spec", "expected"),
    [
        ([{"count": None}, {"count": 3}], list[dict[str, int | None]], True),
        ([{"count": "bad"}], list[dict[str, int | None]], False),
        (None, None, True),
        (1, None, False),
        ((), tuple[()], True),
        ((1,), tuple[()], False),
        ({"count": 3}, Mapping[str, int], True),
        ((1, 2), Sequence[int], True),
        (frozenset({1}), Collection[int], True),
        ([], list[int | str], True),
        (True, int, True),
    ],
)
def test_nested_runtime_specifications(value: object, spec: object, expected: bool) -> None:
    """Runtime matching follows nested container and isinstance semantics without coercion."""
    assert match_type(value, spec) is expected


@pytest.mark.parametrize("value", [[], [1], None, 3])
@pytest.mark.parametrize("spec", [GenericAlias(list, 42), list[Literal[1]], Annotated[int, "count"]])
def test_invalid_specs_fail_independently_of_subject(value: object, spec: object) -> None:
    """Empty or mismatching subjects must not conceal an unsupported specification."""
    with pytest.raises(InvalidTypeSpecificationError):
        match_type(value, spec)


def test_collection_semantics_are_explicit() -> None:
    """ABC guards follow Python iteration, including dictionary keys and text characters."""
    assert is_sequence_of("abc", str)
    assert is_collection_of({"a": 1}, str)
    assert not is_dict_of({"a": 1}, str)
    assert not is_list_of((1,), int)
    assert not is_set_of(frozenset({1}), int)


@pytest.mark.parametrize("matcher", [ReSearch, ReMatch, ReFullmatch])
def test_failed_nonstring_comparison_clears_captures(matcher: type[RegexMatch]) -> None:
    """A later case must not read captures left by a different subject."""
    regex = matcher("(?P<letter>a)")
    assert regex == "a"
    assert regex != 1
    with pytest.raises(ValueError, match="No match found"):
        regex.groupdict()


def test_value_pattern_binds_subject_and_exposes_captures() -> None:
    """Dotted regex patterns extend match cases while the as binding stays the subject."""

    class Patterns:
        ticket = ReFullmatch(r"issue-(?P<number>\d+)")

    match "issue-42":
        case Patterns.ticket as subject:
            assert subject == "issue-42"
            assert Patterns.ticket[0] == "issue-42"
            assert Patterns.ticket["number"] == "42"
        case _:
            pytest.fail("The ticket should match")


@pytest.mark.parametrize("spec", [int | Literal["x"], GenericAlias(dict, (str,)), GenericAlias(tuple, (int, Ellipsis, str))])
def test_invalid_union_arms_and_arities_are_rejected(spec: object) -> None:
    """A matching first union arm must not hide an invalid arm or malformed container."""
    with pytest.raises(InvalidTypeSpecificationError):
        match_type(1, spec)


@pytest.mark.parametrize("matcher", [RegexMatch, ReSearch, ReMatch, ReFullmatch])
def test_regex_flags_and_capture_errors(matcher: type[RegexMatch]) -> None:
    """Every matching mode supports flags and standard capture indexing failures."""
    regex = matcher("(?P<letter>a)", flags=re.IGNORECASE)
    assert regex == "A"
    assert regex["letter"] == "A"
    with pytest.raises(IndexError):
        _ = regex[2]
    with pytest.raises(IndexError):
        _ = regex["missing"]
    assert regex != "z"
    with pytest.raises(ValueError, match="No match found"):
        _ = regex[0]


@pytest.mark.parametrize(
    ("guard", "empty"),
    [
        (is_list_of, []),
        (is_tuple_of, ()),
        (is_set_of, set[int]()),
        (is_frozenset_of, frozenset[int]()),
        (is_sequence_of, []),
        (is_collection_of, {}),
    ],
)
def test_empty_collections_satisfy_guards(guard: Callable[[object, type[object]], bool], empty: object) -> None:
    """An empty typed collection has no contradicting elements and can enter the case."""
    assert guard(empty, int)


def test_compiled_regex_patterns_keep_flags() -> None:
    """A precompiled expression keeps its matching behavior in a value pattern."""
    regex = ReFullmatch(re.compile(r"(a)", re.IGNORECASE))
    assert regex == "A"
    assert regex.groups() == ("A",)
