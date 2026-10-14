"""Keep the working records small; move finished history to a readable, dated archive.

What a session reads should be what is still useful. Finished history moves to `.speky/archive/`, never
deleted: each entry keeps its original IDs, dates and wording, gets the date and rule it was archived
under, and stays searchable (`speky history`). Git history holds every earlier version as well.

    .speky/archive/index.md                  what is archived, per file: entries, date range (generated)
    .speky/archive/log/<YYYY-MM>.md           session-log entries beyond the newest `log_keep`
    .speky/archive/tasks/<phase>.md           finished tasks (readable) + archive/tasks.json (exact records)
    .speky/archive/owner/<YYYY-MM>.md         owner actions ticked at least `owner_days` ago, with notes
    .speky/archive/decisions/<YYYY>.md        oldest decisions beyond the newest `decisions_keep`
    .speky/archive/knowledge/<topic>.md       knowledge entries retired on purpose, with the reason
    .speky/archive/state.json                 bookkeeping (when owner items were first seen ticked)

Rules (`tidy:` in speky.yaml): log_keep 5 · tasks of a completed phase, or done/deferred `task_days` (30) ago
without a phase, and only when no open sub-task depends on them · owner_days 14 · decisions_keep 100.
Never archived: changes (specs/stories with their findings and evidence), living specs, phases, ADRs,
design files, open work, anything the owner has not ticked.
"""
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

from .items import Project, now, write_json

DEFAULTS = {"log_keep": 5, "task_days": 30, "owner_days": 14, "decisions_keep": 100, "auto": True}
LOG_HEAD_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})(?: \d{2}:\d{2})? · ", re.MULTILINE)
DECISION_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) \[\w+\] D(\d+):", re.MULTILINE)


def archive_dir(project: Project) -> Path:
    return project.dir / "archive"


def rules(project: Project) -> dict:
    return {**DEFAULTS, **(project.config.get("tidy") or {})}


def _append(path: Path, header: str, block: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text() if path.exists() else header
    path.write_text(text.rstrip("\n") + "\n\n" + block.strip("\n") + "\n")


def _state(project: Project) -> dict:
    path = archive_dir(project) / "state.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _save_state(project: Project, data: dict) -> None:
    archive_dir(project).mkdir(parents=True, exist_ok=True)
    write_json(archive_dir(project) / "state.json", data)


# ---------------------------------------------------------------------------- what would move
def _log_moves(project: Project, r: dict) -> List[dict]:
    path = project.dir / "log.md"
    if not path.exists():
        return []
    text = path.read_text()
    heads = list(LOG_HEAD_RE.finditer(text))
    old = heads[:-r["log_keep"]] if len(heads) > r["log_keep"] else []
    moves = []
    for i, m in enumerate(old):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        moves.append({"kind": "log", "date": m.group(1), "text": text[m.start():end].strip("\n"),
                      "start": m.start(), "end": end})
    return moves


def _task_moves(project: Project, r: dict) -> List[dict]:
    from . import phases as phases_mod
    from .tasks import Tasks
    path = project.dir / "backlog.json"
    if not path.exists():
        return []
    done_phases = {p.id for p in phases_mod.all_phases(project) if p.status == "done"}
    cutoff = (datetime.now() - timedelta(days=int(r["task_days"]))).isoformat()
    tasks = [t for t in Tasks(project).items if t.get("kind") == "task"]
    finished = {t["id"] for t in tasks if t.get("status") in ("done", "deferred")}

    def ready(t):
        if t["id"] not in finished:
            return False
        if t.get("phase") in done_phases:
            return True
        stamp = t.get("done_at") or t.get("deferred_at") or ""
        return not t.get("phase") and bool(stamp) and stamp < cutoff

    candidates = {t["id"] for t in tasks if ready(t)}
    # keep a task while any of its sub-tasks stays active
    changed = True
    while changed:
        changed = False
        for t in tasks:
            if t["id"] in candidates and any(c.get("parent") == t["id"] and c["id"] not in candidates for c in tasks):
                candidates.discard(t["id"])
                changed = True
    return [{"kind": "tasks", "task": t, "group": t.get("phase") or "no-phase"} for t in tasks if t["id"] in candidates]


def _owner_moves(project: Project, r: dict) -> (List[dict], dict):
    from .owner import OwnerActions
    if not (project.dir / "owner.md").exists():
        return [], {}
    st = _state(project)
    seen = dict(st.get("owner_ticked_seen") or {})
    oa = OwnerActions(project)
    items = oa.items()
    today = date.today().isoformat()
    cutoff = (date.today() - timedelta(days=int(r["owner_days"]))).isoformat()
    moves = []
    for it in items:
        if not it["done"]:
            seen.pop(it["id"], None)
            continue
        first = seen.setdefault(it["id"], today)
        children_open = any(c["parent"] == it["id"] and not c["done"] for c in items)
        if first <= cutoff and not children_open and not (it["parent"] and
                                                          any(p["id"] == it["parent"] and not p["done"] for p in items)):
            moves.append({"kind": "owner", "item": it, "section": it["section"], "first_seen_ticked": first})
    return moves, seen


def _decision_moves(project: Project, r: dict) -> List[dict]:
    path = project.dir / "decisions.md"
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    entries = [i for i, l in enumerate(lines) if DECISION_RE.match(l)]
    keep = int(r["decisions_keep"])
    old = entries[:-keep] if len(entries) > keep else []
    return [{"kind": "decisions", "line": i, "text": lines[i], "date": DECISION_RE.match(lines[i]).group(1)}
            for i in old]


def plan(project: Project) -> dict:
    r = rules(project)
    owner, _ = _owner_moves(project, r)
    moves = _log_moves(project, r) + _task_moves(project, r) + owner + _decision_moves(project, r)
    summary: Dict[str, int] = {}
    for m in moves:
        summary[m["kind"]] = summary.get(m["kind"], 0) + 1
    return {"rules": r, "moves": summary,
            "detail": {"log": [m["date"] for m in moves if m["kind"] == "log"],
                       "tasks": [m["task"]["id"] for m in moves if m["kind"] == "tasks"],
                       "owner": [m["item"]["id"] for m in moves if m["kind"] == "owner"],
                       "decisions": [f"D{DECISION_RE.match(m['text']).group(2)}" for m in moves
                                     if m["kind"] == "decisions"]}}


# ---------------------------------------------------------------------------- apply
def apply(project: Project, reason: str = "speky tidy") -> dict:
    from .owner import OwnerActions
    from .tasks import Tasks
    r = rules(project)
    stamp = now()
    tag = f"archived {stamp[:16].replace('T', ' ')} ({reason})"
    done: Dict[str, list] = {}
    a = archive_dir(project)

    # session log: verbatim entries, by month
    logs = _log_moves(project, r)
    if logs:
        path = project.dir / "log.md"
        text = path.read_text()
        for m in logs:
            _append(a / "log" / f"{m['date'][:7]}.md", f"# Session log {m['date'][:7]} (archived)\n",
                    m["text"] + f"\n\n<!-- {tag} -->")
        for m in sorted(logs, key=lambda m: -m["start"]):
            text = text[:m["start"]] + text[m["end"]:]
        if "Older entries:" not in text:
            text = re.sub(r"\n\n", "\n\nOlder entries: `.speky/archive/log/` (`speky history <words>`).\n\n", text, count=1)
        path.write_text(re.sub(r"\n{3,}", "\n\n", text))
        done["log"] = [m["date"] for m in logs]

    # tasks: readable copy + exact records
    moves = _task_moves(project, r)
    if moves:
        tasks = Tasks(project)
        ids = {m["task"]["id"] for m in moves}
        records_path = a / "tasks.json"
        records = json.loads(records_path.read_text()) if records_path.exists() else []
        for m in moves:
            t = m["task"]
            mark = "[x]" if t["status"] == "done" else "[-]"
            when = ", ".join(f"{k.replace('_at', '')} {t[k][:10]}" for k in ("created_at", "doing_at", "done_at",
                                                                           "deferred_at") if t.get(k))
            body = f"- {mark} {t['id']} {t['name']}" + (f" (parent {t['parent']})" if t.get("parent") else "") + \
                f"\n  - {when}" + "".join(f"\n  - {n}" for n in t.get("notes") or []) + \
                (f"\n  - refs: {', '.join(t['refs'])}" if t.get("refs") else "") + f"\n  - {tag}"
            _append(a / "tasks" / f"{m['group']}.md", f"# Archived tasks: {m['group']}\n", body)
            records.append({**t, "archived_at": stamp, "archived_by": reason})
        write_json(records_path, records)
        tasks.items = [t for t in tasks.items if t.get("id") not in ids]
        tasks.save()
        done["tasks"] = sorted(ids, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)

    # owner actions ticked long enough ago: the item with its notes, verbatim
    owner, seen = _owner_moves(project, r)
    if owner:
        oa = OwnerActions(project)
        drop = set()
        for m in owner:
            it = m["item"]
            block = "\n".join(oa.lines[it["line"]:it["end"] + 1])
            _append(a / "owner" / f"{stamp[:7]}.md", f"# Owner actions archived {stamp[:7]}\n",
                    f"## {m['section'] or '(no section)'}\n\n{block}\n  - ticked by {m['first_seen_ticked']} · {tag}")
            drop.update(range(it["line"], it["end"] + 1))
            seen.pop(it["id"], None)
        oa.lines = [l for i, l in enumerate(oa.lines) if i not in drop]
        if not any("archive/owner" in l for l in oa.lines[:8]):
            oa.lines.insert(min(3, len(oa.lines)), "Done items move to `.speky/archive/owner/` after "
                            f"{r['owner_days']} days.")
        oa.save()
        done["owner"] = [m["item"]["id"] for m in owner]
    st = _state(project)
    st["owner_ticked_seen"] = seen
    _save_state(project, st)

    # decisions beyond the newest `decisions_keep`, by year
    decisions = _decision_moves(project, r)
    if decisions:
        path = project.dir / "decisions.md"
        lines = path.read_text().splitlines()
        for m in decisions:
            _append(a / "decisions" / f"{m['date'][:4]}.md", f"# Decisions {m['date'][:4]} (archived; IDs unchanged)\n",
                    m["text"])
        drop = {m["line"] for m in decisions}
        lines = [l for i, l in enumerate(lines) if i not in drop]
        if not any("archive/decisions" in l for l in lines[:6]):
            lines.insert(min(3, len(lines)), "Older decisions: `.speky/archive/decisions/` (IDs unchanged).")
        path.write_text("\n".join(lines).rstrip() + "\n")
        done["decisions"] = [f"D{DECISION_RE.match(m['text']).group(2)}" for m in decisions]

    if done:
        render_index(project)
    return {"archived": done, "at": stamp}


def retire_knowledge(project: Project, topic: str, entry: str, reason: str) -> dict:
    """Move one knowledge entry (matched by the start of its text) to the archive, with the reason."""
    from . import knowledge
    from .errors import SpekyError
    from .items import slugify
    path = knowledge.knowledge_dir(project) / f"{slugify(topic)}.md"
    if not path.exists():
        raise SpekyError("topic_not_found", f"No knowledge topic '{topic}'.", "Run `speky knowledge list`.")
    lines = path.read_text().splitlines()
    want = " ".join(entry.split()).lower()
    starts = [i for i, l in enumerate(lines) if l.startswith("- ") and
              want in " ".join(l[2:].split()).lower()[:max(len(want) + 20, 80)]]
    if len(starts) != 1:
        raise SpekyError("entry_not_unique", f"{len(starts)} entries in {topic} match '{entry}'.",
                         "Give more of the entry's opening words.")
    i = starts[0]
    j = i + 1
    while j < len(lines) and lines[j].startswith((" ", "\t")) and lines[j].strip():
        j += 1
    block = "\n".join(lines[i:j])
    _append(archive_dir(project) / "knowledge" / f"{slugify(topic)}.md", f"# Retired knowledge: {topic}\n",
            f"{block}\n  - retired {now()[:10]}: {reason}")
    path.write_text("\n".join(lines[:i] + lines[j:]).rstrip() + "\n")
    render_index(project)
    return {"topic": topic, "retired": block[:200], "reason": reason}


def render_index(project: Project) -> None:
    a = archive_dir(project)
    rows = []
    for f in sorted(a.rglob("*.md")):
        if f.name == "index.md":
            continue
        text = f.read_text()
        dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        entries = len(re.findall(r"^(?:## \d{4}|- )", text, re.MULTILINE))
        rows.append(f"| `{f.relative_to(a)}` | {entries} | {min(dates) if dates else ''} | {max(dates) if dates else ''} |")
    a.mkdir(parents=True, exist_ok=True)
    (a / "index.md").write_text(
        "# Archive\n\nFinished history moved out of the working records by `speky tidy` (rules: "
        "`speky tidy --json`). Nothing here is deleted or edited: entries keep their IDs, dates and wording, "
        "plus when and why they were archived. Search everything with `speky history <words>`; earlier "
        "versions of every file are in git.\n\n| File | Entries | First date | Last date |\n|---|---|---|---|\n"
        + "\n".join(rows) + "\n")


# ---------------------------------------------------------------------------- history
def history(project: Project, query: str, kind: str = "all", since: str = None, git: bool = False,
            limit: int = 60) -> dict:
    """Search the working records and the archive (and optionally commit messages) for disputes,
    revisions and backtracking. Each hit has its file, line, the nearest date and the text."""
    rx = re.compile(re.escape(query), re.IGNORECASE)
    groups = {"log": ["log.md", "state.md", "archive/log/*.md"],
              "tasks": ["tasks.md", "archive/tasks/*.md"],
              "owner": ["owner.md", "archive/owner/*.md"],
              "decisions": ["decisions.md", "archive/decisions/*.md"],
              "knowledge": ["knowledge/*.md", "archive/knowledge/*.md", "glossary.md"],
              "changes": ["specs/*/*.md", "stories/*/*.md", "capabilities/*/spec.md"]}
    patterns = [p for k, ps in groups.items() if kind in ("all", k) for p in ps]
    hits = []
    for pattern in patterns:
        for f in sorted(project.dir.glob(pattern)):
            current_date = ""
            for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                d = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", line)
                if d:
                    current_date = d.group(1)
                if rx.search(line):
                    if since and current_date and current_date < since:
                        continue
                    hits.append({"file": str(f.relative_to(project.root)), "line": n, "date": current_date,
                                 "archived": "/archive/" in str(f), "text": line.strip()[:240]})
    if git:
        import subprocess
        out = subprocess.run(["git", "log", "--format=%h %ad %s", "--date=short", "-i", f"--grep={query}"],
                             cwd=project.root, capture_output=True, text=True).stdout.splitlines()
        hits += [{"file": "git log", "line": None, "date": l.split()[1] if len(l.split()) > 1 else "",
                  "archived": False, "text": l} for l in out]
    hits.sort(key=lambda h: h["date"] or "", reverse=True)
    return {"query": query, "total": len(hits), "hits": hits[:limit]}


# ---------------------------------------------------------------------------- watermark
def watermark(project: Project, prime_chars: int = None) -> List[str]:
    """Signs that the working records or the session-start load have grown past their budget."""
    from .tasks import Tasks
    r = rules(project)
    budget = int((project.config.get("context") or {}).get("prime_budget_tokens", 2500))
    notes = []
    if prime_chars and prime_chars / 4 > budget:
        notes.append(f"session start is ~{prime_chars // 4} tokens (budget {budget}): shorten always-loaded "
                     "knowledge (`speky knowledge retire`, or make a topic read-when)")
    p = plan(project)["moves"]
    if p:
        notes.append("finished history can move to the archive: " +
                     ", ".join(f"{n} {k}" for k, n in p.items()) + " (`speky tidy --apply`)")
    finished = [t for t in Tasks(project).list() if t["status"] in ("done", "deferred")] \
        if (project.dir / "backlog.json").exists() else []
    if len(finished) > 40 and not p.get("tasks"):
        notes.append(f"{len(finished)} finished tasks stay in the working list because their phases are open")
    return notes
