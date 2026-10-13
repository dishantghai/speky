"""Decision log, remembered facts, ADRs and glossary (CONTRACTS.md §7). All append-only."""
import re
from datetime import date
from pathlib import Path

from .errors import SpekyError
from .items import Project, slugify

DECISION_TYPES = ("decision", "constraint", "assumption", "question", "direction", "event")


def _append(path: Path, header: str, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(header)
    with open(path, "a") as f:
        f.write(line.rstrip("\n") + "\n")


def decide(project: Project, text: str, type_: str = "decision", ref: str = None) -> dict:
    if type_ not in DECISION_TYPES:
        raise SpekyError("bad_decision_type", f"Type must be one of {', '.join(DECISION_TYPES)}.")
    if ref:
        project.find(ref)
    path = project.dir / "decisions.md"
    existing = path.read_text() if path.exists() else ""
    number = len(re.findall(r"^- \S+ \[\w+\] D\d+:", existing, re.MULTILINE)) + 1
    entry = f"- {date.today().isoformat()} [{type_}] D{number}: {' '.join(text.split())}"
    if ref:
        entry += f" (ref: {ref})"
    _append(path, "# Decision log\n\nAppend-only. A later entry supersedes an earlier one on the same "
                  "point; never edit or reorder lines.\n\n", entry)
    return {"id": f"D{number}", "type": type_, "text": text, "ref": ref, "file": str(path)}


def decisions(project: Project, ref: str = None) -> list:
    path = project.dir / "decisions.md"
    if not path.exists():
        return []
    lines = [l[2:] for l in path.read_text().splitlines() if re.match(r"^- \S+ \[\w+\] D\d+:", l)]
    return [l for l in lines if not ref or f"(ref: {ref})" in l]


def remember(project: Project, fact: str) -> dict:
    path = project.dir / "memory.md"
    _append(path, "# Project memory\n\nFacts every agent session should know (injected by "
                  "`speky prime`). Keep each to one line.\n\n", f"- {' '.join(fact.split())}")
    return {"fact": fact, "file": str(path)}


def memories(project: Project) -> list:
    path = project.dir / "memory.md"
    if not path.exists():
        return []
    return [l[2:] for l in path.read_text().splitlines() if l.startswith("- ")]


def adr_new(project: Project, title: str, context: str = "", decision: str = "",
            supersedes: str = None) -> dict:
    folder = project.dir / "adr"
    folder.mkdir(parents=True, exist_ok=True)
    numbers = [int(p.name[:4]) for p in folder.glob("[0-9][0-9][0-9][0-9]-*.md")]
    number = max(numbers, default=0) + 1
    path = folder / f"{number:04d}-{slugify(title)}.md"
    body = (f"# ADR {number:04d}: {title}\n\nStatus: Accepted\nDate: {date.today().isoformat()}\n"
            + (f"Supersedes: {supersedes}\n" if supersedes else "")
            + f"\n## Context\n{context or '<!-- What forces this decision. -->'}\n"
            f"\n## Decision\n{decision or '<!-- The rule: what it binds, what divergence it prevents. -->'}\n"
            "\n## Consequences\n<!-- What gets easier, what gets harder. -->\n")
    path.write_text(body)
    if supersedes:
        old = next(folder.glob(f"{int(supersedes):04d}-*.md"), None)
        if old:
            old.write_text(old.read_text().replace("Status: Accepted",
                                                   f"Status: Superseded by {number:04d}", 1))
    return {"id": f"{number:04d}", "file": str(path)}


def adr_list(project: Project) -> list:
    folder = project.dir / "adr"
    result = []
    for p in sorted(folder.glob("[0-9][0-9][0-9][0-9]-*.md")) if folder.exists() else []:
        text = p.read_text()
        status = re.search(r"^Status:\s*(.+)$", text, re.MULTILINE)
        title = text.splitlines()[0].split(":", 1)[-1].strip() if text else p.stem
        result.append({"id": p.name[:4], "title": title,
                       "status": status.group(1).strip() if status else "unknown", "file": str(p)})
    return result


def term(project: Project, word: str, definition: str) -> dict:
    path = project.dir / "glossary.md"
    if path.exists() and re.search(rf"^- \*\*{re.escape(word)}\*\*", path.read_text(), re.MULTILINE | re.IGNORECASE):
        raise SpekyError("term_exists", f"'{word}' is already in the glossary.",
                         f"Edit {path} to change its definition.")
    _append(path, "# Glossary\n\nCanonical domain terms. Code, specs and UI use these words.\n\n",
            f"- **{word}** — {' '.join(definition.split())}")
    return {"term": word, "file": str(path)}
