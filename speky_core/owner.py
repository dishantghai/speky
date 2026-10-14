"""Owner actions: things only the owner can do (accounts, money, judgement, people).

Stored in `.speky/owner.md`. The owner ticks boxes and writes notes under an item; agents read the
file at every session start (`speky prime`) and turn notes into tasks. Format:

    ## Decide or provide
    - [ ] O3 An API key for the real-model benchmark
      - Notes: added OPENAI_API_KEY to .env
"""
import re
from typing import List, Optional

from .errors import SpekyError
from .items import Project, now

OWNER_NAME = "owner.md"
HEADER = """# Owner actions

Things only the owner can do: accounts, money, judgement, people. Tick the box when done and write
notes under an item (indented) — agents read this file at the start of every session.
"""
ITEM_RE = re.compile(r"^- \[(.)\] (?:(O\d+)\s+)?(.*)$")
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")


class OwnerActions:
    def __init__(self, project: Project):
        self.project = project
        self.path = project.dir / OWNER_NAME
        self.lines = self.path.read_text().splitlines() if self.path.exists() else HEADER.splitlines()

    def items(self) -> List[dict]:
        result, section, current = [], "", None
        for i, line in enumerate(self.lines):
            s = SECTION_RE.match(line)
            if s and not line.startswith("###"):
                section, current = s.group(1), None
                continue
            m = ITEM_RE.match(line)
            if m:
                current = {"id": m.group(2) or "", "done": m.group(1).lower() == "x", "text": m.group(3).strip(),
                           "section": section, "notes": [], "line": i}
                result.append(current)
                continue
            if current is not None and line.startswith((" ", "\t")) and line.strip():
                current["notes"].append(line.strip())
            elif line.strip() and not line.startswith((" ", "\t")):
                current = None
        return result

    def open_items(self) -> List[dict]:
        return [i for i in self.items() if not i["done"]]

    def save(self) -> None:
        self.project.dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(self.lines).rstrip("\n") + "\n")

    def _next_id(self) -> str:
        nums = [int(m.group(1)) for l in self.lines for m in [re.search(r"\bO(\d+)\b", l)]
                if m and ITEM_RE.match(l)]
        return f"O{max(nums, default=0) + 1}"

    def assign_missing_ids(self) -> int:
        changed = 0
        for item in self.items():
            if not item["id"]:
                m = ITEM_RE.match(self.lines[item["line"]])
                self.lines[item["line"]] = f"- [{m.group(1)}] {self._next_id()} {m.group(3).strip()}"
                changed += 1
        if changed:
            self.save()
        return changed

    def add(self, text: str, section: str = "To do", note: str = "") -> dict:
        oid = self._next_id()
        new = [f"- [ ] {oid} {text}"] + ([f"  - {note}"] if note else [])
        # append at the end of the named section, creating it if needed
        start = next((i for i, l in enumerate(self.lines)
                      if SECTION_RE.match(l) and SECTION_RE.match(l).group(1).lower() == section.lower()), None)
        if start is None:
            self.lines += ["", f"## {section}", ""] + new
        else:
            end = next((i for i in range(start + 1, len(self.lines)) if SECTION_RE.match(self.lines[i])),
                       len(self.lines))
            while end > start + 1 and not self.lines[end - 1].strip():
                end -= 1
            self.lines[end:end] = new
        self.save()
        return self.get(oid)

    def get(self, oid: str) -> dict:
        for item in self.items():
            if item["id"].lower() == oid.lower():
                return item
        raise SpekyError("owner_action_not_found", f"No owner action {oid}.", "Run `speky owner list`.")

    def set_done(self, oid: str, done: bool = True, note: str = "") -> dict:
        item = self.get(oid)
        m = ITEM_RE.match(self.lines[item["line"]])
        self.lines[item["line"]] = f"- [{'x' if done else ' '}] {item['id']} {m.group(3).strip()}"
        if note:
            insert_at = item["line"] + 1 + len(item["notes"])
            self.lines[insert_at:insert_at] = [f"  - {note} ({now()[:10]})"]
        self.save()
        return self.get(oid)
