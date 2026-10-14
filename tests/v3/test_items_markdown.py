from speky_core import markdown as md
from speky_core.items import Project

from .conftest import GOOD_SPEC, spec


def test_create_spec_and_story_ids(project):
    a = spec(project)
    b = spec(project, "Second")
    s1 = project.create("story", "Fix typo", story_type="bug")
    s2 = project.create("story", "Another bug", story_type="bug")
    f1 = project.create("story", "A feature")
    assert [a.id, b.id, s1.id, s2.id, f1.id] == ["001", "002", "B001", "B002", "F001"]
    assert a.info()["title"] == "Paste a video link"
    assert s1.info()["type"] == "bug"


def test_ids_never_reused_after_deletion(project):
    import shutil
    spec(project, "One")
    two = spec(project, "Two")
    shutil.rmtree(two.path)
    spec(project, "Three")
    spec(project, "Four")
    assert [i.id for i in project.items()] == ["001", "003", "004"]


def test_ids_continue_after_highest(project):
    (project.specs_dir / "007-old").mkdir(parents=True)
    assert spec(project).id == "008"


def test_hash_ids(project):
    from speky_core import config
    config.save(project.root, {**config.DEFAULTS, "id_style": "hash"})
    a = spec(project)
    assert a.id.startswith("001x") and len(a.id) == 8
    b = spec(project, "Two")
    assert b.id.startswith("002x")
    assert project.find(a.id).path == a.path


def test_find_by_padded_and_exact_id(project):
    a = spec(project)
    assert project.find("1").path == a.path
    assert project.find("001").path == a.path
    assert project.try_find("01").path == a.path
    assert project.try_find("010") is None


def test_v2_status_shapes_normalise(project):
    item = spec(project)
    item.save_status({"id": "001", "name": "Old name", "status": "done", "created_at": "x"})
    info = item.info()
    assert info["title"] == "Old name" and info["status"] == "completed"


def test_parse_requirements_and_scenarios():
    reqs = md.parse_requirements(GOOD_SPEC)
    assert [r.id for r in reqs] == ["R1", "R2"]
    assert all(r.scenarios and r.scenarios[0].complete for r in reqs)


def test_section_aliases_cover_v2_headings():
    v2 = "# X\n\n## Overview\nWhy.\n\n## MVP Scope\n- a\n\n## Out of Scope (IMPORTANT)\n- b\n"
    assert md.find_section(v2, "why") == "Why."
    assert md.find_section(v2, "scope") == "- a"
    assert md.find_section(v2, "non_goals") == "- b"


def test_parse_delta():
    text = """## ADDED Requirements
### Requirement: Dark mode
The app SHALL offer dark mode.
#### Scenario: Toggle
- WHEN the user toggles
- THEN the theme changes

## MODIFIED Requirements
### ui-R2: Session timeout
Sessions SHALL expire after 15 minutes.
#### Scenario: Idle
- WHEN 15 minutes pass
- THEN the session ends

## REMOVED Requirements
### ui-R3: Remember me
Reason: replaced.
"""
    d = md.parse_delta(text)
    assert [r.title for r in d.added] == ["Dark mode"] and d.added[0].id is None
    assert [r.id for r in d.modified] == ["ui-R2"]
    assert [r.id for r in d.removed] == ["ui-R3"]
