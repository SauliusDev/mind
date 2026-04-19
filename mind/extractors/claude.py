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
    ) -> tuple[list[Message], dict[str, str]]:
        directory = Path(transcript_dir)
        messages: list[Message] = []
        updated = dict(known_files)

        for jsonl_file in sorted(directory.glob("*.jsonl")):
            fname = jsonl_file.name
            current_mtime = _iso_mtime(jsonl_file)

            if fname in known_files and known_files[fname] >= current_mtime:
                continue

            for entry in _parse_jsonl(jsonl_file):
                msg = _extract_message(entry, max_chars)
                if msg:
                    messages.append(msg)

            updated[fname] = current_mtime

        return messages, updated


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

    return Message(role=role, text=text[:max_chars], timestamp=timestamp, tool="claude")


def _get_text(content: str | list) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block["text"].strip()
    return ""
