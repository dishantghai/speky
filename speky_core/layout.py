"""Where every non-code artifact lives — the same in every SPEKY project.

Each kind of artifact has one default location. A few can be moved with `paths.<key>` in
`.speky/speky.yaml` (for example when a project's tooling already depends on `docs/adr/`); SPEKY's own
stores cannot. `speky layout` prints the effective map; `speky layout --check` reports artifacts kept
somewhere SPEKY does not know about. Code is not covered: where code goes depends on the project.
"""
import re
from pathlib import Path
from typing import Dict, List, Optional

from .items import Project

# key, default (relative to the project root), what it holds, overridable with paths.<key>
ARTIFACTS = [
    ("settings", ".speky/speky.yaml", "SPEKY settings", False),
    ("specs", ".speky/specs/<NNN-slug>/", "changes: specs (spec.md, plan.md, deltas/, findings, evidence)", False),
    ("stories", ".speky/stories/<X001-slug>/", "changes: stories (story.md, plan.md, …)", False),
    ("capabilities", ".speky/capabilities/<capability>/spec.md", "living specs: how the system behaves now", False),
    ("epics", ".speky/epics/<id-slug>/", "epics: shared docs and member stories", False),
    ("phases", ".speky/phases/<id>/manifest.yaml", "phases, their deliverables (the gate) and order", False),
    ("tasks", ".speky/backlog.json · .speky/tasks.md", "tasks W<n> (tasks.md is the readable view)", False),
    ("knowledge", ".speky/knowledge/<topic>.md", "project knowledge by topic", False),
    ("decisions", ".speky/decisions.md", "decision log (append-only)", False),
    ("adr_dir", ".speky/adr/", "architecture decision records NNNN-slug.md (template.md if present)", True),
    ("glossary", ".speky/glossary.md", "domain terms", False),
    ("owner", ".speky/owner.md", "actions only the owner can take", False),
    ("log", ".speky/log.md · .speky/state.md", "session log and where things stand", False),
    ("design_system", ".speky/design/system.md", "the design-system document (tokens, type, components)", True),
    ("design_screens", ".speky/design/screens/<screen-id>/", "screen designs, one folder per screen ID", True),
    ("design_reviews", ".speky/design/reviews/", "design and UX reviews", True),
    ("imports", ".speky/imports/<name>/", "imported documents and prototype code (with manifest)", False),
    ("context", ".speky/context/", "v2 project documents (product, architecture, tech decisions); new facts go "
                                    "to knowledge topics and ADRs", False),
    ("research", ".speky/research/", "research notes not tied to one change (per change: research.md)", True),
    ("testing", ".speky/testing/", "recorded test runs (per machine)", False),
]
DEFAULTS = {key: default for key, default, _, _ in ARTIFACTS}
OVERRIDABLE = {key for key, _, _, can in ARTIFACTS if can}


def path(project: Project, key: str) -> Path:
    """Effective location of an overridable artifact kind (the first one if several are configured)."""
    return paths(project, key)[0]


def paths(project: Project, key: str) -> List[Path]:
    configured = (project.config.get("paths") or {}).get(key)
    if configured:
        values = [configured] if isinstance(configured, str) else list(configured)
        return [project.root / v for v in values]
    return [project.root / DEFAULTS[key].split("<")[0].rstrip("/")]


def describe(project: Project) -> List[Dict]:
    configured = project.config.get("paths") or {}
    rows = []
    for key, default, what, can in ARTIFACTS:
        where = configured.get(key) if can and configured.get(key) else default
        rows.append({"kind": key, "path": where, "what": what, "overridden": bool(can and configured.get(key)),
                     "override": f"paths.{key}" if can else None})
    return rows


ADR_FILE_RE = re.compile(r"^\d{3,4}-[\w-]+\.md$")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "out", ".next", "coverage", ".speky",
             "__pycache__", "target", "Pods", ".dart_tool"}


def _adr_folders(project: Project) -> List[str]:
    known = {str(p.relative_to(project.root)) for p in paths(project, "adr_dir")}
    found = []
    for d in project.root.rglob("*"):
        if not d.is_dir() or any(p in SKIP_DIRS or p.startswith(".") for p in d.relative_to(project.root).parts):
            continue
        rel = str(d.relative_to(project.root))
        if rel in known:
            continue
        adrs = [f for f in d.iterdir() if f.is_file() and ADR_FILE_RE.match(f.name)
                and re.search(r"^\W*status\W", f.read_text(errors="ignore")[:2000], re.I | re.M)]
        if len(adrs) >= 2:
            found.append(rel)
    return found


def check(project: Project) -> Dict:
    """Non-code artifacts kept where SPEKY doesn't look."""
    from . import uxdesign
    problems = []
    for rel in uxdesign.find_design_folders(project):
        problems.append({"kind": "design_screens", "path": rel,
                         "fix": "import the screens (`speky design screen add <id> <files> --move`) or, if tooling "
                                f"depends on the folder, `speky config set paths.design_screens {rel}`"})
    for rel in _adr_folders(project):
        problems.append({"kind": "adr_dir", "path": rel,
                         "fix": f"ADRs found here: `speky config set paths.adr_dir {rel}` (or move them to .speky/adr/)"})
    legacy = project.dir / "context" / "design_system.md"
    if legacy.exists() and not (project.config.get("paths") or {}).get("design_system") \
            and not (project.root / DEFAULTS["design_system"]).exists():
        problems.append({"kind": "design_system", "path": ".speky/context/design_system.md",
                         "fix": "`speky migrate --apply` moves it to .speky/design/system.md"})
    return {"valid": not problems, "problems": problems}


def summary_lines(project: Project) -> List[str]:
    """For `speky prime`: the overridden locations (defaults are in `speky layout`)."""
    rows = [r for r in describe(project) if r["overridden"]]
    return [f"{r['kind']}: `{r['path']}`" for r in rows]
