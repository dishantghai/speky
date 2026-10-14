"""Housekeeping: `speky cleanup` and `speky review`.

cleanup — finds clutter agents leave behind (`*_SPEC.md`, `IMPLEMENTATION_COMPLETE.md`, `temp_*.md`, stray
markdown in `.speky/`) and moves it to `.speky/backups/cleanup-<time>/` (recoverable). SPEKY's own files
are never touched. Dry run unless `--apply`.

review — re-checks completed work: is there evidence for every requirement, do the files the evidence
names still exist, and do the tests still pass on today's code? Items completed without evidence (for
example under v2) are reported so they can be verified or have their gaps filed.
"""
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List

from . import markdown as md
from .items import DONE_STATUSES, Project
from .verification import load_evidence

CLUTTER_PATTERNS = ["*_SPEC.md", "IMPLEMENTATION_COMPLETE.md", "implementation_notes.md", "analysis_*.md",
                    "temp_*.md", "*.tmp.md", "*_SETUP.md"]
SPEKY_FILES = {"speky.yaml", "config.yaml", "ids.json", "checkpoint.json", "backlog.json", "backlog.md",
               "decisions.md", "memory.md", "state.md", "log.md", "owner.md", "tasks.md", "roadmap.md",
               "glossary.md"}
KEEP_ROOT = {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md",
             "LICENSE.md", "SECURITY.md", "CODE_OF_CONDUCT.md"}


def find_clutter(project: Project) -> List[Path]:
    found = []
    for pattern in CLUTTER_PATTERNS:
        for f in project.root.glob(pattern):
            if f.is_file() and f.name not in KEEP_ROOT:
                found.append(f)
    for f in project.dir.iterdir() if project.dir.is_dir() else []:
        if f.is_file() and f.name not in SPEKY_FILES and (f.suffix == ".md" or
                                                         any(f.match(p) for p in CLUTTER_PATTERNS)):
            found.append(f)
    temp = project.dir / "temp"
    if temp.is_dir():
        found += [p for p in temp.rglob("*") if p.is_file()]
    return sorted(set(found))


def cleanup(project: Project, apply: bool = False) -> dict:
    clutter = find_clutter(project)
    rel = [str(p.relative_to(project.root)) for p in clutter]
    if not apply or not clutter:
        return {"clutter": rel, "moved_to": None, "applied": False}
    dest = project.dir / "backups" / f"cleanup-{datetime.now():%Y%m%d-%H%M%S}"
    dest.mkdir(parents=True)
    gi = project.dir / "backups" / ".gitignore"
    if not gi.exists():
        gi.write_text("# local safety copies; git history already has the originals\n*\n")
    for p in clutter:
        target = dest / p.relative_to(project.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(target))
    return {"clutter": rel, "moved_to": str(dest.relative_to(project.root)), "applied": True}


_PATH_RE = re.compile(r"([\w./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|kt|swift|dart|rb|php|cs|md))(?:::|:\d|\b)")


def review(project: Project, ref: str = None, run_tests: bool = True) -> dict:
    items = [project.find(ref)] if ref else [i for i in project.items() if i.info()["status"] in DONE_STATUSES]
    cmd = project.config.get("verify_command") or ""
    tests = None
    if run_tests and cmd:
        proc = subprocess.run(cmd, shell=True, cwd=project.root, capture_output=True, text=True)
        tests = {"command": cmd, "exit_code": proc.returncode, "passed": proc.returncode == 0,
                 "output_tail": "\n".join((proc.stdout + proc.stderr).splitlines()[-12:])}
    report = []
    for item in items:
        reqs = md.parse_requirements(md.strip_comments(item.read_doc()))
        evidence = load_evidence(item)
        missing = [r.id for r in reqs if evidence.get(r.id, {}).get("status") != "met"]
        gone = []
        for rid, ev in evidence.items():
            for m in _PATH_RE.finditer(ev.get("evidence", "")):
                path = m.group(1).split("::")[0]
                if "/" in path and not (project.root / path).exists():
                    gone.append(f"{rid}: {path}")
        if not reqs:
            verdict = "no_requirements"
        elif not evidence:
            verdict = "no_evidence"
        elif missing or gone:
            verdict = "incomplete"
        else:
            verdict = "verified"
        report.append({"id": item.id, "title": item.info()["title"], "status": item.info()["status"],
                       "verdict": verdict, "requirements_without_evidence": missing, "evidence_gone": gone})
    counts = {}
    for r in report:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {"items": report, "counts": counts, "tests": tests,
            "next": ("For items that are not `verified`: check the code against the requirements "
                     "(speky-verify skill, review step) and either record evidence "
                     "(`speky evidence`) or file the gaps (`speky new story ... --discovered-from <id>`).")}
