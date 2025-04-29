import logging
from collections.abc import Callable
from functools import wraps
from types import TracebackType
from typing import ParamSpec, Self, TypeVar

logger = logging.getLogger(__name__)


P = ParamSpec("P")
T = TypeVar("T")


class Suppress:
    """
    Suppress specified exceptions raised in a function, if no args are passed
    then all `Exceptions` are suppressed
    """

    def __init__(
        self,
        *exceptions: type[BaseException | BaseExceptionGroup],
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

    def __call__(self, func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwds: P.kwargs) -> T:
            with self:
                return func(*args, **kwds)

        return wrapper

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException | BaseExceptionGroup] | None,
        exc_value: BaseException | BaseExceptionGroup | None,
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
        if issubclass(exc_type, BaseExceptionGroup) and isinstance(
            exc_value, BaseExceptionGroup
        ):
            # exc_value is a BaseExceptionGroup
            # exc_match are the exceptions in the group that are in self.exceptions
            # exc_rest is the rest of the exceptions in the group

            # if exc_rest is not empty, then at least one exception in the group was not in self.exceptions
            # so we suppress the group and re-raise the rest
            _exc_match, exc_rest = exc_value.split(self.exceptions)

            if exc_rest is None:
                if msg := self.format_msg(exc_type, exc_rest):
                    logger.debug(msg)
                return True

            raise exc_rest
        return False

    def format_msg(
        self,
        exc_type: type[BaseException | BaseExceptionGroup] | None,
        exc_value: BaseException | BaseExceptionGroup | None,
    ) -> str:
        if self.msg:
            return self.msg.format(e=exc_value, exc_type=exc_type, exc_value=exc_value)
        return ""
