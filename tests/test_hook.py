import stat
from mind.hook import install_hook, uninstall_hook, HOOK_MARKER


def test_install_creates_hook(tmp_path):
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    install_hook(tmp_path)
    hook = git_dir / "post-commit"
    assert hook.exists()
    content = hook.read_text()
    assert "mind sync" in content
    assert HOOK_MARKER in content
    assert hook.stat().st_mode & stat.S_IXUSR


def test_install_appends_to_existing_hook(tmp_path):
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    hook = git_dir / "post-commit"
    hook.write_text("#!/usr/bin/env bash\necho existing\n")
    hook.chmod(0o755)
    install_hook(tmp_path)
    content = hook.read_text()
    assert "existing" in content
    assert "mind sync" in content


def test_install_skips_if_already_installed(tmp_path):
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    install_hook(tmp_path)
    first = (git_dir / "post-commit").read_text()
    install_hook(tmp_path)
    second = (git_dir / "post-commit").read_text()
    assert first == second


def test_uninstall_removes_mind_block(tmp_path):
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    install_hook(tmp_path)
    uninstall_hook(tmp_path)
    content = (git_dir / "post-commit").read_text()
    assert "mind sync" not in content
