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


def build_prompt(cfg: Config, facets: dict[str, list[str]], current_mind: str) -> str:
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
    import os
    cmd_template = cfg.llm_commands.get(cfg.llm_provider, "claude -p {prompt}")
    cmd_str = cmd_template.replace("{prompt}", shlex.quote(prompt))
    cmd = shlex.split(cmd_str)
    print(f"  synthesizing with {cfg.llm_provider}...")
    mind_file = mind_dir / "mind.md"
    mtime_before = mind_file.stat().st_mtime if mind_file.exists() else 0
    chunks: list[str] = []
    env = {**os.environ, "CLAUDE_MIND_RUN": "1"}
    with subprocess.Popen(cmd, cwd=mind_dir.parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env) as proc:
        for chunk in proc.stdout:
            print(chunk, end="", flush=True)
            chunks.append(chunk)
        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"LLM synthesis failed (exit {proc.returncode}): {err}")
    print()
    mtime_after = mind_file.stat().st_mtime if mind_file.exists() else 0
    if mtime_after <= mtime_before:
        mind_file.write_text("".join(chunks))
