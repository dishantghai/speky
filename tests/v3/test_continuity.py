"""Milestone 2: continuity — phases, tasks, handoff/checkpoint, knowledge, owner actions, refs,
done checks, ADRs in the project's own folder, AGENTS.md redirection and the PreCompact hook."""
import json

import pytest

from speky_core import continuity, harness, journal, knowledge, phases, protocol, refs, validation, verification
from speky_core.errors import SpekyError
from speky_core.owner import OwnerActions
from speky_core.tasks import Tasks

from .conftest import GOOD_SPEC, cli, git, spec


# ---------------------------------------------------------------- phases (v2 manifests)
def test_phases_use_the_v2_manifest_format(project):
    """Older SPEKY versions read phases/<id>/manifest.yaml and phases/roadmap.yaml; keep that shape."""
    import yaml
    phases.add(project, "Workbench", "phase-1a")
    phases.add_deliverable(project, "phase-1a", "Walkthrough test passes", run="true")
    phases.add_deliverable(project, "phase-1a", "Owner reaches the fix in 15 minutes")
    phases.set_status(project, "phase-1a", "doing")
    data = yaml.safe_load((project.dir / "phases" / "phase-1a" / "manifest.yaml").read_text())
    assert data["name"] == "Workbench" and data["status"] == "in_progress"
    assert [d["id"] for d in data["deliverables"]] == ["D1", "D2"]
    roadmap = yaml.safe_load((project.dir / "phases" / "roadmap.yaml").read_text())
    assert roadmap["current_phase"] == "phase-1a"


def test_phase_gate_runs_commands_and_needs_evidence_for_manual(project):
    phases.add(project, "P", "p1")
    phases.add_deliverable(project, "p1", "tests pass", run="true")
    phases.add_deliverable(project, "p1", "owner signs off")
    result = phases.check(project, "p1")
    assert [d["verified"] for d in result["deliverables"]] == [True, False] and not result["passed"]
    with pytest.raises(SpekyError):
        phases.verify_deliverable(project, "p1", "D2", "")
    phases.verify_deliverable(project, "p1", "D2", "owner approved in chat")
    assert phases.check(project, "p1")["passed"]
    assert cli("phases", "complete", "p1")["status"] == "done"


def test_phase_complete_refuses_open_tasks(project):
    phases.add(project, "P", "p1")
    Tasks(project).add("finish docs", phase="p1")
    err = cli("phases", "complete", "p1", expect=1)
    assert err["error"]["code"] == "phase_gate_not_met"
    out = cli("phases", "complete", "p1", "--force", "docs moved to next phase")
    assert out["status"] == "done"
    assert "without its gate" in journal.decisions(project)[0]


# ---------------------------------------------------------------- tasks (backlog store)
def test_tasks_live_in_backlog_and_v2_backlog_ignores_them(project):
    (project.dir / "backlog.json").write_text(json.dumps(
        [{"name": "deferred thing", "status": "pending", "type": "CODE_BEHIND"}]))
    phases.add(project, "P", "p1")
    phases.set_status(project, "p1", "doing")
    t = Tasks(project).add("Wire SSE", refs=["adr:0021"])
    sub = Tasks(project).add("Add retry", parent=t["id"])
    assert t["phase"] == "p1" and sub["phase"] == "p1"
    items = json.loads((project.dir / "backlog.json").read_text())
    assert len(items) == 3 and items[0]["status"] == "pending"
    # older SPEKY versions review only `status: pending` entries; tasks never use that status
    assert [i["name"] for i in items if i.get("status") == "pending"] == ["deferred thing"]
    assert [d["name"] for d in cli("backlog")["deferred"]] == ["deferred thing"]
    view = (project.dir / "tasks.md").read_text()
    assert "- [ ] W1 Wire SSE (refs: adr:0021)" in view and "  - [ ] W2 Add retry" in view


def test_task_lifecycle_and_promote(project):
    t = Tasks(project).add("Fix overlay paste")
    Tasks(project).set_status(t["id"], "doing")
    out = Tasks(project).promote(t["id"], "story", "bug")
    assert out["item"].startswith("B")
    item = project.find(out["item"])
    assert item.load_status()["from_task"] == t["id"]
    assert Tasks(project).get(t["id"])["promoted_to"] == out["item"]


def test_next_falls_back_to_tasks_then_phase_gate(project):
    phases.add(project, "P", "p1")
    phases.add_deliverable(project, "p1", "owner signs off")
    phases.set_status(project, "p1", "doing")
    t = Tasks(project).add("Write docs")
    nxt = protocol.next_action(project)
    assert nxt["action"] == "task" and nxt["task"] == t["id"]
    Tasks(project).set_status(t["id"], "done")
    assert protocol.next_action(project)["action"] == "gate"
    phases.verify_deliverable(project, "p1", "D1", "ok")
    assert protocol.next_action(project)["action"] == "phase"


# ---------------------------------------------------------------- handoff / checkpoint
def test_handoff_writes_log_state_and_records_tests(repo):
    from speky_core import config
    config.save(repo.root, {**config.DEFAULTS, "verify_command": "true"})
    notes = repo.root / "notes.md"
    notes.write_text("## Summary\nPhase 0 done; workbench next.\n\n## Done\n- profiled the kernel\n\n"
                     "## Learned\n- deepcopy was the cost\n\n## Next\n1. Layers editor\n2. Cassettes\n\n"
                     "## Watch out for\n- kill stray servers on 7431\n")
    out = cli("handoff", "--file", str(notes))
    assert out["tests"]["passed"] and out["committed"] is None  # conservative profile
    log = (repo.dir / "log.md").read_text()
    assert "**Done**\n- profiled the kernel" in log and "tests PASS" in log
    state = continuity.read_state(repo)
    assert state["summary"] == "Phase 0 done; workbench next."
    assert state["next"] == ["Layers editor", "Cassettes"]
    assert state["watch"] == ["kill stray servers on 7431"]
    # a second, partial handoff keeps the earlier narrative
    cli("handoff", "--done", "small fix", "--no-tests")
    assert continuity.read_state(repo)["next"] == ["Layers editor", "Cassettes"]
    assert (repo.dir / "log.md").read_text().count("\n## ") == 2


def test_handoff_commits_for_team_maintainer(repo):
    from speky_core import config
    config.save(repo.root, {**config.DEFAULTS, "agent_profile": "team-maintainer"})
    out = cli("handoff", "--done", "x", "--title", "Phase 0 gate", "--no-tests")
    assert out["committed"] == "Handoff: Phase 0 gate"
    assert "Handoff: Phase 0 gate" in git(repo.root, "log", "--oneline", "-1")


def test_prime_picks_up_after_handoff_and_reports_drift(repo):
    cli("handoff", "--summary", "Where we are", "--next", "Do the thing", "--no-tests", "--title", "T1")
    (repo.root / "new.py").write_text("x = 1\n")
    git(repo.root, "add", "new.py")
    git(repo.root, "commit", "-q", "-m", "work after handoff")
    (repo.root / "dirty.py").write_text("y = 2\n")
    text = protocol.prime(repo)
    assert '"T1"' in text and "Where we are" in text and "1. Do the thing" in text
    assert "1 commit(s) since the handoff" in text and "dirty.py" in text
    assert "trust git" in text


def test_auto_checkpoint_is_reported_after_compaction(repo):
    cli("handoff", "--summary", "s", "--no-tests")
    cli("checkpoint", "--auto")
    assert "Context was compacted" in protocol.prime(repo)


def test_checkpoint_auto_outside_a_project_is_silent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli("checkpoint", "--auto")["skipped"]


# ---------------------------------------------------------------- knowledge / owner
def test_knowledge_topics_always_and_read_when(project):
    knowledge.remember(project, "Owner decides names and licence", "owner")
    knowledge.remember(project, "Overhead 0.56 ms/step", "kernel", read_when="touching the kernel")
    knowledge.remember(project, "Overhead 1.8 ms/step earlier", "kernel")
    topics = {t["topic"]: t for t in knowledge.topics(project)}
    assert topics["owner"]["always"] and not topics["kernel"]["always"]
    assert topics["kernel"]["entries"] == 2 and topics["kernel"]["newest"].endswith("1.8 ms/step earlier")
    text = protocol.prime(project)
    assert "Owner decides names and licence" in text
    assert "`.speky/knowledge/kernel.md` (2 entries) — read when touching the kernel" in text
    assert "0.56 ms" not in text  # not loaded, only indexed


def test_knowledge_promote_to_adr(project):
    knowledge.remember(project, "Plans pinned in system text", "plans")
    out = knowledge.promote(project, "plans", "Plans are core")
    assert (project.root / out["adr"]["file"]).exists()
    assert "Promoted to ADR" in (project.dir / "knowledge" / "plans.md").read_text()


def test_owner_actions_roundtrip_with_hand_edits(project):
    oa = OwnerActions(project)
    o1 = oa.add("Reserve the PyPI name", "Do soon")
    oa.add("Pick a real backend", "Decide or provide")
    path = project.dir / "owner.md"
    # the owner ticks one box and writes a note under the other, by hand
    text = path.read_text().replace("- [ ] O1 Reserve", "- [x] O1 Reserve")
    text = text.replace("- [ ] O2 Pick a real backend", "- [ ] O2 Pick a real backend\n  - Notes: use the claims API")
    text += "\n- [ ] Book the trademark search\n"
    path.write_text(text)
    oa = OwnerActions(project)  # reading numbers the hand-added item
    assert "- [ ] O3 Book the trademark search" in path.read_text()
    open_ = oa.open_items()
    assert [o["id"] for o in open_] == ["O2", "O3"]
    assert open_[0]["notes"] == ["- Notes: use the claims API"]
    assert "Owner notes to act on: O2" in protocol.prime(project)


# ---------------------------------------------------------------- refs, done checks, ADRs
def test_refs_check_against_configured_patterns(project):
    from speky_core import config
    (project.root / "docs" / "adr").mkdir(parents=True)
    (project.root / "docs" / "adr" / "0021-clean.md").write_text("# ADR-0021: Clean\n")
    config.save(project.root, {**config.DEFAULTS, "refs": {"adr": {"glob": "docs/adr/{id}-*.md"}}})
    Tasks(project).add("Follow the layers", refs=["adr:0021", "adr:0099"])
    out = refs.scan(project)
    assert [b["ref"] for b in out["broken"]] == ["adr:0099"] and not out["valid"]


def test_done_checks_by_label(repo):
    from speky_core import config
    config.save(repo.root, {**config.DEFAULTS, "done_checks": {"ui": [
        {"name": "review", "file": "docs/reviews/*{id}*"},
        {"name": "a11y", "manual": "Keyboard path and contrast checked"}]}})
    item = spec(repo)
    item.update_status(labels=["ui"])
    verification.start(repo, item)
    for r in ("R1", "R2"):
        verification.record_evidence(repo, item, r, "met", "t")
    result = verification.verify(repo, item)
    assert not result["passed"] and any("review" in m for m in result["missing"])
    (repo.root / "docs" / "reviews").mkdir(parents=True)
    (repo.root / "docs" / "reviews" / f"2026-{item.id}-run-view.md").write_text("PASS")
    verification.record_evidence(repo, item, "check:a11y", "met", "tabbed through, AA contrast")
    assert verification.verify(repo, item)["passed"]


def test_adrs_in_project_folder_with_project_template(project):
    from speky_core import config
    adr = project.root / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "template.md").write_text("# ADR-NNNN: Title\n\n- **Status:** Proposed\n- **Date:** YYYY-MM-DD\n\n"
                                     "## Context\nWhat forces.\n\n## Decision\nWhat.\n\n## Consequences\nSo.\n")
    (adr / "0022-prano-vs-apps.md").write_text("# ADR-0022: Prano vs apps\n\n- **Status:** Accepted (owner)\n")
    config.save(project.root, {**config.DEFAULTS, "paths": {"adr_dir": "docs/adr"}})
    out = journal.adr_new(project, "Use SSE", context="Polling is slow")
    assert out["id"] == "0023" and out["file"] == "docs/adr/0023-use-sse.md"
    text = (project.root / out["file"]).read_text()
    assert text.startswith("# ADR-0023: Use SSE") and "**Status:** Accepted" in text and "Polling is slow" in text
    listed = {a["id"]: a for a in journal.adr_list(project)}
    assert listed["0022"]["status"].startswith("Accepted") and listed["0022"]["title"] == "Prano vs apps"


# ---------------------------------------------------------------- harness
def test_claude_md_that_imports_agents_md_gets_the_block_in_agents_md(project):
    root = project.root
    (root / "CLAUDE.md").write_text("@AGENTS.md\n")
    (root / "AGENTS.md").write_text("# How to work here\n\nRules.\n")
    out = harness.setup(project, "claude-code")
    assert out["check"]["status"] == "current"
    assert (root / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    agents = (root / "AGENTS.md").read_text()
    assert agents.startswith("# How to work here") and "profile:full" in agents
    settings = json.loads((root / ".claude" / "settings.json").read_text())
    assert any("speky checkpoint --auto" in h["command"]
               for e in settings["hooks"]["PreCompact"] for h in e["hooks"])
    harness.remove(project, "claude-code")
    assert "BEGIN SPEKY" not in (root / "AGENTS.md").read_text()
    assert "hooks" not in json.loads((root / ".claude" / "settings.json").read_text())


def test_existing_claude_md_block_moves_to_agents_md(project):
    root = project.root
    (root / "AGENTS.md").write_text("Rules.\n")
    (root / "CLAUDE.md").write_text("@AGENTS.md\n\n" + harness._block_text("minimal"))
    harness.setup(project, "claude-code")
    assert (root / "CLAUDE.md").read_text().strip() == "@AGENTS.md"
    assert "BEGIN SPEKY v:3" in (root / "AGENTS.md").read_text()


def test_removing_claude_code_keeps_agents_md_block_used_by_codex(project):
    root = project.root
    (root / "CLAUDE.md").write_text("@AGENTS.md\n")
    harness.setup(project, "claude-code")
    harness.setup(project, "codex")
    harness.remove(project, "claude-code")
    assert "BEGIN SPEKY v:3" in (root / "AGENTS.md").read_text()


def test_verify_a_task_runs_tests_and_marks_it_done(project):
    from speky_core import config
    cfg = project.config
    cfg["verify_command"] = "python -c 'raise SystemExit(0)'"
    config.save(project.root, cfg)
    Tasks(project).add("Small fix")
    out = cli("verify", "W1")
    assert out["passed"] and out["status"] == "done"
    Tasks(project).add("Another")
    cfg["verify_command"] = "python -c 'raise SystemExit(3)'"
    config.save(project.root, cfg)
    out = cli("task", "done", "W2", "--verify", expect=1)
    assert out["error"]["code"] == "task_not_verified"
    assert Tasks(project).get("W2")["status"] == "todo"


def test_owner_actions_nested_items_and_notes_with_blank_lines(project):
    (project.dir / "owner.md").write_text(
        "# Owner\n\n## Do soon\n\n- [ ] **Reserve names**\n  - [ ] PyPI\n  - [ ] npm\n"
        "- [ ] The test\n  - Notes:\n    1. hesitated here\n\n    2. and here\n- [ ] Last\n")
    OwnerActions(project)
    assert (project.dir / "owner.md").read_text().count("] O") == 5
    items = {i["id"]: i for i in OwnerActions(project).items()}
    assert items["O2"]["parent"] == "O1" and items["O3"]["parent"] == "O1"
    assert items["O4"]["notes"] == ["- Notes:", "1. hesitated here", "2. and here"]
    OwnerActions(project).set_done("O2", True, "reserved")
    OwnerActions(project).set_done("O4", True, "done")
    text = (project.dir / "owner.md").read_text()
    assert "  - [x] O2 PyPI\n    - reserved" in text
    assert "    2. and here\n  - done" in text and text.endswith("- [ ] O5 Last\n")


def test_phase_order(project):
    for pid in ("phase-1a", "track-x", "phase-0"):
        phases.add(project, pid, pid)
    assert [p.id for p in phases.all_phases(project)] == ["phase-0", "phase-1a", "track-x"]
    out = cli("phases", "order", "phase-0", "track-x")
    assert out["order"] == ["phase-0", "track-x", "phase-1a"]
    phases.add(project, "Later", "a-later")
    assert [p.id for p in phases.all_phases(project)][-1] == "a-later"


def test_playbooks_cited_refs_and_design_system_in_next_and_context(project):
    from speky_core import config
    (project.root / "docs" / "ux" / "screens").mkdir(parents=True)
    (project.root / "docs" / "ux" / "screens" / "README.md").write_text("| `RV-E2-held` | held |\n")
    (project.root / "docs" / "ux" / "DESIGN.md").write_text("# Design\n")
    (project.root / "docs" / "ux" / "stitch.md").write_text("# Stitch\n")
    cfg = project.config
    cfg["refs"] = {"screen": {"file": "docs/ux/screens/README.md", "contains": "`{id}`"}}
    cfg["paths"] = {"design_system": "docs/ux/DESIGN.md"}
    cfg["playbooks"] = {"ui": {"skill": "screen-design-narratives", "read": ["docs/ux/stitch.md"],
                               "note": "Review before showing the owner."}}
    config.save(project.root, cfg)
    body = GOOD_SPEC.replace("## Requirements", "Matches screen:RV-E2-held.\n\n## Requirements")
    item = spec(project, body=body)
    item.update_status(labels=["ui"])
    nxt = protocol.next_action(project)
    assert "screen-design-narratives" in nxt["instruction"] and nxt["also_skills"] == ["screen-design-narratives"]
    assert "docs/ux/stitch.md" in nxt["read"]
    packet = cli("context", item.id)
    reads = {l.get("read") for l in packet["layers"]}
    assert {"docs/ux/DESIGN.md", "docs/ux/stitch.md", "docs/ux/screens/README.md"} <= reads
    Tasks(project).add("Design the Layers editor", labels=["ui"])
    item.update_status(status="archived")
    assert "screen-design-narratives" in protocol.next_action(project)["instruction"]
    assert "[ui]" in (project.dir / "tasks.md").read_text()


def test_extra_skills_installed_for_each_harness(project, tmp_path_factory, monkeypatch):
    from speky_core import config
    src = tmp_path_factory.mktemp("skills") / "screen-design-narratives"
    (src / "references").mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: screen-design-narratives\ndescription: d\n---\nbody\n")
    (src / "references" / "stitch-guide.md").write_text("guide\n")
    monkeypatch.setattr(harness, "USER_SKILL_DIRS", {"claude-code": tmp_path_factory.mktemp("noskills")})
    cfg = project.config
    cfg["extra_skills"] = [str(src)]
    config.save(project.root, cfg)
    harness.setup(project, "codex")
    target = project.root / ".agents" / "skills" / "screen-design-narratives"
    assert (target / "references" / "stitch-guide.md").exists()
    assert harness.check(project, "codex")["status"] == "current"
    (src / "SKILL.md").write_text((src / "SKILL.md").read_text() + "more\n")
    assert harness.check(project, "codex")["files"][".agents/skills/screen-design-narratives/SKILL.md"] == "stale"
    monkeypatch.setattr(harness, "USER_SKILL_DIRS", {"claude-code": src.parent})
    out = harness.setup(project, "claude-code")
    assert any("already available to claude-code" in c for c in out["changes"])
    assert not (project.root / ".claude" / "skills" / "screen-design-narratives").exists()
    harness.remove(project, "codex")
    assert not target.exists()


def test_checkpoint_and_test_runs_are_git_ignored(repo):
    continuity.checkpoint(repo, run_tests=False)
    assert (repo.dir / ".gitignore").read_text().splitlines()[1:] == ["checkpoint.json", "testing/runs.json"]
    assert ".speky/checkpoint.json" not in git(repo.root, "status", "--porcelain", "--untracked-files=all")


def test_handoff_file_bullets_continue_on_wrapped_lines():
    notes = continuity.parse_handoff_file("## Watch out for\n- Kill stray `prano demo`\n  servers on 7431.\n- Second\n")
    assert notes["watch"] == ["Kill stray `prano demo` servers on 7431.", "Second"]


def test_owner_item_text_wraps_without_becoming_notes(project):
    (project.dir / "owner.md").write_text("## Do\n\n- [ ] **Trademark search** for PRANO\n  in classes 9 and 42.\n"
                                          "- [ ] Test it\n  - Notes: slow start\n")
    items = OwnerActions(project).items()
    assert items[0]["text"] == "**Trademark search** for PRANO in classes 9 and 42." and items[0]["notes"] == []
    assert items[1]["notes"] == ["- Notes: slow start"]


def test_always_knowledge_over_budget_names_the_files_to_read(project):
    from speky_core import config
    for i in range(6):
        journal.remember(project, f"owner preference {i} " + "x" * 300, "owner", True)
        journal.remember(project, f"env fact {i} " + "y" * 300, "environment", True)
    cfg = project.config
    cfg["prime_knowledge_chars"] = 1500
    config.save(project.root, cfg)
    text = protocol.prime(project)
    assert text.index("owner preference 5") < text.index("env fact") if "env fact" in text else True
    assert "`.speky/knowledge/owner.md` (2 more)" in text and "`.speky/knowledge/environment.md` (6 more)" in text


def test_handoff_commit_is_not_reported_as_work_since(repo):
    cfg = repo.config
    cfg["agent_profile"] = "team-maintainer"
    from speky_core import config
    config.save(repo.root, cfg)
    git(repo.root, "add", "-A")
    git(repo.root, "commit", "-q", "-m", "setup")
    out = continuity.handoff(repo, summary="s", run_tests=False)
    assert out["committed"]
    assert "since the handoff" not in protocol.prime(repo)


def test_labelled_task_must_meet_its_done_checks(project):
    from speky_core import config
    cfg = project.config
    cfg["verify_command"] = "true"
    cfg["done_checks"] = {"ui": [{"name": "review", "manual": "a recorded UX review"}],
                          "all": [{"name": "changelog", "file": "CHANGES-{id}.md"}]}
    config.save(project.root, cfg)
    Tasks(project).add("Layers editor", labels=["ui"])
    out = cli("task", "done", "W1", "--verify", expect=1)
    assert out["error"]["code"] == "task_not_verified"
    assert cli("verify", "W1", expect=2)["missing"] == ["done check review (ui): a recorded UX review"]  # `all` not applied
    cli("evidence", "W1", "check:review", "--status", "met", "--evidence", "docs/ux/reviews/x.md PASS")
    assert cli("task", "done", "W1", "--verify")["status"] == "done"


def test_ui_changes_must_cite_an_approved_design_in_the_standard_layout(project, tmp_path):
    from speky_core import uxdesign
    out = cli("story", "Layers editor", "--labels", "ui")
    item = project.find(out["item"])
    assert "## Design" in item.read_doc() and "To be designed" in item.read_doc()
    item.doc_path.write_text(GOOD_SPEC.replace("## Requirements", "## Design\nTo be designed\n\n## Requirements"))
    nxt = protocol.next_action(project)
    assert nxt["action"] == "design" and nxt["skill"] == "speky-design"
    assert ".speky/design/system.md" in nxt["instruction"]
    assert any("screen approve" in c for c in nxt["commands"])
    rubric = {r["rubric"]: r["passed"] for r in validation.run_rubric(project, item, project.config)}
    assert rubric["design"] is False and rubric["design_system"] is False
    # the agent designs it: system document + a screen in the standard layout, cited by `--for`
    (project.dir / "design").mkdir()
    (project.dir / "design" / "system.md").write_text("# Design system\n")
    png = tmp_path / "main.png"
    png.write_bytes(b"png")
    cli("design", "screen", "add", "layers-editor-main", str(png), "--for", item.id, "--state", "default")
    doc = item.read_doc()
    assert "- screen:layers-editor-main" in doc and "To be designed" not in doc
    st = uxdesign.state(project, item)
    assert st["cited"] == [".speky/design/screens/layers-editor-main"] and st["unapproved"] == ["layers-editor-main"]
    nxt = protocol.next_action(project)
    assert nxt["action"] == "design" and "not approved" in nxt["why"]
    cli("design", "screen", "approve", "layers-editor-main", "--by", "owner")
    assert protocol.next_action(project)["action"] == "validate"
    assert "approved by owner" in " ".join(journal.decisions(project))
    cli("check", item.id)
    item.update_status(status="in_progress")
    nxt = protocol.next_action(project)
    assert ".speky/design/system.md" in nxt["read"] and ".speky/design/screens/layers-editor-main" in nxt["read"]
    catalogue = (project.dir / "design" / "screens.md").read_text()
    assert "`layers-editor-main`" in catalogue and "approved" in catalogue
    # a new iteration supersedes; citing the old one is then a broken reference
    cli("design", "screen", "add", "layers-editor-main-v2", str(png))
    out = cli("design", "screen", "add", "layers-editor-main", str(png), expect=1)
    assert out["error"]["code"] == "screen_approved"
    cli("design", "screen", "supersede", "layers-editor-main", "--by", "layers-editor-main-v2")
    assert "superseded" in uxdesign.state(project, item)["broken"][0]


def test_design_files_outside_the_layout_and_tool_links_are_flagged(project):
    from speky_core import uxdesign
    (project.dir / "design").mkdir()
    (project.dir / "design" / "system.md").write_text("# DS\n")
    (project.root / "mocks").mkdir()
    (project.root / "mocks" / "a.png").write_bytes(b"png")
    item = spec(project, body=GOOD_SPEC.replace("## Requirements",
                "## Design\n- `mocks/a.png`\n\n## Requirements"))
    rubric = {r["rubric"]: r["passed"] for r in validation.run_rubric(project, item, project.config)}
    assert rubric["design_location"] is False
    item.doc_path.write_text(GOOD_SPEC.replace("## Requirements",
                             "## Design\n- [Stitch](https://stitch.withgoogle.com/p/1)\n\n## Requirements"))
    rubric = {r["rubric"]: r["passed"] for r in validation.run_rubric(project, item, project.config)}
    assert rubric["design_in_repo"] is False and not uxdesign.satisfied(uxdesign.state(project, item))


def test_no_new_design_needed_is_a_valid_answer_and_design_decisions_is_not_a_design_section(project):
    from speky_core import uxdesign
    item = spec(project, body=GOOD_SPEC.replace("## Requirements", "## Design decisions\nUse SQLite.\n\n## Requirements"))
    assert not uxdesign.is_ui(project, item)
    item.update_status(labels=["ui"])
    item.doc_path.write_text(GOOD_SPEC.replace(
        "## Requirements", "## Design\nNo new design needed: the button reuses the existing toolbar.\n\n## Requirements"))
    assert uxdesign.satisfied(uxdesign.state(project, item))


def test_promote_carries_labels_and_refs_and_unlabelled_ui_text_is_flagged(project):
    from speky_core import config
    cfg = project.config
    cfg["playbooks"] = {"ui": {"skill": "screen-design-narratives"}}
    config.save(project.root, cfg)
    Tasks(project).add("Next screens", labels=["ui"], refs=["adr:0021"])
    out = cli("task", "promote", "W1", "--title", "Layers editor")
    item = project.find(out["item"])
    assert out["carried"] == ["labels", "refs"] and item.load_status()["labels"] == ["ui"]
    doc = item.read_doc()
    assert "## Design" in doc and "- adr:0021" in doc and item.info()["title"] == "Layers editor"
    assert cli("task", "show", "W1")["promoted_to"] == item.id
    # a change written without the label, in a UI project
    plain = spec(project, body=GOOD_SPEC.replace("## Requirements",
                                                 "The editor panel lists layers; click a tab to switch views.\n\n## Requirements"))
    rubric = {r["rubric"]: r for r in validation.run_rubric(project, plain, project.config)}
    assert not rubric["ui_label"]["passed"] and "panel" in rubric["ui_label"]["evidence"]
    assert "label it" in protocol.action_for(project, spec(project, "Empty", body=None))["instruction"]


def test_layout_defaults_overrides_and_check(project):
    from speky_core import config, layout
    rows = {r["kind"]: r for r in cli("layout")["layout"]}
    assert rows["design_screens"]["path"] == ".speky/design/screens/<screen-id>/" and not rows["adr_dir"]["overridden"]
    folder = project.root / "project_ops" / "HIFI_UI_DESIGN_SCREENS"
    folder.mkdir(parents=True)
    for n in ("Browser Tab Bar", "Settings Screen", "Space Card Design"):
        (folder / f"{n}.png").write_bytes(b"png")
    (project.root / "docs" / "decisions").mkdir(parents=True)
    for n in ("0001-a.md", "0002-b.md"):
        (project.root / "docs" / "decisions" / n).write_text("# ADR\n\nStatus: Accepted\n")
    (project.root / "project_ops" / "TECH_RESEARCH").mkdir()
    for n in ("a.md", "b.md"):
        (project.root / "project_ops" / "TECH_RESEARCH" / n).write_text("notes\n")
    problems = {p["kind"]: p["path"] for p in cli("layout", "--check")["problems"]}
    assert problems == {"design_screens": "project_ops/HIFI_UI_DESIGN_SCREENS", "adr_dir": "docs/decisions",
                        "research": "project_ops/TECH_RESEARCH"}
    # import the screens into the standard layout (one ID per screen) — the folder is emptied
    for f in sorted(folder.iterdir()):
        cli("design", "screen", "add", f.stem.lower().replace(" ", "-"), str(f), "--move")
    assert not any(folder.iterdir())
    assert cli("design", "screen", "list")["screens"][0]["id"] == "browser-tab-bar"
    cfg = project.config
    cfg["paths"] = {"adr_dir": "docs/decisions", "research": "project_ops/TECH_RESEARCH"}
    config.save(project.root, cfg)
    assert cli("layout", "--check")["valid"]
    assert rows["adr_dir"]["override"] == "paths.adr_dir"
    assert "adr_dir: `docs/decisions`" in protocol.prime(project)


def test_override_screen_folder_with_flat_files_is_citable(project):
    from speky_core import config, uxdesign
    folder = project.root / "ux"
    folder.mkdir()
    (folder / "Browser Tab Bar.png").write_bytes(b"png")
    cfg = project.config
    cfg["paths"] = {"design_screens": "ux"}
    config.save(project.root, cfg)
    item = spec(project, body=GOOD_SPEC.replace("## Requirements",
                "## Design\n- screen:browser-tab-bar\n- `ux/Browser Tab Bar.png`\n\n## Requirements"))
    st = uxdesign.state(project, item)
    assert st["cited"] == ["ux/Browser Tab Bar.png"] and st["outside"] == [] and st["broken"] == []



def test_reference_screens_need_no_new_approval(project, tmp_path):
    from speky_core import uxdesign
    png = tmp_path / "tab.png"
    png.write_bytes(b"png")
    cli("design", "screen", "add", "browser-tab-bar", str(png))
    item = spec(project, body=GOOD_SPEC.replace("## Requirements",
                "## Design\nNo new design needed: behaviour fix; tab bar as in screen:browser-tab-bar.\n\n## Requirements"))
    st = uxdesign.state(project, item)
    assert st["cited"] == [".speky/design/screens/browser-tab-bar"] and st["unapproved"] == []


def test_grouped_screens_and_multi_screen_folders(project, tmp_path):
    from speky_core import design
    root = project.dir / "design" / "screens"
    held = root / "run-view" / "v2-E" / "held"
    held.mkdir(parents=True)
    (held / "render@2x.png").write_bytes(b"png")
    (held / "screen.yaml").write_text("id: RV-E2-held\ntitle: Held before Think\nstatus: approved\n")
    build = root / "run-view" / "build"
    build.mkdir(parents=True)
    for n in ("empty.png", "empty-light.png"):
        (build / n).write_bytes(b"png")
    (build / "screens.yaml").write_text(
        "- id: RV-B1-empty\n  title: Before the first run\n  files: [empty.png]\n  status: superseded\n"
        "  superseded_by: RV-B2-empty\n- id: RV-B1-empty-light\n  files: [empty-light.png]\n")
    ids = {s["id"]: s for s in design.screens(project)}
    assert set(ids) == {"RV-E2-held", "RV-B1-empty", "RV-B1-empty-light"}
    assert ids["RV-E2-held"]["group"] == "run-view/v2-E" and ids["RV-B1-empty"]["path"].endswith("build/empty.png")
    assert refs.scan(project)["valid"]
    cli("design", "screen", "approve", "RV-B1-empty-light", "--by", "owner")
    assert "status: approved" in (build / "screens.yaml").read_text()
    out = cli("design", "screen", "add", "RV-E3-held", str(held / "render@2x.png"), "--group", "run-view/v3")
    assert out["path"] == ".speky/design/screens/run-view/v3/RV-E3-held"
    catalogue = (project.dir / "design" / "screens.md").read_text()
    assert "## run-view/build" in catalogue and "`RV-B1-empty`" in catalogue
    # adr: is built in
    (project.dir / "adr").mkdir()
    (project.dir / "adr" / "0021-clean.md").write_text("# ADR-0021\n\nStatus: Accepted\n")
    assert refs.locate(project, "adr", "0021", {"builtin": "adr"}) == ".speky/adr/0021-clean.md"


def test_rejected_screens_and_reference_kind(project, tmp_path):
    from speky_core import uxdesign
    png = tmp_path / "a.png"
    png.write_bytes(b"png")
    cli("design", "screen", "add", "variant-a", str(png))
    (project.dir / "design" / "screens" / "variant-a" / "screen.yaml").write_text("id: variant-a\nstatus: rejected\n")
    cli("design", "screen", "add", "baseline", str(png), "--kind", "reference")
    item = spec(project, body=GOOD_SPEC.replace("## Requirements", "## Design\n- screen:variant-a\n\n## Requirements"))
    assert uxdesign.state(project, item)["broken"] == ["screen:variant-a (explored, not chosen)"]


def test_a_clone_without_checkpoint_picks_up_from_the_committed_log(repo):
    from speky_core import config
    cfg = repo.config
    cfg["agent_profile"] = "team-maintainer"
    config.save(repo.root, cfg)
    git(repo.root, "add", "-A")
    git(repo.root, "commit", "-q", "-m", "setup")
    continuity.handoff(repo, summary="where we are", next_=["do W2"], title="Layout moved", run_tests=False)
    (repo.root / "x.py").write_text("x = 1\n")
    git(repo.root, "add", "x.py")
    git(repo.root, "commit", "-q", "-m", "later work")
    (repo.dir / "checkpoint.json").unlink()          # another machine / a fresh clone
    text = protocol.prime(repo)
    assert '"Layout moved"' in text and "No handoff recorded" not in text
    assert "1 commit(s) since the handoff" in text and "later work" in text
