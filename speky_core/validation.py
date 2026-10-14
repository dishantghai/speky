"""Validation that converges (CONTRACTS.md §5).

Deterministic rubric + a findings ledger + rounds with a cap. The rubric checks structure only;
judgement findings come from the agent (`speky finding add`) after it has verified them. Closed
findings are never re-raised, an unchanged spec never starts a new round, and after `max_rounds`
the remaining non-blocking findings are parked so validation stops.
"""
import hashlib
import json
import re
from typing import List, Optional

from . import markdown as md
from .errors import SpekyError
from .items import Item, Project, now, write_json

SEVERITIES = ("blocker", "major", "minor")
CLOSED = ("fixed", "accepted", "wontfix", "deferred", "parked")
STATUSES = ("open",) + CLOSED
BLOCKER_DEFINITION = ("an implementer must guess, and a wrong guess changes user-visible behaviour "
                      "or stored data")


def fingerprint(text: str) -> str:
    norm = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    norm = " ".join(w for w in norm.split() if len(w) > 2)
    return hashlib.sha1(norm.encode()).hexdigest()[:12]


def spec_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------- rubric
def run_rubric(project: Project, item: Item, cfg: dict) -> List[dict]:
    """Structure checks. Returns [{rubric, passed, severity, text, evidence}]."""
    text = item.read_doc()
    results = []

    def check(rubric, passed, severity, text_, evidence=""):
        results.append({"rubric": rubric, "passed": bool(passed), "severity": severity,
                        "text": text_, "evidence": evidence})

    if not text.strip():
        check("document", False, "blocker", f"{item.doc_path.name} is missing or empty",
              str(item.doc_path))
        return results

    check("why", md.section_has_content(md.find_section(text, "why")), "major",
          "Say why this change exists (## Why — the problem and who has it)")
    check("scope", md.section_has_content(md.find_section(text, "scope")), "major",
          "Say what is true when this is done (## Capabilities)")
    check("non_goals", md.section_has_content(md.find_section(text, "non_goals")), "major",
          "Name at least one non-goal (## Non-goals) so the implementer doesn't fill the gap")

    reqs = md.parse_requirements(md.strip_comments(text))
    check("requirements", bool(reqs), "blocker",
          "Add requirements as `### R1: <title>` so they can be verified and traced",
          f"{len(reqs)} requirement(s) found")
    missing = [r.id for r in reqs if not any(s.complete for s in r.scenarios)]
    check("scenarios", bool(reqs) and not missing, "blocker",
          "Every requirement needs a `#### Scenario:` with a WHEN line and a THEN line",
          ("missing in " + ", ".join(missing)) if missing else "")
    dupes = sorted({r.id for r in reqs if [x.id for x in reqs].count(r.id) > 1})
    check("requirement_ids", not dupes, "blocker", "Requirement IDs must be unique",
          ", ".join(dupes))

    markers = md.clarification_markers(text)
    limit = cfg.get("max_clarification_markers", 3)
    check("clarifications", len(markers) <= limit, "blocker",
          f"At most {limit} [NEEDS CLARIFICATION] markers; make informed guesses for the rest and "
          "list them under ## Assumptions", f"{len(markers)} marker(s)")

    from .templates import unfilled_placeholders
    placeholders = unfilled_placeholders(text)
    check("placeholders", not placeholders, "blocker",
          "Replace the template placeholders with real content", ", ".join(placeholders))

    deps = item.info()["dependencies"]
    unknown = [d for d in deps if not project.try_find(d)]
    check("dependencies", not unknown, "blocker", "Every dependency must be an existing item",
          ", ".join(unknown))

    from . import uxdesign
    hints = uxdesign.looks_user_facing(project, item)
    check("ui_label", not hints, "major",
          "This change reads as user-facing (" + ", ".join(hints[:6]) + "). If it changes what users see, label "
          "it (`speky set " + item.id + " --labels ui`: adds `## Design`); if not, add `## Design` with \"No new "
          "design needed: <why>\"", ", ".join(hints))
    if uxdesign.is_ui(project, item):
        st = uxdesign.state(project, item)
        check("design", uxdesign.satisfied(st), "major",
              "UI change: say in `## Design` which design it implements (screen IDs like screen:<id>, design "
              "files or links, per state), or \"No new design needed: <why>\". Find an existing design first; "
              "if none exists, create one (speky-design skill)",
              "to be designed" if st["to_design"] and not st["not_needed"] else ", ".join(st["cited"]))
        check("design_refs", not st["broken"], "major", "Design references in `## Design` must exist "
              "(and not be superseded)", ", ".join(st["broken"]))
        check("design_location", not st["outside"], "major",
              "Designs live in the design locations (`speky layout`): import them with `speky design screen add "
              "<id> <files> --move` and cite `screen:<id>`", ", ".join(st["outside"]))
        if st["links"] and not st["cited"] and not st["not_needed"]:
            check("design_in_repo", False, "major", "A design-tool link is a pointer, not the design: export "
                  "the screens into the repo (`speky design screen add`) and cite them", ", ".join(st["links"]))
        check("design_system", bool(st["system"]), "major",
              "This project has UI work but no design-system document: create one (speky-design skill) "
              "and set `paths.design_system` in speky.yaml")

    lines = len([l for l in text.splitlines() if l.strip()])
    max_lines = cfg.get("max_spec_lines", 250)
    check("length", lines <= max_lines, "minor",
          f"Keep the change under {max_lines} lines; move detail to plan.md or a companion file",
          f"{lines} lines")
    return results


# ---------------------------------------------------------------------------- ledger
class Ledger:
    def __init__(self, item: Item):
        self.item = item
        self.path = item.path / "findings.json"
        self.findings = json.loads(self.path.read_text()) if self.path.exists() else []

    def save(self):
        write_json(self.path, self.findings)

    def get(self, finding_id: str) -> dict:
        for f in self.findings:
            if f["id"].lower() == finding_id.lower():
                return f
        raise SpekyError("finding_not_found", f"No finding {finding_id} on {self.item.id}.",
                         f"Run `speky finding list {self.item.id}`.")

    def open(self, severities=SEVERITIES, kinds=("gap", "question")) -> List[dict]:
        return [f for f in self.findings
                if f["status"] == "open" and f["severity"] in severities and f["kind"] in kinds]

    def _next_id(self) -> str:
        nums = [int(f["id"][1:]) for f in self.findings if f["id"][1:].isdigit()]
        return f"F{max(nums, default=0) + 1}"

    def find_duplicate(self, fp: str, rubric: Optional[str], source: str) -> Optional[dict]:
        for f in self.findings:
            if f["fingerprint"] == fp:
                return f
            if rubric and source == "rubric" and f.get("source") == "rubric" and f.get("rubric") == rubric:
                return f
        return None

    def add(self, text: str, severity: str, kind: str = "gap", source: str = "agent",
            rubric: str = None, evidence: str = "", round_: int = 0, max_questions: int = 5) -> dict:
        if severity not in SEVERITIES:
            raise SpekyError("bad_severity", f"Severity must be one of {', '.join(SEVERITIES)}.",
                             f"Blocker = {BLOCKER_DEFINITION}.")
        if kind not in ("gap", "question"):
            raise SpekyError("bad_kind", "Kind must be `gap` or `question`.")
        fp = fingerprint(text) if source != "rubric" else f"rubric:{rubric}"
        dup = self.find_duplicate(fp, rubric, source)
        if dup:
            if source == "rubric" and dup["status"] == "fixed":
                # the structure broke again: reopen rather than re-adding
                dup.update(status="open", round=round_, reopened_at=now())
                self.save()
                return {**dup, "duplicate": False, "reopened": True}
            return {**dup, "duplicate": True}
        if kind == "question":
            asked = [f for f in self.findings if f["kind"] == "question"]
            if len(asked) >= max_questions:
                raise SpekyError(
                    "question_cap_reached",
                    f"{self.item.id} already has {len(asked)} questions (cap {max_questions}).",
                    "Make an informed guess, write it under `## Assumptions`, and record it with "
                    f"`speky decide \"...\" --type assumption --ref {self.item.id}`.")
        finding = {"id": self._next_id(), "source": source, "rubric": rubric, "severity": severity,
                   "kind": kind, "text": text, "evidence": evidence, "status": "open",
                   "round": round_, "fingerprint": fp, "created_at": now()}
        self.findings.append(finding)
        self.save()
        return {**finding, "duplicate": False}

    def resolve(self, finding_id: str, status: str, ruling: str = "") -> dict:
        if status not in CLOSED + ("open",):
            raise SpekyError("bad_status", f"Status must be one of {', '.join(STATUSES)}.")
        if status in ("accepted", "wontfix", "parked", "deferred") and not ruling:
            raise SpekyError("ruling_required", f"Closing a finding as '{status}' needs a ruling.",
                             'Add --ruling "<what you decided> — <why> — <cost if wrong>".')
        f = self.get(finding_id)
        f.update(status=status, ruling=ruling or f.get("ruling", ""), resolved_at=now())
        self.save()
        return f


# ---------------------------------------------------------------------------- check
def check(project: Project, item: Item, force: bool = False) -> dict:
    """Run the rubric, sync rubric findings into the ledger, and decide convergence."""
    cfg = project.config
    status = item.load_status()
    validation = dict(status.get("validation") or {})
    text = item.read_doc()
    h = spec_hash(text)
    ledger = Ledger(item)
    max_rounds = int(cfg.get("max_rounds", 2))

    unchanged = validation.get("spec_hash") == h and validation.get("round", 0) > 0
    if unchanged and not force:
        result = _summary(item, ledger, validation, run_rubric(project, item, cfg), cfg)
        result["cached"] = True
        result["message"] = ("Spec unchanged since round %d — nothing new to validate."
                             % validation.get("round", 0))
        return result

    round_ = validation.get("round", 0) + 1
    rubric = run_rubric(project, item, cfg)
    for r in rubric:
        existing = ledger.find_duplicate(f"rubric:{r['rubric']}", r["rubric"], "rubric")
        if not r["passed"]:
            ledger.add(r["text"], r["severity"], source="rubric", rubric=r["rubric"],
                       evidence=r["evidence"], round_=round_)
        elif existing and existing["status"] == "open":
            ledger.resolve(existing["id"], "fixed")

    converged_reason = ""
    blocking = ledger.open(("blocker", "major"))
    if not blocking:
        converged_reason = "no open blocker or major findings"
    elif round_ >= max_rounds and not force and not ledger.open(("blocker",)):
        for f in blocking:
            f.update(status="parked", ruling="implementation-time question (validation cap reached)",
                     resolved_at=now())
        ledger.save()
        converged_reason = (f"cap of {max_rounds} rounds reached; remaining major findings parked "
                            "as implementation-time questions")

    validation = {"round": round_, "spec_hash": h, "converged": bool(converged_reason),
                  "converged_reason": converged_reason, "checked_at": now()}
    item.update_status(validation=validation)
    result = _summary(item, ledger, validation, rubric, cfg)
    result["cached"] = False
    return result


def _summary(item: Item, ledger: Ledger, validation: dict, rubric: List[dict], cfg: dict) -> dict:
    open_blockers = ledger.open(("blocker",))
    open_majors = ledger.open(("major",))
    open_minors = ledger.open(("minor",))
    # Converged is live: a blocker the agent added after the last round un-converges the change
    converged = validation.get("round", 0) > 0 and not open_blockers and not open_majors
    max_rounds = int(cfg.get("max_rounds", 2))
    if converged:
        reason = validation.get("converged_reason") or "no open blocker or major findings"
        message = (f"Converged in round {validation.get('round')}: {reason}. "
                   "More validation is unlikely to add value.")
        next_step = f"speky next {item.id}"
    elif open_blockers:
        message = f"{len(open_blockers)} blocker(s) must be fixed before planning."
        next_step = f"fix the blockers in {item.doc_path.name}, then `speky check {item.id}`"
    else:
        message = f"{len(open_majors)} major finding(s) open (round {validation.get('round')}/{max_rounds})."
        next_step = (f"fix or rule on them (`speky finding resolve {item.id} <F#> --as accepted "
                     f"--ruling \"...\"`), then `speky check {item.id}`")
    return {
        "item": item.id, "round": validation.get("round", 0), "max_rounds": max_rounds,
        "converged": converged, "converged_reason": validation.get("converged_reason", ""),
        "rubric": rubric, "open": {"blocker": open_blockers, "major": open_majors, "minor": open_minors},
        "questions_asked": len([f for f in ledger.findings if f["kind"] == "question"]),
        "max_questions": cfg.get("max_questions", 5),
        "message": message, "next": next_step,
    }


def is_converged(item: Item) -> bool:
    validation = item.load_status().get("validation") or {}
    if not validation.get("round"):
        return False
    ledger = Ledger(item)
    return not ledger.open(("blocker", "major"))
