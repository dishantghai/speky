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
    assert s2["id"] == "002" and s2["status"] == "completed" and s2["kind"] == "spec"
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
