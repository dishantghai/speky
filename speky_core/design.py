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
SCREEN_KINDS = ("hifi", "lofi", "wireframe", "flow", "reference")  # reference: snapshots of what is built
SCREEN_STATUSES = ("draft", "approved", "superseded", "rejected")  # rejected: explored, not chosen
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
SCREENS_LIST = "screens.yaml"  # several screens kept as single files in one folder


def _load_yaml(path: Path):
    if path.exists():
        return yamlio.load(path.read_text())
    return None


def _load_meta(folder: Path) -> dict:
    data = _load_yaml(folder / SCREEN_META)
    return data if isinstance(data, dict) else {}


def _save_meta(folder: Path, meta: dict) -> None:
    (folder / SCREEN_META).write_text(yamlio.dump(meta))


def _row(project: Project, meta: dict, sid: str, files: List[Path], path: Path, group: str, source: dict) -> Dict:
    return {"id": sid, "title": meta.get("title", sid), "status": meta.get("status", "draft"),
            "kind": meta.get("kind", "hifi"), "states": meta.get("states") or [],
            "items": [str(i) for i in meta.get("items") or []],
            "files": [_rel(project, f) for f in files], "path": _rel(project, path), "group": group,
            "review": meta.get("review"), "superseded_by": meta.get("superseded_by"), "_source": source}


def _design_files(folder: Path) -> List[Path]:
    return [f for f in sorted(folder.rglob("*")) if f.is_file() and f.suffix.lower() in DESIGN_EXT]


def screens(project: Project) -> List[Dict]:
    """Every screen: {id, title, status, kind, states, items, files, path, group, review, superseded_by}.

    Under a screens root: a folder with `screen.yaml` is a screen (at any depth, so screens can be grouped,
    e.g. `run-view/v2-E/held/`); a `screens.yaml` lists several screens kept as single files in its folder;
    in the default root a top-level folder without metadata is a screen too (ID = folder name); in an
    override root, design files lying directly in it are screens (ID = slug of the file name)."""
    out, seen = [], set()
    default = project.root / layout.DEFAULTS["design_screens"].split("<")[0].rstrip("/")

    def add_row(row):
        if row["id"] not in seen:
            seen.add(row["id"])
            out.append(row)

    for root in layout.paths(project, "design_screens"):
        if not root.is_dir():
            continue
        claimed = set()

        def walk(folder: Path):
            group = str(folder.relative_to(root)) if folder != root else ""
            listed = _load_yaml(folder / SCREENS_LIST)
            for i, entry in enumerate(listed if isinstance(listed, list) else []):
                if isinstance(entry, dict) and entry.get("id"):
                    files = [folder / f for f in entry.get("files") or []]
                    claimed.update(f.resolve() for f in files)
                    add_row(_row(project, entry, str(entry["id"]), files, files[0] if len(files) == 1 else folder,
                                 group, {"kind": "list", "file": folder / SCREENS_LIST, "index": i}))
            for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
                if (sub / SCREEN_META).exists():
                    meta = _load_meta(sub)
                    add_row(_row(project, meta, str(meta.get("id") or sub.name), _design_files(sub), sub,
                                 group, {"kind": "dir", "folder": sub}))
                else:
                    has_meta = any(sub.rglob(SCREEN_META)) or any(sub.rglob(SCREENS_LIST))
                    if root == default and folder == root and not has_meta:
                        add_row(_row(project, {}, sub.name, _design_files(sub), sub, group,
                                     {"kind": "dir", "folder": sub}))
                    elif has_meta:
                        walk(sub)

        walk(root)
        if root != default:
            for f in sorted(root.iterdir()):
                if f.is_file() and f.suffix.lower() in DESIGN_EXT and f.resolve() not in claimed:
                    add_row({**_row(project, {}, slugify(f.stem), [f], f, "", {"kind": "file"}),
                             "title": f.stem, "status": None, "kind": None})
    return out


def find_screen(project: Project, sid: str) -> Optional[Dict]:
    rows = screens(project)
    for s in rows:
        if s["id"] == sid:
            return s
    for s in rows:
        if s["id"].lower() == sid.lower() or slugify(s["id"]) == slugify(sid):
            return s
    return None


def _record(project: Project, sid: str):
    """(screen, meta, save) for a screen that has metadata; save(meta) writes it back."""
    s = find_screen(project, sid) or find_screen(project, Path(sid).stem)
    if not s:
        raise SpekyError("screen_not_found", f"No screen '{sid}'.", "Run `speky design screen list --json`.")
    src = s["_source"]
    if src["kind"] == "dir":
        folder = src["folder"]
        meta = _load_meta(folder) or {"id": s["id"]}

        def save(m):
            _save_meta(folder, m)
        return s, meta, save
    if src["kind"] == "list":
        listed = _load_yaml(src["file"])

        def save(m):
            listed[src["index"]] = m
            src["file"].write_text(yamlio.dump(listed))
        return s, dict(listed[src["index"]]), save
    raise SpekyError("screen_is_a_file", f"Screen '{s['id']}' is a single file ({s['path']}) without metadata.",
                     f"Import it: `speky design screen add {s['id']} \"{s['path']}\" --move`.")


def screen_add(project: Project, sid: str, files: List[str], title: str = "", kind: str = "hifi",
               states: List[str] = None, item: str = None, source: str = "", move: bool = False,
               group: str = "") -> dict:
    if not ID_RE.match(sid):
        raise SpekyError("bad_screen_id", f"'{sid}' is not a valid screen ID.",
                         "Use letters, digits, '.', '_' and '-', e.g. layers-editor-main or RV-E3-held.")
    if kind not in SCREEN_KINDS:
        raise SpekyError("bad_screen_kind", f"Kind must be one of {', '.join(SCREEN_KINDS)}.")
    existing_row = find_screen(project, sid)
    if existing_row and existing_row["id"] == sid and existing_row["_source"]["kind"] == "dir":
        folder = existing_row["_source"]["folder"]
    else:
        folder = screens_root(project) / group / sid if group else screens_root(project) / sid
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
    if s["_source"]["kind"] != "file":
        _, meta, save = _record(project, s["id"])
        if item.id not in (meta.get("items") or []):
            meta["items"] = (meta.get("items") or []) + [item.id]
        save(meta)
    uxdesign.cite_screen(project, item, s["id"])
    render_catalogue(project)
    return {"screen": s["id"], "item": item.id}


def approve(project: Project, sid: str, by: str, note: str = "") -> dict:
    from . import journal
    s, meta, save = _record(project, sid)
    meta.update(status="approved", approved_by=by, approved_at=now())
    save(meta)
    journal.decide(project, f"Design {s['id']} approved by {by}" + (f": {note}" if note else ""),
                   "decision", (meta.get("items") or [None])[0])
    render_catalogue(project)
    return {"screen": s["id"], "status": "approved"}


def supersede(project: Project, old: str, new: str) -> dict:
    _, ometa, osave = _record(project, old)
    _, nmeta, nsave = _record(project, new)
    ometa.update(status="superseded", superseded_by=new)
    osave(ometa)
    nmeta["supersedes"] = old
    nmeta["items"] = sorted(set((nmeta.get("items") or []) + (ometa.get("items") or [])))
    nsave(nmeta)
    render_catalogue(project)
    return {"superseded": old, "by": new}


def review(project: Project, sid: str, review_file: str, result: str) -> dict:
    if result not in ("pass", "fail"):
        raise SpekyError("bad_result", "Result is pass or fail.")
    s, meta, save = _record(project, sid)
    src = Path(review_file)
    if not src.exists():
        raise SpekyError("source_not_found", f"{review_file} does not exist.")
    target_dir = reviews_dir(project)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{date.today().isoformat()}-{s['id']}.md"
    if src.resolve() != target.resolve():
        shutil.copyfile(src, target)
    meta["review"] = {"file": _rel(project, target), "result": result, "at": now()}
    save(meta)
    render_catalogue(project)
    return {"screen": s["id"], "review": meta["review"]}


def record_analysis(project: Project, sid: str, analysis_file: str) -> dict:
    """The agent's analysis of a screen (tokens, layout, components), stored next to it."""
    s, meta, save = _record(project, sid)
    src = Path(analysis_file)
    if not src.exists():
        raise SpekyError("source_not_found", f"{analysis_file} does not exist.")
    if s["_source"]["kind"] == "dir":
        target = s["_source"]["folder"] / "analysis.md"
        meta["analysis"] = "analysis.md"
    else:
        target = s["_source"]["file"].parent / f"{s['id']}.analysis.md"
        meta["analysis"] = target.name
    shutil.copyfile(src, target)
    save(meta)
    return {"screen": s["id"], "analysis": _rel(project, target)}


def render_catalogue(project: Project) -> None:
    """`.speky/design/screens.md`: every screen by group, with status, states, items and review."""
    rows = screens(project)
    if not rows and not (design_dir(project) / "screens.md").exists():
        return
    lines = ["# Screens", "", "_Generated by SPEKY (`speky design screen …`). Cite a screen as `screen:<id>` in a "
             "change's `## Design`. A new iteration gets a new ID; the old one is superseded._", ""]
    groups: Dict[str, List[Dict]] = {}
    for s in rows:
        groups.setdefault(s.get("group") or "", []).append(s)
    for group in sorted(groups):
        if group:
            lines += [f"## {group}", ""]
        lines += ["| ID | Title | Status | States | Items | Review | Path |", "|---|---|---|---|---|---|---|"]
        for s in groups[group]:
            rev = f"{s['review']['result']} ({s['review']['file']})" if isinstance(s.get("review"), dict) else \
                (str(s["review"]) if s.get("review") else "")
            status_ = (s["status"] or "—") + (f" → {s['superseded_by']}" if s.get("superseded_by") else "")
            lines.append(f"| `{s['id']}` | {s['title']} | {status_} | {', '.join(s['states'])} | "
                         f"{', '.join(s['items'])} | {rev} | `{s['path']}` |")
        lines.append("")
    design_dir(project).mkdir(parents=True, exist_ok=True)
    (design_dir(project) / "screens.md").write_text("\n".join(lines).rstrip() + "\n")


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
            "screens": [{k: s[k] for k in ("id", "title", "status", "items", "path", "group")} for s in rows],
            "catalogues": catalogues,
            "playbooks": {k: v.get("skill") for k, v in playbook.items() if isinstance(v, dict)},
            "technology": data.get("technology"),
            "open_conflicts": [c for c in data.get("conflicts", []) if not c.get("resolution")],
            "components": data.get("components", []),
            "legacy_assets": legacy_assets(project),
            "outside_layout": uxdesign.find_design_folders(project),
            "ui_items": ui_items, "needing_design": [u["item"] for u in ui_items if not u["designed"]],
            "awaiting_approval": sorted({s for u in ui_items for s in u["unapproved"]})}
