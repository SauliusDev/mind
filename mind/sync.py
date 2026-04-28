from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

from mind.compressor import load_or_extract, aggregate_facets
from mind.config import Config
from mind.extractors.claude import ClaudeExtractor
from mind.extractors.gemini import GeminiExtractor
from mind.extractors.cursor import CursorExtractor
from mind.extractors.codex import CodexExtractor
from mind.extractors.copilot import CopilotExtractor
from mind.extractors.opencode import OpencodeExtractor
from mind.index import Index, SourceIndex
from mind.synthesizer import build_prompt, run_synthesis

_EXTRACTORS = {
    "claude":    ClaudeExtractor,
    "gemini":    GeminiExtractor,
    "cursor":    CursorExtractor,
    "codex":     CodexExtractor,
    "copilot":   CopilotExtractor,
    "opencode":  OpencodeExtractor,
}

# extractors that need project_path passed to extract_new
_NEEDS_PROJECT_PATH = {"copilot", "codex", "opencode"}


def run_sync(cfg: Config, mind_dir: Path, project_path: str) -> None:
    index = Index.load(mind_dir)
    cache_dir = mind_dir / "facets"
    all_facets: list[dict] = []
    updated_sources: dict[str, SourceIndex] = dict(index.sources)
    total_messages = 0

    for tool_name in cfg.enabled_tools:
        extractor_cls = _EXTRACTORS.get(tool_name)
        if not extractor_cls:
            continue

        extractor = extractor_cls()
        transcript_dir = extractor.find_project_path(project_path)
        if not transcript_dir:
            continue

        known = index.known_files(tool_name)
        print(f"  {tool_name}  scanning...", end="\r", flush=True)
        try:
            if tool_name in _NEEDS_PROJECT_PATH:
                messages, new_files = extractor.extract_new(
                    transcript_dir, known, cfg.max_message_chars, project_path=project_path
                )
            else:
                messages, new_files = extractor.extract_new(transcript_dir, known, cfg.max_message_chars)
        except Exception as e:
            print(f"  {tool_name}  warning: {e}" + " " * 20)
            continue

        if not messages:
            print(f"  {tool_name}  up to date" + " " * 20)
            continue

        new_file_count = len(new_files) - len(known)
        print(f"  {tool_name}  {len(messages)} messages · {new_file_count} new files")
        facets = load_or_extract(project_path, tool_name, new_files, messages, cfg, cache_dir)
        all_facets.append(facets)
        updated_sources[tool_name] = SourceIndex(path=transcript_dir, files=new_files)
        total_messages += len(messages)

    if not all_facets:
        print("✓ mind up to date")
        return

    aggregated = aggregate_facets(all_facets)
    current_mind = (mind_dir / "mind.md").read_text() if (mind_dir / "mind.md").exists() else ""
    prompt = build_prompt(cfg, aggregated, current_mind)
    run_synthesis(cfg, prompt, mind_dir)

    index.sources = updated_sources
    index.sync_count += 1
    index.last_sync = datetime.now(tz=timezone.utc).isoformat()
    index.write(mind_dir)

    print(f"✓ mind synced — {total_messages} messages processed")
