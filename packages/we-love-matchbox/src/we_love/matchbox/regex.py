import re
from dataclasses import dataclass, field
from typing import override


@dataclass
class RegexMatch:
    """Search using a dotted value pattern and read captures in the case body.

    >>> class Patterns:
    ...     ticket = ReFullmatch(r"issue-(?P<number>\\d+)")
    >>> match "issue-42":
    ...     case Patterns.ticket as text:
    ...         print(text, Patterns.ticket["number"])
    ...     case _:
    ...         print("not a ticket")
    issue-42 42

    The capture belongs to the last successful comparison only:

    >>> Patterns.ticket == "other"
    False
    >>> Patterns.ticket.groups()
    Traceback (most recent call last):
        ...
    ValueError: No match found
    """

    pattern: str | re.Pattern[str]
    compiled_pattern: re.Pattern[str] = field(init=False)

    _match: re.Match[str] | None = None
    flags: re.RegexFlag = re.NOFLAG

    def __post_init__(self) -> None:
        self.compiled_pattern = re.compile(self.pattern, self.flags)

    @override
    def __eq__(self, other: object) -> bool:
        self._match = None
        if not isinstance(other, str):
            return NotImplemented

        self._match = self.match_text(other)
        return self._match is not None

    def match_text(self, text: str) -> re.Match[str] | None:
        return self.compiled_pattern.search(text)

    def __getitem__(self, group: int | str) -> str | None:
        if self._match is None:
            raise ValueError("No match found")
        value: object = self._match.group(group)
        if value is None or isinstance(value, str):
            return value
        raise TypeError("Unexpected regular expression group")

    def groups(self) -> tuple[str | None, ...]:
        if self._match is None:
            raise ValueError("No match found")
        return tuple(self[index] for index in range(1, self.compiled_pattern.groups + 1))

    def groupdict(self) -> dict[str, str | None]:
        if self._match is None:
            raise ValueError("No match found")
        return {name: self[name] for name in self.compiled_pattern.groupindex}


class ReSearch(RegexMatch):
    pass


class ReMatch(RegexMatch):
    @override
    def match_text(self, text: str) -> re.Match[str] | None:
        return self.compiled_pattern.match(text)


class ReFullmatch(RegexMatch):
    @override
    def match_text(self, text: str) -> re.Match[str] | None:
        return self.compiled_pattern.fullmatch(text)
