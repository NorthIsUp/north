import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar, override

MatchFuncT = Callable[[re.Pattern[str], str, int, int], re.Match[str] | None]


@dataclass
class RegexMatch:
    pattern: str | re.Pattern[str]
    compiled_pattern: re.Pattern[str] = field(init=False)

    _match: re.Match[str] | None = None
    flags: re.RegexFlag = re.NOFLAG
    match_func: ClassVar[MatchFuncT] = lambda pattern, value, start, end: pattern.search(value, start, end)

    def __post_init__(self) -> None:
        self.compiled_pattern = re.compile(self.pattern, self.flags)

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, str):
            return NotImplemented

        self._match = self.match_func(self.compiled_pattern, other, 0, len(other))
        return self._match is not None

    def __getitem__(self, group: int | str) -> str | None:
        if self._match is None:
            raise ValueError("No match found")
        value: object = self._match.group(group)
        if value is None or isinstance(value, str):
            return value
        raise TypeError("Unexpected regular expression group")

    def groups(self) -> tuple[str, ...]:
        if self._match is None:
            raise ValueError("No match found")
        return self._match.groups(default="")

    def groupdict(self) -> dict[str, str]:
        if self._match is None:
            raise ValueError("No match found")
        return self._match.groupdict(default="")


class ReSearch(RegexMatch):
    match_func: ClassVar[MatchFuncT] = lambda pattern, value, start, end: pattern.search(value, start, end)


class ReMatch(RegexMatch):
    match_func: ClassVar[MatchFuncT] = lambda pattern, value, start, end: pattern.match(value, start, end)


class ReFullmatch(RegexMatch):
    match_func: ClassVar[MatchFuncT] = lambda pattern, value, start, end: pattern.fullmatch(value, start, end)
