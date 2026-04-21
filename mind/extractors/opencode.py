from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mind.extractors.base import Message

_DB_PATH = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


class OpencodeExtractor:
    tool_name = "opencode"

    def __init__(self, db_path: str | None = None) -> None:
        self._db = Path(db_path) if db_path else _DB_PATH

    def find_project_path(self, project_path: str) -> str | None:
        if not self._db.exists():
            return None
        try:
            conn = sqlite3.connect(f"file:{self._db}?mode=ro", uri=True)
            row = conn.execute(
                "SELECT id FROM project WHERE worktree = ?", (project_path,)
            ).fetchone()
            conn.close()
            return str(self._db) if row else None
        except Exception:
            return None

    def extract_new(
        self,
        transcript_dir: str,
        known_files: dict[str, str],
        max_chars: int,
        project_path: str = "",
    ) -> tuple[list[Message], dict[str, str]]:
        db = Path(transcript_dir)
        messages: list[Message] = []
        updated = dict(known_files)

        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            sessions = conn.execute(
                "SELECT id FROM session WHERE directory = ?", (project_path,)
            ).fetchall()

            for (session_id,) in sessions:
                known_key = f"session:{session_id}"
                last_seen = int(known_files.get(known_key, "0") or "0")

                rows = conn.execute(
                    """
                    SELECT m.id, json_extract(m.data, '$.role'), m.time_created, p.data
                    FROM message m
                    JOIN part p ON p.message_id = m.id
                    WHERE m.session_id = ?
                      AND json_extract(m.data, '$.role') IN ('user', 'assistant')
                      AND m.time_created > ?
                    ORDER BY m.time_created
                    """,
                    (session_id, last_seen),
                ).fetchall()

                if not rows:
                    continue

                max_time = last_seen
                seen_msg_ids: set[str] = set()

                for msg_id, role, time_created, part_data in rows:
                    if msg_id in seen_msg_ids:
                        continue

                    pd = json.loads(part_data) if isinstance(part_data, str) else part_data
                    if pd.get("type") != "text":
                        continue
                    text = pd.get("text", "").strip()
                    if not text or text.startswith('{"type": "function"'):
                        continue

                    seen_msg_ids.add(msg_id)
                    ts = _ms_to_iso(time_created)
                    messages.append(Message(role=role, text=text[:max_chars], timestamp=ts, tool="opencode"))
                    max_time = max(max_time, time_created)

                updated[known_key] = str(max_time)

            conn.close()
        except Exception:
            pass

        return messages, updated


def _ms_to_iso(ms: int) -> str:
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return ""
