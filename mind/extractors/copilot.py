from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from mind.extractors.base import Message


def _default_base() -> Path:
    return Path.home() / ".copilot" / "session-state"


class CopilotExtractor:
    tool_name = "copilot"

    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(base_dir) if base_dir else _default_base()

    def find_project_path(self, project_path: str) -> str | None:
        return str(self._base) if self._base.exists() else None

    def extract_new(
        self,
        transcript_dir: str,
        known_files: dict[str, str],
        max_chars: int,
        project_path: str = "",
    ) -> tuple[list[Message], dict[str, str]]:
        directory = Path(transcript_dir)
        messages: list[Message] = []
        updated = dict(known_files)

        for session_dir in directory.iterdir():
            if not session_dir.is_dir():
                continue
            events_file = session_dir / "events.jsonl"
            if not events_file.exists():
                continue

            fname = session_dir.name + "/events.jsonl"
            current_mtime = _iso_mtime(events_file)
            if fname in known_files and known_files[fname] >= current_mtime:
                continue

            if project_path:
                session_cwd = _read_session_cwd(events_file)
                if not session_cwd or not session_cwd.startswith(project_path):
                    continue

            for msg in _read_messages(events_file, max_chars):
                messages.append(msg)

            updated[fname] = current_mtime

        return messages, updated


def _iso_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _read_session_cwd(events_file: Path) -> str:
    try:
        first_line = events_file.read_text().split("\n", 1)[0]
        obj = json.loads(first_line)
        if obj.get("type") == "session.start":
            return obj.get("data", {}).get("cwd", "")
    except Exception:
        pass
    return ""


def _read_messages(events_file: Path, max_chars: int) -> list[Message]:
    messages: list[Message] = []
    try:
        for line in events_file.read_text().splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            event_type = obj.get("type", "")
            if event_type not in ("user.message", "assistant.message"):
                continue
            data = obj.get("data", {})
            role = "user" if event_type == "user.message" else "assistant"
            content = data.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict)
                )
            content = content.strip()
            if not content:
                continue
            timestamp = obj.get("timestamp", "")
            messages.append(Message(role=role, text=content[:max_chars], timestamp=timestamp, tool="copilot"))
    except Exception:
        pass
    return messages
