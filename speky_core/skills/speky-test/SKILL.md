---
name: speky-test
description: Use when tests are written, run, generated or debugged in a SPEKY project — setting up testing, test-first work (TDD), end-to-end tests, coverage, test gaps for requirements, or triaging failing tests (`speky test`).
---

# Tests

1. **Set up once:** `speky test init` detects the runner and sets `verify_command` (and coverage/e2e
   commands when it can). Check with `speky test status --json`; fix with
   `speky config set verify_command "<cmd>"` or `speky config set testing.coverage_command "<cmd>"`.
2. **Every requirement gets a test that proves it.** `speky test gaps --json` lists requirements without
   one. Write the test in the project's existing style and location, then link it:
   `speky test link <item> R1 "<path>::<test name>"`.
3. **Test-first (TDD)**, when the project or the item asks for it: write the failing test, prove it
   fails — `speky test red <item> R1 --cmd "<command running just that test>"` — implement, then
   `speky test green <item> R1 --cmd "<same command>"` (records the evidence).
4. **Run:** `speky test run --json` (records the result for `speky prime` and handoffs);
   e2e: `speky test run --type e2e`. Coverage: `speky test coverage --json` against the threshold.
5. **Triage failures** before changing anything. For each failing test decide:
   - regression — the code broke behaviour a requirement needs → fix the code;
   - outdated — the requirement changed on purpose → update the test and say which change;
   - flaky — passes and fails without changes → quarantine with a task, never delete silently;
   - expected (TDD red) — leave it.
   Record anything you can't fix now as a finding on the item, a bug story (`speky new story "…" --type bug`), or a small `speky task add "..." --kind fix`.
6. Never claim tests pass without fresh output from this session.
