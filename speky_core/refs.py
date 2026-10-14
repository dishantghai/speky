"""References to artifacts outside SPEKY (`adr:0021`, `screen:RV-E2-held`, `item:019`).

Configured in `.speky/speky.yaml`:

    refs:
      adr: {glob: "docs/adr/{id}-*.md"}
      screen: {file: "docs/ux/screens/README.md", contains: "`{id}`"}

`speky refs` scans SPEKY's own files for `<kind>:<id>` and reports references that don't resolve.
"""
import glob as globlib
import re
from pathlib import Path
from typing import Dict, List, Optional

from .items import Project


def _kinds(project: Project) -> Dict[str, dict]:
    kinds = dict(project.config.get("refs") or {})
    kinds.setdefault("item", {"builtin": "item"})
    kinds.setdefault("screen", {"builtin": "screen"})  # .speky/design/screens/<id>/ (or paths.design_screens)
    return kinds


def resolve(project: Project, kind: str, ref_id: str, spec: dict) -> bool:
    if spec.get("builtin") == "item":
        return project.try_find(ref_id) is not None
    if spec.get("builtin") == "screen":
        from . import design
        return design.find_screen(project, ref_id) is not None
    if "glob" in spec:
        return bool(globlib.glob(str(project.root / spec["glob"].replace("{id}", ref_id))))
    if "file" in spec:
        path = project.root / spec["file"]
        needle = spec.get("contains", "{id}").replace("{id}", ref_id)
        return path.exists() and needle in path.read_text()
    return False


def locate(project: Project, kind: str, ref_id: str, spec: dict) -> Optional[str]:
    """The file a reference points at (for context packets), or None."""
    if spec.get("builtin") == "item":
        item = project.try_find(ref_id)
        return str(item.doc_path.relative_to(project.root)) if item else None
    if spec.get("builtin") == "screen":
        from . import design
        s = design.find_screen(project, ref_id)
        return s["path"] if s else None
    if "glob" in spec:
        hits = sorted(globlib.glob(str(project.root / spec["glob"].replace("{id}", ref_id))))
        return str(Path(hits[0]).relative_to(project.root)) if hits else None
    if "file" in spec and resolve(project, kind, ref_id, spec):
        return spec["file"]
    return None


def cited(project: Project, text: str) -> List[dict]:
    """`<kind>:<id>` references in a text, with the file each one points at."""
    kinds = _kinds(project)
    pattern = re.compile(r"(?<![\w/])(" + "|".join(re.escape(k) for k in kinds) + r"):([A-Za-z0-9][\w.\-]*\w)")
    out, seen = [], set()
    for m in pattern.finditer(text):
        ref = f"{m.group(1)}:{m.group(2)}"
        if ref not in seen:
            seen.add(ref)
            out.append({"ref": ref, "read": locate(project, m.group(1), m.group(2), kinds[m.group(1)])})
    return out


def scan(project: Project) -> dict:
    kinds = _kinds(project)
    pattern = re.compile(r"(?<![\w/])(" + "|".join(re.escape(k) for k in kinds) + r"):([A-Za-z0-9][\w.\-]*\w)")
    found: List[dict] = []
    files = [p for p in project.dir.rglob("*.md") if "backups" not in p.parts]
    for path in files:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            for m in pattern.finditer(line):
                kind, ref_id = m.group(1), m.group(2)
                found.append({"ref": f"{kind}:{ref_id}", "kind": kind, "id": ref_id,
                              "file": str(path.relative_to(project.root)), "line": n,
                              "resolved": resolve(project, kind, ref_id, kinds[kind])})
    broken = [f for f in found if not f["resolved"]]
    return {"kinds": sorted(kinds), "references": len(found), "broken": broken, "valid": not broken}
