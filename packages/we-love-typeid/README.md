# we-love-typeid

Install with `uv add we-love-typeid`. Python 3.13+, with a `py.typed` marker.

```python
from typing import Literal
from we_love.typeid import TypeId

UserId = TypeId[Literal["user"]]
item = UserId("01jp36hnz4fvmvm4bge859pb5r")
assert item.uuid_str == "01958668-d7e4-7ee9-ba11-70720a9b2cb8"
```

Identifiers are immutable str subclasses; slicing and casing return plain strings. Prefixes use at most 63 lowercase letters and internal underscores; an empty prefix is allowed. Suffixes are exactly 26 lowercase Crockford base32 characters encoding 128 bits. Pass a suffix, matching prefixed string, or UUID to a specialized class. The unspecialized class preserves an embedded prefix. Conversion preserves every UUID bit, including its original version and variant; it does not guarantee UUIDv7 input.

Version 0.3.0 rejects malformed suffixes at construction instead of delaying failure until UUID conversion. Code using short placeholder suffixes must switch to valid encodings. See the executable package docstring examples, run by ordinary pytest discovery.
