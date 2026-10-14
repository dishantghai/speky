---
name: speky-design
description: Use when `speky next` says design, or when design is involved in a SPEKY project — the design-system document, screens (hi-fi, lo-fi, wireframes), design reviews, icons — or when asked to find, create, analyse, review or approve designs, link screens to work, or keep the design system in sync with the code (`speky design`).
---

# Design system and screens

**Where design lives (every project, `speky layout`):** `.speky/design/system.md` (the design system),
`.speky/design/screens/<screen-id>/` (one folder per screen; the catalogue is `.speky/design/screens.md`),
`.speky/design/reviews/` (reviews). A project may move these with `paths.design_*`; never invent another
place. A screen is cited as `screen:<id>` in a change's `## Design`.

**The project's own workflow comes first.** If `speky next` names a playbook (`also_skills`, e.g. a
design skill using Stitch or Figma), follow it for *how* to design; store and cite the result as below.

## Design for one change (`speky next` says design)

1. **Find before you make.** `speky design status --json`: the design system, every screen (ID, status,
   items), UI items still needing a design, and design folders outside the layout. Read the screens
   that could fit. Found → `speky design link <screen-id> <item>` (records it and cites it).
2. **None exists → create it** with the playbook's tool or what is available (Stitch, Figma, an
   HTML/CSS mock). Start from the design system and the nearest existing screens; real content only.
   Export it into the repo: `speky design screen add <screen-id> <files…> --for <item> --state <state>`
   (`--source <tool link>`). Never cite only a tool link.
3. **Review it** against the design system and the requirements (every state, keyboard, contrast), write
   the review and record it: `speky design screen review <screen-id> --file <review.md> --result pass|fail`.
   A failing review means iterate, not present.
4. **The owner approves** before anything is built: show it, then on their yes
   `speky design screen approve <screen-id> --by "<owner>"`. A later iteration gets a new ID:
   `speky design screen add <new-id> …`, then `speky design screen supersede <old-id> --by <new-id>`.
5. **No design system yet?** Write `.speky/design/system.md` from the existing UI (tokens, type, spacing,
   radii, shadows, components with states) or from the first approved screens.
6. **Designs kept elsewhere** (`speky layout --check`): import them, `speky design screen add <id>
   <files> --move`; only if tooling depends on the folder, `speky config set paths.design_screens <folder>`.

## Keeping design and code consistent

- **Analyse a screen** (you can read images): colours (hex), type, spacing, radii, shadows, layout,
  components and states → markdown → `speky design analysis <screen-id> --from <analysis.md>`. Say what
  you measured and what you estimated.
- **Conflicts** with the design system: `speky design conflict <color|typography|spacing|radius|shadow|
  layout|component> "<where>" --existing "<system>" --new "<screen>"`; recommend a value (accessibility
  first), the owner decides when the look changes: `speky design resolve <C#> --value … --reason …`.
- **After UI work**, compare the code's tokens and components with `system.md`; add what was built (with
  file paths) to its component list, and file drift as tasks.
- Implementation: `speky context <item>` lists the design system and the item's screens; hi-fi means
  match it, lo-fi means guidance. Reuse documented components before creating new ones.
