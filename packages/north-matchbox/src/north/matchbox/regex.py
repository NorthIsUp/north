import re
from dataclasses import dataclass, field
from typing import Callable, ClassVar

MatchFuncT = Callable[[re.Pattern[str], str, int, int], re.Match[str] | None]


@dataclass
class RegexMatch:
    pattern: str | re.Pattern[str]
    compiled_pattern: re.Pattern[str] = field(init=False)

    _match: re.Match[str] | None = None
    flags: re.RegexFlag = re.NOFLAG
    match_func: ClassVar[MatchFuncT] = re.Pattern.search

    def __post_init__(self) -> None:
        self.compiled_pattern = re.compile(self.pattern, self.flags)

    def __eq__(self, other: str) -> bool:
        self._match = self.match_func(self.compiled_pattern, other, 0, len(other))
        return self._match is not None

    def __getitem__(self, group: int | str) -> str | None:
        if self._match is None:
            raise ValueError("No match found")
        return self._match[group]

    def groups(self) -> tuple[str, ...]:
        if self._match is None:
            raise ValueError("No match found")
        return self._match.groups()

    def groupdict(self) -> dict[str, str]:
        if self._match is None:
            raise ValueError("No match found")
        return self._match.groupdict()


class ReSearch(RegexMatch):
    match_func: ClassVar[MatchFuncT] = re.Pattern.search


class ReMatch(RegexMatch):
    match_func: ClassVar[MatchFuncT] = re.Pattern.match


class ReFullmatch(RegexMatch):
    match_func: ClassVar[MatchFuncT] = re.Pattern.fullmatch
