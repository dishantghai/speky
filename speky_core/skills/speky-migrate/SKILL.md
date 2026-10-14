---
name: speky-migrate
description: Use when a project has a SPEKY v2 .speky/ folder (context/, config.yaml, specs/, stories/), keeps continuity notes by hand (STATE/PLAN/LOG/KNOWLEDGE files, owner to-do lists, a session protocol in AGENTS.md), or `speky migrate` reports pending steps. Brings it onto SPEKY without losing anything.
---

# Bring a project onto SPEKY

Nothing is moved or deleted: SPEKY reads v2's specs, stories, epics, phases, backlog and design files
as they are. Work on a branch; never stage or change the user's unrelated uncommitted files.

1. `git status` (note the user's files) → `git checkout -b chore/speky`.
2. `speky migrate --json` (dry run) → `speky migrate --apply` → dry run again: nothing pending.
   It also moves v2's product profile and tech stack into knowledge and its backlog file into the
   backlog; read what it reports.
3. `speky setup <harness>` for each tool the team uses (`speky setup --list`; v2's cursor, windsurf, vscode and antigravity rules files are cleaned up) → `speky setup <h> --check`
   says current. The old v2 rules block is replaced (your own rules kept; backup in `.speky/backups/`).
   If CLAUDE.md only imports AGENTS.md, the block goes into AGENTS.md.
4. `speky test init`; check `speky config get verify_command`.

## Adopt hand-kept continuity notes (if the project has them)
Map each kind of note to its SPEKY home with the generic commands — keep the wording, drop nothing:
| Hand-kept | SPEKY |
|---|---|
| Plan with phases/milestones and gates | `speky phases add "<name>" --id <id>`; each gate line → `speky phases deliverable <id> "<text>" [--run "<cmd>"]`; finished ones → `speky phases verify`/`complete --force "<why>"` |
| Checklist items (done/in progress/todo/deferred), nested | `speky task add "<text>" --phase <id> [--parent W<n>]`, then `speky task done|start|defer` — keep citations as `--refs adr:0021,screen:RV-1` |
| Knowledge / gotchas / owner preferences by topic | `speky remember "<entry>" --topic <topic> [--always] [--read-when "<trigger>"]`; owner preferences → `--topic owner --always` |
| Session log | keep it; start new entries with `speky handoff`. Note the old file's location in the first handoff. |
| Current state / next actions / watch-outs | first `speky handoff --file <notes.md>` with `## Summary`, `## Next`, `## Watch out for` copied from it |
| Owner-only to-dos (with the owner's notes) | `speky owner add "<text>" --section "<section>"`; ticked → `speky owner done`; keep notes with `--note` |
| ADRs elsewhere | `speky config set paths.adr_dir <dir>` (SPEKY uses that folder and its template) |
| Cited IDs (screens, ADRs) | `speky config set refs.<kind>.glob "<pattern with {id}>"`; `speky refs --json` must be valid |
| Definition of done rules (e.g. UI needs a review file) | `speky config set done_checks.<label> ...` (file / run / manual checks), label items with `--labels` |
| Session protocol in AGENTS.md | replace it with the SPEKY block (step 3); keep project rules (architecture, product) outside the block |
Verify the import against the source files before retiring them; only the owner decides to delete them.

## Seed living specs from completed work
Group completed items into capabilities (user-visible areas). For each, write
`.speky/capabilities/<capability>/spec.md`: `## Purpose`, `<!-- speky:next-id N -->`, and requirements
`### <capability>-R<n>: <title>` with WHEN/THEN scenarios describing what the code does **today**
(read the code). Items `speky migrate` lists as suspect completions: check the code; file real gaps
(`speky story "..." --type bug --discovered-from <id>`), then `speky migrate --done check_suspect_completions`.
`speky capabilities --json` must say valid.

## Finish
`speky decide "Migrated to SPEKY" --type event`; verify `speky status`, `speky next --json`,
`speky prime`, `speky refs --json`; a fresh agent session picks up the right next step. Commit only
`.speky/`, the harness files and the instruction files.
