"""Design assets and the design system (v2's `speky design`), on v2's layout: `.speky/design/` with
`manifest.json` (technology, system_doc, hifi_images, lofi_images, icons, conflicts, components) and
`{hifi,lofi,system,icons}/source/`.

SPEKY stores assets, links them to items and tracks conflicts between the design-system document and
hi-fi screens. Looking at images, extracting tokens, judging conflicts and syncing the design system
with code is the agent's work (speky-design skill); the agent records results here.
"""
import json
import shutil
from pathlib import Path
from typing import List

from .errors import SpekyError
from .items import Project, now, write_json

KINDS = {"hifi": "hifi_images", "lofi": "lofi_images", "icon": "icons", "system": None}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
CONFLICT_TYPES = ("color", "typography", "spacing", "radius", "shadow", "layout", "component")


def design_dir(project: Project) -> Path:
    return project.dir / "design"


def _manifest(project: Project) -> dict:
    path = design_dir(project) / "manifest.json"
    if not path.exists():
        raise SpekyError("design_not_initialized", "No design system yet.", "Run `speky design init`.")
    data = json.loads(path.read_text())
    for i, c in enumerate(data.get("conflicts", []), 1):  # v2 conflicts had no IDs
        c.setdefault("id", f"C{i}")
    return data


def _save(project: Project, data: dict) -> None:
    data["updated_at"] = now()
    write_json(design_dir(project) / "manifest.json", data)


def init(project: Project, technology: str = "") -> dict:
    base = design_dir(project)
    for sub in ("hifi", "lofi", "system", "icons"):
        (base / sub / "source").mkdir(parents=True, exist_ok=True)
    path = base / "manifest.json"
    if path.exists():
        data = json.loads(path.read_text())
        if technology:
            data["technology"] = technology
    else:
        data = {"id": "design-system", "created_at": now(), "technology": technology,
                "source_mode": "files", "system_doc": None, "hifi_images": [], "lofi_images": [],
                "icons": [], "conflicts": [], "components": []}
    _save(project, data)
    return status(project)


def add(project: Project, path: str, kind: str, item: str = None) -> dict:
    if kind not in KINDS:
        raise SpekyError("bad_design_kind", f"Kind must be one of {', '.join(KINDS)}.")
    data = _manifest(project)
    src = Path(path).expanduser()
    if not src.exists():
        raise SpekyError("source_not_found", f"{path} does not exist.")
    folder = design_dir(project) / ("icons" if kind == "icon" else kind) / "source"
    files = [src] if src.is_file() else [p for p in src.iterdir() if p.is_file()]
    added = []
    for f in files:
        shutil.copy2(f, folder / f.name)
        if kind == "system":
            data["system_doc"] = str((folder / f.name).relative_to(project.dir))
        elif f.suffix.lower() in IMAGE_EXT:
            key = KINDS[kind]
            entries = data.setdefault(key, [])
            if not any(e["filename"] == f.name for e in entries):
                entries.append({"filename": f.name, "type": kind, "added_at": now(), "related_specs": []})
        added.append(f.name)
    _save(project, data)
    if item:
        for name in added:
            if kind in ("hifi", "lofi"):
                link(project, name, item)
    return {"added": added, "kind": kind, **status(project)}


def _find_image(data: dict, filename: str):
    for key in ("hifi_images", "lofi_images", "icons"):
        for e in data.get(key, []):
            if e["filename"] == filename:
                return e
    raise SpekyError("design_asset_not_found", f"No design image '{filename}'.", "Run `speky design status`.")


def link(project: Project, filename: str, item_ref: str) -> dict:
    data = _manifest(project)
    item = project.find(item_ref)
    entry = _find_image(data, filename)
    if item.id not in entry.setdefault("related_specs", []):
        entry["related_specs"].append(item.id)
    _save(project, data)
    return {"filename": filename, "linked_to": entry["related_specs"]}


def record_analysis(project: Project, filename: str, analysis_file: str) -> dict:
    """Store the agent's analysis of an image (tokens, layout, components) next to it."""
    data = _manifest(project)
    entry = _find_image(data, filename)
    src = Path(analysis_file)
    if not src.exists():
        raise SpekyError("source_not_found", f"{analysis_file} does not exist.")
    folder = design_dir(project) / ("icons" if entry["type"] == "icon" else entry["type"]) / "source"
    target = folder / (Path(filename).stem + ".analysis.md")
    shutil.copyfile(src, target)
    entry["analysis_path"] = str(target.relative_to(project.dir))
    entry["analyzed_at"] = now()
    _save(project, data)
    return {"filename": filename, "analysis": entry["analysis_path"]}


def add_conflict(project: Project, type_: str, location: str, existing: str, new: str,
                 severity: str = "medium", context: str = "") -> dict:
    if type_ not in CONFLICT_TYPES:
        raise SpekyError("bad_conflict_type", f"Type must be one of {', '.join(CONFLICT_TYPES)}.")
    data = _manifest(project)
    conflicts = data.setdefault("conflicts", [])
    cid = f"C{len(conflicts) + 1}"
    conflicts.append({"id": cid, "type": type_, "location": location, "existing_value": existing,
                      "new_value": new, "severity": severity, "context": context, "detected_at": now()})
    _save(project, data)
    return conflicts[-1]


def resolve_conflict(project: Project, cid: str, value: str, reason: str) -> dict:
    data = _manifest(project)
    for c in data.get("conflicts", []):
        if c.get("id") == cid:
            c["resolution"] = {"value": value, "reason": reason, "resolved_at": now()}
            _save(project, data)
            from . import journal
            journal.decide(project, f"Design {c['type']} at {c['location']}: use {value} — {reason}", "decision")
            return c
    raise SpekyError("conflict_not_found", f"No design conflict {cid}.")


def status(project: Project) -> dict:
    """Where the project's design lives and which UI changes still need one (works without `design init`)."""
    from . import uxdesign
    data = _manifest(project) if (design_dir(project) / "manifest.json").exists() else {}
    imgs = data.get("hifi_images", []) + data.get("lofi_images", [])
    catalogues = sorted({spec["file"] for spec in (project.config.get("refs") or {}).values()
                         if isinstance(spec, dict) and spec.get("file")} |
                        {spec["glob"] for spec in (project.config.get("refs") or {}).values()
                         if isinstance(spec, dict) and spec.get("glob")})
    ui_items = []
    for item in project.items():
        if item.info()["status"] not in ("archived", "completed") and uxdesign.is_ui(project, item):
            st = uxdesign.state(project, item)
            ui_items.append({"item": item.id, "title": item.info()["title"], "designed": uxdesign.satisfied(st),
                             "cited": st["cited"], "broken": st["broken"]})
    playbook = (project.config.get("playbooks") or {})
    return {"design_system": uxdesign.design_system(project), "technology": data.get("technology"),
            "catalogues": catalogues, "playbooks": {k: v.get("skill") for k, v in playbook.items()
                                                    if isinstance(v, dict)},
            "images": len(imgs), "analyzed": len([i for i in imgs if i.get("analysis_path")]),
            "unlinked": [i["filename"] for i in imgs if not i.get("related_specs")],
            "icons": len(data.get("icons", [])),
            "open_conflicts": [c for c in data.get("conflicts", []) if not c.get("resolution")],
            "components": data.get("components", []),
            "ui_items": ui_items, "needing_design": [u["item"] for u in ui_items if not u["designed"]]}
