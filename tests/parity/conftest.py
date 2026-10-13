"""Parity safety net for SPEKY v2.

Runs real `speky <command>` invocations end to end in a temp project, with the model
replaced by a scripted fake. These tests pin v2's observable behaviour (files written,
statuses, exit codes) so a rewrite can prove that no capability was lost — see the
parity inventory in docs/v3/PLAN.md §2.8.
"""
import json
import os
import sys

import pytest

import speky
import speky_llm

PROFILE = {
    "name": "Recipe Cards", "description": "Turns cooking videos into step-by-step recipe cards.",
    "target_users": "Home cooks", "problem": "Videos are hard to follow while cooking",
    "platform": "web", "scale": "personal", "domain": "cooking",
    "features": ["Import: paste a video link", "Cards: step-by-step view"],
    "constraints": "None", "mvp_scope": "Import and view one recipe",
}

SPEC = """# {name}

## Overview
Lets a home cook do the thing.

## MVP Scope
- One path only

## User Stories
- As a cook, I want to do the thing, so that I can cook.
  - Acceptance: the thing works

## Requirements
### Functional Requirements (MVP only)
- It does the thing

### Non-Functional Requirements
- None

## Out of Scope
- Everything else

## Open Questions
None

## Technical Approach
- Plain functions
"""

STORY = """# {name}

## Description
A small change.

## Acceptance Criteria
- [ ] It works

## Context
- **Related Spec**: none

## Tasks
1. Do it

## Notes
None
"""

# (substring that identifies the prompt, response). First match wins.
DEFAULT_SCRIPT = [
    ("Generate exactly 5 clarifying questions",
     "1. Who is it for?\n2. What is in the MVP?\n3. Which platform?\n4. What scale?\n5. Any constraints?"),
    ("create a structured product profile", json.dumps(PROFILE)),
    ("writing a feature specification", SPEC),
    ("creating an implementation plan", "# Implementation Plan\n\n## Tasks\n- [ ] **Do it** (estimate: 2h)\n"),
    ("Analyze this feature specification for quality",
     "## Tech Violations\nNone\n\n## Gaps/Issues\n- **Gap**: Error state undefined\n  **Fix**: Add one\n\n"
     "## Cross-Spec Concerns\nNone\n\n## Suggestions\n- None\n\n## Summary\nGood."),
    ("Analyze the drift", "NO_DRIFT_DETECTED"),
    ("You are creating a development story", STORY),
    ("Analyze if this spec needs updates", "NEEDS_UPDATE: NO"),
]
FALLBACK = "OK"


class FakeLLM:
    """Stands in for LLMRouter.complete: answers from a script and records every call."""

    def __init__(self, script=None):
        self.script = list(script or DEFAULT_SCRIPT)
        self.calls = []

    def complete(self, prompt, system, max_tokens, temperature, stream=False, retries=3,
                 expect_json=False):
        self.calls.append(prompt)
        for key, response in self.script:
            if key in prompt:
                return response
        return FALLBACK


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(speky_llm.LLMRouter, "complete",
                        lambda self, *a, **kw: fake.complete(*a, **kw))
    return fake


@pytest.fixture
def project(tmp_path, monkeypatch, fake_llm):
    """An empty project directory with no real API keys, config or network."""
    home = tmp_path / "home"
    home.mkdir()
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(speky_llm, "GLOBAL_CONFIG", home / ".speky" / "models.yaml")
    for var in list(os.environ):
        if var.endswith("_API_KEY") or var in ("SPEKY_MODEL", "ANTHROPIC_MODEL", "OPENAI_MODEL"):
            monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SPEKY_MODEL", "anthropic/fake-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.chdir(root)
    yield root
    speky.Console.configure()


def run(*argv, answers=None):
    """Run `speky <argv> --non-interactive` in the current directory; return the exit code."""
    args = ["speky", *argv, "--non-interactive"]
    for question, value in (answers or {}).items():
        args += ["--answer", f"{question}={value}"]
    old_argv = sys.argv
    sys.argv = args
    speky.Console._asked = {}  # per-process state in the real CLI
    try:
        speky.main()
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 1
    finally:
        sys.argv = old_argv
        speky.Console.configure()
    return 0


def init_project():
    code = run("init", "A web app that turns cooking videos into recipe cards",
               answers={"How would you like to proceed": "No, start fresh"})
    assert code == 0


SPEC_ANSWERS = {"How would you like to proceed": "No, start fresh",
                "Generate implementation plan now": "no"}


def new_spec(name):
    assert run("spec", name, answers=SPEC_ANSWERS) == 0
