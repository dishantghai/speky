# SPEKY

**Spec-driven development for AI coding agents.**

SPEKY keeps a project's changes, requirements, decisions, evidence and working memory in `.speky/`,
and the coding agent you already use (Claude Code, Codex, Cursor, Windsurf, Copilot, Antigravity,
OpenCode, …) does the work by following SPEKY's skills and the `speky` CLI. No API key is needed for
that. Without a coding agent, `speky run` is SPEKY's own agent.

What it gives you:

- **Changes with testable requirements.** Each spec or story has `### R1:` requirements with
  WHEN/THEN scenarios.
- **Validation that converges.** A rubric plus a findings ledger. Findings are never raised twice,
  and validation stops after two rounds unless you ask for more.
- **Nothing is done without evidence.** Every requirement needs a test, file or command as proof,
  and `speky verify` re-runs the tests on the current code.
- **Living specs.** Archiving a change merges it into `.speky/capabilities/`, so the specs describe
  what the system does now.
- **Continuity.** Handoffs, checkpoints, knowledge topics and owner actions mean a new session (or
  one after context compaction) picks up at the right point without the old conversation.
- **Planning when you need it.** Phases with deliverables as their gate, tasks, epics, dependencies
  and implementation order.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dishantghai/speky/main/scripts/install.sh | bash
```

Or download a binary from [releases](https://github.com/dishantghai/speky/releases/latest)
(`speky-macos-arm64`, `speky-macos-x86_64`, `speky-linux-x86_64`, `speky-windows-x86_64.exe`),
`chmod +x` it and put it on your `PATH`. From source: `pip install .` (Python 3.8+).

## Start

```bash
cd your-project && git init                      # if it isn't a repo yet
speky init --harness claude-code                 # new project
speky init --from-project --harness claude-code  # existing code: reads README, manifests, tests
speky migrate                                    # SPEKY v2 project: dry run, then --apply
```

Then ask your agent for what you want built. Use the harness for your tool (`speky setup --list`):

| Tool | `speky setup …` | What it writes |
|---|---|---|
| Claude Code | `claude-code` | skills in `.claude/skills/`, a short block in `CLAUDE.md`, hooks: `speky prime` at session start, `speky checkpoint` before compaction |
| Codex | `codex` | skills in `.agents/skills/`, a block in `AGENTS.md` |
| Cursor / Windsurf | `cursor` / `windsurf` | skills in `.agents/skills/`, a block in `AGENTS.md` (v2's `.cursorrules` / `.windsurfrules` cleaned) |
| VS Code + Copilot | `vscode` (or `copilot`) | skills in `.github/skills/`, a block in `.github/copilot-instructions.md` |
| Antigravity | `antigravity` | skills in `.agent/skills/`, `.agent/rules/speky.md` |
| Anything that reads AGENTS.md | `agents-md` | a block in `AGENTS.md` |

`speky setup <tool> --check` says whether the files are current; `--remove` takes out only what SPEKY
wrote. If `CLAUDE.md` only imports `@AGENTS.md`, the block goes into `AGENTS.md`.

## How work flows

The agent asks `speky next --json` for the one next action. The answer names the skill to follow,
the commands to run and when the action is done. Work is sized first:

| Size | Use |
|---|---|
| Quick, clear fix | Just do it, then run the tests. |
| Small planned work | A task: `speky task add "…"`, then `speky task done W1 --verify`. |
| Changes behaviour | A story or spec: `speky story "…"` / `speky spec "…"`. |

A change goes through:

```bash
speky spec "Paste a video link"        # .speky/specs/001-paste-a-video-link/spec.md
speky check 001                        # rubric + findings; says when validation has converged
speky plan 001                         # planning packet; the agent writes plan.md
speky start 001                        # in progress; records the base commit
speky evidence 001 R1 --status met --evidence "tests/test_import.py::test_valid_link"
speky verify 001                       # runs verify_command; passes only with evidence for every requirement
speky archive 001                      # merges the change into the living specs
speky commit 001                       # commit message built from the item; secrets are never staged
```

`speky context 001` lists what to read for an item and why: knowledge, decisions and ADRs, design,
phase, epic, related specs, dependencies and the item itself. `speky status` shows the whole project.

## Memory and continuity

Nothing important lives only in a conversation:

```bash
speky remember "WebContentsView replaced BrowserView" --topic tech --always   # knowledge/<topic>.md
speky remember "Sidecar must be rebuilt after kernel changes" --topic kernel --read-when "touching the kernel"
speky decide "Use SQLite, not SurrealDB" --type decision      # decisions.md (append-only)
speky adr new "Event bus for panels"                          # ADRs (paths.adr_dir, your template)
speky owner add "Create the Apple developer account"          # owner.md: only the owner can do it
speky handoff --summary "…" --next "…" --learned "…"          # log.md + state.md (+ test run)
speky prime                                                   # what a new session reads first
```

`speky prime` (run automatically at session start in Claude Code) prints where to pick up: the last
handoff, what changed since then in git, the last test result, the next actions that were recorded,
owner actions waiting, and the knowledge marked `always`. A checkpoint is saved before every
compaction.

## Planning

```bash
speky phases add "Workbench" --id phase-1      # .speky/phases/<id>/manifest.yaml
speky phases deliverable phase-1 "Walkthrough test passes" --run "pnpm test:e2e"
speky phases start phase-1
speky phases check phase-1                     # runs deliverable commands; others need evidence
speky phases complete phase-1                  # refused while deliverables or tasks are open
speky task add "Wire SSE" --phase phase-1 --refs adr:0021
speky epic add "Checkout"                      # stories that share docs and context
speky deps add 003 001                         # 003 depends on 001; `speky order [--export]` for the order
```

## Settings: `.speky/speky.yaml`

```yaml
verify_command: "pnpm test"         # what `speky verify` runs
agent_profile: conservative         # or team-maintainer (commits handoffs, archives verified work)
testing: {coverage_command: "…", coverage_threshold: 80, e2e_command: "npx playwright test"}
paths: {adr_dir: docs/adr, design_system: docs/ux/DESIGN.md}
playbooks:                          # a kind of work with its own workflow, by label (--labels ui)
  ui: {skill: screen-design-narratives, read: [docs/ux/stitch.md]}
extra_skills: [~/.claude/skills/screen-design-narratives]   # installed by `speky setup` for every tool
refs:                               # `speky refs` checks adr:0021, screen:RV-1, … resolve
  adr: {glob: "docs/adr/{id}-*.md"}
done_checks:                        # extra conditions for `speky verify`, by label
  ui: [{name: screenshot, manual: "attach a screenshot of the changed screen"}]
```

`speky config get|set <key> [<value>]` edits it. The full reference is
[docs/v3/CONTRACTS.md](docs/v3/CONTRACTS.md).

## More commands

| Area | Commands |
|---|---|
| Tests | `speky test init|run|coverage|gaps|link`, `speky test red|green` (TDD proof) |
| Design | `speky design …`: design assets, the design system, links to specs, conflicts |
| Import | `speky import add|link|status|reconcile`: documents and prototype code |
| Housekeeping | `speky review` (re-check completed work), `speky cleanup` (clutter to a recoverable backup), `speky backlog` |
| References | `speky refs`, `speky link <id> --type discovered-from --to <id>`, `speky gate …` |

Every command takes `--json` and prints one JSON document; errors carry a `fix`. Nothing prompts.
v2's command names still work where an equivalent exists (`validate-spec` = `check`,
`sequence` = `order`, …). `speky --help` lists everything.

## No coding agent? `speky run`

```bash
speky config model claude-code/sonnet          # your Claude subscription via the `claude` CLI
speky run "Add a CSV export to the reports page"
speky run --next                               # work through `speky next` until idle
```

`speky run` follows the same skills and protocol as a coding agent. File access is confined to the
repository, and shell access is limited to the project's test commands and read-only git unless you
pass `--allow-shell`. Any provider works: Anthropic, OpenAI, Gemini, OpenRouter, Groq, DeepSeek,
Mistral, Ollama, LM Studio, any OpenAI-compatible server. Keys come from the environment or the
project's `.env`. See [MODELS.md](MODELS.md).

## Docs

- [docs/v3/CONTRACTS.md](docs/v3/CONTRACTS.md): files, formats, commands and the agent protocol
- [docs/v3/MIGRATION.md](docs/v3/MIGRATION.md): moving a SPEKY v2 project
- [docs/v3/PLAN.md](docs/v3/PLAN.md): design notes and the reasoning behind them
- [MODELS.md](MODELS.md): models for `speky run`
- [DEPLOYMENT.md](DEPLOYMENT.md): building and releasing
- [docs/v2/](docs/v2/README.md): the v2 documentation (archive) and where each v2 command went
