from __future__ import annotations
import re
import shlex
import subprocess
from pathlib import Path

from mind.compressor import aggregate_facets, load_or_extract
from mind.config import Config
from mind.extractors.claude import ClaudeExtractor
from mind.extractors.codex import CodexExtractor
from mind.extractors.copilot import CopilotExtractor
from mind.extractors.cursor import CursorExtractor
from mind.extractors.gemini import GeminiExtractor
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


def build_evolve_prompt(cfg: Config, facets: dict[str, list[str]], existing_claude: str) -> str:
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
        print("  appended to .claude/CLAUDE.md")


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
