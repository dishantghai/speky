import subprocess

import pytest

from speky import SPEKY, Console


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "app.py").write_text("print(1)\n")
    git(tmp_path, "add", "app.py")
    git(tmp_path, "commit", "-q", "-m", "init")
    status = tmp_path / ".speky" / "specs" / "001-x" / "status.json"
    status.parent.mkdir(parents=True)
    status.write_text("{}")
    Console.configure(non_interactive=True, assume_yes=True)
    yield tmp_path, status
    Console.configure()


def staged(repo):
    return set(filter(None, git(repo, "diff", "--cached", "--name-only").splitlines()))


def test_secret_files_are_never_auto_staged(repo):
    root, status = repo
    (root / "app.py").write_text("print(2)\n")
    (root / ".env").write_text("KEY=secret\n")
    (root / "deploy.pem").write_text("-----\n")
    assert SPEKY(project_root=root)._stage_files_for_commit(status)
    assert staged(root) == {"app.py", ".speky/specs/001-x/status.json"}


def test_already_staged_files_are_committed_as_is(repo):
    root, status = repo
    (root / "app.py").write_text("print(2)\n")
    (root / "other.py").write_text("x = 1\n")
    git(root, "add", "app.py")
    assert SPEKY(project_root=root)._stage_files_for_commit(status)
    assert staged(root) == {"app.py", ".speky/specs/001-x/status.json"}


def test_ignored_status_file_is_skipped(repo):
    root, status = repo
    (root / ".gitignore").write_text(".speky/\n")
    (root / "app.py").write_text("print(2)\n")
    assert SPEKY(project_root=root)._stage_files_for_commit(status)
    assert staged(root) == {"app.py", ".gitignore"}


def test_deleted_files_are_staged(repo):
    root, status = repo
    (root / "app.py").unlink()
    assert SPEKY(project_root=root)._stage_files_for_commit(status)
    assert "app.py" in staged(root)


def test_declining_stages_nothing(repo):
    root, status = repo
    (root / "app.py").write_text("print(2)\n")
    Console.configure(non_interactive=True, answers=[("Stage and commit", "no")])
    assert not SPEKY(project_root=root)._stage_files_for_commit(status)
    assert staged(root) == set()
