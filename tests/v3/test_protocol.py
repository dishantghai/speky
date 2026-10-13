import json

from speky_core import graph, protocol, validation, verification

from .conftest import GOOD_SPEC, spec


def test_next_walks_the_lifecycle(repo):
    p = repo
    assert protocol.next_action(p)["action"] == "idle"
    item = p.create("spec", "Paste a video link")
    assert protocol.next_action(p)["action"] == "propose"
    item.doc_path.write_text(GOOD_SPEC)
    assert protocol.next_action(p)["action"] == "validate"
    validation.check(p, item)
    assert protocol.next_action(p)["action"] == "plan"
    (item.path / "plan.md").write_text("# Plan\n")
    assert protocol.next_action(p)["action"] == "start"
    verification.start(p, item)
    nxt = protocol.next_action(p)
    assert nxt["action"] == "implement" and nxt["skill"] == "speky-implement"
    for r in ("R1", "R2"):
        verification.record_evidence(p, item, r, "met", "t")
    verification.verify(p, item, run="true")
    assert protocol.next_action(p)["action"] == "archive"
    verification.archive(p, item)
    assert protocol.next_action(p)["action"] == "idle"


def test_small_story_skips_plan(project):
    story = project.create("story", "Fix typo", story_type="bug", size="small", body=GOOD_SPEC)
    validation.check(project, story)
    assert protocol.next_action(project, story.id)["action"] == "start"


def test_fix_structure_when_blockers_open_on_unchanged_doc(project):
    item = spec(project, body=GOOD_SPEC.replace("#### Scenario: Valid link", "Not a scenario"))
    validation.check(project, item)
    assert protocol.next_action(project, item.id)["action"] == "fix_structure"


def test_dependencies_and_gates_block_work(project):
    a = spec(project, "A")
    b = spec(project, "B", dependencies=["001"])
    assert [i["id"] for i in graph.ready(project)] == ["001"]
    assert protocol.next_action(project, b.id)["action"] == "blocked"
    gate = graph.add_gate(a, "human", "Choose the video provider")
    assert protocol.next_action(project, a.id)["action"] == "resolve_gate"
    assert protocol.next_action(project)["action"] == "resolve_gate"
    graph.resolve_gate(a, gate["id"], by="user")
    assert protocol.next_action(project, a.id)["action"] == "validate"
    a.update_status(status="completed")
    assert [i["id"] for i in graph.ready(project)] == ["002"]


def test_cycles_are_reported(project):
    spec(project, "A")
    b = spec(project, "B", dependencies=["001"])
    project.find("001").update_status(dependencies=["002"])
    assert protocol.state(project)["cycles"]


def test_prime_is_small_and_names_the_next_action(project):
    from speky_core import journal
    spec(project)
    journal.remember(project, "Run tests with pnpm test --run")
    text = protocol.prime(project)
    assert "speky next --json" in text and "validate" in text
    assert "pnpm test --run" in text
    assert len(text) < 6000  # ~1.5k tokens
    hook = json.loads(protocol.prime_hook_json(project))
    assert hook["hookSpecificOutput"]["hookEventName"] == "SessionStart"
