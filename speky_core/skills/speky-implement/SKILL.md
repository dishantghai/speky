---
name: speky-implement
description: Use when `speky next` says start or implement, or when implementing a SPEKY spec or story. Records the base commit, implements requirement by requirement, records evidence, and keeps scope fixed.
---

# Implement a change

1. `speky start <id>` — records the base commit verification diffs from. `speky context <id> --json`
   lists what to read (design, phase, epic, related specs, decisions, knowledge topics).
   UI changes: build what the designs cited in `## Design` show, in every state, with the design
   system's tokens and components (`speky next` lists the files). A difference you need is a
   decision for the owner, not a silent change; done checks may ask for screenshots and a review.
2. Work the plan's tasks in order (`speky next` names the next one): `speky task start W<n>`, do it,
   `speky task done W<n> --verify` (runs the task's check; when the last task closing a requirement
   passes, SPEKY records that requirement's evidence). Write the test first when
   the project has tests; for test-first work record the proof with `speky test red|green`
   (speky-test skill).
3. Scope stays fixed. Work this change needs → another task of its plan (`speky task add --for <id>
   --closes …`). Other work you discover goes into a new item:
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
