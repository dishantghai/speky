"""Parity tests for the v2 commands beyond the core loop (PLAN.md §2.8)."""
import json
import subprocess

import pytest

from tests.parity.conftest import init_project, new_spec, run


@pytest.fixture
def ready_project(project):
    init_project()
    new_spec("Import video")
    new_spec("Recipe cards")
    return project


def speky_path(project, *parts):
    return project.joinpath(".speky", *parts)


def test_epic_create_show_add_remove(ready_project):
    p = ready_project
    assert run("story", "Paste link", "--type", "feature") == 0
    assert run("story", "Show steps", "--type", "feature") == 0
    assert run("epic", "Importing", "--spec", "001", "--stories", "F001") == 0
    epics = list(speky_path(p, "epics").iterdir())
    assert [e.name.split("-")[0] for e in epics] == ["E001"]
    assert run("epic", "E001") == 0
    assert run("epic", "E001", "--add", "F002") == 0
    assert run("epic", "E001", "--remove", "F002") == 0
    assert run("epics") == 0


def test_story_linked_to_spec_and_epic(ready_project):
    p = ready_project
    run("epic", "Importing", "--spec", "001")
    assert run("story", "Paste link", "--epic", "E001", "--spec", "001") == 0
    story = next(speky_path(p, "stories").iterdir())
    status = json.loads((story / "status.json").read_text())
    assert status.get("related_epic") == "E001"
    assert "001" in json.dumps(status.get("related_specs", []))


def test_adopt_ide_created_story_and_spec(ready_project):
    p = ready_project
    story = speky_path(p, "stories", "F009-hand-made")
    story.mkdir(parents=True)
    (story / "story.md").write_text("# Hand made\n\n## Description\nx\n\n## Acceptance Criteria\n- [ ] y\n")
    assert run("adopt", "F009", "--skip-validation") == 0
    assert (story / "status.json").exists()

    spec = speky_path(p, "specs", "005-hand-spec")
    spec.mkdir()
    (spec / "spec.md").write_text("# Hand spec\n\n## Overview\nx\n")
    assert run("adopt", "005", "--skip-validation") == 0
    assert (spec / "status.json").exists()


def test_validate_story_quick(ready_project):
    run("story", "Fix login typo", "--type", "bug")
    assert run("validate-story", "B001", "--quick") in (0, 1)  # verdict, not a crash


def test_dependency_commands(ready_project):
    assert run("mark-foundation", "001") == 0
    assert run("reset-deps", "002") == 0
    assert run("infer-deps", "002") == 0
    assert run("fix-circular-deps") == 0
    assert run("sequence", "--export") == 0
    assert speky_path(ready_project, "roadmap.md").exists()


def test_phases_lifecycle(ready_project):
    assert run("phases", "create", "phase-1") == 0
    assert speky_path(ready_project, "phases", "phase-1").is_dir()
    for argv in (["phases", "show", "phase-1"], ["phases", "status"], ["phases", "list"],
                 ["phases", "start", "phase-1"], ["context"]):
        assert run(*argv) == 0, argv
    # v3: the phase guide is the context packet, not a separate command
    assert run("phases", "guide", "phase-1") == 1


def test_decisions_and_backlog(ready_project):
    assert run("decisions") == 0
    assert run("backlog") == 0


def test_sync_writes_codebase_context(ready_project):
    (ready_project / "app.py").write_text("print('hi')\n")
    assert run("sync") == 0
    assert speky_path(ready_project, "context", "codebase.md").exists()


def test_import_docs_into_specs(ready_project):
    src = speky_path(ready_project, "imports", "mvp", "source")
    src.mkdir(parents=True, exist_ok=True)
    (src / "prd.md").write_text("# PRD\n\nUsers paste a link and get a recipe card.\n")
    assert run("import", "--phase", "mvp", "--no-review") in (0, 1)
    assert run("import-status") == 0


def test_poc_import_writes_agent_task(ready_project, tmp_path):
    poc = tmp_path / "poc"
    poc.mkdir()
    (poc / "main.py").write_text("print('poc')\n")
    run("poc-import", "--path", str(poc))
    tasks = list(speky_path(ready_project, "imports", "poc_import").glob("poc-*/task.md"))
    assert len(tasks) == 1


def test_commit_completed_spec(ready_project):
    p = ready_project
    subprocess.run(["git", "init", "-q"], cwd=p, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=p, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=p, check=True)
    (p / "app.py").write_text("print('feature')\n")
    run("implement", "001")
    run("complete", "001")
    assert run("commit", "001", answers={"Edit commit message": "no"}) == 0
    log = subprocess.run(["git", "log", "--oneline"], cwd=p, capture_output=True, text=True).stdout
    assert log.strip()


def test_config_ides_and_model(ready_project):
    assert run("config", "--ides", "add", "cursor") == 0
    assert (ready_project / ".cursorrules").exists()
    assert run("config", "--ides", "remove", "cursor") == 0
    assert run("config", "--providers") == 0


def test_design_and_testing_modules(ready_project):
    assert run("design", "init", "--tech", "react") == 0
    assert speky_path(ready_project, "design").is_dir()
    assert run("design", "status") == 0
    assert run("test", "status") in (0, 1)


def test_init_from_project(project):
    (project / "README.md").write_text("# Recipe Cards\n\nTurns cooking videos into recipe cards.\n")
    (project / "package.json").write_text(json.dumps({"dependencies": {"react": "18", "express": "4"}}))
    assert run("init", "--from-project") == 0
    assert speky_path(project, "context", "context.json").exists()


def test_host_mode_guide_and_status(project):
    assert run("host", "guide") == 0
    assert run("host", "status") == 0


def test_sequence_with_spec_missing_name(ready_project):
    """Real projects have status.json files with `title` but no `name` (v2 crashed on them)."""
    status = speky_path(ready_project, "specs", "002-recipe-cards", "status.json")
    data = json.loads(status.read_text())
    data.pop("name", None)
    data["title"] = "Recipe cards"
    status.write_text(json.dumps(data))
    assert run("sequence") == 0
    assert run("sequence", "--export") == 0
