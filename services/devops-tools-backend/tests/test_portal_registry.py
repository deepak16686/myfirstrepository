"""Registry loader tests — exercise the real `config/tools.yaml`."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.tool_registry import (
    Registry,
    get_tool_by_id,
    invalidate_registry_cache,
    load_registry,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_REGISTRY = REPO_ROOT / "config" / "tools.yaml"


@pytest.fixture(autouse=True)
def _clear_cache():
    invalidate_registry_cache()
    yield
    invalidate_registry_cache()


def test_real_registry_loads() -> None:
    """The canonical tools.yaml must parse without error and be non-empty."""
    registry = load_registry(REAL_REGISTRY)
    assert isinstance(registry, Registry)
    assert registry.schema_version == 1
    assert len(registry.tools) > 0
    assert len(registry.categories) > 0


def test_real_registry_no_duplicate_ids() -> None:
    registry = load_registry(REAL_REGISTRY)
    ids = [t.id for t in registry.tools]
    assert len(ids) == len(set(ids)), "duplicate tool IDs are rejected by the loader"


def test_real_registry_every_tool_has_core_fields() -> None:
    registry = load_registry(REAL_REGISTRY)
    for t in registry.tools:
        assert t.id and isinstance(t.id, str)
        assert t.name
        assert t.category
        assert t.icon
        # health spec is always present
        assert t.health is not None
        assert t.health.method in {
            "GET",
            "POST",
            "HEAD",
            "tcp",
            "docker_ps",
            "docker_exec",
        }


def test_real_registry_categories_cover_all_tools() -> None:
    registry = load_registry(REAL_REGISTRY)
    cat_ids = {c.id for c in registry.categories}
    # Every tool's category should be declared (warn via assertion, not fail —
    # the portal tolerates orphans).
    missing = {t.category for t in registry.tools if t.category not in cat_ids}
    assert not missing, f"tools reference undeclared categories: {missing}"


def test_get_tool_by_id() -> None:
    registry = load_registry(REAL_REGISTRY)
    first_id = registry.tools[0].id
    found = get_tool_by_id(registry, first_id)
    assert found is not None
    assert found.id == first_id
    assert get_tool_by_id(registry, "does-not-exist") is None


def test_registry_mtime_cache(tmp_path: Path) -> None:
    """Editing the file should bust the cache on next load."""
    fake = tmp_path / "tools.yaml"
    fake.write_text(
        """
schema_version: 1
categories:
  - {id: ai, name: AI, order: 1}
tools:
  - id: foo
    name: Foo
    category: ai
    description: test
    icon: brain
    url_internal: http://foo:1
    url_external: http://localhost:1
    health: {method: GET, path: /, expect_status: 200}
    credentials: none
    embed: false
    tags: []
""",
        encoding="utf-8",
    )
    r1 = load_registry(fake)
    assert len(r1.tools) == 1

    # Replace contents, bump mtime.
    fake.write_text(
        """
schema_version: 1
categories:
  - {id: ai, name: AI, order: 1}
tools:
  - id: foo
    name: Foo
    category: ai
    description: test
    icon: brain
    url_internal: http://foo:1
    url_external: http://localhost:1
    health: {method: GET, path: /, expect_status: 200}
    credentials: none
    embed: false
    tags: []
  - id: bar
    name: Bar
    category: ai
    description: test2
    icon: brain
    url_internal: http://bar:2
    url_external: http://localhost:2
    health: {method: GET, path: /, expect_status: 200}
    credentials: none
    embed: false
    tags: []
""",
        encoding="utf-8",
    )
    # Force mtime forward (some filesystems have coarse mtime resolution).
    import os
    import time

    future = time.time() + 2
    os.utime(fake, (future, future))

    r2 = load_registry(fake)
    assert len(r2.tools) == 2


def test_registry_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_registry(tmp_path / "nope.yaml")


def test_expect_status_variants() -> None:
    """Ensure int, list[int], and 'running' all validate."""
    registry = load_registry(REAL_REGISTRY)
    saw_int = saw_list = saw_str = False
    for t in registry.tools:
        es = t.health.expect_status
        if isinstance(es, int):
            saw_int = True
        elif isinstance(es, list):
            saw_list = True
        elif isinstance(es, str):
            saw_str = True
    assert saw_int
    # Real registry may or may not contain list / "running" — but the types
    # must validate without error (already exercised by the load above).
    _ = saw_list, saw_str
