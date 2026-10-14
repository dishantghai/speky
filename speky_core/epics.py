"""Epics: groups of stories sharing context — `.speky/epics/E001-slug/manifest.yaml` (same files as v2).

An epic may relate to a spec; its stories get `related_epic` (and the epic's spec in `related_specs`).
Other files in the epic folder are shared documents loaded into the context of its stories.
Progress is computed from the stories' statuses, never stored.
"""
import re
from typing import List, Optional

from . import yamlio
from .errors import SpekyError
from .items import DONE_STATUSES, Project, now, slugify


def epics_dir(project: Project):
    return project.dir / "epics"


def _folder(project: Project, ref: str):
    base = epics_dir(project)
    if not base.is_dir():
        return None
    m = re.match(r"^[Ee](\d+)$", ref.strip())
    wanted = {ref.strip().lower()} | ({f"e{int(m.group(1)):03d}"} if m else set())
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d.name.lower() == ref.lower() or d.name.split("-", 1)[0].lower() in wanted):
            return d
    return None


def _load(folder) -> dict:
    return yamlio.load((folder / "manifest.yaml").read_text()) or {}


def _save(folder, data: dict) -> None:
    data["updated"] = now()
    (folder / "manifest.yaml").write_text(yamlio.dump(data))


def get(project: Project, ref: str) -> dict:
    folder = _folder(project, ref)
    if not folder or not (folder / "manifest.yaml").exists():
        raise SpekyError("epic_not_found", f"No epic {ref}.", "Run `speky epic list --json`.")
    data = _load(folder)
    stories = []
    for sid in data.get("stories") or []:
        item = project.try_find(str(sid))
        stories.append({"id": str(sid), "title": item.info()["title"] if item else "(missing)",
                        "status": item.info()["status"] if item else "missing"})
    done = len([s for s in stories if s["status"] in DONE_STATUSES])
    doing = len([s for s in stories if s["status"] in ("in_progress", "review")])
    docs = sorted(p.name for p in folder.iterdir() if p.is_file() and p.name != "manifest.yaml")
    return {"id": data.get("id", folder.name.split("-", 1)[0]), "name": data.get("name", ""),
            "description": data.get("description", ""), "related_spec": data.get("related_spec"),
            "priority": data.get("priority", "P1"), "stories": stories, "docs": docs,
            "progress": {"total": len(stories), "completed": done, "in_progress": doing,
                         "pending": len(stories) - done - doing},
            "folder": str(folder.relative_to(project.root))}


def list_all(project: Project) -> List[dict]:
    base = epics_dir(project)
    if not base.is_dir():
        return []
    return [get(project, d.name) for d in sorted(base.iterdir())
            if d.is_dir() and (d.name[:1].upper() == "E") and (d / "manifest.yaml").exists()]


def add(project: Project, name: str, related_spec: str = None, stories: List[str] = None,
        description: str = "", priority: str = "P1") -> dict:
    if related_spec and not project.try_find(related_spec):
        raise SpekyError("item_not_found", f"No spec {related_spec}.")
    base = epics_dir(project)
    base.mkdir(parents=True, exist_ok=True)
    numbers = [int(m.group(1)) for d in base.iterdir() for m in [re.match(r"^E(\d+)", d.name)] if m]
    epic_id = f"E{max(numbers, default=0) + 1:03d}"
    folder = base / f"{epic_id}-{slugify(name)}"
    folder.mkdir()
    related = project.try_find(related_spec).id if related_spec else None
    _save(folder, {"id": epic_id, "name": name,
                   "description": description or "Epic for grouping related stories",
                   "created": now(), "related_spec": related, "priority": priority,
                   "stories": [], "docs": []})
    for sid in stories or []:
        attach(project, epic_id, sid)
    return get(project, epic_id)


def attach(project: Project, epic_ref: str, story_ref: str) -> dict:
    folder = _folder(project, epic_ref)
    if not folder:
        raise SpekyError("epic_not_found", f"No epic {epic_ref}.")
    item = project.find(story_ref)
    if item.kind != "story":
        raise SpekyError("not_a_story", f"{item.id} is a spec; epics group stories.",
                         "Link a spec with `speky epic add ... --spec <id>` instead.")
    data = _load(folder)
    stories = [str(s) for s in data.get("stories") or []]
    if item.id not in stories:
        stories.append(item.id)
        data["stories"] = stories
        _save(folder, data)
    status = item.load_status()
    status["related_epic"] = data["id"]
    if data.get("related_spec"):
        related = status.get("related_specs", []) or []
        if data["related_spec"] not in related:
            related.append(data["related_spec"])
        status["related_specs"] = related
    item.save_status(status)
    return get(project, data["id"])


def detach(project: Project, epic_ref: str, story_ref: str) -> dict:
    folder = _folder(project, epic_ref)
    if not folder:
        raise SpekyError("epic_not_found", f"No epic {epic_ref}.")
    data = _load(folder)
    item = project.find(story_ref)
    data["stories"] = [str(s) for s in data.get("stories") or [] if str(s) != item.id]
    _save(folder, data)
    status = item.load_status()
    if status.get("related_epic") == data["id"]:
        status.pop("related_epic")
        item.save_status(status)
    return get(project, data["id"])


def epic_of(project: Project, item_id: str) -> Optional[dict]:
    for epic in list_all(project):
        if any(s["id"] == item_id for s in epic["stories"]):
            return epic
    return None
