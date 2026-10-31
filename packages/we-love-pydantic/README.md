# we-love-pydantic

Pydantic model helpers and legacy CLI compatibility.

Install with `uv add we-love-pydantic`. Requires Python 3.13+.

## Executable example

```pycon
>>> from pydantic import BaseModel
>>> class Options(BaseModel, metaclass=Singleton):
...     count: int = 1
>>> Options() is Options()
True
>>> Options.new_instance(count=2).count
2
```

`Singleton` caches one model instance per class: subsequent constructor arguments do not replace the first instance. `new_instance` constructs without using the cache. Define singletons only for process-scoped state; use ordinary models for request or task state. `we_love.pydantic.cli` reexports canonical `we_love.cli` objects for compatibility.

Examples run in ordinary pytest discovery through `examples_test.py`. The distribution ships a `py.typed` marker.
