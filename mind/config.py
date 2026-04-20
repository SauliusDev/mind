from __future__ import annotations
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


_TOOL_PATHS_SIMPLE = {
    "claude": "~/.claude/projects",
    "gemini": "~/.gemini/tmp",
    "cursor": "~/.cursor/projects",
    "codex":  "~/.codex",
}

_COPILOT_PATHS = {
    "linux":   "~/.config/Code/User/workspaceStorage",
    "darwin":  "~/Library/Application Support/Code/User/workspaceStorage",
    "win32":   "%APPDATA%/Code/User/workspaceStorage",
}

_DEFAULT_LLM_COMMANDS = {
    "claude": "claude -p {prompt} --allowedTools 'Write(_mind/mind.md)'",
    "gemini": "gemini -p {prompt}",
    "codex":  "codex {prompt}",
}


def resolve_tool_path(tool: str) -> str:
    if tool == "copilot":
        platform = sys.platform
        key = "linux" if platform.startswith("linux") else platform
        return _COPILOT_PATHS.get(key, _COPILOT_PATHS["linux"])
    return _TOOL_PATHS_SIMPLE.get(tool, "")


@dataclass
class Config:
    project_name: str
    project_path: Path
    llm_provider: str
    llm_commands: dict[str, str]
    enabled_tools: list[str]
    max_messages_per_sync: int = 150
    max_message_chars: int = 500
    mind_max_lines: int = 150

    @classmethod
    def load(cls, project_path: Path) -> "Config":
        toml_path = project_path / "mind.toml"
        if not toml_path.exists():
            raise FileNotFoundError(f"mind.toml not found in {project_path}")
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        llm_commands = dict(_DEFAULT_LLM_COMMANDS)
        llm_commands.update(data.get("llm", {}).get("providers", {}))

        limits = data.get("limits", {})
        return cls(
            project_name=data["project"]["name"],
            project_path=project_path,
            llm_provider=data.get("llm", {}).get("provider", "claude"),
            llm_commands=llm_commands,
            enabled_tools=data.get("tools", {}).get("enabled", list(_TOOL_PATHS_SIMPLE)),
            max_messages_per_sync=limits.get("max_messages_per_sync", 150),
            max_message_chars=limits.get("max_message_chars", 500),
            mind_max_lines=limits.get("mind_max_lines", 150),
        )
