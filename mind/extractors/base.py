from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Message:
    role: str        # "user" or "assistant"
    text: str
    timestamp: str   # ISO 8601
    tool: str        # "claude" | "gemini" | "cursor" | "codex" | "copilot"

    def truncated(self, max_chars: int) -> str:
        return self.text[:max_chars]

    def format(self, max_chars: int = 500) -> str:
        return f"[{self.role.upper()}]: {self.truncated(max_chars)}"


class BaseExtractor(Protocol):
    tool_name: str

    def find_project_path(self, project_path: str) -> str | None:
        """Return the tool-specific transcript directory for this project, or None."""
        ...

    def extract_new(
        self,
        transcript_dir: str,
        known_files: dict[str, str],
        max_chars: int,
    ) -> tuple[list[Message], dict[str, str]]:
        """
        Extract messages from files newer than known_files mtimes.
        Returns (messages, updated_known_files).
        """
        ...
