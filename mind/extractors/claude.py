from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from mind.extractors.base import Message

_BASE_DIR = Path.home() / ".claude" / "projects"


def _slug_from_path(project_path: str) -> str:
    # Claude Code encodes the project cwd into its ~/.claude/projects/<dir>
    # name by replacing every non-alphanumeric character (/, _, ., etc.)
    # with "-". Mirror that exactly, otherwise projects whose absolute path
    # contains "_" or "." resolve to a directory that does not exist and
    # mind silently finds no transcripts.
    return re.sub(r"[^A-Za-z0-9]", "-", project_path).lstrip("-")


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

    def extract_delta(
        self,
        file_path: str,
        from_line: int,
        prev_fingerprint: str,
        max_chars: int,
    ) -> tuple[list[Message], int, str, bool]:
        """
        Returns (messages, new_line_count, boundary_fingerprint, was_rewritten).

        from_line == 0 -> full scan. Otherwise scan only lines [from_line:],
        unless the file shrank past from_line or the line at from_line-1 no
        longer matches prev_fingerprint (rewrite) -> full re-scan.
        """
        raw = Path(file_path).read_text(errors="replace").splitlines()
        total = len(raw)

        was_rewritten = False
        if from_line > 0:
            if from_line > total or _fingerprint(raw[from_line - 1]) != prev_fingerprint:
                was_rewritten = True

        if from_line <= 0 or was_rewritten:
            slice_lines = raw
        else:
            slice_lines = raw[from_line:]

        messages = _messages_from_lines(slice_lines, max_chars)
        boundary = _fingerprint(raw[total - 1]) if total > 0 else ""
        return messages, total, boundary, was_rewritten


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


def _fingerprint(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8", errors="replace")).hexdigest()[:16]


def _messages_from_lines(lines: list[str], max_chars: int) -> list[Message]:
    messages: list[Message] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = _extract_message(entry, max_chars)
        if msg:
            messages.append(msg)
    return messages
