"""Harness adapters: `speky setup <harness> [--check | --remove]` (CONTRACTS.md §10).

Each recipe installs the SPEKY skills where that harness looks for them and a small managed block in
its instruction file. Blocks carry a version, profile and content hash so `--check` can tell
missing / stale / current, and `--remove` deletes only what SPEKY wrote.
"""
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from . import config
from .errors import SpekyError
from .items import Project

SKILLS_DIR = Path(__file__).parent / "skills"
BEGIN_RE = re.compile(r"<!-- BEGIN SPEKY v:3 profile:(\w+) hash:([0-9a-f]+) -->")
END = "<!-- END SPEKY v:3 -->"
V2_BEGIN = "<!-- BEGIN SPEKY MANAGED BLOCK"
V2_END = "<!-- END SPEKY MANAGED BLOCK -->"
HOOK_COMMAND = "command -v speky >/dev/null 2>&1 && speky prime --hook-json || true"

MINIMAL_BLOCK = """## SPEKY

This project uses SPEKY for spec-driven development (`.speky/`). The full workflow is injected at
session start by `speky prime`; if it is missing, run `speky prime`.

- Ask `speky next --json` what to do; follow the skill it names (`speky`, `speky-propose`,
  `speky-validate`, `speky-plan`, `speky-implement`, `speky-verify`).
- No completion claims without fresh evidence (`speky verify <id>`).
"""

FULL_BLOCK = """## SPEKY

This project uses SPEKY for spec-driven development. Changes live in `.speky/specs/` and
`.speky/stories/`; current behaviour lives in `.speky/capabilities/`. SPEKY holds state and rules;
you do the work through the `speky` CLI (every `--json` command prints one JSON document).

- Start with `speky prime` (workflow + current state), then `speky next --json`, and follow the
  action and skill it names. Skills: `speky`, `speky-propose`, `speky-validate`, `speky-plan`,
  `speky-implement`, `speky-verify` (in the skills folder for this tool).
- Size work first: a quick, clear fix needs no item; anything that changes behaviour gets
  `speky new spec|story "<title>"`.
- Requirements are `### R1: ...` with WHEN/THEN scenarios. Record evidence per requirement
  (`speky evidence <id> R1 --status met --evidence "<test id>"`), then `speky verify <id>`.
  No completion claims without fresh evidence.
- Validation converges: `speky check <id>`; record only verified findings; stop when it says converged.
- Discovered work: `speky new story "..." --discovered-from <id>`. Decisions: `speky decide`.
- Human gates (stack, design, scope, merge) are the user's call: stop and ask.
"""

RECIPES = {
    "claude-code": {"skills": ".claude/skills", "file": "CLAUDE.md", "profile": "minimal",
                    "hook": ".claude/settings.json", "v2_ide": "claude-code"},
    "codex": {"skills": ".agents/skills", "file": "AGENTS.md", "profile": "full", "hook": None,
              "v2_ide": None},
    "agents-md": {"skills": None, "file": "AGENTS.md", "profile": "full", "hook": None, "v2_ide": None},
}


def skill_names() -> List[str]:
    return sorted(p.name for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists())


def _block_text(profile: str) -> str:
    body = MINIMAL_BLOCK if profile == "minimal" else FULL_BLOCK
    digest = hashlib.sha1(body.encode()).hexdigest()[:8]
    return f"<!-- BEGIN SPEKY v:3 profile:{profile} hash:{digest} -->\n{body.rstrip()}\n{END}\n"


def _find_block(text: str):
    m = BEGIN_RE.search(text)
    if not m:
        return None
    end = text.find(END, m.end())
    if end == -1:
        return None
    return m.start(), end + len(END), m.group(1), m.group(2), text[m.end():end].strip("\n")


def _strip_v2_rules(project: Project, path: Path, text: str) -> (str, str):
    """Remove v2's rules from an instruction file. Returns (new_text, what_happened)."""
    start = text.find(V2_BEGIN)
    if start != -1:
        end = text.find(V2_END, start)
        if end != -1:
            return (text[:start].rstrip("\n") + "\n" + text[end + len(V2_END):].lstrip("\n")).strip("\n") + "\n", \
                "removed v2 managed block"
    if "# SPEKY Project Rules" in text and "# USER RULES" in text:
        backup_dir = project.dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{path.name.lstrip('.')}.{datetime.now():%Y%m%d-%H%M%S}.bak"
        backup.write_text(text)
        user = _legacy_user_rules(text)
        kept = f"# Project rules\n\n{user}\n" if user else ""
        return kept, f"replaced legacy v2 rules file (backup: {backup.relative_to(project.root)})"
    return text, ""


_LEGACY_TEMPLATE = {
    "Add your custom IDE rules below this line. They will be preserved when SPEKY updates.",
    "Example:", "- Always use TypeScript strict mode", "- Prefer async/await over promises",
    "- Use descriptive variable names",
}


def _legacy_user_rules(text: str) -> str:
    start = text.find("# USER RULES")
    end = text.find("\n---\n\n## Project Context", start)
    section = text[start + len("# USER RULES"):end if end != -1 else len(text)]
    lines = [l for l in section.splitlines() if l.strip() not in _LEGACY_TEMPLATE]
    return "\n".join(lines).strip()


def _write_block(project: Project, rel: str, profile: str) -> List[str]:
    path = project.root / rel
    text = path.read_text() if path.exists() else ""
    notes = []
    text, note = _strip_v2_rules(project, path, text)
    if note:
        notes.append(f"{rel}: {note}")
    block = _block_text(profile)
    found = _find_block(text)
    if found:
        start, end = found[0], found[1]
        text = text[:start] + block.rstrip("\n") + text[end:]
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block
    path.write_text(text if text.endswith("\n") else text + "\n")
    notes.append(f"{rel}: SPEKY block written ({profile})")
    return notes


def _install_skills(project: Project, rel: str) -> List[str]:
    dest = project.root / rel
    notes = []
    for name in skill_names():
        target = dest / name
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SKILLS_DIR / name / "SKILL.md", target / "SKILL.md")
        notes.append(f"{rel}/{name}/SKILL.md")
    return notes


def _hook_entries(settings: dict) -> list:
    return settings.setdefault("hooks", {}).setdefault("SessionStart", [])


def _is_speky_hook(entry: dict) -> bool:
    return any("speky prime" in h.get("command", "") for h in entry.get("hooks", []))


def _install_hook(project: Project, rel: str) -> List[str]:
    path = project.root / rel
    settings = {}
    if path.exists():
        try:
            settings = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError as e:
            raise SpekyError("settings_unreadable", f"{rel} is not valid JSON: {e}",
                             "Fix it by hand, then run setup again.")
    entries = _hook_entries(settings)
    entries[:] = [e for e in entries if not _is_speky_hook(e)]
    entries.append({"matcher": "startup|resume|clear|compact",
                    "hooks": [{"type": "command", "command": HOOK_COMMAND}]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return [f"{rel}: SessionStart hook runs `speky prime --hook-json` (startup, resume, clear, compact)"]


def _disable_v2_rules(project: Project, ide: str) -> List[str]:
    """Stop v2 from rewriting its big rules block for an IDE that v3 now manages."""
    ctx = project.dir / "context" / "context.json"
    if not ide or not ctx.exists():
        return []
    data = json.loads(ctx.read_text())
    current = data.get("enabled_ides")
    if current is None:
        cfg_text = (project.dir / "config.yaml").read_text() if (project.dir / "config.yaml").exists() else ""
        m = re.search(r"^ide:\s*(\S+)", cfg_text, re.MULTILINE)
        current = [m.group(1)] if m else ["windsurf"]
    if isinstance(current, str):
        current = [current]
    remaining = [i for i in current if i != ide]
    if remaining == current and "enabled_ides" in data:
        return []
    data["enabled_ides"] = remaining
    ctx.write_text(json.dumps(data, indent=2))
    return [f".speky/context/context.json: v2 rules no longer written for {ide}"]


def setup(project: Project, harness: str) -> Dict:
    recipe = _recipe(harness)
    notes = []
    if recipe["skills"]:
        notes += _install_skills(project, recipe["skills"])
    notes += _write_block(project, recipe["file"], recipe["profile"])
    if recipe["hook"]:
        notes += _install_hook(project, recipe["hook"])
    notes += _disable_v2_rules(project, recipe["v2_ide"])
    cfg = project.config
    if harness not in cfg["harnesses"]:
        cfg["harnesses"] = cfg["harnesses"] + [harness]
    config.save(project.root, cfg)
    return {"harness": harness, "changes": notes, "check": check(project, harness)}


def check(project: Project, harness: str) -> Dict:
    recipe = _recipe(harness)
    files = {}
    path = project.root / recipe["file"]
    found = _find_block(path.read_text()) if path.exists() else None
    if not found:
        files[recipe["file"]] = "missing"
    else:
        expected = _block_text(recipe["profile"])
        files[recipe["file"]] = "current" if found[2] == recipe["profile"] and \
            BEGIN_RE.search(expected).group(2) == found[3] and \
            found[4] == expected.split("\n", 1)[1].rsplit(END, 1)[0].strip("\n") else "stale"
        text = path.read_text()
        if V2_BEGIN in text or ("# SPEKY Project Rules" in text and "# USER RULES" in text):
            files[recipe["file"]] = "stale (v2 rules still present)"
    if recipe["skills"]:
        for name in skill_names():
            rel = f"{recipe['skills']}/{name}/SKILL.md"
            target = project.root / rel
            if not target.exists():
                files[rel] = "missing"
            else:
                files[rel] = "current" if target.read_text() == (SKILLS_DIR / name / "SKILL.md").read_text() \
                    else "stale"
    if recipe["hook"]:
        hook_path = project.root / recipe["hook"]
        ok = False
        if hook_path.exists():
            try:
                ok = any(_is_speky_hook(e) for e in json.loads(hook_path.read_text())
                         .get("hooks", {}).get("SessionStart", []))
            except json.JSONDecodeError:
                ok = False
        files[recipe["hook"]] = "current" if ok else "missing"
    overall = "current" if all(v == "current" for v in files.values()) else \
        "missing" if all(v == "missing" for v in files.values()) else "stale"
    return {"harness": harness, "status": overall, "files": files}


def remove(project: Project, harness: str) -> Dict:
    recipe = _recipe(harness)
    notes = []
    path = project.root / recipe["file"]
    if path.exists():
        found = _find_block(path.read_text())
        if found:
            text = path.read_text()
            text = (text[:found[0]].rstrip("\n") + "\n" + text[found[1]:].lstrip("\n")).strip("\n")
            path.write_text(text + "\n" if text else "")
            notes.append(f"{recipe['file']}: SPEKY block removed")
    if recipe["skills"]:
        for name in skill_names():
            target = project.root / recipe["skills"] / name
            if target.exists():
                shutil.rmtree(target)
                notes.append(f"{recipe['skills']}/{name}: removed")
    if recipe["hook"]:
        hook_path = project.root / recipe["hook"]
        if hook_path.exists():
            settings = json.loads(hook_path.read_text() or "{}")
            entries = _hook_entries(settings)
            before = len(entries)
            entries[:] = [e for e in entries if not _is_speky_hook(e)]
            if not entries:
                settings["hooks"].pop("SessionStart")
            if not settings["hooks"]:
                settings.pop("hooks")
            hook_path.write_text(json.dumps(settings, indent=2) + "\n")
            if len(entries) != before:
                notes.append(f"{recipe['hook']}: SessionStart hook removed")
    cfg = project.config
    cfg["harnesses"] = [h for h in cfg["harnesses"] if h != harness]
    config.save(project.root, cfg)
    return {"harness": harness, "changes": notes}


def _recipe(harness: str) -> dict:
    if harness not in RECIPES:
        raise SpekyError("unknown_harness", f"No setup recipe for '{harness}'.",
                         f"Available: {', '.join(RECIPES)}.")
    return RECIPES[harness]
