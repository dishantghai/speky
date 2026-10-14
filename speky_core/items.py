"""Changes: v2 spec folders (`.speky/specs/NNN-slug`) and story folders (`.speky/stories/X001-slug`).

A v2 item folder *is* a v3 change. This module reads and writes them without moving or renaming
anything, and normalises the different `status.json` shapes v2 commands wrote.
"""
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import config
from .errors import SpekyError

SPEC_STATUSES = ["draft", "ready", "in_progress", "review", "completed", "archived"]
DONE_STATUSES = {"completed", "archived", "done"}
STORY_PREFIXES = {"feature": "F", "bug": "B", "enhancement": "E", "tech_debt": "T", "spike": "S"}
PRIORITY_ORDER = {"P0": 0, "critical": 0, "P1": 1, "high": 1, "P2": 2, "medium": 2, "P3": 3, "low": 3}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "item"


def write_json(path: Path, data) -> None:
    """Atomic write so a reader never sees half a file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


@dataclass
class Item:
    path: Path
    kind: str  # "spec" | "story"

    @property
    def id(self) -> str:
        return self.path.name.split("-", 1)[0]

    @property
    def slug(self) -> str:
        return self.path.name.split("-", 1)[1] if "-" in self.path.name else ""

    @property
    def doc_path(self) -> Path:
        name = "spec.md" if self.kind == "spec" else "story.md"
        doc = self.path / name
        if not doc.exists():
            other = self.path / ("story.md" if self.kind == "spec" else "spec.md")
            if other.exists():
                return other
        return doc

    @property
    def status_path(self) -> Path:
        return self.path / "status.json"

    def read_doc(self) -> str:
        return self.doc_path.read_text() if self.doc_path.exists() else ""

    def load_status(self) -> dict:
        data = {}
        if self.status_path.exists():
            try:
                data = json.loads(self.status_path.read_text())
            except json.JSONDecodeError as e:
                raise SpekyError("status_unreadable", f"{self.status_path} is not valid JSON: {e}",
                                 "Fix the JSON by hand, or delete the file and run `speky migrate --apply`.")
        return data

    def save_status(self, data: dict) -> None:
        data.setdefault("id", self.id)
        data["updated_at"] = now()
        write_json(self.status_path, data)

    def update_status(self, **changes) -> dict:
        data = self.load_status()
        data.update(changes)
        self.save_status(data)
        return data

    def info(self) -> dict:
        """Normalised view over the v2 status.json shapes."""
        raw = self.load_status()
        status = raw.get("status", "draft")
        if status == "done":
            status = "completed"
        return {
            "id": self.id,
            "kind": self.kind,
            "type": raw.get("type", "spec" if self.kind == "spec" else "feature"),
            "title": raw.get("title") or raw.get("name") or self.slug.replace("-", " "),
            "status": status,
            "priority": raw.get("priority", "P2"),
            "dependencies": [str(d) for d in raw.get("dependencies", []) or []],
            "gates": raw.get("gates", []),
            "links": raw.get("links", []),
            "validation": raw.get("validation", {}),
            "verification": raw.get("verification", {}),
            "base_sha": raw.get("base_sha"),
            "path": str(self.path),
        }


class Project:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = config.speky_dir(self.root)
        self.specs_dir = self.dir / "specs"
        self.stories_dir = self.dir / "stories"
        self.capabilities_dir = self.dir / "capabilities"

    CAPABILITIES_README = ("# Living specs\n\nOne folder per capability: `<capability>/spec.md` says how the system behaves "
                           "now. Changes update them when they are archived (`speky archive`). This file keeps the "
                           "folder in git while it is empty.\n")

    def ensure_capabilities_dir(self) -> None:
        """Create `.speky/capabilities/` with a README, so git keeps the folder even while it is empty."""
        self.capabilities_dir.mkdir(parents=True, exist_ok=True)
        readme = self.capabilities_dir / "README.md"
        if not readme.exists():
            readme.write_text(self.CAPABILITIES_README)

    @classmethod
    def open(cls, start: Path = None, require: bool = True) -> "Project":
        project = cls(config.find_root(start))
        if require and not project.dir.is_dir():
            raise SpekyError("not_initialized", f"No .speky/ folder in {project.root} or its parents.",
                             'Run `speky init "<idea>"`, `speky init --from-project`, or `speky migrate --apply`.')
        return project

    @property
    def config(self) -> dict:
        return config.load(self.root)

    def items(self) -> List[Item]:
        found = []
        for base, kind in ((self.specs_dir, "spec"), (self.stories_dir, "story")):
            if base.is_dir():
                found += [Item(d, kind) for d in sorted(base.iterdir())
                          if d.is_dir() and re.match(r"^[A-Za-z]?\d", d.name)]
        return found

    def find(self, ref: str) -> Item:
        item = self.try_find(ref)
        if not item:
            raise SpekyError("item_not_found", f"No spec or story matches '{ref}'.",
                             "Run `speky state --json` to list items and their IDs.")
        return item

    def try_find(self, ref: str) -> Optional[Item]:
        if not ref:
            return None
        ref = ref.strip()
        wanted = {ref.lower()}
        match = re.match(r"^([A-Za-z]?)(\d+)$", ref)  # "1" -> "001", "f1" -> "F001"
        if match:
            wanted.add(f"{match.group(1)}{int(match.group(2)):03d}".lower())
        items = self.items()
        for item in items:
            if item.path.name.lower() == ref.lower() or item.id.lower() in wanted:
                return item
        # a unique part of the folder name ("billing", "user login"); ambiguous names match nothing
        slug = re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-")
        named = [i for i in items if slug and slug in i.path.name.lower().split("-", 1)[-1]] if not match else []
        return named[0] if len(named) == 1 else None

    def next_id(self, kind: str, story_type: str = "feature") -> str:
        prefix = "" if kind == "spec" else STORY_PREFIXES.get(story_type, "F")
        base = self.specs_dir if kind == "spec" else self.stories_dir
        pattern = re.compile(rf"^{re.escape(prefix)}(\d+)", re.IGNORECASE)
        highest = 0
        if base.is_dir():
            for d in base.iterdir():
                m = pattern.match(d.name) if d.is_dir() else None
                if m:
                    highest = max(highest, int(m.group(1)))
        # High-water mark: a deleted item's number is never handed out again
        counters_path = self.dir / "ids.json"
        counters = json.loads(counters_path.read_text()) if counters_path.exists() else {}
        key = prefix or "spec"
        next_n = max(highest, int(counters.get(key, 0))) + 1
        counters[key] = next_n
        write_json(counters_path, counters)
        number = f"{prefix}{next_n:03d}"
        if self.config.get("id_style") == "hash":
            number += "x" + secrets.token_hex(2)  # branch-safe suffix; the letter keeps the number parseable
        return number

    def create(self, kind: str, title: str, story_type: str = "feature", size: str = "change",
               body: str = None, priority: str = "P2", dependencies: List[str] = None) -> Item:
        from .templates import change_template
        if kind not in ("spec", "story"):
            raise SpekyError("bad_kind", f"Unknown kind '{kind}'.", "Use `spec` or `story`.")
        if kind == "story" and story_type not in STORY_PREFIXES:
            raise SpekyError("bad_story_type", f"Unknown story type '{story_type}'.",
                             f"Use one of: {', '.join(STORY_PREFIXES)}.")
        for dep in dependencies or []:
            if not self.try_find(dep):
                raise SpekyError("unknown_dependency", f"Dependency '{dep}' does not exist.",
                                 "Create it first or drop it from --deps.")
        item_id = self.next_id(kind, story_type)
        base = self.specs_dir if kind == "spec" else self.stories_dir
        path = base / f"{item_id}-{slugify(title)}"
        path.mkdir(parents=True)
        item = Item(path, kind)
        item.doc_path.write_text(body if body is not None else change_template(title, size, kind))
        status = {
            "id": item_id, "status": "draft", "created": now(), "source": "speky-v3",
            "priority": priority, "dependencies": list(dependencies or []), "size": size, "kind": kind,
        }
        if kind == "spec":
            status["name"] = title
        else:
            status.update({"title": title, "type": story_type})
        item.save_status(status)
        return item
