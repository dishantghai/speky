"""`speky migrate [--apply]` — bring a SPEKY v2 project up to v3 without losing anything.

Deterministic part only: settings, folders, status.json normalisation and a report of what needs
judgement (seeding living specs, suspect completions). The judgement part is the speky-migrate skill.
Never deletes, moves or rewrites user documents.
"""
import json
import re
from typing import Dict, List

from . import config, graph, validation
from . import markdown as md
from .items import DONE_STATUSES, Project, now, write_json

V2_STATUS_ALIASES = {"done": "completed", "in-progress": "in_progress", "inprogress": "in_progress",
                     "complete": "completed", "todo": "draft", "planned": "ready"}


def plan(project: Project) -> Dict:
    steps: List[dict] = []
    issues: List[dict] = []
    if not (project.dir / config.CONFIG_NAME).exists():
        steps.append({"step": "create_config", "detail": f"create .speky/{config.CONFIG_NAME}"})
    if not project.capabilities_dir.exists():
        steps.append({"step": "create_capabilities", "detail": "create .speky/capabilities/"})

    seen: Dict[str, str] = {}
    suspect, no_ids, open_items = [], [], []
    for item in project.items():
        rel = str(item.path.relative_to(project.root))
        try:
            raw = item.load_status()
        except Exception as e:  # unreadable JSON is reported, never overwritten
            issues.append({"issue": "status_unreadable", "item": rel, "detail": str(e)})
            continue
        fixes = {}
        if not item.status_path.exists():
            fixes["create status.json"] = True
        if raw.get("id") != item.id:
            fixes["id"] = item.id
        status = str(raw.get("status", "draft")).lower()
        if status in V2_STATUS_ALIASES:
            fixes["status"] = V2_STATUS_ALIASES[status]
        elif status not in ("draft", "ready", "in_progress", "review", "completed", "archived"):
            fixes["status"] = "draft"
            issues.append({"issue": "unknown_status", "item": rel, "detail": f"'{status}' → draft"})
        deps = raw.get("dependencies", [])
        if deps and not isinstance(deps, list):
            fixes["dependencies"] = [str(deps)]
        if fixes:
            steps.append({"step": "normalise_status", "item": item.id, "detail": fixes})

        key = item.id.lower()
        if key in seen:
            issues.append({"issue": "duplicate_id", "item": rel, "detail": f"same ID as {seen[key]}"})
        seen[key] = rel

        final_status = fixes.get("status", status)
        text = item.read_doc()
        has_ids = bool(md.parse_requirements(md.strip_comments(text)))
        if final_status in DONE_STATUSES:
            skipped = [d for d in raw.get("drift_resolved", []) or []
                       if d.get("action") == "skipped" and d.get("type") in ("CODE_BEHIND", "TECH_DEVIATION")]
            if skipped:
                suspect.append({"item": item.id, "title": item.info()["title"],
                                "skipped_drift": len(skipped)})
        else:
            open_items.append(item.id)
            if not has_ids:
                no_ids.append(item.id)

    for dep_issue in _dependency_issues(project):
        issues.append(dep_issue)
    for cycle in graph.cycles(project):
        issues.append({"issue": "dependency_cycle", "detail": " → ".join(cycle)})

    judgement = []
    completed = [i.id for i in project.items() if i.info()["status"] in DONE_STATUSES]
    if completed and not any(project.capabilities_dir.glob("*/spec.md")):
        judgement.append({"task": "seed_living_specs", "items": completed,
                          "detail": "Write .speky/capabilities/<capability>/spec.md from what the code "
                                    "does today (speky-migrate skill, step 5)."})
    if suspect:
        judgement.append({"task": "check_suspect_completions", "items": suspect,
                          "detail": "Completed items whose v2 drift review skipped CODE_BEHIND/"
                                    "TECH_DEVIATION findings. Check the code; file gaps as stories."})
    if no_ids:
        judgement.append({"task": "add_requirement_ids", "items": no_ids,
                          "detail": "Open items without `### R1:` requirements; run `speky check <id>`."})
    harnesses = project.config.get("harnesses", []) if (project.dir / config.CONFIG_NAME).exists() else []
    if not harnesses:
        judgement.append({"task": "setup_harness",
                          "detail": "Run `speky setup claude-code|codex|agents-md` for the tools in use."})
    return {"root": str(project.root), "pending": steps, "issues": issues, "judgement": judgement,
            "items": len(project.items()), "open_items": open_items,
            "done": not steps}


def _dependency_issues(project: Project) -> List[dict]:
    all_info = graph.statuses(project)
    result = []
    for info in all_info.values():
        for dep in info["dependencies"]:
            if not project.try_find(dep):
                result.append({"issue": "unknown_dependency", "item": info["id"], "detail": dep})
    return result


def apply(project: Project) -> Dict:
    before = plan(project)
    applied = []
    for step in before["pending"]:
        if step["step"] == "create_config":
            config.save(project.root, dict(config.DEFAULTS))
        elif step["step"] == "create_capabilities":
            project.capabilities_dir.mkdir(parents=True, exist_ok=True)
            (project.capabilities_dir / "README.md").write_text(
                "# Living specs\n\nOne folder per capability: `<capability>/spec.md` describes how the "
                "system behaves **now**. Changes update them through `deltas/` when archived "
                "(`speky archive`). Format: https://github.com/dishantghai/speky/blob/main/docs/v3/CONTRACTS.md#4-living-specs-and-deltas\n")
        elif step["step"] == "normalise_status":
            item = project.find(step["item"])
            raw = item.load_status() if item.status_path.exists() else {"created": now()}
            for key, value in step["detail"].items():
                if key != "create status.json":
                    raw[key] = value
            raw.setdefault("migrated_to_v3", now())
            item.save_status(raw)
        applied.append(step)
    after = plan(project)
    return {"applied": applied, "remaining": after["pending"], "issues": after["issues"],
            "judgement": after["judgement"], "done": after["done"]}
