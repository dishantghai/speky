"""The agent protocol: `state`, `next` and `prime` (CONTRACTS.md §9).

`next` derives the single next action from files on disk, so any harness — or a new session after
context compaction — gets the same answer without remembering anything.
"""
import json
from typing import Optional

from . import graph, journal, validation
from .items import DONE_STATUSES, Item, Project


def state(project: Project) -> dict:
    all_info = graph.statuses(project)
    items = []
    for info in all_info.values():
        reasons = graph.blocked_by(info, all_info) if info["status"] not in DONE_STATUSES else []
        items.append({k: info[k] for k in ("id", "kind", "type", "title", "status", "priority",
                                           "dependencies", "gates")}
                     | {"blocked_by": reasons,
                        "converged": bool(info["validation"].get("converged")),
                        "verified": bool(info["verification"].get("passed"))})
    open_gates = [{"item": i["id"], **g} for i in items for g in i["gates"] if g.get("status") == "open"]
    return {"root": str(project.root), "items": items,
            "ready": [i["id"] for i in graph.ready(project)], "open_gates": open_gates,
            "cycles": graph.cycles(project), "config": project.config}


def _rel(path) -> str:
    from pathlib import Path
    path = Path(path)
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _action(action, item: Optional[Item], why, instruction, skill=None, commands=(), read=(),
            done_when=""):
    return {"action": action, "item": item.id if item else None, "why": why,
            "instruction": instruction, "skill": skill, "commands": list(commands),
            "read": [_rel(p) for p in read], "done_when": done_when}


def action_for(project: Project, item: Item) -> dict:
    info = item.info()
    doc = item.doc_path
    rel_doc = doc.relative_to(project.root)
    all_info = graph.statuses(project)

    if info["status"] in DONE_STATUSES:
        return _action("idle", item, f"{item.id} is {info['status']}.",
                       "Nothing to do for this item.", done_when="")

    gates = [g for g in info["gates"] if g.get("status") == "open"]
    if gates:
        g = gates[0]
        return _action("resolve_gate", item, f"Gate {g['id']} ({g['type']}) is open: {g['reason']}",
                       "Stop and ask the user to decide. Do not decide a human gate yourself."
                       if g["type"] == "human" else "Wait for the CI run / PR, then resolve the gate.",
                       commands=[f"speky gate resolve {item.id} {g['id']} --by \"<who>\""],
                       done_when="the gate is resolved")

    blockers = [r for r in graph.blocked_by(info, all_info) if not r.startswith("gate")]
    if blockers:
        return _action("blocked", item, "Waiting on: " + ", ".join(blockers),
                       "Work on the dependencies first (`speky ready`), or remove a wrong dependency.",
                       commands=["speky ready --json"], done_when="dependencies are completed")

    status = info["status"]
    from .templates import unfilled_placeholders
    doc_text = item.read_doc()
    if status in ("draft", "ready") and (not doc_text.strip() or unfilled_placeholders(doc_text)):
        return _action("propose", item, f"{rel_doc} is empty or still the template.",
                       "Write the change: why, capabilities, non-goals, requirements `### R1:` with "
                       "WHEN/THEN scenarios. Ask at most 5 questions, one at a time, each with your "
                       "recommended answer; put informed guesses under ## Assumptions.",
                       skill="speky-propose", read=[doc], commands=[f"speky check {item.id} --json"],
                       done_when=f"`speky check {item.id}` has no blockers")

    if status in ("draft", "ready") and not validation.is_converged(item):
        val = item.load_status().get("validation") or {}
        stale = val.get("spec_hash") != validation.spec_hash(item.read_doc())
        open_blockers = validation.Ledger(item).open(("blocker",))
        if open_blockers and not stale:
            return _action("fix_structure", item, f"{len(open_blockers)} blocker(s) open.",
                           "Fix each blocker in the document (or rule on it with a reason), then check again.",
                           skill="speky-validate", read=[doc, item.path / "findings.json"],
                           commands=[f"speky finding list {item.id} --json",
                                     f"speky check {item.id} --json"],
                           done_when="no open blockers")
        return _action("validate", item,
                       "Not validated yet." if not val.get("round") else "Spec changed or findings open.",
                       "Run the rubric, then review the change once through the ambiguity checklist in "
                       "the speky-validate skill. Record only findings you verified "
                       "(`speky finding add`). Stop when `speky check` says converged.",
                       skill="speky-validate", read=[doc],
                       commands=[f"speky check {item.id} --json",
                                 f"speky finding add {item.id} --severity major --text \"...\""],
                       done_when=f"`speky check {item.id}` reports converged")

    if status == "draft":
        size = item.load_status().get("size", "change")
        if size not in ("quick", "small") and not (item.path / "plan.md").exists():
            return _action("plan", item, "Validated; no plan yet.",
                           "Write plan.md: the decisions the implementer cannot make alone (files, "
                           "interfaces, values from the spec), agent-sized tasks, and the command that "
                           "verifies each. No hour estimates.",
                           skill="speky-plan", read=[doc], commands=[f"speky start {item.id}"],
                           done_when=f"{item.path.relative_to(project.root)}/plan.md exists")
        return _action("start", item, "Validated and planned.",
                       "Record the starting commit, then implement.",
                       skill="speky-implement", commands=[f"speky start {item.id}"],
                       done_when="status is in_progress")

    if status == "ready":
        return _action("start", item, "Planned.", "Record the starting commit, then implement.",
                       skill="speky-implement", commands=[f"speky start {item.id}"],
                       done_when="status is in_progress")

    if status == "in_progress":
        ver = item.load_status().get("verification") or {}
        why = ("Implementation in progress." if not ver else
               "Last verification failed: " + "; ".join(ver.get("missing", [])[:3]))
        plan = item.path / "plan.md"
        return _action("implement", item, why,
                       "Implement the requirements. File work you discover as new items "
                       "(`speky new ... --discovered-from`), don't grow this one. For each requirement "
                       "record evidence, then verify with a fresh test run.",
                       skill="speky-implement",
                       read=[doc] + ([plan] if plan.exists() else []),
                       commands=[f"speky evidence {item.id} R1 --status met --evidence \"<test id>\"",
                                 f"speky verify {item.id} --json"],
                       done_when=f"`speky verify {item.id}` passes")

    if status == "review":
        return _action("archive", item, "Verified.",
                       "Merge the change's deltas into the living specs and close it. If the change "
                       "altered behaviour, make sure deltas/<capability>.md describes it first.",
                       skill="speky-verify", read=[item.path / "deltas"],
                       commands=[f"speky archive {item.id} --json"],
                       done_when="status is archived")

    return _action("idle", item, f"Unknown status '{status}'.", "Fix status.json by hand.")


def next_action(project: Project, ref: str = None) -> dict:
    if ref:
        return action_for(project, project.find(ref))
    queue = graph.ready(project)
    for info in queue:
        action = action_for(project, project.find(info["id"]))
        if action["action"] not in ("idle", "blocked"):
            return action
    gated = [i for i in project.items()
             if i.info()["status"] not in DONE_STATUSES
             and any(g.get("status") == "open" for g in i.info()["gates"])]
    if gated:
        return action_for(project, gated[0])
    return _action("idle", None, "No open work is ready.",
                   "Ask the user what to build next, size it, and create it with "
                   "`speky new spec \"<title>\"` (or `speky new story \"<title>\" --type bug`).",
                   skill="speky", commands=['speky new spec "<title>" --size change'],
                   done_when="a new item exists")


PROFILE_CLOSE = {
    "conservative": "Before saying \"done\": run `speky verify <id>` and report the result, list "
                    "changed files, and propose the commit. Do not commit or push unless asked.",
    "team-maintainer": "Before saying \"done\": run `speky verify <id>`, archive verified items, "
                       "commit your changes with a message naming the item. Do not push unless asked.",
}


def prime(project: Project, limit_items: int = 5) -> str:
    cfg = project.config
    st = state(project)
    open_items = [i for i in st["items"] if i["status"] not in DONE_STATUSES]
    in_progress = [i for i in open_items if i["status"] in ("in_progress", "review")]
    ready = st["ready"][:limit_items]
    nxt = next_action(project)
    lines = [
        "# SPEKY workflow (spec-driven development)",
        "",
        "This project tracks work as changes in `.speky/specs/` and `.speky/stories/`; current "
        "behaviour lives in `.speky/capabilities/`. SPEKY holds state and rules; you do the work.",
        "",
        "- Ask `speky next --json` what to do; it names the action, the skill to use and when it is done.",
        "- Size work first: a quick, clear fix can be done directly and verified; anything that changes "
        "behaviour gets a change (`speky new spec|story`).",
        "- Requirements are `### R1: ...` with WHEN/THEN scenarios. Record evidence per requirement "
        "(`speky evidence`), then `speky verify`. No completion claims without fresh evidence.",
        "- Found other work? `speky new story \"...\" --discovered-from <id>` — don't grow the current item.",
        "- Decisions: `speky decide \"...\" --type decision|assumption --ref <id>`; facts: `speky remember`.",
        "- Human gates (stack, design, scope, merge) are the user's call: stop and ask.",
        "",
        "## Now",
        f"- Next action: **{nxt['action']}**" + (f" on {nxt['item']}" if nxt["item"] else "")
        + f" — {nxt['why']}",
    ]
    if in_progress:
        lines.append("- In progress: " + ", ".join(f"{i['id']} {i['title']}" for i in in_progress))
    if ready:
        lines.append("- Ready: " + ", ".join(ready))
    if st["open_gates"]:
        lines.append("- Open gates: " + ", ".join(f"{g['item']}/{g['id']} {g['reason']}"
                                                  for g in st["open_gates"]))
    mem = journal.memories(project)
    if mem:
        lines += ["", "## Project memory"] + [f"- {m}" for m in mem[-20:]]
    lines += ["", "## Session close",
              PROFILE_CLOSE.get(cfg.get("agent_profile"), PROFILE_CLOSE["conservative"])]
    return "\n".join(lines) + "\n"


def prime_hook_json(project: Project) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                              "additionalContext": prime(project)}})
