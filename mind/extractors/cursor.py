from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from mind.extractors.base import Message

_BASE_DIR = Path.home() / ".cursor" / "projects"


def _slug_from_path(project_path: str) -> str:
    return project_path.replace("/", "-").lstrip("-")


class CursorExtractor:
    tool_name = "cursor"

    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir) if base_dir else _BASE_DIR

    def find_project_path(self, project_path: str) -> str | None:
        slug = _slug_from_path(project_path)
        transcripts = self._base / slug / "agent-transcripts"
        return str(transcripts) if transcripts.exists() else None

    def extract_new(
        self,
        transcript_dir: str,
        known_files: dict[str, str],
        max_chars: int,
    ) -> tuple[list[Message], dict[str, str]]:
        directory = Path(transcript_dir)
        messages: list[Message] = []
        updated = dict(known_files)

        for jsonl_file in sorted(directory.rglob("*.jsonl")):
            rel = str(jsonl_file.relative_to(directory))
            current_mtime = _iso_mtime(jsonl_file)

            if rel in known_files and known_files[rel] >= current_mtime:
                continue

            for entry in _parse_jsonl(jsonl_file):
                msg = _extract_message(entry, max_chars)
                if msg:
                    messages.append(msg)

            updated[rel] = current_mtime

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
    role = entry.get("role", "")
    if role not in ("user", "assistant"):
        return None

    content = entry.get("message", {}).get("content", [])
    text = ""
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block["text"].strip()
                break
    elif isinstance(content, str):
        text = content.strip()

    if not text:
        return None

    # strip <user_query> wrapper Cursor injects around user input
    text = re.sub(r"<user_query>\s*", "", text)
    text = re.sub(r"\s*</user_query>", "", text).strip()

    if not text or text.startswith("/"):
        return None

    return Message(role=role, text=text[:max_chars], timestamp="", tool="cursor")
