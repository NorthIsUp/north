"""Select typed values using the fzf executable."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    from collections.abc import Callable


@overload
def fzf_select[T](
    items: list[T],
    prompt: str = ...,
    format_fn: Callable[[T], str] = ...,
    height: int = ...,
    width: int = ...,
    many: Literal[False] = False,
    header: str | None = None,
) -> T | None: ...


@overload
def fzf_select[T](
    items: list[T],
    prompt: str = ...,
    format_fn: Callable[[T], str] = ...,
    height: int = ...,
    width: int = ...,
    *,
    many: Literal[True],
    header: str | None = None,
) -> list[T] | None: ...


@overload
def fzf_select[T](
    items: list[T],
    prompt: str = ...,
    format_fn: Callable[[T], str] = ...,
    height: int = ...,
    width: int = ...,
    *,
    many: bool,
    header: str | None = None,
) -> T | list[T] | None: ...


def fzf_select[T](
    items: list[T],
    prompt: str = "Select an item: ",
    format_fn: Callable[[T], str] = str,
    height: int = 40,
    width: int = 100,
    many: bool = False,
    header: str | None = None,
) -> T | list[T] | None:
    command = ["fzf", "--prompt", prompt, "--height", str(height), "--with-nth", "2..", "--delimiter", "\t"]
    if many:
        command.append("--multi")
    if header is not None:
        command.extend(("--header", header))
    labels = [f"{index}\t{format_fn(item).replace(chr(10), ' ')}" for index, item in enumerate(items)]
    result = subprocess.run(command, input="\n".join(labels), text=True, stdout=subprocess.PIPE, check=False)
    if result.returncode in {1, 130} or not result.stdout.strip():
        return None
    result.check_returncode()
    selected = [items[int(line.split("\t", 1)[0])] for line in result.stdout.splitlines()]
    return selected if many else selected[0]
