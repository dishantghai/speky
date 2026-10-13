"""Git helpers. Everything degrades to NO_VCS when the project is not a git repository."""
import hashlib
import subprocess
from pathlib import Path
from typing import List, Optional

NO_VCS = "NO_VCS"


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    except FileNotFoundError:
        return None
    return result.stdout if result.returncode == 0 else None


def head(root: Path) -> str:
    out = _git(root, "rev-parse", "HEAD")
    return out.strip() if out else NO_VCS


def is_repo(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-inside-work-tree") is not None


def changed_files(root: Path, base: str) -> List[str]:
    """Files changed since `base`: committed, staged, unstaged and untracked (excluding .speky/)."""
    if base in (None, NO_VCS) or not is_repo(root):
        return []
    files = set()
    committed = _git(root, "diff", "--name-only", f"{base}..HEAD")
    files.update((committed or "").splitlines())
    working = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    for line in (working or "").splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.add(path.strip('"'))
    return sorted(f for f in files if f and not f.startswith(".speky/"))


def tree_fingerprint(root: Path) -> str:
    """Identifies the current code state: HEAD plus the uncommitted diff (excluding .speky/)."""
    if not is_repo(root):
        return NO_VCS
    diff = _git(root, "diff", "HEAD", "--", ".", ":(exclude).speky") or ""
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "--", ".", ":(exclude).speky") or ""
    digest = hashlib.sha1((diff + untracked).encode()).hexdigest()[:12]
    return f"{head(root)[:12]}+{digest}"
