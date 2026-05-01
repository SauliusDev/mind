from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from mind.extractors.base import Message

_BASE_DIR = Path.home() / ".claude" / "projects"


def _slug_from_path(project_path: str) -> str:
    return project_path.replace("/", "-").lstrip("-")


class ClaudeExtractor:
    tool_name = "claude"

    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir) if base_dir else _BASE_DIR

    def find_project_path(self, project_path: str) -> str | None:
        slug = "-" + _slug_from_path(project_path)
        candidate = self._base / slug
        return str(candidate) if candidate.exists() else None

    def extract_new(
        self,
        transcript_dir: str,
        known_files: dict[str, str],
        max_chars: int,
        lookbehind: int = 0,
    ) -> tuple[list[Message], dict[str, str], int, int]:
        """Returns (messages, updated_files, n_new, n_stale)."""
        directory = Path(transcript_dir)
        messages: list[Message] = []
        updated = dict(known_files)

        pending: list[tuple[Path, str]] = []
        for jsonl_file in directory.glob("*.jsonl"):
            fname = jsonl_file.name
            current_mtime = _iso_mtime(jsonl_file)
            if fname not in known_files:
                pending.append((jsonl_file, current_mtime))
            elif known_files[fname] < current_mtime:
                pending.append((jsonl_file, current_mtime))

        pending.sort(key=lambda t: t[1], reverse=True)

        n_new = sum(1 for f, _ in pending if f.name not in known_files)
        n_stale = len(pending) - n_new

        if lookbehind > 0:
            pending = pending[:lookbehind]

        for jsonl_file, current_mtime in pending:
            for entry in _parse_jsonl(jsonl_file):
                msg = _extract_message(entry, max_chars)
                if msg:
                    messages.append(msg)
            updated[jsonl_file.name] = current_mtime

        return messages, updated, n_new, n_stale

    def count_total(self, project_path: str) -> int:
        transcript_dir = self.find_project_path(project_path)
        if not transcript_dir:
            return 0
        return len(list(Path(transcript_dir).glob("*.jsonl")))


def _iso_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


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


def _extract_message(entry: dict, max_chars: int) -> Message | None:
    if entry.get("type") not in ("user", "assistant"):
        return None
    if entry.get("isMeta"):
        return None

    message = entry.get("message", {})
    role = message.get("role", entry.get("type", ""))
    content = message.get("content", "")
    timestamp = entry.get("timestamp", "")

    text = _get_text(content)
    if not text:
        return None
    if text.startswith("/") or text.startswith("<"):
        return None

    if max_chars and max_chars > 0:
        text = text[:max_chars]
    return Message(role=role, text=text, timestamp=timestamp, tool="claude")


def _get_text(content: str | list) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block["text"].strip()
    return ""
