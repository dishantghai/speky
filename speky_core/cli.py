"""v3 commands of the `speky` CLI. `speky.py` hands these command names to `main()` here.

Every command accepts `--json`: exactly one JSON document on stdout, human text on stderr.
Errors exit 1 with {"ok": false, "error": {"code", "message", "fix"}}.
"""
import argparse
import json
import sys
from typing import List

from . import graph, harness, journal, migrate, protocol, validation, verification
from .errors import SpekyError
from .items import STORY_PREFIXES, Project

COMMANDS = {"new", "state", "ready", "next", "check", "finding", "start", "evidence", "verify",
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
  decide | remember | adr | term   decision log, memory, ADRs, glossary
  gate add|resolve | link      human/ci/pr gates; typed links
  prime [--hook-json]          workflow + state for an agent session
  setup <harness>              install skills + instructions (claude-code, codex, agents-md)
  migrate [--apply]            bring a v2 project to v3 (dry run by default)
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

    add("state")
    add("ready")
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

    sp = add("prime")
    sp.add_argument("--hook-json", action="store_true")
    sp = add("setup")
    sp.add_argument("harness", nargs="?")
    sp.add_argument("--check", action="store_true")
    sp.add_argument("--remove", action="store_true")
    sp.add_argument("--list", action="store_true")
    sp = add("migrate")
    sp.add_argument("--apply", action="store_true")
    sp = add("set")
    sp.add_argument("id")
    sp.add_argument("--status", required=True,
                    choices=["draft", "ready", "in_progress", "review", "completed", "archived"])
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


def run(argv: List[str]) -> dict:
    args = _parser().parse_args(argv)
    cmd = args.cmd
    if cmd == "setup" and args.list:
        return {"harnesses": list(harness.RECIPES)}
    project = Project.open(require=cmd not in ("migrate",))

    if cmd == "new":
        size = args.size or ("small" if args.kind == "story" else "change")
        deps = [d.strip() for d in args.deps.split(",") if d.strip()]
        body = open(args.body_file).read() if args.body_file else None
        item = project.create(args.kind, args.title, story_type=args.type, size=size, body=body,
                              priority=args.priority, dependencies=deps)
        if args.discovered_from:
            graph.add_link(project, item, "discovered-from", args.discovered_from)
        return {"item": item.id, "path": str(item.path.relative_to(project.root)),
                "doc": str(item.doc_path.relative_to(project.root)), "size": size,
                "next": f"write {item.doc_path.relative_to(project.root)}, then `speky check {item.id}`"}
    if cmd == "state":
        return protocol.state(project)
    if cmd == "ready":
        return {"items": graph.ready(project)}
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
        return journal.remember(project, args.fact)
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
        return migrate.apply(project) if args.apply else migrate.plan(project)
    if cmd == "set":
        item = project.find(args.id)
        item.update_status(status=args.status)
        return {"item": item.id, "status": args.status}
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
