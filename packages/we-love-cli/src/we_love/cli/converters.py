from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing import ClassVar


class ConversionError(ValueError):
    def __init__(self, message: str, value: Any) -> None:
        self.message = message
        self.value = value


CONVERTER_REGISTRY: dict[type[object], list[BaseConverter[object]]] = defaultdict(list)


class BaseConverter[T]:
    handled_type: type[T]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        CONVERTER_REGISTRY[cls.handled_type].append(cls())  # type: ignore[arg-type]

    def encode(self, s: T) -> str:
        for converter in CONVERTER_REGISTRY[self.handled_type]:
            try:
                return converter.encode(s)
            except ConversionError:
                continue
        raise ConversionError(f"No converter found for type: {self.handled_type}", s)

    def decode(self, s: str) -> T: ...


class StringConverter(BaseConverter[str]):
    handled_type: type[str] = str

    def encode(self, s: str) -> str:
        return s

    def decode(self, s: str) -> str:
        return s


class IntConverter(BaseConverter[int]):
    handled_type: type[int] = int

    def encode(self, s: int) -> str:
        return str(s)

    def decode(self, s: str) -> int:
        if s.isdigit():
            return int(s)
        else:
            raise ConversionError(f"Invalid int: '{s}'", s)


class FloatConverter(BaseConverter[float]):
    handled_type: type[float] = float

    def encode(self, s: float) -> str:
        return str(s)

    def decode(self, s: str) -> float:
        if s.replace(".", "", 1).isdigit():
            return float(s)
        else:
            raise ConversionError(f"Invalid float: '{s}'", s)


class BoolConverter(BaseConverter[bool]):
    handled_type: type[bool] = bool

    _true_values: ClassVar[frozenset[str]] = frozenset(["true", "t", "yes", "y", "1", "on"])
    _false_values: ClassVar[frozenset[str]] = frozenset(["false", "f", "no", "n", "0", "off"])

    def encode(self, s: bool) -> str:
        return str(s)

    def decode(self, s: str, strict: bool = True) -> bool:
        s = s.lower()
        if strict:
            if s in self._true_values:
                return True
            elif s in self._false_values:
                return False
            else:
                raise ConversionError(f"Invalid bool: '{s}'", s)
        else:
            return s not in self._false_values


class PathConverter(BaseConverter[Path]):
    handled_type: type[Path] = Path

    def encode(self, s: Path) -> str:
        return str(s.expanduser().resolve())

    def decode(self, s: str, strict: bool = True) -> Path:
        path = Path(s).expanduser().resolve()
        if strict:
            if path.exists():
                return path
            else:
                raise ConversionError(f"Path does not exist: '{s}'", s)
        else:
            return path


class DateTimeConverter(BaseConverter[datetime]):
    handled_type: type[datetime] = datetime

    def encode(self, s: datetime) -> str:
        return s.isoformat()

    def decode(self, s: str) -> datetime:
        return datetime.fromisoformat(s)


class DateConverter(BaseConverter[date]):
    handled_type: type[date] = date

    def encode(self, s: date) -> str:
        return s.isoformat()

    def decode(self, s: str) -> date:
        return date.fromisoformat(s)


class TimeConverter(BaseConverter[time]):
    handled_type: type[time] = time

    def encode(self, s: time) -> str:
        return s.isoformat()

    def decode(self, s: str) -> time:
        return time.fromisoformat(s)


class ListConverter[T](BaseConverter[list[T]]):
    handled_type: type[list[T]] = list[T]

    def encode(self, s: list[T]) -> str:
        return ", ".join(CONVERTER_REGISTRY[T].encode(item) for item in s)

    def decode(self, s: str) -> list[T]:
        return [self.converter.decode(item) for item in s.split(",")]
