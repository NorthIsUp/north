# we-love-funcy

Selective exception suppression for contexts and decorators.

Install with `uv add we-love-funcy`. Requires Python 3.13+.

## Executable example

```pycon
>>> with Suppress(ValueError):
...     int("invalid")
>>> @Suppress(ValueError)
... def number(text):
...     return int(text)
>>> number("12")
12
>>> number("invalid") is None
True
```

`Suppress` works as a context manager and a synchronous or async-function decorator. It returns None for suppressed failures and preserves successful values. Exception groups keep their unmatched leaves. No exception types means Exception; cancellation and other BaseExceptions propagate unless explicitly requested. Synchronous functions returning awaitables are supported too.

Examples run in ordinary pytest discovery through `examples_test.py`. The distribution ships a `py.typed` marker.

An awaitable factory can fail synchronously before returning a coroutine; suppression then returns None immediately. Check the result before awaiting. The decorator annotations expose this possibility.
