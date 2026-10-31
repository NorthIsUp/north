"""Selective exception suppression for contexts and decorators.

>>> with Suppress(ValueError):
...     int("invalid")
>>> @Suppress(ValueError)
... def number(text):
...     return int(text)
>>> number("12")
12
>>> number("invalid") is None
True
"""

from __future__ import annotations

import logging
from functools import wraps
from inspect import isawaitable, iscoroutinefunction
from typing import TYPE_CHECKING, Self, TypeGuard, TypeIs, overload

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from types import TracebackType


def is_exception_group(value: BaseException | None) -> TypeIs[BaseExceptionGroup[BaseException]]:
    return isinstance(value, BaseExceptionGroup)


logger = logging.getLogger(__name__)


def _is_async[**P](func: Callable[P, object]) -> TypeGuard[Callable[P, Awaitable[object]]]:
    return iscoroutinefunction(func)


def _is_awaitable(value: object) -> TypeIs[Awaitable[object]]:
    return isawaitable(value)


class Suppress:
    """
    Suppress specified exceptions raised in a function, if no args are passed
    then all `Exceptions` are suppressed
    """

    def __init__(
        self,
        *exceptions: type[BaseException],
        msg: str = "",
    ) -> None:
        """
        Initialize a Suppress context manager.

        Args:
            *exceptions: Exception types to suppress. If none provided, suppresses all Exceptions.
            msg: Optional message to include when exceptions are suppressed.
        """
        if not exceptions:
            exceptions = (Exception,)
        self.exceptions = exceptions
        self.msg = msg

    @overload
    def __call__[**P, R](self, func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | None] | None]: ...

    @overload
    def __call__[**P, R](self, func: Callable[P, R]) -> Callable[P, R | None]: ...

    def __call__[**P](self, func: Callable[P, object]) -> Callable[P, object]:
        async def await_result(value: Awaitable[object]) -> object:
            with self:
                return await value
            return None

        if _is_async(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwds: P.kwargs) -> object:
                with self:
                    return await func(*args, **kwds)
                return None

            return async_wrapper

        @wraps(func)
        def wrapper(*args: P.args, **kwds: P.kwargs) -> object:
            with self:
                result = func(*args, **kwds)
                return await_result(result) if _is_awaitable(result) else result
            return None

        return wrapper

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Suppress exceptions of the given types, raise the rest"""

        # See http://bugs.python.org/issue12029 for more details
        if exc_type is None:
            return None
        if issubclass(exc_type, self.exceptions):
            if msg := self.format_msg(exc_type, exc_value):
                logger.debug(msg)
            return True
        if issubclass(exc_type, BaseExceptionGroup) and is_exception_group(exc_value):
            # exc_value is a BaseExceptionGroup
            # exc_match are the exceptions in the group that are in self.exceptions
            # exc_rest is the rest of the exceptions in the group

            # if exc_rest is not empty, then at least one exception in the group was not in self.exceptions
            # so we suppress the group and re-raise the rest
            _exc_match, exc_rest = exc_value.split(self.exceptions)

            if exc_rest is None:
                if msg := self.format_msg(type(exc_value), exc_value):
                    logger.debug(msg)
                return True

            raise exc_rest
        return False

    def format_msg(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
    ) -> str:
        if self.msg:
            return self.msg.format(e=exc_value, exc_type=exc_type, exc_value=exc_value)
        return ""
