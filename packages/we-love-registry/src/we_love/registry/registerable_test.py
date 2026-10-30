from __future__ import annotations

from pydantic import BaseModel
from we_love.registry.registerable import RegisterableModel, Registry


class Entry(RegisterableModel):
    pass


class Owner(BaseModel):
    registry: Registry


def test_registry_supports_nested_model_validation_and_serialization() -> None:
    registry = Registry()
    entry = Entry(name="example")
    registry.register(entry)
    owner = Owner(registry=registry)
    assert owner.registry["example"] is entry
    dumped = owner.model_dump()
    restored = Owner.model_validate(dumped)
    restored_entry = restored.registry["example"]
    assert isinstance(restored_entry, RegisterableModel)
    assert restored_entry.name == "example"
    assert "registry" in Owner.model_json_schema()["properties"]


def test_registry_entries_own_collection_iteration() -> None:
    registry = Registry()
    first = Entry(name="first")
    second = Entry(name="second", enabled=False)
    registry.register(first)
    registry.register(second)
    assert list(registry.entries.values()) == [first, second]
    assert registry.enabled() == [first]
    assert "autodiscovery_module" in dict(registry)
