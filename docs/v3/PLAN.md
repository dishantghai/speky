# SPEKY v3 — Plan

Branch: `speky-v3-plan`. Status: **discussion / planning — nothing implemented yet.**
This file records everything agreed or proposed so far so nothing is lost between sessions.
Sections marked *(open)* are still under discussion.

---

## 0. What SPEKY is for (from `project_ops/prompt_first.md`)

An intent-driven, AI-assisted, spec-driven development framework for a solo founder or a team of 2–35:

- State an intent → SPEKY asks clarifying questions, elaborates the prompt, routes work to the right
  role (PM, architect, research, UX/UI, coding, review, QA), monitors it, and keeps the human in the loop
  only for macro decisions (tech stack, design, scope).
- Specs that humans and AI both read; minimal number of documents; everything in one git repo.
- Context gathered, cached and kept current, so AI doesn't forget on large codebases; efficient token use.
- Drift management across specs / stories / plans / code; tech debt; migrations; release; security.
- Tech-, product-, scale- and **harness-agnostic**.

---

## 1. Evaluation of SPEKY v2 (current `main`)

### 1.1 The central problem: the brain is blind
SPEKY v2's own LLM calls are single-shot, tool-less prompts. It does the code-dependent reasoning without
seeing code, while the IDE agent (which can read code, run tests, use git) only receives instructions.

| Step | What the model actually sees | Where |
|---|---|---|
| `spec` | no code (`existing_code = ""  # TODO ... via MCP`) | `speky.py:5635` |
| `plan` | spec + product blurb + 4-key tech stack | `speky.py:5841` |
| `sync` | first 100 **file names** | `speky.py:9322` |
| drift on `complete` | files picked by keyword-matching spec words to **file names**, 6 extensions only, first 200 lines of top 12 | `speky.py:7957` |
| `review` | stub — "requires MCP integration (coming soon)" | `speky.py:9412` |

No `git diff` is used anywhere. The parts that work best (`poc-import` writing a `task.md` for the IDE agent;
host mode) are the ones that delegate reasoning to the agent.

### 1.2 Other findings
- **Context bloat.** ~34 KB rules file (`.cursorrules` ≈1,000 lines), mostly SPEKY command docs, rewritten
  after most commands and loaded on every agent turn — contradicts the token-efficiency goal.
- **Destructive writes.** `_write_file_rules` overwrites the whole file (`speky.py:3068`) though the template
  claims user rules are preserved (`speky.py:4670`) → wipes an existing `CLAUDE.md`. The `vscode` target
  writes markdown into `.vscode/settings.json` (`speky.py:2986`).
- **77 hard character truncations** (`[:2000]` etc.) silently drop content instead of retrieval.
- **State scattered** over `context.json`, per-item `status.json`, `config.yaml` (hand-rolled writer that
  stores Python list reprs → the `enabled_ides` crash), `manifest.yaml` (custom YAML parser, `speky.py:18706`),
  `models.yaml` (real PyYAML).
- **Feature sprawl vs. missing essentials.** ~40 commands (epics, phases, sequence, backlog, renumber,
  reconcile, design sync…) but no web research, no code-review agent, no QA/security agent, no intent router.
- **Web-app assumptions.** Tech stack fixed to frontend/backend/database/deployment; drift scans 6 extensions;
  plans sized in human hours (2–8 h, <40 h); specs capped at "1–2 user stories".
- **Engineering base.** One 21k-line file, a 259-method class, zero tests, CI smoke test is `|| true`;
  42 of 47 LLM calls parsed from free text by line prefixes at temperature 0.7; 19 bare `except:`;
  default model `claude-sonnet-4-20250514`.
- **Correctness bugs.** Next spec ID = `len(dirs)+1` (collides after deletion); `_find_spec_dir` uses
  prefix/substring match (`speky.py:13028`); `is_story = id[0].isalpha() and len>=4`; `speky commit` runs
  `git add -A`.

### 1.3 Keep from v2
- `speky_llm.py` router (multi-provider, fallbacks) — clean.
- Non-interactive design: `-y`, `--answer`, exit code 4.
- Spec template's **Out of Scope** + **Open Questions**, and resolving open questions before planning.
- The `poc-import` pattern: SPEKY writes a task file, the agent does the code reading.

---

## 2. v3 direction (agreed in discussion)

### 2.1 Invert the roles
The coding agent (any harness) does the reasoning with real tools; SPEKY is a **deterministic state and
protocol engine**: IDs, status transitions, dependency graph, templates, validation rules, human gates,
git anchors, ledgers. The core makes **no LLM calls**.

### 2.2 Harness-agnostic surfaces (lowest common denominator first)
| Layer | Role | Reach |
|---|---|---|
| Core CLI + library | Owns all state (spec frontmatter, IDs, statuses, deps, AC IDs, git base SHA, findings ledger, gates). No LLM. | Every harness (all can run shell) |
| `speky next` protocol | CLI prints the next step as a short instruction + JSON ("Draft spec 004. Read X, Y. Write to Z. Then run `speky check 004`.") | Every harness — the workflow lives in tool output, not in a rules file |
| MCP server | Same core operations as typed tools | Most harnesses |
| Skills / `AGENTS.md` | Workflow instructions as `SKILL.md` + a small managed block in `AGENTS.md` | Most current harnesses (support uneven — verify per harness) |
| Thin adapters | `speky install --harness claude-code\|codex\|cursor\|gemini\|…` | Per harness, tens of lines each |
| Headless runner | SPEKY's own small tool-using agent loop for CI / no harness, via the existing router | Optional |

### 2.3 LangGraph / Deep Agents — decision: not now
- Deep Agents is the same pattern as the harnesses (planning tool, FS, subagents, long system prompt):
  similar token use, and we'd re-implement editing, search, permissions and sandboxing.
- Harnesses are often on flat-rate subscriptions; a custom agent bills per API token.
- SPEKY's own workflow is a small state machine → plain Python in the core.
- Revisit only if the headless runner becomes a long-running, parallel, resumable orchestrator; design the
  core state machine so LangGraph could wrap it later.

### 2.4 Token strategy (harness-independent)
1. Precise context packets from `speky next`: files to read, acceptance criteria, verification command.
2. Replace the 34 KB rules file with a 1–2 KB managed pointer block (between markers, never overwrite
   user content).
3. Cached codebase index updated incrementally from `git diff`, not LLM re-summaries.
4. Deterministic checks (sections, AC format, deps) before any LLM call.
5. Cheap models for cheap steps (router supports it): triage, dedupe, classification.
6. Exploration in subagents that return summaries.
7. Stable prompt prefixes for provider prompt caching.

### 2.5 Drift and completion anchored on git + tests
- `implement` records the base commit SHA.
- `complete` diffs from it and checks each acceptance criterion against the diff and test results.
- Persist AC → files/tests links; completion gated on evidence, not on running `complete`.

### 2.6 One source of truth
Status, priority, dependencies, phase/epic live in YAML frontmatter of `spec.md` / `story.md`, parsed by one
real YAML library. Every acceptance criterion gets an ID (e.g. `AC-003.2`). Everything else is derived.

### 2.7 Scope — capability parity is a hard rule *(user decision, 2026-10-14)*
**v3 must not lose a single capability that v2 has.** v3 makes each one better, more flexible and
harness-agnostic. What changes is *how much is enforced*: because current harnesses already plan,
track todos, use subagents and read code, many steps that a year-old spec-driven framework made
mandatory become **optional or right-sized** (on by default only where they pay off), never removed.

- Core loop: **intent → spec → validate → plan → implement (agent) → verify → done**.
- Every v2 capability stays reachable; see the parity inventory in §2.8. Epics, phases and sequence
  keep their commands but may share one dependency-graph engine underneath.
- Design and testing stay first-class, packaged as modules that can be switched on or off.
- Research, review and QA are added as agent steps on top of the core, not as Python prompt functions.
- Plans use **agent-sized tasks with a verification command**; hour estimates become optional.
  Tech stack is free-form (the v2 frontend/backend/database/deployment keys stay as optional fields).

### 2.8 v2 capability parity inventory (nothing may be dropped)
Every row must have a v3 home before v3 replaces v2. "How it changes" is the proposal, not final.

| v2 capability (commands) | v3 home / how it changes |
|---|---|
| `init` (idea, research docs, paste notes, clarifying questions, product profile, tech-stack discussion, specs from research, POC prompt), `init --from-project` | Kept. Agent reads the repo; questions limited to what code can't answer (intent, rationale, rejected options) |
| `spec` (with research input, backlog anti-rot check, phase prompt) | Kept. Agent-drafted with code access; deterministic template + frontmatter |
| `validate-spec`, `validate-story` (quick/interactive, AI fixes, defer, split story, cross-spec overlap, tech-decision violations, dependency checks) | Kept. Rubric + findings ledger + convergence (§3) |
| `plan` (spec/story, `--check`, open-question resolution) | Kept. Agent-sized tasks with verify commands |
| `story` (feature/bug/enhancement/tech_debt/spike, `--epic`, `--spec`), `adopt` | Kept. Same types; adopt becomes `speky check` + register |
| `epic`, `epics` | Kept |
| `implement` (context chain, TDD mode, IDE open) | Kept. Emits a context packet; records base SHA |
| `complete` (drift categories, interactive resolution, sync, next-step recommendations, `--test`) | Kept. Drift from git diff + AC evidence (§2.5) |
| `commit` (generated message, `--edit`) | Kept. Stages only files tied to the item, not `git add -A` |
| `status`, `sync`, `review`, `cleanup`, `context` | Kept. `review` becomes real (diff-based); `sync` incremental from git |
| `backlog` (deferred items, promote to story) | Kept. Merged with the findings ledger's deferred items |
| `import`, `import-status`, `reconcile` (external docs → specs, mismatch resolution) | Kept |
| `poc-import` (agent task files, resume, conflicts, merge/deprecate specs) | Kept — already the right pattern |
| `sequence`, `infer-deps`, `mark-foundation`, `reset-deps`, `fix-circular-deps`, `renumber` | Kept on one dependency-graph engine; renumber becomes rarely needed with collision-free IDs |
| `phases` (list/show/status/start/complete/guide/create/suggest) | Kept |
| `decisions` | Kept. Becomes the decision log feeding validation and context |
| `design` (init/import/analyze/link/resolve/validate/status/sync) | Kept as the design module |
| `test` (init/gen/run/coverage/status/e2e/link/gaps/recommend/setup/tdd-red/tdd-green/tdd-status/triage…) | Kept as the testing module |
| `config` (IDEs, model, providers), multi-provider router, fallbacks | Kept. IDE list becomes harness adapters |
| `host` mode, `-y`, `--answer`, `--answers`, `--non-interactive`, exit code 4 | Kept and extended (`speky next`, `--json`) |
| IDE rule generation (Windsurf, Cursor, Claude Code, VS Code, Antigravity) | Kept as adapters, but managed blocks only — never overwrite user content |

---

## 3. Validation that converges (fixes the `validate-spec` loop)

### 3.1 Why v2 never stops finding gaps
1. Earlier findings never reach the validation prompt: `ValidationSession.get_context_for_ai()` is only
   used by the per-gap suggestion helpers, `add_decision()` is never called, and handled action items
   are deleted from `validation_actions.json` — so the next run raises the same gaps in new words.
   *(Fixed in v3/build: v2 `validate-spec`/`validate-story` now use the v3 ledger, pass earlier
   findings to the model, run at temperature 0, skip unchanged specs and stop at the round cap.)*
2. Open-ended prompt ("Gaps", "Suggestions") with no severity, rubric, or definition of done.
3. Temperature 0.7 → different findings each run.
4. AI fixes lengthen the spec → more surface to criticise.
5. Score only decreases; any gap → `is_valid = false`; no stopping rule.

### 3.2 Design
- **Fixed rubric** (~10–12 named checks), each pass/fail with a quoted line as evidence: every story has
  testable ACs with IDs; error/empty states defined; data entities named; out-of-scope stated; dependencies
  exist; no conflict with tech decisions/other specs; blocking open questions listed; … Every gap maps to a
  rubric item. Free-form suggestions: separate, capped at 3, never blocking.
- **Severity bar.** *Blocker* = "an implementer must guess, and a wrong guess changes user-visible behaviour
  or stored data". Only blocker/major block planning; minors shown once.
- **Thorough first pass.** 2–3 independent lenses in parallel at temperature 0 (completeness/testability;
  consistency with tech decisions and other specs; edge cases/failure modes), merged and deduped.
- **Findings ledger** with stable IDs, fingerprints and status (fixed / accepted risk / won't fix /
  deferred / implementation-time question). Fed into the prompt ("do not re-raise"), deduped in code with a
  cheap-model check.
- **Re-check only what changed.** Unchanged spec hash → cached result, no LLM call. Otherwise re-check
  changed sections + confirm fixed items stay fixed.
- **Fixes narrow, not grow.** Prefer moving items to Out of Scope / Open Questions; enforce a length budget.
- **Explicit convergence signal**, default max 2 rounds, 3rd needs `--force`:
  > Converged: round 2 found 0 new blockers and 2 minor nits. More validation is unlikely to help.
  > Next: `speky plan 004`.
- **"Good enough to plan"** — gaps that only matter while coding go to the ledger as implementation-time
  questions.

---

## 4. Ideas from other frameworks *(research done 2026-10-14 — proposal, not yet agreed)*

Sources read (shallow clones, latest `main` as of 2026-10-14):
- **Beads** (`steveyegge/beads`, now `gastownhall/beads`): README, AGENTS.md, docs/core-concepts
  (ids, dependencies, graph links), workflows (gates, molecules, formulas, wisps, todo), multi-agent
  coordination, `ide-setup.md`, `bd prime` source (session-close protocol), `remember`, `lint`, `doctor`.
- **BMAD-METHOD** (v7 alpha on `main`): all 30 skills listed and their descriptions; read in depth: `bmad`
  hub + help routing, `bmad-spec` (Spec Law, memlog), `bmad-build` (workflow, routing, review/triage,
  loopbacks), `bmad-build-auto` contract, `bmad-code-review` (lenses, triage), `bmad-ticket`
  (tickets.toml, slicing rules), `bmad-architecture` (spine), `bmad-deep-recon`, `bmad-retrospective`,
  `bmad-project-context` + "Theory of Project Context", `bmad-eval`, customization model, planning-path docs.
- **OpenSpec**: README, concepts (specs vs changes, delta specs, schemas), agent contract (JSON shapes,
  diagnostics), commands (`propose/apply/verify/archive`).
- **Spec Kit**: README, command templates `specify`, `clarify`, `checklist`, `analyze`, `converge`,
  constitution template, extensions/workflows layout.
- **squid** (`iusztinpaul/squid`): README, `squid-plan`, `squid-grilling`, `squid-review`,
  `pr-reviewer` agent, `squid-clean-harness`.
- **Superpowers** (`obra/superpowers`): all 15 skills listed; read in depth: `using-superpowers`,
  `brainstorming`, `writing-plans`, `subagent-driven-development` (+ reviewer prompt, scripts),
  `verification-before-completion`, `systematic-debugging`, `receiving-code-review`,
  `finishing-a-development-branch`, `writing-skills`, hooks.
- External: ETH Zurich "Evaluating AGENTS.md" (arXiv 2602.11988); Böckeler, "Understanding SDD: Kiro,
  spec-kit and Tessl" (martinfowler.com); 2026 SDD critiques; Agent Skills (`SKILL.md`) adoption.

### 4.1 Must adopt — each fixes a known SPEKY problem

**A. Living specs + change deltas (OpenSpec) → specs stay true after `complete`.**
v2 specs describe one feature and go stale once it ships; drift has nothing current to compare against.
- `specs/<capability>/spec.md` = how the system behaves *now* (source of truth).
- Each v2 spec/story becomes a **change**: proposal + delta spec (`ADDED / MODIFIED / REMOVED
  Requirements`) + design + tasks. On completion the delta merges into the living spec; the change is
  archived with full history.
- Requirements use `### Requirement:` + `#### Scenario:` (GIVEN/WHEN/THEN) and RFC 2119 words; each gets a
  stable ID → these are the acceptance-criterion IDs of §2.6.
- *Dependencies are enablers, not gates* (OpenSpec schema): an artifact DAG tells what can be written
  next, without forcing an order.
- Böckeler's critique applies here: Spec Kit and Kiro are "spec-first only, not spec-anchored over time".
  Living specs make SPEKY spec-anchored.

**B. Agent protocol as JSON (OpenSpec agent contract, BMAD `render_skill` "read and follow", Beads `prime`).**
This is the concrete shape of `speky next` (§2.2):
- `speky status --json` → artifacts with `done/ready/blocked/skipped`, `requires`, `missingDeps`;
  the first `ready` artifact is the one to write next.
- `speky instructions <artifact> --json` → template, rules, context files, dependencies, output path.
- One JSON document per call on stdout; human text on stderr; failures as a diagnostic envelope
  `{severity, code, message, target, fix}` and fixed exit codes (extends v2's exit code 4).
- `speky prime` (Beads): ~1–2k tokens of workflow + memories, injected by a SessionStart hook on
  startup, clear **and after compaction** (Beads and Superpowers both do this), so agents never lose the workflow.

**C. Validation that converges — concrete rules (Spec Kit, BMAD, squid, Superpowers).**
Extends §3.2 with proven mechanics:
- *Spec Kit `specify`:* make informed guesses and record them under **Assumptions**; at most **3**
  `[NEEDS CLARIFICATION]` markers per spec, keep only the 3 most critical.
- *Spec Kit `clarify`:* a fixed **ambiguity taxonomy** (scope, data model, UX flow incl. error/empty
  states, non-functional, integrations, edge cases, constraints, terminology, completion signals,
  placeholders) marked Clear/Partial/Missing; **max 5 questions per session**, ranked by Impact ×
  Uncertainty, asked **one at a time with a recommended answer**, written back into the spec after each
  answer; stop when critical ones are resolved or the user says done. → This *is* the rubric of §3.2.
- *Spec Kit `checklist`:* "unit tests for English" — checks requirement quality, never implementation.
- *Spec Kit `analyze`:* strictly read-only, ≤ 50 findings, overflow summarised.
- *BMAD triage:* every finding is **verified** before it counts; verdicts `high/medium/low/false/
  maybe-false`; reviewer-assigned severities are ignored; **reject `low` findings whose fix adds
  complexity**; group by root cause; never drop a finding silently; a triage log carries prior verdicts
  forward (`carried`) so re-runs don't re-litigate.
- *squid:* binary **Blocker / Nit** with concrete triggers; **max 3 reject rounds per feature**, then
  `USER ACTION REQUIRED`.
- *Superpowers:* fix loop capped at 5 rounds, escalate to a stronger model at round 4, then
  **adjudicate and park with a ruling** (`Ruling: what — why — cost if wrong`); a deferred minor
  never re-enters the loop.
- *BMAD self-validate:* two passes — **coherence** (Spec Law) and **preservation** (every load-bearing
  source claim landed somewhere; drops are logged, not silent).

**D. Verification instead of guessed drift (Spec Kit `converge`, OpenSpec `verify`, Superpowers).**
- Gap types `missing / partial / contradicts / unrequested`, each traced to a requirement ID with file
  evidence and a severity (Spec Kit). v2 drift names stay as aliases: CODE_BEHIND→missing/partial,
  SPEC_BEHIND & SCOPE_CREEP→unrequested, TECH_DEVIATION→contradicts, DOC_STALE kept.
- **Append-only** remediation tasks; when nothing is left, files stay **byte-for-byte unchanged** and a
  clean result is reported.
- Three dimensions: completeness, correctness, coherence (OpenSpec).
- **Evidence before claims** (Superpowers): "tests pass" needs fresh command output; "agent completed"
  needs a VCS diff; "requirements met" needs a line-by-line checklist. Completion claims are not evidence.
- Combined with §2.5: diff from the recorded base SHA bounds the code scope.

**E. Decision memory that survives sessions (BMAD memlog, squid ADR + glossary, Beads `remember`).**
- Append-only **decision log** (`decision | constraint | assumption | question | direction | event`, one
  line each). Specs are *derived* from it, so independent steps never overwrite each other (BMAD).
  This replaces v2's unused `ValidationSession.decisions_made` and feeds "don't re-raise" (§3.2).
- **Stable IDs never reused or renumbered** (BMAD `CAP-N`, `AD-n`; Beads ids).
- **ADRs** for decisions with lasting consequences; **glossary** for domain terms (v2's terminology
  mappings become it). Settled ADRs are not re-opened by grilling or validation; a change that
  contradicts an accepted ADR needs a superseding ADR (squid).
- Architecture as a **spine of invariants** only — "could two independently built units choose
  incompatibly?" — with `Binds / Prevents / Rule` per decision; structure that code owns is seed, not
  spine (BMAD). Upgrades v2 `tech_decisions.md`.
- `speky remember "<fact>"` → injected by `prime`, with an optional size budget (Beads).

**F. Small, verified context — not dumps (BMAD Theory of Project Context + ETH study).**
Evidence: context files that restate the repo give no success gain and cost ≈ +20% inference
(arXiv 2602.11988); a compressed index of knowledge the model *lacks* went 53% → 100% (BMAD-cited study);
agents skip retrieval they must choose to do.
- Store only what code can't say: intent, rationale, rejected options, policy, divergent conventions,
  pitfalls **from observed failures** (`speky record` / Beads-style). Never store file maps (they rot
  fastest) — this changes v2 `codebase.md`.
- Every pointer names an **observable trigger** (a path, file type, task), never a judgement call.
- Audit question per line: "would removing this change agent behaviour?" A working rule is removed only
  when its subject is gone or a human retires it. Audits end smaller or equal.
- Managed blocks between versioned markers with a hash (`<!-- BEGIN SPEKY v:1 profile:minimal hash:… -->`),
  with `--check` (missing/stale/current) and `--remove` touching only the block (Beads). No instruction in
  two loaded files.
- Profiles: **minimal** block (points to `speky prime`) for hook-capable harnesses, **full** for
  AGENTS.md-only harnesses (Beads).

**G. Harness adapters as recipes (Beads `bd setup <recipe>`, Superpowers, OpenSpec 30+ tools).**
`speky setup <harness>` with `--check/--remove`, per-harness files (skills dir, hooks, rules), a
`--list`, and custom recipes. Ship workflows as `SKILL.md` skills (Agent Skills format, readable by 30+
tools; skills dirs vary: `.agents/skills/`, `.claude/skills/`, `.gemini/skills/` …). Per-harness
tool-name mapping files like Superpowers' `references/<harness>-tools.md`. Avoid harness-only features
inside skill bodies (e.g. variable substitution works only in Claude Code).

**H. Work graph: ready queue, typed links, gates (Beads, BMAD tickets).**
- `speky ready` = items with every blocker closed (v2 `sequence` already topo-sorts; expose the frontier).
- Typed links: `blocks`, `parent-child`, `related`, `discovered-from`, `caused-by`, `validates`,
  `supersedes`. **`discovered-from`** lets the agent file found work (→ v2 backlog) instead of scope creep.
- **Gates as blockers**: `human` (macro decisions: stack, design, scope), `gh:run` (CI green),
  `gh:pr` (merged), `timer` — work leaves the ready set until the gate closes; no polling (Beads).
- Per-entry fields from BMAD `tickets.toml`: `verify` (one runnable check), `covers` (requirement IDs),
  `after` (real prerequisites only), `risk`, `hitl`, `unknown` (blocks until settled),
  `plan_checkpoint`, `done_checkpoint`. Estimates only when the user gives one (BMAD/Superpowers: no
  time estimates by default).
- Slicing rules worth keeping: first story is the **tracer bullet**; next is the least certain one;
  **lanes** (stories touching the same code run in order); "split, never shrink" (no "placeholder for
  now"); optional closing **refactor sweep** fed by deferred review findings.
- **Collision-free IDs**: fixes the `len+1` bug; sequential human IDs for solo use, hash-suffixed for
  teams/branches (Beads hash IDs), configurable.

**I. Writer ≠ judge, and right model per role (squid, Superpowers, BMAD).**
- Verification and review run in a **fresh context** that never saw the implementation session; the
  implementer never spawns its own reviewer.
- Per task: one review with two verdicts — **spec compliance** and **quality**; one broad review at the end.
- Review input is a **diff file + brief + report path**, never pasted history (Superpowers measured a
  42k-char dispatch that was 99% pasted history).
- Model per role via the existing router: strongest model for planning/review judgement, mid-tier for
  implementation, cheapest for mechanical tasks; "turn count beats token price" (Superpowers, squid).

**J. Right-sizing / intent router (BMAD planning path, Superpowers brainstorming, Spec Kit entry points,
OpenSpec lite vs full).**
`speky do "<intent>"` sizes the work and says so (user can override):
quick/clear → just do it + verify · small change → story + verify · one session → spec(lite) + plan ·
epic → spec + slices · project → product brief/PRD + architecture spine + epics. Separate entry points
for **bug fix** (root cause first — Superpowers systematic-debugging: no fix without investigation; after
3 failed fixes, question the architecture) and **idea assessment**. This is the orchestrator from the
original vision.

**K. Agent authority policy (Beads profiles, Superpowers stop rules).**
`agent.profile = conservative | minimal | team-maintainer` decides whether agents may commit/push;
default conservative. Unattended runs make **rulings, not stalls**, and stop only for: irreversible or
destructive actions, security-sensitive actions, side effects outside the worktree (push, merge,
publish), or a plan so broken every path is a guess. A session-close protocol ("before saying done:
close items, run checks, report git status") replaces v2 `git add -A`.

**L. Durable progress ledger for long runs (Superpowers, BMAD).**
A per-plan ledger file (`Task N: complete`, fix rounds, rulings, base SHA). After compaction, trust the
ledger + `git log` over memory — re-running finished tasks was the costliest failure Superpowers observed.
Plan files carry a resumable `status` (`draft → ready → in-progress → in-review → built → done |
blocked`) so any harness resumes from the right step (BMAD build-auto table).

**M. Test the skills themselves (Superpowers `writing-skills`, BMAD `bmad-eval`).**
Skills are tested like code: baseline vs bare model, variant vs stripped version, rubric quality, and
**trigger accuracy** of the description; pressure scenarios that make the agent want to skip a step.
Plus host-mode replay tests for the CLI (§1.2 "zero tests").

### 4.2 Adopt as optional modules (keep v2 parity, off by default or on demand)
- **Unattended pipeline** — BMAD `build-auto` worker contract / squid `implement-night`: one worker per
  ticket, terminal status in the plan, orchestrator reads it. Matches the "automations" goal.
- **Research module** — BMAD `deep-recon` epistemics: never conclude from training data alone; project
  context shapes *questions*, never *evidence*; every claim has publisher/date; freshness windows; option
  to **draft a prompt for the user's own deep-research tool** and import the report. Fills the
  research-agent gap.
- **Retrospective** at epic close from evidence (plans, diffs, commits), with action items checked next
  epic (BMAD).
- **Correct course** — impact of a requirement change across PRD/specs/architecture/UX (BMAD); upgrades
  v2 `reconcile`.
- **Worktree per change** (Superpowers, squid) and a finish-branch menu (merge / PR / keep).
- **Workflow templates** (Beads formulas/molecules, Spec Kit workflows) for repeatable flows such as
  releases; **ephemeral runs** for ops checklists (Beads wisps).
- **Extension hooks** `before_* / after_*` per command (Spec Kit) — how the design and testing modules
  plug in.
- **Layered customisation**: defaults → team override → personal override, merged (BMAD TOML layers).
- **External trackers** (GitHub/Jira/Linear) as stores behind the same ticket model (BMAD `bmad-ticket`
  configs); **cross-repo planning store** later for teams (OpenSpec Stores, beta).
- **Visual companion / mockups** during discovery (Superpowers brainstorming) — ties to the design module.
- **Session diagnosis** — why a run went wrong, cost, repeated work (Superpowers `diagnosing-superpowers`).
- **Compaction of closed items** into summaries (Beads) — only if archives grow large.

### 4.3 Skip (fluff for SPEKY, or conflicts with its goals)
- Dolt database / federation / HTTP backend (Beads) — plain files in git are enough for 1–35 people.
- Named personas with greetings and communication styles, party mode, brainstorming-technique
  libraries, PRFAQ theatre (BMAD) — keep the *roles* (PM, architect, research, UX, review, QA) as skills,
  drop the personas.
- Rigid "MUST invoke a skill if 1% chance" enforcement (`using-superpowers`) — conflicts with
  right-sizing; triggers should be observable.
- Branch-per-spec and many generated markdown files per feature (Spec Kit) — Böckeler: "verbose and
  tedious to review … rather review code".
- Stack-specific scaffold library (squid) — SPEKY is stack-agnostic; could come later as community
  templates.
- Output-compression plugins (caveman, used by squid) — orthogonal to SPEKY.
- Mandatory TDD for everything (Superpowers iron law) — keep v2 `--tdd` and the testing module as an option.

---

## 5. What no longer needs enforcing *(research track 2)*

### 5.1 Evidence
- Current harnesses already ship, natively or via plugins: plan mode, todo tracking, subagents, skills
  (`SKILL.md`, 30+ tools), hooks (incl. SessionStart after compaction), memory files, background tasks,
  worktrees, code-review commands.
- SDD critiques in 2026 converge on: **overhead on small work** ("a four-phase process for a two-line fix
  is theatre"), **spec drift/staleness**, **over-specification** (pseudo-code specs = writing it twice),
  "waterfall with markdown", review burden. Böckeler: Kiro produced 4 user stories + 16 acceptance
  criteria for a small bug ("sledgehammer to crack a nut"); agents still often didn't follow all the
  instructions; specs live per change request, not per feature.
- Defences that hold: specs matter for multi-session / multi-agent / multi-person work, because the spec
  survives the session and the transcript doesn't. → Proportionality is the answer.

### 5.2 v2 behaviour → v3 enforcement level (nothing removed)
| v2 behaviour | Why it's no longer mandatory | v3 level |
|---|---|---|
| Rules file says "refuse to implement without a spec" | Harness + right-sizing handles small work; forcing specs is the top SDD complaint | Off; `speky do` sizes work instead |
| `sync` writes `codebase.md` file map | Agents explore code themselves; stored maps rot and cost tokens | Off for harness mode; on for headless/API mode; stores only non-derivable facts |
| Plans with 3–8 tasks and hour estimates | Harness plan mode + todos handle micro-steps; estimates are noise | Plan = decisions + verify commands; detailed tasks only for epics/unattended runs; estimates opt-in |
| Open questions must be resolved before planning | Most can be informed guesses | Only blockers block; rest → Assumptions (Spec Kit ≤3 markers) |
| Every story validated | Simple stories don't need it | Quick check by default; full validation on risk/size |
| `implement` writes a big context chain into rules files | Agent reads files itself | Short context packet of pointers + AC + verify command |
| Interactive drift review item by item | Batch triage with recommended actions is faster | Summary + recommended action; interactive on request |
| Generated commit messages, IDE opening | Harnesses do this | Kept, optional |
| TDD red/green tracking | Agents can follow TDD skills | Kept as `--tdd` option |
| Phase guides / `context` generation | Generated on demand | Kept, on demand |

### 5.3 Still worth enforcing (harnesses don't do it)
- Durable intent and decision memory across sessions, people and harnesses (decision log, ADRs, glossary).
- Requirement IDs and traceability from requirement → code → test.
- Verification evidence before anything is marked done.
- Human gates on macro decisions (stack, design, scope, merge/release).
- Cross-spec consistency and dependencies; living specs updated at completion.
- Convergence caps on validation/review loops.
- Agent authority policy for commit/push.

---

## 6. First milestone *(proposed, updated after research)*
Core state engine (living specs + changes, decision log, stable IDs, ready queue) + `speky status/
instructions/next --json` + `speky prime` + converging validator (taxonomy, ≤5 questions, ledger, caps) +
`speky setup <harness>` for two harnesses with managed blocks.
Exit test: one change goes intent → spec → validate → plan → implement → verify → archive (living spec
updated) in two different harnesses, with zero v2 capabilities lost (checked against §2.8).

## 7. Decisions *(agreed 2026-10-14)*
| Question | Decision |
|---|---|
| First harnesses | **Claude Code + Codex** (hook-capable + AGENTS.md/skills profiles). Cursor, Gemini CLI next. |
| Code location | New package **`speky_core/`** in this repo (a `speky/` package would shadow `speky.py`, the v2 entry point). v3 commands are subcommands of the same `speky` CLI; v2 commands keep working on the same folders. |
| ID style | **Sequential by default**, hash-suffixed IDs optional (teams/branches). |
| Requirement format | **BMAD five-field kernel** (Why, Capabilities, Constraints, Non-goals, Success signal) for the change proposal; **OpenSpec `Requirement`/`Scenario`** with stable IDs for requirements. |

Execution order (agreed): (1) fix v2 destructive bugs on `main` as small branches; (2) parity safety net
(host-mode replay tests per §2.8 row); (3) v3 contracts (`docs/v3/CONTRACTS.md`); (4) milestone-1
vertical slices; (5) pilot in both harnesses; (6) v2 → v3 migration.

### Still open
- Which §4.2 modules come right after milestone 1.
- Migration details for v2 `.speky/` projects.

## 9. Status *(2026-10-14)*

Branch `v3/build` (worktree `../speky-v3`); `main` is an ancestor, so it fast-forwards.

**Done and verified**
- v2 fixes (released in v0.5.1): collision-free IDs, `commit` without `git add -A`, VS Code rules to
  `.github/copilot-instructions.md`, managed rules block; v2 `validate-spec`/`validate-story` converge.
- v2 parity net: 23 end-to-end command tests with a scripted model (`tests/parity/`).
- v3 core (`speky_core/`, CONTRACTS.md): state, `next`/`prime` protocol, rubric + ledger convergence,
  evidence-gated `verify`, `archive` into living specs, decisions/memory/ADR/glossary, gates and
  links, `setup` for claude-code / codex / agents-md, `migrate`. 95 tests in total.
- Packaging: `speky_core` + skills ship in the wheel and the Nuitka binaries (build/release workflows).
- Real-harness pilots (headless Claude Code, prompts with no SPEKY instructions):
  1. small feature → story, assumptions recorded, tests first, evidence, verify, archive (30 turns,
     $0.69); found 4 bugs, all fixed with regression tests;
  2. change-sized request → spec, converged in 1 round, plan, 4 assumptions instead of stalling,
     MODIFIED/ADDED living spec, verify, archive (24 turns, $0.60, no errors);
  3. docstring typo → no SPEKY item, verified directly (5 turns, $0.18).
  The SessionStart hook injected `speky prime` in every run.

- spayce_electron migrated (branch `chore/speky-v3`, 2 commits, not pushed): CLAUDE.md 1,107 → 10
  lines; 12 living-spec capabilities (69 requirements, valid); 12 suspect v2 completions checked by
  an agent with the speky-migrate skill — 6 false alarms, 4 real gaps + 3 more found; 8 stories
  filed; 4 of the agent's claims spot-checked in the code and confirmed. A fresh Claude Code session
  then recommended the right next item unprompted. Bugs this surfaced were fixed in SPEKY:
  migrate --done, CONTRACTS.md URL refs, v2 testing-context bloat + duplicate markers, v2
  `sequence` crash on specs without `name`, self-ignoring backups, `speky capabilities` validator.

**Not verified**
- Codex live run (CLI not installed here); its files are covered by unit tests and the Agent
  Skills format check.

**Parity notes (§2.8)**: every v2 command still runs unchanged on the same folders; design, testing,
phases, epics, import, poc-import keep their v2 implementation for now.

## 10. Milestone 2: continuity *(agreed 2026-10-14)*

Goal: SPEKY becomes the only store for everything an agent needs to pick up at the right point after
compaction or in a new session, replacing hand-kept mechanisms like aIDE's `ops/agent/` (STATE, PLAN,
LOG, KNOWLEDGE, owner-next-steps) and its AGENTS.md session protocol. Stores are **markdown files SPEKY
parses** (people and agents can edit them by hand; SPEKY reads the edits back), not hidden JSON.

| # | Feature | Replaces in aIDE |
|---|---|---|
| 1 | `speky handoff` / `speky checkpoint`: log entry, regenerated state snapshot, optional `Handoff:` commit | the AGENTS.md §3 handoff |
| 2 | PreCompact hook → `speky checkpoint --auto` (mechanical snapshot before compaction) | "treat any milestone as a possible last moment" |
| 3 | `prime` session-start block: last handoff, commits since, uncommitted files, last test run, "trust git" rule | AGENTS.md §1 steps 1–5 |
| 4 | Roadmap: milestones (phases/tracks) with gates + lightweight tasks `W<n>` (todo/doing/done/deferred, nested, promotable to story/spec) in `.speky/roadmap.md`; `next` falls back to tasks | PLAN.md |
| 5 | Knowledge by topic in `.speky/knowledge/<topic>.md`; `always` topics injected, others indexed with a read-when trigger; promote to ADR | KNOWLEDGE.md |
| 6 | Owner actions `O<n>` in `.speky/owner.md` (checkboxes + notes the owner writes) | ops/temp/owner-next-steps.md |
| 7 | ~~Format-specific importer~~ *(dropped: it would bake one project's conventions into SPEKY)*. Adoption of hand-kept notes is done with the generic commands, driven by the `speky-migrate` skill; `speky roadmap fmt` gives IDs to tasks written by hand | — |
| 8 | Block goes into AGENTS.md when CLAUDE.md only imports it | — |
| 9 | Per-label done checks (`run`, `file`, `manual`) enforced by `verify` | AGENTS.md §4b UI definition of done |
| 10 | References (`adr:0021`, `screen:RV-E2-held`) checked against configurable patterns; `paths.adr_dir` + project ADR template | screen-ID and ADR citations |

Project-specific rules (aIDE's constitution, architecture rules, UX process) stay in the project's own
AGENTS.md outside SPEKY's block; SPEKY only provides the mechanisms. **Nothing in SPEKY is specific to
aIDE**: aIDE is retrofitted onto these generic features afterwards, as any project would be.

## 11. Milestone 3: one SPEKY *(proposed 2026-10-14)*

**Goal (owner):** the new SPEKY is robust, complete and unambiguous. No v2 command is kept alive only for
compatibility: every v2 capability becomes a native feature — one data model, one command style
(non-interactive, `--json` everywhere), reasoning done by the agent through skills. When every row below
has its new home and its parity test, the v2 implementation (`speky.py`'s 21k lines, 176 interactive
prompts, 18 commands that call a model themselves) is deleted.

**Rules that make it unambiguous**
- One store per concept; one command family per concept; one way to do each thing.
- The CLI never asks questions and never calls a model. Questions to the user and judgement belong to the
  agent, guided by a skill; SPEKY records the results.
- Every command: `--json` output, stable error codes with a fix, idempotent where possible.

| v2 capability | New home (command · data · skill) | Notes |
|---|---|---|
| `init` (idea interview, product profile, tech stack, research docs, specs from research, `--from-project`) | `speky init` (scaffold + setup) · `knowledge/product.md` (always) + ADRs/`knowledge/tech.md` · **speky-init** skill (≤5 questions, reads repo/docs, proposes first specs/tasks) | product profile and tech stack stop being a separate JSON |
| `spec`, `story` (types, `--epic`, `--spec`, `--files`), `adopt` | `speky new spec\|story` (+ `--epic --related --files --labels --phase`) · items · **speky-propose** | hand-made folders are recognised automatically; `adopt` = `speky check` |
| `validate-spec`, `validate-story` | `speky check` · findings ledger · **speky-validate** | one validator |
| `plan` | **speky-plan** skill + a plan rubric in `speky check` (every requirement covered, each task has a verify command) | |
| `implement` (context chain, IDE handoff, `--tdd`) | `speky start` + `speky context <id>` (packet: doc, plan, deps, epic, phase, design, files, ADRs, knowledge triggers) · `--tdd` → red/green evidence | no rules-file rewriting |
| `complete` (drift detection + resolution) | `speky verify` + review step in **speky-verify** (fresh-context diff review → findings) + `speky archive` | evidence-based instead of keyword-guessing |
| `commit` | `speky commit <id>` (message from item, requirements met, evidence; explicit files) | no model call |
| `status` | `speky status` (human) / `--json` | `state` becomes an alias |
| `sync` (codebase.md) | knowledge topics with read-when triggers, maintained by the agent | stored file maps rot (ETH study); the agent reads code live |
| `review` | `speky review [<id>]`: re-run verification of completed items (tests, evidence still valid) | the v2 stub becomes real |
| `cleanup` | `speky cleanup` (`--json`, dry-run default) | |
| `backlog` | `speky task` (tasks and deferred items in one list) · `speky backlog` = deferred view | |
| `import`, `import-status`, `reconcile` | `speky import <path>` (register sources + manifest) · `speky import status` · **speky-import** skill (docs → specs/tasks/knowledge/ADRs; reconcile → findings/tasks) | |
| `poc-import` | `speky import <path> --code` · **speky-import** (code mode: features, conflicts as findings, resume from manifest) | |
| `sequence`, `infer-deps`, `mark-foundation`, `reset-deps`, `fix-circular-deps` | `speky deps add\|remove\|clear\|foundation\|cycles` · `speky order [--export]` · inference in **speky-plan** | |
| `renumber` | **dropped**: IDs are references (decisions, links, commits, log); order lives in deps/priority (`speky order`) | owner agreed |
| `decisions` (tech decisions) | `speky decide` / `speky adr` / `knowledge/tech.md` | |
| `config` (IDEs, model, providers) | `speky setup <harness>` · `speky config get\|set` (speky.yaml) · `speky config --model/--providers` for `speky run` | |
| `design` (init, import, analyze with vision, link, resolve, validate, status, sync) | `speky design add\|link\|status` (assets + links to items) · **speky-design** skill (agent analyses images, maintains the design-system doc, conflicts → findings, resolutions → decisions) | |
| `phases` (create, start, complete, list, show, status, guide, suggest) | `speky phases` (same manifests; `deliverable`, `verify`, `check`) · guide = `speky context --phase` · suggest in **speky-plan** | |
| `context` | `speky context <id>\|--phase <id>` | |
| `test` (init, gen, run, coverage, status, e2e, link, gaps, recommend, tdd-red/green, triage, …) | `speky test init\|run\|status\|gaps\|coverage` (runner detection, results, requirement↔test links via evidence) · **speky-test** skill (write tests, e2e, TDD, triage failures → findings) | |
| `epic`, `epics` | `speky epic add\|show\|list\|attach\|detach` (same manifests) | |
| `host` mode | **dropped**: existed so an agent could answer v2's model prompts; in the new SPEKY the agent is native | |
| `-y`, `--answer`, `--non-interactive` | not needed: every command is non-interactive | |

**Decisions (owner, 2026-10-14):**
- **Built-in runner:** `speky run` — a small, provider-agnostic agent loop inside SPEKY that runs the same
  skills through the model router (API key or Claude subscription) with file and command tools, so SPEKY
  also works without a coding agent. It is the only place SPEKY talks to a model or asks the user.
- **Familiar names, one implementation each:** `speky spec "x"` = `speky new spec "x"`, `speky status`,
  `speky phases`, `speky epic`, `speky test`, … Removed names print what replaces them.
- **Dropped:** `renumber` (use `speky order`), host mode (the agent is native), sync's `codebase.md`
  (knowledge topics instead).

**Build order:** (1) foundation: phases on v2's manifests (real YAML), tasks in the backlog, handoff/
checkpoint, knowledge, owner actions, refs, done checks, harness + prime/next; (2) one command surface for
every row above; (3) skills speky-init, speky-import, speky-design, speky-test + updates; (4) `speky run`;
(5) `speky migrate` for v2 data; (6) delete the v2 implementation, parity tests rewritten against the new
commands; (7) retrofit aIDE, real-agent pilots, release.

## 8. Sources
- Beads — https://github.com/steveyegge/beads (docs: https://beads.gascity.com/)
- BMAD-METHOD — https://github.com/bmad-code-org/BMAD-METHOD (docs: https://docs.bmad-method.org/)
- OpenSpec — https://github.com/Fission-AI/OpenSpec
- Spec Kit — https://github.com/github/spec-kit
- squid — https://github.com/iusztinpaul/squid
- Superpowers — https://github.com/obra/superpowers
- Gloaguen et al., "Evaluating AGENTS.md" — https://arxiv.org/abs/2602.11988
- Böckeler, "Understanding Spec-Driven-Development: Kiro, spec-kit, and Tessl" —
  https://www.martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html
- SDD critiques 2026 — https://alexcloudstar.com/blog/spec-driven-development-2026/ ,
  https://nimbalyst.com/blog/spec-driven-development-with-coding-agents/ ,
  https://dev.to/krlz/spec-driven-development-in-2026-what-it-is-the-tooling-and-how-teams-actually-use-it-2fk2
- Agent Skills adoption — https://noqta.tn/en/news/skill-md-open-standard-30-ai-coding-tools-adoption-2026 ,
  harness skills directories: https://git.secluded.site/agent-skills/blob/72563aede0d7ddaab38774894f13262fcca0b884/vendor/impeccable/HARNESSES.md
