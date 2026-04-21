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
        sessions_dir = self._base / "sessions"
        return str(sessions_dir) if sessions_dir.exists() else None

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

        for session_file in sorted(directory.rglob("rollout-*.jsonl")):
            rel = str(session_file.relative_to(directory))
            current_mtime = _iso_mtime(session_file)
            if rel in known_files and known_files[rel] >= current_mtime:
                continue

            session_cwd = _read_session_cwd(session_file)
            if project_path and session_cwd and not session_cwd.startswith(project_path):
                continue

            for msg in _read_messages(session_file, max_chars):
                messages.append(msg)

            updated[rel] = current_mtime

        return messages, updated


def _iso_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _read_session_cwd(session_file: Path) -> str:
    try:
        for line in session_file.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("type") == "session_meta":
                return obj.get("payload", {}).get("cwd", "")
    except Exception:
        pass
    return ""


def _read_messages(session_file: Path, max_chars: int) -> list[Message]:
    messages: list[Message] = []
    try:
        for line in session_file.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("type") != "event_msg":
                continue
            payload = obj.get("payload", {})
            event_type = payload.get("type", "")
            timestamp = obj.get("timestamp", "")

            if event_type == "user_message":
                text = payload.get("message", "").strip()
                if text:
                    messages.append(Message(
                        role="user",
                        text=text[:max_chars],
                        timestamp=timestamp,
                        tool="codex",
                    ))
            elif event_type == "agent_message" and payload.get("phase") in ("final", "final_answer", None):
                text = payload.get("message", "").strip()
                if text:
                    messages.append(Message(
                        role="assistant",
                        text=text[:max_chars],
                        timestamp=timestamp,
                        tool="codex",
                    ))
    except Exception:
        pass
    return messages
