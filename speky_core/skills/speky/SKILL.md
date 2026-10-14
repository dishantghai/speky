---
name: speky
description: Use when starting work in a repository that has a .speky/ folder, when the user asks what to work on next, asks to build, change or fix something there, or mentions SPEKY. Routes the work to the right size and the right speky-* skill.
---

# SPEKY

SPEKY keeps this project's changes, requirements, decisions and evidence in `.speky/`. It holds
state and rules; you do the reasoning and the work. Talk to it through the `speky` CLI.

## Start here

Run `speky next --json`. It returns one action with the skill to use, the files to read, the
commands to run and when it is done. Follow it, then ask again. After context compaction or in a
new session, ask again — the answer comes from files, not memory.

| `action` | Use |
|---|---|
| `propose` | speky-propose |
| `validate`, `fix_structure` | speky-validate |
| `plan` | speky-plan |
| `start`, `implement` | speky-implement |
| `archive` | speky-verify |
| `resolve_gate` | stop and ask the user — never decide a human gate yourself |
| `blocked` | work on what it is waiting for (`speky ready --json`) |
| `idle` | ask the user what to build next, then size it (below) |

## Size the work before creating anything

Say the size in one line; the user can override it.

| Size | When | Do |
|---|---|---|
| quick | the request says everything (typo, config value, one obvious line) | do it, run the tests, report — no item |
| small | one behaviour, one session | `speky new story "<title>" --type feature|bug --size small` |
| change | new or changed behaviour that needs agreement first | `speky new spec "<title>"` |
| epic | several independently shippable parts | one spec per part, linked with `--deps` |

A bug: find the root cause before proposing a fix; after three failed fixes, question the design.

## Rules that always apply
- No completion claims without fresh evidence: test output, a diff, a requirement-by-requirement check.
- Discovered work becomes a new item (`--discovered-from <id>`), never silent scope growth.
- Record decisions with `speky decide "..." --type decision|assumption --ref <id>`; durable facts with `speky remember "..."`.
- Never edit `status.json`, `findings.json` or `evidence.json` by hand; use the CLI.
- Every `--json` command prints one JSON document; on error read `error.fix`.
