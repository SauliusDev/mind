from __future__ import annotations
from pathlib import Path
from unittest.mock import patch

from mind.evolve import build_evolve_prompt, _parse_report_files, _parse_claude_md_addition, run_evolve
from mind.config import Config


def _make_config(tmp_path: Path) -> Config:
    (tmp_path / "_mind").mkdir(exist_ok=True)
    (tmp_path / "_mind" / "mind.toml").write_text("""
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
    mind_dir.mkdir(exist_ok=True)
    empty_facets = {k: [] for k in SAMPLE_FACETS}
    with patch("mind.evolve.load_or_extract", return_value=empty_facets):
        with patch("mind.evolve.aggregate_facets", return_value=empty_facets):
            with patch("mind.evolve._run_synthesis_capture", return_value=SAMPLE_REPORT):
                with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=None):
                    run_evolve(cfg, tmp_path, mind_dir, write=False)
    assert (mind_dir / "evolve-report.md").exists()
    assert "## Rules" in (mind_dir / "evolve-report.md").read_text()


def test_run_evolve_write_creates_rule_files(tmp_path):
    cfg = _make_config(tmp_path)
    mind_dir = tmp_path / "_mind"
    mind_dir.mkdir(exist_ok=True)
    empty_facets = {k: [] for k in SAMPLE_FACETS}
    with patch("mind.evolve.load_or_extract", return_value=empty_facets):
        with patch("mind.evolve.aggregate_facets", return_value=empty_facets):
            with patch("mind.evolve._run_synthesis_capture", return_value=SAMPLE_REPORT):
                with patch("mind.extractors.claude.ClaudeExtractor.find_project_path", return_value=None):
                    run_evolve(cfg, tmp_path, mind_dir, write=True)
    assert (tmp_path / ".claude" / "rules" / "no-httpx.md").exists()
    assert (tmp_path / ".claude" / "skills" / "data-pipeline.md").exists()
