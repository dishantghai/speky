---
name: speky-propose
description: Use when `speky next` says propose, or when the user wants a new SPEKY spec or story written. Turns an intent into a short change document with requirement IDs and WHEN/THEN scenarios.
---

# Propose a change

Goal: a short contract someone could build without guessing — and no longer than that.

1. Find out what is wanted. If something non-trivial is missing, ask — **one question per message,
   at most 5 in total, each with your recommended answer** and one line on why it matters. Ask only
   what changes what gets built. If the code can answer it, read the code instead of asking.
   Skip questions the user opted out of; state your defaults out loud instead.
2. Create the item if it doesn't exist: `speky new spec "<title>"` (or `speky new story ...`).
3. Write the document (`spec.md` / `story.md`):
   - `## Why` — the problem and who has it.
   - `## Capabilities` — what is true when it's done.
   - `## Non-goals` — at least one.
   - `## Requirements` — `### R1: <title>` with a SHALL sentence and at least one
     `#### Scenario:` using GIVEN / WHEN / THEN lines. Cover the error or empty state.
   - `## Assumptions` — every informed guess you made instead of asking.
   - At most 3 `[NEEDS CLARIFICATION: ...]` markers; guess the rest and list them as assumptions.
4. Requirements describe behaviour, not implementation. No class names, no library choices
   (those go in plan.md). If behaviour of an existing capability changes, write
   `deltas/<capability>.md` with `## ADDED|MODIFIED|REMOVED Requirements`
   (see `.speky/capabilities/` for current IDs).
5. Record assumptions and decisions: `speky decide "..." --type assumption --ref <id>`.
6. Run `speky check <id> --json` and fix every blocker it reports.

Done when `speky check <id>` reports no blockers. Then `speky next`.
