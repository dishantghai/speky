"""Item IDs and commit staging (behaviour carried over from v2's fixes)."""
from speky_core import commit
from speky_core.items import Project

from .conftest import cli, git


def make(project, kind, *names):
    base = project.specs_dir if kind == "spec" else project.stories_dir
    for name in names:
        (base / name).mkdir(parents=True)
    return base


def test_next_id_skips_gaps_and_never_reuses_a_deleted_number(project):
    make(project, "spec", "001-login", "003-billing")
    assert project.next_id("spec") == "004"
    (project.specs_dir / "003-billing").rmdir()
    assert project.next_id("spec") == "005"


def test_next_id_per_story_prefix(project):
    make(project, "story", "F001-a", "F007-b", "B002-c")
    assert project.next_id("story", "feature") == "F008"
    assert project.next_id("story", "bug") == "B003"
    assert project.next_id("story", "tech_debt").endswith("001")


def test_find_exact_id_not_substring_and_unique_name(project):
    for name in ("010-search", "100-export", "001-user-login", "002-login-audit"):
        (project.specs_dir / name).mkdir(parents=True)
        (project.specs_dir / name / "spec.md").write_text(f"# {name}\n")
    p = Project(project.root)
    assert p.try_find("1").path.name == "001-user-login"
    assert p.try_find("10").path.name == "010-search"
    assert p.try_find("user login").path.name == "001-user-login"
    assert p.try_find("search").path.name == "010-search"
    assert p.try_find("login") is None  # ambiguous
    assert p.try_find("F002") is None


def test_story_ids_case_insensitive(project):
    for name in ("F001-cart", "F010-checkout"):
        (project.stories_dir / name).mkdir(parents=True)
        (project.stories_dir / name / "story.md").write_text("# x\n")
    p = Project(project.root)
    assert p.try_find("f1").path.name == "F001-cart"
    assert p.try_find("F010").path.name == "F010-checkout"


def _done_item(repo):
    item = repo.create("spec", "X")
    item.update_status(status="review")
    return item


def staged_after_commit(repo):
    return set(filter(None, git(repo.root, "show", "--name-only", "--format=", "HEAD").splitlines()))


def test_secret_files_are_never_auto_staged(repo):
    item = _done_item(repo)
    (repo.root / "app.py").write_text("print(2)\n")
    (repo.root / ".env").write_text("KEY=secret\n")
    (repo.root / "deploy.pem").write_text("-----\n")
    out = commit.commit(repo, item.id)
    assert set(out["held_back"]) == {".env", "deploy.pem"}
    files = staged_after_commit(repo)
    assert "app.py" in files and ".env" not in files and "deploy.pem" not in files


def test_already_staged_files_are_committed_as_is(repo):
    item = _done_item(repo)
    (repo.root / "app.py").write_text("print(2)\n")
    (repo.root / "other.py").write_text("x = 1\n")
    git(repo.root, "add", "app.py")
    commit.commit(repo, item.id)
    files = staged_after_commit(repo)
    assert "app.py" in files and "other.py" not in files


def test_ignored_speky_folder_is_skipped_and_deletions_are_staged(repo):
    item = _done_item(repo)
    (repo.root / ".gitignore").write_text(".speky/\n")
    tracked = [f for f in git(repo.root, "ls-files").splitlines() if not f.startswith(".speky/")]
    victim = tracked[0]
    (repo.root / victim).unlink()
    out = commit.commit(repo, item.id)
    assert out["committed"]
    files = staged_after_commit(repo)
    assert victim in files and not any(f.startswith(".speky/") for f in files)
