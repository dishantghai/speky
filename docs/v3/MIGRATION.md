# Migrating a SPEKY v2 project — checklist

Works for any project with a v2 `.speky/` folder (`specs/`, `stories/`, `context/`). Nothing is
moved, renamed or deleted: SPEKY reads the same spec and story folders, and v2's command names still
work where an equivalent exists. An agent can run this with the `speky-migrate` skill (installed by
`speky setup`); this page is the same procedure for a person.

**Already migrated with SPEKY 0.6?** Run `speky migrate` again after upgrading: it lists only the
steps that are new or still pending (for example moving the v2 product profile and tech stack into
knowledge topics), and `speky setup <harness>` refreshes the skills and blocks.

## 0. Before you start
- [ ] SPEKY with v3 commands installed: `speky next --help` works.
- [ ] `git status` — note uncommitted files that are **not** yours to commit. Don't stage them.
- [ ] Work on a branch: `git checkout -b chore/speky-v3`.

## 1. Deterministic migration
- [ ] `speky migrate` — dry run; read `pending`, `issues`, `judgement`.
- [ ] Fix any `issues` it lists (unreadable status files, duplicate IDs, unknown dependencies,
      cycles) — by hand, they need a person's judgement.
- [ ] `speky migrate --apply` — creates `.speky/speky.yaml` and `.speky/capabilities/`, fixes
      only status files that need it (missing `id`, v2 aliases such as `done`), and moves v2 data
      that has a new home: the product profile (`context.json` → `knowledge/product.md`), tech stack
      and key decisions (→ `knowledge/tech.md`; both are loaded in every session), pending
      `validation_actions.json` (→ each spec's findings ledger) and `testing/config.yaml`
      (→ `speky.yaml` `testing`, with the detected test commands).
- [ ] `speky migrate` again → `"done": true`, nothing pending.

## 2. Agent instructions (the biggest token win)
v2 wrote a ~1,000-line rules file (CLAUDE.md, .windsurfrules, .cursorrules, …) loaded on every
agent turn. v3 replaces it with a ~10-line block plus skills loaded on demand.
- [ ] `speky setup <harness>` for each tool the team uses: `claude-code`, `codex`, `cursor`,
      `windsurf`, `vscode` (Copilot), `antigravity`, `agents-md` (`speky setup --list`).
      The old v2 rules file is backed up to `.speky/backups/`; rules you added under
      `# USER RULES` are kept above the new block.
- [ ] `speky setup <harness> --check` → `"status": "current"` for every file.
- [ ] Read the new CLAUDE.md / AGENTS.md: your own rules are still there, v2's are gone.
- [ ] v2's rules for other tools are cleaned when you set that tool up (`.cursorrules`,
      `.windsurfrules`: SPEKY's part removed, your rules kept; `.agent/rules/0*-speky-*.md`: removed,
      backed up). Files for tools nobody uses any more can simply be deleted.

## 3. Settings
- [ ] `speky test init` detects the test, coverage and e2e commands; check `verify_command` in
      `.speky/speky.yaml` (e.g. `pnpm test --run`) — `speky verify` runs it.
- [ ] Choose `agent_profile`: `conservative` (agents propose commits) or `team-maintainer`.

## 4. Judgement work (agent with the `speky-migrate` skill, or a person)
- [ ] **Suspect completions** — items `speky migrate` lists under `check_suspect_completions`
      were marked completed although v2's drift review skipped CODE_BEHIND / TECH_DEVIATION
      findings. For each: check the code; file real gaps as stories
      (`speky new story "..." --type bug --discovered-from <id>`).
- [ ] **Living specs** — group completed items into capabilities (user-visible areas) and write
      `.speky/capabilities/<capability>/spec.md` describing what the code does **today**
      (`### <capability>-R<n>:` requirements with WHEN/THEN scenarios). Start with the areas you
      will change next; this can be done incrementally.
- [ ] Mark each handled task: `speky migrate --done check_suspect_completions` (likewise
      `add_requirement_ids`); `seed_living_specs` clears itself once capability specs exist and
      `speky capabilities --json` reports `"valid": true`.
- [ ] **Open items** (draft/ready/in_progress): `speky check <id>`; add `### R1:` requirement IDs
      and scenarios where the rubric asks. Don't rewrite intent.
- [ ] **Hand-kept notes** — if the project kept its own state/plan/log/knowledge files or an
      instruction-file protocol, map them onto SPEKY (the `speky-migrate` skill has the table):
      milestones → `speky phases`, checklists → `speky task`, learnings → `speky remember --topic`,
      session notes → `speky handoff`, things only the owner can do → `speky owner add`, ADR folder →
      `paths.adr_dir`, IDs of screens/docs → `refs:`, per-kind definitions of done → `done_checks:`.

## 5. Verify
- [ ] `speky state --json` lists every v2 spec and story with the right status.
- [ ] `speky next --json` returns a sensible action.
- [ ] `speky prime` prints a short workflow summary.
- [ ] v2 names still work: `speky status`, `speky sequence`, `speky validate-spec <id>`.
- [ ] `speky capabilities --json` → `"valid": true`.
- [ ] Rule files are stable: note `shasum CLAUDE.md`, run a few commands (`speky status`,
      `speky sequence`), and check the hash didn't change; `speky setup <harness> --check` → current.
- [ ] A fresh agent session in the repo picks up SPEKY (Claude Code: the SessionStart hook runs
      `speky prime`) — e.g. `claude -p "What should I work on next? Don't change anything."`
- [ ] Spot-check the agent's judgement: for 3–4 filed gap stories, confirm the cited code really
      shows the gap.

## 6. Commit
- [ ] `speky decide "Migrated to SPEKY v3" --type event`; `speky handoff --summary "..."` so the next
      session picks up from here.
- [ ] Stage only `.speky/`, the harness files (`.claude/`, `.agents/`) and `CLAUDE.md` / `AGENTS.md`
      — never unrelated work: `git add .speky .claude CLAUDE.md && git commit`.
