"""Design for changes that touch what users see.

A change is UI work when it carries a UI label (`ui_labels` in speky.yaml, default ui/ux/frontend) or has
a `## Design` section. Such a change must say which design it implements, so the implementer never
guesses: screen IDs (`screen:<id>`, resolved through `refs`), design files in the repo, or assets linked
with `speky design link`. "No new design needed: <why>" is a valid answer; "To be designed" is not done
yet. The project's design-system document (`paths.design_system`, else `.speky/context/design_system.md`
or the one registered with `speky design add --type system`) is required once there is UI work.

SPEKY checks and routes; finding an existing design or creating one with the project's design tool
(Stitch, Figma, hand-written HTML, …) is the agent's work (speky-design skill and any `ui` playbook).
"""
import json
import re
from pathlib import Path
from typing import List, Optional

from . import markdown as md
from .items import Item, Project

DEFAULT_UI_LABELS = ("ui", "ux", "frontend")
DESIGN_FILE_RE = re.compile(r"`([^`\n]+\.(?:png|jpe?g|webp|svg|html?|fig|pdf|md))`|\]\(([^)\s]+)\)", re.I)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".html", ".htm", ".pdf", ".fig"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "out", ".next", "coverage", ".speky",
             "__pycache__", "target", "Pods", ".dart_tool"}


def screen_dirs(project: Project) -> List[str]:
    """Folders holding screen designs (`paths.design_screens`: one path or a list)."""
    value = (project.config.get("paths") or {}).get("design_screens") or []
    return [value] if isinstance(value, str) else list(value)


def screens(project: Project, limit: int = 300) -> List[str]:
    out = []
    for d in screen_dirs(project):
        base = project.root / d
        for f in sorted(base.rglob("*")) if base.is_dir() else []:
            if f.is_file() and f.suffix.lower() in IMAGE_EXT:
                out.append(str(f.relative_to(project.root)))
                if len(out) >= limit:
                    return out
    return out


def find_design_folders(project: Project) -> List[str]:
    """Unregistered folders that look like design screens: a design/screen/mock/ux-ish name with 3+ images."""
    known = set(screen_dirs(project))
    found = []
    name_re = re.compile(r"design|screen|mock|wirefram|ux|ui[-_ ]|hifi|lofi|figma|stitch", re.I)
    for d in project.root.rglob("*"):
        if not d.is_dir() or any(p in SKIP_DIRS or p.startswith(".") for p in d.relative_to(project.root).parts):
            continue
        rel = str(d.relative_to(project.root))
        if not name_re.search(d.name) or any(rel == k or rel.startswith(k + "/") for k in known):
            continue
        images = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXT - {".pdf"}]
        if len(images) >= 3 and not any(rel.startswith(f + "/") for f in found):
            found.append(rel)
    return found[:10]
NOT_NEEDED_RE = re.compile(r"\bno (?:new )?(?:design|screens?|ui change)s? (?:is |are )?needed\b|\bnot needed\b"
                           r"|\bno ui change\b", re.I)
TO_DESIGN_RE = re.compile(r"\bto be designed\b|\bnot designed yet\b|\bTBD\b", re.I)

SECTION = """## Design
<!-- Which design this implements, so nobody guesses during implementation:
     - Screens: IDs from the screen catalogue (screen:<id>) or design files in the repo, per state
       (default, empty, error, loading).
     - Design system: {system}
     Look for an existing design first (`speky design status`, the screen catalogue). If there is none,
     write "To be designed" and `speky next` runs the design step. If nothing visual changes, write
     "No new design needed: <why>". -->
To be designed
"""


def ui_labels(project: Project) -> List[str]:
    return list(project.config.get("ui_labels") or DEFAULT_UI_LABELS)


UI_WORDS_RE = re.compile(r"\b(screens?|pages?|panels?|views?|buttons?|dialogs?|modals?|tabs?|forms?|layouts?|"
                         r"click(?:s|ed|ing)?|hover|keyboard|UI|UX|sidebar|toolbar|menus?|inspector|editor|"
                         r"dark mode|light mode|theme)\b", re.I)


def project_has_ui(project: Project) -> bool:
    """Signals that this project builds things people see: a design system, a ui playbook, UI labels in use."""
    if design_system(project) or set(project.config.get("playbooks") or {}) & set(ui_labels(project)):
        return True
    return any(set(i.load_status().get("labels") or []) & set(ui_labels(project)) for i in project.items())


def looks_user_facing(project: Project, item: Item) -> List[str]:
    """UI words in an unlabelled change of a UI project (a prompt to decide, not a verdict)."""
    if is_ui(project, item) or not project_has_ui(project):
        return []
    words = [m.group(0).lower() for m in UI_WORDS_RE.finditer(md.strip_comments(item.read_doc()))]
    return sorted(set(words)) if len(words) >= 3 else []


def has_ui_label(project: Project, item: Item) -> bool:
    return bool(set(item.load_status().get("labels") or []) & set(ui_labels(project)))


def is_ui(project: Project, item: Item) -> bool:
    return has_ui_label(project, item) or md.find_section(item.read_doc(), "design") is not None


def design_system(project: Project) -> Optional[str]:
    configured = (project.config.get("paths") or {}).get("design_system")
    candidates = [configured] if configured else []
    candidates.append(str((project.dir / "context" / "design_system.md").relative_to(project.root)))
    manifest = project.dir / "design" / "manifest.json"
    if manifest.exists():
        doc = json.loads(manifest.read_text()).get("system_doc")
        if doc:
            candidates.append(str((project.dir / doc).relative_to(project.root)))
    return next((c for c in candidates if c and (project.root / c).exists()), None)


def linked_assets(project: Project, item: Item) -> List[str]:
    manifest = project.dir / "design" / "manifest.json"
    if not manifest.exists():
        return []
    data = json.loads(manifest.read_text())
    out = []
    for kind in ("hifi", "lofi"):
        for img in data.get(f"{kind}_images", []):
            if any(str(s) == item.id or str(s).startswith(item.id + "-") for s in img.get("related_specs", [])):
                out.append(str((project.dir / "design" / kind / "source" / img["filename"]).relative_to(project.root)))
    return out


def state(project: Project, item: Item) -> dict:
    """What the item says about its design."""
    from . import refs
    text = md.strip_comments(item.read_doc())
    section = md.find_section(text, "design")
    body = "\n".join(section) if isinstance(section, list) else (section or "")
    cited, broken = [], []
    for c in refs.cited(project, body):
        (cited if c["read"] else broken).append(c["read"] or c["ref"])
    for m in DESIGN_FILE_RE.finditer(body):
        path = m.group(1) or m.group(2)
        if path.startswith(("http://", "https://")):
            cited.append(path)  # a design tool link (Stitch, Figma)
        elif (project.root / path).exists():
            cited.append(path)
        elif "/" in path:
            broken.append(path)
    cited += linked_assets(project, item)
    return {"ui": is_ui(project, item), "section": section is not None,
            "cited": list(dict.fromkeys(cited)), "broken": broken,
            "not_needed": bool(NOT_NEEDED_RE.search(body)),
            "to_design": bool(TO_DESIGN_RE.search(body)) or not body.strip(),
            "system": design_system(project)}


def satisfied(st: dict) -> bool:
    return st["not_needed"] or (bool(st["cited"]) and not st["to_design"])


def ensure_section(project: Project, item: Item) -> bool:
    """Add a `## Design` section to a UI change that has none (before ## Requirements)."""
    if not has_ui_label(project, item):
        return False
    text = item.read_doc()
    if md.find_section(text, "design") is not None:
        return False
    block = SECTION.format(system=f"`{design_system(project)}`" if design_system(project)
                           else "none yet — create it with the speky-design skill")
    at = re.search(r"^## Requirements", text, re.M)
    text = text[:at.start()] + block + "\n" + text[at.start():] if at else text.rstrip() + "\n\n" + block
    item.doc_path.write_text(text)
    return True
