from __future__ import annotations
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from mind.extractors.base import Message


def _default_base() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Code" / "User" / "workspaceStorage"
    if sys.platform.startswith("win"):
        import os
        return Path(os.environ.get("APPDATA", "~")) / "Code" / "User" / "workspaceStorage"
    return Path.home() / ".config" / "Code" / "User" / "workspaceStorage"


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

        for ws_dir in directory.iterdir():
            if not ws_dir.is_dir():
                continue
            db_path = ws_dir / "state.vscdb"
            if not db_path.exists():
                continue

            fname = str(ws_dir.name) + "/state.vscdb"
            current_mtime = _iso_mtime(db_path)
            if fname in known_files and known_files[fname] >= current_mtime:
                continue

            workspace_project = _read_workspace_project(db_path)
            if project_path and workspace_project and workspace_project != project_path:
                continue

            for entry in _read_chat_messages(db_path):
                role = entry.get("role", "")
                if role not in ("user", "assistant"):
                    continue
                text = entry.get("content", "").strip()
                if not text or text.startswith("/") or text.startswith("<"):
                    continue
                messages.append(Message(role=role, text=text[:max_chars], timestamp="", tool="copilot"))

            updated[fname] = current_mtime

        return messages, updated


def _iso_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _read_workspace_project(db_path: Path) -> str:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = conn.execute("SELECT value FROM ItemTable WHERE key='folder'").fetchone()
        conn.close()
        if row:
            data = json.loads(row[0])
            uri = data.get("folderUri", "")
            return uri.replace("file://", "")
    except Exception:
        pass
    return ""


def _read_chat_messages(db_path: Path) -> list[dict]:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = conn.execute("SELECT value FROM ItemTable WHERE key='copilot.chatSessions'").fetchone()
        conn.close()
        if row:
            return json.loads(row[0]) or []
    except Exception:
        pass
    return []
