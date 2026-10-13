---
name: speky-implement
description: Use when `speky next` says start or implement, or when implementing a SPEKY spec or story. Records the base commit, implements requirement by requirement, records evidence, and keeps scope fixed.
---

# Implement a change

1. `speky start <id>` — records the base commit verification diffs from.
2. Work task by task from plan.md (or the requirements for small items). Write the test first when
   the project has tests.
3. Scope stays fixed. Work you discover goes into a new item:
   `speky new story "<title>" --type bug|feature|tech_debt --discovered-from <id>`.
4. Ambiguity mid-task: decide, and record the ruling —
   `speky decide "<what> — <why> — <cost if wrong>" --type decision --ref <id>`. Stop and ask only
   for: irreversible or destructive actions, security-sensitive actions, effects outside this
   repository (push, merge, publish), or when every path forward is a guess.
5. For each requirement, once its scenario demonstrably works, record evidence:
   `speky evidence <id> R1 --status met --evidence "<test id | file:line | command + result>"`.
   `partial`, `missing` or `contradicts` are honest answers too.
6. `speky verify <id> --json` (add `--run "<test command>"` if `verify_command` isn't set).
   Fix what it lists and verify again.

If you can run a fresh subagent, have it review the diff against the requirements before you
claim done; the writer is not the judge.

Done when `speky verify <id>` passes. Then follow the speky-verify skill.
