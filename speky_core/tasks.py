"""Lightweight tasks: work that needs no spec or story folder (yet).

Stored in `.speky/backlog.json` next to v2's deferred backlog items, marked `kind: "task"`. v2's
`speky backlog` reviews only `status: "pending"` items, so tasks never show up there. A readable view
is written to `.speky/tasks.md` after every change. A task can belong to a phase and an epic, have a
parent task, cite references (`adr:0021`, `screen:RV-1`) and be promoted to a story or spec.
"""
import json
import re
from typing import List, Optional

from .errors import SpekyError
from .items import Project, now, write_json

STATUSES = ("todo", "doing", "done", "deferred")
# tasks outside a spec/story plan: only small work that changes no behaviour
WORK_KINDS = ("fix", "chore", "measure")
FEATURE_RE = re.compile(r"\b(implement|build|add support|support for|new (?:feature|screen|view|page|panel|command|"
                        r"endpoint|api|mode|flow)|allow (?:users?|the owner)|let (?:users?|the owner)|introduce|enable)\b",
                        re.IGNORECASE)
PLAN_BEGIN = "<!-- BEGIN SPEKY tasks: generated from `speky task`, edit with `speky task …` -->"
PLAN_END = "<!-- END SPEKY tasks -->"
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
                "notes": t.get("notes", []), "labels": t.get("labels", []), "promoted_to": t.get("promoted_to"),
                "for": t.get("item"), "closes": t.get("closes", []), "check": t.get("check"),
                "work": t.get("work"), "exception": t.get("exception")}

    def get(self, ref: str) -> dict:
        for t in self._tasks():
            if t["id"].lower() == ref.lower():
                return t
        raise SpekyError("task_not_found", f"No task {ref}.", "Run `speky task list --json`.")

    def archived(self, ref: str = None) -> list:
        """Tasks moved to the archive by `speky tidy` (exact records)."""
        import json
        path = self.project.dir / "archive" / "tasks.json"
        rows = json.loads(path.read_text()) if path.exists() else []
        return [t for t in rows if not ref or t["id"].lower() == ref.lower()]

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
        for item_id in sorted({t["item"] for t in self._tasks() if t.get("item")}):
            self.render_plan(item_id)

    def add(self, text: str, phase: str = None, epic: str = None, parent: str = None,
            refs: List[str] = None, status: str = "todo", labels: List[str] = None, item: str = None,
            closes: List[str] = None, check: str = None, work: str = None, exception: str = None,
            enforce: bool = False) -> dict:
        """A task in a spec/story's plan (`item`, closing its requirements or done checks), or a standalone
        task for small work without behaviour change (`work`: fix | chore | measure) or a recorded
        `exception`. `enforce` applies these rules (the CLI always does)."""
        from . import phases as phases_mod
        text = " ".join(text.split())
        if item:
            it = self.project.find(item)
            item = it.id
            closes = self._valid_closes(it, closes or [])
            if enforce and not closes:
                raise SpekyError("task_closes_nothing", f"A task in {item}'s plan must close something it defines.",
                                 f"Add --closes with its requirement IDs ({', '.join(self._targets(it)) or 'none yet'}), "
                                 "e.g. --closes R1,R2.")
            phase = phase or it.load_status().get("phase")
        elif enforce:
            if not work and not exception:
                raise SpekyError("task_needs_spec", "Work that changes behaviour belongs to a spec or story's plan.",
                                 "Add it to a plan: `speky task add --for <spec|story> \"…\" --closes R1` (create the "
                                 "change first with `speky new story|spec`), or, for small work that changes no "
                                 "behaviour, `--kind fix|chore|measure`, or `--exception \"<why>\"` (recorded, shown "
                                 "to the owner).")
            if work and work not in WORK_KINDS:
                raise SpekyError("bad_work_kind", f"Kind must be one of {', '.join(WORK_KINDS)}.")
            if work in ("chore", "measure") and FEATURE_RE.search(text) and not exception:
                raise SpekyError("task_looks_like_a_feature",
                                 f"'{text[:80]}' reads like new behaviour, not a {work}.",
                                 "Give it a spec or story (`speky new story`), or `--exception \"<why>\"`.")
        if parent:
            par = self.get(parent)
            phase = phase or par.get("phase")
        if phase:
            phase = phases_mod.get(self.project, phase).id
        else:
            cur = phases_mod.current(self.project)
            phase = cur.id if cur else None
        if epic:
            epic = self._epic_id(epic)
        if enforce and not item and not phase and not epic:
            raise SpekyError("task_untraced", "A task outside a spec/story plan still belongs to a phase or an epic.",
                             "Add --phase <id> or --epic <id> (`speky phases list`, `speky epic list`; create one with "
                             "`speky phases add` or `speky epic add`).")
        task = {"id": self._next_id(), "kind": "task", "name": text, "status": status,
                "phase": phase, "epic": epic, "parent": parent, "refs": refs or [], "labels": labels or [], "notes": [],
                "created_at": now()}
        if item:
            task.update(item=item, closes=closes, check=check)
        else:
            task.update({k: v for k, v in (("work", work), ("exception", exception), ("check", check)) if v})
        self.items.append(task)
        self.save()
        if exception:
            from . import journal
            journal.decide(self.project, f"Task {task['id']} runs without a spec or story: {exception} "
                                         f"({text[:80]})", "decision")
        return self._view(task)

    # ---------------------------------------------------------------- plans of specs and stories
    @staticmethod
    def _targets(item) -> List[str]:
        from . import markdown as md
        return [r.id for r in md.parse_requirements(md.strip_comments(item.read_doc())) if r.id]

    def _valid_closes(self, item, closes: List[str]) -> List[str]:
        from .verification import done_checks_for
        reqs = self._targets(item)
        checks = [f"check:{c['name']}" for c in done_checks_for(self.project, item) if c.get("name")]
        out = []
        for c in closes:
            c = c.strip()
            norm = c if c.lower().startswith("check:") else c.upper()
            if norm not in reqs + checks:
                raise SpekyError("unknown_target", f"{item.id} defines no {c}.",
                                 f"Requirements: {', '.join(reqs) or 'none'}" +
                                 (f"; done checks: {', '.join(checks)}" if checks else "") + ".")
            out.append(norm)
        return out

    def for_item(self, item_id: str) -> List[dict]:
        return [self._view(t) for t in self._tasks() if t.get("item") == item_id]

    def coverage(self, item) -> dict:
        """Which of the change's requirements its plan's tasks close."""
        reqs = self._targets(item)
        tasks = [t for t in self._tasks() if t.get("item") == item.id and t["status"] != "deferred"]
        covered = {c for t in tasks for c in t.get("closes") or []}
        return {"requirements": reqs, "uncovered": [r for r in reqs if r not in covered],
                "tasks": len(tasks), "open": [t["id"] for t in tasks if t["status"] in ("todo", "doing")]}

    def attach(self, ref: str, item_ref: str, closes: List[str]) -> dict:
        t = self.get(ref)
        it = self.project.find(item_ref)
        t["item"] = it.id
        t["closes"] = self._valid_closes(it, closes)
        if not t["closes"]:
            raise SpekyError("task_closes_nothing", "Say what it closes: --closes R1,R2.")
        t.pop("work", None)
        t["phase"] = t.get("phase") or it.load_status().get("phase")
        self.save()
        return self._view(t)

    def set_kind(self, ref: str, work: str = None, exception: str = None) -> dict:
        t = self.get(ref)
        if t.get("item"):
            raise SpekyError("task_in_a_plan", f"{t['id']} is part of {t['item']}'s plan; it needs no kind.")
        if work:
            if work not in WORK_KINDS:
                raise SpekyError("bad_work_kind", f"Kind must be one of {', '.join(WORK_KINDS)}.")
            t["work"] = work
        if exception:
            t["exception"] = exception
            from . import journal
            journal.decide(self.project, f"Task {t['id']} runs without a spec or story: {exception} "
                                         f"({t['name'][:80]})", "decision")
        if not work and not exception:
            raise SpekyError("kind_required", "Give --kind fix|chore|measure or --exception \"<why>\".")
        self.save()
        return self._view(t)

    def unclassified(self) -> List[dict]:
        """Open tasks that break the rules (made before them): standalone without a kind, or belonging to no
        spec/story, phase or epic."""
        return [self._view(t) for t in self._tasks() if t["status"] in ("todo", "doing") and not t.get("item")
                and not t.get("promoted_to") and
                ((not t.get("work") and not t.get("exception")) or (not t.get("phase") and not t.get("epic")))]

    def _epic_id(self, epic: str) -> str:
        from . import epics as epics_mod
        return str(epics_mod.get(self.project, epic)["id"])

    def place(self, ref: str, phase: str = None, epic: str = None) -> dict:
        """Put a standalone task in a phase and/or an epic (traceability)."""
        from . import phases as phases_mod
        t = self.get(ref)
        if phase:
            t["phase"] = phases_mod.get(self.project, phase).id
        if epic:
            t["epic"] = self._epic_id(epic)
        if not phase and not epic:
            raise SpekyError("place_where", "Give --phase <id> and/or --epic <id>.")
        self.save()
        return self._view(t)

    def exceptions(self) -> List[dict]:
        return [self._view(t) for t in self._tasks() if t.get("exception")]

    def _close_requirements(self, t: dict, evidence: str) -> List[str]:
        """When the last task closing a requirement is done, record the evidence for it."""
        from .verification import record_evidence
        if not t.get("item"):
            return []
        item = self.project.try_find(t["item"])
        if not item:
            return []
        met = []
        for target in t.get("closes") or []:
            others = [x for x in self._tasks() if x.get("item") == item.id and target in (x.get("closes") or [])]
            if all(x["status"] == "done" for x in others):
                ids = ", ".join(x["id"] for x in others)
                record_evidence(self.project, item, target, "met", f"{ids}: {evidence}")
                met.append(target)
        return met

    def render_plan(self, item_id: str) -> None:
        """The plan's task list inside the change's plan.md, between SPEKY markers."""
        item = self.project.try_find(item_id)
        if not item:
            return
        tasks = [t for t in self._tasks() if t.get("item") == item_id]
        path = item.path / "plan.md"
        body = [PLAN_BEGIN] + [f"- {MARK[t['status']]} {t['id']} {t['name']} — closes {', '.join(t.get('closes') or [])}"
                               + (f"; check: `{t['check']}`" if t.get("check") else "") for t in tasks] + [PLAN_END]
        block = "\n".join(body)
        text = path.read_text() if path.exists() else f"# Plan: {item.info()['title']}\n"
        if PLAN_BEGIN in text and PLAN_END in text:
            a, b = text.index(PLAN_BEGIN), text.index(PLAN_END) + len(PLAN_END)
            text = text[:a] + block + text[b:]
        else:
            text = text.rstrip() + "\n\n## Tasks\n\n" + block + "\n"
        path.write_text(text)

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
        cmd = run or t.get("check") or self.project.config.get("verify_command") or ""
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
        met = self._close_requirements(t, f"`{cmd}` passed ({now()[:10]})") if passed else []
        return {"task": t["id"], "passed": passed, "command": cmd, "exit_code": proc.returncode,
                "status": t["status"], "missing": missing, "done_checks": checks, "requirements_met": met,
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

    def promote(self, ref: str, to: str = "story", story_type: str = "feature", title: str = None) -> dict:
        """The task becomes a story or spec; its phase, labels and references carry over."""
        from . import uxdesign
        t = self.get(ref)
        item = self.project.create("spec" if to == "spec" else "story", (title or t["name"])[:80],
                                   story_type=story_type, size="small" if to == "story" else "change")
        carry = {k: t[k] for k in ("phase", "labels", "refs") if t.get(k)}
        item.update_status(from_task=t["id"], **carry)
        others = [r for r in t.get("refs") or [] if not r.startswith("screen:")]
        if others:  # cite them in the document too, where the implementer reads
            text = item.read_doc()
            item.doc_path.write_text(text.rstrip() + "\n\n## References\n" + "".join(f"- {r}\n" for r in others))
        uxdesign.ensure_section(self.project, item)
        for s in uxdesign.task_screens(self.project, t):  # the task's screens become the change's design
            from . import design
            design.link(self.project, s["id"], item.id)
        t["promoted_to"] = item.id
        t["status"] = "doing"
        self.save()
        return {"task": t["id"], "item": item.id, "doc": str(item.doc_path.relative_to(self.project.root)),
                "carried": sorted(carry)}

    def render(self) -> None:
        """Readable view: `.speky/tasks.md` (generated)."""
        from . import phases as phases_mod
        order = [p.id for p in phases_mod.all_phases(self.project)]
        tasks = [t for t in self._tasks() if not t.get("item")]
        planned = [t for t in self._tasks() if t.get("item")]
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
                    refs += f" ({t['work']})" if t.get("work") else (" (exception)" if t.get("exception") else "")
                    lines.append(f"{'  ' * depth}- {MARK[t['status']]} {t['id']} {t['name']}{refs}{extra}")
                    lines.extend(f"{'  ' * (depth + 1)}- {n}" for n in t.get("notes") or [])
                    emit(t["id"], depth + 1)

            emit(None, 0)
            orphans = [t for t in groups[phase] if t.get("parent") and
                       t["parent"] not in {x["id"] for x in groups[phase]}]
            for t in orphans:
                lines.append(f"- {MARK[t['status']]} {t['id']} {t['name']} (parent {t['parent']})")
            lines.append("")
        if planned:
            lines += ["## Plans of specs and stories", ""]
            for item_id in sorted({t["item"] for t in planned}):
                lines.append(f"- {item_id}")
                lines += [f"  - {MARK[t['status']]} {t['id']} {t['name']} — closes {', '.join(t.get('closes') or [])}"
                          for t in planned if t["item"] == item_id]
            lines.append("")
        (self.project.dir / "tasks.md").write_text("\n".join(lines).rstrip() + "\n")
