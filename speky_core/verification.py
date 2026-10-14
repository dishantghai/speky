"""Start, evidence, verify and archive (CONTRACTS.md §4, §6).

Verification is evidence-gated: a change passes only when every requirement has `met`
evidence, the verify command (if any) passed on the current tree, and no blocker is open.
Archive merges the change's deltas into the living capability specs.
"""
import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List

from . import markdown as md
from . import vcs
from .errors import SpekyError
from .items import Item, Project, now, write_json
from .templates import CAPABILITY
from .validation import Ledger

EVIDENCE_STATUSES = ("met", "partial", "missing", "contradicts")
DELTA_FORMAT_HINT = ("Delta format: `## ADDED Requirements` then `### Requirement: <title>` (or `### R1: "
                     "<title>`) with a `#### Scenario:` (WHEN/THEN); `## MODIFIED Requirements` / "
                     "`## REMOVED Requirements` then `### <capability>-R<n>: <title>` using IDs from "
                     ".speky/capabilities/<capability>/spec.md.")


# ---------------------------------------------------------------------------- start
def start(project: Project, item: Item) -> dict:
    status = item.load_status()
    base = vcs.head(project.root)
    changes = {"status": "in_progress", "base_sha": status.get("base_sha") or base,
               "implementation_started": status.get("implementation_started") or now()}
    item.update_status(**changes)
    return {"item": item.id, "status": "in_progress", "base_sha": changes["base_sha"]}


# ---------------------------------------------------------------------------- evidence
def _evidence_path(item: Item) -> Path:
    return item.path / "evidence.json"


def load_evidence(item: Item) -> Dict[str, dict]:
    path = _evidence_path(item)
    return json.loads(path.read_text()) if path.exists() else {}


def record_evidence(project: Project, item: Item, req_id: str, status: str, evidence: str) -> dict:
    if status not in EVIDENCE_STATUSES:
        raise SpekyError("bad_evidence_status", f"Status must be one of {', '.join(EVIDENCE_STATUSES)}.")
    req_ids = [r.id for r in md.parse_requirements(md.strip_comments(item.read_doc()))]
    manual = [f"check:{c['name']}" for c in done_checks_for(project, item) if c.get("manual")]
    req_id = req_id if req_id.lower().startswith("check:") else req_id.upper()
    if req_id not in req_ids + manual:
        raise SpekyError("unknown_requirement", f"{item.id} has no requirement or manual check {req_id}.",
                         f"Requirements in {item.doc_path.name}: {', '.join(req_ids) or 'none'}"
                         + (f"; manual checks: {', '.join(manual)}" if manual else "") + ".")
    if status == "met" and not evidence.strip():
        raise SpekyError("evidence_required", "`met` needs evidence: a test id, file:line or command.",
                         'Add --evidence "tests/test_import.py::test_valid_link".')
    data = load_evidence(item)
    data[req_id] = {"status": status, "evidence": evidence, "recorded_at": now(),
                    "tree": vcs.tree_fingerprint(project.root)}
    write_json(_evidence_path(item), data)
    return {"item": item.id, "requirement": req_id, **data[req_id]}


# ---------------------------------------------------------------------------- verify
def _run(command: str, root: Path, timeout: int = 1800) -> dict:
    try:
        proc = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True,
                              timeout=timeout)
        output = (proc.stdout + proc.stderr).strip().splitlines()
        return {"command": command, "exit_code": proc.returncode, "output_tail": "\n".join(output[-40:])}
    except subprocess.TimeoutExpired:
        return {"command": command, "exit_code": 124, "output_tail": f"timed out after {timeout}s"}


def verify(project: Project, item: Item, run: str = None) -> dict:
    cfg = project.config
    status = item.load_status()
    reqs = md.parse_requirements(md.strip_comments(item.read_doc()))
    evidence = load_evidence(item)
    base = status.get("base_sha")
    command = run if run is not None else (cfg.get("verify_command") or "")

    missing: List[str] = []
    per_req = []
    for r in reqs:
        ev = evidence.get(r.id)
        state = ev["status"] if ev else "missing"
        per_req.append({"id": r.id, "title": r.title, "status": state,
                        "evidence": ev["evidence"] if ev else ""})
        if state != "met":
            missing.append(f"{r.id} ({r.title}): {state}")
    if not reqs:
        missing.append("no requirements with IDs (### R1: ...) to verify against")

    run_result = _run(command, project.root) if command else None
    if run_result and run_result["exit_code"] != 0:
        missing.append(f"verify command failed (exit {run_result['exit_code']}): {command}")

    blockers = Ledger(item).open(("blocker",))
    for f in blockers:
        missing.append(f"open blocker {f['id']}: {f['text']}")

    checks = run_done_checks(project, item, evidence)
    missing += [f"done check {c['name']} ({c['label']}): {c['detail']}" for c in checks if not c["passed"]]
    from .tasks import Tasks
    missing += [f"plan task {t['id']} is {t['status']}: {t['text'][:60]}" for t in Tasks(project).for_item(item.id)
                if t["status"] in ("todo", "doing")]

    passed = not missing
    tree = vcs.tree_fingerprint(project.root)
    verification = {"passed": passed, "checked_at": now(), "tree": tree,
                    "command": command, "exit_code": run_result["exit_code"] if run_result else None,
                    "missing": missing}
    changes = {"verification": verification}
    if passed and status.get("status") in ("draft", "ready", "in_progress"):
        changes["status"] = "review"
    item.update_status(**changes)
    return {
        "item": item.id, "passed": passed, "missing": missing, "requirements": per_req,
        "changed_files": vcs.changed_files(project.root, base),
        "base_sha": base, "run": run_result, "done_checks": checks,
        "message": ("Verified: every requirement has evidence"
                    + (" and the verify command passed." if command else ".")) if passed
        else f"Not verified: {len(missing)} item(s) missing.",
    }


# ---------------------------------------------------------------------------- living specs
def _capability_path(project: Project, cap: str) -> Path:
    return project.capabilities_dir / cap / "spec.md"


def _validate_cap_name(cap: str) -> None:
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", cap):
        raise SpekyError("bad_capability", f"Capability name '{cap}' must be lowercase-kebab-case.",
                         "Rename the delta file, e.g. deltas/browser-tabs.md.")


def capability_requirements(project: Project, cap: str) -> List[md.Requirement]:
    path = _capability_path(project, cap)
    return md.parse_requirements(path.read_text(), md.CAP_REQ_RE) if path.exists() else []


def plan_merge(project: Project, item: Item) -> List[dict]:
    """Work out every delta merge without writing; raises on any inconsistency."""
    plans = []
    deltas_dir = item.path / "deltas"
    for delta_file in sorted(deltas_dir.glob("*.md")) if deltas_dir.is_dir() else []:
        cap = delta_file.stem
        _validate_cap_name(cap)
        delta = md.parse_delta(delta_file.read_text())
        if delta.unparsed:
            raise SpekyError("unreadable_delta_heading",
                             f"{delta_file}: cannot read " + "; ".join(delta.unparsed),
                             DELTA_FORMAT_HINT)
        if not (delta.added or delta.modified or delta.removed):
            raise SpekyError("empty_delta", f"{delta_file} has no requirements under "
                             "## ADDED / ## MODIFIED / ## REMOVED Requirements.", DELTA_FORMAT_HINT)
        existing = {r.id: r for r in capability_requirements(project, cap)}
        for r in delta.modified + delta.removed:
            if not r.id or r.id not in existing:
                raise SpekyError("unknown_requirement_in_delta",
                                 f"{delta_file}: {r.id or r.title} is not in capability '{cap}'.",
                                 f"Use an ID from {_capability_path(project, cap)} or move it to ADDED.")
        for r in delta.added:
            if not any(s.complete for s in r.scenarios):
                raise SpekyError("delta_requirement_without_scenario",
                                 f"{delta_file}: added requirement '{r.title}' has no WHEN/THEN scenario.")
        plans.append({"capability": cap, "delta": delta, "file": str(delta_file),
                      "added": len(delta.added), "modified": len(delta.modified),
                      "removed": len(delta.removed)})
    return plans


def _apply_merge(project: Project, plan: dict, source_id: str) -> List[str]:
    cap, delta = plan["capability"], plan["delta"]
    path = _capability_path(project, cap)
    if path.exists():
        text = path.read_text()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = CAPABILITY.format(name=cap.replace("-", " ").title(),
                                 purpose=delta.purpose or f"<!-- What '{cap}' is for. -->")
    reqs = md.parse_requirements(text, md.CAP_REQ_RE)
    head = text.split("## Requirements", 1)[0].rstrip()
    # High-water mark so a removed requirement's ID is never handed out again
    mark = re.search(r"<!-- speky:next-id (\d+) -->", head)
    head = re.sub(r"\n*<!-- speky:next-id \d+ -->", "", head)
    by_id = {r.id: r for r in reqs}
    order = [r.id for r in reqs]
    for r in delta.modified:
        r.body.append(f"\n<!-- updated by {source_id} -->")
        by_id[r.id] = r
    for r in delta.removed:
        by_id.pop(r.id, None)
        order.remove(r.id)
    used = [int(r.id.rsplit("-R", 1)[1]) for r in reqs]
    next_n = max([int(mark.group(1)) if mark else 1, max(used, default=0) + 1])
    new_ids = []
    for r in delta.added:
        r.id = f"{cap}-R{next_n}"
        next_n += 1
        r.body.append(f"\n<!-- added by {source_id} -->")
        by_id[r.id] = r
        order.append(r.id)
        new_ids.append(r.id)
    body = "\n".join(by_id[i].text() for i in order)
    path.write_text(f"{head}\n\n<!-- speky:next-id {next_n} -->\n\n## Requirements\n\n{body}")
    return new_ids


def archive(project: Project, item: Item, force_reason: str = None) -> dict:
    status = item.load_status()
    if status.get("status") == "archived":
        raise SpekyError("already_archived", f"{item.id} is already archived; its deltas were merged "
                         f"on {status.get('archived_at', '?')}.",
                         "Change behaviour again through a new item (`speky new ...`), not by re-archiving.")
    verification = status.get("verification") or {}
    tree = vcs.tree_fingerprint(project.root)
    if not force_reason:
        if not verification.get("passed"):
            raise SpekyError("not_verified", f"{item.id} has not passed `speky verify`.",
                             f"Run `speky verify {item.id}`, or archive with --force \"<reason>\".")
        if verification.get("tree") != tree:
            raise SpekyError("stale_verification",
                             f"The code changed after {item.id} was verified.",
                             f"Run `speky verify {item.id}` again on the current tree.")
    plans = plan_merge(project, item)  # validates everything before any write
    merged = []
    for plan in plans:
        new_ids = _apply_merge(project, plan, item.id)
        merged.append({"capability": plan["capability"], "added": new_ids,
                       "modified": plan["modified"], "removed": plan["removed"]})
    changes = {"status": "archived", "archived_at": now(), "merged_capabilities": merged}
    if status.get("status") not in ("completed", "archived"):
        changes["completed_at"] = now()
    if force_reason:
        changes["archive_forced"] = force_reason
    item.update_status(**changes)
    return {"item": item.id, "status": "archived", "merged": merged,
            "message": (f"Archived {item.id}; living specs updated: "
                        + ", ".join(m["capability"] for m in merged)) if merged
            else f"Archived {item.id} (no deltas to merge)."}


def capabilities_report(project: Project) -> List[dict]:
    """Every living spec with its requirements and structural problems."""
    report = []
    base = project.capabilities_dir
    for path in sorted(base.glob("*/spec.md")) if base.is_dir() else []:
        cap = path.parent.name
        text = path.read_text()
        parsed = md.parse_requirements(text, md.CAP_REQ_RE)
        reqs = [r for r in parsed if r.id]  # living specs need <capability>-R<n> IDs
        problems = []
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", cap):
            problems.append("folder name must be lowercase-kebab-case")
        stray = [l.strip() for l in md.strip_comments(text).splitlines()
                 if l.startswith("### ") and not md.CAP_REQ_RE.match(l)]
        problems += [f"unreadable requirement heading: {l}" for l in stray]
        wrong_prefix = [r.id for r in reqs if not r.id.startswith(cap + "-R")]
        if wrong_prefix:
            problems.append("IDs must start with '%s-R': %s" % (cap, ", ".join(wrong_prefix)))
        ids = [r.id for r in reqs]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            problems.append("duplicate IDs: " + ", ".join(dupes))
        no_scenario = [r.id for r in reqs if not any(sc.complete for sc in r.scenarios)]
        if no_scenario:
            problems.append("no WHEN/THEN scenario: " + ", ".join(no_scenario))
        mark = re.search(r"<!-- speky:next-id (\d+) -->", text)
        highest = max((int(i.rsplit("-R", 1)[1]) for i in ids if "-R" in i), default=0)
        if not mark:
            problems.append(f"missing <!-- speky:next-id {highest + 1} --> marker")
        elif int(mark.group(1)) <= highest:
            problems.append(f"next-id {mark.group(1)} must be greater than {highest}")
        if not md.section_has_content(md.sections(text).get("purpose")):
            problems.append("## Purpose is empty")
        report.append({"capability": cap, "requirements": len(reqs), "ids": ids,
                       "problems": problems, "file": str(path.relative_to(project.root))})
    return report


# ---------------------------------------------------------------------------- definition of done
def checks_for_labels(project: Project, labels: List[str]) -> List[dict]:
    config_checks = project.config.get("done_checks") or {}
    result = []
    for label in labels:
        for check in config_checks.get(label, []) or []:
            result.append({**check, "label": label})
    return result


def done_checks_for(project: Project, item: Item) -> List[dict]:
    """Checks configured in speky.yaml `done_checks` for this item's labels (and `all`)."""
    return checks_for_labels(project, ["all"] + list(item.load_status().get("labels", []) or []))


def run_done_checks(project: Project, item: Item, evidence: Dict[str, dict]) -> List[dict]:
    return run_checks(project, item.id, done_checks_for(project, item), evidence)


def run_checks(project: Project, ref_id: str, checks: List[dict], evidence: Dict[str, dict]) -> List[dict]:
    import glob as globlib
    results = []
    for c in checks:
        name = c.get("name") or c.get("run") or c.get("file") or c.get("manual")
        if c.get("run"):
            r = _run(c["run"].replace("{id}", ref_id), project.root)
            results.append({"name": name, "label": c["label"], "passed": r["exit_code"] == 0,
                            "detail": f"`{c['run']}` exited {r['exit_code']}"})
        elif c.get("file"):
            pattern = c["file"].replace("{id}", ref_id)
            hits = globlib.glob(str(project.root / pattern))
            results.append({"name": name, "label": c["label"], "passed": bool(hits),
                            "detail": f"needs a file matching {pattern}" if not hits else hits[0]})
        elif c.get("manual"):
            ev = evidence.get(f"check:{c.get('name')}")
            ok = bool(ev and ev.get("status") == "met")
            results.append({"name": name, "label": c["label"], "passed": ok,
                            "detail": c["manual"] if not ok else ev.get("evidence", "")})
    return results
