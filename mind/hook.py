from __future__ import annotations
import shutil
import stat
from pathlib import Path

HOOK_MARKER = "# mind managed block"


def _make_hook_block() -> str:
    mind_bin = shutil.which("mind") or "mind"
    return f"""\
{HOOK_MARKER} — do not edit
(cd "$(git rev-parse --show-toplevel)" && {mind_bin} sync) &
disown
# end mind managed block
"""


def install_hook(project_path: Path) -> None:
    hook_path = project_path / ".git" / "hooks" / "post-commit"
    hook_block = _make_hook_block()

    if hook_path.exists():
        content = hook_path.read_text()
        if HOOK_MARKER in content:
            return  # already installed
        hook_path.write_text(content.rstrip("\n") + "\n\n" + hook_block)
    else:
        hook_path.write_text("#!/usr/bin/env bash\n\n" + hook_block)

    current = hook_path.stat().st_mode
    hook_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def uninstall_hook(project_path: Path) -> None:
    hook_path = project_path / ".git" / "hooks" / "post-commit"
    if not hook_path.exists():
        return

    lines = hook_path.read_text().splitlines(keepends=True)
    result = []
    inside = False
    for line in lines:
        if HOOK_MARKER in line and "do not edit" in line:
            inside = True
            continue
        if inside and "end mind managed block" in line:
            inside = False
            continue
        if not inside:
            result.append(line)

    hook_path.write_text("".join(result))
