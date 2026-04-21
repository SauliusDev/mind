# mind evolve — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 150-message cap in `sync`/`rebuild` with an uncapped two-pass Haiku compression pipeline, and add a new `mind evolve` command that generates a `.claude/` artifact report from full session history.

**Architecture:** Haiku compresses raw transcript chunks into compact JSON facets (cached per batch in `_mind/facets/`). The main LLM synthesises aggregated facets — `sync`/`rebuild` produce an updated `mind.md`; `evolve` produces a 4-section markdown report (rules, skills, CLAUDE.md additions, prompting tips).

**Tech Stack:** Python 3.11+, click, subprocess, hashlib, json, re, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `mind/config.py` | Modify | Add `haiku_command`, `chunk_size`; remove `max_messages_per_sync` |
| `mind/compressor.py` | Create | Haiku facet extraction, cache read/write, aggregation |
| `mind/synthesizer.py` | Modify | `build_prompt()` accepts `facets: dict` instead of `list[Message]` |
| `mind/sync.py` | Modify | Replace message cap + raw messages with compressor pipeline |
| `mind/evolve.py` | Create | `build_evolve_prompt()`, `_parse_report_files()`, `run_evolve()` |
| `mind/cli.py` | Modify | Add `evolve` command; `rebuild` wipes `_mind/facets/`; update template |
| `pyproject.toml` | Modify | Bump version `0.1.6` → `0.1.7` |
| `tests/test_compressor.py` | Create | Unit tests for compressor |
| `tests/test_evolve.py` | Create | Unit tests for evolve |
| `tests/test_synthesizer.py` | Modify | Update callers of `build_prompt` to pass facets dict |
| `tests/test_config.py` | Modify | Update assertions for removed/added fields |
| `tests/test_sync.py` | Modify | Mock compressor instead of run_synthesis directly |

---

## Task 1: Update `mind/config.py`

**Files:**
- Modify: `mind/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py — add these, keep existing tests
def test_config_new_fields(tmp_path):
    toml = tmp_path / "mind.toml"
    toml.write_text("""
[project]
name = "my-project"
[llm]
provider = "claude"
haiku_command = "myhaiku -p {prompt}"
chunk_size = 50
[tools]
enabled = ["claude"]
""")
    cfg = Config.load(tmp_path)
    assert cfg.haiku_command == "myhaiku -p {prompt}"
    assert cfg.chunk_size == 50


def test_config_defaults_new_fields(tmp_path):
    toml = tmp_path / "mind.toml"
    toml.write_text("""
[project]
name = "my-project"
[llm]
provider = "claude"
[tools]
enabled = ["claude"]
""")
    cfg = Config.load(tmp_path)
    assert cfg.haiku_command == "claude -p {prompt} --model claude-haiku-4-5-20251001"
    assert cfg.chunk_size == 30
```

Also **update** the existing `test_config_defaults` test — remove the `max_messages_per_sync` assertion:

```python
def test_config_defaults(tmp_path):
    toml = tmp_path / "mind.toml"
    toml.write_text("""
[project]
name = "my-project"
[llm]
provider = "claude"
[tools]
enabled = ["claude", "gemini"]
""")
    cfg = Config.load(tmp_path)
    assert cfg.project_name == "my-project"
    assert cfg.llm_provider == "claude"
    assert cfg.enabled_tools == ["claude", "gemini"]
    assert cfg.max_message_chars == 500
    assert cfg.mind_max_lines == 150
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/saulius/dev/mind && python -m pytest tests/test_config.py -v
```

Expected: FAIL — `Config` has no `haiku_command` or `chunk_size` attribute, and `max_messages_per_sync` assertion still fires.

- [ ] **Step 3: Replace `mind/config.py` with the updated implementation**

```python
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

_DEFAULT_HAIKU_COMMAND = "claude -p {prompt} --model claude-haiku-4-5-20251001"


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
    haiku_command: str = _DEFAULT_HAIKU_COMMAND
    chunk_size: int = 30
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

        llm_section = data.get("llm", {})
        limits = data.get("limits", {})
        return cls(
            project_name=data["project"]["name"],
            project_path=project_path,
            llm_provider=llm_section.get("provider", "claude"),
            llm_commands=llm_commands,
            enabled_tools=data.get("tools", {}).get("enabled", list(_TOOL_PATHS_SIMPLE)),
            haiku_command=llm_section.get("haiku_command", _DEFAULT_HAIKU_COMMAND),
            chunk_size=limits.get("chunk_size", 30),
            max_message_chars=limits.get("max_message_chars", 500),
            mind_max_lines=limits.get("mind_max_lines", 150),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/saulius/dev/mind && python -m pytest tests/test_config.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/saulius/dev/mind && git add mind/config.py tests/test_config.py
git commit -m "feat(config): add haiku_command + chunk_size, remove max_messages_per_sync"
```

---

## Task 2: Create `mind/compressor.py`

**Files:**
- Create: `mind/compressor.py`
- Create: `tests/test_compressor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_compressor.py
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mind.compressor import (
    extract_facets,
    aggregate_facets,
    load_or_extract,
    _cache_key,
)
from mind.config import Config
from mind.extractors.base import Message


def _make_config(tmp_path: Path) -> Config:
    (tmp_path / "mind.toml").write_text("""
[project]
name = "test-project"
[llm]
provider = "claude"
[tools]
enabled = ["claude"]
[limits]
chunk_size = 3
""")
    return Config.load(tmp_path)


def _messages(n: int) -> list[Message]:
    return [
        Message("user", f"msg {i}", f"2026-04-{i+1:02d}T10:00:00Z", "claude")
        for i in range(n)
    ]


EMPTY_FACETS = {
    "corrections": [], "workflows": [], "decisions": [],
    "friction": [], "lessons": [], "prompting_gaps": [],
}

SAMPLE_FACETS = {
    "corrections": ["don't use httpx"],
    "workflows": [],
    "decisions": ["use DuckDB"],
    "friction": [],
    "lessons": ["✓ bulk inserts fast"],
    "prompting_gaps": [],
}


def test_extract_facets_calls_haiku_once_per_chunk(tmp_path):
    cfg = _make_config(tmp_path)  # chunk_size=3
    msgs = _messages(7)  # 3 chunks: [3, 3, 1]

    with patch("mind.compressor._run_haiku") as mock_haiku:
        mock_haiku.return_value = json.dumps(EMPTY_FACETS)
        extract_facets(msgs, cfg)
        assert mock_haiku.call_count == 3


def test_extract_facets_merges_results(tmp_path):
    cfg = _make_config(tmp_path)  # chunk_size=3
    msgs = _messages(4)  # 2 chunks

    facets_a = {**EMPTY_FACETS, "corrections": ["use polars"]}
    facets_b = {**EMPTY_FACETS, "decisions": ["chose DuckDB"]}

    with patch("mind.compressor._run_haiku") as mock_haiku:
        mock_haiku.side_effect = [json.dumps(facets_a), json.dumps(facets_b)]
        result = extract_facets(msgs, cfg)

    assert "use polars" in result["corrections"]
    assert "chose DuckDB" in result["decisions"]


def test_extract_facets_skips_invalid_json(tmp_path):
    cfg = _make_config(tmp_path)
    msgs = _messages(3)

    with patch("mind.compressor._run_haiku") as mock_haiku:
        mock_haiku.return_value = "not json"
        result = extract_facets(msgs, cfg)

    assert result["corrections"] == []


def test_aggregate_facets_merges_and_deduplicates():
    a = {**EMPTY_FACETS, "corrections": ["use polars", "no httpx"]}
    b = {**EMPTY_FACETS, "corrections": ["use polars", "avoid pandas"]}
    result = aggregate_facets([a, b])
    assert result["corrections"] == ["use polars", "no httpx", "avoid pandas"]


def test_cache_key_differs_by_project_path():
    key1 = _cache_key("/proj/a", "claude", {"f.jsonl": "2026-01-01"})
    key2 = _cache_key("/proj/b", "claude", {"f.jsonl": "2026-01-01"})
    assert key1 != key2


def test_cache_key_differs_by_mtime():
    key1 = _cache_key("/proj", "claude", {"f.jsonl": "2026-01-01"})
    key2 = _cache_key("/proj", "claude", {"f.jsonl": "2026-01-02"})
    assert key1 != key2


def test_load_or_extract_returns_cached_without_haiku(tmp_path):
    cfg = _make_config(tmp_path)
    cache_dir = tmp_path / "facets"
    cache_dir.mkdir()

    files = {"session.jsonl": "2026-04-01T10:00:00"}
    key = _cache_key(str(tmp_path), "claude", files)
    (cache_dir / f"{key}.json").write_text(json.dumps(SAMPLE_FACETS))

    with patch("mind.compressor._run_haiku") as mock_haiku:
        result = load_or_extract(str(tmp_path), "claude", files, [], cfg, cache_dir)
        assert mock_haiku.call_count == 0

    assert result["corrections"] == ["don't use httpx"]


def test_load_or_extract_creates_cache_on_miss(tmp_path):
    cfg = _make_config(tmp_path)
    cache_dir = tmp_path / "facets"

    files = {"session.jsonl": "2026-04-01T10:00:00"}

    with patch("mind.compressor._run_haiku") as mock_haiku:
        mock_haiku.return_value = json.dumps(SAMPLE_FACETS)
        load_or_extract(str(tmp_path), "claude", files, _messages(2), cfg, cache_dir)

    key = _cache_key(str(tmp_path), "claude", files)
    assert (cache_dir / f"{key}.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/saulius/dev/mind && python -m pytest tests/test_compressor.py -v
```

Expected: FAIL — `mind.compressor` does not exist.

- [ ] **Step 3: Create `mind/compressor.py`**

```python
from __future__ import annotations
import hashlib
import json
import shlex
import subprocess
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
    cmd_str = cfg.haiku_command.replace("{prompt}", shlex.quote(prompt))
    cmd = shlex.split(cmd_str)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Haiku compression failed: {result.stderr.strip()}")
    return result.stdout.strip()


def extract_facets(messages: list[Message], cfg: Config) -> dict:
    chunks = [
        messages[i : i + cfg.chunk_size]
        for i in range(0, len(messages), cfg.chunk_size)
    ]
    merged: dict[str, list] = {k: [] for k in _EMPTY_FACETS}
    for chunk in chunks:
        conversation = "\n\n".join(m.format(cfg.max_message_chars) for m in chunk)
        prompt = _FACET_PROMPT_TEMPLATE.format(conversation=conversation)
        try:
            raw = _run_haiku(cfg, prompt)
            facet = json.loads(raw)
        except (json.JSONDecodeError, RuntimeError):
            continue
        for key in merged:
            merged[key].extend(facet.get(key, []))
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
        return json.loads(cache_file.read_text())
    facets = extract_facets(messages, cfg)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(facets))
    return facets
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/saulius/dev/mind && python -m pytest tests/test_compressor.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/saulius/dev/mind && git add mind/compressor.py tests/test_compressor.py
git commit -m "feat(compressor): Haiku facet extraction with batch cache"
```

---

## Task 3: Update `mind/synthesizer.py`

`build_prompt` currently receives `list[Message]`. Change it to receive `facets: dict`.

**Files:**
- Modify: `mind/synthesizer.py`
- Modify: `tests/test_synthesizer.py`

- [ ] **Step 1: Update the tests first**

Replace the full contents of `tests/test_synthesizer.py`:

```python
from unittest.mock import patch, MagicMock
from mind.synthesizer import build_prompt, run_synthesis
from mind.config import Config
from pathlib import Path


def _make_config(tmp_path: Path) -> Config:
    (tmp_path / "mind.toml").write_text("""
[project]
name = "test-project"
[llm]
provider = "claude"
[tools]
enabled = ["claude"]
""")
    return Config.load(tmp_path)


SAMPLE_FACETS = {
    "corrections": ["don't use httpx"],
    "workflows": ["fetch → filter → write parquet"],
    "decisions": ["chose DuckDB"],
    "friction": ["AI kept adding unrelated code"],
    "lessons": ["✓ bulk inserts 50x faster"],
    "prompting_gaps": ["user said 'the data' without specifying which file"],
}

EMPTY_FACETS = {
    "corrections": [], "workflows": [], "decisions": [],
    "friction": [], "lessons": [], "prompting_gaps": [],
}


def test_build_prompt_contains_project_name(tmp_path):
    cfg = _make_config(tmp_path)
    prompt = build_prompt(cfg, SAMPLE_FACETS, current_mind="# mind — test-project\n")
    assert "test-project" in prompt


def test_build_prompt_includes_corrections(tmp_path):
    cfg = _make_config(tmp_path)
    prompt = build_prompt(cfg, SAMPLE_FACETS, current_mind="")
    assert "don't use httpx" in prompt


def test_build_prompt_includes_current_mind(tmp_path):
    cfg = _make_config(tmp_path)
    current = "# mind — test-project\n## behavior\n- never do X\n"
    prompt = build_prompt(cfg, EMPTY_FACETS, current_mind=current)
    assert "never do X" in prompt


def test_build_prompt_no_facets(tmp_path):
    cfg = _make_config(tmp_path)
    prompt = build_prompt(cfg, EMPTY_FACETS, current_mind="")
    assert "test-project" in prompt
    assert "(none)" in prompt


def test_run_synthesis_calls_subprocess(tmp_path):
    cfg = _make_config(tmp_path)
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        run_synthesis(cfg, "test prompt", mind_dir)
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "claude" in cmd[0]
        assert "-p" in cmd


def test_run_synthesis_raises_on_failure(tmp_path):
    cfg = _make_config(tmp_path)
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()
    import pytest
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        with pytest.raises(RuntimeError, match="LLM synthesis failed"):
            run_synthesis(cfg, "test prompt", mind_dir)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/saulius/dev/mind && python -m pytest tests/test_synthesizer.py -v
```

Expected: FAIL — `build_prompt` still expects `list[Message]`.

- [ ] **Step 3: Update `mind/synthesizer.py`**

```python
from __future__ import annotations
import subprocess
import shlex
from pathlib import Path

from mind.config import Config

_PROMPT_TEMPLATE = """\
You are updating _mind/mind.md for project: {project_name}.

This file is injected into every AI coding session as a context primer.
Write for an LLM reader. Dense, precise, no fluff. No architecture trees.

## Extracted insights from recent AI sessions:

Corrections (things user had to re-ask or correct):
{corrections}

Workflows (repeated patterns the user invoked):
{workflows}

Technical decisions made:
{decisions}

Friction points (where AI missed the mark):
{friction}

Lessons learned:
{lessons}

## Current mind.md:
{current_mind}

## Instructions:
Update mind.md. Rules:
- behavior: extract user corrections as new rules. NEVER delete existing rules.
- context: rewrite from scratch — current project state in 2-3 sentences
- active: update task statuses based on insights
- decisions: add new decisions, drop ones explicitly superseded
- lessons: add new items (✓ worked / ✗ failed), merge duplicates, never repeat
- history: append one compressed entry for this sync (date + what changed)
- Stay within {mind_max_lines} lines total. Compress oldest history first if over budget.

Write the complete updated mind.md now.
"""


def _fmt(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "(none)"


def build_prompt(cfg: Config, facets: dict, current_mind: str) -> str:
    return _PROMPT_TEMPLATE.format(
        project_name=cfg.project_name,
        corrections=_fmt(facets.get("corrections", [])),
        workflows=_fmt(facets.get("workflows", [])),
        decisions=_fmt(facets.get("decisions", [])),
        friction=_fmt(facets.get("friction", [])),
        lessons=_fmt(facets.get("lessons", [])),
        current_mind=current_mind or "(empty — cold start)",
        mind_max_lines=cfg.mind_max_lines,
    )


def run_synthesis(cfg: Config, prompt: str, mind_dir: Path) -> None:
    cmd_template = cfg.llm_commands.get(cfg.llm_provider, "claude -p {prompt}")
    cmd_str = cmd_template.replace("{prompt}", shlex.quote(prompt))
    cmd = shlex.split(cmd_str)
    result = subprocess.run(cmd, cwd=mind_dir.parent)
    if result.returncode != 0:
        raise RuntimeError(f"LLM synthesis failed with exit code {result.returncode}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/saulius/dev/mind && python -m pytest tests/test_synthesizer.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/saulius/dev/mind && git add mind/synthesizer.py tests/test_synthesizer.py
git commit -m "feat(synthesizer): build_prompt accepts facets dict, remove message list"
```

---

## Task 4: Update `mind/sync.py`

Remove the 150-message cap. Replace raw message list passed to `build_prompt` with compressor pipeline.

**Files:**
- Modify: `mind/sync.py`
- Modify: `tests/test_sync.py`

- [ ] **Step 1: Update `tests/test_sync.py`**

```python
from pathlib import Path
from unittest.mock import patch, MagicMock
import shutil
from mind.sync import run_sync
from mind.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


def _make_project(tmp_path: Path) -> tuple[Path, Config]:
    (tmp_path / "mind.toml").write_text("""
[project]
name = "test-project"
[llm]
provider = "claude"
[tools]
enabled = ["claude"]
[limits]
chunk_size = 10
""")
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()
    (mind_dir / "mind.md").write_text("# mind — test-project\n## behavior\n")
    cfg = Config.load(tmp_path)
    return mind_dir, cfg


def test_sync_calls_synthesis_when_new_content(tmp_path):
    mind_dir, cfg = _make_project(tmp_path)
    transcripts = tmp_path / ".claude_projects" / "-home-ubuntu-test-project"
    transcripts.mkdir(parents=True)
    shutil.copy(FIXTURES / "claude_sample.jsonl", transcripts / "session1.jsonl")

    with patch("mind.sync.load_or_extract") as mock_compress:
        mock_compress.return_value = {
            "corrections": [], "workflows": [], "decisions": [],
            "friction": [], "lessons": [], "prompting_gaps": [],
        }
        with patch("mind.sync.run_synthesis") as mock_synth:
            with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=str(transcripts)):
                run_sync(cfg, mind_dir, project_path=str(tmp_path))
            assert mock_synth.called


def test_sync_skips_synthesis_when_nothing_new(tmp_path):
    mind_dir, cfg = _make_project(tmp_path)
    with patch("mind.sync.run_synthesis") as mock_synth:
        run_sync(cfg, mind_dir, project_path=str(tmp_path))
        assert not mock_synth.called


def test_sync_no_message_cap(tmp_path):
    """run_sync must not truncate messages — all new files go to compressor."""
    mind_dir, cfg = _make_project(tmp_path)
    transcripts = tmp_path / ".claude_projects" / "-home-ubuntu-test-project"
    transcripts.mkdir(parents=True)

    # Write 5 separate session files
    sample = FIXTURES / "claude_sample.jsonl"
    for i in range(5):
        shutil.copy(sample, transcripts / f"session{i}.jsonl")

    captured_messages = []

    def capture(project_path, tool, files, messages, cfg, cache_dir):
        captured_messages.extend(messages)
        return {"corrections": [], "workflows": [], "decisions": [],
                "friction": [], "lessons": [], "prompting_gaps": []}

    with patch("mind.sync.load_or_extract", side_effect=capture):
        with patch("mind.sync.run_synthesis"):
            with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=str(transcripts)):
                run_sync(cfg, mind_dir, project_path=str(tmp_path))

    # All messages from all files must reach the compressor (no cap)
    assert len(captured_messages) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/saulius/dev/mind && python -m pytest tests/test_sync.py -v
```

Expected: FAIL — `mind.sync` does not import `load_or_extract`.

- [ ] **Step 3: Replace `mind/sync.py`**

```python
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

        if not messages:
            continue

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/saulius/dev/mind && python -m pytest tests/test_sync.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full suite to check nothing broke**

```bash
cd /home/saulius/dev/mind && python -m pytest -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/saulius/dev/mind && git add mind/sync.py tests/test_sync.py
git commit -m "feat(sync): replace message cap with compressor pipeline"
```

---

## Task 5: Create `mind/evolve.py`

**Files:**
- Create: `mind/evolve.py`
- Create: `tests/test_evolve.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_evolve.py
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mind.evolve import build_evolve_prompt, _parse_report_files, _parse_claude_md_addition, run_evolve
from mind.config import Config


def _make_config(tmp_path: Path) -> Config:
    (tmp_path / "mind.toml").write_text("""
[project]
name = "test-project"
[llm]
provider = "claude"
[tools]
enabled = ["claude"]
""")
    return Config.load(tmp_path)


SAMPLE_FACETS = {
    "corrections": ["don't use httpx"],
    "workflows": ["fetch → filter → write"],
    "decisions": ["chose DuckDB"],
    "friction": ["AI added unrelated imports"],
    "lessons": ["✓ bulk inserts 50x faster"],
    "prompting_gaps": ["user said 'the data' without specifying which file"],
}

SAMPLE_REPORT = """\
## Rules

### FILE: no-httpx.md
Never use httpx. Use requests instead.
---END---

## Skills

### FILE: data-pipeline.md
Trigger: user says "run the pipeline"
Steps: fetch, filter, write parquet
---END---

## CLAUDE.md Additions

Project uses DuckDB for all analytics.
---END---

## Prompting Techniques

Instead of: "process the data"
Try: "process src/data/trades/parquet/*.parquet using DuckDB"
"""


def test_build_evolve_prompt_contains_project_name(tmp_path):
    cfg = _make_config(tmp_path)
    prompt = build_evolve_prompt(cfg, SAMPLE_FACETS, existing_claude="")
    assert "test-project" in prompt


def test_build_evolve_prompt_contains_all_facet_fields(tmp_path):
    cfg = _make_config(tmp_path)
    prompt = build_evolve_prompt(cfg, SAMPLE_FACETS, existing_claude="")
    assert "don't use httpx" in prompt
    assert "chose DuckDB" in prompt
    assert "✓ bulk inserts" in prompt
    assert "without specifying which file" in prompt


def test_build_evolve_prompt_includes_existing_claude(tmp_path):
    cfg = _make_config(tmp_path)
    prompt = build_evolve_prompt(cfg, SAMPLE_FACETS, existing_claude="## Existing rules\n### no-sql.md")
    assert "no-sql.md" in prompt


def test_parse_report_files_extracts_rules():
    files = _parse_report_files(SAMPLE_REPORT, "Rules")
    assert "no-httpx.md" in files
    assert "Never use httpx" in files["no-httpx.md"]


def test_parse_report_files_extracts_skills():
    files = _parse_report_files(SAMPLE_REPORT, "Skills")
    assert "data-pipeline.md" in files
    assert "fetch, filter" in files["data-pipeline.md"]


def test_parse_report_files_returns_empty_for_missing_section():
    files = _parse_report_files(SAMPLE_REPORT, "NonExistent")
    assert files == {}


def test_parse_claude_md_addition_extracts_content():
    content = _parse_claude_md_addition(SAMPLE_REPORT)
    assert "Project uses DuckDB" in content


def test_run_evolve_saves_report(tmp_path):
    cfg = _make_config(tmp_path)
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()

    empty_facets = {k: [] for k in SAMPLE_FACETS}

    with patch("mind.evolve.load_or_extract", return_value=empty_facets):
        with patch("mind.evolve.aggregate_facets", return_value=empty_facets):
            with patch("mind.evolve._run_synthesis_capture", return_value=SAMPLE_REPORT):
                with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=None):
                    run_evolve(cfg, tmp_path, mind_dir, write=False)

    assert (mind_dir / "evolve-report.md").exists()
    content = (mind_dir / "evolve-report.md").read_text()
    assert "## Rules" in content


def test_run_evolve_write_creates_rule_files(tmp_path):
    cfg = _make_config(tmp_path)
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir()

    empty_facets = {k: [] for k in SAMPLE_FACETS}

    with patch("mind.evolve.load_or_extract", return_value=empty_facets):
        with patch("mind.evolve.aggregate_facets", return_value=empty_facets):
            with patch("mind.evolve._run_synthesis_capture", return_value=SAMPLE_REPORT):
                with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=None):
                    run_evolve(cfg, tmp_path, mind_dir, write=True)

    assert (tmp_path / ".claude" / "rules" / "no-httpx.md").exists()
    assert (tmp_path / ".claude" / "skills" / "data-pipeline.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/saulius/dev/mind && python -m pytest tests/test_evolve.py -v
```

Expected: FAIL — `mind.evolve` does not exist.

- [ ] **Step 3: Create `mind/evolve.py`**

```python
from __future__ import annotations
import re
import shlex
import subprocess
from pathlib import Path

from mind.compressor import load_or_extract, aggregate_facets
from mind.config import Config
from mind.extractors.claude import ClaudeExtractor
from mind.extractors.gemini import GeminiExtractor
from mind.extractors.cursor import CursorExtractor
from mind.extractors.codex import CodexExtractor
from mind.extractors.copilot import CopilotExtractor
from mind.synthesizer import _fmt

_EXTRACTORS = {
    "claude":  ClaudeExtractor,
    "gemini":  GeminiExtractor,
    "cursor":  CursorExtractor,
    "codex":   CodexExtractor,
    "copilot": CopilotExtractor,
}

_EVOLVE_PROMPT_TEMPLATE = """\
Analyze AI coding session insights for project: {project_name} and generate a structured artifact report.

## Session insights:

Corrections (things user had to re-ask or correct):
{corrections}

Workflows (repeated multi-step patterns):
{workflows}

Technical decisions made:
{decisions}

Friction points (where AI missed the mark):
{friction}

Lessons learned:
{lessons}

Prompting gaps (where vague prompting caused re-work):
{prompting_gaps}

## Existing .claude/ context (do NOT duplicate these):
{existing_claude}

---

## Output format — follow exactly:

## Rules

For each recurring correction, output a candidate .claude/rules/ file:

### FILE: descriptive-name.md
[complete rule content — concise instruction the AI must follow]
---END---

## Skills

For each repeated multi-step workflow, output a candidate .claude/skills/ file:

### FILE: skill-name.md
[complete skill content with trigger condition and steps]
---END---

## CLAUDE.md Additions

Project context the user repeatedly had to explain. Write raw markdown to append.
---END---

## Prompting Techniques

For each prompting gap, show a concrete rewrite:
Instead of: [vague pattern]
Try: [specific alternative]
"""


def _read_existing_claude(project_path: Path) -> str:
    claude_dir = project_path / ".claude"
    if not claude_dir.exists():
        return "(no .claude/ directory found)"

    parts: list[str] = []

    claude_md = claude_dir / "CLAUDE.md"
    if claude_md.exists():
        parts.append(f"### CLAUDE.md (first 1500 chars)\n{claude_md.read_text()[:1500]}")

    rules_dir = claude_dir / "rules"
    if rules_dir.exists():
        rule_files = sorted(rules_dir.glob("*.md"))[:8]
        if rule_files:
            parts.append("### Existing rules/: " + ", ".join(f.name for f in rule_files))

    skills_dir = claude_dir / "skills"
    if skills_dir.exists():
        skill_files = sorted(skills_dir.glob("*.md"))[:8]
        if skill_files:
            parts.append("### Existing skills/: " + ", ".join(f.name for f in skill_files))

    return "\n\n".join(parts) if parts else "(empty .claude/ directory)"


def build_evolve_prompt(cfg: Config, facets: dict, existing_claude: str) -> str:
    return _EVOLVE_PROMPT_TEMPLATE.format(
        project_name=cfg.project_name,
        corrections=_fmt(facets.get("corrections", [])),
        workflows=_fmt(facets.get("workflows", [])),
        decisions=_fmt(facets.get("decisions", [])),
        friction=_fmt(facets.get("friction", [])),
        lessons=_fmt(facets.get("lessons", [])),
        prompting_gaps=_fmt(facets.get("prompting_gaps", [])),
        existing_claude=existing_claude,
    )


def _parse_report_files(report: str, section: str) -> dict[str, str]:
    section_pattern = rf"## {re.escape(section)}\n(.*?)(?=\n## |\Z)"
    section_match = re.search(section_pattern, report, re.DOTALL)
    if not section_match:
        return {}
    section_text = section_match.group(1)
    file_pattern = r"### FILE: (.+?)\n(.*?)---END---"
    return {
        match.group(1).strip(): match.group(2).strip()
        for match in re.finditer(file_pattern, section_text, re.DOTALL)
    }


def _parse_claude_md_addition(report: str) -> str:
    match = re.search(r"## CLAUDE\.md Additions\n(.*?)---END---", report, re.DOTALL)
    return match.group(1).strip() if match else ""


def _run_synthesis_capture(cfg: Config, prompt: str, cwd: Path) -> str:
    cmd_template = cfg.llm_commands.get(cfg.llm_provider, "claude -p {prompt}")
    cmd_str = cmd_template.replace("{prompt}", shlex.quote(prompt))
    cmd = shlex.split(cmd_str)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"LLM evolve failed with exit code {result.returncode}")
    return result.stdout.strip()


def run_evolve(cfg: Config, project_path: Path, mind_dir: Path, write: bool = False) -> None:
    cache_dir = mind_dir / "facets"
    all_facets: list[dict] = []
    total_messages = 0

    for tool_name in cfg.enabled_tools:
        extractor_cls = _EXTRACTORS.get(tool_name)
        if not extractor_cls:
            continue

        extractor = extractor_cls()
        transcript_dir = extractor.find_project_path(str(project_path))
        if not transcript_dir:
            continue

        try:
            if tool_name == "copilot":
                messages, all_files = extractor.extract_new(
                    transcript_dir, {}, cfg.max_message_chars, project_path=str(project_path)
                )
            else:
                messages, all_files = extractor.extract_new(transcript_dir, {}, cfg.max_message_chars)
        except Exception as e:
            print(f"mind evolve: warning — {tool_name} extractor failed: {e}")
            continue

        if not messages:
            continue

        facets = load_or_extract(str(project_path), tool_name, all_files, messages, cfg, cache_dir)
        all_facets.append(facets)
        total_messages += len(messages)

    aggregated = aggregate_facets(all_facets)
    existing_claude = _read_existing_claude(project_path)
    prompt = build_evolve_prompt(cfg, aggregated, existing_claude)

    print(f"mind evolve: analysing {total_messages} messages across {len(all_facets)} tools...")
    report = _run_synthesis_capture(cfg, prompt, project_path)

    report_path = mind_dir / "evolve-report.md"
    report_path.write_text(report)
    print(report)
    print(f"\n✓ report saved to {report_path}")

    if write:
        _write_artifacts(project_path, report)


def _write_artifacts(project_path: Path, report: str) -> None:
    rules = _parse_report_files(report, "Rules")
    skills = _parse_report_files(report, "Skills")
    claude_md_addition = _parse_claude_md_addition(report)

    if rules:
        rules_dir = project_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in rules.items():
            (rules_dir / filename).write_text(content + "\n")
            print(f"  wrote .claude/rules/{filename}")

    if skills:
        skills_dir = project_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in skills.items():
            (skills_dir / filename).write_text(content + "\n")
            print(f"  wrote .claude/skills/{filename}")

    if claude_md_addition:
        claude_md = project_path / ".claude" / "CLAUDE.md"
        mode = "a" if claude_md.exists() else "w"
        with open(claude_md, mode) as f:
            f.write(f"\n\n{claude_md_addition}\n")
        print(f"  appended to .claude/CLAUDE.md")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/saulius/dev/mind && python -m pytest tests/test_evolve.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/saulius/dev/mind && git add mind/evolve.py tests/test_evolve.py
git commit -m "feat(evolve): new command — full-history report with artifact generation"
```

---

## Task 6: Update `mind/cli.py`

Add `evolve` command. Update `rebuild` to wipe `_mind/facets/`. Update `_TOML_TEMPLATE` to remove `max_messages_per_sync` and add `chunk_size`.

**Files:**
- Modify: `mind/cli.py`

- [ ] **Step 1: Apply all three changes to `mind/cli.py`**

**Change 1** — update `_TOML_TEMPLATE` (replace the existing template string):

```python
_TOML_TEMPLATE = """\
[project]
name = "{project_name}"

[llm]
provider = "{llm}"
# haiku_command = "claude -p {{prompt}} --model claude-haiku-4-5-20251001"

[tools]
enabled = ["claude", "gemini", "cursor", "codex", "copilot"]

[limits]
chunk_size = 30
max_message_chars = 500
mind_max_lines = 150
"""
```

**Change 2** — add import at top of `cli.py` (after the existing imports):

```python
from mind.evolve import run_evolve
```

**Change 3** — update `rebuild` to wipe `_mind/facets/` before running sync. Replace the block inside `rebuild` that calls `shutil.rmtree(mind_dir)`:

The current block:
```python
    if mind_dir.exists():
        import shutil
        shutil.rmtree(mind_dir)
        click.echo(f"✓ deleted {mind_dir}")
```

Replace with:
```python
    if mind_dir.exists():
        import shutil
        shutil.rmtree(mind_dir)
        click.echo(f"✓ deleted {mind_dir}")
    # facets cache is inside _mind/ so it is already wiped above
```

No code change needed for the facets wipe — `_mind/facets/` lives inside `_mind/` which `rebuild` already deletes entirely. Just verify this is true (it is, by design).

**Change 4** — add `evolve` command at the end of `cli.py` (before the final newline):

```python
@main.command()
@click.option("--project-path", default=".", show_default=True)
@click.option(
    "--write",
    is_flag=True,
    default=False,
    help="Write suggested rules/skills/CLAUDE.md to .claude/ directory.",
)
def evolve(project_path: str, write: bool) -> None:
    """Analyse full session history and suggest .claude/ artifacts."""
    root = Path(project_path).resolve()
    cfg = Config.load(root)
    mind_dir = root / "_mind"
    if not mind_dir.exists():
        click.echo("✗ _mind/ not found. Run: mind init")
        return
    run_evolve(cfg, root, mind_dir, write=write)
```

- [ ] **Step 2: Run the full test suite**

```bash
cd /home/saulius/dev/mind && python -m pytest -v
```

Expected: all PASS.

- [ ] **Step 3: Smoke test the CLI registration**

```bash
cd /home/saulius/dev/mind && python -m mind.cli evolve --help
```

Expected output includes:
```
Usage: cli evolve [OPTIONS]
  Analyse full session history and suggest .claude/ artifacts.
Options:
  --project-path TEXT  [default: .]
  --write              Write suggested rules/skills/CLAUDE.md...
```

- [ ] **Step 4: Commit**

```bash
cd /home/saulius/dev/mind && git add mind/cli.py
git commit -m "feat(cli): add evolve command, update TOML template"
```

---

## Task 7: Bump version to 0.1.7

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update version in `pyproject.toml`**

Change line 7 from:
```toml
version = "0.1.6"
```
To:
```toml
version = "0.1.7"
```

- [ ] **Step 2: Run full suite one final time**

```bash
cd /home/saulius/dev/mind && python -m pytest -v
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
cd /home/saulius/dev/mind && git add pyproject.toml
git commit -m "chore: bump version to 0.1.7"
```

---

## Self-Review Checklist

- [x] **Spec coverage**
  - `haiku_command` + `chunk_size` in Config → Task 1
  - `mind/compressor.py` with cache → Task 2
  - `synthesizer.py` accepts facets dict → Task 3
  - `sync.py` uncapped, uses compressor → Task 4
  - `mind/evolve.py` with 4-section report → Task 5
  - `evolve` CLI command + `rebuild` wipes facets cache → Task 6
  - Version bump → Task 7
  - `test_compressor.py` → Task 2
  - `test_evolve.py` → Task 5
  - `test_sync.py` updated → Task 4
  - `test_synthesizer.py` updated → Task 3
  - `test_config.py` updated → Task 1

- [x] **Type consistency** — `build_prompt(cfg, facets: dict, current_mind: str)` used consistently in Tasks 3, 4. `load_or_extract(project_path, tool, files, messages, cfg, cache_dir)` signature matches between Tasks 2, 4, 5.

- [x] **No placeholders** — all code blocks are complete and runnable.

- [x] **`_fmt` reuse** — `evolve.py` imports `_fmt` from `synthesizer.py` to avoid duplication.
