"""Executable examples of the public package contract."""

import doctest

import we_love.avatars as api


def test_documented_examples() -> None:
    """The published usage examples execute and produce their documented output."""
    result = doctest.testmod(api, raise_on_error=True)
    assert result.attempted > 0
    assert result.failed == 0
