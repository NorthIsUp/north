"""Keep the documented match-statement examples executable in every test run."""

from __future__ import annotations

import doctest
from typing import TYPE_CHECKING

import pytest

from . import guards, regex

if TYPE_CHECKING:
    from types import ModuleType


@pytest.mark.parametrize("module", [guards, regex])
def test_match_statement_doctests(module: ModuleType) -> None:
    """Users can copy the documented guard and regex cases and get the shown output."""
    result = doctest.testmod(module, raise_on_error=True)
    assert result.attempted > 0
    assert result.failed == 0
