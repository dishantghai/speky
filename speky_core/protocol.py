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
            done_when="", task: str = None):
    return {"action": action, "item": item.id if item else None, "task": task, "why": why,
            "instruction": instruction, "skill": skill, "commands": list(commands),
            "read": [_rel(p) for p in read], "done_when": done_when}


def action_for(project: Project, item: Item) -> dict:
    from . import playbooks, uxdesign
    result = _item_action(project, item)
    if result["action"] in ("plan", "start", "implement") and uxdesign.is_ui(project, item):
        st = uxdesign.state(project, item)
        files = ([st["system"]] if st["system"] else []) + [c for c in st["cited"] if not c.startswith("http")]
        result["instruction"] = ("Build what the cited designs show, in every state, with the design system's "
                                 "tokens and components: " + ", ".join(files or st["cited"]) + ". "
                                 + result["instruction"])
        result["read"] = result["read"] + [f for f in files if f not in result["read"]]
    if result["action"] in ("plan", "start", "implement", "validate", "propose", "design"):
        books = playbooks.for_labels(project, item.load_status().get("labels") or [])
        if books:
            result["instruction"] = playbooks.instruction(books) + " " + result["instruction"]
            result["also_skills"] = [b["skill"] for b in books if b["skill"]]
            result["read"] = result["read"] + [r for b in books for r in b["read"] if r not in result["read"]]
    return result


def _project_has_ui(project: Project) -> bool:
    from . import uxdesign
    return uxdesign.project_has_ui(project)


def _item_action(project: Project, item: Item) -> dict:
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
                       "recommended answer; put informed guesses under ## Assumptions."
                       + (" This project has UI: if the change affects what users see, label it "
                          f"(`speky set {item.id} --labels ui`) and fill `## Design`." if _project_has_ui(project)
                          else ""),
                       skill="speky-propose", read=[doc], commands=[f"speky check {item.id} --json"],
                       done_when=f"`speky check {item.id}` has no blockers")

    from . import uxdesign
    if status in ("draft", "ready") and uxdesign.is_ui(project, item):
        st = uxdesign.state(project, item)
        if not uxdesign.satisfied(st) or not st["system"]:
            todo = []
            if not st["system"]:
                todo.append("there is no design-system document yet: create it from the existing UI (tokens, "
                            "type, spacing, components) or the first approved screens, and set "
                            "`paths.design_system`")
            if not uxdesign.satisfied(st):
                todo.append("find the design this change implements: `speky design status`, the screen "
                            "catalogue and `refs` (screen:<id>); if one exists, cite it in `## Design`. If none "
                            "exists, create it with the project's design tool (its playbook, or whatever is "
                            "available: Stitch, Figma, an HTML mock), save it in the repo, give it an ID, "
                            "review it, and cite it. Show new designs to the owner before building: design "
                            "is their call")
            return _action("design", item, "UI change without " + (
                               "a cited design" if not uxdesign.satisfied(st) else "a design system") + ".",
                           "This change affects what users see; " + "; ".join(todo) + ".",
                           skill="speky-design", read=[doc] + ([project.root / st["system"]] if st["system"] else []),
                           commands=["speky design status --json", "speky refs --json",
                                     f"speky gate add {item.id} --type human --reason \"approve the design\"",
                                     f"speky check {item.id} --json"],
                           done_when=f"`## Design` in {rel_doc} cites the design and a design system exists")

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
        return _action("start", item, "Validated; " + ("planned." if (item.path / "plan.md").exists()
                                                         else f"no plan needed ({size})."),
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


def backlog_pending(project: Project) -> int:
    """Deferred items in v2's backlog (`speky backlog` reviews them)."""
    path = project.dir / "backlog.json"
    try:
        items = json.loads(path.read_text()) if path.exists() else []
    except json.JSONDecodeError:
        return 0
    return len([i for i in items if isinstance(i, dict) and i.get("status", "pending") == "pending"])


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
    task_action = _roadmap_action(project)
    if task_action:
        return task_action
    deferred = backlog_pending(project)
    why = "No open work is ready." + (f" {deferred} deferred backlog item(s) wait for review "
                                      "(`speky backlog`)." if deferred else "")
    return _action("idle", None, why,
                   "Ask the user what to build next (offer the deferred backlog if any), size it, "
                   "and create it with `speky new spec \"<title>\"` (or `speky new story \"<title>\" "
                   "--type bug`), or add a task with `speky task add \"...\"`.",
                   skill="speky", commands=['speky new spec "<title>" --size change']
                   + (["speky backlog"] if deferred else []),
                   done_when="a new item exists")


def _roadmap_action(project: Project) -> Optional[dict]:
    """When no spec or story is ready: tasks of the current phase, then its gate."""
    from . import phases as phases_mod
    from .tasks import Tasks
    tasks = Tasks(project)
    task_help = ("Size it first: if it changes behaviour, promote it (`speky task promote {id} --to story`) "
                 "and follow the change workflow; otherwise do it, then `speky task done {id} --verify` (runs the tests). "
                 "Work you discover goes in as a new task (`speky task add`).")
    from . import playbooks

    def with_playbook(action: dict, t: dict) -> dict:
        books = playbooks.for_labels(project, t.get("labels") or [])
        if books:
            action["instruction"] = playbooks.instruction(books) + " " + action["instruction"]
            action["also_skills"] = [b["skill"] for b in books if b["skill"]]
            action["read"] = action["read"] + [r for b in books for r in b["read"]]
        return action

    doing = [t for t in tasks.list(status="doing") if not t.get("promoted_to")]
    if doing:
        t = doing[0]
        return with_playbook(_action("task", None, f"Task {t['id']} is in progress: {t['text'][:120]}",
                       task_help.format(id=t["id"]), skill="speky",
                       commands=[f"speky task done {t['id']} --verify", f"speky task promote {t['id']} --to story"],
                       done_when=f"{t['id']} is done or promoted", task=t["id"]), t)
    phase = phases_mod.current(project)
    todo = [t for t in tasks.list(status="todo") if not phase or t.get("phase") in (phase.id, None)]
    if todo:
        t = todo[0]
        where = f" in {phase.id}" if phase and t.get("phase") == phase.id else ""
        return with_playbook(_action("task", None, f"Next task{where}: {t['text'][:120]}",
                       f"Start it with `speky task start {t['id']}`. " + task_help.format(id=t["id"]),
                       skill="speky", commands=[f"speky task start {t['id']}", f"speky task done {t['id']} --verify"],
                       done_when=f"{t['id']} is done or promoted", task=t["id"]), t)
    if not phase:
        return None
    unverified = [d for d in phase.deliverables() if not d["verified"]]
    if unverified:
        return _action("gate", None, f"Phase {phase.id}: no open tasks; {len(unverified)} deliverable(s) "
                       "not verified yet.",
                       "Check the phase: `speky phases check` runs deliverable commands; others need evidence "
                       "(`speky phases verify <phase> <D#> --evidence ...`) or the owner's confirmation.",
                       commands=[f"speky phases check {phase.id}", f"speky phases complete {phase.id}"],
                       done_when=f"{phase.id} is completed")
    return _action("phase", None, f"Phase {phase.id}: tasks done and deliverables verified.",
                   "Complete the phase and record a handoff.",
                   commands=[f"speky phases complete {phase.id}", "speky handoff --file <notes.md>"],
                   done_when=f"{phase.id} is completed")


PROFILE_CLOSE = {
    "conservative": "Before saying \"done\": run `speky verify <id>` and report the result, list "
                    "changed files, and propose the commit. Do not commit or push unless asked.",
    "team-maintainer": "Commit in small, reviewed steps; never leave work only in the working tree. "
                       "Before saying \"done\": run `speky verify <id>`, archive verified items, commit "
                       "with a message naming the item. Do not push unless asked.",
}


def _ago(stamp: str) -> str:
    from datetime import datetime
    try:
        delta = datetime.now() - datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return ""
    hours = delta.total_seconds() / 3600
    return f"{int(hours * 60)} min ago" if hours < 1 else f"{hours:.0f} h ago" if hours < 48 \
        else f"{hours / 24:.0f} days ago"


def prime(project: Project, limit_items: int = 5) -> str:
    from . import continuity, knowledge
    from .owner import OwnerActions
    cfg = project.config
    st = state(project)
    open_items = [i for i in st["items"] if i["status"] not in DONE_STATUSES]
    in_progress = [i for i in open_items if i["status"] in ("in_progress", "review")]
    ready = st["ready"][:limit_items]
    nxt = next_action(project)
    facts = continuity.session_facts(project)
    recorded = continuity.read_state(project)
    lines = [
        "# SPEKY workflow (spec-driven development)",
        "",
        "Everything needed to continue lives in `.speky/`, never only in a conversation: changes "
        "(`specs/`, `stories/`), living specs (`capabilities/`), phases (`phases/`), tasks (`tasks.md`), "
        "knowledge (`knowledge/`), owner actions (`owner.md`), the session log and state (`log.md`, `state.md`).",
        "",
        "- Ask `speky next --json` what to do; it names the action, the skill and when it is done.",
        "- Size work first: a quick, clear fix can be done directly and verified; anything that changes "
        "behaviour gets a change (`speky new spec|story`); small planned work is a task (`speky task`).",
        "- Requirements are `### R1: ...` with WHEN/THEN scenarios. Record evidence per requirement "
        "(`speky evidence`), then `speky verify`. No completion claims without fresh evidence.",
        "- Found other work? `speky task add \"...\"` or `speky new story \"...\" --discovered-from <id>`.",
        "- Write what you learn **when you learn it** (`speky remember \"...\" --topic <topic>`); "
        "decisions: `speky decide` (small) or `speky adr new` (lasting). Compaction can happen any time.",
        "- Owner-only actions (accounts, money, judgement, people) go to `speky owner add`; human gates "
        "(stack, design, scope, merge) are the owner's call: stop and ask.",
        "",
        "## Pick up here",
    ]
    last = facts["last_handoff"]
    if last:
        lines.append(f"- Last handoff: {last.get('at', '')[:16]} ({_ago(last.get('at'))}) — "
                     f"\"{last.get('title', '')}\"")
    else:
        lines.append("- No handoff recorded yet.")
    # a handoff rewrites checkpoint.json without the auto flag, so an auto checkpoint is newer
    if facts["auto_checkpoint"] and facts["checkpoint_at"]:
        lines.append(f"- Context was compacted around {facts['checkpoint_at'][:16]}; the state at that "
                     "moment was saved automatically.")
    drift = []
    if facts["commits_since"]:
        drift.append(f"{len(facts['commits_since'])} commit(s) since the handoff: "
                     + "; ".join(c[:60] for c in facts["commits_since"][:4]))
    if facts["uncommitted"]:
        drift.append(f"{len(facts['uncommitted'])} uncommitted file(s): "
                     + ", ".join(facts["uncommitted"][:5]))
    lines += [f"- {d}" for d in drift]
    t = facts["last_test"]
    if t:
        lines.append(f"- Last test run: {'PASS' if t['passed'] else 'FAIL'} (`{t['command']}`, "
                     f"{_ago(t['at'])})")
    if recorded.get("summary"):
        summary = recorded["summary"].splitlines()
        lines += ["", "**Where things stand** (from `.speky/state.md`):"] + summary[:10]
        if len(summary) > 10:
            lines.append("… (rest in `.speky/state.md`)")
    if recorded.get("next"):
        lines += ["", "**Next actions recorded at the last handoff:**"] + \
                 [f"{i}. {n}" for i, n in enumerate(recorded["next"][:6], 1)]
    if recorded.get("watch"):
        lines += ["", "**Watch out for:**"] + [f"- {w}" for w in recorded["watch"][:6]]
    lines += ["", "If git, the tests and this summary disagree, trust git and the tests, then correct the "
                  "record with `speky handoff`."]

    lines += ["", "## Now",
              f"- Next action: **{nxt['action']}**"
              + (f" on {nxt['item'] or nxt.get('task')}" if (nxt["item"] or nxt.get("task")) else "")
              + f" — {nxt['why']}"]
    from . import phases as phases_mod
    from .tasks import Tasks
    phase = phases_mod.current(project)
    open_tasks = [t for t in Tasks(project).list() if t["status"] in ("doing", "todo")
                  and not t.get("promoted_to") and (not phase or t.get("phase") in (phase.id, None))]
    if phase:
        verified = [d for d in phase.deliverables() if d["verified"]]
        lines.append(f"- Phase {phase.id} {phase.data.get('name', '')} [{phase.status}]: "
                     f"{len(verified)}/{len(phase.deliverables())} deliverables verified, "
                     f"{len(open_tasks)} open task(s)")
    if open_tasks:
        lines.append("- Next tasks: " + "; ".join(f"{t['id']} {t['text'][:60]}" for t in open_tasks[:3]))
    if in_progress:
        lines.append("- In progress: " + ", ".join(f"{i['id']} {i['title']}" for i in in_progress))
    if ready:
        lines.append("- Ready: " + ", ".join(ready))
    if st["open_gates"]:
        lines.append("- Open gates: " + ", ".join(f"{g['item']}/{g['id']} {g['reason']}"
                                                  for g in st["open_gates"]))
    owner = OwnerActions(project).open_items()
    if owner:
        lines.append(f"- Waiting on the owner ({len(owner)} open, `.speky/owner.md`): "
                     + "; ".join(f"{o['id']} {o['text'][:60]}" for o in owner[:3]))
        with_notes = [o for o in owner if o["notes"]]
        if with_notes:
            lines.append("  Owner notes to act on: " + ", ".join(o["id"] for o in with_notes[:6]))

    always = knowledge.always_entries(project)
    others = [k for k in knowledge.topics(project) if not k["always"]]
    if always or others:
        lines += ["", "## Knowledge"]
        lines += [f"- {e['text']}" for e in always if "text" in e]
        cut = [e for e in always if e.get("truncated")]
        if cut:
            lines.append("- Always-loaded topics continue in their files; read them now: "
                         + ", ".join(f"`{e['file']}` ({e['more']} more)" for e in cut))
        for k in others:
            when = f" — read when {k['read_when']}" if k["read_when"] else ""
            lines.append(f"- `{k['file']}` ({k['entries']} entries){when}")

    context_dir = project.dir / "context"
    refs = [f"`.speky/context/{n}`" for n in ("tech_decisions.md", "product.md", "architecture.md",
                                              "design_system.md") if (context_dir / n).exists()]
    from . import journal
    adr_rel = journal.adr_dir(project)
    if adr_rel.is_dir():
        refs.append(f"`{adr_rel.relative_to(project.root)}/`")
    if refs:
        lines += ["", "## Project knowledge",
                  "Before choosing a library, a pattern or a UI approach, read " + ", ".join(refs)
                  + " — they record decisions the code can't show."]
    if (project.dir / "testing" / "ide_context.md").exists():
        lines += ["", "## Testing",
                  "Before writing or running tests, read `.speky/testing/ide_context.md` "
                  "(test commands, layout and conventions for this project)."]
    lines += ["", "## Session close",
              PROFILE_CLOSE.get(cfg.get("agent_profile"), PROFILE_CLOSE["conservative"]),
              "After each finished milestone and before you stop, hand off: write a short notes file with "
              "`## Summary`, `## Done`, `## Learned`, `## Next`, `## Watch out for`, then "
              "`speky handoff --file <notes.md>` (it logs the session, refreshes `.speky/state.md` and "
              "records the test result). Treat any finished milestone as a possible last moment before "
              "compaction."]
    return "\n".join(lines) + "\n"


def prime_hook_json(project: Project) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                              "additionalContext": prime(project)}})
