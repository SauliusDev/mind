from __future__ import annotations
import json
from pathlib import Path

from mind.cache import FacetCache, FileFacets, EMPTY_FACETS


def _ff() -> FileFacets:
    return FileFacets(
        mtime="2026-05-17T05:14:21+00:00",
        size=1234,
        lines_processed=10,
        boundary_fingerprint="abc123def4567890",
        user_msg_count=5,
        skipped=False,
        facets={**EMPTY_FACETS, "decisions": ["use duckdb"]},
    )


def test_save_then_load_round_trips_all_fields(tmp_path):
    cache = FacetCache(tmp_path / "facets")
    cache.save("claude", "sess1", _ff())
    loaded = cache.load("claude", "sess1")
    assert loaded == _ff()


def test_load_missing_returns_none(tmp_path):
    cache = FacetCache(tmp_path / "facets")
    assert cache.load("claude", "nope") is None


def test_corrupt_json_returns_none(tmp_path):
    cache = FacetCache(tmp_path / "facets")
    p = tmp_path / "facets" / "claude" / "bad.json"
    p.parent.mkdir(parents=True)
    p.write_text("{ not json")
    assert cache.load("claude", "bad") is None


def test_missing_schema_key_returns_none(tmp_path):
    cache = FacetCache(tmp_path / "facets")
    p = tmp_path / "facets" / "claude" / "old.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"corrections": [], "workflows": []}))
    assert cache.load("claude", "old") is None


def test_save_is_atomic_no_tmp_left(tmp_path):
    cache = FacetCache(tmp_path / "facets")
    cache.save("claude", "sess1", _ff())
    tool_dir = tmp_path / "facets" / "claude"
    assert (tool_dir / "sess1.json").exists()
    assert not any(p.name.endswith(".tmp") for p in tool_dir.iterdir())


def test_wrong_field_types_returns_none(tmp_path):
    cache = FacetCache(tmp_path / "facets")
    p = tmp_path / "facets" / "claude" / "wt.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({
        "mtime": "t", "size": "not-an-int", "lines_processed": 1,
        "boundary_fingerprint": "fp", "user_msg_count": 1,
        "skipped": False, "facets": {},
    }))
    assert cache.load("claude", "wt") is None
