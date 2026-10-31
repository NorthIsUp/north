# we-love-matchbox

Dependency-free guards and regex value patterns for Python 3.13+ `match`
statements. Install with `uv add we-love-matchbox`.

## Narrow a case with a typed guard

```python
from we_love.matchbox import is_dict_of

payload: object = {"apples": 3, "pears": 2}
match payload:
    case dict() as counts if is_dict_of(counts, int):
        total = sum(counts.values())  # counts narrows to dict[str, int]
    case _:
        total = 0
```

`is_dict_of(value, T)` checks string keys and values of type `T`.
`is_list_of`, `is_tuple_of`, `is_set_of`, and `is_frozenset_of` check their
concrete container and every element. `is_sequence_of` and `is_collection_of`
accept the corresponding `collections.abc` interfaces. Empty containers pass.
Sequence/collection guards include strings and bytes; dictionaries iterate
keys. Use the concrete guards when those semantics are unwanted. Runtime class
checks follow `isinstance`, including subclasses (`bool` is an `int`).

## Match nested type expressions

```python
from we_love.matchbox import match_type

match payload:
    case _ if match_type(payload, dict[str, int | None]):
        pass
    case _:
        pass
```

`match_type` returns a boolean; it cannot statically narrow arbitrary type
expressions. Use typed guards when the case body needs narrowed types.
Supported specifications:

- Runtime-checkable classes, `None`, and `object` (accepts any value).
- Unions (`int | str`, `int | None`, and `typing.Union`/`Optional`).
- Nested `list[T]`, `set[T]`, `frozenset[T]`, and `dict[K, V]`.
- Fixed tuples (`tuple[int, str]`), variadic tuples (`tuple[int, ...]`),
  and empty tuples (`tuple[()]`).
- Parameterized `Collection`, `Sequence`, `MutableSequence`, `Set`,
  `MutableSet`, `Mapping`, and `MutableMapping` from `collections.abc`,
  including their `typing` spellings.

Values are never coerced. Unsupported specifications raise
`InvalidTypeSpecificationError` before examining the value, even for empty
containers or unused union arms. `Any`, `Literal`, `Annotated`, `TypeVar`,
forward references, type aliases declared with `type`, and arbitrary generic
classes are unsupported. Iterators are not consumed. Cyclic containers are
outside the supported input model.

## Regex value patterns

```python
from we_love.matchbox import ReFullmatch


class Patterns:
    ticket = ReFullmatch(r"issue-(?P<number>\d+)")


match "issue-42":
    case Patterns.ticket as text:
        number = Patterns.ticket["number"]  # "42"; text is "issue-42"
    case _:
        number = None
```

A dotted name is required: `case ticket:` is a capture pattern, not a regex
comparison. `RegexMatch` and `ReSearch` search anywhere, `ReMatch` matches at
the start, and `ReFullmatch` requires the whole string. Constructors accept a
string or compiled pattern and optional regex flags via `flags=`.

After success, `[0]` is the full match, integer/name indexing reads captures,
`groups()` returns a tuple, and `groupdict()` returns named captures. Optional
unmatched groups stay `None`. Invalid group names/indexes raise `IndexError`.
Every failed comparison, including non-string subjects, clears captures;
reading captures without a current match raises `ValueError`.

Matchers hold the last comparison's state. Read captures immediately in the
case body and create separate instances for concurrent or nested matching.
The `as` binding is the original subject, not the matcher or a `re.Match`.

Executable versions of these examples live in the API docstrings and run via
`mise run test` and the package CI tests. The package ships `py.typed`.

## 0.3.0

Fix dictionary guard narrowing and stale regex captures; add validated union
and nested type matching, export all public guards/matching modes, and include
executable `match` examples. Previously rejected unions now match normally;
`None` is accepted as shorthand for `type(None)`.
