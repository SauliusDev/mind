from __future__ import annotations
import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path

EMPTY_FACETS: dict[str, list[str]] = {
    "corrections": [],
    "workflows": [],
    "decisions": [],
    "friction": [],
    "lessons": [],
    "prompting_gaps": [],
}


def empty_facets() -> dict[str, list[str]]:
    return {k: [] for k in EMPTY_FACETS}


@dataclass
class FileFacets:
    mtime: str
    size: int
    lines_processed: int
    boundary_fingerprint: str
    user_msg_count: int
    skipped: bool
    facets: dict[str, list[str]] = field(default_factory=empty_facets)


_SCHEMA_KEYS = {
    "mtime", "size", "lines_processed", "boundary_fingerprint",
    "user_msg_count", "skipped", "facets",
}


class FacetCache:
    """Per-transcript facet cache under <cache_dir>/<tool>/<session_id>.json."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)

    def _path(self, tool: str, session_id: str) -> Path:
        return self.cache_dir / tool / f"{session_id}.json"

    def load(self, tool: str, session_id: str) -> FileFacets | None:
        path = self._path(tool, session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict) or not _SCHEMA_KEYS.issubset(data):
            return None
        if not (
            isinstance(data["mtime"], str)
            and isinstance(data["size"], int)
            and isinstance(data["lines_processed"], int)
            and isinstance(data["boundary_fingerprint"], str)
            and isinstance(data["user_msg_count"], int)
            and isinstance(data["skipped"], bool)
            and isinstance(data["facets"], dict)
        ):
            return None
        return FileFacets(**{k: data[k] for k in _SCHEMA_KEYS})

    def save(self, tool: str, session_id: str, ff: FileFacets) -> None:
        path = self._path(tool, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(ff)))
        os.replace(tmp, path)
