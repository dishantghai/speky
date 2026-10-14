"""Session continuity: handoff, checkpoint, the session log and the state snapshot.

Work must survive context compaction and new sessions without depending on conversation history:
- `speky checkpoint` records the mechanical state (git, uncommitted files, in-progress work, last test
  run) in `.speky/checkpoint.json`. A PreCompact hook runs it automatically.
- `speky handoff` additionally takes the agent's narrative (summary, done, learned, next, watch-outs),
  appends a dated entry to `.speky/log.md` and regenerates `.speky/state.md`.
- `speky prime` reads both at session start and tells the agent where to pick up.
"""
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from . import graph, vcs
from .items import DONE_STATUSES, Project, now, write_json

LOG_NAME = "log.md"
STATE_NAME = "state.md"
CHECKPOINT_NAME = "checkpoint.json"
LOCAL_FILES = ("checkpoint.json", "testing/runs.json", "turn.json")  # per machine: never committed
TURN_NAME = "turn.json"


def write_checkpoint(project: Project, data: dict) -> None:
    ensure_local_ignored(project)
    write_json(project.dir / CHECKPOINT_NAME, data)


def ensure_local_ignored(project: Project) -> None:
    """`.speky/.gitignore` lists SPEKY's per-machine files (checkpoint, last test runs)."""
    path = project.dir / ".gitignore"
    lines = path.read_text().splitlines() if path.exists() else ["# per-machine SPEKY state (speky checkpoint, speky test)"]
    missing = [f for f in LOCAL_FILES if f not in lines]
    if missing:
        project.dir.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines + missing) + "\n")
LOG_HEADER = "# Session log\n\nAppend-only: one entry per handoff, newest last. Written by `speky handoff`.\n"
SECTIONS = {"summary": "Where things stand", "done": "Done", "learned": "Learned", "next": "Next",
            "watch": "Watch out for", "mechanism": "Mechanism changes"}


# ---------------------------------------------------------------------------- mechanical state
def _git(root: Path, *args) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""
    except FileNotFoundError:
        return ""


def load_checkpoint(project: Project) -> dict:
    path = project.dir / CHECKPOINT_NAME
    return json.loads(path.read_text()) if path.exists() else {}


def snapshot(project: Project, run_tests: bool = False) -> dict:
    """Mechanical state of the project right now."""
    from .tasks import Tasks
    prev = load_checkpoint(project)
    head = vcs.head(project.root)
    dirty = [l[3:] for l in _git(project.root, "status", "--porcelain=v1").splitlines()
             if l[3:] and not l[3:].startswith(".speky/")]
    last_handoff = prev.get("last_handoff") or {}
    since = last_handoff.get("head")
    commits = []
    if since and since != head and since != vcs.NO_VCS:
        commits = [l for l in _git(project.root, "log", "--oneline", f"{since}..HEAD").splitlines() if l]
    in_progress = [{"id": i["id"], "title": i["title"], "status": i["status"]}
                   for i in graph.statuses(project).values() if i["status"] in ("in_progress", "review")]
    doing = [{"id": t["id"], "text": t["text"][:120]} for t in Tasks(project).list(status="doing")]
    snap = {"at": now(), "head": head, "branch": _git(project.root, "branch", "--show-current").strip(),
            "uncommitted": dirty, "commits_since_handoff": commits, "in_progress_items": in_progress,
            "doing_tasks": doing, "last_test": prev.get("last_test"), "last_handoff": last_handoff}
    if run_tests:
        cmd = project.config.get("verify_command") or ""
        if cmd:
            proc = subprocess.run(cmd, shell=True, cwd=project.root, capture_output=True, text=True)
            snap["last_test"] = {"command": cmd, "exit_code": proc.returncode, "passed": proc.returncode == 0,
                                 "at": now(), "head": head,
                                 "output_tail": "\n".join((proc.stdout + proc.stderr).splitlines()[-12:])}
    return snap


def checkpoint(project: Project, run_tests: bool = False, auto: bool = False, transcript: str = None) -> dict:
    snap = snapshot(project, run_tests=run_tests)
    snap["auto"] = auto
    if auto and transcript:  # before compaction: what the agent was in the middle of
        flight = in_flight_from_transcript(transcript)
        if flight:
            snap["in_flight"] = flight
    write_checkpoint(project, snap)
    return snap


# ---------------------------------------------------------------------------- handoff
def parse_handoff_file(text: str) -> Dict[str, object]:
    """Read `## Summary / ## Done / ## Learned / ## Next / ## Watch out for / ## Mechanism changes`."""
    aliases = {"summary": "summary", "where things stand": "summary", "done": "done", "learned": "learned",
               "next": "next", "next actions": "next", "watch out for": "watch", "watch": "watch",
               "watch-outs": "watch", "mechanism changes": "mechanism", "mechanism": "mechanism",
               "title": "title"}
    result: Dict[str, object] = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            current = aliases.get(m.group(1).strip().lower())
            continue
        if current:
            result.setdefault(current, []).append(line)
    out = {}
    for key, lines in result.items():
        body = "\n".join(lines).strip()
        if key in ("summary", "title"):
            out[key] = body
        else:  # one entry per bullet; indented or unbulleted lines continue the bullet above
            items: List[str] = []
            for l in body.splitlines():
                if not l.strip():
                    continue
                if re.match(r"^(\d+\.|-|\*)\s+", l) or not items:
                    items.append(re.sub(r"^(\d+\.|-|\*)\s+", "", l).strip())
                else:
                    items[-1] += " " + l.strip()
            out[key] = items
    return out


def handoff(project: Project, summary: str = "", done: List[str] = None, learned: List[str] = None,
            next_: List[str] = None, watch: List[str] = None, mechanism: List[str] = None,
            title: str = "", run_tests: bool = True, commit: bool = None) -> dict:
    snap = snapshot(project, run_tests=run_tests)
    prev_state = read_state(project)
    narrative = {
        "summary": summary or prev_state.get("summary", ""),
        "next": next_ if next_ else prev_state.get("next", []),
        "watch": watch if watch is not None else prev_state.get("watch", []),
    }
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = title or (done[0][:70] if done else "Handoff")

    # 1. log entry (append-only)
    log = project.dir / LOG_NAME
    if not log.exists():
        log.write_text(LOG_HEADER)
    entry = [f"\n## {stamp} · {title}\n"]
    for key, label in (("done", "Done"), ("learned", "Learned"), ("next", "Next"),
                       ("mechanism", "Mechanism changes")):
        values = {"done": done, "learned": learned, "next": next_, "mechanism": mechanism}[key]
        if values:
            entry.append(f"**{label}**")
            entry += [f"- {v}" for v in values]
            entry.append("")
    facts = [f"head {snap['head'][:10]}"]
    if snap["commits_since_handoff"]:
        facts.append(f"{len(snap['commits_since_handoff'])} commit(s) since the last handoff")
    if snap.get("last_test"):
        t = snap["last_test"]
        facts.append(f"tests {'PASS' if t['passed'] else 'FAIL'} (`{t['command']}`)")
    if snap["uncommitted"]:
        facts.append(f"{len(snap['uncommitted'])} uncommitted file(s)")
    entry.append("_" + " · ".join(facts) + "_")
    with open(log, "a") as f:
        f.write("\n".join(entry) + "\n")

    # 2. state snapshot (regenerated)
    snap["last_handoff"] = {"at": now(), "head": snap["head"], "title": title}
    write_checkpoint(project, snap)
    write_state(project, narrative, snap)

    # 3. optional commit
    profile = project.config.get("agent_profile", "conservative")
    should_commit = commit if commit is not None else profile == "team-maintainer"
    committed = None
    if should_commit and vcs.is_repo(project.root):
        _git(project.root, "add", "--", ".speky")
        msg = f"Handoff: {title}"
        r = subprocess.run(["git", "commit", "-m", msg], cwd=project.root, capture_output=True, text=True)
        committed = msg if r.returncode == 0 else None
        if committed:  # the record's own commit is not "work since the handoff"
            snap["head"] = _git(project.root, "rev-parse", "HEAD").strip() or snap.get("head")
            snap["last_handoff"]["head"] = snap["head"]
            write_checkpoint(project, snap)
    return {"title": title, "log": str(log.relative_to(project.root)),
            "state": str((project.dir / STATE_NAME).relative_to(project.root)),
            "tests": snap.get("last_test"), "uncommitted": snap["uncommitted"], "committed": committed,
            "warnings": (["work is only in the working tree — commit it"] if snap["uncommitted"] else [])}


# ---------------------------------------------------------------------------- state.md
def read_state(project: Project) -> dict:
    path = project.dir / STATE_NAME
    if not path.exists():
        return {}
    text = path.read_text()
    out = {}

    def section(name):
        m = re.search(rf"^## {re.escape(name)}\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
        return m.group(1).strip() if m else ""

    out["summary"] = section("Where things stand")
    out["next"] = [re.sub(r"^\d+\.\s+", "", l).strip() for l in section("Next actions").splitlines() if l.strip()]
    out["watch"] = [l[2:].strip() for l in section("Watch out for").splitlines() if l.startswith("- ")]
    upd = re.search(r"\*\*Updated:\*\*\s*([^·\n]+)", text)
    out["updated"] = upd.group(1).strip() if upd else ""
    return out


def write_state(project: Project, narrative: dict, snap: dict) -> None:
    from .owner import OwnerActions
    from . import phases as phases_mod
    active = phases_mod.current(project)
    t = snap.get("last_test")
    tests = f"{'PASS' if t['passed'] else 'FAIL'} (`{t['command']}`, {t['at'][:16]})" if t else "not run"
    lines = ["# STATE", "",
             "_Generated by `speky handoff` — change it through a handoff, not by hand. "
             "If git and this file disagree, trust git._", "",
             f"**Updated:** {snap['at'][:16]} · **Phase:** "
             + (f"{active.id} {active.data.get('name', '')} [{active.status}]" if active else "none")
             + f" · **Tests:** {tests}", ""]
    lines += ["## Where things stand", narrative.get("summary") or "_(no summary given)_", ""]
    lines += ["## Next actions"] + [f"{i}. {n}" for i, n in enumerate(narrative.get("next") or [], 1)]
    if not narrative.get("next"):
        lines.append("_(none given — run `speky next`)_")
    lines.append("")
    work = [f"- {i['id']} {i['title']} ({i['status']})" for i in snap["in_progress_items"]]
    work += [f"- {d['id']} {d['text']} (task, doing)" for d in snap["doing_tasks"]]
    if work:
        lines += ["## In progress"] + work + [""]
    owner = OwnerActions(project).open_items()
    if owner:
        lines += ["## Waiting on the owner"] + [f"- {o['id']} {o['text'][:110]}" for o in owner[:8]] + [""]
    if narrative.get("watch"):
        lines += ["## Watch out for"] + [f"- {w}" for w in narrative["watch"]] + [""]
    (project.dir / STATE_NAME).write_text("\n".join(lines).rstrip() + "\n")


# ---------------------------------------------------------------------------- session start facts
def last_handoff_from_log(project: Project) -> dict:
    """The last handoff as the committed record shows it (`log.md` + its `Handoff:` commit), for a clone or
    another machine that has no `checkpoint.json` (that file is per machine and not committed)."""
    path = project.dir / LOG_NAME
    if not path.exists():
        return {}
    heads = re.findall(r"^## (\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?) · (.+?)\s*$", path.read_text(), re.MULTILINE)
    if not heads:
        return {}
    stamp, title = heads[-1]
    at = stamp.replace(" ", "T") + (":00" if " " in stamp else "T00:00:00")
    sha = _git(project.root, "log", "-1", "--format=%H", "--fixed-strings", f"--grep=Handoff: {title}").strip()
    if not sha:  # no Handoff: commit (conservative profile): the last commit that touched the log
        sha = _git(project.root, "log", "-1", "--format=%H", "--", str(path.relative_to(project.root))).strip()
    return {"at": at, "title": title, "head": sha or None, "source": "log.md"}



def session_facts(project: Project) -> dict:
    """What `speky prime` shows at session start: is the recorded state still the state on disk?"""
    cp = load_checkpoint(project)
    last = cp.get("last_handoff") or last_handoff_from_log(project)
    head = vcs.head(project.root)
    since = last.get("head")
    commits = []
    if since and since != head and since != vcs.NO_VCS:
        commits = [l for l in _git(project.root, "log", "--oneline", f"{since}..HEAD").splitlines() if l]
    dirty = [l[3:] for l in _git(project.root, "status", "--porcelain=v1").splitlines()
             if l[3:] and not l[3:].startswith(".speky/")]
    return {"last_handoff": last, "commits_since": commits, "uncommitted": dirty,
            "last_test": cp.get("last_test"), "checkpoint_at": cp.get("at"), "auto_checkpoint": cp.get("auto"),
            "in_flight": cp.get("in_flight") if cp.get("auto") else None,
            "state_exists": (project.dir / STATE_NAME).exists()}


# ---------------------------------------------------------------------------- nothing lives only in the chat
# Each kind of record and the files that hold it (relative to .speky/, or to the repository root for "root:")
RECORD_GROUPS = {
    "owner": ("owner.md",),
    "decisions": ("decisions.md", "adr/*.md"),
    "knowledge": ("knowledge/*.md", "glossary.md", "root:AGENTS.md", "root:CLAUDE.md"),
    "plan": ("backlog.json", "phases/*/manifest.yaml", "phases/roadmap.yaml", "specs/*/*.md", "stories/*/*.md",
             "specs/*/findings.json", "stories/*/findings.json", "epics/*/*.md"),
    "state": ("state.md", "log.md"),
}

# what the agent's reply can contain, and the records that must change for it
REPLY_SIGNALS = {
    "handoff": (re.compile(
        r"\b(only you|you(?:'ll| will)? need to|you should|your call|your decision|for you to|needs? your|"
        r"waiting on you|you'd have to|if you agree|do you want me to|shall i|should i|want me to|"
        r"i(?:'d| would)? recommend|i suggest|my recommendation|i'd (?:defer|drop|move|split|stop|start)|"
        r"next steps? for you|things only you|owner(?:-only)? actions?)\b", re.I), ("owner", "decisions", "plan")),
    "assumption": (re.compile(
        r"\b(i assumed|i'm assuming|i am assuming|assuming that|on the assumption|i'll .{0,40}\bnext\b|"
        r"next,? i'll|in the next session|later i'll|i will .{0,30}\bnext\b)", re.I), ("decisions", "plan", "state")),
}
# what the owner's message can contain, and the records that must change for it
DIRECTIVE_RE = re.compile(
    r"\b(always|never|from now on|going forward|in (?:the )?future|i prefer|i'd prefer|i want you to|"
    r"i don'?t want|don'?t ever|do not ever|make sure (?:to|that|you)|remember (?:that|to)|stop doing|"
    r"please don'?t|please do not|must always|must never|by default)\b", re.I)
FEEDBACK_RE = re.compile(
    r"\b(confusing|not intuitive|unintuitive|doesn'?t work|does not work|not working|broken|buggy|bug|"
    r"is wrong|looks wrong|i don'?t like|ugly|hard to (?:find|read|use|understand)|can'?t find|unclear|"
    r"not clear|too (?:small|big|slow|cramped|busy)|should (?:be|show|not))\b", re.I)
ANSWER_RE = re.compile(r"\b(yes|no|yep|nope|ok(?:ay)?|sure|agreed?|go ahead|approved?|approve|reject(?:ed)?|do it|"
                       r"let'?s|option\s*\w+|go with|choose|pick|defer(?:red)?|skip|both|neither|sounds good|"
                       r"correct|don'?t)\b", re.I)
STOPWORDS = {"decide", "recommended", "because", "should", "would", "about", "there", "their", "which", "until",
             "after", "before", "with", "from", "that", "this", "what", "when", "into", "then", "than", "them"}


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3 and w not in STOPWORDS}
LINK_RE = re.compile(r"https?://\S+")
ACCOUNT_RE = re.compile(r"\b(account|logged in|signed in|api key|credentials?|workspace|organi[sz]ation|project id|"
                        r"dashboard|bucket|cluster)\b", re.I)

FIXES = {
    "handoff": "actions only the owner can take → `speky owner add \"<what>\" --section \"<Do soon|Decide or "
               "provide|People>\"`; recommendations that need their decision → `speky owner add \"Decide: <question> "
               "(recommended: <answer>, because …)\" --section \"Decide or provide\"`; plan changes → `speky task …`",
    "assumption": "assumptions → `speky decide \"…\" --type assumption`; what you promised to do next → `speky task "
                  "add` (or the Next list of a handoff)",
    "instruction": "the owner gave a standing instruction → `speky remember \"<rule>\" --topic owner --always` (or a "
                   "rule in AGENTS.md when it governs how work is done)",
    "feedback": "the owner gave feedback → one task or finding per point (`speky task add \"…\" [--labels ui] [--refs "
                "screen:<id>]` or `speky finding add <item> …`), and a note on the owner item it answers",
    "answer": "the owner answered an open decision → tick it, `speky owner done <id> --note \"<their answer>\"`, "
              "and `speky decide \"…\"`",
    "link": "the owner shared a link or an account → `speky remember \"<what it is, what it is for>\" --topic "
            "environment` (never store a secret; record where it is kept)",
}
NEEDS = {"instruction": ("knowledge",), "feedback": ("plan", "owner"), "answer": ("owner",), "link": ("knowledge",)}


def _group_fingerprints(project: Project) -> Dict[str, Dict[str, float]]:
    from . import layout
    out: Dict[str, Dict[str, float]] = {}
    adr_extra = [p for p in layout.paths(project, "adr_dir") if project.dir not in p.parents]
    for group, patterns in RECORD_GROUPS.items():
        files = {}
        for pattern in patterns:
            if pattern.startswith("root:"):
                matches = [project.root / pattern[5:]]
            else:
                matches = list(project.dir.glob(pattern))
                if pattern == "adr/*.md":
                    matches += [f for d in adr_extra for f in d.glob("*.md")]
            for f in matches:
                if f.is_file():
                    files[str(f)] = f.stat().st_mtime
        out[group] = files
    return out


def owner_signals(project: Project, prompt: str) -> Dict[str, list]:
    """What in the owner's message must end up in a record."""
    from .owner import OwnerActions
    signals: Dict[str, list] = {}
    statements = [s for s in re.split(r"(?<=[.!?\n])\s+", prompt) if s.strip() and not s.strip().endswith("?")]
    directives = sorted({m.group(0).lower() for s in statements for m in DIRECTIVE_RE.finditer(s)})
    if directives:
        signals["instruction"] = directives
    feedback = sorted({m.group(0).lower() for m in FEEDBACK_RE.finditer(prompt)})
    if feedback:
        signals["feedback"] = feedback
    decide = [o for o in OwnerActions(project).open_items() if "decide" in o["text"].lower()[:30]] \
        if (project.dir / "owner.md").exists() else []
    if decide and ANSWER_RE.search(prompt):
        said = _words(prompt)
        named = [o["id"] for o in decide if re.search(rf"\b{o['id']}\b", prompt)]
        # the open decisions this message talks about: named by ID, or sharing words with it (the only one open)
        about = named or [o["id"] for o in decide if len(said & _words(o["text"])) >= 2] or \
            ([decide[0]["id"]] if len(decide) == 1 else [])
        if about:
            signals["answer"] = about[:6]
    links = LINK_RE.findall(prompt) + [m.group(0).lower() for m in ACCOUNT_RE.finditer(prompt)]
    if links:
        signals["link"] = sorted(set(links))[:6]
    return signals


def turn_start(project: Project, prompt: str = "") -> None:
    """UserPromptSubmit hook: remember the records' state and what the owner's message asks to be kept."""
    if not project.dir.is_dir():
        return
    ensure_local_ignored(project)
    write_json(project.dir / TURN_NAME, {"at": now(), "groups": _group_fingerprints(project),
                                          "signals": owner_signals(project, prompt or ""),
                                          "prompt": (prompt or "")[:300]})


def stop_check(project: Project, payload: dict) -> Optional[dict]:
    """Stop hook: block once when something from this turn would live only in the chat.

    Owner side: standing instructions, feedback, answers to open decisions, links and accounts.
    Agent side: hand-offs to the owner (actions, decisions, recommendations), assumptions, promises.
    Each needs a specific kind of record to change this turn; unrelated edits don't count."""
    if not project.dir.is_dir() or payload.get("stop_hook_active") or \
            project.config.get("record_check") is False:
        return None
    path = project.dir / TURN_NAME
    if not path.exists():
        return None
    turn = json.loads(path.read_text())
    before = turn.get("groups")
    if before is None:
        return None
    now_ = _group_fingerprints(project)
    changed = {g for g in RECORD_GROUPS if now_.get(g) != before.get(g)}
    missing = []
    message = payload.get("last_assistant_message") or ""
    for kind, (rx, needs) in REPLY_SIGNALS.items():
        hits = sorted({m.group(0).lower() for m in rx.finditer(message)})
        if hits and not changed & set(needs):
            missing.append((kind, hits))
    for kind, hits in (turn.get("signals") or {}).items():
        if not changed & set(NEEDS.get(kind, ())):
            missing.append((kind, hits))
    if not missing:
        return None
    lines = [f"- {FIXES[k]} (found: {', '.join(str(h) for h in hits[:4])})" for k, hits in missing]
    return {"decision": "block", "reason": (
        "SPEKY: something from this turn exists only in the chat. Record it before you stop, so the next session "
        "and the owner can see it:\n" + "\n".join(lines) +
        "\nIf a point needs no record (for example it was a question, not an instruction), say so in one line.")}


# ---------------------------------------------------------------------------- in flight at compaction
def in_flight_from_transcript(transcript_path: str) -> dict:
    """The owner's latest request and the agent's step list, read from a Claude Code transcript (JSONL)."""
    request, todos, created = "", [], {}
    try:
        lines = Path(transcript_path).read_text(errors="ignore").splitlines()
    except OSError:
        return {}
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        msg = d.get("message") or {}
        content = msg.get("content")
        if d.get("type") == "user" and msg.get("role", "user") == "user":
            if isinstance(content, str) and content.strip() and not content.startswith("<"):
                request = content.strip()
            elif isinstance(content, list):
                texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                text = "\n".join(t for t in texts if t.strip() and not t.startswith("<"))
                if text.strip():
                    request = text.strip()
        if isinstance(content, list):
            for c in content:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                name, inp = c.get("name"), c.get("input") or {}
                if name == "TodoWrite":
                    todos = [{"step": t.get("content", ""), "status": t.get("status", "pending")}
                             for t in inp.get("todos") or []]
                    created = {}
                elif name == "TaskCreate":
                    tid = str(len(created) + 1)
                    created[tid] = {"step": inp.get("subject", ""), "status": "pending"}
                    todos = list(created.values())
                elif name == "TaskUpdate" and str(inp.get("taskId")) in created:
                    t = created[str(inp.get("taskId"))]
                    t["status"] = inp.get("status", t["status"])
                    t["step"] = inp.get("subject", t["step"])
                    todos = list(created.values())
    return {"request": request[:600], "steps": todos[:30]} if request or todos else {}
