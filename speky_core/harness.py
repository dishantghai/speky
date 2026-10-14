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
PRECOMPACT_COMMAND = "command -v speky >/dev/null 2>&1 && speky checkpoint --auto >/dev/null 2>&1 || true"

MINIMAL_BLOCK = """## SPEKY

This project uses SPEKY for spec-driven development (`.speky/`). The full workflow is injected at
session start by `speky prime`; if it is missing, run `speky prime`.

- Ask `speky next --json` what to do and follow the skill it names (`speky` is the hub).
- No completion claims without fresh evidence (`speky verify <id>`).
"""

FULL_BLOCK = """## SPEKY

This project uses SPEKY for spec-driven development. Changes live in `.speky/specs/` and
`.speky/stories/`; current behaviour lives in `.speky/capabilities/`. SPEKY holds state and rules;
you do the work through the `speky` CLI (every `--json` command prints one JSON document).

- Start with `speky prime` (where to pick up + workflow), then `speky next --json`, and follow the
  action and skill it names. Skills (in this tool's skills folder): `speky` (hub), `speky-init`,
  `speky-propose`, `speky-validate`, `speky-plan`, `speky-implement`, `speky-test`, `speky-verify`,
  `speky-import`, `speky-design`, `speky-migrate`.
- Write learnings down when you learn them (`speky remember --topic`); hand off at the end of a session
  or milestone (`speky handoff --file <notes.md>`).
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


def _imports_agents_md(text: str) -> bool:
    """CLAUDE.md that only imports AGENTS.md (plus, possibly, an old SPEKY block)."""
    found = _find_block(text)
    if found:
        text = text[:found[0]] + text[found[1]:]
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return bool(lines) and all(l.startswith("@") for l in lines) and any(l == "@AGENTS.md" for l in lines)


def instruction_target(project: Project, recipe: dict) -> (str, str):
    """(file, profile) the SPEKY block goes into. A CLAUDE.md that only imports AGENTS.md means the
    project keeps one instruction file for every tool, so the block goes there (full profile)."""
    rel = recipe["file"]
    if rel == "CLAUDE.md":
        path = project.root / "CLAUDE.md"
        if path.exists() and _imports_agents_md(path.read_text()):
            return "AGENTS.md", "full"
    return rel, recipe["profile"]


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
        (backup_dir / ".gitignore").write_text("# local safety copies; git history already has the originals\n*\n")
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


TESTING_SECTION_RE = re.compile(r"# 🧪 SPEKY Testing Context.*?(?:(?:# END SPEKY Testing Context\s*)+|\Z)",
                                re.DOTALL)
STRAY_TESTING_END_RE = re.compile(r"^(?:# END SPEKY Testing Context\s*\n)+", re.MULTILINE)


def _strip_v2_testing(text: str) -> (str, bool):
    """Remove v2's testing-context section (and stray end markers) from an instruction file."""
    new = TESTING_SECTION_RE.sub("", text)
    new = STRAY_TESTING_END_RE.sub("", new)
    new = re.sub(r"\n{3,}", "\n\n", new).strip("\n")
    return (new + "\n" if new else ""), new.strip() != text.strip()


def _write_block(project: Project, rel: str, profile: str) -> List[str]:
    path = project.root / rel
    text = path.read_text() if path.exists() else ""
    notes = []
    text, note = _strip_v2_rules(project, path, text)
    if note:
        notes.append(f"{rel}: {note}")
    text, stripped = _strip_v2_testing(text)
    if stripped:
        notes.append(f"{rel}: removed v2 testing-context section (see `speky prime`)")
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


def _remove_block(project: Project, rel: str) -> List[str]:
    path = project.root / rel
    if not path.exists():
        return []
    text = path.read_text()
    found = _find_block(text)
    if not found:
        return []
    text = (text[:found[0]].rstrip("\n") + "\n" + text[found[1]:].lstrip("\n")).strip("\n")
    path.write_text(text + "\n" if text else "")
    return [f"{rel}: SPEKY block removed"]


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
    return any(("speky prime" in h.get("command", "")) or ("speky checkpoint" in h.get("command", ""))
               for h in entry.get("hooks", []))


def _install_hook(project: Project, rel: str) -> List[str]:
    path = project.root / rel
    settings = {}
    if path.exists():
        try:
            settings = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError as e:
            raise SpekyError("settings_unreadable", f"{rel} is not valid JSON: {e}",
                             "Fix it by hand, then run setup again.")
    hooks = settings.setdefault("hooks", {})
    for event, matcher, command in (("SessionStart", "startup|resume|clear|compact", HOOK_COMMAND),
                                    ("PreCompact", "manual|auto", PRECOMPACT_COMMAND)):
        entries = hooks.setdefault(event, [])
        entries[:] = [e for e in entries if not _is_speky_hook(e)]
        entries.append({"matcher": matcher, "hooks": [{"type": "command", "command": command}]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return [f"{rel}: SessionStart hook runs `speky prime --hook-json` (startup, resume, clear, compact)",
            f"{rel}: PreCompact hook runs `speky checkpoint --auto` (saves state before compaction)"]


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
    target, profile = instruction_target(project, recipe)
    if target != recipe["file"]:
        notes += _remove_block(project, recipe["file"])
        notes.append(f"{recipe['file']} only imports {target}: SPEKY block goes into {target}")
    notes += _write_block(project, target, profile)
    if recipe["hook"]:
        notes += _install_hook(project, recipe["hook"])
    notes += _disable_v2_rules(project, recipe["v2_ide"])
    project.capabilities_dir.mkdir(parents=True, exist_ok=True)
    cfg = project.config
    if harness not in cfg["harnesses"]:
        cfg["harnesses"] = cfg["harnesses"] + [harness]
    config.save(project.root, cfg)
    return {"harness": harness, "changes": notes, "check": check(project, harness)}


def check(project: Project, harness: str) -> Dict:
    recipe = _recipe(harness)
    files = {}
    target, profile = instruction_target(project, recipe)
    path = project.root / target
    found = _find_block(path.read_text()) if path.exists() else None
    if not found:
        files[target] = "missing"
    else:
        expected = _block_text(profile)
        files[target] = "current" if found[2] == profile and \
            BEGIN_RE.search(expected).group(2) == found[3] and \
            found[4] == expected.split("\n", 1)[1].rsplit(END, 1)[0].strip("\n") else "stale"
        text = path.read_text()
        if V2_BEGIN in text or ("# SPEKY Project Rules" in text and "# USER RULES" in text) \
                or "SPEKY Testing Context" in text:
            files[target] = "stale (v2 rules still present)"
    if target != recipe["file"] and (project.root / recipe["file"]).exists() and \
            _find_block((project.root / recipe["file"]).read_text()):
        files[recipe["file"]] = "stale (SPEKY block belongs in %s)" % target
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
                hooks = json.loads(hook_path.read_text()).get("hooks", {})
                ok = all(any(_is_speky_hook(e) for e in hooks.get(ev, []))
                         for ev in ("SessionStart", "PreCompact"))
            except json.JSONDecodeError:
                ok = False
        files[recipe["hook"]] = "current" if ok else "missing"
    overall = "current" if all(v == "current" for v in files.values()) else \
        "missing" if all(v == "missing" for v in files.values()) else "stale"
    return {"harness": harness, "status": overall, "files": files}


def remove(project: Project, harness: str) -> Dict:
    recipe = _recipe(harness)
    notes = []
    target, _ = instruction_target(project, recipe)
    still_used = {instruction_target(project, RECIPES[h])[0] for h in project.config.get("harnesses", [])
                  if h != harness and h in RECIPES}
    for rel in {recipe["file"], target} - still_used:
        notes += _remove_block(project, rel)
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
            hooks = settings.get("hooks", {})
            removed = False
            for event in ("SessionStart", "PreCompact"):
                entries = hooks.get(event, [])
                kept = [e for e in entries if not _is_speky_hook(e)]
                removed = removed or len(kept) != len(entries)
                if kept:
                    hooks[event] = kept
                else:
                    hooks.pop(event, None)
            if not hooks:
                settings.pop("hooks", None)
            hook_path.write_text(json.dumps(settings, indent=2) + "\n")
            if removed:
                notes.append(f"{recipe['hook']}: SPEKY hooks removed")
    cfg = project.config
    cfg["harnesses"] = [h for h in cfg["harnesses"] if h != harness]
    config.save(project.root, cfg)
    return {"harness": harness, "changes": notes}


def _recipe(harness: str) -> dict:
    if harness not in RECIPES:
        raise SpekyError("unknown_harness", f"No setup recipe for '{harness}'.",
                         f"Available: {', '.join(RECIPES)}.")
    return RECIPES[harness]
