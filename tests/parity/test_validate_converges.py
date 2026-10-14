"""v2 `validate-spec` must converge: no re-run on an unchanged spec, earlier findings passed to the
model, and a round cap (the loop reported by users)."""
from tests.parity.conftest import init_project, new_spec, run

KEY = "Analyze this feature specification for quality"


def calls(fake):
    return [c for c in fake.calls if KEY in c]


def test_validate_spec_stops_looping(project, fake_llm):
    init_project()
    new_spec("Import video")
    spec = project / ".speky" / "specs" / "001-import-video" / "spec.md"

    run("validate-spec", "001", "--quick")
    assert len(calls(fake_llm)) == 1

    run("validate-spec", "001", "--quick")  # unchanged spec: no new round
    assert len(calls(fake_llm)) == 1

    spec.write_text(spec.read_text() + "\n## Error states\n- Show a message.\n")
    run("validate-spec", "001", "--quick")  # round 2 sees round 1's findings
    assert len(calls(fake_llm)) == 2
    assert "ALREADY REVIEWED" in calls(fake_llm)[1] and "Error state undefined" in calls(fake_llm)[1]

    spec.write_text(spec.read_text() + "\nMore.\n")
    run("validate-spec", "001", "--quick")  # cap reached: converged, no model call
    assert len(calls(fake_llm)) == 2

    run("validate-spec", "001", "--quick", "--force")
    assert len(calls(fake_llm)) == 3


def test_validate_story_stops_looping(project, fake_llm):
    init_project()
    run("story", "Fix login typo", "--type", "bug")
    before = len(fake_llm.calls)
    run("validate-story", "B001", "--quick")
    first = len(fake_llm.calls)
    assert first > before
    run("validate-story", "B001", "--quick")
    assert len(fake_llm.calls) == first
