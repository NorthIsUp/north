"""Executable identifier examples."""

import doctest

import we_love.typeid as api


def test_documented_examples() -> None:
    """Prefixed identifier examples decode to the documented UUID without changing bits."""
    result = doctest.testmod(api, raise_on_error=True)
    assert result.attempted > 0
    assert result.failed == 0
