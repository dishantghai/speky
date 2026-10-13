import pytest

from speky_core import validation
from speky_core.errors import SpekyError

from .conftest import GOOD_SPEC, spec


def test_good_spec_converges_in_round_one(project):
    item = spec(project)
    result = validation.check(project, item)
    assert result["round"] == 1 and result["converged"]
    assert all(r["passed"] for r in result["rubric"])


def test_template_is_blocked_by_placeholders(project):
    item = project.create("spec", "New thing")
    result = validation.check(project, item)
    failed = {r["rubric"] for r in result["rubric"] if not r["passed"]}
    assert {"placeholders", "why", "non_goals"} <= failed
    assert not result["converged"]


def test_unchanged_spec_does_not_start_a_new_round(project):
    item = spec(project)
    validation.check(project, item)
    again = validation.check(project, item)
    assert again["cached"] and again["round"] == 1
    assert "nothing new" in again["message"].lower()


def test_majors_are_parked_at_the_cap_but_blockers_are_not(project):
    item = spec(project)
    validation.check(project, item)
    ledger = validation.Ledger(item)
    ledger.add("Retry behaviour for flaky networks is unclear", "major", round_=1)
    item.doc_path.write_text(GOOD_SPEC + "\nMore text.\n")
    second = validation.check(project, item)  # round 2 == cap
    assert second["converged"] and "parked" in second["converged_reason"]
    parked = [f for f in validation.Ledger(item).findings if f["status"] == "parked"]
    assert len(parked) == 1 and "implementation-time" in parked[0]["ruling"]

    item.doc_path.write_text(GOOD_SPEC.replace("### R2: Reject other links", "### R2: Reject"))
    validation.Ledger(item).add("Data retention is undefined", "blocker", round_=2)
    third = validation.check(project, item)
    assert not third["converged"]
    assert [f["text"] for f in third["open"]["blocker"]] == ["Data retention is undefined"]


def test_closed_findings_are_never_re_raised(project):
    item = spec(project)
    ledger = validation.Ledger(item)
    f = ledger.add("The error message for unknown sites is not specified", "major")
    ledger.resolve(f["id"], "fixed")
    again = ledger.add("The ERROR message for unknown sites is not specified!", "major")
    assert again["duplicate"] and again["id"] == f["id"] and again["status"] == "fixed"
    assert len(validation.Ledger(item).findings) == 1


def test_question_cap(project):
    item = spec(project)
    ledger = validation.Ledger(item)
    for topic in ("pagination", "retention", "authentication", "localisation", "offline"):
        ledger.add(f"How should {topic} behave?", "major", kind="question")
    with pytest.raises(SpekyError) as e:
        ledger.add("A sixth question about something else", "major", kind="question")
    assert e.value.code == "question_cap_reached" and "Assumptions" in e.value.fix


def test_closing_without_fixing_needs_a_ruling(project):
    item = spec(project)
    ledger = validation.Ledger(item)
    f = ledger.add("Pagination limits unclear", "minor")
    with pytest.raises(SpekyError) as e:
        ledger.resolve(f["id"], "accepted")
    assert e.value.code == "ruling_required"
    ledger.resolve(f["id"], "accepted", "Use 50 per page — common default — cheap to change")


def test_rubric_findings_close_when_fixed_and_reopen_when_broken(project):
    item = spec(project, body=GOOD_SPEC.replace("## Non-goals\n- Editing recipes.\n", ""))
    first = validation.check(project, item)
    assert any(f["rubric"] == "non_goals" for f in first["open"]["major"])
    item.doc_path.write_text(GOOD_SPEC)
    second = validation.check(project, item)
    assert second["converged"]
    ng = [f for f in validation.Ledger(item).findings if f.get("rubric") == "non_goals"][0]
    assert ng["status"] == "fixed"


def test_clarification_marker_limit(project):
    body = GOOD_SPEC + "\n" + "\n".join(f"[NEEDS CLARIFICATION: q{i}]" for i in range(4))
    item = spec(project, body=body)
    result = validation.check(project, item)
    assert not result["converged"]
    assert any(f["rubric"] == "clarifications" for f in result["open"]["blocker"])


def test_unknown_dependency_is_a_blocker(project):
    item = spec(project)
    item.update_status(dependencies=["099"])
    result = validation.check(project, item)
    assert any(f["rubric"] == "dependencies" for f in result["open"]["blocker"])


def test_v2_spec_without_requirement_ids(project):
    v2 = "# Old\n\n## Overview\nx\n\n## MVP Scope\n- y\n\n## Out of Scope\n- z\n\n## User Stories\n- As a user...\n"
    item = spec(project, body=v2)
    result = validation.check(project, item)
    assert {f["rubric"] for f in result["open"]["blocker"]} >= {"requirements", "scenarios"}
