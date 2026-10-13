# v2 parity safety net

End-to-end tests that run real `speky <command>` invocations in a temp project with the model
replaced by a scripted fake (`FakeLLM` in `conftest.py`). They pin what v2 does today so that
SPEKY v3 can prove it lost nothing (the parity inventory is `docs/v3/PLAN.md` §2.8).

Run: `python -m pytest -q tests` (needs `pip install -r requirements-dev.txt`).

## Coverage

**Behaviour pinned** = asserts files/statuses. **Smoke** = asserts the command runs to completion
only (the fake model's answers don't exercise its logic yet). **Not yet** = to add.

| v2 capability | Level | Test |
|---|---|---|
| `init` (fresh idea), `init --from-project` | Behaviour pinned / smoke | `test_init_creates_context_and_rules`, `test_init_from_project` |
| Commands refuse to run before init | Behaviour pinned | `test_commands_need_init` |
| `spec` → `plan` → `implement` → `complete` (status transitions, drift call) | Behaviour pinned | `test_spec_plan_implement_complete` |
| Spec IDs | Behaviour pinned | `test_second_spec_gets_next_id` |
| `validate-spec --quick` | Smoke (model called) | `test_validate_spec_quick` |
| `story` (types, `--epic`, `--spec`), story `complete` | Behaviour pinned | `test_story_lifecycle`, `test_story_linked_to_spec_and_epic` |
| `validate-story --quick` | Smoke | `test_validate_story_quick` |
| `epic` create/show/add/remove, `epics` | Behaviour pinned (create) / smoke | `test_epic_create_show_add_remove` |
| `adopt` story and spec | Behaviour pinned | `test_adopt_ide_created_story_and_spec` |
| `mark-foundation`, `reset-deps`, `infer-deps`, `fix-circular-deps`, `sequence --export` | Smoke + roadmap file | `test_dependency_commands` |
| `phases` create/show/status/list/start/guide, `context` | Behaviour pinned (create) / smoke | `test_phases_lifecycle` |
| `decisions`, `backlog` | Smoke | `test_decisions_and_backlog` |
| `sync` | Behaviour pinned | `test_sync_writes_codebase_context` |
| `import`, `import-status` | Smoke | `test_import_docs_into_specs` |
| `poc-import` (agent task file) | Behaviour pinned | `test_poc_import_writes_agent_task` |
| `commit` | Behaviour pinned | `test_commit_completed_spec` |
| `config` (`--ides add/remove`, `--providers`, `--list-ides`) | Behaviour pinned / smoke | `test_config_ides_and_model`, `test_status_and_read_only_commands` |
| `design init/status`, `test status` | Smoke | `test_design_and_testing_modules` |
| `host guide/status`, `status`, `review`, `cleanup --dry-run`, `renumber --dry-run` | Smoke | `test_host_mode_guide_and_status`, `test_status_and_read_only_commands` |

### Not yet covered
- `validate-spec` / `validate-story` interactive flows (fix, defer, split, AI fixes, saved sessions)
- `complete` with drift found + interactive resolution; `--test`
- `plan --check`, open-question resolution in `plan`
- `import` with a scripted analysis (specs proposed and created), `reconcile`
- `poc-import --resume`, conflict resolution, spec merge/deprecate
- `phases complete/suggest`, `epic` progress after story completion
- `design import/analyze/link/resolve/validate/sync`; `test init/gen/run/coverage/tdd-*/triage`
- Host mode round trip (`--host` + `host show/answer` from a second process)
- `implement --tdd`, `config --model`
