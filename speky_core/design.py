"""Design: the design-system document, screens and reviews, in the standard layout (`speky layout`).

    .speky/design/system.md                 the design-system document          (paths.design_system)
    .speky/design/screens/<screen-id>/      one folder per screen: images, HTML  (paths.design_screens)
        screen.yaml                         id, title, kind, states, items, status, source, review
    .speky/design/screens.md                the catalogue (generated)
    .speky/design/reviews/<date>-<id>.md    design and UX reviews               (paths.design_reviews)
    .speky/design/icons/                    icons
    .speky/design/manifest.json             technology, conflicts with the system, components

A screen's folder name is its ID, cited as `screen:<id>` in a change's `## Design`. A new iteration gets a
new ID and the old one is marked superseded, never overwritten. Screens start as `draft`; the owner
approves them (`speky design screen approve`) before UI work is built from them.

Projects whose tooling keeps screens elsewhere set `paths.design_screens` (one folder or a list): each
sub-folder with a `screen.yaml` is a screen, and image files directly in such a folder are screens too
(ID = slug of the file name). Looking at images, extracting tokens, generating designs with a tool
(Stitch, Figma, …) and reviewing them is the agent's work (speky-design skill); SPEKY stores, links and
checks.
"""
import json
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from . import layout, yamlio
from .errors import SpekyError
from .items import Project, now, slugify, write_json

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
DESIGN_EXT = IMAGE_EXT | {".html", ".htm", ".pdf", ".fig"}
CONFLICT_TYPES = ("color", "typography", "spacing", "radius", "shadow", "layout", "component")
SCREEN_KINDS = ("hifi", "lofi", "wireframe", "flow")
SCREEN_META = "screen.yaml"
ID_RE = re.compile(r"^[A-Za-z0-9][\w.-]*$")


def design_dir(project: Project) -> Path:
    return project.dir / "design"


def system_path(project: Project) -> Path:
    return layout.path(project, "design_system")


def screens_root(project: Project) -> Path:
    return layout.path(project, "design_screens")


def reviews_dir(project: Project) -> Path:
    return layout.path(project, "design_reviews")


def _rel(project: Project, p: Path) -> str:
    return str(p.relative_to(project.root))


# ---------------------------------------------------------------------------- manifest (system metadata)
def _manifest(project: Project) -> dict:
    path = design_dir(project) / "manifest.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    for i, c in enumerate(data.get("conflicts", []), 1):  # v2 conflicts had no IDs
        c.setdefault("id", f"C{i}")
    return data


def _save(project: Project, data: dict) -> None:
    data["updated_at"] = now()
    design_dir(project).mkdir(parents=True, exist_ok=True)
    write_json(design_dir(project) / "manifest.json", data)


def init(project: Project, technology: str = "") -> dict:
    screens_root(project).mkdir(parents=True, exist_ok=True)
    data = _manifest(project)
    data.setdefault("created_at", now())
    if technology:
        data["technology"] = technology
    data.setdefault("conflicts", [])
    data.setdefault("components", [])
    _save(project, data)
    render_catalogue(project)
    return status(project)


# ---------------------------------------------------------------------------- screens
def _load_meta(folder: Path) -> dict:
    path = folder / SCREEN_META
    if path.exists():
        data = yamlio.load(path.read_text())
        return data if isinstance(data, dict) else {}
    return {}


def _save_meta(folder: Path, meta: dict) -> None:
    (folder / SCREEN_META).write_text(yamlio.dump(meta))


def screens(project: Project) -> List[Dict]:
    """Every screen in the design locations: {id, title, status, kind, states, items, files, path}."""
    out, seen = [], set()
    default = project.root / layout.DEFAULTS["design_screens"].split("<")[0].rstrip("/")
    for root in layout.paths(project, "design_screens"):
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and (root == default or (entry / SCREEN_META).exists()):
                meta = _load_meta(entry)
                sid = str(meta.get("id") or entry.name)
                files = [_rel(project, f) for f in sorted(entry.rglob("*"))
                         if f.is_file() and f.suffix.lower() in DESIGN_EXT]
                out.append({"id": sid, "title": meta.get("title", sid), "status": meta.get("status", "draft"),
                            "kind": meta.get("kind", "hifi"), "states": meta.get("states") or [],
                            "items": [str(i) for i in meta.get("items") or []], "files": files,
                            "path": _rel(project, entry), "review": meta.get("review"),
                            "superseded_by": meta.get("superseded_by")})
                seen.add(sid)
            elif entry.is_file() and entry.suffix.lower() in DESIGN_EXT:
                sid = slugify(entry.stem)
                if sid not in seen:
                    out.append({"id": sid, "title": entry.stem, "status": None, "kind": None, "states": [],
                                "items": [], "files": [_rel(project, entry)], "path": _rel(project, entry),
                                "review": None, "superseded_by": None})
                    seen.add(sid)
    return out


def find_screen(project: Project, sid: str) -> Optional[Dict]:
    for s in screens(project):
        if s["id"].lower() == sid.lower() or slugify(s["id"]) == slugify(sid):
            return s
    return None


def _screen_folder(project: Project, sid: str) -> Path:
    s = find_screen(project, sid)
    if not s:
        raise SpekyError("screen_not_found", f"No screen '{sid}'.", "Run `speky design screen list --json`.")
    folder = project.root / s["path"]
    if not folder.is_dir():
        raise SpekyError("screen_is_a_file", f"Screen '{sid}' is a single file ({s['path']}) without metadata.",
                         f"Import it: `speky design screen add {s['id']} \"{s['path']}\" --move`.")
    return folder


def screen_add(project: Project, sid: str, files: List[str], title: str = "", kind: str = "hifi",
               states: List[str] = None, item: str = None, source: str = "", move: bool = False) -> dict:
    if not ID_RE.match(sid):
        raise SpekyError("bad_screen_id", f"'{sid}' is not a valid screen ID.",
                         "Use letters, digits, '.', '_' and '-', e.g. layers-editor-main or RV-E3-held.")
    if kind not in SCREEN_KINDS:
        raise SpekyError("bad_screen_kind", f"Kind must be one of {', '.join(SCREEN_KINDS)}.")
    folder = screens_root(project) / sid
    existing = _load_meta(folder)
    if existing.get("status") == "approved" and files:
        raise SpekyError("screen_approved", f"Screen {sid} is approved; a new iteration gets a new ID.",
                         f"`speky design screen add <new-id> ...`, then `speky design screen supersede {sid} --by <new-id>`.")
    folder.mkdir(parents=True, exist_ok=True)
    added = []
    for f in files or []:
        src = Path(f).expanduser()
        if not src.is_absolute():
            src = Path.cwd() / src
        if not src.exists():
            raise SpekyError("source_not_found", f"{f} does not exist.")
        for one in ([src] if src.is_file() else [p for p in sorted(src.rglob("*")) if p.is_file()]):
            target = folder / (one.name if src.is_file() else one.relative_to(src))
            target.parent.mkdir(parents=True, exist_ok=True)
            (shutil.move if move else shutil.copy2)(str(one), str(target))
            added.append(_rel(project, target))
        if move and src.is_dir() and not any(p.is_file() for p in src.rglob("*")):
            shutil.rmtree(src)
    meta = {"id": sid, "title": title or existing.get("title") or sid.replace("-", " "),
            "kind": kind, "status": existing.get("status", "draft"),
            "states": sorted(set((existing.get("states") or []) + (states or []))),
            "items": existing.get("items") or [], "source": source or existing.get("source", ""),
            "created_at": existing.get("created_at", now())}
    for k in ("review", "approved_by", "approved_at", "superseded_by", "supersedes", "analysis"):
        if existing.get(k):
            meta[k] = existing[k]
    _save_meta(folder, meta)
    if item:
        link(project, sid, item)
    render_catalogue(project)
    return {"screen": sid, "path": _rel(project, folder), "added": added, "status": meta["status"]}


def link(project: Project, sid: str, item_ref: str) -> dict:
    """The screen belongs to an item: recorded on the screen and cited in the item's `## Design`."""
    from . import uxdesign
    item = project.find(item_ref)
    s = find_screen(project, sid) or find_screen(project, Path(sid).stem)
    if not s:
        raise SpekyError("screen_not_found", f"No screen '{sid}'.", "Run `speky design screen list --json`.")
    folder = project.root / s["path"]
    if folder.is_dir():
        meta = _load_meta(folder) or {"id": s["id"]}
        if item.id not in (meta.get("items") or []):
            meta["items"] = (meta.get("items") or []) + [item.id]
        _save_meta(folder, meta)
    uxdesign.cite_screen(project, item, s["id"])
    render_catalogue(project)
    return {"screen": s["id"], "item": item.id}


def approve(project: Project, sid: str, by: str, note: str = "") -> dict:
    from . import journal
    folder = _screen_folder(project, sid)
    meta = _load_meta(folder)
    meta.update(status="approved", approved_by=by, approved_at=now())
    _save_meta(folder, meta)
    journal.decide(project, f"Design {meta.get('id', sid)} approved by {by}" + (f": {note}" if note else ""),
                   "decision", (meta.get("items") or [None])[0])
    render_catalogue(project)
    return {"screen": meta.get("id", sid), "status": "approved"}


def supersede(project: Project, old: str, new: str) -> dict:
    old_folder, new_folder = _screen_folder(project, old), _screen_folder(project, new)
    meta = _load_meta(old_folder)
    meta.update(status="superseded", superseded_by=new)
    _save_meta(old_folder, meta)
    nmeta = _load_meta(new_folder)
    nmeta["supersedes"] = old
    nmeta["items"] = sorted(set((nmeta.get("items") or []) + (meta.get("items") or [])))
    _save_meta(new_folder, nmeta)
    render_catalogue(project)
    return {"superseded": old, "by": new}


def review(project: Project, sid: str, review_file: str, result: str) -> dict:
    if result not in ("pass", "fail"):
        raise SpekyError("bad_result", "Result is pass or fail.")
    folder = _screen_folder(project, sid)
    src = Path(review_file)
    if not src.exists():
        raise SpekyError("source_not_found", f"{review_file} does not exist.")
    target_dir = reviews_dir(project)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{date.today().isoformat()}-{sid}.md"
    if src.resolve() != target.resolve():
        shutil.copyfile(src, target)
    meta = _load_meta(folder)
    meta["review"] = {"file": _rel(project, target), "result": result, "at": now()}
    _save_meta(folder, meta)
    render_catalogue(project)
    return {"screen": sid, "review": meta["review"]}


def record_analysis(project: Project, sid: str, analysis_file: str) -> dict:
    """The agent's analysis of a screen (tokens, layout, components), stored in its folder."""
    s = find_screen(project, sid) or find_screen(project, Path(sid).stem)
    if not s:
        raise SpekyError("screen_not_found", f"No screen '{sid}'.", "Run `speky design screen list --json`.")
    folder = _screen_folder(project, s["id"])
    src = Path(analysis_file)
    if not src.exists():
        raise SpekyError("source_not_found", f"{analysis_file} does not exist.")
    shutil.copyfile(src, folder / "analysis.md")
    meta = _load_meta(folder)
    meta["analysis"] = "analysis.md"
    _save_meta(folder, meta)
    return {"screen": s["id"], "analysis": _rel(project, folder / "analysis.md")}


def render_catalogue(project: Project) -> None:
    """`.speky/design/screens.md`: every screen with its status, states, items and review."""
    rows = screens(project)
    if not rows and not (design_dir(project) / "screens.md").exists():
        return
    lines = ["# Screens", "", "_Generated by SPEKY (`speky design screen …`). Cite a screen as `screen:<id>` in a "
             "change's `## Design`. A new iteration gets a new ID; the old one is superseded._", "",
             "| ID | Title | Status | States | Items | Review | Path |", "|---|---|---|---|---|---|---|"]
    for s in rows:
        rev = f"{s['review']['result']} ({s['review']['file']})" if s.get("review") else ""
        status_ = (s["status"] or "—") + (f" → {s['superseded_by']}" if s.get("superseded_by") else "")
        lines.append(f"| `{s['id']}` | {s['title']} | {status_} | {', '.join(s['states'])} | "
                     f"{', '.join(s['items'])} | {rev} | `{s['path']}` |")
    design_dir(project).mkdir(parents=True, exist_ok=True)
    (design_dir(project) / "screens.md").write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------- v2-style entry points
def add(project: Project, path: str, kind: str, item: str = None) -> dict:
    """`speky design add <file|folder> --type system|hifi|lofi|icon`: into the standard layout."""
    src = Path(path).expanduser()
    if not src.exists():
        raise SpekyError("source_not_found", f"{path} does not exist.")
    if kind == "system":
        target = system_path(project)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.resolve() != src.resolve():
            raise SpekyError("design_system_exists", f"{_rel(project, target)} already exists.",
                             "Merge the new content into it, or remove it first.")
        if target.resolve() != src.resolve():
            shutil.copyfile(src, target)
        return {"design_system": _rel(project, target), **status(project)}
    if kind == "icon":
        folder = design_dir(project) / "icons"
        folder.mkdir(parents=True, exist_ok=True)
        files = [src] if src.is_file() else [p for p in src.iterdir() if p.is_file()]
        for f in files:
            shutil.copy2(f, folder / f.name)
        return {"icons": [f.name for f in files], **status(project)}
    files = [src] if src.is_file() else [p for p in sorted(src.iterdir()) if p.suffix.lower() in DESIGN_EXT]
    added = [screen_add(project, slugify(f.stem), [str(f)], title=f.stem, kind=kind, item=item)["screen"]
             for f in files]
    return {**status(project), "added": added}


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


# ---------------------------------------------------------------------------- v2 assets → standard layout
def legacy_assets(project: Project) -> Dict[str, int]:
    """What v2's layout (`{hifi,lofi,system,icons}/source/` + manifest image lists) still holds."""
    data = _manifest(project)
    out = {"images": sum(len(data.get(f"{k}_images", [])) for k in ("hifi", "lofi")),
           "system_doc": 1 if data.get("system_doc") else 0}
    icons = design_dir(project) / "icons" / "source"
    out["icons"] = len(list(icons.iterdir())) if icons.is_dir() else 0
    return {k: v for k, v in out.items() if v}


def convert_legacy(project: Project) -> dict:
    """Move v2 design assets into the standard layout, keeping their links and analyses."""
    data = _manifest(project)
    moved = []
    for kind in ("hifi", "lofi"):
        for e in data.get(f"{kind}_images", []):
            src = design_dir(project) / kind / "source" / e["filename"]
            if not src.exists():
                continue
            sid = slugify(Path(e["filename"]).stem)
            screen_add(project, sid, [str(src)], title=Path(e["filename"]).stem, kind=kind, move=True)
            folder = screens_root(project) / sid
            meta = _load_meta(folder)
            meta["items"] = sorted(set((meta.get("items") or []) + [str(s) for s in e.get("related_specs", [])]))
            if e.get("analysis_path") and (project.dir / e["analysis_path"]).exists():
                shutil.move(str(project.dir / e["analysis_path"]), str(folder / "analysis.md"))
                meta["analysis"] = "analysis.md"
            _save_meta(folder, meta)
            moved.append(sid)
        data[f"{kind}_images"] = []
    if data.get("system_doc"):
        src = project.dir / data["system_doc"]
        if src.exists() and not system_path(project).exists():
            system_path(project).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(system_path(project)))
        data.pop("system_doc", None)
    icon_src = design_dir(project) / "icons" / "source"
    if icon_src.is_dir():
        for f in icon_src.iterdir():
            shutil.move(str(f), str(design_dir(project) / "icons" / f.name))
        icon_src.rmdir()
    for kind in ("hifi", "lofi", "system"):
        folder = design_dir(project) / kind
        if folder.is_dir() and not any(p.is_file() for p in folder.rglob("*")):
            shutil.rmtree(folder)
    _save(project, data)
    render_catalogue(project)
    return {"screens": moved}


# ---------------------------------------------------------------------------- status
def status(project: Project) -> dict:
    """Where the design lives, its screens, and which UI changes still need one."""
    from . import uxdesign
    data = _manifest(project)
    rows = screens(project)
    catalogues = sorted({spec["file"] for spec in (project.config.get("refs") or {}).values()
                         if isinstance(spec, dict) and spec.get("file")})
    if (design_dir(project) / "screens.md").exists():
        catalogues.append(_rel(project, design_dir(project) / "screens.md"))
    ui_items = []
    for item in project.items():
        if item.info()["status"] not in ("archived", "completed") and uxdesign.is_ui(project, item):
            st = uxdesign.state(project, item)
            ui_items.append({"item": item.id, "title": item.info()["title"], "designed": uxdesign.satisfied(st),
                             "cited": st["cited"], "broken": st["broken"], "unapproved": st["unapproved"]})
    playbook = project.config.get("playbooks") or {}
    return {"design_system": uxdesign.design_system(project),
            "screens_dir": uxdesign.screen_dirs(project),
            "reviews_dir": _rel(project, reviews_dir(project)),
            "screens": [{k: s[k] for k in ("id", "title", "status", "items", "path")} for s in rows],
            "catalogues": catalogues,
            "playbooks": {k: v.get("skill") for k, v in playbook.items() if isinstance(v, dict)},
            "technology": data.get("technology"),
            "open_conflicts": [c for c in data.get("conflicts", []) if not c.get("resolution")],
            "components": data.get("components", []),
            "legacy_assets": legacy_assets(project),
            "outside_layout": uxdesign.find_design_folders(project),
            "ui_items": ui_items, "needing_design": [u["item"] for u in ui_items if not u["designed"]],
            "awaiting_approval": sorted({s for u in ui_items for s in u["unapproved"]})}
