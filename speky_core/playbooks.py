"""Playbooks: how this project does a kind of work, by label.

Some work has its own workflow — UI work goes through design narratives, a design tool and a UX review;
data migrations through a dry run and a backup. The project names it once in `speky.yaml`:

    playbooks:
      ui:
        skill: screen-design-narratives          # a skill the agent follows (see `extra_skills`)
        read: [docs/ux/stitch.md, docs/ux/DESIGN.md]
        note: "Never show the owner a UI without a recorded UX review."

An item or task with that label (`--labels ui`) gets the playbook in `speky next` and `speky context`.
SPEKY does not run the playbook; it makes sure the agent knows it applies.
"""
from typing import List

from .items import Project


def for_labels(project: Project, labels: List[str]) -> List[dict]:
    books = project.config.get("playbooks") or {}
    out = []
    for label in labels or []:
        book = books.get(label)
        if isinstance(book, dict):
            out.append({"label": label, "skill": book.get("skill"), "read": list(book.get("read") or []),
                        "note": book.get("note", "")})
    return out


def instruction(books: List[dict]) -> str:
    parts = []
    for b in books:
        bits = [f"This is `{b['label']}` work"]
        if b["skill"]:
            bits.append(f"follow the `{b['skill']}` skill")
        if b["read"]:
            bits.append("read " + ", ".join(f"`{r}`" for r in b["read"]))
        parts.append(": ".join([bits[0], "; ".join(bits[1:])]) if len(bits) > 1 else bits[0])
        if b["note"]:
            parts[-1] += f". {b['note']}"
    return " ".join(p if p.endswith(".") else p + "." for p in parts)
