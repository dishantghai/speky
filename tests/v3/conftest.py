import json
import subprocess
import sys
from pathlib import Path

import pytest

from speky_core.cli import main as cli_main
from speky_core.items import Project

GOOD_SPEC = """# Paste a video link

## Why
Home cooks lose their place in cooking videos.

## Capabilities
- Paste a link and get a recipe card.

## Non-goals
- Editing recipes.

## Requirements

### R1: Accept a video link
The app SHALL accept a YouTube URL.

#### Scenario: Valid link
- GIVEN the import screen
- WHEN the user pastes a valid link
- THEN a recipe card draft is created

### R2: Reject other links
The app SHALL refuse links it cannot read.

#### Scenario: Unknown site
- GIVEN the import screen
- WHEN the user pastes a link from an unknown site
- THEN an error explains which sites work

## Assumptions
- Only public videos.
"""


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / ".speky").mkdir()
    monkeypatch.chdir(tmp_path)
    return Project(tmp_path)


@pytest.fixture
def repo(project):
    root = project.root
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "app.py").write_text("print(1)\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return project


def spec(project, title="Paste a video link", body=GOOD_SPEC, **kw):
    return project.create("spec", title, body=body, **kw)


def cli(*argv, expect=0):
    """Run a v3 command with --json, return the parsed document."""
    from io import StringIO
    out = StringIO()
    old = sys.stdout
    sys.stdout = out
    try:
        code = cli_main([*argv, "--json"])
    finally:
        sys.stdout = old
    assert code == expect, out.getvalue()
    return json.loads(out.getvalue())
