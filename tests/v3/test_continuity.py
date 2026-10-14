"""Milestone 2: continuity — phases, tasks, handoff/checkpoint, knowledge, owner actions, refs,
done checks, ADRs in the project's own folder, AGENTS.md redirection and the PreCompact hook."""
import json

import pytest

from speky_core import continuity, harness, journal, knowledge, phases, protocol, refs, verification
from speky_core.errors import SpekyError
from speky_core.owner import OwnerActions
from speky_core.tasks import Tasks

from .conftest import GOOD_SPEC, cli, git, spec


# ---------------------------------------------------------------- phases (v2 manifests)
def test_phases_use_v2_manifests_and_v2_can_read_them(project):
    import speky
    p = phases.add(project, "Workbench", "phase-1a")
    phases.add_deliverable(project, "phase-1a", "Walkthrough test passes", run="true")
    phases.add_deliverable(project, "phase-1a", "Owner reaches the fix in 15 minutes")
    phases.set_status(project, "phase-1a", "doing")
    manifest = project.dir / "phases" / "phase-1a" / "manifest.yaml"
    assert manifest.exists()
    v2 = speky.SPEKY(project_root=project.root)
    data = v2._load_phase("phase-1a")
    assert data["name"] == "Workbench" and data["status"] == "in_progress"
    assert [d["id"] for d in data["deliverables"]] == ["D1", "D2"]
    assert v2._load_roadmap()["current_phase"] == "phase-1a"


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
    import speky
    (project.dir / "backlog.json").write_text(json.dumps(
        [{"name": "deferred thing", "status": "pending", "type": "CODE_BEHIND"}]))
    phases.add(project, "P", "p1")
    phases.set_status(project, "p1", "doing")
    t = Tasks(project).add("Wire SSE", refs=["adr:0021"])
    sub = Tasks(project).add("Add retry", parent=t["id"])
    assert t["phase"] == "p1" and sub["phase"] == "p1"
    items = json.loads((project.dir / "backlog.json").read_text())
    assert len(items) == 3 and items[0]["status"] == "pending"
    assert speky.SPEKY(project_root=project.root)._get_backlog_count()["total"] == 1
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
    oa = OwnerActions(project)
    assert oa.assign_missing_ids() == 1
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
