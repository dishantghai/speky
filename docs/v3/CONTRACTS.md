# SPEKY v3 — Contracts

Status: **implemented in milestone 1** (`speky_core/`). This file is the reference for the on-disk
layout, the item lifecycle, the agent protocol (JSON), the convergence rules and the harness adapters.
Background and rationale: `PLAN.md`.

## 0. Principles
- **The core makes no LLM calls.** The coding agent (any harness) does the reasoning; SPEKY owns
  state, IDs, rules, gates and evidence. v2 commands that call a model keep working unchanged.
- **One data model with v2.** A v2 spec folder (`.speky/specs/NNN-slug/`) or story folder
  (`.speky/stories/X001-slug/`) *is* a v3 **change**. v3 adds files and fields; it never moves,
  renames or deletes v2 files. Every v2 command keeps working on the same folders.
- **Nothing is enforced that a harness already does.** Gates exist only where §5.3 of the plan says so.

Package name: `speky_core` (a `speky/` package would shadow `speky.py`, the v2 entry point).
The v3 commands are subcommands of the same `speky` CLI.

## 1. Layout

```
.speky/
  speky.yaml                     # v3 settings (real YAML) — see §8
  specs/NNN-slug/                # change (feature spec)           ← v2, unchanged
  stories/X001-slug/             # change (story: F/B/E/T/S)        ← v2, unchanged
    spec.md | story.md           # the change's contract (requirements with IDs, §3)
    plan.md                      # optional: decisions + verify commands
    status.json                  # machine state (v2 fields kept; v3 fields §2)
    deltas/<capability>.md       # v3: what this change does to the living specs (§4)
    findings.json                # v3: validation ledger (§5)
    evidence.json                # v3: per-requirement verification evidence (§6)
  capabilities/<capability>/spec.md   # v3: living specs — how the system behaves NOW (§4)
  decisions.md                   # v3: append-only decision log (§7)
  memory.md                      # v3: remembered facts injected by `speky prime`
  adr/NNNN-slug.md               # v3: architecture decision records
  glossary.md                    # v3: domain terms
  archive/                       # v3: nothing is moved here in milestone 1 (archive = status)
```

## 2. Item state (`status.json`)

v2 fields are read as-is; shapes differ between v2 commands, so v3 normalises on read:
`title` ← `title` | `name`; `created` ← `created` | `created_at`; `completed` ← `completed` | `completed_at`.

Lifecycle (`status`): `draft → ready → in_progress → review → completed` (v2 values) plus v3
`archived`. v2's `done` is treated as `completed`.

v3 fields (all optional):

| Field | Meaning |
|---|---|
| `kind` | `spec` or `story` (derived from folder) |
| `size` | `quick`, `small`, `change`, `epic` |
| `base_sha` | commit recorded by `speky start` — verification diffs from here |
| `gates` | `[{id, type: human|ci|pr, reason, status: open|resolved, resolved_by?, resolved_at?}]` |
| `links` | `[{type: discovered-from|caused-by|related|validates|supersedes, target}]` |
| `validation` | `{round, spec_hash, converged, converged_reason, checked_at}` |
| `verification` | `{passed, checked_at, head_sha, command, exit_code, missing: [...]}` |
| `archived_at` | set by `speky archive` |

`dependencies` (v2) are blocking links. An item is **ready to work** when every dependency is
`completed|archived` and it has no open gate.

## 3. Requirement format (in `spec.md` / `story.md`)

```markdown
## Why
## Capabilities            (or v2 "## MVP Scope")
## Constraints
## Non-goals               (or v2 "## Out of Scope")
## Success signal
## Assumptions             (informed guesses, instead of open questions)
## Requirements

### R1: Paste a video link
The app SHALL accept a YouTube or TikTok URL.

#### Scenario: Valid link
- GIVEN the import screen
- WHEN the user pastes a valid link
- THEN a recipe card draft is created
```

- Requirement header: `### R<n>: <title>`; IDs are stable inside the change and never reused.
- Every requirement needs ≥ 1 scenario with a `WHEN` and a `THEN` line.
- At most **3** `[NEEDS CLARIFICATION: …]` markers per change.
- v2 specs without IDs still load; `speky check` reports the missing structure as findings.

## 4. Living specs and deltas

`capabilities/<cap>/spec.md` = current behaviour. Requirements there use `### <CAP>-R<n>: <title>`
(e.g. `### import-R3: Paste a video link`), stable forever.

A change's `deltas/<cap>.md`:

```markdown
## ADDED Requirements
### Requirement: Paste a video link
...scenarios...
## MODIFIED Requirements
### import-R3: Paste a video link
...full new text...
## REMOVED Requirements
### import-R5: Remember me
Reason: replaced by 2FA.
```

`speky archive <id>` merges every delta: ADDED gets the next `<cap>-R<n>`; MODIFIED replaces by ID;
REMOVED deletes by ID. A delta that names an unknown ID fails the archive (nothing is written).

## 5. Validation that converges

`speky check <id>` runs the deterministic **rubric** and returns the convergence state:

| Rubric item | Severity if failed |
|---|---|
| `why` — Why/Overview section present | major |
| `scope` — Capabilities/MVP Scope present | major |
| `non_goals` — Non-goals/Out of Scope present, not empty | major |
| `requirements` — ≥ 1 `### R<n>:` requirement | blocker |
| `scenarios` — every requirement has a scenario with WHEN + THEN | blocker |
| `clarifications` — ≤ 3 `[NEEDS CLARIFICATION]` markers | blocker |
| `dependencies` — every dependency ID exists | blocker |
| `length` — ≤ `max_spec_lines` (default 250) | minor |

Agents add judgement findings with `speky finding add` (only after verifying them):
`{id: F<n>, source: rubric|agent, rubric, severity: blocker|major|minor, kind: gap|question,
text, evidence, status: open|fixed|accepted|wontfix|deferred|parked, ruling?, round, fingerprint}`.

Rules (configurable in `speky.yaml`):
- **Blocker** = an implementer must guess, and a wrong guess changes user-visible behaviour or stored data.
- Duplicate findings (same fingerprint = normalised text, or same rubric item) are rejected.
- **Questions** (`kind: question`) are capped at `max_questions` (5) per change; past the cap the agent
  must make an informed guess and record it under `## Assumptions`.
- A **round** = a `speky check` on a changed spec. Unchanged spec → cached result, no new round.
- **Converged** when no open blocker/major findings remain. When `round ≥ max_rounds` (2) and only
  questions/majors remain, `check` parks them (`status: parked`, ruling `"implementation-time
  question"`) and reports *converged by cap*; `--force` allows another round.
- Fixed/accepted/wontfix/deferred/parked findings are never re-raised (fingerprint match).

## 6. Verification and archive

- `speky start <id>` → `status: in_progress`, records `base_sha` (HEAD, or `NO_VCS`).
- `speky evidence <id> R1 --status met|partial|missing|contradicts --evidence "<file:line | test id | command>"`
- `speky verify <id> [--run "<cmd>"]` →
  - changed files since `base_sha` (committed + uncommitted + untracked),
  - runs the verify command (`--run`, else `verify_command` in `speky.yaml`) and records exit code
    and output tail,
  - **passes** only when: every requirement has `met` evidence, the command (if any) exited 0 on the
    current tree, and no open blocker finding exists. Otherwise lists what is missing.
  - `status: review` on pass.
- `speky archive <id>` → requires a passed verification of the current tree (or `--force` with a
  recorded reason), merges deltas (§4), `status: archived`.

## 7. Decisions, memory, ADRs, glossary
- `speky decide "<text>" --type decision|constraint|assumption|question|direction|event [--ref <id>]`
  appends `- <date> [<type>] D<n>: <text> (ref: <id>)` to `decisions.md`. Never edited in place.
- `speky remember "<fact>"` appends to `memory.md` (injected by `prime`).
- `speky adr new "<title>"` → `adr/NNNN-slug.md` (Status: Accepted); `speky adr list`.
- `speky term "<term>" "<definition>"` → `glossary.md`.

## 8. `speky.yaml`
```yaml
version: 3
agent_profile: conservative   # conservative | team-maintainer
id_style: sequential          # sequential | hash
max_rounds: 2
max_questions: 5
max_clarification_markers: 3
max_spec_lines: 250
verify_command: ""            # e.g. "pnpm test" — used by `speky verify` when --run is absent
harnesses: []                 # filled by `speky setup`
```

## 9. Agent protocol (JSON)

Every `--json` call prints exactly one JSON document on stdout; human text goes to stderr.
Failures: `{"ok": false, "error": {"code": "...", "message": "...", "fix": "..."}}` and exit 1.

- `speky state --json` — items `{id, kind, title, status, ready, blocked_by, gates, validation, verification}`, ready queue, open gates.
- `speky ready --json` — items ready to work, by priority then ID.
- `speky next [<id>] --json` — the one next action:
  `{action, item, why, instruction, skill, commands: [...], read: [...], done_when}` where
  `action ∈ propose | fix_structure | validate | resolve_gate | plan | start | implement | verify | archive | idle`.
- `speky check <id> --json`, `speky verify <id> --json` — results as above.
- `speky prime [--hook-json]` — ~1–2k tokens: workflow, commands, current state, memory,
  session-close protocol for the agent profile. `--hook-json` wraps it for Claude Code SessionStart.

## 10. Harness adapters — `speky setup <harness> [--check | --remove]`

| Harness | Writes |
|---|---|
| `claude-code` | `.claude/skills/speky*/SKILL.md`; `.claude/settings.json` SessionStart hook (`startup|clear|compact`) running `speky prime --hook-json`; minimal block in `CLAUDE.md` |
| `codex` | `.agents/skills/speky*/SKILL.md`; full block in `AGENTS.md` |
| `agents-md` | full block in `AGENTS.md` only (OpenCode, Factory, Cursor, Zed, …) |

Blocks are wrapped in `<!-- BEGIN SPEKY v:3 profile:<p> hash:<h> -->` … `<!-- END SPEKY v:3 -->`.
`--check` reports `missing | stale | current` per file; `--remove` deletes only SPEKY's block,
skills and hook entry. Setting up a harness also removes that harness's v2 rules block and drops it
from v2 `enabled_ides`, so the agent never loads both.

Skills (`SKILL.md`, Agent Skills format): `speky` (hub), `speky-propose`, `speky-validate`,
`speky-plan`, `speky-implement`, `speky-verify`, `speky-migrate`.

## 11. Migration from v2 — `speky migrate [--apply]`
Dry run by default. Creates `speky.yaml` and `capabilities/`; normalises `status.json` only where needed (missing
`id`, v2 status aliases such as `done`); reports duplicate IDs, unknown dependencies, specs without requirement IDs, and
completed items whose v2 drift was skipped; never deletes or rewrites user content. Seeding living
specs from completed changes needs judgement and is done by the agent with the `speky-migrate` skill.
