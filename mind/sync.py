from __future__ import annotations
from pathlib import Path

from mind.config import Config
from mind.extractors.base import Message
from mind.extractors.claude import ClaudeExtractor
from mind.extractors.gemini import GeminiExtractor
from mind.extractors.cursor import CursorExtractor
from mind.extractors.codex import CodexExtractor
from mind.extractors.copilot import CopilotExtractor
from mind.index import Index, SourceIndex
from mind.synthesizer import build_prompt, run_synthesis

_EXTRACTORS = {
    "claude":  ClaudeExtractor,
    "gemini":  GeminiExtractor,
    "cursor":  CursorExtractor,
    "codex":   CodexExtractor,
    "copilot": CopilotExtractor,
}


def run_sync(cfg: Config, mind_dir: Path, project_path: str) -> None:
    index = Index.load(mind_dir)
    all_messages: list[Message] = []
    updated_sources: dict[str, SourceIndex] = dict(index.sources)

    for tool_name in cfg.enabled_tools:
        extractor_cls = _EXTRACTORS.get(tool_name)
        if not extractor_cls:
            continue

        extractor = extractor_cls()
        transcript_dir = extractor.find_project_path(project_path)
        if not transcript_dir:
            continue

        known = index.known_files(tool_name)
        try:
            if tool_name == "copilot":
                messages, new_files = extractor.extract_new(
                    transcript_dir, known, cfg.max_message_chars, project_path=project_path
                )
            else:
                messages, new_files = extractor.extract_new(transcript_dir, known, cfg.max_message_chars)
        except Exception as e:
            print(f"mind: warning — {tool_name} extractor failed: {e}")
            continue

        all_messages.extend(messages)
        updated_sources[tool_name] = SourceIndex(path=transcript_dir, files=new_files)

    if not all_messages:
        print("✓ mind up to date")
        return

    all_messages.sort(key=lambda m: m.timestamp)
    all_messages = all_messages[-cfg.max_messages_per_sync:]

    current_mind = (mind_dir / "mind.md").read_text() if (mind_dir / "mind.md").exists() else ""
    prompt = build_prompt(cfg, all_messages, current_mind)
    run_synthesis(cfg, prompt, mind_dir)

    print(f"✓ mind synced — {len(all_messages)} messages processed")
