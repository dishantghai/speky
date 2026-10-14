"""v3 commands of the `speky` CLI. `speky.py` hands these command names to `main()` here.

Every command accepts `--json`: exactly one JSON document on stdout, human text on stderr.
Errors exit 1 with {"ok": false, "error": {"code", "message", "fix"}}.
"""
import argparse
import json
import re
import sys
from typing import List

from . import continuity, graph, harness, journal, knowledge, migrate, protocol, refs, validation, verification
from . import commit as commit_mod
from . import context as context_mod
from . import deps as deps_mod
from . import design as design_mod
from . import epics as epics_mod
from . import imports as imports_mod
from . import maintenance, projectinfo
from . import phases as phases_mod
from . import testing as testing_mod
from .owner import OwnerActions
from .tasks import Tasks
from .errors import SpekyError
from .items import STORY_PREFIXES, Project

REMOVED = {"renumber": "IDs never change; implementation order is `speky order`.",
           "host": "host mode is gone: the agent drives SPEKY directly (`speky next --json`).",
           "sync": "codebase.md is gone: keep facts the code can't show with `speky remember --topic <topic>`."}
COMMANDS = {"capabilities", "task", "phases", "owner", "knowledge", "handoff", "checkpoint", "refs",
            "init", "status", "context", "epic", "epics", "deps", "order", "commit", "cleanup", "review",
            "import", "import-status", "design", "test", "config", "backlog", "adopt", "validate-spec",
            "validate-story", "plan", "implement", "complete", "sequence", "infer-deps", "mark-foundation",
            "reset-deps", "fix-circular-deps", "decisions", "reconcile", "poc-import", "spec", "story",
            "renumber", "host", "sync", "run", "new", "state", "ready", "next", "check", "finding", "start", "evidence", "verify",
            "archive", "decide", "remember", "adr", "term", "gate", "link", "prime", "setup",
            "migrate", "set"}

HELP = """SPEKY: spec-driven development for AI coding agents.

Start here
  New project        speky init [--harness claude-code]   then ask your agent to build something
  Existing project   speky init --from-project --harness claude-code
  SPEKY v2 project   speky migrate                          (dry run, then --apply)
  What to do next    speky next                             (the one next action and its skill)
  No coding agent    speky run "<what you want>"            (SPEKY's own agent; needs a model)

Work items
  spec | story "<title>"   create a change (also: new spec|story); --epic --related --files --phase
  task add|start|done [--verify]|defer|promote|list   small work without a spec (verify W<n> runs the tests)
  epic add|show|attach|detach|list            stories that share context
  phases list|add|start|deliverable|verify|check|complete|order   phases; deliverables are the gate
  deps add|remove|clear|foundation|cycles  ·  order [--export]        dependencies and order
  set <id> --status|--priority  ·  link <id> --type …  ·  gate add|…  ·  backlog (deferred items)

Building
  check <id>  ·  finding add|list|resolve     validation that converges
  plan | context <id>                         planning / context packet (pointers for the agent)
  implement <id> (= start)  ·  evidence <id> <R#>  ·  verify <id>  ·  complete <id>  ·  archive <id>
  commit <id>  ·  review [<id>]  ·  cleanup  ·  test init|run|coverage|gaps|link|red|green  ·  design …

Memory and session
  handoff  ·  checkpoint  ·  prime  ·  status | state | ready  ·  remember --topic  ·  knowledge
  decide  ·  adr  ·  owner add|done|list  ·  term  ·  refs  ·  capabilities  ·  import add|link|status|reconcile

Setup
  setup <claude-code|codex|cursor|windsurf|vscode|antigravity|agents-md>  ·  config get|set|model|providers
  migrate [--apply|--done TASK]

v2 names that still work: adopt, validate-spec, validate-story (= check), sequence (= order),
  mark-foundation, reset-deps, fix-circular-deps, infer-deps (= deps …), decisions, epics, import-status,
  reconcile, poc-import (= import …). Removed: renumber, host, sync (each says what replaces it).

Every command takes --json (one JSON document; errors carry a fix). Nothing ever prompts.
Reference: https://github.com/dishantghai/speky/blob/main/docs/v3/CONTRACTS.md"""


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="speky", description=HELP,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>")

    def add(name, **kw):
        sp = sub.add_parser(name, **kw)
        sp.add_argument("--json", action="store_true", help="print one JSON document")
        return sp

    def new_options(sp):
        sp.add_argument("title")
        sp.add_argument("--type", default="feature", choices=list(STORY_PREFIXES))
        sp.add_argument("--size", default=None, choices=["quick", "small", "change", "epic"])
        sp.add_argument("--priority", default="P2")
        sp.add_argument("--deps", default="", help="comma-separated item IDs")
        sp.add_argument("--discovered-from", default=None)
        sp.add_argument("--body-file", default=None, help="use this file as the document")
        sp.add_argument("--labels", default="", help="comma-separated labels (select done checks)")
        sp.add_argument("--epic", default=None, help="add the story to this epic")
        sp.add_argument("--related", "--spec", "--specs", dest="related", default="",
                        help="comma-separated related specs")
        sp.add_argument("--files", default="", help="comma-separated affected files")
        sp.add_argument("--phase", default=None)

    sp = add("new", help="create a change")
    sp.add_argument("kind", choices=["spec", "story"])
    new_options(sp)
    new_options(add("spec", help="create a spec (same as `new spec`)"))
    new_options(add("story", help="create a story (same as `new story`)"))

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
    po = psub.add_parser("order", help="set the order phases are listed and worked in")
    po.add_argument("ids", nargs="+")
    po.add_argument("--json", action="store_true")

    sp = add("task")
    tsub = sp.add_subparsers(dest="action", required=True)
    ta = tsub.add_parser("add")
    ta.add_argument("text")
    ta.add_argument("--phase", default=None)
    ta.add_argument("--epic", default=None)
    ta.add_argument("--parent", default=None)
    ta.add_argument("--refs", default="", help="comma-separated, e.g. adr:0021,screen:RV-1")
    ta.add_argument("--labels", default="", help="comma-separated, e.g. ui (selects a playbook)")
    ta.add_argument("--json", action="store_true")
    for name in ("start", "done", "defer", "todo"):
        tx = tsub.add_parser(name)
        tx.add_argument("id")
        tx.add_argument("--note", default="")
        if name == "done":
            tx.add_argument("--verify", action="store_true", help="run verify_command first; done only if it passes")
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

    # ---- one SPEKY: every v2 capability as a native command
    sp = add("init", help="start SPEKY in this project")
    sp.add_argument("idea", nargs="?", default="")
    sp.add_argument("--from-project", action="store_true", help="read this project's docs and manifests")
    sp.add_argument("--harness", default=None, help="also run `speky setup <harness>`")

    sp = add("status", help="items, phase, tasks and next action")
    sp = add("context", help="context packet for an item or a phase")
    sp.add_argument("id", nargs="?")
    sp.add_argument("--phase", default=None)
    sp.add_argument("--full", action="store_true", help="inline the documents")

    sp = add("epic", help="epics: groups of stories")
    esub = sp.add_subparsers(dest="action")
    ea = esub.add_parser("add")
    ea.add_argument("name")
    ea.add_argument("--spec", default=None)
    ea.add_argument("--stories", default="")
    ea.add_argument("--description", default="")
    ea.add_argument("--json", action="store_true")
    for name in ("show",):
        ex = esub.add_parser(name)
        ex.add_argument("id")
        ex.add_argument("--json", action="store_true")
    for name in ("attach", "detach"):
        ex = esub.add_parser(name)
        ex.add_argument("id")
        ex.add_argument("story")
        ex.add_argument("--json", action="store_true")
    el = esub.add_parser("list")
    el.add_argument("--json", action="store_true")
    add("epics", help="list epics (same as `epic list`)")

    sp = add("deps", help="dependencies between items")
    dsub = sp.add_subparsers(dest="action", required=True)
    for name in ("add", "remove"):
        dx = dsub.add_parser(name)
        dx.add_argument("id")
        dx.add_argument("on", nargs="+")
        dx.add_argument("--json", action="store_true")
    dc = dsub.add_parser("clear")
    dc.add_argument("id", nargs="?")
    dc.add_argument("--all", action="store_true")
    dc.add_argument("--json", action="store_true")
    df = dsub.add_parser("foundation")
    df.add_argument("id")
    df.add_argument("--json", action="store_true")
    dy = dsub.add_parser("cycles")
    dy.add_argument("--json", action="store_true")
    sp = add("order", help="implementation order from dependencies and priority")
    sp.add_argument("--export", action="store_true", help="write .speky/roadmap.md")
    sp.add_argument("--open", action="store_true", help="only items not done")

    sp = add("commit", help="commit a verified change")
    sp.add_argument("id")
    sp.add_argument("--files", default="", help="comma-separated files (default: changed since start)")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--force", default=None, metavar="REASON")

    sp = add("cleanup", help="move clutter files to a recoverable backup")
    sp.add_argument("--apply", action="store_true")
    sp.add_argument("--dry-run", action="store_true", help="(default)")
    sp = add("review", help="re-check completed work: evidence and tests")
    sp.add_argument("id", nargs="?")
    sp.add_argument("--no-tests", action="store_true")

    sp = add("import", help="bring documents or prototype code into SPEKY")
    isub = sp.add_subparsers(dest="action")
    ia = isub.add_parser("add")
    ia.add_argument("name")
    ia.add_argument("--from", dest="sources", action="append", default=[])
    ia.add_argument("--code", action="append", default=[])
    ia.add_argument("--json", action="store_true")
    il = isub.add_parser("link")
    il.add_argument("name")
    il.add_argument("refs", nargs="+")
    il.add_argument("--json", action="store_true")
    for name in ("done", "show", "reconcile"):
        ix = isub.add_parser(name)
        ix.add_argument("name")
        ix.add_argument("--json", action="store_true")
    ist = isub.add_parser("status")
    ist.add_argument("--json", action="store_true")
    add("import-status", help="same as `import status`")

    sp = add("design", help="design assets and the design system")
    gsub = sp.add_subparsers(dest="action")
    gi = gsub.add_parser("init")
    gi.add_argument("--tech", default="")
    gi.add_argument("--json", action="store_true")
    ga = gsub.add_parser("add")
    ga.add_argument("path")
    ga.add_argument("--type", dest="kind", default="hifi", choices=["hifi", "lofi", "icon", "system"])
    ga.add_argument("--for", dest="item", default=None)
    ga.add_argument("--json", action="store_true")
    gl = gsub.add_parser("link")
    gl.add_argument("file")
    gl.add_argument("item")
    gl.add_argument("--json", action="store_true")
    gn = gsub.add_parser("analysis")
    gn.add_argument("file")
    gn.add_argument("--from", dest="analysis", required=True, help="markdown file with the analysis")
    gn.add_argument("--json", action="store_true")
    gc = gsub.add_parser("conflict")
    gc.add_argument("type", choices=["color", "typography", "spacing", "radius", "shadow", "layout", "component"])
    gc.add_argument("location")
    gc.add_argument("--existing", required=True)
    gc.add_argument("--new", required=True)
    gc.add_argument("--severity", default="medium")
    gc.add_argument("--json", action="store_true")
    gr = gsub.add_parser("resolve")
    gr.add_argument("conflict")
    gr.add_argument("--value", required=True)
    gr.add_argument("--reason", required=True)
    gr.add_argument("--json", action="store_true")
    gs = gsub.add_parser("status")
    gs.add_argument("--json", action="store_true")

    sp = add("test", help="tests: init, run, coverage, gaps, link, red/green")
    xsub = sp.add_subparsers(dest="action")
    for name in ("init", "status", "coverage"):
        xx = xsub.add_parser(name)
        xx.add_argument("--json", action="store_true")
    xr = xsub.add_parser("run")
    xr.add_argument("files", nargs="*")
    xr.add_argument("--type", dest="kind", default="unit", choices=["unit", "e2e"])
    xr.add_argument("--json", action="store_true")
    xg = xsub.add_parser("gaps")
    xg.add_argument("id", nargs="?")
    xg.add_argument("--json", action="store_true")
    xl = xsub.add_parser("link")
    xl.add_argument("id")
    xl.add_argument("requirement")
    xl.add_argument("test")
    xl.add_argument("--json", action="store_true")
    for name in ("red", "green"):
        xt = xsub.add_parser(name)
        xt.add_argument("id")
        xt.add_argument("requirement")
        xt.add_argument("--cmd", dest="test_cmd", required=True, help="command that runs just this test")
        xt.add_argument("--json", action="store_true")

    sp = add("run", help="SPEKY's own agent (no coding agent needed; uses a configured model)")
    sp.add_argument("goal", nargs="?", default="")
    sp.add_argument("--next", action="store_true", help="work through `speky next` until idle")
    sp.add_argument("--model", default=None, help="provider/model for this run")
    sp.add_argument("--max-steps", type=int, default=60)
    sp.add_argument("--allow-shell", action="store_true", help="allow any shell command (default: tests and read-only git)")

    sp = add("config", help="show or change .speky/speky.yaml")
    csub = sp.add_subparsers(dest="action")
    cm = csub.add_parser("model", help="show or set the model `speky run` uses (~/.speky/models.yaml)")
    cm.add_argument("ref", nargs="?")
    cm.add_argument("--json", action="store_true")
    cp = csub.add_parser("providers", help="model providers and whether they are ready")
    cp.add_argument("--json", action="store_true")
    cg = csub.add_parser("get")
    cg.add_argument("key", nargs="?")
    cg.add_argument("--json", action="store_true")
    cs = csub.add_parser("set")
    cs.add_argument("key")
    cs.add_argument("value")
    cs.add_argument("--json", action="store_true")

    sp = add("backlog", help="deferred items waiting for review")
    add("adopt", help="same as `check` for a folder made by hand").add_argument("id")
    for alias in ("validate-spec", "validate-story"):
        sp = add(alias, help="same as `check`")
        sp.add_argument("id")
        sp.add_argument("--force", action="store_true")
        sp.add_argument("--quick", action="store_true", help="(accepted; check is always quick)")
    for alias, help_ in (("plan", "planning packet for an item (the agent writes plan.md)"),
                         ("implement", "start an item and get its context packet"),
                         ("complete", "verify an item, then archive it")):
        sp = add(alias, help=help_)
        sp.add_argument("id")
        sp.add_argument("--run", default=None, help="(complete) verify command")
    add("sequence", help="same as `order`").add_argument("--export", action="store_true")
    add("infer-deps", help="dependencies are inferred by the agent (speky-plan skill)").add_argument("id", nargs="?")
    add("mark-foundation", help="same as `deps foundation`").add_argument("id")
    sp = add("reset-deps", help="same as `deps clear`")
    sp.add_argument("id", nargs="?")
    sp.add_argument("--all", action="store_true")
    add("fix-circular-deps", help="same as `deps cycles`")
    add("decisions", help="decision log, ADRs and tech knowledge")
    add("reconcile", help="same as `import reconcile`").add_argument("name")
    sp = add("poc-import", help="same as `import add --code`")
    sp.add_argument("--path", required=False, default=None)
    sp.add_argument("--name", default="poc")
    for gone, use in (("renumber", "IDs never change; see `speky order`"),
                      ("host", "the agent drives SPEKY directly; see `speky next`"),
                      ("sync", "knowledge topics replace codebase.md; see `speky remember --topic`")):
        add(gone, help=f"removed: {use}")
    p.format_help = lambda: f"usage: speky <command> [options] [--json]\n\n{HELP}\n"
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
    if cmd == "run":
        from . import runner
        proj = Project.open(require=False)
        goal = args.goal or ("Do the next SPEKY action (`speky next`), then continue with the following ones "
                             "until `speky next` says idle or you need the owner. Hand off at the end."
                             if args.next else "")
        if not goal:
            raise SpekyError("goal_required", "Say what to do: speky run \"<what you want>\", or --next.")
        r = runner.Runner(proj, runner.make_completer(proj, args.model), allow_shell=args.allow_shell,
                          max_steps=args.max_steps)
        return r.run(goal)
    if cmd == "config" and args.action in ("model", "providers"):
        from speky_llm import LLMRouter, save_model
        proj = Project.open(require=False)
        router = LLMRouter(project_root=proj.root)
        if args.action == "providers":
            return {"providers": {name: router.status(name) for name in sorted(router.providers)},
                    "model": router.model_ref}
        if args.ref:
            router.resolve(args.ref)  # validates provider/model
            save_model(args.ref)
            return {"model": args.ref, "file": "~/.speky/models.yaml"}
        return {"model": router.model_ref, "fallbacks": router.fallbacks}
    if cmd == "init":
        from . import bootstrap
        from .config import find_root
        return bootstrap.init(find_root(), args.idea, args.from_project, args.harness)
    if cmd == "checkpoint" and args.auto and not Project.open(require=False).dir.is_dir():
        return {"skipped": "not a SPEKY project"}
    project = Project.open(require=cmd not in ("migrate", "setup"))
    if cmd == "setup" and not project.dir.is_dir() and not (args.check or args.remove):
        project.dir.mkdir()  # setup bootstraps a v3 project (no LLM needed, unlike v2 `init`)

    if cmd in ("new", "spec", "story"):
        kind = args.kind if cmd == "new" else cmd
        size = args.size or ("small" if kind == "story" else "change")
        deps_ = [d.strip() for d in args.deps.split(",") if d.strip()]
        body = open(args.body_file).read() if args.body_file else None
        item = project.create(kind, args.title, story_type=args.type, size=size, body=body,
                              priority=args.priority, dependencies=deps_)
        extra = {}
        if args.labels:
            extra["labels"] = [l.strip() for l in args.labels.split(",") if l.strip()]
        if args.related:
            extra["related_specs"] = [project.find(r.strip()).id for r in args.related.split(",") if r.strip()]
        if args.files:
            extra["affected_files"] = [f.strip() for f in args.files.split(",") if f.strip()]
        if args.phase:
            extra["phase"] = phases_mod.get(project, args.phase).id
        if extra:
            item.update_status(**extra)
        if args.epic:
            epics_mod.attach(project, args.epic, item.id)
        if args.discovered_from:
            graph.add_link(project, item, "discovered-from", args.discovered_from)
        return {"item": item.id, "path": str(item.path.relative_to(project.root)),
                "doc": str(item.doc_path.relative_to(project.root)), "size": size,
                "next": f"write {item.doc_path.relative_to(project.root)} (speky-propose skill), "
                        f"then `speky check {item.id}`"}
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
    if cmd == "evidence" and re.match(r"^[Ww]\d+$", args.id) and not project.try_find(args.id):
        return Tasks(project).record_evidence(args.id, args.requirement, args.status, args.evidence or "")
    if cmd == "evidence":
        return verification.record_evidence(project, project.find(args.id), args.requirement,
                                            args.status, args.evidence)
    if cmd == "verify":
        if re.match(r"^[Ww]\d+$", args.id) and not project.try_find(args.id):
            return Tasks(project).verify(args.id, run=args.run)  # a task: tests pass → done
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
        if action == "order":
            return phases_mod.set_order(project, args.ids)
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
            labels_ = [l.strip() for l in args.labels.split(",") if l.strip()]
            return tasks.add(args.text, args.phase, args.epic, args.parent, refs_, labels=labels_)
        if args.action == "list":
            return {"tasks": tasks.list(args.status, args.phase)}
        if args.action == "promote":
            return tasks.promote(args.id, args.to, args.type)
        if args.action == "done" and args.verify:
            result = tasks.verify(args.id)
            if not result["passed"]:
                raise SpekyError("task_not_verified", f"{args.id} stays open: `{result['command']}` failed.",
                                 "Fix the failure and run it again, or mark it done without --verify.")
            return result
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
        name = harness.ALIASES.get(args.harness, args.harness)
        if args.check:
            return harness.check(project, name)
        if args.remove:
            return harness.remove(project, name)
        return harness.setup(project, name)
    if cmd == "migrate":
        if not project.dir.is_dir():
            raise SpekyError("not_initialized", f"No .speky/ folder in {project.root}.",
                             "Nothing to migrate; start with `speky init`.")
        if args.done:
            return migrate.mark_done(project, args.done)
        return migrate.apply(project) if args.apply else migrate.plan(project)
    if cmd == "set" and re.match(r"^[Ww]\d+$", args.id) and args.labels is not None and not args.status:
        tasks = Tasks(project)
        t = tasks.get(args.id)
        t["labels"] = [l.strip() for l in args.labels.split(",") if l.strip()]
        tasks.save()
        return {"task": t["id"], "labels": t["labels"]}
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
    # ---- one SPEKY: native homes of the v2 commands
    if cmd in REMOVED:
        raise SpekyError("command_removed", f"`speky {cmd}` was removed.", REMOVED[cmd])
    if cmd == "status":
        st = protocol.state(project)
        cur = phases_mod.current(project)
        return {**st, "phase": cur.to_dict() if cur else None, "next": protocol.next_action(project),
                "tasks": Tasks(project).list(), "owner": OwnerActions(project).open_items()}
    if cmd == "context":
        if args.phase:
            return context_mod.phase_packet(project, args.phase, args.full)
        if not args.id:
            cur = phases_mod.current(project)
            if not cur:
                raise SpekyError("id_required", "Name an item, or --phase <id>.")
            return context_mod.phase_packet(project, cur.id, args.full)
        return context_mod.item_packet(project, args.id, args.full)
    if cmd in ("epic", "epics"):
        action = "list" if cmd == "epics" else (args.action or "list")
        if action == "list":
            return {"epics": epics_mod.list_all(project)}
        if action == "add":
            stories = [x.strip() for x in args.stories.split(",") if x.strip()]
            return epics_mod.add(project, args.name, args.spec, stories, args.description)
        if action == "show":
            return epics_mod.get(project, args.id)
        if action == "attach":
            return epics_mod.attach(project, args.id, args.story)
        return epics_mod.detach(project, args.id, args.story)
    if cmd == "deps":
        if args.action == "add":
            return deps_mod.add(project, args.id, args.on)
        if args.action == "remove":
            return deps_mod.remove(project, args.id, args.on)
        if args.action == "clear":
            if not args.id and not args.all:
                raise SpekyError("id_required", "Name an item, or --all.")
            return deps_mod.clear(project, None if args.all else args.id)
        if args.action == "foundation":
            return deps_mod.foundation(project, args.id)
        return {"cycles": graph.cycles(project)}
    if cmd in ("order", "sequence"):
        rows = deps_mod.order(project, include_done=not getattr(args, "open", False))
        out = {"order": rows, "cycles": graph.cycles(project)}
        if args.export:
            out["exported"] = deps_mod.export(project)
        return out
    if cmd == "mark-foundation":
        return deps_mod.foundation(project, args.id)
    if cmd == "reset-deps":
        if not args.id and not args.all:
            raise SpekyError("id_required", "Name an item, or --all.")
        return deps_mod.clear(project, None if args.all else args.id)
    if cmd == "fix-circular-deps":
        cycles = graph.cycles(project)
        return {"cycles": cycles, "next": "Break each cycle with `speky deps remove <id> <dep>`." if cycles
                else "No dependency cycles."}
    if cmd == "infer-deps":
        return {"order": deps_mod.order(project, include_done=False),
                "next": "Inferring dependencies is judgement work: follow the speky-plan skill (dependencies "
                        "step) and record each with `speky deps add <id> <depends-on>`."}
    if cmd == "commit":
        files = [f.strip() for f in args.files.split(",") if f.strip()]
        return commit_mod.commit(project, args.id, files or None, args.dry_run, args.force)
    if cmd == "cleanup":
        return maintenance.cleanup(project, apply=args.apply)
    if cmd == "review":
        return maintenance.review(project, args.id, run_tests=not args.no_tests)
    if cmd in ("import", "import-status", "reconcile", "poc-import"):
        if cmd == "import-status" or (cmd == "import" and args.action in (None, "status")):
            return {"imports": imports_mod.status(project)}
        if cmd == "reconcile":
            return imports_mod.packet(project, args.name, reconcile=True)
        if cmd == "poc-import":
            if not args.path:
                raise SpekyError("path_required", "Give the prototype folder: --path <dir>.")
            return imports_mod.add(project, args.name, code=[args.path])
        if args.action == "add":
            return imports_mod.add(project, args.name, args.sources, args.code)
        if args.action == "link":
            return imports_mod.link(project, args.name, args.refs)
        if args.action == "done":
            return imports_mod.done(project, args.name)
        return imports_mod.packet(project, args.name, reconcile=args.action == "reconcile")
    if cmd == "design":
        action = args.action or "status"
        if action == "init":
            return design_mod.init(project, args.tech)
        if action == "add":
            return design_mod.add(project, args.path, args.kind, args.item)
        if action == "link":
            return design_mod.link(project, args.file, args.item)
        if action == "analysis":
            return design_mod.record_analysis(project, args.file, args.analysis)
        if action == "conflict":
            return design_mod.add_conflict(project, args.type, args.location, args.existing, args.new, args.severity)
        if action == "resolve":
            return design_mod.resolve_conflict(project, args.conflict, args.value, args.reason)
        return design_mod.status(project)
    if cmd == "test":
        action = args.action or "status"
        if action == "init":
            return testing_mod.init(project)
        if action == "run":
            return testing_mod.run(project, args.kind, args.files)
        if action == "coverage":
            return testing_mod.coverage(project)
        if action == "gaps":
            return testing_mod.gaps(project, args.id)
        if action == "link":
            return testing_mod.link(project, args.id, args.requirement, args.test)
        if action in ("red", "green"):
            return testing_mod.tdd(project, args.id, args.requirement, action, args.test_cmd)
        return testing_mod.status(project)
    if cmd == "config":
        from . import config as config_mod
        cfg = project.config
        if args.action == "set":
            import yaml as _yaml
            node = cfg
            keys = args.key.split(".")
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            current = node.get(keys[-1]) if isinstance(node, dict) else None
            from .config import DEFAULTS
            stringy = keys[-1].endswith("command") or isinstance(current, str) or \
                (len(keys) == 1 and isinstance(DEFAULTS.get(keys[0]), str))
            value = args.value if stringy else _yaml.safe_load(args.value)
            node[keys[-1]] = value
            config_mod.save(project.root, cfg)
            return {"set": args.key, "value": value}
        if args.action == "get" and args.key:
            node = cfg
            for k in args.key.split("."):
                node = node.get(k) if isinstance(node, dict) else None
            return {"key": args.key, "value": node}
        return {"config": cfg, "file": ".speky/speky.yaml"}
    if cmd == "backlog":
        import json as _json
        path = project.dir / "backlog.json"
        items = _json.loads(path.read_text()) if path.exists() else []
        deferred = [i for i in items if i.get("kind") != "task" and i.get("status") == "pending"]
        md_items = []
        if (project.dir / "backlog.md").exists():
            md_items = [l[3:].strip() for l in (project.dir / "backlog.md").read_text().splitlines()
                        if l.startswith("## ")]
        return {"deferred": deferred, "deferred_md": md_items,
                "next": "Promote what matters: `speky task add \"...\"` or `speky new story \"...\"`; "
                        "the rest can stay deferred."}
    if cmd in ("adopt", "validate-spec", "validate-story"):
        return validation.check(project, project.find(args.id), force=getattr(args, "force", False))
    if cmd == "plan":
        packet = context_mod.item_packet(project, args.id)
        return {**packet, "instruction": "Write plan.md for this item following the speky-plan skill, "
                                         f"then `speky start {packet['item']}`."}
    if cmd == "implement":
        started = verification.start(project, project.find(args.id))
        return {**started, "context": context_mod.item_packet(project, args.id)}
    if cmd == "complete":
        item = project.find(args.id)
        result = verification.verify(project, item, run=args.run)
        if not result["passed"]:
            return result
        return {**result, "archive": verification.archive(project, item)}
    if cmd == "decisions":
        return {"decisions": journal.decisions(project), "adrs": journal.adr_list(project),
                "tech": [e for t in knowledge.topics(project) if t["topic"] == "tech"
                         for e in knowledge.entries_of((project.root / t["file"]).read_text())],
                "legacy_tech_decisions": ".speky/context/tech_decisions.md"
                if (project.dir / "context" / "tech_decisions.md").exists() else None}
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
