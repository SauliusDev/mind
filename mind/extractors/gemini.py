from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from mind.extractors.base import Message

_BASE_DIR = Path.home() / ".gemini" / "tmp"


class GeminiExtractor:
    tool_name = "gemini"

    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir) if base_dir else _BASE_DIR

    def find_project_path(self, project_path: str) -> str | None:
        project_name = Path(project_path).name
        chats = self._base / project_name / "chats"
        return str(chats) if chats.exists() else None

    def extract_new(
        self,
        transcript_dir: str,
        known_files: dict[str, str],
        max_chars: int,
    ) -> tuple[list[Message], dict[str, str]]:
        directory = Path(transcript_dir)
        messages: list[Message] = []
        updated = dict(known_files)

        for json_file in sorted(directory.glob("session-*.json")):
            fname = json_file.name
            current_mtime = _iso_mtime(json_file)

            if fname in known_files and known_files[fname] >= current_mtime:
                continue

            try:
                data = json.loads(json_file.read_text(errors="replace"))
            except json.JSONDecodeError:
                continue

            for entry in data.get("messages", []):
                msg = _extract_message(entry, max_chars)
                if msg:
                    messages.append(msg)

            updated[fname] = current_mtime

        return messages, updated


def _iso_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _extract_message(entry: dict, max_chars: int) -> Message | None:
    msg_type = entry.get("type", "")
    if msg_type not in ("user", "gemini"):
        return None

    content = entry.get("content", [])
    text = ""
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and "text" in block:
                text = block["text"].strip()
                break
    elif isinstance(content, str):
        text = content.strip()

    if not text or text.startswith("/") or text.startswith("<"):
        return None

    role = "user" if msg_type == "user" else "assistant"
    return Message(role=role, text=text[:max_chars], timestamp=entry.get("timestamp", ""), tool="gemini")
