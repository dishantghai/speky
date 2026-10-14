"""Context packets: everything an agent needs to work on one item or one phase, as pointers.

Replaces v2's implementation "context chain" (which was pasted into the IDE rules file) and phase
guides. The packet lists files to read with a reason and a few facts inline; `--full` inlines the
documents. Layers, broad to specific: project knowledge → tech decisions/ADRs → design → phase →
epic → related specs → dependencies → the item itself (doc, plan, deltas, findings, evidence).
"""
import json
from pathlib import Path
from typing import List, Optional

from . import epics, graph, journal, knowledge, markdown as md, phases
from .errors import SpekyError
from .items import DONE_STATUSES, Item, Project
from .validation import Ledger


def _rel(project: Project, path: Path) -> str:
    return str(path.relative_to(project.root))


def _layer(project: Project, name: str, path: Path, why: str, full: bool) -> Optional[dict]:
    if not path.exists():
        return None
    entry = {"layer": name, "read": _rel(project, path), "why": why}
    if full and path.is_file():
        entry["content"] = path.read_text()
    return entry


def _project_layers(project: Project, full: bool) -> List[dict]:
    layers = []
    for t in knowledge.topics(project):
        if t["always"] or t["topic"] in ("product", "tech"):
            layers.append(_layer(project, "knowledge", project.root / t["file"],
                                 f"{t['title']}: facts the code can't show", full))
    ctx = project.dir / "context"
    for name, why in (("product.md", "what the product is and for whom"),
                      ("tech_decisions.md", "authoritative tech decisions: don't choose other packages"),
                      ("architecture.md", "architecture rules")):
        layers.append(_layer(project, "project", ctx / name, why, full))
    adr = journal.adr_dir(project)
    if adr.is_dir():
        accepted = [a for a in journal.adr_list(project) if a["status"].lower().startswith("accepted")]
        layers.append({"layer": "decisions", "read": _rel(project, adr),
                       "why": f"{len(accepted)} accepted ADRs bind the design; check before deciding",
                       "adrs": [f"{a['id']} {a['title']}" for a in accepted][-15:]})
    return [l for l in layers if l]


def _design_layers(project: Project, item_id: str, full: bool) -> List[dict]:
    design = project.dir / "design"
    layers = []
    configured = (project.config.get("paths") or {}).get("design_system")
    system = project.root / configured if configured else project.dir / "context" / "design_system.md"
    if system.exists():
        layers.append(_layer(project, "design", system, "design system: tokens and components to reuse", full))
    manifest = design / "manifest.json"
    if manifest.exists():
        data = json.loads(manifest.read_text())
        for kind in ("hifi", "lofi"):
            for img in data.get(f"{kind}_images", []):
                if any(item_id.startswith(str(s)) or str(s).startswith(item_id) for s in img.get("related_specs", [])):
                    src = design / kind / "source" / img["filename"]
                    entry = {"layer": "design", "read": _rel(project, src) if src.exists() else img["filename"],
                             "why": f"{kind} design for this item"
                                    + (" — match it pixel-perfect" if kind == "hifi" else " — guidance")}
                    if img.get("analysis_path") and (project.dir / img["analysis_path"]).exists():
                        entry["analysis"] = _rel(project, project.dir / img["analysis_path"])
                    layers.append(entry)
    return layers


def item_packet(project: Project, ref: str, full: bool = False) -> dict:
    item = project.find(ref)
    info = item.info()
    status = item.load_status()
    layers = _project_layers(project, full)
    layers += _design_layers(project, item.id, full)

    phase_id = status.get("phase")
    for p in phases.all_phases(project):
        specs = [str(s.get("id") if isinstance(s, dict) else s) for s in p.data.get("specs") or []]
        if item.id in specs:
            phase_id = p.id
    if phase_id:
        try:
            p = phases.get(project, phase_id)
            layers.append({"layer": "phase", "read": _rel(project, p.manifest_path),
                           "why": f"phase {p.id} ({p.data.get('name', '')}): stay inside its scope and excludes",
                           "deliverables": [d["name"] for d in p.deliverables()]})
        except SpekyError:
            pass

    epic = epics.epic_of(project, item.id) if item.kind == "story" else None
    if epic:
        layers.append({"layer": "epic", "read": epic["folder"],
                       "why": f"epic {epic['id']} {epic['name']}: shared docs and sibling stories",
                       "docs": epic["docs"], "siblings": [f"{s['id']} {s['title']} ({s['status']})"
                                                          for s in epic["stories"] if s["id"] != item.id]})

    for rid in (status.get("related_specs") or [])[:3]:
        rel = project.try_find(str(rid))
        if rel:
            layers.append({"layer": "related", "read": _rel(project, rel.doc_path),
                           "why": f"related spec {rel.id} {rel.info()['title']}"})

    all_info = graph.statuses(project)
    deps = []
    for d in info["dependencies"]:
        dep = all_info.get(d)
        if dep:
            deps.append({"id": d, "title": dep["title"], "status": dep["status"],
                         "done": dep["status"] in DONE_STATUSES})
    files = status.get("affected_files") or []
    item_layer = {"layer": "item", "read": _rel(project, item.doc_path), "why": "the change you are building"}
    if full:
        item_layer["content"] = item.read_doc()
    layers.append(item_layer)
    for extra, why in (("plan.md", "the plan: decisions, tasks and verify commands"),
                       ("research.md", "research gathered for this item")):
        layers.append(_layer(project, "item", item.path / extra, why, full))
    deltas = item.path / "deltas"
    if deltas.is_dir():
        layers.append({"layer": "item", "read": _rel(project, deltas),
                       "why": "how this change alters the living specs"})
    from . import playbooks, refs
    books = playbooks.for_labels(project, status.get("labels") or [])
    for b in books:
        layers.append({"layer": "playbook", "label": b["label"], "skill": b["skill"],
                       "why": playbooks.instruction([b])})
        for r in b["read"]:
            layers.append(_layer(project, "playbook", project.root / r, f"part of the `{b['label']}` playbook", full))
    for c in refs.cited(project, item.read_doc()):
        if c["read"]:
            layers.append({"layer": "reference", "ref": c["ref"], "read": c["read"],
                           "why": f"the item cites {c['ref']}"})
    reqs = md.parse_requirements(md.strip_comments(item.read_doc()))
    return {"item": item.id, "kind": item.kind, "title": info["title"], "status": info["status"],
            "requirements": [f"{r.id}: {r.title}" for r in reqs],
            "dependencies": deps, "affected_files": files,
            "open_findings": [f"{f['id']} [{f['severity']}] {f['text']}" for f in Ledger(item).open()],
            "decisions": journal.decisions(project, item.id),
            "knowledge_topics": [f"{t['file']}" + (f" (read when {t['read_when']})" if t["read_when"] else "")
                                 for t in knowledge.topics(project) if not t["always"]],
            "layers": [l for l in layers if l],
            "base_sha": status.get("base_sha"),
            "next": f"speky next {item.id}"}


def phase_packet(project: Project, ref: str, full: bool = False) -> dict:
    """What v2's phase guide gave: scope, items in order, deliverables, prerequisites."""
    from . import deps as deps_mod
    from .tasks import Tasks
    p = phases.get(project, ref)
    specs = [str(s.get("id") if isinstance(s, dict) else s) for s in p.data.get("specs") or []]
    ordered = [r for r in deps_mod.order(project) if r["id"] in specs]
    return {"phase": p.id, "name": p.data.get("name", ""), "status": p.status,
            "description": p.data.get("description", ""),
            "read": _rel(project, p.manifest_path),
            "items_in_order": ordered,
            "tasks": Tasks(project).list(phase=p.id),
            "deliverables": p.deliverables(),
            "acceptance_criteria": p.data.get("acceptance_criteria") or [],
            "prerequisites": p.data.get("prerequisites") or [],
            "depends_on": p.data.get("depends_on") or [], "unlocks": p.data.get("unlocks") or [],
            "layers": _project_layers(project, full)}
