"""Phases (milestones) for the agent protocol — the same `.speky/phases/<id>/manifest.yaml` files the
v2 `speky phases` commands use, with JSON output for agents.

A phase's gate is its deliverables (each may carry a `run:` command that proves it) and acceptance
criteria; verified deliverables are recorded in `phases/<id>/status.json` (`verified_deliverables`),
exactly as v2 records them.
"""
import json
import re
import subprocess
from typing import Dict, List, Optional

from . import yamlio
from .errors import SpekyError
from .items import Project, now, slugify, write_json

V2_STATUS = {"todo": "not_started", "doing": "in_progress", "done": "completed", "deferred": "deferred"}
V3_STATUS = {"not_started": "todo", "planned": "todo", "in_progress": "doing", "active": "doing",
             "completed": "done", "complete": "done", "done": "done", "deferred": "deferred"}


def phases_dir(project: Project):
    return project.dir / "phases"


def _load_yaml_file(path) -> dict:
    try:
        data = yamlio.load(path.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    raise SpekyError("phase_unreadable", f"{path} is not valid YAML.", "Fix it by hand.")


def roadmap_meta(project: Project) -> dict:
    path = phases_dir(project) / "roadmap.yaml"
    if not path.exists():
        return {}
    try:
        data = yamlio.load(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_roadmap_meta(project: Project, data: dict) -> None:
    path = phases_dir(project) / "roadmap.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yamlio.dump(data))


class Phase:
    def __init__(self, project: Project, folder):
        self.project = project
        self.dir = folder
        self.manifest_path = folder / "manifest.yaml"
        self.status_path = folder / "status.json"
        self.data = _load_yaml_file(self.manifest_path)

    @property
    def id(self) -> str:
        return str(self.data.get("id") or self.dir.name)

    @property
    def status(self) -> str:
        return V3_STATUS.get(str(self.data.get("status", "not_started")), "todo")

    def save(self) -> None:
        self.data["updated_at"] = now()
        self.manifest_path.write_text(yamlio.dump(self.data))

    def verified(self) -> List[str]:
        if not self.status_path.exists():
            return []
        return list(json.loads(self.status_path.read_text()).get("verified_deliverables", []))

    def _save_verified(self, ids: List[str], evidence: Dict[str, str] = None) -> None:
        data = json.loads(self.status_path.read_text()) if self.status_path.exists() else {}
        data["verified_deliverables"] = ids
        if evidence:
            data.setdefault("evidence", {}).update(evidence)
        write_json(self.status_path, data)

    def deliverables(self) -> List[dict]:
        verified = set(self.verified())
        out = []
        for i, d in enumerate(self.data.get("deliverables") or [], 1):
            d = d if isinstance(d, dict) else {"name": str(d)}
            did = str(d.get("id") or f"D{i}")
            out.append({"id": did, "name": d.get("name", ""), "run": d.get("run"),
                        "pass_criteria": d.get("pass_criteria", ""), "verified": did in verified})
        return out

    def to_dict(self, with_tasks: bool = True) -> dict:
        from .tasks import Tasks
        result = {"id": self.id, "name": self.data.get("name", self.id), "status": self.status,
                  "description": self.data.get("description", ""),
                  "deliverables": self.deliverables(),
                  "acceptance_criteria": self.data.get("acceptance_criteria") or [],
                  "specs": [s.get("id") if isinstance(s, dict) else s for s in self.data.get("specs") or []],
                  "file": str(self.manifest_path.relative_to(self.project.root))}
        if with_tasks:
            tasks = Tasks(self.project).list(phase=self.id)
            result["tasks"] = {s: len([t for t in tasks if t["status"] == s])
                               for s in ("todo", "doing", "done", "deferred")}
        return result


def all_phases(project: Project) -> List[Phase]:
    base = phases_dir(project)
    if not base.is_dir():
        return []
    phases = []
    for folder in sorted(base.iterdir()):
        if folder.is_dir() and (folder / "manifest.yaml").exists():
            try:
                phases.append(Phase(project, folder))
            except SpekyError:
                continue
    return phases


def get(project: Project, ref: str) -> Phase:
    for p in all_phases(project):
        if p.id.lower() == ref.lower() or p.dir.name.lower() == ref.lower():
            return p
    raise SpekyError("phase_not_found", f"No phase '{ref}'.", "Run `speky phases list --json`.")


def current(project: Project) -> Optional[Phase]:
    """The phase in progress (v2's `current_phase` first), else the first one not started."""
    meta = roadmap_meta(project)
    phases = all_phases(project)
    if meta.get("current_phase"):
        for p in phases:
            if p.id == meta["current_phase"] and p.status in ("doing", "todo"):
                return p
    for status in ("doing", "todo"):
        for p in phases:
            if p.status == status:
                return p
    return None


def add(project: Project, name: str, phase_id: str = None, description: str = "",
        status: str = "todo") -> Phase:
    base = phases_dir(project)
    base.mkdir(parents=True, exist_ok=True)
    if not phase_id:
        n = len([d for d in base.iterdir() if d.is_dir()]) + 1
        phase_id = f"phase-{n:02d}-{slugify(name)[:30]}"
    folder = base / phase_id
    if folder.exists():
        raise SpekyError("phase_exists", f"Phase '{phase_id}' already exists.")
    folder.mkdir()
    data = {"id": phase_id, "name": name, "description": description, "status": V2_STATUS[status],
            "specs": [], "deliverables": [], "acceptance_criteria": [], "depends_on": [], "unlocks": [],
            "created_at": now()}
    (folder / "manifest.yaml").write_text(yamlio.dump(data))
    return Phase(project, folder)


def set_status(project: Project, ref: str, status: str) -> Phase:
    phase = get(project, ref)
    phase.data["status"] = V2_STATUS[status]
    phase.data[f"{status}_at"] = now()
    phase.save()
    meta = roadmap_meta(project)
    if status == "doing":
        meta["current_phase"] = phase.id
        _save_roadmap_meta(project, meta)
    elif status in ("done", "deferred") and meta.get("current_phase") == phase.id:
        nxt = current(project)
        meta["current_phase"] = nxt.id if nxt else None
        _save_roadmap_meta(project, meta)
    return phase


def add_deliverable(project: Project, ref: str, name: str, run: str = None, pass_criteria: str = "") -> dict:
    phase = get(project, ref)
    items = phase.data.setdefault("deliverables", []) or []
    phase.data["deliverables"] = items
    nums = [int(re.sub(r"\D", "", str(d.get("id", "")) or "0") or 0) for d in items if isinstance(d, dict)]
    did = f"D{max(nums, default=len(items)) + 1}"
    entry = {"id": did, "name": name}
    if pass_criteria:
        entry["pass_criteria"] = pass_criteria
    if run:
        entry["run"] = run
    items.append(entry)
    phase.save()
    return next(d for d in phase.deliverables() if d["id"] == did)


def verify_deliverable(project: Project, ref: str, deliverable: str, evidence: str) -> dict:
    phase = get(project, ref)
    ids = [d["id"] for d in phase.deliverables()]
    if deliverable not in ids:
        raise SpekyError("deliverable_not_found", f"{phase.id} has no deliverable {deliverable}.",
                         f"Deliverables: {', '.join(ids) or 'none'}.")
    if not evidence.strip():
        raise SpekyError("evidence_required", "A verified deliverable needs evidence.",
                         'Add --evidence "<what you ran or checked, and the result>".')
    verified = phase.verified()
    if deliverable not in verified:
        verified.append(deliverable)
    phase._save_verified(verified, {deliverable: f"{evidence} ({now()[:10]})"})
    return {"phase": phase.id, "deliverable": deliverable, "verified": True}


def check(project: Project, ref: str) -> dict:
    """Run `run:` deliverables, report manual ones, open tasks and unfinished specs."""
    from .items import DONE_STATUSES
    from .tasks import Tasks
    phase = get(project, ref)
    verified = phase.verified()
    results = []
    for d in phase.deliverables():
        if d["run"]:
            proc = subprocess.run(d["run"], shell=True, cwd=project.root, capture_output=True, text=True)
            ok = proc.returncode == 0
            if ok and d["id"] not in verified:
                verified.append(d["id"])
                phase._save_verified(verified, {d["id"]: f"`{d['run']}` passed ({now()[:10]})"})
            results.append({**d, "verified": ok, "exit_code": proc.returncode,
                            "output_tail": "\n".join((proc.stdout + proc.stderr).splitlines()[-12:])})
        else:
            results.append(d)
    open_tasks = [t["id"] for t in Tasks(project).list(phase=phase.id) if t["status"] in ("todo", "doing")]
    open_specs = []
    for sid in phase.to_dict(with_tasks=False)["specs"]:
        item = project.try_find(str(sid))
        if item and item.info()["status"] not in DONE_STATUSES:
            open_specs.append(item.id)
    passed = all(r["verified"] for r in results) and not open_tasks and not open_specs
    return {"phase": phase.id, "deliverables": results, "acceptance_criteria": phase.data.get("acceptance_criteria") or [],
            "open_tasks": open_tasks, "open_specs": open_specs, "passed": passed}
