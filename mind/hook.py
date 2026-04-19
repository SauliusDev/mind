from __future__ import annotations
import stat
from pathlib import Path

HOOK_MARKER = "# mind managed block"
_HOOK_BLOCK = f"""\
{HOOK_MARKER} — do not edit
(cd "$(git rev-parse --show-toplevel)" && mind sync) &
disown
# end mind managed block
"""


def install_hook(project_path: Path) -> None:
    hook_path = project_path / ".git" / "hooks" / "post-commit"

    if hook_path.exists():
        content = hook_path.read_text()
        if HOOK_MARKER in content:
            return  # already installed
        hook_path.write_text(content.rstrip("\n") + "\n\n" + _HOOK_BLOCK)
    else:
        hook_path.write_text("#!/usr/bin/env bash\n\n" + _HOOK_BLOCK)

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
