"""One SPEKY: every v2 capability, proven on its native command (rows of docs/v3/PLAN.md §11)."""
import json
import subprocess

import pytest

from speky_core import phases
from speky_core.items import Project

from .conftest import GOOD_SPEC, cli, git, spec


# ---------------------------------------------------------------- init
def test_init_new_idea(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = cli("init", "A web app that turns cooking videos into recipe cards", "--harness", "claude-code")
    assert out["created"] and out["harness"] == "current" and "product idea" in out["recorded"]
    assert (tmp_path / ".speky" / "knowledge" / "product.md").read_text().count("cooking videos") == 1
    assert "speky-init" in out["next"]


def test_init_from_project_reads_docs_manifests_and_tests(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("# Recipe Cards\n\nTurns cooking videos into recipe cards.\n")
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "vitest --run"},
                                                       "dependencies": {"react": "18", "express": "4"},
                                                       "devDependencies": {"vitest": "1"}}))
    (tmp_path / "pnpm-lock.yaml").write_text("")
    monkeypatch.chdir(tmp_path)
    out = cli("init", "--from-project")
    assert out["verify_command"] == "pnpm test"
    assert "README.md" in out["read_first"]
    tech = (tmp_path / ".speky" / "knowledge" / "tech.md").read_text()
    assert "React" in tech and "Express" in tech
    assert "Recipe Cards" in (tmp_path / ".speky" / "knowledge" / "product.md").read_text()


def test_init_in_a_v2_project_points_to_migrate(tmp_path, monkeypatch):
    (tmp_path / ".speky" / "context").mkdir(parents=True)
    (tmp_path / ".speky" / "context" / "context.json").write_text("{}")
    monkeypatch.chdir(tmp_path)
    assert "speky migrate" in cli("init")["next"]


# ---------------------------------------------------------------- spec / story / adopt
def test_spec_and_story_with_epic_related_files_phase_labels(project):
    cli("spec", "Import video")
    cli("phases", "add", "MVP", "--id", "mvp")
    cli("epic", "add", "Importing", "--spec", "001")
    out = cli("story", "Paste link", "--type", "bug", "--epic", "E001", "--related", "001",
              "--files", "src/import.ts,src/link.ts", "--phase", "mvp", "--labels", "ui")
    status = json.loads((project.root / out["path"] / "status.json").read_text())
    assert out["item"] == "B001" and status["related_epic"] == "E001"
    assert status["related_specs"] == ["001"] and status["affected_files"] == ["src/import.ts", "src/link.ts"]
    assert status["phase"] == "mvp" and status["labels"] == ["ui"]
    assert cli("new", "story", "Thumb", "--type", "enhancement")["item"] == "E001"


def test_adopt_hand_made_folders(project):
    story = project.stories_dir / "F009-hand-made"
    story.mkdir(parents=True)
    (story / "story.md").write_text(GOOD_SPEC)
    out = cli("adopt", "F009")
    assert out["converged"] and cli("state")["items"][0]["id"] == "F009"


def test_validate_aliases_are_check(project):
    spec(project)
    assert cli("validate-spec", "001")["round"] == 1
    assert cli("validate-spec", "001")["cached"]


# ---------------------------------------------------------------- plan / implement / complete / commit
def test_plan_implement_complete_commit(repo):
    item = spec(repo)
    assert "speky-plan" in cli("plan", "001")["instruction"]
    started = cli("implement", "001")
    assert started["status"] == "in_progress" and started["context"]["item"] == "001"
    (repo.root / "feature.py").write_text("def ok(): return True\n")
    (repo.root / ".env").write_text("SECRET=1\n")
    cli("evidence", "001", "R1", "--status", "met", "--evidence", "tests/test_x.py::test_a")
    cli("evidence", "001", "R2", "--status", "met", "--evidence", "tests/test_x.py::test_b")
    assert cli("commit", "001", expect=1)["error"]["code"] == "not_verified"
    done = cli("complete", "001", "--run", "true")
    assert done["passed"] and done["archive"]["status"] == "archived"
    dry = cli("commit", "001", "--dry-run")
    assert dry["message"].startswith("feat(001): Paste a video link")
    assert "R1 Accept a video link — met: tests/test_x.py::test_a" in dry["message"]
    assert "feature.py" in dry["files"] and ".env" in dry["held_back"]
    out = cli("commit", "001")
    assert out["committed"] and "feat(001)" in git(repo.root, "log", "--oneline", "-1")
    assert ".env" in git(repo.root, "status", "--porcelain")  # the secret stayed out


# ---------------------------------------------------------------- status / review / cleanup / backlog
def test_status_view(project):
    spec(project)
    out = cli("status")
    assert out["items"][0]["id"] == "001" and out["next"]["action"] in ("validate", "plan")


def test_review_reports_completions_without_evidence(repo):
    item = spec(repo)
    item.update_status(status="completed")
    out = cli("review", "--no-tests")
    assert out["items"][0]["verdict"] == "no_evidence"


def test_cleanup_moves_clutter_but_never_speky_files(project):
    (project.root / "IMPLEMENTATION_COMPLETE.md").write_text("done!")
    (project.dir / "random-notes.md").write_text("x")
    cli("handoff", "--done", "x", "--no-tests")  # creates state.md and log.md
    dry = cli("cleanup")
    assert set(dry["clutter"]) == {"IMPLEMENTATION_COMPLETE.md", ".speky/random-notes.md"}
    out = cli("cleanup", "--apply")
    assert out["applied"] and not (project.root / "IMPLEMENTATION_COMPLETE.md").exists()
    assert (project.dir / "state.md").exists() and (project.dir / "log.md").exists()
    assert (project.root / out["moved_to"] / "IMPLEMENTATION_COMPLETE.md").exists()


def test_backlog_shows_deferred_not_tasks(project):
    (project.dir / "backlog.json").write_text(json.dumps([{"name": "old drift", "status": "pending"}]))
    cli("task", "add", "a task")
    out = cli("backlog")
    assert [d["name"] for d in out["deferred"]] == ["old drift"]


# ---------------------------------------------------------------- import / reconcile / poc
def test_import_docs_link_status_reconcile(project, tmp_path):
    docs = tmp_path / "docs-in"
    docs.mkdir()
    (docs / "prd.md").write_text("# PRD\n")
    out = cli("import", "add", "mvp", "--from", str(docs))
    assert out["documents"] == [{"name": "prd.md", "type": "markdown"}]
    cli("spec", "Import video")
    cli("import", "link", "mvp", "001", "W99")
    st = cli("import", "status")["imports"][0]
    assert st["derived"] == ["001", "W99"] and st["status"] == "active"
    assert project.find("001").load_status()["source_import"] == "mvp"
    rec = cli("reconcile", "mvp")
    assert rec["mode"] == "reconcile" and rec["read"] == [".speky/imports/mvp/source/prd.md"]


def test_poc_import_registers_code_in_place(project, tmp_path):
    poc = tmp_path / "poc"
    poc.mkdir()
    out = cli("poc-import", "--path", str(poc))
    assert out["kind"] == "code" and out["code_paths"] == [str(poc.resolve())]


# ---------------------------------------------------------------- deps / order
def test_deps_order_foundation_cycles_export(project):
    for t in ("Login", "Profile", "Settings", "Core"):
        cli("spec", t, "--priority", "P1")
    cli("deps", "add", "002", "001")
    cli("deps", "add", "003", "002")
    cli("mark-foundation", "004")
    order = [r["id"] for r in cli("order")["order"]]
    assert order == ["004", "001", "002", "003"]
    cli("deps", "add", "001", "003")
    assert cli("fix-circular-deps")["cycles"]
    cli("reset-deps", "001")
    assert not cli("deps", "cycles")["cycles"]
    assert cli("sequence", "--export")["exported"] == ".speky/roadmap.md"


# ---------------------------------------------------------------- decisions / config
def test_decisions_and_config(project):
    cli("decide", "Use SQLite", "--type", "decision")
    cli("remember", "Python 3.12", "--topic", "tech")
    out = cli("decisions")
    assert "Use SQLite" in out["decisions"][0] and out["tech"][0].endswith("Python 3.12")
    cli("config", "set", "testing.coverage_threshold", "85")
    assert cli("config", "get", "testing.coverage_threshold")["value"] == 85


# ---------------------------------------------------------------- design
def test_design_assets_links_analysis_conflicts(project, tmp_path):
    img = tmp_path / "screen.png"
    img.write_bytes(b"\x89PNG")
    system = tmp_path / "design_system.md"
    system.write_text("# Design\nPrimary #112233\n")
    cli("spec", "Import video")
    cli("design", "init", "--tech", "react")
    cli("design", "add", str(system), "--type", "system")
    out = cli("design", "add", str(img), "--type", "hifi", "--for", "001")
    assert out["images"] == 1 and out["unlinked"] == []
    analysis = tmp_path / "a.md"
    analysis.write_text("Primary looks like #112244")
    cli("design", "analysis", "screen.png", "--from", str(analysis))
    c = cli("design", "conflict", "color", "primary", "--existing", "#112233", "--new", "#112244")
    assert cli("design", "status")["open_conflicts"][0]["id"] == c["id"]
    cli("design", "resolve", c["id"], "--value", "#112233", "--reason", "system wins")
    st = cli("design", "status")
    assert st["analyzed"] == 1 and st["open_conflicts"] == []
    packet = cli("context", "001")
    assert any(l["layer"] == "design" and l.get("analysis") for l in packet["layers"])


# ---------------------------------------------------------------- context / epics
def test_context_packets(project):
    cli("spec", "Import video")
    cli("story", "Paste link")
    cli("epic", "add", "Importing", "--spec", "001", "--stories", "F001")
    cli("phases", "add", "MVP", "--id", "mvp")
    pk = cli("context", "F001")
    layers = {l["layer"] for l in pk["layers"]}
    assert {"epic", "related", "item"} <= layers
    ph = cli("context", "--phase", "mvp")
    assert ph["phase"] == "mvp"


def test_epics_attach_detach_progress(project):
    cli("story", "A")
    cli("story", "B")
    cli("epic", "add", "Group", "--stories", "F001")
    cli("epic", "attach", "E001", "F002")
    project.find("F001").update_status(status="completed")
    shown = cli("epic", "show", "E001")
    assert shown["progress"] == {"total": 2, "completed": 1, "in_progress": 0, "pending": 1}
    cli("epic", "detach", "E001", "F002")
    assert "related_epic" not in project.find("F002").load_status()
    assert len(cli("epics")["epics"]) == 1


# ---------------------------------------------------------------- testing
def test_testing_detect_run_gaps_link_tdd_coverage(repo):
    (repo.root / "pyproject.toml").write_text("[project]\nname='x'\n")
    out = cli("test", "init")
    assert out["detected"]["runner"] == "pytest"
    cli("config", "set", "verify_command", "true")
    cli("config", "set", "testing.coverage_command", "echo 'TOTAL   10   2   80%'")
    run = cli("test", "run")
    assert run["passed"]
    spec(repo)
    assert cli("test", "gaps")["total"] == 2
    cli("test", "link", "001", "R1", "tests/test_import.py::test_valid_link")
    assert cli("test", "gaps")["total"] == 1
    assert cli("test", "green", "001", "R2", "--cmd", "true", expect=1)["error"]["code"] == "tdd_no_red"
    assert cli("test", "red", "001", "R2", "--cmd", "true", expect=1)["error"]["code"] == "tdd_not_red"
    cli("test", "red", "001", "R2", "--cmd", "false")
    cli("test", "green", "001", "R2", "--cmd", "true")
    assert cli("test", "gaps")["total"] == 1  # "true (red → green)" is not a test id...
    cov = cli("test", "coverage")
    assert cov["percent"] == 80.0 and cov["meets_threshold"] is True
    assert cli("test", "status")["tdd"][0]["requirements"]["R2"] == ["green", "red"]


# ---------------------------------------------------------------- removed
@pytest.mark.parametrize("name", ["renumber", "host", "sync"])
def test_removed_commands_say_what_replaces_them(project, name):
    err = cli(name, expect=1)["error"]
    assert err["code"] == "command_removed" and err["fix"]
