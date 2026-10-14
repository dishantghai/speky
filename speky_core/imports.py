"""External knowledge and prototype code coming into SPEKY (v2's import, import-status, reconcile and
poc-import), on v2's layout: `.speky/imports/<name>/source/` + `manifest.json`.

SPEKY registers sources and records what came out of them; turning documents or code into specs, tasks,
knowledge and ADRs — and reconciling code with imported documents — is judgement work for the agent
(speky-import skill).
"""
import json
import shutil
from pathlib import Path
from typing import List

from .errors import SpekyError
from .items import Project, now, slugify, write_json

DOC_TYPES = {".md": "markdown", ".txt": "text", ".pdf": "pdf", ".docx": "docx", ".html": "html",
             ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".csv": "csv"}


def imports_dir(project: Project) -> Path:
    return project.dir / "imports"


def _manifest_path(project: Project, name: str) -> Path:
    return imports_dir(project) / name / "manifest.json"


def _load(project: Project, name: str) -> dict:
    path = _manifest_path(project, name)
    if not path.exists():
        raise SpekyError("import_not_found", f"No import '{name}'.", "Run `speky import status --json`.")
    return json.loads(path.read_text())


def _save(project: Project, name: str, data: dict) -> None:
    data["updated_at"] = now()
    write_json(_manifest_path(project, name), data)


def add(project: Project, name: str, sources: List[str] = None, code: List[str] = None) -> dict:
    """Register an import. Documents are copied into `source/`; code paths are referenced in place."""
    name = slugify(name)
    folder = imports_dir(project) / name
    src = folder / "source"
    src.mkdir(parents=True, exist_ok=True)
    existing = json.loads(_manifest_path(project, name).read_text()) if _manifest_path(project, name).exists() else {}
    documents = list(existing.get("documents", []))
    for s in sources or []:
        path = Path(s).expanduser()
        if not path.exists():
            raise SpekyError("source_not_found", f"{s} does not exist.")
        files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
        for f in files:
            rel = f.name if path.is_file() else str(f.relative_to(path))
            target = src / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            documents.append({"name": rel, "type": DOC_TYPES.get(f.suffix.lower(), "other")})
    code_paths = list(existing.get("code_paths", []))
    for c in code or []:
        path = Path(c).expanduser().resolve()
        if not path.is_dir():
            raise SpekyError("source_not_found", f"{c} is not a folder.")
        code_paths.append(str(path))
    for f in src.rglob("*"):  # files the user placed by hand
        if f.is_file() and str(f.relative_to(src)) not in {d["name"] for d in documents}:
            documents.append({"name": str(f.relative_to(src)), "type": DOC_TYPES.get(f.suffix.lower(), "other")})
    data = {"id": name, "name": existing.get("name", name.replace("-", " ").title()),
            "imported_at": existing.get("imported_at", now()), "source_folder": str(src),
            "documents": documents, "code_paths": code_paths,
            "kind": "code" if code_paths and not documents else "docs" if not code_paths else "mixed",
            "derived_specs": existing.get("derived_specs", []), "derived": existing.get("derived", []),
            "status": existing.get("status", "pending"), "analysis_version": "3"}
    _save(project, name, data)
    return {**data, "next": f"Follow the speky-import skill for '{name}': read the sources, then create "
                            f"specs/tasks/knowledge and record them with `speky import link {name} <id>`."}


def link(project: Project, name: str, refs: List[str]) -> dict:
    data = _load(project, name)
    for ref in refs:
        item = project.try_find(ref)
        rid = item.id if item else ref  # tasks (W..), ADRs, knowledge topics are recorded as given
        if rid not in data["derived"]:
            data["derived"].append(rid)
        if item:
            if item.kind == "spec" and rid not in data["derived_specs"]:
                data["derived_specs"].append(rid)
            item.update_status(source_import=name)
    data["status"] = "active"
    _save(project, name, data)
    return data


def done(project: Project, name: str) -> dict:
    data = _load(project, name)
    data["status"] = "complete"
    data["completed_at"] = now()
    _save(project, name, data)
    return data


def status(project: Project) -> List[dict]:
    base = imports_dir(project)
    out = []
    for folder in sorted(base.iterdir()) if base.is_dir() else []:
        m = folder / "manifest.json"
        if folder.is_dir() and m.exists():
            d = json.loads(m.read_text())
            out.append({"id": d.get("id", folder.name), "name": d.get("name"), "status": d.get("status"),
                        "kind": d.get("kind", "docs"), "documents": len(d.get("documents", [])),
                        "code_paths": d.get("code_paths", []), "derived": d.get("derived", d.get("derived_specs", [])),
                        "imported_at": d.get("imported_at")})
        elif folder.is_dir() and folder.name == "poc_import":
            for sess in sorted(folder.glob("poc-*")):
                st = json.loads((sess / "state.json").read_text()) if (sess / "state.json").exists() else {}
                out.append({"id": f"poc_import/{sess.name}", "name": "POC import (v2)", "kind": "code",
                            "status": st.get("phase"), "code_paths": st.get("poc_paths", []), "derived": []})
    return out


def packet(project: Project, name: str, reconcile: bool = False) -> dict:
    """What the agent reads for an import (or a reconcile pass)."""
    data = _load(project, name)
    src = imports_dir(project) / name / "source"
    return {"import": name, "kind": data.get("kind"), "status": data.get("status"),
            "read": [str((src / d["name"]).relative_to(project.root)) for d in data.get("documents", [])],
            "code_paths": data.get("code_paths", []), "derived": data.get("derived", []),
            "mode": "reconcile" if reconcile else "import",
            "instruction": ("Compare the code with these sources and with the derived items; record each "
                            "mismatch as a finding on the item, or a task/story for missing work."
                            if reconcile else
                            "Turn the sources into specs (`speky new spec`), tasks, knowledge and ADRs; "
                            "check overlaps with existing items first; link what you create.")}
