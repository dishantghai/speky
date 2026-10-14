# SPEKY v2 documentation (archive)

These pages describe SPEKY v2 (up to 0.6), whose commands called an AI model themselves. They are kept
for history. Every v2 capability has a home in SPEKY today; the v2 command names still work where an
equivalent exists. Start from the [README](../../README.md) instead.

| v2 | Now |
|---|---|
| `init` (interview, research, tech stack) | `speky init [--from-project]` + the `speky-init` skill |
| `spec`, `story`, `adopt` | `speky spec|story "<title>"`, `speky check <id>` (adopt = check) |
| `validate-spec`, `validate-story` | `speky check <id>` + `speky finding …` (converges) |
| `plan`, `implement`, `complete` | `speky plan|context <id>`, `speky start <id>`, `speky verify` + `speky archive` |
| `commit`, `review`, `cleanup` | `speky commit <id>`, `speky review`, `speky cleanup` |
| `status` | `speky status` / `speky state --json` |
| `epic`, `epics` | `speky epic …` |
| `phases` | `speky phases …` (same manifests; deliverables are the gate) |
| `sequence`, `infer-deps`, `mark-foundation`, `reset-deps`, `fix-circular-deps` | `speky order`, `speky deps …` |
| `decisions`, `context.json` tech stack | `speky decide`, `speky adr`, `speky remember --topic tech` |
| `import`, `import-status`, `reconcile`, `poc-import` | `speky import …` + the `speky-import` skill |
| `design` | `speky design …` + the `speky-design` skill |
| `test …` | `speky test …` + the `speky-test` skill |
| `config` (IDE, model) | `speky setup <harness>`, `speky config get|set|model|providers` |
| `backlog` | `speky backlog` (deferred items), `speky task …` |
| `renumber`, `host`, `sync` | removed: IDs never change (`speky order`); agents drive SPEKY directly; knowledge topics replace `codebase.md` |

Moving a v2 project: `speky migrate`, then `speky migrate --apply` (see
[docs/v3/MIGRATION.md](../v3/MIGRATION.md)).
