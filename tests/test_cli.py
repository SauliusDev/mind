from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch
from mind.cli import main
import subprocess


def _git_init(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)


def test_init_creates_mind_dir(tmp_path):
    _git_init(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--project-path", str(tmp_path), "--name", "test", "--llm", "claude"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "_mind").exists()
    assert (tmp_path / "_mind" / "mind.md").exists()
    assert (tmp_path / "_mind" / "index.yaml").exists()
    assert (tmp_path / "_mind" / "mind.toml").exists()

def test_init_prints_mind_md_reminder(tmp_path):
    _git_init(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--project-path", str(tmp_path), "--name", "test", "--llm", "claude"])
    assert result.exit_code == 0, result.output
    assert "Read _mind/mind.md before every conversation" in result.output
    assert "add this line to your agent instructions file" in result.output

def test_init_installs_hook(tmp_path):
    _git_init(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init", "--project-path", str(tmp_path), "--name", "test", "--llm", "claude"])
    assert (tmp_path / ".git" / "hooks" / "post-commit").exists()

def test_sync_command(tmp_path):
    _git_init(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init", "--project-path", str(tmp_path), "--name", "test", "--llm", "claude"])
    with patch("mind.cli.run_sync") as mock:
        result = runner.invoke(main, ["sync", "--project-path", str(tmp_path)])
        assert result.exit_code == 0
        assert mock.called

def test_status_command(tmp_path):
    _git_init(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init", "--project-path", str(tmp_path), "--name", "test", "--llm", "claude"])
    result = runner.invoke(main, ["status", "--project-path", str(tmp_path)])
    assert result.exit_code == 0
    assert "test" in result.output


def test_status_claude_counts_per_file_cache(tmp_path, monkeypatch):
    _git_init(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init", "--project-path", str(tmp_path), "--name", "p", "--llm", "claude"])

    # Fake claude transcript dir with 5 sessions
    tdir = tmp_path / "claude_proj"
    tdir.mkdir()
    for i in range(5):
        (tdir / f"s{i}.jsonl").write_text('{"type":"user","message":{"role":"user","content":"x"}}\n')
    monkeypatch.setattr(
        "mind.extractors.claude.ClaudeExtractor.find_project_path",
        lambda self, p: str(tdir),
    )
    # Per-file cache: 3 of the 5 conversations processed
    cache_dir = tmp_path / "_mind" / "facets" / "claude"
    cache_dir.mkdir(parents=True)
    for i in range(3):
        (cache_dir / f"s{i}.json").write_text("{}")

    result = runner.invoke(main, ["status", "--project-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    # claude line must reflect the per-file cache, NOT "0 synced"
    claude_line = next(l for l in result.output.splitlines() if l.strip().startswith("claude"))
    assert "3 synced" in claude_line
    assert "2 queued" in claude_line
    assert "0 synced" not in claude_line


def test_status_claude_zero_cache_shows_zero_not_crash(tmp_path, monkeypatch):
    _git_init(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init", "--project-path", str(tmp_path), "--name", "p", "--llm", "claude"])
    tdir = tmp_path / "claude_proj"
    tdir.mkdir()
    (tdir / "s0.jsonl").write_text('{"type":"user","message":{"role":"user","content":"x"}}\n')
    monkeypatch.setattr(
        "mind.extractors.claude.ClaudeExtractor.find_project_path",
        lambda self, p: str(tdir),
    )
    result = runner.invoke(main, ["status", "--project-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    claude_line = next(l for l in result.output.splitlines() if l.strip().startswith("claude"))
    assert "0 synced" in claude_line
    assert "1 queued" in claude_line
