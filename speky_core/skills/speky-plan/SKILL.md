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
3. Tasks: each is one session's work with its own check — **a command and the output that means it
   passed**. First task is the thinnest path through every layer (tracer bullet). Split, never
   shrink: "placeholder for now" is a second task.
4. No hour estimates. A plan longer than the code it describes has written the code; replace bodies
   with signatures and test names.
5. If the plan needs a decision with lasting consequences (new datastore, dependency, boundary,
   public contract), write an ADR: `speky adr new "<title>"` — or add a human gate if the user must
   choose: `speky gate add <id> --type human --reason "..."`.
6. Set the project's verify command once if missing: edit `verify_command` in `.speky/speky.yaml`.

Done when plan.md exists and covers every requirement. Then `speky next` (it will say start).
