"""Design for changes that touch what users see.

A change is UI work when it carries a UI label (`ui_labels` in speky.yaml, default ui/ux/frontend) or has
a `## Design` section. Such a change must say which design it implements, so the implementer never
guesses: screens (`screen:<id>`) or design files that live in the design locations (`speky layout`), or
"No new design needed: <why>". "To be designed" is not done yet. A cited screen must be approved before the
change is built. The project needs one design-system document (`.speky/design/system.md` by default).

SPEKY checks and routes; finding an existing design or creating one with the project's design tool
(Stitch, Figma, hand-written HTML, …) is the agent's work (speky-design skill and any `ui` playbook).
"""
import re
from pathlib import Path
from typing import List, Optional

from . import layout
from . import markdown as md
from .items import Item, Project

DEFAULT_UI_LABELS = ("ui", "ux", "frontend")
DESIGN_FILE_RE = re.compile(r"`([^`\n]+\.(?:png|jpe?g|webp|svg|html?|fig|pdf))`|\]\(([^)\s]+)\)", re.I)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".html", ".htm", ".pdf", ".fig"}
NOT_NEEDED_RE = re.compile(r"\bno (?:new )?(?:design|screens?|ui change)s? (?:is |are )?needed\b|\bnot needed\b"
                           r"|\bno ui change\b", re.I)
TO_DESIGN_RE = re.compile(r"\bto be designed\b|\bnot designed yet\b|\bTBD\b", re.I)
UI_WORDS_RE = re.compile(r"\b(screens?|pages?|panels?|views?|buttons?|dialogs?|modals?|tabs?|forms?|layouts?|"
                         r"click(?:s|ed|ing)?|hover|keyboard|UI|UX|sidebar|toolbar|menus?|inspector|editor|"
                         r"dark mode|light mode|theme)\b", re.I)

SECTION = """## Design
<!-- Which design this implements, so nobody guesses during implementation:
     - Screens: screen:<id> from the screen catalogue ({screens}), per state (default, empty, error, loading).
     - Design system: {system}
     Look for an existing design first (`speky design status`). If there is none, write "To be designed"
     and `speky next` runs the design step. If nothing visual changes, write "No new design needed: <why>". -->
To be designed
"""


# ---------------------------------------------------------------------------- where design lives
def design_system(project: Project) -> Optional[str]:
    """The design-system document, if there is one (standard location, override, or the v2 location
    until `speky migrate` moves it)."""
    candidates = [layout.path(project, "design_system"), project.dir / "context" / "design_system.md"]
    hit = next((c for c in candidates if c.exists()), None)
    return str(hit.relative_to(project.root)) if hit else None


def screen_dirs(project: Project) -> List[str]:
    return [str(p.relative_to(project.root)) for p in layout.paths(project, "design_screens")]


def _under_design_locations(project: Project, rel: str) -> bool:
    roots = layout.paths(project, "design_screens") + layout.paths(project, "design_reviews") + \
        [project.dir / "design"]
    target = (project.root / rel).resolve()
    return any(target == r.resolve() or r.resolve() in target.parents for r in roots)


def find_design_folders(project: Project) -> List[str]:
    """Folders outside the design locations that look like screen designs (a design-ish name, 3+ images)."""
    known = screen_dirs(project) + [str((project.dir / "design").relative_to(project.root))]
    found = []
    name_re = re.compile(r"design|screen|mock|wirefram|ux|ui[-_ ]|hifi|lofi|figma|stitch", re.I)
    for d in project.root.rglob("*"):
        if not d.is_dir() or any(p in layout.SKIP_DIRS or p.startswith(".") for p in d.relative_to(project.root).parts):
            continue
        rel = str(d.relative_to(project.root))
        if not name_re.search(d.name) or any(rel == k or rel.startswith(k + "/") or k.startswith(rel + "/")
                                             for k in known):
            continue
        images = 0
        for f in d.rglob("*"):
            if f.is_file() and f.suffix.lower() in IMAGE_EXT - {".pdf"}:
                images += 1
                if images >= 3:
                    break
        if images >= 3:
            found.append(rel)
    found.sort(key=lambda r: (r.count("/"), r))  # the outermost folder of each group
    outer = []
    for rel in found:
        if not any(rel.startswith(o + "/") for o in outer):
            outer.append(rel)
    return outer[:10]


# ---------------------------------------------------------------------------- which items are UI work
def ui_labels(project: Project) -> List[str]:
    return list(project.config.get("ui_labels") or DEFAULT_UI_LABELS)


def has_ui_label(project: Project, item: Item) -> bool:
    return bool(set(item.load_status().get("labels") or []) & set(ui_labels(project)))


def is_ui(project: Project, item: Item) -> bool:
    return has_ui_label(project, item) or md.find_section(item.read_doc(), "design") is not None


def project_has_ui(project: Project) -> bool:
    """Signals that this project builds things people see: a design system, screens, a ui playbook, UI labels."""
    from . import design
    if design_system(project) or design.screens(project) or \
            set(project.config.get("playbooks") or {}) & set(ui_labels(project)):
        return True
    return any(set(i.load_status().get("labels") or []) & set(ui_labels(project)) for i in project.items())


def looks_user_facing(project: Project, item: Item) -> List[str]:
    """UI words in an unlabelled change of a UI project (a prompt to decide, not a verdict)."""
    if is_ui(project, item) or not project_has_ui(project):
        return []
    words = [m.group(0).lower() for m in UI_WORDS_RE.finditer(md.strip_comments(item.read_doc()))]
    return sorted(set(words)) if len(words) >= 3 else []


# ---------------------------------------------------------------------------- what an item says
def state(project: Project, item: Item) -> dict:
    """What the item says about its design: cited screens/files, broken ones, ones outside the design
    locations, screens still waiting for approval."""
    from . import design, refs
    body = md.find_section(md.strip_comments(item.read_doc()), "design") or ""
    cited, broken, outside, unapproved = [], [], [], []
    for c in refs.cited(project, body):
        if c["ref"].startswith("screen:"):
            s = design.find_screen(project, c["ref"].split(":", 1)[1])
            if s:
                cited.append(s["path"])
                if s["status"] == "draft":
                    unapproved.append(s["id"])
                elif s["status"] == "superseded":
                    broken.append(f"{c['ref']} (superseded by {s['superseded_by']})")
                elif s["status"] == "rejected":
                    broken.append(f"{c['ref']} (explored, not chosen)")
                continue
        (cited if c["read"] else broken).append(c["read"] or c["ref"])
    links = []
    for m in DESIGN_FILE_RE.finditer(body):
        path = m.group(1) or m.group(2)
        if path.startswith(("http://", "https://")):
            links.append(path)  # a design-tool link: fine as a pointer, but the design must be in the repo
        elif (project.root / path).exists():
            cited.append(path)
            if not _under_design_locations(project, path):
                outside.append(path)
        elif "/" in path:
            broken.append(path)
    for s in design.screens(project):
        if item.id in (s["items"] or []) and s["path"] not in cited:
            cited.append(s["path"])
            if s["status"] == "draft":
                unapproved.append(s["id"])
    not_needed = bool(NOT_NEEDED_RE.search(body))
    return {"ui": is_ui(project, item), "section": bool(body), "cited": list(dict.fromkeys(cited)),
            "links": links, "broken": broken, "outside": outside,
            # screens cited only as a reference ("no new design needed") need no new approval
            "unapproved": [] if not_needed else sorted(set(unapproved)),
            "not_needed": not_needed,
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
    system = design_system(project)
    block = SECTION.format(system=f"`{system}`" if system else "none yet — create it (speky-design skill)",
                           screens=", ".join(f"`{d}`" for d in screen_dirs(project)))
    at = re.search(r"^## Requirements", text, re.M)
    text = text[:at.start()] + block + "\n" + text[at.start():] if at else text.rstrip() + "\n\n" + block
    item.doc_path.write_text(text)
    return True


def cite_screen(project: Project, item: Item, sid: str) -> None:
    """Put `screen:<id>` into the item's `## Design` (replacing "To be designed")."""
    text = item.read_doc()
    ref = f"screen:{sid}"
    if ref in text:
        return
    if md.find_section(text, "design") is None:
        ensure_section(project, item) if has_ui_label(project, item) else None
        text = item.read_doc()
        if md.find_section(text, "design") is None:
            at = re.search(r"^## Requirements", text, re.M)
            block = "## Design\n"
            text = text[:at.start()] + block + "\n" + text[at.start():] if at else text.rstrip() + "\n\n" + block
    if TO_DESIGN_RE.search(text.split("## Design", 1)[1].split("\n## ", 1)[0]):
        head, rest = text.split("## Design", 1)
        section, sep, tail = rest.partition("\n## ")
        section = TO_DESIGN_RE.sub(f"- {ref}", section, count=1)
        text = head + "## Design" + section + sep + tail
    else:
        head, rest = text.split("## Design", 1)
        section, sep, tail = rest.partition("\n## ")
        text = head + "## Design" + section.rstrip("\n") + f"\n- {ref}\n" + ("\n" if sep else "") + sep.lstrip("\n") + tail
    item.doc_path.write_text(text)


def task_screens(project: Project, task: dict) -> List[dict]:
    """Screens a task works from: its `screen:<id>` references, and screens that name the task."""
    from . import design
    rows = design.screens(project)
    wanted = {r.split(":", 1)[1] for r in task.get("refs") or [] if r.startswith("screen:")}
    return [s for s in rows if s["id"] in wanted or task["id"] in (s["items"] or [])]

