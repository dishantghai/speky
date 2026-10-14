---
name: speky-migrate
description: Use when a project has a SPEKY v2 .speky/ folder (specs/, stories/, context/) and the user wants it moved to SPEKY v3, or `speky migrate` reports pending steps. Migrates without losing any v2 data.
---

# Migrate a SPEKY v2 project to v3

v3 reads the same `.speky/specs/` and `.speky/stories/` folders; nothing is moved or deleted.
Work on a branch and keep the user's uncommitted files untouched.

1. `git status` — note files the user hasn't committed; never stage or change them.
   `git checkout -b chore/speky-v3`.
2. `speky migrate --json` (dry run). Read every reported issue.
3. `speky migrate --apply` — writes `.speky/speky.yaml`, `.speky/capabilities/`, normalises
   `status.json`. Re-run the dry run: it must report nothing left to apply.
4. `speky setup <harness>` for each harness the team uses (`claude-code`, `codex`, `agents-md`).
   This replaces the old 1,000-line v2 rules block with a small managed block, keeps the user's own
   rules, and backs the old file up under `.speky/backups/`. Then `speky setup <harness> --check`.
5. Seed living specs from **completed** items — the part that needs judgement:
   - Group completed specs/stories by capability (a user-visible area such as `browser-tabs`).
   - For each capability write `.speky/capabilities/<capability>/spec.md` with `## Purpose` and
     requirements `### <capability>-R<n>: <title>` + WHEN/THEN scenarios **describing what the code
     does today** — read the code; don't copy spec text that was never built.
   - Completed items whose v2 drift review was skipped (`speky migrate` lists them) are suspect:
     check the code before claiming the behaviour exists; record gaps as new bug/tech_debt stories.
   - Put `<!-- speky:next-id N -->` above `## Requirements` (N = highest R number + 1).
   - `speky capabilities --json` must report `"valid": true` (format: the speky-verify skill, step 3).
6. Open items (draft/ready/in_progress): run `speky check <id>`; add requirement IDs and scenarios
   where the rubric asks. Don't rewrite intent.
7. Record the migration: `speky decide "Migrated to SPEKY v3" --type event`.
8. Verify: `speky capabilities --json` is valid; `speky state --json` lists every item; `speky next --json` returns a sensible action;
   `speky setup <harness> --check` says current; the v2 commands (`speky status`) still work.
   Commit only `.speky/`, the harness files and the instruction files — never the user's
   unrelated changes.
