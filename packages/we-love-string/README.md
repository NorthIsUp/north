# we-love-string

Identifier casing and colored differences.

Install with `uv add we-love-string`. Requires Python 3.13+.

## Executable example

```pycon
>>> to_snake("HTTPServer42")
'http_server42'
>>> camelcase("http-server42")
'httpServer42'
>>> colordiff("same", "same")
'same'
```

Both casing vocabularies use ASCII words, split acronym boundaries, and normalize punctuation. `to_camel`/`pascalcase` are PascalCase; `to_lower_camel`/`camelcase` are lowerCamelCase. Plain upper/lower/capital/trim operations preserve punctuation. This release normalizes legacy aliases consistently; identifiers that previously retained repeated delimiters can change.

Examples run in ordinary pytest discovery through `examples_test.py`. The distribution ships a `py.typed` marker.
