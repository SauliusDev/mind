from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from mind.extractors.base import Message

_BASE_DIR = Path.home() / ".codex"


class CodexExtractor:
    tool_name = "codex"

    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir) if base_dir else _BASE_DIR

    def find_project_path(self, project_path: str) -> str | None:
        return str(self._base) if self._base.exists() else None

    def extract_new(
        self,
        transcript_dir: str,
        known_files: dict[str, str],
        max_chars: int,
    ) -> tuple[list[Message], dict[str, str]]:
        directory = Path(transcript_dir)
        messages: list[Message] = []
        updated = dict(known_files)

        history = directory / "history.jsonl"
        if history.exists():
            current_mtime = _iso_mtime(history)
            if "history.jsonl" not in known_files or known_files["history.jsonl"] < current_mtime:
                for entry in _parse_jsonl(history):
                    text = entry.get("text", "").strip()
                    if text and not text.startswith("/") and not text.startswith("<"):
                        messages.append(Message(
                            role="user",
                            text=text[:max_chars],
                            timestamp=_ts_to_iso(entry.get("ts", 0)),
                            tool="codex",
                        ))
                updated["history.jsonl"] = current_mtime

        return messages, updated


def _iso_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _ts_to_iso(ts: int | float) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (ValueError, OSError):
        return ""


def _parse_jsonl(path: Path) -> list[dict]:
    entries = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries
