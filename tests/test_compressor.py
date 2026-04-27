from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mind.compressor import (
    extract_facets,
    aggregate_facets,
    load_or_extract,
    _cache_key,
)
from mind.config import Config
from mind.extractors.base import Message


def _make_config(tmp_path: Path) -> Config:
    (tmp_path / "_mind").mkdir(exist_ok=True)
    (tmp_path / "_mind" / "mind.toml").write_text("""
[project]
name = "test-project"
[llm]
provider = "claude"
[tools]
enabled = ["claude"]
[limits]
chunk_size = 3
""")
    return Config.load(tmp_path)


def _messages(n: int) -> list[Message]:
    return [
        Message("user", f"msg {i}", f"2026-04-{i+1:02d}T10:00:00Z", "claude")
        for i in range(n)
    ]


EMPTY_FACETS = {
    "corrections": [], "workflows": [], "decisions": [],
    "friction": [], "lessons": [], "prompting_gaps": [],
}

SAMPLE_FACETS = {
    "corrections": ["don't use httpx"],
    "workflows": [],
    "decisions": ["use DuckDB"],
    "friction": [],
    "lessons": ["✓ bulk inserts fast"],
    "prompting_gaps": [],
}


def test_extract_facets_calls_haiku_once_per_chunk(tmp_path):
    cfg = _make_config(tmp_path)  # chunk_size=3
    msgs = _messages(7)  # 3 chunks: [3, 3, 1]

    with patch("mind.compressor._run_haiku") as mock_haiku:
        mock_haiku.return_value = json.dumps(EMPTY_FACETS)
        extract_facets(msgs, cfg)
        assert mock_haiku.call_count == 3


def test_extract_facets_merges_results(tmp_path):
    cfg = _make_config(tmp_path)  # chunk_size=3
    msgs = _messages(4)  # 2 chunks

    facets_a = {**EMPTY_FACETS, "corrections": ["use polars"]}
    facets_b = {**EMPTY_FACETS, "decisions": ["chose DuckDB"]}

    with patch("mind.compressor._run_haiku") as mock_haiku:
        mock_haiku.side_effect = [json.dumps(facets_a), json.dumps(facets_b)]
        result = extract_facets(msgs, cfg)

    assert "use polars" in result["corrections"]
    assert "chose DuckDB" in result["decisions"]


def test_extract_facets_skips_invalid_json(tmp_path):
    cfg = _make_config(tmp_path)
    msgs = _messages(3)

    with patch("mind.compressor._run_haiku") as mock_haiku:
        mock_haiku.return_value = "not json"
        result = extract_facets(msgs, cfg)

    assert result["corrections"] == []


def test_aggregate_facets_merges_and_deduplicates():
    a = {**EMPTY_FACETS, "corrections": ["use polars", "no httpx"]}
    b = {**EMPTY_FACETS, "corrections": ["use polars", "avoid pandas"]}
    result = aggregate_facets([a, b])
    assert result["corrections"] == ["use polars", "no httpx", "avoid pandas"]


def test_cache_key_differs_by_project_path():
    key1 = _cache_key("/proj/a", "claude", {"f.jsonl": "2026-01-01"})
    key2 = _cache_key("/proj/b", "claude", {"f.jsonl": "2026-01-01"})
    assert key1 != key2


def test_cache_key_differs_by_mtime():
    key1 = _cache_key("/proj", "claude", {"f.jsonl": "2026-01-01"})
    key2 = _cache_key("/proj", "claude", {"f.jsonl": "2026-01-02"})
    assert key1 != key2


def test_load_or_extract_returns_cached_without_haiku(tmp_path):
    cfg = _make_config(tmp_path)
    cache_dir = tmp_path / "facets"
    cache_dir.mkdir()

    files = {"session.jsonl": "2026-04-01T10:00:00"}
    key = _cache_key(str(tmp_path), "claude", files)
    (cache_dir / f"{key}.json").write_text(json.dumps(SAMPLE_FACETS))

    with patch("mind.compressor._run_haiku") as mock_haiku:
        result = load_or_extract(str(tmp_path), "claude", files, [], cfg, cache_dir)
        assert mock_haiku.call_count == 0

    assert result["corrections"] == ["don't use httpx"]


def test_load_or_extract_creates_cache_on_miss(tmp_path):
    cfg = _make_config(tmp_path)
    cache_dir = tmp_path / "facets"

    files = {"session.jsonl": "2026-04-01T10:00:00"}

    with patch("mind.compressor._run_haiku") as mock_haiku:
        mock_haiku.return_value = json.dumps(SAMPLE_FACETS)
        load_or_extract(str(tmp_path), "claude", files, _messages(2), cfg, cache_dir)

    key = _cache_key(str(tmp_path), "claude", files)
    assert (cache_dir / f"{key}.json").exists()
