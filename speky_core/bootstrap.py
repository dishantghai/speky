"""`speky init`: start SPEKY in a project — no model, no questions.

Creates `.speky/` (settings, folders), records the idea or what the project says about itself
(docs, manifests, detected tech) as product/tech knowledge, detects the test command, and optionally
sets up a harness. The interview (at most five questions), the product description and the first
specs or tasks are the agent's job (speky-init skill).
"""
from pathlib import Path

from . import config, harness, knowledge, projectinfo, testing
from .items import Project


def init(root: Path, idea: str = "", from_project: bool = False, harness_name: str = None) -> dict:
    project = Project(root)
    existed = project.dir.is_dir()
    legacy_v2 = (project.dir / "context" / "context.json").exists()
    for sub in ("specs", "stories", "phases", "epics", "knowledge"):
        (project.dir / sub).mkdir(parents=True, exist_ok=True)
    project.ensure_capabilities_dir()
    if not (project.dir / config.CONFIG_NAME).exists():
        config.save(project.root, dict(config.DEFAULTS))
    recorded = []
    if idea:
        knowledge.remember(project, f"Product idea (from the owner): {idea}", "product", always=True)
        recorded.append("product idea")
    evidence = None
    if from_project:
        evidence = projectinfo.collect_evidence(project.root)
        if not idea and evidence.get("summary") and not evidence["summary"].startswith("Existing project '"):
            knowledge.remember(project, f"From the README: {evidence['summary']}", "product", always=True)
            recorded.append("README summary")
        for kind, value in (evidence.get("detected_tech") or {}).items():
            knowledge.remember(project, f"{kind.capitalize()} (detected from manifests): {value}", "tech",
                               read_when="choosing libraries or touching infrastructure")
            recorded.append(f"tech: {kind}")
    tests = testing.init(project)
    setup = harness.setup(project, harness_name) if harness_name else None
    docs = [str(d.relative_to(project.root)) for d in (evidence or {}).get("docs", [])][:15]
    return {"root": str(project.root), "created": not existed, "recorded": recorded,
            "verify_command": project.config.get("verify_command"),
            "detected_tests": tests["detected"], "harness": setup and setup["check"]["status"],
            "read_first": docs,
            "legacy_v2": legacy_v2,
            "next": ("This project has SPEKY v2 data: run `speky migrate` first." if legacy_v2 else
                     "Follow the speky-init skill: ask at most five questions (one at a time, each with a "
                     "recommended answer), describe the product with `speky remember --topic product`, record "
                     "stack decisions as ADRs, then propose the first phase and specs or tasks.")}
