import pytest

from speky_core import verification, vcs
from speky_core.errors import SpekyError

from .conftest import git, spec


def test_start_records_base_commit(repo):
    item = spec(repo)
    result = verification.start(repo, item)
    assert result["base_sha"] == vcs.head(repo.root) and item.info()["status"] == "in_progress"


def test_start_without_git(project):
    item = spec(project)
    assert verification.start(project, item)["base_sha"] == vcs.NO_VCS


def test_evidence_rules(repo):
    item = spec(repo)
    with pytest.raises(SpekyError) as e:
        verification.record_evidence(repo, item, "R9", "met", "x")
    assert e.value.code == "unknown_requirement"
    with pytest.raises(SpekyError) as e:
        verification.record_evidence(repo, item, "R1", "met", "")
    assert e.value.code == "evidence_required"


def test_verify_needs_evidence_for_every_requirement_and_a_passing_command(repo):
    item = spec(repo)
    verification.start(repo, item)
    (repo.root / "feature.py").write_text("def accept(url): return True\n")
    verification.record_evidence(repo, item, "R1", "met", "tests/test_x.py::test_accept")
    r = verification.verify(repo, item, run="true")
    assert not r["passed"] and any("R2" in m for m in r["missing"])
    assert "feature.py" in r["changed_files"]

    verification.record_evidence(repo, item, "R2", "met", "tests/test_x.py::test_reject")
    failing = verification.verify(repo, item, run="exit 3")
    assert not failing["passed"] and failing["run"]["exit_code"] == 3

    ok = verification.verify(repo, item, run="true")
    assert ok["passed"] and item.info()["status"] == "review"


def test_open_blocker_blocks_verification(repo):
    from speky_core.validation import Ledger
    item = spec(repo)
    for r in ("R1", "R2"):
        verification.record_evidence(repo, item, r, "met", "t")
    Ledger(item).add("Data retention unspecified", "blocker")
    assert not verification.verify(repo, item, run="true")["passed"]


def _verified(repo, item):
    verification.start(repo, item)
    for r in ("R1", "R2"):
        verification.record_evidence(repo, item, r, "met", "t")
    assert verification.verify(repo, item, run="true")["passed"]


def test_archive_requires_fresh_verification(repo):
    item = spec(repo)
    with pytest.raises(SpekyError) as e:
        verification.archive(repo, item)
    assert e.value.code == "not_verified"
    _verified(repo, item)
    (repo.root / "late_change.py").write_text("x = 1\n")
    with pytest.raises(SpekyError) as e:
        verification.archive(repo, item)
    assert e.value.code == "stale_verification"
    assert verification.verify(repo, item, run="true")["passed"]
    assert verification.archive(repo, item)["status"] == "archived"


DELTA_1 = """## Purpose
Importing recipes from videos.

## ADDED Requirements
### Requirement: Accept a video link
The app SHALL accept a YouTube URL.
#### Scenario: Valid link
- WHEN the user pastes a valid link
- THEN a draft is created

### Requirement: Remember me
Keeps users signed in.
#### Scenario: Return visit
- WHEN the user comes back
- THEN they are still signed in
"""

DELTA_2 = """## MODIFIED Requirements
### import-R1: Accept a video link
The app SHALL accept YouTube and TikTok URLs.
#### Scenario: TikTok
- WHEN the user pastes a TikTok link
- THEN a draft is created

## REMOVED Requirements
### import-R2: Remember me
Reason: replaced by passkeys.

## ADDED Requirements
### Requirement: Passkeys
The app SHALL support passkeys.
#### Scenario: Sign in
- WHEN the user signs in with a passkey
- THEN they are signed in
"""


def test_archive_merges_deltas_into_living_specs_and_never_reuses_ids(repo):
    from speky_core import markdown as md
    first = spec(repo)
    (first.path / "deltas").mkdir()
    (first.path / "deltas" / "import.md").write_text(DELTA_1)
    _verified(repo, first)
    merged = verification.archive(repo, first)["merged"]
    assert merged[0]["added"] == ["import-R1", "import-R2"]

    second = spec(repo, "TikTok links")
    (second.path / "deltas").mkdir()
    (second.path / "deltas" / "import.md").write_text(DELTA_2)
    _verified(repo, second)
    merged = verification.archive(repo, second)["merged"]
    assert merged[0]["added"] == ["import-R3"]  # R2 was removed and is never reused

    living = (repo.capabilities_dir / "import" / "spec.md").read_text()
    reqs = {r.id: r for r in md.parse_requirements(living, md.CAP_REQ_RE)}
    assert set(reqs) == {"import-R1", "import-R3"}
    assert "TikTok" in reqs["import-R1"].text()
    assert "Importing recipes from videos." in living


def test_bad_delta_writes_nothing(repo):
    item = spec(repo)
    (item.path / "deltas").mkdir()
    (item.path / "deltas" / "import.md").write_text("## MODIFIED Requirements\n### import-R9: Nope\nx\n")
    _verified(repo, item)
    with pytest.raises(SpekyError) as e:
        verification.archive(repo, item)
    assert e.value.code == "unknown_requirement_in_delta"
    assert not (repo.capabilities_dir / "import").exists()
    assert item.info()["status"] == "review"


def test_forced_archive_records_reason(project):
    item = spec(project)
    result = verification.archive(project, item, force_reason="spike, nothing to verify")
    assert result["status"] == "archived"
    assert item.load_status()["archive_forced"] == "spike, nothing to verify"
