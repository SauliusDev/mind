from __future__ import annotations
import hashlib
import json
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from mind.config import Config
from mind.extractors.base import Message

_FACET_PROMPT_TEMPLATE = """\
Extract structured insights from this AI coding session transcript chunk.

## Transcript:
{conversation}

## Instructions:
Output ONLY a JSON object with these keys (all are string arrays, use [] if nothing relevant):
{{
  "corrections": [things the user had to correct or re-ask the AI about],
  "workflows":   [repeated multi-step patterns the user invoked],
  "decisions":   [technical or architectural decisions made],
  "friction":    [where the AI missed the mark, over-changed things, or misunderstood],
  "lessons":     [things learned that worked (prefix ✓) or failed (prefix ✗)],
  "prompting_gaps": [cases where vague user prompting caused confusion or re-work]
}}

Output ONLY the JSON object. No explanation, no markdown fences.
"""

_EMPTY_FACETS: dict[str, list] = {
    "corrections": [],
    "workflows": [],
    "decisions": [],
    "friction": [],
    "lessons": [],
    "prompting_gaps": [],
}


def _cache_key(project_path: str, tool: str, files: dict[str, str]) -> str:
    sorted_files = sorted(files.items())
    raw = f"{project_path}|{tool}|{json.dumps(sorted_files)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _run_haiku(cfg: Config, prompt: str) -> str:
    import os
    cmd_str = cfg.haiku_command.replace("{prompt}", shlex.quote(prompt))
    cmd = shlex.split(cmd_str)
    env = {**os.environ, "CLAUDE_MIND_RUN": "1"}
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Haiku compression failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _process_chunk(chunk: list[Message], cfg: Config) -> dict | None:
    conversation = "\n\n".join(m.format(cfg.max_message_chars) for m in chunk)
    prompt = _FACET_PROMPT_TEMPLATE.format(conversation=conversation)
    try:
        raw = _run_haiku(cfg, prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except (json.JSONDecodeError, RuntimeError):
        return None


def extract_facets(messages: list[Message], cfg: Config) -> dict:
    chunks = [
        messages[i : i + cfg.chunk_size]
        for i in range(0, len(messages), cfg.chunk_size)
    ]
    total = len(chunks)
    merged: dict[str, list] = {k: [] for k in _EMPTY_FACETS}
    completed = 0
    print(f"  extracting {total} chunk{'s' if total != 1 else ''}  0/{total}", end="", flush=True)
    with ThreadPoolExecutor(max_workers=total) as executor:
        futures = {executor.submit(_process_chunk, chunk, cfg): i for i, chunk in enumerate(chunks, 1)}
        for future in as_completed(futures):
            completed += 1
            i = futures[future]
            chunk = chunks[i - 1]
            print(f"\r  extracting chunk {i}/{total} ({len(chunk)} messages)...", end="", flush=True)
            facet = future.result()
            if facet is None:
                continue
            for key in merged:
                merged[key].extend(facet.get(key, []))
    print()
    return merged


def aggregate_facets(all_facets: list[dict]) -> dict:
    merged: dict[str, list] = {k: [] for k in _EMPTY_FACETS}
    for facets in all_facets:
        for key in merged:
            merged[key].extend(facets.get(key, []))
    for key in merged:
        merged[key] = list(dict.fromkeys(merged[key]))
    return merged


def load_or_extract(
    project_path: str,
    tool: str,
    files: dict[str, str],
    messages: list[Message],
    cfg: Config,
    cache_dir: Path,
) -> dict:
    key = _cache_key(project_path, tool, files)
    cache_file = cache_dir / f"{key}.json"
    if cache_file.exists():
        print("  cache hit — skipping extraction", flush=True)
        return json.loads(cache_file.read_text())
    facets = extract_facets(messages, cfg)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(facets))
    return facets
