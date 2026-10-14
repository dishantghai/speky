"""Parsing the parts of change and capability documents that rules depend on."""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
CHANGE_REQ_RE = re.compile(r"^###\s+(R\d+)\s*:\s*(.+?)\s*$")
CAP_REQ_RE = re.compile(r"^###\s+([a-z0-9][a-z0-9-]*-R\d+)\s*:\s*(.+?)\s*$")
NEW_REQ_RE = re.compile(r"^###\s+(?:Requirement|R\d+)\s*:\s*(.+?)\s*$")
SCENARIO_RE = re.compile(r"^####\s+Scenario\s*:\s*(.+?)\s*$")
CLARIFY_RE = re.compile(r"\[NEEDS CLARIFICATION[^\]]*\]", re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# v3 section names and the v2 headings that mean the same thing
SECTION_ALIASES = {
    "why": ["why", "overview", "purpose", "description", "problem"],
    "scope": ["capabilities", "mvp scope", "scope", "this spec covers"],
    "non_goals": ["non-goals", "non goals", "out of scope"],
    "requirements": ["requirements"],
    "assumptions": ["assumptions"],
    "open_questions": ["open questions"],
}


@dataclass
class Scenario:
    title: str
    lines: List[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        text = " ".join(self.lines).upper()
        return bool(re.search(r"\bWHEN\b", text) and re.search(r"\bTHEN\b", text))


@dataclass
class Requirement:
    id: Optional[str]
    title: str
    body: List[str] = field(default_factory=list)
    scenarios: List[Scenario] = field(default_factory=list)

    def text(self, header: str = None) -> str:
        head = header or (f"### {self.id}: {self.title}" if self.id else f"### Requirement: {self.title}")
        return "\n".join([head, *self.body]).rstrip() + "\n"


def strip_comments(text: str) -> str:
    return COMMENT_RE.sub("", text)


def sections(text: str) -> Dict[str, str]:
    """`## Heading` -> body, keys lower-cased."""
    result, current, buf = {}, None, []
    for line in text.splitlines():
        m = SECTION_RE.match(line)
        if m and not line.startswith("###"):
            if current is not None:
                result[current] = "\n".join(buf).strip()
            current, buf = m.group(1).strip().lower(), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        result[current] = "\n".join(buf).strip()
    return result


def find_section(text: str, key: str) -> Optional[str]:
    """Body of the first section matching a v3 key or one of its v2 aliases (None if absent)."""
    found = sections(text)
    for name, body in found.items():
        clean = re.sub(r"[^a-z -]", "", name).strip()
        if any(clean == alias or clean.startswith(alias) for alias in SECTION_ALIASES[key]):
            return body
    return None


def parse_requirements(text: str, header_re=CHANGE_REQ_RE) -> List[Requirement]:
    """Requirements (`### R1: Title`) with their scenarios, in document order."""
    reqs, current, scenario = [], None, None
    for line in text.splitlines():
        m = header_re.match(line) or (NEW_REQ_RE.match(line) if header_re is not CHANGE_REQ_RE else None)
        if m:
            if header_re is not CHANGE_REQ_RE and NEW_REQ_RE.match(line):
                current = Requirement(None, NEW_REQ_RE.match(line).group(1))
            else:
                current = Requirement(m.group(1), m.group(2))
            reqs.append(current)
            scenario = None
            continue
        if current is None:
            continue
        if line.startswith("## ") or (line.startswith("### ") and not line.startswith("####")):
            current, scenario = None, None
            continue
        current.body.append(line)
        s = SCENARIO_RE.match(line)
        if s:
            scenario = Scenario(s.group(1))
            current.scenarios.append(scenario)
        elif scenario is not None:
            scenario.lines.append(line)
    for req in reqs:
        while req.body and not req.body[-1].strip():
            req.body.pop()
    return reqs


def clarification_markers(text: str) -> List[str]:
    return CLARIFY_RE.findall(strip_comments(text))


def section_has_content(body: Optional[str]) -> bool:
    if body is None:
        return False
    body = strip_comments(body).strip()
    return bool(body) and body.lower() not in ("none", "n/a", "-", "tbd")


@dataclass
class Delta:
    added: List[Requirement] = field(default_factory=list)
    modified: List[Requirement] = field(default_factory=list)
    removed: List[Requirement] = field(default_factory=list)
    purpose: str = ""
    unparsed: List[str] = field(default_factory=list)  # headings SPEKY could not read


def parse_delta(text: str) -> Delta:
    delta = Delta()
    parts = sections(strip_comments(text))
    for name, body in parts.items():
        if name.split()[0] in ("added", "modified", "removed"):
            for line in body.splitlines():
                if line.startswith("### ") and not (CAP_REQ_RE.match(line) or
                                                    (name.startswith("added") and NEW_REQ_RE.match(line))):
                    delta.unparsed.append(f"{name}: {line.strip()}")
        if name.startswith("added"):
            delta.added = parse_requirements(body, CAP_REQ_RE)
        elif name.startswith("modified"):
            delta.modified = parse_requirements(body, CAP_REQ_RE)
        elif name.startswith("removed"):
            delta.removed = parse_requirements(body, CAP_REQ_RE)
        elif name == "purpose":
            delta.purpose = body.strip()
    return delta
