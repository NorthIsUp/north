# we-love-registry

Typed model and class registration with explicit discovery.

Install with `uv add we-love-registry`. Requires Python 3.13+.

## Executable example

```pycon
>>> class Example(RegisterableModel):
...     pass
>>> registry = Registry()
>>> entry = Example(name="demo")
>>> registry.register(entry)
>>> registry["demo"] is entry
True
>>> [item.name for item in registry.enabled() if isinstance(item, RegisterableModel)]
['demo']
```

Use `RegisterableModel` for named instances and `RegisterableType` for automatically registered subclasses. Descendants share their family registry. `entries` provides a mapping, `all()` returns sorted entries, and `enabled()` filters disabled entries. Registry remains a Pydantic model: normal model iteration yields field pairs. Discovery imports direct children unless recursion is enabled; import errors propagate and failed discovery can be retried.

Examples run in ordinary pytest discovery through `examples_test.py`. The distribution ships a `py.typed` marker.
