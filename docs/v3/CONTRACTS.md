# SPEKY v3 — Contracts

Status: **implemented** (`speky_core/`, the only implementation since v0.7; v2's code was removed once
every v2 command had a home — see `tests/capabilities/test_v2_capability_homes.py`). This file is the
reference for the on-disk layout, the item lifecycle, the agent protocol (JSON), the convergence rules,
continuity and the harness adapters. Background and rationale: `PLAN.md`.

## 0. Principles
- **The core makes no LLM calls.** The coding agent (any harness) does the reasoning; SPEKY owns
  state, IDs, rules, gates and evidence. The one exception is `speky run` (§14), SPEKY's own agent for
  working without a coding agent.
- **One data model with v2.** A v2 spec folder (`.speky/specs/NNN-slug/`) or story folder
  (`.speky/stories/X001-slug/`) *is* a change. SPEKY adds files and fields; it never moves, renames or
  deletes v2 files, and keeps v2's formats where both exist (phase manifests, `backlog.json`, design
  `manifest.json`), so a teammate on an older SPEKY still reads them.
- **Nothing is enforced that a harness already does.** Gates exist only where §5.3 of the plan says so.
- **Nothing lives only in a conversation.** Everything needed to continue is in `.speky/` (§12).

Package: `speky_core`; `speky.py` is only the entry point. v2's command names still work as aliases
(`validate-spec` = `check`, `sequence` = `order`, …); `renumber`, `host` and `sync` were removed and say
what replaces them.

## 1. Layout — where every non-code artifact lives

The same in every SPEKY project. `speky layout` prints the effective map, `speky layout --check` reports
artifacts kept where SPEKY doesn't look, and `speky prime` tells agents to use these homes. Code is not
covered: where code goes is the project's business. Only the rows marked *override* can move, with
`paths.<key>` in `speky.yaml` (for tooling that already depends on another folder).

| Kind | Default | Holds | Override |
|---|---|---|---|
| settings | `.speky/speky.yaml` | SPEKY settings (§8) | — |
| specs | `.speky/specs/<NNN-slug>/` | spec.md, plan.md, research.md, deltas/, findings.json, evidence.json, status.json | — |
| stories | `.speky/stories/<X001-slug>/` | the same for stories (F/B/E/T/S) | — |
| capabilities | `.speky/capabilities/<capability>/spec.md` | living specs: how the system behaves now (§4) | — |
| epics | `.speky/epics/<id-slug>/` | shared docs and member stories | — |
| phases | `.speky/phases/<id>/manifest.yaml`, `roadmap.yaml` | phases, deliverables (the gate), order (§13) | — |
| tasks | `.speky/backlog.json`, `.speky/tasks.md` | tasks W<n> and deferred items; tasks.md is the view | — |
| knowledge | `.speky/knowledge/<topic>.md` | project knowledge by topic (§7) | — |
| decisions | `.speky/decisions.md` | decision log, append-only | — |
| adr_dir | `.speky/adr/` | ADRs `NNNN-slug.md` (+ `template.md`) | `paths.adr_dir` |
| glossary | `.speky/glossary.md` | domain terms | — |
| owner | `.speky/owner.md` | actions only the owner can take (§12) | — |
| log | `.speky/log.md`, `.speky/state.md` | session log; where things stand (§12) | — |
| design_system | `.speky/design/system.md` | the design-system document | `paths.design_system` |
| design_screens | `.speky/design/screens/<screen-id>/` | one folder per screen (images, HTML, `screen.yaml`); catalogue `.speky/design/screens.md` | `paths.design_screens` |
| design_reviews | `.speky/design/reviews/` | design and UX reviews `<date>-<screen>.md` | `paths.design_reviews` |
| design_docs | `.speky/design/` (`brief.md`, `narratives/`, `presentations/`, `feedback/`, guides) | design briefs, narratives, tool guides, pages shown to the owner, user feedback | — |
| imports | `.speky/imports/<name>/` | imported documents and prototype code | — |
| context | `.speky/context/` | v2 project documents (product, architecture, tech decisions) | — |
| research | `.speky/research/` | research not tied to one change (per change: `research.md`) | `paths.research` |
| testing | `.speky/testing/` | recorded test runs (per machine, git-ignored) | — |

Also: `.speky/design/icons/`, `.speky/design/manifest.json` (technology, design conflicts, components),
`.speky/checkpoint.json` (per machine, git-ignored), `.speky/backups/` (git-ignored).

**Screens.** A screen's folder name is its ID, cited as `screen:<id>` (built-in reference). `screen.yaml`:
`id, title, kind (hifi|lofi|wireframe|flow|reference), states, items, status (draft|approved|superseded|rejected), source,
review, approved_by, supersedes / superseded_by`. `speky design screen add <id> <files> [--for <item>]
[--state …] [--move]`, `… approve <id> --by <owner>`, `… supersede <id> --by <new-id>`,
`… review <id> --file <review.md> --result pass|fail`, `… list`. An approved screen is never overwritten:
a new iteration gets a new ID. Screens can be grouped: a folder with `screen.yaml` is a screen at any depth
(`screens/run-view/v2-E/held/`), and a `screens.yaml` in a folder lists several screens kept as single
files there (`[{id, title, files: [empty.png], status, …}]`); `speky design screen add … --group run-view/v3`.
In the default root a top-level folder without metadata is a screen too (ID = folder name). With
`paths.design_screens` set, design files lying directly in it are screens (ID = slug of the file name).
`adr:<NNNN>` and `screen:<id>` are built-in references (`speky refs`).

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
- **Done checks** (`done_checks` in `speky.yaml`, §8) add per-label conditions: a command that must
  pass, a file that must exist, or a manual check recorded as evidence `check:<name>`
  (`speky evidence <id> check:screenshot --status met --evidence "..."`). `verify` fails until they hold.
- **UI changes** (a label in `ui_labels`, default ui/ux/frontend, or a `## Design` section) must cite the
  design they implement in `## Design` — `screen:<id>` or design files inside the design locations (§1) —
  or say "No new design needed: <why>"; a design-tool link alone is not enough (export it into the repo).
  Cited screens must be approved by the owner before the change is built, and the project needs a
  design-system document. The rubric checks this (`design`, `design_refs`, `design_location`,
  `design_in_repo`, `design_system`; major). `speky next` returns a `design` action (speky-design skill +
  the `ui` playbook) until the design is cited, in place, approved and a design system exists; at
  plan/start/implement it adds the design system and the cited screens to `read`. In a project with UI,
  an unlabelled change whose text reads user-facing gets a `ui_label` finding.
  `speky new … --labels ui` adds a `## Design` section; `speky design status` lists UI items still
  needing a design.
- **Tasks**: `speky verify W<n>` (or `speky task done W<n> --verify`) runs the verify command and the done
  checks of the task's labels (not `all`), and closes the task only when both pass. Manual checks:
  `speky evidence W<n> check:<name> --status met --evidence "..."`.
- `speky archive <id>` → requires a passed verification of the current tree (or `--force` with a
  recorded reason), merges deltas (§4), `status: archived`.

## 7. Decisions, memory, ADRs, glossary
- `speky decide "<text>" --type decision|constraint|assumption|question|direction|event [--ref <id>]`
  appends `- <date> [<type>] D<n>: <text> (ref: <id>)` to `decisions.md`. Never edited in place.
- `speky remember "<fact>" --topic <topic> [--always | --read-when "<trigger>"]` adds a dated line,
  newest first, to `knowledge/<topic>.md`. A topic marked `<!-- speky: always -->` is printed by
  `prime` in every session; `<!-- speky: read when <trigger> -->` is listed with its trigger.
  `speky knowledge list|show|promote <topic>` (promote turns a mature topic into an ADR).
- `speky adr new "<title>"` → `<adr_dir>/NNNN-slug.md` from the project's own template when
  `<adr_dir>/template.md` exists; `speky adr list`.
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
# optional
testing:                      # `speky test init` detects these
  coverage_command: "pytest -q --cov"
  coverage_threshold: 80
  e2e_command: "npx playwright test"
paths:                        # move an overridable artifact (§1); everything else has a fixed home
  adr_dir: docs/adr
  design_system: docs/ux/DESIGN.md
  design_screens: [docs/ux/screens]
playbooks:                    # how this project does a kind of work, by label (items and tasks: --labels)
  ui:
    skill: screen-design-narratives
    read: [docs/ux/stitch.md]
    note: "Never show the owner a UI without a recorded UX review."
extra_skills:                 # skills besides SPEKY's; `speky setup` installs them for every harness
  - ~/.claude/skills/screen-design-narratives   # (skipped where the tool already sees it)
refs:                         # `<kind>:<id>` references checked by `speky refs`
  adr: {glob: "docs/adr/{id}-*.md"}
  screen: {file: "docs/ux/screens/README.md", contains: "`{id}`"}
done_checks:                  # per label (`all` = every item); see §6
  ui:
    - {name: screenshot, manual: "attach a screenshot of the changed screen"}
    - {name: e2e, run: "npx playwright test --grep {id}"}
  all:
    - {name: changelog, file: "docs/changes/{id}*.md"}
```
`speky config get|set <key> [<value>]` reads and writes these (dotted keys; strings stay strings).

## 9. Agent protocol (JSON)

Every `--json` call prints exactly one JSON document on stdout; human text goes to stderr.
Failures: `{"ok": false, "error": {"code": "...", "message": "...", "fix": "..."}}` and exit 1.

- `speky state --json` — items `{id, kind, title, status, ready, blocked_by, gates, validation, verification}`, ready queue, open gates.
- `speky ready --json` — items ready to work, by priority then ID.
- `speky next [<id>] --json` — the one next action:
  `{action, item, why, instruction, skill, commands: [...], read: [...], done_when}` where
  `action ∈ propose | design | fix_structure | validate | resolve_gate | plan | start | implement | archive |
  task | gate | phase | idle` (`task`: the next task W<n>; `gate`/`phase`: the current phase's
  deliverables need verifying / the phase can be completed).
- `speky check <id> --json`, `speky verify <id> --json` — results as above.
- `speky prime [--hook-json]` — workflow, **Pick up here** (last handoff, drift since then, last test
  run, next actions recorded), owner actions waiting, the next action, always-loaded knowledge and
  the triggers of the other topics, session-close protocol for the agent profile. `--hook-json`
  wraps it for Claude Code SessionStart.
- `speky context <id>|--phase <id> [--full]` — a context packet: what to read and why, layer by layer
  (knowledge → tech decisions/ADRs → design → phase → epic → related specs → dependencies → the item →
  playbooks for its labels → files behind the references it cites, e.g. `screen:RV-E2-held`).
- A labelled item or task whose label has a playbook gets it in `next`: the instruction names the
  playbook, `also_skills` lists its skill, `read` adds its files.

## 10. Harness adapters — `speky setup <harness> [--check | --remove]`

| Harness | Writes |
|---|---|
| `claude-code` | `.claude/skills/speky*/SKILL.md`; `.claude/settings.json` hooks: SessionStart (`startup|clear|compact`) → `speky prime --hook-json`, PreCompact → `speky checkpoint --auto`, UserPromptSubmit → `speky checkpoint --turn-start`, Stop → `speky checkpoint --stop` (record check, §12); minimal block in `CLAUDE.md` (or in `AGENTS.md` when `CLAUDE.md` only imports it) |
| `codex` | `.agents/skills/speky*/SKILL.md`; full block in `AGENTS.md` |
| `cursor`, `windsurf` | `.agents/skills/`; full block in `AGENTS.md`; v2's `.cursorrules` / `.windsurfrules` cleaned (SPEKY part removed, your rules kept) |
| `vscode` (alias `copilot`) | `.github/skills/`; full block in `.github/copilot-instructions.md` |
| `antigravity` | `.agent/skills/`; full block in `.agent/rules/speky.md`; v2's generated `.agent/rules/0*-speky-*.md` removed (backed up) |
| `agents-md` | full block in `AGENTS.md` only (OpenCode, Factory, Zed, …) |

Blocks are wrapped in `<!-- BEGIN SPEKY v:3 profile:<p> hash:<h> -->` … `<!-- END SPEKY v:3 -->`.
`--check` reports `missing | stale | current` per file; `--remove` deletes only SPEKY's block,
skills and hook entry. Setting up a harness also removes that harness's v2 rules block and drops it
from v2 `enabled_ides`, so the agent never loads both.

Skills (`SKILL.md`, Agent Skills format): `speky` (hub), `speky-init`, `speky-propose`,
`speky-validate`, `speky-plan`, `speky-implement`, `speky-test`, `speky-verify`, `speky-import`,
`speky-design`, `speky-migrate`. `speky setup --list` shows the harnesses.

## 11. Migration from v2 — `speky migrate [--apply]`
Dry run by default. Creates `speky.yaml` and `capabilities/`; normalises `status.json` only where needed (missing
`id`, v2 status aliases such as `done`); moves v2 data that has a new home — `context.json` product
profile → `knowledge/product.md`, tech stack and key decisions → `knowledge/tech.md` (both loaded every
session), pending `validation_actions.json` → findings ledgers, `testing/config.yaml` → `speky.yaml`
`testing`; reports duplicate IDs, unknown dependencies, specs without requirement IDs, and completed
items whose v2 drift was skipped; never deletes or rewrites user content. Judgement tasks (seeding
living specs, checking suspect completions, mapping hand-kept notes) are listed for the agent and done
with the `speky-migrate` skill; `speky migrate --done <task>` marks one handled. Idempotent: a second
run lists only what is still pending.

## 12. Continuity — nothing depends on the conversation

| File | Written by | Read by |
|---|---|---|
| `checkpoint.json` | `speky checkpoint` (PreCompact hook: `--auto`), `handoff`, `test run` | `prime` |
| `log.md` | `speky handoff` — dated entry: summary, done, learned, next, watch-outs, mechanism changes | people, `prime` (latest entry) |
| `state.md` | `speky handoff` (regenerated) | `prime` ("Where things stand") |
| `owner.md` | `speky owner add|done`, and the owner by hand (ticks, indented notes) | `prime` (open items + new notes) |
| `knowledge/*.md` | `speky remember --topic` | `prime` (always topics; triggers of the rest) |

**Nothing lives only in the chat (record check).** When the owner sends a message, SPEKY fingerprints its
records by kind — owner (`owner.md`), decisions (`decisions.md`, ADRs), knowledge (`knowledge/`, glossary,
AGENTS.md/CLAUDE.md), plan (backlog, phases, change documents, findings), state (`state.md`, `log.md`) — in
`.speky/turn.json` (per machine), and notes what the message itself must leave behind: a standing
instruction ("from now on…", "always/never…", not in questions) → knowledge; feedback ("confusing", "doesn't
work"…) → plan or owner; an answer to an open "Decide:" item (named by ID or sharing its words) → owner; a
link or account → knowledge. When the agent is about to stop, its reply is read too: hand-offs to the owner
(actions, approvals, recommendations) → owner, decisions or plan; assumptions and promises ("I assumed…",
"next I'll…") → decisions, plan or state. If a kind of record that should have changed did not, the stop is
blocked once with the exact commands, or the agent says in one line why nothing needs recording. Unrelated
edits do not count. Before compaction, `speky checkpoint --auto` also saves what was in flight — the owner's
latest request and the agent's step list (TodoWrite / TaskCreate) — and `speky prime` shows it after
compaction. Claude Code runs it through hooks; other harnesses get the same rule in
their SPEKY block. `record_check: false` in `speky.yaml` turns it off.

`speky handoff --summary … --done … --learned … --next … --watch … [--title …] [--commit] [--no-tests]`
or `--file notes.md` (sections `## Summary`, `## Done`, `## Learned`, `## Next`, `## Watch out for`).
It runs the verify command unless `--no-tests`. Under `agent_profile: team-maintainer` it commits the
`.speky/` records as `Handoff: <title>`. `prime` compares the checkpoint with git and reports drift
(new commits, uncommitted files, stale test result); when they disagree the agent trusts git and the
tests and corrects the record with a new handoff.

## 13. Planning: phases, tasks, epics, dependencies, references

- **Phases** (`speky phases list|add|start|deliverable|verify|check|complete|suggest`): the gate of a
  phase is its deliverables; a deliverable with `run:` is verified by running it (`phases check`),
  others by recorded evidence (`phases verify <phase> <D#> --evidence …`). `complete` refuses while
  deliverables are unverified or tasks of the phase are open (`--force "<reason>"` records a decision).
- **Tasks** W<n> (`speky task add|start|done|defer|todo|promote|list`): small planned work without a
  folder; `--phase`, `--epic`, `--parent`, `--refs adr:0021,screen:RV-1`. `promote` turns one into a
  story or spec. `next` offers tasks of the current phase when no item is ready.
- **Epics** (`speky epic add|show|attach|detach|list`): stories that share docs and context.
- **Dependencies** (`speky deps add|remove|clear|foundation|cycles`, `speky order [--export]`):
  `order` sorts by dependencies, foundation flag and priority; `--export` writes `roadmap.md`.
- **References** (`speky refs`): finds `<kind>:<id>` in SPEKY's files and reports those that don't
  resolve under `refs:` (§8). `item:<id>` is built in.

## 14. `speky run` — SPEKY's own agent

For working without a coding agent. A JSON tool loop over the model router (`speky_llm`: any provider
in `~/.speky/models.yaml`, an API key in the environment or the project's `.env`, or a Claude
subscription through the `claude` CLI — `speky config model claude-code/sonnet`). Tools: read/list/
search/write/edit files (confined to the repository, never `.git/`), any `speky` command, `run`
(the project's test commands and read-only git unless `--allow-shell`), `skill`, `ask_user` (needs a
terminal; otherwise the model records an assumption), `finish`. It follows the same skills and
`speky next` protocol as a coding agent. `speky run --next` works through `speky next` until idle.
