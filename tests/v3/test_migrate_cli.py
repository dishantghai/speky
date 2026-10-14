import json

from speky_core import migrate
from speky_core.items import Project

from .conftest import cli


def make_v2_project(root):
    sp = root / ".speky"
    (sp / "context").mkdir(parents=True)
    (sp / "context" / "context.json").write_text(json.dumps({"product": {"name": "X"}}))
    (sp / "config.yaml").write_text("ide: windsurf\n")
    s1 = sp / "specs" / "001-foundation"
    s1.mkdir(parents=True)
    (s1 / "spec.md").write_text("# Foundation\n\n## Overview\nx\n")
    (s1 / "status.json").write_text(json.dumps({"id": "001", "name": "foundation", "status": "completed",
                                                "drift_resolved": [{"type": "CODE_BEHIND", "action": "skipped",
                                                                    "description": "store missing"}]}))
    s2 = sp / "specs" / "002-browser"
    s2.mkdir()
    (s2 / "spec.md").write_text("# Browser\n\n## Overview\ny\n")
    (s2 / "status.json").write_text(json.dumps({"name": "browser", "status": "done", "dependencies": ["001", "009"]}))
    st = sp / "stories" / "B001-fix"
    st.mkdir(parents=True)
    (st / "story.md").write_text("# Fix\n")
    (st / "status.json").write_text(json.dumps({"id": "B001", "title": "Fix", "status": "ready"}))
    return sp


def test_migrate_dry_run_then_apply_is_idempotent(tmp_path, monkeypatch):
    sp = make_v2_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    docs_before = {p: p.read_text() for p in sp.rglob("*.md")}
    project = Project(tmp_path)
    report = migrate.plan(project)
    assert not report["done"]
    assert {i["issue"] for i in report["issues"]} >= {"unknown_dependency"}
    tasks = {j["task"]: j for j in report["judgement"]}
    assert tasks["check_suspect_completions"]["items"][0]["item"] == "001"
    assert "B001" in tasks["add_requirement_ids"]["items"]
    assert not (sp / "speky.yaml").exists()  # dry run writes nothing

    result = migrate.apply(project)
    assert result["done"] and not result["remaining"]
    assert (sp / "speky.yaml").exists() and (sp / "capabilities").is_dir()
    s2 = json.loads((sp / "specs" / "002-browser" / "status.json").read_text())
    assert s2["id"] == "002" and s2["status"] == "completed"
    s1 = json.loads((sp / "specs" / "001-foundation" / "status.json").read_text())
    assert "migrated_to_v3" not in s1  # already-valid status files are not rewritten
    assert {p: p.read_text() for p in sp.rglob("*.md") if p in docs_before} == docs_before
    assert migrate.plan(project)["done"]


def test_cli_json_envelope_and_errors(tmp_path, monkeypatch):
    (tmp_path / ".speky").mkdir()
    monkeypatch.chdir(tmp_path)
    out = cli("new", "spec", "Paste link")
    assert out["ok"] and out["item"] == "001"
    err = cli("check", "042", expect=1)
    assert err["ok"] is False and err["error"]["code"] == "item_not_found" and err["error"]["fix"]
    state = cli("state")
    assert state["items"][0]["id"] == "001"
    v = cli("verify", "001", expect=2)
    assert v["passed"] is False


def test_cli_outside_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    err = cli("next", expect=1)
    assert err["error"]["code"] == "not_initialized"


def test_cli_decide_remember_adr_term(tmp_path, monkeypatch):
    (tmp_path / ".speky").mkdir()
    monkeypatch.chdir(tmp_path)
    cli("new", "spec", "Paste link")
    assert cli("decide", "Use YouTube oEmbed", "--type", "decision", "--ref", "001")["id"] == "D1"
    assert cli("decide", "Public videos only", "--type", "assumption")["id"] == "D2"
    cli("remember", "Run pnpm test --run")
    a1 = cli("adr", "new", "Use SQLite")
    a2 = cli("adr", "new", "Use Postgres", "--supersedes", a1["id"])
    adrs = {a["id"]: a for a in cli("adr", "list")["adrs"]}
    assert adrs["0001"]["status"].startswith("Superseded by 0002") and adrs["0002"]["status"] == "Accepted"
    cli("term", "Recipe card", "One recipe shown as steps")
    assert cli("term", "Recipe card", "dup", expect=1)["error"]["code"] == "term_exists"
    story = cli("new", "story", "Thumbnail broken", "--type", "bug", "--discovered-from", "001")
    status = json.loads((tmp_path / story["path"] / "status.json").read_text())
    assert status["links"] == [{"type": "discovered-from", "target": "001"}]


def test_speky_entry_point_routes_v3_commands(tmp_path, monkeypatch, capsys):
    import sys
    import pytest
    import speky
    (tmp_path / ".speky").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["speky", "new", "spec", "Paste link", "--json"])
    with pytest.raises(SystemExit) as e:
        speky.main()
    assert e.value.code == 0
    assert json.loads(capsys.readouterr().out)["item"] == "001"


def test_setup_bootstraps_a_new_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = cli("setup", "claude-code")
    assert out["check"]["status"] == "current"
    assert (tmp_path / ".speky" / "speky.yaml").exists()
    assert (tmp_path / ".speky" / "capabilities").is_dir()
    assert cli("next")["action"] == "idle"


def test_migrate_done_acknowledges_judgement_tasks(tmp_path, monkeypatch):
    make_v2_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli("migrate", "--apply")
    tasks = [j["task"] for j in cli("migrate")["judgement"]]
    assert "check_suspect_completions" in tasks
    out = cli("migrate", "--done", "check_suspect_completions")
    assert "check_suspect_completions" not in out["remaining"]
    assert cli("migrate", "--done", "nope", expect=1)["error"]["code"] == "unknown_migration_task"


def test_parser_knows_every_command():
    from speky_core.cli import COMMANDS, _parser
    sub = next(a for a in _parser()._actions if a.dest == "cmd")
    assert set(sub.choices) == COMMANDS


def test_migrate_moves_v2_product_tech_validation_and_testing(tmp_path, monkeypatch):
    sp = make_v2_project(tmp_path)
    ctx = {"product": {"name": "Spayce", "description": "One app for browsing and notes",
                       "platforms": ["macOS", "Linux"]},
           "architecture": {"tech_stack": {"desktop": "Electron 30+", "ui": "React 18+"},
                            "decisions": ["pnpm workspaces monorepo"]},
           "decisions": ["Use WebContentsView (not BrowserView)"]}
    (sp / "context" / "context.json").write_text(json.dumps(ctx))
    (sp / "specs" / "001-foundation" / "validation_actions.json").write_text(json.dumps([
        {"item": "**Missing error types**: which package", "intent": "Fixed", "status": "applied"},
        {"item": "Retry policy undefined", "intent": "Fix", "status": "pending"}]))
    (sp / "testing").mkdir()
    (sp / "testing" / "config.yaml").write_text("coverage_threshold: 75\n")
    monkeypatch.chdir(tmp_path)
    plan = cli("migrate")
    steps = {s["step"] for s in plan["pending"]}
    assert {"import_v2_product", "import_v2_tech", "import_v2_validation", "import_v2_testing"} <= steps
    cli("migrate", "--apply")
    product = (sp / "knowledge" / "product.md").read_text()
    assert "Product: Spayce" in product and "Platforms: macOS, Linux" in product
    tech = (sp / "knowledge" / "tech.md").read_text()
    assert "Use WebContentsView" in tech and "Electron 30+" in tech and "always" in tech
    findings = json.loads((sp / "specs" / "001-foundation" / "findings.json").read_text())
    assert [f["status"] for f in findings] == ["accepted", "open"]
    assert "Missing error types" in findings[0]["text"] and "**" not in findings[0]["text"]
    assert cli("config", "get", "testing.coverage_threshold")["value"] == 75
    assert cli("migrate")["done"]
    from speky_core import protocol
    from speky_core.items import Project
    text = protocol.prime(Project(tmp_path))
    assert "Use WebContentsView" in text and "Product: Spayce" in text


def test_migrate_lists_unclassified_ui_items_until_they_say_their_design(tmp_path, monkeypatch):
    from speky_core.items import Project
    from .conftest import GOOD_SPEC
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".speky" / "context").mkdir(parents=True)
    (tmp_path / ".speky" / "context" / "design_system.md").write_text("# Design system\n")
    cli("migrate", "--apply")
    p = Project(tmp_path)
    item = p.create("story", "Sidebar paste", body=GOOD_SPEC.replace(
        "## Requirements", "Right-click in the sidebar menu shows Paste on the tab.\n\n## Requirements"))
    tasks = {j["task"]: j for j in cli("migrate")["judgement"]}
    assert tasks["classify_ui_items"]["items"] == [item.id]
    item.doc_path.write_text(item.read_doc().replace(
        "## Requirements", "## Design\nNo new design needed: the existing menu gains one entry.\n\n## Requirements"))
    assert "classify_ui_items" not in {j["task"] for j in cli("migrate")["judgement"]}
