"""Lightweight tasks: work that needs no spec or story folder (yet).

Stored in `.speky/backlog.json` next to v2's deferred backlog items, marked `kind: "task"`. v2's
`speky backlog` reviews only `status: "pending"` items, so tasks never show up there. A readable view
is written to `.speky/tasks.md` after every change. A task can belong to a phase and an epic, have a
parent task, cite references (`adr:0021`, `screen:RV-1`) and be promoted to a story or spec.
"""
import json
from typing import List, Optional

from .errors import SpekyError
from .items import Project, now, write_json

STATUSES = ("todo", "doing", "done", "deferred")
MARK = {"todo": "[ ]", "doing": "[~]", "done": "[x]", "deferred": "[-]"}


class Tasks:
    def __init__(self, project: Project):
        self.project = project
        self.path = project.dir / "backlog.json"
        self.items = json.loads(self.path.read_text()) if self.path.exists() else []

    def _tasks(self) -> List[dict]:
        return [i for i in self.items if i.get("kind") == "task"]

    def list(self, status: str = None, phase: str = None) -> List[dict]:
        return [self._view(t) for t in self._tasks()
                if (not status or t["status"] == status) and (not phase or t.get("phase") == phase)]

    def _view(self, t: dict) -> dict:
        return {"id": t["id"], "text": t["name"], "status": t["status"], "phase": t.get("phase"),
                "epic": t.get("epic"), "parent": t.get("parent"), "refs": t.get("refs", []),
                "notes": t.get("notes", []), "labels": t.get("labels", []), "promoted_to": t.get("promoted_to")}

    def get(self, ref: str) -> dict:
        for t in self._tasks():
            if t["id"].lower() == ref.lower():
                return t
        raise SpekyError("task_not_found", f"No task {ref}.", "Run `speky task list --json`.")

    def _next_id(self) -> str:
        path = self.project.dir / "ids.json"
        counters = json.loads(path.read_text()) if path.exists() else {}
        used = [int(t["id"][1:]) for t in self._tasks() if t["id"][1:].isdigit()]
        n = max([counters.get("W", 0)] + used) + 1
        counters["W"] = n
        write_json(path, counters)
        return f"W{n}"

    def save(self) -> None:
        self.project.dir.mkdir(parents=True, exist_ok=True)
        write_json(self.path, self.items)
        self.render()

    def add(self, text: str, phase: str = None, epic: str = None, parent: str = None,
            refs: List[str] = None, status: str = "todo", labels: List[str] = None) -> dict:
        from . import phases as phases_mod
        if parent:
            par = self.get(parent)
            phase = phase or par.get("phase")
        if phase:
            phase = phases_mod.get(self.project, phase).id
        else:
            cur = phases_mod.current(self.project)
            phase = cur.id if cur else None
        if epic and not (self.project.dir / "epics").exists():
            raise SpekyError("epic_not_found", f"No epic {epic}.")
        task = {"id": self._next_id(), "kind": "task", "name": " ".join(text.split()), "status": status,
                "phase": phase, "epic": epic, "parent": parent, "refs": refs or [], "labels": labels or [], "notes": [],
                "created_at": now()}
        self.items.append(task)
        self.save()
        return self._view(task)

    def set_status(self, ref: str, status: str, note: str = "") -> dict:
        if status not in STATUSES:
            raise SpekyError("bad_status", f"Status must be one of {', '.join(STATUSES)}.")
        t = self.get(ref)
        t["status"] = status
        t[f"{status}_at"] = now()
        if note:
            t.setdefault("notes", []).append(f"{now()[:10]} {note}")
        self.save()
        return self._view(t)

    def verify(self, ref: str, run: str = None) -> dict:
        """Run the project's tests for a task; a pass marks it done and records the run as a note."""
        import subprocess
        t = self.get(ref)
        cmd = run or self.project.config.get("verify_command") or ""
        if not cmd:
            raise SpekyError("no_verify_command", "No verify command configured.",
                             "Set verify_command in speky.yaml (`speky test init` detects it), or pass --run.")
        from .verification import checks_for_labels, run_checks
        proc = subprocess.run(cmd, shell=True, cwd=self.project.root, capture_output=True, text=True)
        # a labelled task meets that label's done checks too (`all` checks are for specs and stories)
        checks = run_checks(self.project, t["id"], checks_for_labels(self.project, t.get("labels") or []),
                            t.get("evidence") or {})
        missing = ([] if proc.returncode == 0 else [f"`{cmd}` failed"]) + \
            [f"done check {c['name']} ({c['label']}): {c['detail']}" for c in checks if not c["passed"]]
        passed = not missing
        note = f"verified: `{cmd}` exit {proc.returncode}" + (f"; {len(missing)} missing" if missing else "")
        if passed and t["status"] != "done":
            t["status"], t["done_at"] = "done", now()
        t.setdefault("notes", []).append(f"{now()[:10]} {note}")
        self.save()
        return {"task": t["id"], "passed": passed, "command": cmd, "exit_code": proc.returncode,
                "status": t["status"], "missing": missing, "done_checks": checks,
                "output_tail": "\n".join((proc.stdout + proc.stderr).splitlines()[-15:])}

    def record_evidence(self, ref: str, check: str, status: str, evidence: str) -> dict:
        """Evidence for a manual done check of a labelled task (`check:<name>`)."""
        from .verification import checks_for_labels
        t = self.get(ref)
        names = [f"check:{c['name']}" for c in checks_for_labels(self.project, t.get("labels") or []) if c.get("manual")]
        if check not in names:
            raise SpekyError("unknown_check", f"{t['id']} has no manual check {check}.",
                             f"Manual checks for its labels: {', '.join(names) or 'none'}.")
        if status == "met" and not evidence.strip():
            raise SpekyError("evidence_required", "`met` needs evidence: a file, test id or review.")
        t.setdefault("evidence", {})[check] = {"status": status, "evidence": evidence, "recorded_at": now()}
        self.save()
        return {"task": t["id"], "check": check, "status": status}

    def promote(self, ref: str, to: str = "story", story_type: str = "feature") -> dict:
        t = self.get(ref)
        item = self.project.create("spec" if to == "spec" else "story", t["name"][:80], story_type=story_type,
                                   size="small" if to == "story" else "change")
        item.update_status(from_task=t["id"], **({"phase": t["phase"]} if t.get("phase") else {}))
        t["promoted_to"] = item.id
        t["status"] = "doing"
        self.save()
        return {"task": t["id"], "item": item.id, "doc": str(item.doc_path.relative_to(self.project.root))}

    def render(self) -> None:
        """Readable view: `.speky/tasks.md` (generated)."""
        from . import phases as phases_mod
        order = [p.id for p in phases_mod.all_phases(self.project)]
        tasks = self._tasks()
        groups = {}
        for t in tasks:
            groups.setdefault(t.get("phase") or "(no phase)", []).append(t)
        lines = ["# Tasks", "", "_Generated by SPEKY from `.speky/backlog.json` — change tasks with "
                 "`speky task …`. Marks: [ ] todo · [~] doing · [x] done · [-] deferred._", ""]
        for phase in [p for p in order if p in groups] + [g for g in groups if g not in order]:
            lines += [f"## {phase}", ""]
            by_parent = {}
            for t in groups[phase]:
                by_parent.setdefault(t.get("parent"), []).append(t)

            def emit(parent, depth):
                for t in by_parent.get(parent, []):
                    extra = f" → {t['promoted_to']}" if t.get("promoted_to") else ""
                    refs = f" (refs: {', '.join(t['refs'])})" if t.get("refs") else ""
                    refs += f" [{', '.join(t['labels'])}]" if t.get("labels") else ""
                    lines.append(f"{'  ' * depth}- {MARK[t['status']]} {t['id']} {t['name']}{refs}{extra}")
                    lines.extend(f"{'  ' * (depth + 1)}- {n}" for n in t.get("notes") or [])
                    emit(t["id"], depth + 1)

            emit(None, 0)
            orphans = [t for t in groups[phase] if t.get("parent") and
                       t["parent"] not in {x["id"] for x in groups[phase]}]
            for t in orphans:
                lines.append(f"- {MARK[t['status']]} {t['id']} {t['name']} (parent {t['parent']})")
            lines.append("")
        (self.project.dir / "tasks.md").write_text("\n".join(lines).rstrip() + "\n")
