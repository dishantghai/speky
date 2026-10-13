import json

from tests.parity.conftest import init_project, new_spec, run


def status_of(path):
    return json.loads((path / "status.json").read_text())


def test_init_creates_context_and_rules(project, fake_llm):
    init_project()
    speky_dir = project / ".speky"
    assert (speky_dir / "context" / "context.json").exists()
    assert (speky_dir / "context" / "product.md").exists()
    assert (speky_dir / "context" / "tech_decisions.md").exists()
    data = json.loads((speky_dir / "context" / "context.json").read_text())
    assert data["product"]["name"] == "Recipe Cards"
    assert (project / ".windsurfrules").exists()  # default IDE


def test_commands_need_init(project):
    assert run("status") == 1
    assert run("spec", "Login") == 1


def test_spec_plan_implement_complete(project, fake_llm):
    init_project()
    new_spec("Import video")
    spec_dir = project / ".speky" / "specs" / "001-import-video"
    assert (spec_dir / "spec.md").exists()
    assert status_of(spec_dir)["status"] == "draft"

    assert run("plan", "001") == 0
    assert (spec_dir / "plan.md").exists()
    assert status_of(spec_dir)["status"] == "ready"

    assert run("implement", "001") == 0
    assert status_of(spec_dir)["status"] == "in_progress"

    assert run("complete", "001") == 0
    assert status_of(spec_dir)["status"] == "completed"
    assert any("Analyze the drift" in call for call in fake_llm.calls)


def test_second_spec_gets_next_id(project):
    init_project()
    new_spec("Import video")
    new_spec("Recipe cards")
    names = sorted(p.name for p in (project / ".speky" / "specs").iterdir())
    assert names == ["001-import-video", "002-recipe-cards"]


def test_validate_spec_quick(project, fake_llm):
    init_project()
    new_spec("Import video")
    run("validate-spec", "001", "--quick")
    assert any("Analyze this feature specification for quality" in c for c in fake_llm.calls)


def test_story_lifecycle(project):
    init_project()
    assert run("story", "Fix login typo", "--type", "bug") == 0
    stories = list((project / ".speky" / "stories").iterdir())
    assert len(stories) == 1 and stories[0].name.startswith("B001-")
    assert (stories[0] / "story.md").exists()
    assert run("complete", "B001") == 0
    assert status_of(stories[0])["status"] == "completed"


def test_status_and_read_only_commands(project):
    init_project()
    new_spec("Import video")
    for argv in (["status"], ["epics"], ["sequence"], ["phases", "list"], ["import-status"],
                 ["config"], ["config", "--list-ides"], ["host", "status"], ["review"],
                 ["cleanup", "--dry-run"], ["renumber", "--dry-run"]):
        assert run(*argv) == 0, argv
