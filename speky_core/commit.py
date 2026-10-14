"""`speky commit <id>`: commit a change with a message built from the item itself (no model call).

The message names the item and lists the requirements with the evidence recorded for each, the plan's
tasks and the decisions made. Staging is explicit: what the user already staged, else the files
changed since the item's base commit (likely secrets are never staged automatically), plus the item's
own `.speky/` folder. `--dry-run` shows the message and files without committing.
"""
import fnmatch
import re
import subprocess
from pathlib import Path
from typing import List

from . import journal, markdown as md, vcs
from .errors import SpekyError
from .items import Item, Project
from .verification import load_evidence

TYPE_PREFIX = {"spec": "feat", "feature": "feat", "bug": "fix", "enhancement": "feat",
               "tech_debt": "refactor", "spike": "chore"}
SECRET_PATTERNS = (".env", ".env.*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks",
                   "id_rsa*", "id_ed25519*", "id_ecdsa*", "credentials*", "*credentials.json", "secrets.*",
                   "*.secret", ".npmrc", ".pypirc", ".netrc")


def looks_like_secret(path: str) -> bool:
    name = Path(path).name.lower()
    return any(fnmatch.fnmatch(name, p) for p in SECRET_PATTERNS)


def _git(root, *args, check=False):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=check)


def message(project: Project, item: Item) -> str:
    info = item.info()
    prefix = TYPE_PREFIX.get(info["type"], "feat")
    lines = [f"{prefix}({item.id}): {info['title']}", ""]
    reqs = md.parse_requirements(md.strip_comments(item.read_doc()))
    evidence = load_evidence(item)
    if reqs:
        lines.append("Requirements:")
        for r in reqs:
            ev = evidence.get(r.id)
            lines.append(f"- {r.id} {r.title}" + (f" — {ev['status']}: {ev['evidence']}" if ev else " — no evidence"))
        lines.append("")
    plan = item.path / "plan.md"
    if plan.exists():
        tasks = [re.sub(r"^\s*-\s*\[.\]\s*", "", l).strip(" *") for l in plan.read_text().splitlines()
                 if re.match(r"^\s*-\s*\[.\]", l)]
        if tasks:
            lines.append("Implementation:")
            lines += [f"- {t}" for t in tasks[:8]]
            lines.append("")
    decisions = journal.decisions(project, item.id)
    if decisions:
        lines.append("Decisions:")
        lines += [f"- {d.split(': ', 1)[-1]}" for d in decisions[:6]]
        lines.append("")
    ver = item.load_status().get("verification") or {}
    if ver.get("command"):
        lines.append(f"Verified: `{ver['command']}` exit {ver.get('exit_code')}")
    lines.append(f"Change: {item.path.relative_to(project.root)}")
    return "\n".join(lines).rstrip() + "\n"


def files_to_commit(project: Project, item: Item, explicit: List[str] = None) -> dict:
    root = project.root
    staged = [p for p in _git(root, "diff", "--cached", "--name-only").stdout.splitlines() if p]
    item_rel = str(item.path.relative_to(root))
    if explicit:
        return {"files": list(explicit) + [item_rel], "held_back": [], "source": "explicit"}
    if staged:
        return {"files": staged + [item_rel], "held_back": [], "source": "already staged"}
    base = item.load_status().get("base_sha")
    changed = vcs.changed_files(root, base) if base and base != vcs.NO_VCS else []
    if not changed:
        changed = [l[3:] for l in _git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
                   if l[3:] and not l[3:].startswith(".speky/")]
    untracked = set(_git(root, "ls-files", "--others", "--exclude-standard").stdout.splitlines())
    held = [f for f in changed if f in untracked and looks_like_secret(f)]
    return {"files": [f for f in changed if f not in held] + [item_rel], "held_back": held,
            "source": f"changed since {base[:10]}" if base and base != vcs.NO_VCS else "working tree"}


def commit(project: Project, ref: str, files: List[str] = None, dry_run: bool = False,
           force: str = None) -> dict:
    item = project.find(ref)
    status = item.info()["status"]
    if status not in ("review", "completed", "archived") and not force:
        raise SpekyError("not_verified", f"{item.id} is {status}; commit it after `speky verify {item.id}` "
                         "passes.", f'Verify first, or `speky commit {item.id} --force "<reason>"`.')
    if not vcs.is_repo(project.root):
        raise SpekyError("not_a_repo", "This project is not a git repository.")
    msg = message(project, item)
    plan = files_to_commit(project, item, files)
    result = {"item": item.id, "message": msg, **plan}
    if dry_run:
        return {**result, "committed": False}
    # record the commit in the item before staging, so the commit leaves the tree clean
    item.update_status(committed_at=__import__("datetime").datetime.now().isoformat(timespec="seconds"))
    ignored = set()
    for f in plan["files"]:
        if _git(project.root, "check-ignore", "-q", "--", f).returncode == 0:
            ignored.add(f)
    to_add = [f for f in plan["files"] if f not in ignored]
    r = _git(project.root, "add", "-A", "--", *to_add)
    if r.returncode != 0:
        raise SpekyError("git_add_failed", r.stderr.strip()[:300])
    r = _git(project.root, "commit", "-m", msg)
    if r.returncode != 0:
        raise SpekyError("git_commit_failed", (r.stderr or r.stdout).strip()[:300],
                         "Nothing to commit, or a hook rejected it.")
    sha = _git(project.root, "rev-parse", "--short", "HEAD").stdout.strip()
    if force:
        journal.decide(project, f"Committed {item.id} before verification: {force}", "decision", item.id)
    return {**result, "committed": True, "sha": sha}
