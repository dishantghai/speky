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
   then the speky-propose skill), small no-behaviour things as tasks (`speky task add "..." --kind chore|fix|measure`). Link dependencies
   with `speky deps add`.
7. **UI projects:** the design system goes in `.speky/design/system.md` (write it from the existing UI
   if there is none), screens in `.speky/design/screens/<id>/` (`speky design screen add`). Run
   `speky layout --check`: designs or ADRs kept elsewhere are imported, or — only if tooling depends
   on them — their folder is set as an override (`paths.design_screens`, `paths.adr_dir`). If the
   project has its own design workflow or tool (Stitch, Figma, a design skill), name it as the `ui`
   playbook (`playbooks.ui: {skill, read, note}`) and list an outside skill in `extra_skills`.
8. If tests exist, check `speky config get verify_command`; fix it with `speky config set`.
9. `speky handoff --summary "..." --next "..."`.

Existing SPEKY v2 project? Use the speky-migrate skill instead.
