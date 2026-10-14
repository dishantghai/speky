---
name: speky-import
description: Use when the user brings external material into a SPEKY project — PRDs, research, notes, handoff documents, a prototype or POC codebase — or asks to reconcile the code with such documents (`speky import`, `speky reconcile`, `speky poc-import`).
---

# Import documents or prototype code

1. **Register the sources.** Documents: `speky import add <name> --from <file-or-folder>` (copied into
   `.speky/imports/<name>/source/`). Code: `speky import add <name> --code <folder>` (referenced in place).
   `speky import show <name> --json` lists what to read.
2. **Read everything before creating anything.** Separate: capabilities (what users get), constraints,
   decisions already made, open questions, risks. Check overlaps with existing work first:
   `speky state --json`, `.speky/capabilities/`.
3. **Create, smallest form that fits:**
   - a capability that needs agreement → `speky spec "<title>"`, written with the speky-propose skill;
     keep the source's wording for requirements where it is precise;
   - small work that changes no behaviour → `speky task add "..." --kind fix|chore|measure` (behaviour → a story);
   - durable facts → `speky remember "..." --topic <topic>`; decisions → `speky adr new` / `speky decide`;
   - questions only the owner can answer → `speky owner add "..."`.
   For prototype code: describe what it does today, mark what is worth keeping, and record conflicts
   with existing specs as findings (`speky finding add <id> ...`) — never silently overwrite a spec.
4. **Link what came out:** `speky import link <name> <id> [<id> …]` (specs, stories, tasks, ADR ids).
5. **Dependencies and order:** `speky deps add ...`; propose phases if the import is large.
6. `speky import done <name>` when everything in the sources has a home or a recorded decision to drop it.

## Reconcile (code vs imported documents)
`speky reconcile <name> --json`, then compare the code with each source and each derived item. Record
each mismatch as a finding on the item, or a task/story for missing work (`--discovered-from <id>`).
Don't change code or specs during a reconcile; report.
