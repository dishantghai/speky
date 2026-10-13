# Migrating a SPEKY v2 project to v3 — checklist

Works for any project with a v2 `.speky/` folder (`specs/`, `stories/`, `context/`). Nothing is
moved, renamed or deleted: v3 reads the same spec and story folders, so every v2 command keeps
working afterwards. An agent can run this with the `speky-migrate` skill (installed by
`speky setup`); this page is the same procedure for a person.

## 0. Before you start
- [ ] SPEKY with v3 commands installed: `speky next --help` works.
- [ ] `git status` — note uncommitted files that are **not** yours to commit. Don't stage them.
- [ ] Work on a branch: `git checkout -b chore/speky-v3`.

## 1. Deterministic migration
- [ ] `speky migrate` — dry run; read `pending`, `issues`, `judgement`.
- [ ] Fix any `issues` it lists (unreadable status files, duplicate IDs, unknown dependencies,
      cycles) — by hand, they need a person's judgement.
- [ ] `speky migrate --apply` — creates `.speky/speky.yaml` and `.speky/capabilities/`, and fixes
      only status files that need it (missing `id`, v2 aliases such as `done`).
- [ ] `speky migrate` again → `"done": true`, nothing pending.

## 2. Agent instructions (the biggest token win)
v2 wrote a ~1,000-line rules file (CLAUDE.md, .windsurfrules, .cursorrules, …) loaded on every
agent turn. v3 replaces it with a ~10-line block plus skills loaded on demand.
- [ ] `speky setup claude-code` (and/or `codex`, `agents-md`) for each tool the team uses.
      The old v2 rules file is backed up to `.speky/backups/`; rules you added under
      `# USER RULES` are kept above the new block.
- [ ] `speky setup <harness> --check` → `"status": "current"` for every file.
- [ ] Read the new CLAUDE.md / AGENTS.md: your own rules are still there, v2's are gone.
- [ ] Other v2 IDE files (`.windsurfrules`, `.cursorrules`, …) are left alone; v2 keeps updating
      them for those IDEs. Remove an IDE with `speky config --ides remove <ide>` if unused.

## 3. Settings
- [ ] Set `verify_command` in `.speky/speky.yaml` (e.g. `pnpm test --run`) so `speky verify` runs it.
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
- [ ] **Open items** (draft/ready/in_progress): `speky check <id>`; add `### R1:` requirement IDs
      and scenarios where the rubric asks. Don't rewrite intent.

## 5. Verify
- [ ] `speky state --json` lists every v2 spec and story with the right status.
- [ ] `speky next --json` returns a sensible action.
- [ ] `speky prime` prints a short workflow summary.
- [ ] v2 still works: `speky status`, `speky sequence`.
- [ ] A fresh agent session in the repo picks up SPEKY (Claude Code: the SessionStart hook runs
      `speky prime`).

## 6. Commit
- [ ] `speky decide "Migrated to SPEKY v3" --type event`
- [ ] Stage only `.speky/`, the harness files (`.claude/`, `.agents/`) and `CLAUDE.md` / `AGENTS.md`
      — never unrelated work: `git add .speky .claude CLAUDE.md && git commit`.
