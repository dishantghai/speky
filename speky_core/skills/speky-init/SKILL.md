---
name: speky-init
description: Use when starting SPEKY in a project (`speky init` just ran, or `speky next` says idle in a project with no product knowledge), or when the user describes a new product idea. Turns an idea or an existing codebase into product knowledge, stack decisions and the first phase with its specs or tasks.
---

# Start a project

`speky init` has created `.speky/` and recorded what it could read (idea, README summary, detected
stack, test command). Your job is the judgement around it.

1. **Read first.** `speky status --json` and the files `speky init` listed under `read_first`
   (README, docs, manifests). In an existing project, read enough code to know what is built.
2. **Ask only what you can't find out.** At most five questions, one per message, each with your
   recommended answer and one line on why it matters: who it is for, the problem, what the first
   usable version must do, constraints (platform, compliance, budget), what is out of scope.
   Skip what the code or docs already answer. If the user opts out, state your defaults.
3. **Record the product** in a few lines (no essays):
   `speky remember "<fact>" --topic product` — who, problem, first version, non-goals.
4. **Record the stack** that matters: lasting choices become ADRs (`speky adr new "<title>"
   --context ... --decision ...`); smaller facts go to `speky remember "..." --topic tech`.
   Choosing a stack is the owner's call: propose with reasons, then record their choice.
5. **Plan the first phase:** `speky phases add "<name>"`, deliverables that prove it
   (`speky phases deliverable <phase> "<what>" [--run "<cmd>"]`), then `speky phases start <phase>`.
6. **First work items:** one spec per capability that needs agreement (`speky spec "<title>"`,
   then the speky-propose skill), small things as tasks (`speky task add "..."`). Link dependencies
   with `speky deps add`.
7. **UI projects:** find or create the design-system document (tokens, type, spacing, components) and
   set `speky config set paths.design_system <file>`; if screens live in a catalogue with IDs, add a
   `refs` kind for them (`refs.screen`); if the project has its own design workflow or tool (Stitch,
   Figma, a design skill), name it as the `ui` playbook (`playbooks.ui: {skill, read, note}`) and,
   if that skill lives outside the repo, list it in `extra_skills`.
8. If tests exist, check `speky config get verify_command`; fix it with `speky config set`.
9. `speky handoff --summary "..." --next "..."`.

Existing SPEKY v2 project? Use the speky-migrate skill instead.
