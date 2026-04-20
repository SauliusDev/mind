from __future__ import annotations
import subprocess
import shlex
from pathlib import Path

from mind.config import Config
from mind.extractors.base import Message

_PROMPT_TEMPLATE = """\
You are updating _mind/mind.md for project: {project_name}.

This file is injected into every AI coding session as a context primer.
Write for an LLM reader. Dense, precise, no fluff. No architecture trees.

## New conversation content since last sync:
{conversation}

## Current mind.md:
{current_mind}

## Instructions:
Update mind.md. Rules:
- behavior: extract user corrections/redirections as new rules. NEVER delete existing rules.
- context: rewrite from scratch — current project state in 2-3 sentences
- active: update task statuses based on conversation evidence
- decisions: add new decisions, drop ones explicitly superseded
- lessons: add new items (✓ worked / ✗ failed), merge duplicates, never repeat
- history: append one compressed entry for this sync (date + what changed)
- Stay within {mind_max_lines} lines total. Compress oldest history first if over budget.

Write the complete updated mind.md now.
"""


def build_prompt(
    cfg: Config,
    messages: list[Message],
    current_mind: str,
) -> str:
    if messages:
        conversation = "\n\n".join(m.format(cfg.max_message_chars) for m in messages)
    else:
        conversation = "(no new conversation since last sync)"

    return _PROMPT_TEMPLATE.format(
        project_name=cfg.project_name,
        conversation=conversation,
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
