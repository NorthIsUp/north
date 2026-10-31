# we-love-fzf

Select typed objects using fzf with a pzp fallback.

Install with `uv add we-love-fzf`. Requires Python 3.13+.

## Executable example

```pycon
>>> fzf_select([]) is None
True
```

`fzf_select(items, format_fn=str)` returns an original object, or None on empty input, no match, or cancellation. `many=True` returns a list. Duplicate labels retain object identity. The pzp fallback is a single picker: many=True wraps its single selection in a list. Labels have terminal record delimiters removed. Height is passed to the picker; width is retained for API compatibility and does not force terminal width.

Examples run in ordinary pytest discovery through `examples_test.py`. The distribution ships a `py.typed` marker.
