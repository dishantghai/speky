"""v3 commands of the `speky` CLI. `speky.py` hands these command names to `main()` here.

Every command accepts `--json`: exactly one JSON document on stdout, human text on stderr.
Errors exit 1 with {"ok": false, "error": {"code", "message", "fix"}}.
"""
import argparse
import json
import sys
from typing import List

from . import continuity, graph, harness, journal, knowledge, migrate, protocol, refs, validation, verification
from . import phases as phases_mod
from .owner import OwnerActions
from .tasks import Tasks
from .errors import SpekyError
from .items import STORY_PREFIXES, Project

COMMANDS = {"capabilities", "task", "phases", "owner", "knowledge", "handoff",
            "checkpoint", "refs", "new", "state", "ready", "next", "check", "finding", "start", "evidence", "verify",
            "archive", "decide", "remember", "adr", "term", "gate", "link", "prime", "setup",
            "migrate", "set"}

HELP = """SPEKY v3 commands (agent protocol; add --json to any of them):
  new spec|story "<title>"     create a change (--type, --size, --deps, --discovered-from)
  state | ready | next [<id>]  project state, ready queue, the one next action
  check <id>                   rubric + convergence (--force for another round past the cap)
  finding add|list|resolve     the validation ledger
  start <id>                   record base commit, status in_progress
  evidence <id> <R#>           record verification evidence for a requirement
  verify <id> [--run CMD]      evidence-gated verification
  archive <id>                 merge deltas into living specs, close the change
  capabilities                 living specs with requirement counts and structural problems
  decide | remember | adr | term   decision log, memory, ADRs, glossary
  gate add|resolve | link      human/ci/pr gates; typed links
  prime [--hook-json]          workflow + state for an agent session
  handoff | checkpoint         end-of-session log + state snapshot | mechanical snapshot
  phases                       phases (milestones) with deliverables as their gate
  task                         lightweight tasks (W<n>), promotable to story/spec
  owner                        actions only the owner can take (O<n>)
  knowledge | remember         project knowledge by topic
  refs                         check references like adr:0021 or screen:RV-1
  setup <harness>              install skills + instructions (claude-code, codex, agents-md)
  migrate [--apply|--done T]   bring a v2 project to v3 (dry run by default)
  set <id> --status S          manual status change"""


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="speky", description=HELP,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, **kw):
        sp = sub.add_parser(name, **kw)
        sp.add_argument("--json", action="store_true", help="print one JSON document")
        return sp

    sp = add("new", help="create a change")
    sp.add_argument("kind", choices=["spec", "story"])
    sp.add_argument("title")
    sp.add_argument("--type", default="feature", choices=list(STORY_PREFIXES))
    sp.add_argument("--size", default=None, choices=["quick", "small", "change", "epic"])
    sp.add_argument("--priority", default="P2")
    sp.add_argument("--deps", default="", help="comma-separated item IDs")
    sp.add_argument("--discovered-from", default=None)
    sp.add_argument("--body-file", default=None, help="use this file as the document")
    sp.add_argument("--labels", default="", help="comma-separated labels (select done checks)")

    add("state")
    add("ready")
    add("capabilities")
    sp = add("next")
    sp.add_argument("id", nargs="?")

    sp = add("check")
    sp.add_argument("id")
    sp.add_argument("--force", action="store_true")

    sp = add("finding")
    fsub = sp.add_subparsers(dest="action", required=True)
    fa = fsub.add_parser("add")
    fa.add_argument("id")
    fa.add_argument("--severity", required=True, choices=list(validation.SEVERITIES))
    fa.add_argument("--text", required=True)
    fa.add_argument("--kind", default="gap", choices=["gap", "question"])
    fa.add_argument("--evidence", default="")
    fa.add_argument("--json", action="store_true")
    fl = fsub.add_parser("list")
    fl.add_argument("id")
    fl.add_argument("--all", action="store_true", help="include closed findings")
    fl.add_argument("--json", action="store_true")
    fr = fsub.add_parser("resolve")
    fr.add_argument("id")
    fr.add_argument("finding")
    fr.add_argument("--as", dest="status", required=True, choices=list(validation.STATUSES))
    fr.add_argument("--ruling", default="")
    fr.add_argument("--json", action="store_true")

    sp = add("start")
    sp.add_argument("id")
    sp = add("evidence")
    sp.add_argument("id")
    sp.add_argument("requirement")
    sp.add_argument("--status", required=True, choices=list(verification.EVIDENCE_STATUSES))
    sp.add_argument("--evidence", default="")
    sp = add("verify")
    sp.add_argument("id")
    sp.add_argument("--run", default=None, help="verify command (overrides verify_command)")
    sp = add("archive")
    sp.add_argument("id")
    sp.add_argument("--force", default=None, metavar="REASON")

    sp = add("decide")
    sp.add_argument("text")
    sp.add_argument("--type", default="decision", choices=list(journal.DECISION_TYPES))
    sp.add_argument("--ref", default=None)
    sp = add("remember")
    sp.add_argument("fact")
    sp.add_argument("--topic", default="general")
    sp.add_argument("--always", action="store_true", help="load this topic into every session")
    sp.add_argument("--read-when", default=None, help="trigger shown in prime, e.g. 'touching the kernel'")
    sp = add("adr")
    asub = sp.add_subparsers(dest="action", required=True)
    an = asub.add_parser("new")
    an.add_argument("title")
    an.add_argument("--context", default="")
    an.add_argument("--decision", default="")
    an.add_argument("--supersedes", default=None)
    an.add_argument("--json", action="store_true")
    al = asub.add_parser("list")
    al.add_argument("--json", action="store_true")
    sp = add("term")
    sp.add_argument("word")
    sp.add_argument("definition")

    sp = add("gate")
    gsub = sp.add_subparsers(dest="action", required=True)
    ga = gsub.add_parser("add")
    ga.add_argument("id")
    ga.add_argument("--type", default="human", choices=list(graph.GATE_TYPES))
    ga.add_argument("--reason", required=True)
    ga.add_argument("--json", action="store_true")
    gr = gsub.add_parser("resolve")
    gr.add_argument("id")
    gr.add_argument("gate")
    gr.add_argument("--by", default="")
    gr.add_argument("--note", default="")
    gr.add_argument("--json", action="store_true")
    sp = add("link")
    sp.add_argument("id")
    sp.add_argument("--type", required=True, choices=list(graph.LINK_TYPES))
    sp.add_argument("--to", required=True)

    sp = add("phases")
    psub = sp.add_subparsers(dest="action")
    for name, help_ in (("list", "all phases"), ("status", "progress of every phase")):
        px = psub.add_parser(name, help=help_)
        px.add_argument("--json", action="store_true")
    for name in ("show", "start", "check", "defer", "guide"):
        px = psub.add_parser(name)
        px.add_argument("id")
        px.add_argument("--json", action="store_true")
    pc = psub.add_parser("complete")
    pc.add_argument("id")
    pc.add_argument("--force", default=None, metavar="REASON")
    pc.add_argument("--json", action="store_true")
    for name in ("add", "create"):
        pa = psub.add_parser(name)
        pa.add_argument("name", help="phase name (create: the phase id)")
        pa.add_argument("--id", default=None)
        pa.add_argument("--description", default="")
        pa.add_argument("--json", action="store_true")
    pd = psub.add_parser("deliverable")
    pd.add_argument("id")
    pd.add_argument("name")
    pd.add_argument("--run", default=None, help="command that proves the deliverable")
    pd.add_argument("--pass-criteria", default="")
    pd.add_argument("--json", action="store_true")
    pv = psub.add_parser("verify")
    pv.add_argument("id")
    pv.add_argument("deliverable")
    pv.add_argument("--evidence", required=True)
    pv.add_argument("--json", action="store_true")
    ps = psub.add_parser("suggest")
    ps.add_argument("--json", action="store_true")

    sp = add("task")
    tsub = sp.add_subparsers(dest="action", required=True)
    ta = tsub.add_parser("add")
    ta.add_argument("text")
    ta.add_argument("--phase", default=None)
    ta.add_argument("--epic", default=None)
    ta.add_argument("--parent", default=None)
    ta.add_argument("--refs", default="", help="comma-separated, e.g. adr:0021,screen:RV-1")
    ta.add_argument("--json", action="store_true")
    for name in ("start", "done", "defer", "todo"):
        tx = tsub.add_parser(name)
        tx.add_argument("id")
        tx.add_argument("--note", default="")
        tx.add_argument("--json", action="store_true")
    tp = tsub.add_parser("promote")
    tp.add_argument("id")
    tp.add_argument("--to", default="story", choices=["story", "spec"])
    tp.add_argument("--type", default="feature", choices=list(STORY_PREFIXES))
    tp.add_argument("--json", action="store_true")
    tl = tsub.add_parser("list")
    tl.add_argument("--phase", default=None)
    tl.add_argument("--status", default=None, choices=["todo", "doing", "done", "deferred"])
    tl.add_argument("--json", action="store_true")

    sp = add("owner")
    osub = sp.add_subparsers(dest="action", required=True)
    oa = osub.add_parser("add")
    oa.add_argument("text")
    oa.add_argument("--section", default="To do")
    oa.add_argument("--note", default="")
    oa.add_argument("--json", action="store_true")
    od = osub.add_parser("done")
    od.add_argument("id")
    od.add_argument("--note", default="")
    od.add_argument("--json", action="store_true")
    ol = osub.add_parser("list")
    ol.add_argument("--all", action="store_true")
    ol.add_argument("--json", action="store_true")

    sp = add("knowledge")
    sp.add_argument("action", nargs="?", default="list", choices=["list", "show", "promote"])
    sp.add_argument("topic", nargs="?")
    sp.add_argument("--title", default=None, help="ADR title when promoting")

    sp = add("handoff")
    sp.add_argument("--file", default=None, help="notes with ## Summary/Done/Learned/Next/Watch out for")
    sp.add_argument("--title", default="")
    sp.add_argument("--summary", default="")
    for flag in ("done", "learned", "next", "watch", "mechanism"):
        sp.add_argument(f"--{flag}", action="append", default=None)
    sp.add_argument("--no-tests", action="store_true", help="don't run verify_command")
    sp.add_argument("--commit", action="store_true", default=None, help="commit .speky/ as 'Handoff: ...'")

    sp = add("checkpoint")
    sp.add_argument("--auto", action="store_true", help="called by a hook (no tests)")
    sp.add_argument("--run-tests", action="store_true")

    add("refs")

    sp = add("prime")
    sp.add_argument("--hook-json", action="store_true")
    sp = add("setup")
    sp.add_argument("harness", nargs="?")
    sp.add_argument("--check", action="store_true")
    sp.add_argument("--remove", action="store_true")
    sp.add_argument("--list", action="store_true")
    sp = add("migrate")
    sp.add_argument("--apply", action="store_true")
    sp.add_argument("--done", default=None, metavar="TASK",
                    help="mark a judgement task as handled (e.g. check_suspect_completions)")
    sp = add("set")
    sp.add_argument("id")
    sp.add_argument("--status", default=None,
                    choices=["draft", "ready", "in_progress", "review", "completed", "archived"])
    sp.add_argument("--labels", default=None, help="comma-separated labels (replaces existing)")
    return p


def _human(cmd: str, result) -> str:
    """Short human-readable rendering; agents should use --json."""
    if isinstance(result, str):
        return result
    if cmd == "next":
        lines = [f"Next: {result['action']}" + (f" on {result['item']}" if result["item"] else ""),
                 f"  why:  {result['why']}", f"  do:   {result['instruction']}"]
        if result.get("skill"):
            lines.append(f"  skill: {result['skill']}")
        lines += [f"  $ {c}" for c in result["commands"]]
        if result.get("done_when"):
            lines.append(f"  done when: {result['done_when']}")
        return "\n".join(lines)
    if cmd == "state":
        rows = [f"{i['id']:<8} {i['status']:<12} {i['title'][:60]}"
                + (f"  [blocked: {', '.join(i['blocked_by'])}]" if i["blocked_by"] else "")
                for i in result["items"]]
        return "\n".join(rows + [f"\nReady: {', '.join(result['ready']) or 'none'}"])
    if cmd == "ready":
        return "\n".join(f"{i['id']:<8} {i['status']:<12} {i['title']}" for i in result["items"]) or \
            "Nothing is ready."
    if cmd in ("check", "verify", "archive") or (isinstance(result, dict) and "message" in result):
        lines = [result.get("message", "")]
        if cmd == "check":
            for sev in ("blocker", "major", "minor"):
                for f in result["open"][sev]:
                    lines.append(f"  {f['id']} [{sev}] {f['text']}")
            lines.append(f"Next: {result['next']}")
        if cmd == "verify":
            lines += [f"  - {m}" for m in result["missing"]]
        return "\n".join(l for l in lines if l)
    return json.dumps(result, indent=2)


# v2's global flags; every command here is non-interactive, so they have nothing to do
NOOP_FLAGS = {"-y", "--yes", "--non-interactive", "--no-input"}


def _strip_noop_flags(argv: List[str]) -> List[str]:
    out, skip = [], False
    for i, a in enumerate(argv):
        if skip:
            skip = False
            continue
        if a in NOOP_FLAGS:
            continue
        if a in ("--answer", "--answers"):
            skip = True
            continue
        if a.startswith(("--answer=", "--answers=")):
            continue
        out.append(a)
    return out


def run(argv: List[str]) -> dict:
    args = _parser().parse_args(_strip_noop_flags(argv))
    cmd = args.cmd
    if cmd == "setup" and args.list:
        return {"harnesses": list(harness.RECIPES)}
    if cmd == "checkpoint" and args.auto and not Project.open(require=False).dir.is_dir():
        return {"skipped": "not a SPEKY project"}
    project = Project.open(require=cmd not in ("migrate", "setup"))
    if cmd == "setup" and not project.dir.is_dir() and not (args.check or args.remove):
        project.dir.mkdir()  # setup bootstraps a v3 project (no LLM needed, unlike v2 `init`)

    if cmd == "new":
        size = args.size or ("small" if args.kind == "story" else "change")
        deps = [d.strip() for d in args.deps.split(",") if d.strip()]
        body = open(args.body_file).read() if args.body_file else None
        item = project.create(args.kind, args.title, story_type=args.type, size=size, body=body,
                              priority=args.priority, dependencies=deps)
        if args.labels:
            item.update_status(labels=[l.strip() for l in args.labels.split(",") if l.strip()])
        if args.discovered_from:
            graph.add_link(project, item, "discovered-from", args.discovered_from)
        return {"item": item.id, "path": str(item.path.relative_to(project.root)),
                "doc": str(item.doc_path.relative_to(project.root)), "size": size,
                "next": f"write {item.doc_path.relative_to(project.root)}, then `speky check {item.id}`"}
    if cmd == "state":
        return protocol.state(project)
    if cmd == "ready":
        return {"items": graph.ready(project)}
    if cmd == "capabilities":
        caps = verification.capabilities_report(project)
        return {"capabilities": caps, "total_requirements": sum(c["requirements"] for c in caps),
                "valid": all(not c["problems"] for c in caps)}
    if cmd == "next":
        return protocol.next_action(project, args.id)
    if cmd == "check":
        return validation.check(project, project.find(args.id), force=args.force)
    if cmd == "finding":
        item = project.find(args.id)
        ledger = validation.Ledger(item)
        if args.action == "add":
            round_ = (item.load_status().get("validation") or {}).get("round", 0)
            return ledger.add(args.text, args.severity, kind=args.kind, evidence=args.evidence,
                              round_=round_, max_questions=int(project.config.get("max_questions", 5)))
        if args.action == "list":
            return {"item": item.id, "findings": [f for f in ledger.findings
                                                  if args.all or f["status"] == "open"]}
        return ledger.resolve(args.finding, args.status, args.ruling)
    if cmd == "start":
        return verification.start(project, project.find(args.id))
    if cmd == "evidence":
        return verification.record_evidence(project, project.find(args.id), args.requirement,
                                            args.status, args.evidence)
    if cmd == "verify":
        return verification.verify(project, project.find(args.id), run=args.run)
    if cmd == "archive":
        return verification.archive(project, project.find(args.id), force_reason=args.force)
    if cmd == "decide":
        return journal.decide(project, args.text, args.type, args.ref)
    if cmd == "remember":
        return journal.remember(project, args.fact, args.topic, args.always or None, args.read_when)
    if cmd == "knowledge":
        if args.action == "list":
            return {"topics": knowledge.topics(project)}
        if not args.topic:
            raise SpekyError("topic_required", "Name a topic.", "Run `speky knowledge` to list topics.")
        if args.action == "show":
            path = knowledge.knowledge_dir(project) / f"{args.topic}.md"
            if not path.exists():
                raise SpekyError("topic_not_found", f"No knowledge topic '{args.topic}'.")
            return {"topic": args.topic, "entries": knowledge.entries_of(path.read_text())}
        return knowledge.promote(project, args.topic, args.title or args.topic.replace("-", " ").capitalize())
    if cmd == "phases":
        action = args.action or "list"
        if action in ("list", "status"):
            cur = phases_mod.current(project)
            return {"phases": [p.to_dict() for p in phases_mod.all_phases(project)],
                    "current": cur.id if cur else None}
        if action == "show":
            return phases_mod.get(project, args.id).to_dict()
        if action in ("add", "create"):
            pid = args.id or (args.name if action == "create" else None)
            name = args.name if action == "add" else args.name.replace("-", " ").title()
            return phases_mod.add(project, name, pid, args.description).to_dict()
        if action == "start":
            return phases_mod.set_status(project, args.id, "doing").to_dict()
        if action == "defer":
            return phases_mod.set_status(project, args.id, "deferred").to_dict()
        if action == "deliverable":
            return phases_mod.add_deliverable(project, args.id, args.name, args.run, args.pass_criteria)
        if action == "verify":
            return phases_mod.verify_deliverable(project, args.id, args.deliverable, args.evidence)
        if action == "check":
            return phases_mod.check(project, args.id)
        if action == "complete":
            result = phases_mod.check(project, args.id)
            if not result["passed"] and not args.force:
                missing = [d["id"] for d in result["deliverables"] if not d["verified"]]
                raise SpekyError("phase_gate_not_met",
                                 f"{args.id} is not done: unverified deliverables {missing or '-'}, "
                                 f"open tasks {result['open_tasks'] or '-'}, open specs {result['open_specs'] or '-'}.",
                                 f"Finish them, or `speky phases complete {args.id} --force \"<reason>\"`.")
            phase = phases_mod.set_status(project, args.id, "done")
            if args.force:
                journal.decide(project, f"Completed phase {args.id} without its gate: {args.force}", "decision")
            return {**phase.to_dict(), "check": result}
        if action == "guide":
            raise SpekyError("use_context", "Phase guides are produced by `speky context --phase <id>`.",
                             f"Run `speky context --phase {args.id}`.")
        raise SpekyError("use_skill", "Suggesting phases is judgement work for the agent.",
                         "Follow the speky-plan skill (roadmap mode), then `speky phases add`.")
    if cmd == "task":
        tasks = Tasks(project)
        if args.action == "add":
            refs_ = [r.strip() for r in args.refs.split(",") if r.strip()]
            return tasks.add(args.text, args.phase, args.epic, args.parent, refs_)
        if args.action == "list":
            return {"tasks": tasks.list(args.status, args.phase)}
        if args.action == "promote":
            return tasks.promote(args.id, args.to, args.type)
        status = {"start": "doing", "done": "done", "defer": "deferred", "todo": "todo"}[args.action]
        return tasks.set_status(args.id, status, args.note)
    if cmd == "owner":
        oa = OwnerActions(project)
        if args.action == "add":
            return oa.add(args.text, args.section, args.note)
        if args.action == "done":
            return oa.set_done(args.id, True, args.note)
        return {"actions": oa.items() if args.all else oa.open_items()}
    if cmd == "handoff":
        notes = continuity.parse_handoff_file(open(args.file).read()) if args.file else {}
        return continuity.handoff(
            project, summary=args.summary or notes.get("summary", ""),
            done=(args.done or []) + notes.get("done", []), learned=(args.learned or []) + notes.get("learned", []),
            next_=(args.next or []) + notes.get("next", []), watch=(args.watch or []) + notes.get("watch", []),
            mechanism=(args.mechanism or []) + notes.get("mechanism", []),
            title=args.title or notes.get("title", ""), run_tests=not args.no_tests, commit=args.commit)
    if cmd == "checkpoint":
        snap = continuity.checkpoint(project, run_tests=args.run_tests, auto=args.auto)
        return {"at": snap["at"], "head": snap["head"], "uncommitted": len(snap["uncommitted"]),
                "commits_since_handoff": len(snap["commits_since_handoff"]), "last_test": snap.get("last_test")}
    if cmd == "refs":
        return refs.scan(project)
    if cmd == "adr":
        if args.action == "new":
            return journal.adr_new(project, args.title, args.context, args.decision, args.supersedes)
        return {"adrs": journal.adr_list(project)}
    if cmd == "term":
        return journal.term(project, args.word, args.definition)
    if cmd == "gate":
        item = project.find(args.id)
        if args.action == "add":
            return graph.add_gate(item, args.type, args.reason)
        return graph.resolve_gate(item, args.gate, args.by, args.note)
    if cmd == "link":
        return graph.add_link(project, project.find(args.id), args.type, args.to)
    if cmd == "prime":
        return protocol.prime_hook_json(project) if args.hook_json else protocol.prime(project)
    if cmd == "setup":
        if not args.harness:
            raise SpekyError("harness_required", "Name a harness.",
                             f"One of: {', '.join(harness.RECIPES)} (or --list).")
        if args.check:
            return harness.check(project, args.harness)
        if args.remove:
            return harness.remove(project, args.harness)
        return harness.setup(project, args.harness)
    if cmd == "migrate":
        if not project.dir.is_dir():
            raise SpekyError("not_initialized", f"No .speky/ folder in {project.root}.",
                             "Nothing to migrate; start with `speky init`.")
        if args.done:
            return migrate.mark_done(project, args.done)
        return migrate.apply(project) if args.apply else migrate.plan(project)
    if cmd == "set":
        item = project.find(args.id)
        changes = {}
        if args.status:
            changes["status"] = args.status
        if args.labels is not None:
            changes["labels"] = [l.strip() for l in args.labels.split(",") if l.strip()]
        if not changes:
            raise SpekyError("nothing_to_set", "Give --status and/or --labels.")
        item.update_status(**changes)
        return {"item": item.id, **changes}
    raise SpekyError("unknown_command", f"Unknown command {cmd}.")


def main(argv: List[str] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    try:
        result = run(argv)
    except SpekyError as e:
        if as_json:
            print(json.dumps({"ok": False, "error": e.to_dict()}))
        else:
            print(f"❌ {e.message}" + (f"\n   Fix: {e.fix}" if e.fix else ""), file=sys.stderr)
        return 1
    cmd = argv[0] if argv else ""
    if cmd == "prime":
        print(result, end="" if result.endswith("\n") else "\n")
        return 0
    if as_json:
        print(json.dumps(result if not isinstance(result, dict) else {"ok": True, **result}, default=str))
    else:
        print(_human(cmd, result))
    if cmd == "verify" and not result.get("passed"):
        return 2
    return 0
