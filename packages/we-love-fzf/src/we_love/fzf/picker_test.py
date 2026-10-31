from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from we_love import fzf

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def fallback(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def choose(labels: list[str], *, format_fn: Callable[[str], str], height: int, prompt_str: str, header_str: str) -> str | None:
        calls.append(labels)
        return labels[-1] if labels else None

    monkeypatch.setattr(fzf, "pzp", choose)
    return calls


@pytest.fixture
def fzf_result(monkeypatch: pytest.MonkeyPatch) -> list[subprocess.CompletedProcess[str]]:
    results = [subprocess.CompletedProcess(["fzf"], 0, stdout="1\tduplicate\n")]

    def run(command: list[str], *, input: str, text: bool, stdout: int, check: bool) -> subprocess.CompletedProcess[str]:
        assert "--ansi" in command
        return results[0]

    monkeypatch.setattr(subprocess, "run", run)
    return results


def test_selection_preserves_item_identity(fzf_result: list[subprocess.CompletedProcess[str]]) -> None:
    items = [object(), object()]
    assert fzf.fzf_select(items, format_fn=lambda _item: "duplicate") is items[1]


def test_missing_fzf_uses_pzp(monkeypatch: pytest.MonkeyPatch, fallback: list[list[str]]) -> None:
    def unavailable(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("fzf missing")

    monkeypatch.setattr(subprocess, "run", unavailable)
    assert fzf.fzf_select(["first", "last"]) == "last"
    assert fzf.fzf_select(["first", "last"], many=True) == ["last"]
    assert len(fallback) == 2


def test_cancel_does_not_open_another_picker(fzf_result: list[subprocess.CompletedProcess[str]], fallback: list[list[str]]) -> None:
    fzf_result[0] = subprocess.CompletedProcess(["fzf"], 130, stdout="")
    assert fzf.fzf_select(["first"]) is None
    assert fallback == []


def test_process_failure_is_not_mistaken_for_cancellation(fzf_result: list[subprocess.CompletedProcess[str]]) -> None:
    fzf_result[0] = subprocess.CompletedProcess(["fzf"], 2, stdout="")
    with pytest.raises(subprocess.CalledProcessError):
        fzf.fzf_select(["first"])


def test_empty_input_does_not_start_a_picker(fallback: list[list[str]]) -> None:
    assert fzf.fzf_select(list[str]()) is None
    assert fallback == []


def test_labels_cannot_inject_terminal_records(monkeypatch: pytest.MonkeyPatch) -> None:
    """Embedded newlines, carriage returns, and tabs stay within one displayed item."""

    def run(command: list[str], *, input: str, text: bool, stdout: int, check: bool) -> subprocess.CompletedProcess[str]:
        assert input == "0\tfirst second third fourth"
        return subprocess.CompletedProcess(command, 0, stdout="0\tfirst second third fourth\n")

    monkeypatch.setattr(subprocess, "run", run)
    value = "first\nsecond\rthird\tfourth"
    assert fzf.fzf_select([value]) is value
