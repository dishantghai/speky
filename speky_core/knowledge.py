"""Project knowledge by topic: `.speky/knowledge/<topic>.md`.

What is true, learned or intended but not obvious from the code: owner preferences, design rationale,
measurements, gotchas, environment facts. Newest first within a topic. A topic can be loaded into every
session (`<!-- speky: always -->`) or listed in `speky prime` with a trigger telling the agent when to
read it (`<!-- speky: read when touching the kernel -->`). Mature topics are promoted to ADRs.
"""
import re
from datetime import date
from typing import List, Optional

from .errors import SpekyError
from .items import Project, slugify

META_RE = re.compile(r"<!--\s*speky:\s*(.+?)\s*-->")
ENTRY_RE = re.compile(r"^- ")


def knowledge_dir(project: Project):
    return project.dir / "knowledge"


def _title(slug: str) -> str:
    return slug.replace("-", " ").capitalize()


def topics(project: Project) -> List[dict]:
    folder = knowledge_dir(project)
    result = []
    for path in sorted(folder.glob("*.md")) if folder.exists() else []:
        text = path.read_text()
        metas = META_RE.findall(text)
        always = any(m.strip() == "always" for m in metas)
        trigger = next((m.split("read when", 1)[1].strip() for m in metas if m.startswith("read when")), "")
        heading = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), _title(path.stem))
        entries = entries_of(text)
        result.append({"topic": path.stem, "title": heading, "always": always, "read_when": trigger,
                       "entries": len(entries), "newest": entries[0] if entries else "",
                       "file": str(path.relative_to(project.root))})
    return result


def entries_of(text: str) -> List[str]:
    """Top-level bullets with their continuation lines."""
    entries, current = [], None
    for line in text.splitlines():
        if ENTRY_RE.match(line):
            current = [line[2:].strip()]
            entries.append(current)
        elif current is not None and line.startswith((" ", "\t")) and line.strip():
            current.append(line.strip())
        elif line.strip():
            current = None
    return [" ".join(e) for e in entries]


def remember(project: Project, fact: str, topic: str = "general", always: bool = None,
             read_when: str = None) -> dict:
    slug = slugify(topic)
    path = knowledge_dir(project) / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        metas = []
        if always or (always is None and slug in ("owner", "general")):
            metas.append("<!-- speky: always -->")
        if read_when:
            metas.append(f"<!-- speky: read when {read_when} -->")
        path.write_text(f"# {_title(slug)}\n\n" + ("\n".join(metas) + "\n\n" if metas else ""))
    lines = path.read_text().splitlines()
    entry = f"- ({date.today().isoformat()}) {' '.join(fact.split())}"
    # newest first: insert before the first existing entry, after the header and meta lines
    at = next((i for i, l in enumerate(lines) if ENTRY_RE.match(l)), len(lines))
    lines[at:at] = [entry]
    path.write_text("\n".join(lines).rstrip("\n") + "\n")
    return {"topic": slug, "fact": fact, "file": str(path.relative_to(project.root))}


def always_entries(project: Project, limit_chars: int = None) -> List[dict]:
    """Entries from `always` topics for `speky prime` (owner first), newest first, within a size budget
    (`prime_knowledge_chars` in speky.yaml). Entries over the budget are reported per topic as
    `{"topic", "file", "more": n}` so the agent knows to read the rest."""
    limit = int(limit_chars or project.config.get("prime_knowledge_chars") or 4000)
    out, used = [], 0
    legacy = project.dir / "memory.md"  # milestone-1 memory file
    always = sorted((t for t in topics(project) if t["always"]), key=lambda t: (t["topic"] != "owner", t["topic"]))
    sources = [(t["topic"], t["file"], (project.root / t["file"]).read_text()) for t in always]
    if legacy.exists():
        sources.append(("memory", str(legacy.relative_to(project.root)), legacy.read_text()))
    for topic, file, text in sources:
        entries = entries_of(text)
        for n, e in enumerate(entries):
            if used + len(e) > limit:
                out.append({"topic": topic, "file": file, "more": len(entries) - n, "truncated": True})
                break
            out.append({"topic": topic, "text": e})
            used += len(e)
    return out


def promote(project: Project, topic: str, title: str) -> dict:
    """Turn a mature topic into an ADR and leave a pointer behind."""
    from . import journal
    path = knowledge_dir(project) / f"{slugify(topic)}.md"
    if not path.exists():
        raise SpekyError("topic_not_found", f"No knowledge topic '{topic}'.", "Run `speky knowledge`.")
    entries = entries_of(path.read_text())
    adr = journal.adr_new(project, title, context="\n".join(f"- {e}" for e in entries),
                          decision="<!-- State the rule this knowledge settles. -->")
    with open(path, "a") as f:
        f.write(f"\n> Promoted to ADR {adr['id']} ({adr['file']}) on {date.today().isoformat()}; "
                "keep adding new findings above.\n")
    return {"topic": topic, "adr": adr}
