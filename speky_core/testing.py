"""Testing (v2's `speky test …`): runner detection, recorded runs, requirement ↔ test links, gaps,
coverage against a threshold, and TDD red/green proof.

Settings live in `speky.yaml` under `testing:` (`verify_command` stays the project's main test command):

    testing:
      coverage_command: "pytest --cov -q"
      coverage_threshold: 80
      e2e_command: "npx playwright test"

Writing tests, end-to-end scenarios and triaging failures (regression / outdated / flaky / expected under
TDD) is the agent's work (speky-test skill); SPEKY records the runs and the evidence.
"""
import json
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from . import config as config_mod
from . import markdown as md
from .errors import SpekyError
from .items import Project, now, write_json
from .verification import load_evidence, record_evidence

TEST_ID_RE = re.compile(r"(test[_\w]*\.(py|ts|tsx|js|jsx|go|rs|dart)|_test\.|\.test\.|\.spec\.|::|tests?/)", re.I)


def detect(project: Project) -> dict:
    """Best guess at the project's test, coverage and e2e commands."""
    root = project.root
    found = {"runner": None, "verify_command": None, "coverage_command": None, "e2e_command": None}
    pkg = root / "package.json"
    if pkg.exists():
        data = json.loads(pkg.read_text() or "{}")
        scripts = data.get("scripts", {})
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        manager = "pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists() else "npm"
        if "test" in scripts:
            found.update(runner="vitest" if "vitest" in deps or "vitest" in scripts["test"] else
                         "jest" if "jest" in deps or "jest" in scripts["test"] else "node",
                         verify_command=f"{manager} test")
        if "@playwright/test" in deps:
            found["e2e_command"] = "npx playwright test"
        if found["runner"] == "vitest":
            found["coverage_command"] = "npx vitest run --coverage"
        elif found["runner"] == "jest":
            found["coverage_command"] = "npx jest --coverage"
    elif (root / "pyproject.toml").exists() or (root / "pytest.ini").exists() or (root / "tests").is_dir() \
            or any(root.glob("test_*.py")) or any(root.glob("*_test.py")):
        runner = "uv run pytest -q" if (root / "uv.lock").exists() else "python -m pytest -q"
        found.update(runner="pytest", verify_command=runner,
                     coverage_command=runner.replace("pytest -q", "pytest -q --cov"))
    elif (root / "pubspec.yaml").exists():
        found.update(runner="flutter", verify_command="flutter test", coverage_command="flutter test --coverage")
    elif (root / "go.mod").exists():
        found.update(runner="go", verify_command="go test ./...", coverage_command="go test -cover ./...")
    elif (root / "Cargo.toml").exists():
        found.update(runner="cargo", verify_command="cargo test")
    return found


def _legacy_threshold(project: Project) -> Optional[int]:
    path = project.dir / "testing" / "config.yaml"
    if path.exists():
        m = re.search(r"^coverage_threshold:\s*(\d+)", path.read_text(), re.MULTILINE)
        if m:
            return int(m.group(1))
    return None


def settings(project: Project) -> dict:
    cfg = project.config
    t = dict(cfg.get("testing") or {})
    t.setdefault("coverage_threshold", _legacy_threshold(project) or 80)
    t["verify_command"] = cfg.get("verify_command") or ""
    return t


def init(project: Project) -> dict:
    found = detect(project)
    cfg = project.config
    testing = dict(cfg.get("testing") or {})
    if not cfg.get("verify_command") and found["verify_command"]:
        cfg["verify_command"] = found["verify_command"]
    for key in ("coverage_command", "e2e_command"):
        if found[key] and not testing.get(key):
            testing[key] = found[key]
    testing.setdefault("coverage_threshold", _legacy_threshold(project) or 80)
    testing["runner"] = found["runner"]
    cfg["testing"] = testing
    config_mod.save(project.root, cfg)
    return {"detected": found, "settings": settings(project)}


def _runs_path(project: Project) -> Path:
    return project.dir / "testing" / "runs.json"


def _record(project: Project, kind: str, result: dict) -> None:
    path = _runs_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text()) if path.exists() else {}
    data[kind] = result
    write_json(path, data)


def _execute(project: Project, cmd: str) -> dict:
    proc = subprocess.run(cmd, shell=True, cwd=project.root, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    return {"command": cmd, "exit_code": proc.returncode, "passed": proc.returncode == 0, "at": now(),
            "output_tail": "\n".join(out.splitlines()[-25:]), "_output": out}


def run(project: Project, kind: str = "unit", files: List[str] = None) -> dict:
    s = settings(project)
    cmd = s["verify_command"] if kind == "unit" else s.get(f"{kind}_command", "")
    if not cmd:
        raise SpekyError("no_test_command", f"No {kind} test command configured.",
                         "Run `speky test init`, or set verify_command / testing.<kind>_command in speky.yaml.")
    if files:
        cmd = f"{cmd} {' '.join(files)}"
    result = _execute(project, cmd)
    result.pop("_output")
    _record(project, kind, result)
    from . import continuity
    cp = continuity.load_checkpoint(project)
    if kind == "unit" and not files:
        cp["last_test"] = {k: result[k] for k in ("command", "exit_code", "passed", "at")}
        write_json(project.dir / continuity.CHECKPOINT_NAME, cp)
    return result


def coverage(project: Project) -> dict:
    s = settings(project)
    cmd = s.get("coverage_command")
    if not cmd:
        raise SpekyError("no_coverage_command", "No coverage command configured.",
                         "Set testing.coverage_command in speky.yaml (or `speky test init`).")
    result = _execute(project, cmd)
    out = result.pop("_output")
    pct = None
    for pattern in (r"^TOTAL\s+.*?(\d+(?:\.\d+)?)%\s*$", r"All files\s*\|\s*(\d+(?:\.\d+)?)",
                    r"coverage:\s*(\d+(?:\.\d+)?)%", r"Statements\s*:\s*(\d+(?:\.\d+)?)%"):
        m = re.search(pattern, out, re.MULTILINE)
        if m:
            pct = float(m.group(1))
            break
    threshold = s.get("coverage_threshold", 80)
    result.update(percent=pct, threshold=threshold,
                  meets_threshold=(pct is not None and pct >= threshold) if pct is not None else None)
    _record(project, "coverage", result)
    return result


def link(project: Project, ref: str, req: str, test_id: str) -> dict:
    """A test proves a requirement (recorded as `met` evidence)."""
    item = project.find(ref)
    return record_evidence(project, item, req, "met", test_id)


def gaps(project: Project, ref: str = None) -> dict:
    items = [project.find(ref)] if ref else project.items()
    rows = []
    for item in items:
        reqs = md.parse_requirements(md.strip_comments(item.read_doc()))
        ev = load_evidence(item)
        without = [r.id for r in reqs if not TEST_ID_RE.search(ev.get(r.id, {}).get("evidence", ""))]
        if reqs and without:
            rows.append({"item": item.id, "title": item.info()["title"], "status": item.info()["status"],
                         "requirements_without_tests": without})
    return {"gaps": rows, "total": sum(len(r["requirements_without_tests"]) for r in rows)}


def tdd(project: Project, ref: str, req: str, phase: str, test_cmd: str) -> dict:
    """Red: the test must fail before the code exists. Green: the same test must pass."""
    item = project.find(ref)
    result = _execute(project, test_cmd)
    result.pop("_output")
    status = item.load_status()
    tdd_state = status.setdefault("tdd_proof", {})  # v2 uses "tdd" for something else
    entry = tdd_state.setdefault(req.upper(), {})
    if phase == "red":
        if result["passed"]:
            raise SpekyError("tdd_not_red", f"`{test_cmd}` passes already; a red test must fail first.",
                             "Write a test that fails for the missing behaviour, then record red again.")
        entry["red"] = {"command": test_cmd, "at": result["at"], "exit_code": result["exit_code"]}
    else:
        if "red" not in entry:
            raise SpekyError("tdd_no_red", f"No red run recorded for {req}.",
                             f"Run `speky test red {item.id} {req} --cmd \"...\"` first.")
        if not result["passed"]:
            raise SpekyError("tdd_not_green", f"`{test_cmd}` still fails.", "Make it pass, then record green.")
        entry["green"] = {"command": test_cmd, "at": result["at"]}
        record_evidence(project, item, req, "met", f"{test_cmd} (red → green)")
    item.update_status(tdd_proof=tdd_state)
    return {"item": item.id, "requirement": req.upper(), "phase": phase, **result}


def status(project: Project) -> dict:
    path = _runs_path(project)
    runs = json.loads(path.read_text()) if path.exists() else {}
    tdd_items = []
    for item in project.items():
        t = item.load_status().get("tdd_proof")
        if t:
            tdd_items.append({"item": item.id, "requirements": {k: sorted(v) for k, v in t.items()}})
    return {"settings": settings(project), "last_runs": runs, "gaps": gaps(project)["total"],
            "tdd": tdd_items}
