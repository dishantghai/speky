---
name: speky-plan
description: Use when `speky next` says plan, or when asked to plan a validated SPEKY change. Writes plan.md with the decisions an implementer cannot make alone and the command that verifies each task.
---

# Plan a change

Write `<item folder>/plan.md` for an engineer who knows the language but not this codebase.

1. Read the change, its dependencies, `.speky/adr/`, `decisions.md` and the code it touches.
2. Write down only what the implementer cannot decide alone:
   - files to create or modify, and what each is responsible for;
   - interfaces between tasks (names, parameters, return types);
   - exact values the spec pins;
   - for each requirement, which task covers it.
3. Tasks live in SPEKY, as the plan's task list (SPEKY writes them into plan.md):
   `speky task add --for <id> "<task>" --closes R1[,R2] --check "<command that proves it>"`. Each task
   closes requirements (the acceptance criteria) or done checks of this change; every requirement must be
   closed by at least one task — `speky next` stays on "plan" until it is. Each task is one session's
   work with its own check. First task is the thinnest path through every layer (tracer bullet). Split,
   never shrink: "placeholder for now" is a second task.
4. No hour estimates. A plan longer than the code it describes has written the code; replace bodies
   with signatures and test names.
5. If the plan needs a decision with lasting consequences (new datastore, dependency, boundary,
   public contract), write an ADR: `speky adr new "<title>"` — or add a human gate if the user must
   choose: `speky gate add <id> --type human --reason "..."`.
6. Set the project's verify command once if missing: edit `verify_command` in `.speky/speky.yaml`.

7. **Dependencies:** for each item this one needs first, `speky deps add <id> <needed-id>`
   (`speky order` shows the resulting order; `speky deps cycles` must be empty).

## Roadmap mode (several items, or "plan the project")
Group work into phases that each deliver something usable: `speky phases add "<name>"`, each with
deliverables that prove it (`speky phases deliverable <phase> "<what>" --run "<cmd>"` when a command can
prove it), items attached with `--phase` on `speky spec|story`; their tasks go in each item's plan (`--for`). Only
small work without behaviour change is a standalone task: `speky task add --phase <p> --kind fix|chore|measure`.
Infer dependencies between items from what each needs, record them with `speky deps add`, and check
`speky order --export`. The first item in a phase is the thinnest path through every layer.

Done when plan.md is written and every requirement is closed by a task. Then `speky next` (it will say start).
