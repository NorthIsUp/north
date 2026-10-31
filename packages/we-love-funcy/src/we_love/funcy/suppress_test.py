"""Suppression across context, synchronous, and awaited function boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio.lowlevel
import pytest

from . import Suppress

if TYPE_CHECKING:
    from collections.abc import Awaitable


async def test_async_decorator_suppresses_awaited_failures() -> None:
    """The decorator surrounds coroutine execution, rather than just its creation."""

    @Suppress(ValueError)
    async def operation() -> int:
        await anyio.lowlevel.checkpoint()
        raise ValueError("expected")

    result = operation()
    assert result is not None
    assert await result is None


def test_partial_exception_group_preserves_other_errors() -> None:
    """Suppression removes only selected leaves from a mixed exception group."""
    with pytest.raises(ExceptionGroup) as caught, Suppress(ValueError):
        raise ExceptionGroup("mixed", [ValueError("ignore"), TypeError("keep")])
    assert len(caught.value.exceptions) == 1
    assert isinstance(caught.value.exceptions[0], TypeError)


def test_sync_decorator_keeps_values_and_reraises_other_errors() -> None:
    """Successful return values survive the decorator, and unmatched errors escape."""

    @Suppress(ValueError)
    def operation(value: int) -> int:
        if value < 0:
            raise TypeError("negative")
        return value * 2

    assert operation(2) == 4
    with pytest.raises(TypeError):
        operation(-1)


async def test_sync_factory_returning_awaitable_is_suppressed() -> None:
    """A synchronous coroutine factory gets the same awaited failure handling as async def."""

    async def fail() -> int:
        await anyio.lowlevel.checkpoint()
        raise ValueError("expected")

    @Suppress(ValueError)
    def factory() -> Awaitable[int]:
        return fail()

    result = factory()
    assert result is not None
    assert await result is None


async def test_awaitable_factory_creation_failure_returns_none() -> None:
    """A factory that fails before creating a coroutine has no awaitable to return."""

    @Suppress(ValueError)
    def factory() -> Awaitable[int]:
        raise ValueError("creation failed")

    await anyio.lowlevel.checkpoint()
    assert factory() is None
