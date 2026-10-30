# Typed subset of pzp 0.0.28, verified against its implementation.
from collections.abc import Callable, Sequence

def pzp[T](
    candidates: Sequence[T],
    *,
    height: int | None = None,
    format_fn: Callable[[T], str] = ...,
    prompt_str: str = "> ",
    header_str: str = "",
) -> T | None: ...
