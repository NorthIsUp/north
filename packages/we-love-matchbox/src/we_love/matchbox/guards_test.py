"""Tests for typing utility functions."""

from __future__ import annotations

import pytest

from .guards import is_tuple_of, match_type


class TestIsTupleOf:
    """Test cases for is_tuple_of function."""

    def test_empty_tuple(self) -> None:
        """Test empty tuple."""
        assert is_tuple_of((), str)

    def test_homogeneous_tuple_of_strings(self) -> None:
        """Test tuple containing only strings."""
        assert is_tuple_of(("hello", "world"), str)

    def test_homogeneous_tuple_of_ints(self) -> None:
        """Test tuple containing only integers."""
        assert is_tuple_of((1, 2, 3), int)

    def test_mixed_type_tuple_fails(self) -> None:
        """Test tuple with mixed types returns False."""
        # Now properly checks all elements
        assert not is_tuple_of((1, "hello", 3), int)

        assert not is_tuple_of(("hello", 1, 3), int)

        # All ints should pass
        assert is_tuple_of((1, 2, 3), int)

    def test_not_a_tuple_fails(self) -> None:
        """Test non-tuple types return False."""
        assert not is_tuple_of([1, 2, 3], int)  # type: ignore[arg-type]  Testing non-tuple
        assert not is_tuple_of({1, 2, 3}, int)  # type: ignore[arg-type]  Testing non-tuple
        assert not is_tuple_of("hello", str)  # type: ignore[arg-type]  Testing non-tuple

    def test_nested_tuples(self) -> None:
        """Test tuple of tuples."""
        assert is_tuple_of(((1, 2), (3, 4)), tuple[int, int])
        assert is_tuple_of(((1, "hi"), (3, "ho")), tuple[int, str])
        assert not is_tuple_of(((1, "hi"), (3, "ho"), ("silver")), tuple[int, str])
        assert not is_tuple_of(((1, "hi"), (3, "ho"), (3)), tuple[int, str])

    def test_custom_class(self) -> None:
        """Test tuple of custom class instances."""

        class MyClass:
            pass

        obj1, obj2 = MyClass(), MyClass()
        assert is_tuple_of((obj1, obj2), MyClass)

    def test_subclass_instances(self) -> None:
        """Test tuple with subclass instances."""

        class BaseClass:
            pass

        class SubClass(BaseClass):
            pass

        obj1, obj2 = SubClass(), SubClass()
        # Should return True as SubClass instances are also BaseClass instances
        assert is_tuple_of((obj1, obj2), BaseClass)


class TestMatchType:
    """Test cases for match_type function."""

    def test_simple_type_match(self) -> None:
        """Test matching simple types."""
        assert match_type("hello", str)
        assert match_type(42, int)
        assert match_type(3.14, float)
        assert match_type(True, bool)

    def test_simple_type_mismatch(self) -> None:
        """Test non-matching simple types."""
        assert not match_type("hello", int)
        assert not match_type(42, str)

    def test_tuple_generic_match(self) -> None:
        """Test matching generic tuple types."""
        assert match_type(("hello", "world"), tuple[str, str])
        assert match_type((1, 2, 3), tuple[int, int, int])

    def test_tuple_generic_mismatch(self) -> None:
        """Test non-matching generic tuple types."""
        assert not match_type(("hello", 42), tuple[str, str])
        assert not match_type((1, "2", 3), tuple[int, int, int])

    def test_list_generic_match(self) -> None:
        """Test matching generic list types."""
        assert match_type(["hello", "world"], list[str])
        assert match_type([1, 2, 3], list[int])
        assert match_type([], list[str])  # empty list

    def test_list_generic_mismatch(self) -> None:
        """Test non-matching generic list types."""
        # Now properly checks all elements
        assert not match_type(["hello", 42], list[str])
        assert not match_type([1, "2", 3], list[int])

        # Test with wrong first element
        assert not match_type([42, "hello"], list[str])

    def test_dict_generic_match(self) -> None:
        """Test matching generic dict types."""
        assert match_type({"key": "value"}, dict[str, str])
        assert match_type({1: 10, 2: 20}, dict[int, int])
        assert match_type({}, dict[str, int])  # empty dict

    def test_dict_generic_mismatch(self) -> None:
        """Test non-matching generic dict types."""
        assert not match_type({"key": 42}, dict[str, str])
        assert not match_type({1: "value"}, dict[int, int])

    def test_set_generic_match(self) -> None:
        """Test matching generic set types."""
        assert match_type({"hello", "world"}, set[str])
        assert match_type({1, 2, 3}, set[int])
        assert match_type(set(), set[str])  # empty set

    def test_set_generic_mismatch(self) -> None:
        """Test non-matching generic set types."""
        # Note: can't easily test mixed types in sets since they're unordered
        assert not match_type({1, 2, 3}, set[str])

    def test_frozenset_generic_match(self) -> None:
        """Test matching generic frozenset types."""
        assert match_type(frozenset({"hello", "world"}), frozenset[str])
        assert match_type(frozenset({1, 2, 3}), frozenset[int])

    def test_nested_generics(self) -> None:
        """Test matching nested generic types."""
        # List of tuples
        assert match_type([(1, "a"), (2, "b")], list[tuple[int, str]])
        assert not match_type([(1, "a"), ("2", "b")], list[tuple[int, str]])

        # Dict with tuple values
        assert match_type({"key": (1, 2)}, dict[str, tuple[int, int]])
        assert not match_type({"key": (1, "2")}, dict[str, tuple[int, int]])

    def test_homogeneous_tuple_syntax(self) -> None:
        """Test tuple[T, ...] syntax for homogeneous tuples of any length."""
        # This syntax means "tuple of any number of T elements"
        assert match_type((1, 2, 3, 4, 5), tuple[int, ...])
        assert match_type((), tuple[int, ...])  # Empty is valid
        assert not match_type((1, "2", 3), tuple[int, ...])

        # String tuples
        assert match_type(("a", "b", "c"), tuple[str, ...])
        assert match_type(("a",), tuple[str, ...])

    def test_fixed_length_tuple(self) -> None:
        """Test fixed-length tuple specifications."""
        # tuple[int, str] means exactly 2 elements: int then str
        assert match_type((1, "hello"), tuple[int, str])
        assert not match_type((1, "hello", 2), tuple[int, str])  # Too many
        assert not match_type((1,), tuple[int, str])  # Too few
        assert not match_type(("1", "hello"), tuple[int, str])  # Wrong types

        # Three element tuple
        assert match_type((1, 2, 3), tuple[int, int, int])
        assert not match_type((1, 2), tuple[int, int, int])

    def test_bare_generic_types(self) -> None:
        """Test that using bare generic types works like isinstance."""
        # Bare generic types (without parameters) are handled as regular types
        assert not match_type("hello", list)
        assert match_type([1, 2, 3], list)
        assert match_type({"a": 1}, dict)
        assert match_type((1, 2), tuple)

    def test_invalid_class_raises(self) -> None:
        """Test that invalid classes raise ValueError."""
        with pytest.raises(ValueError, match="Invalid type specification"):
            match_type("hello", None)

    def test_custom_class(self) -> None:
        """Test matching custom class instances."""

        class MyClass:
            pass

        obj = MyClass()
        assert match_type(obj, MyClass)
        assert not match_type(obj, str)

    def test_union_types(self) -> None:
        """Test that union types are not directly supported."""
        # Union types would need special handling

        # This should raise as Union is not handled
        with pytest.raises(ValueError, match="Invalid type specification"):
            match_type("hello", str | int)

    def test_optional_types(self) -> None:
        """Test that optional types are not directly supported."""

        # Optional is just Union[T, None], so it's not handled
        with pytest.raises(ValueError, match="Invalid type specification"):
            match_type("hello", str | None)


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_none_values(self) -> None:
        """Test handling of None values."""
        assert is_tuple_of((None, None), type(None))
        assert match_type(None, type(None))

    def test_any_type(self) -> None:
        """Test handling of Any type."""
        # Test with object type as a proxy for Any behavior
        assert is_tuple_of(("hello", 42, None), object)
