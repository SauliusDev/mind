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
