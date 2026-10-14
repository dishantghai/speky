---
name: speky-design
description: Use when design assets are involved in a SPEKY project — a design system document, hi-fi or lo-fi screens, icons — or when asked to analyse designs, check them against the design system, resolve conflicts, link screens to work, or keep the design system in sync with the code (`speky design`).
---

# Design system and screens

**The project's own design workflow comes first.** If `speky next` or `speky context` names a playbook
for the work (e.g. `ui` → a design skill such as screen-design-narratives, a design-tool guide, a
review rubric), follow it. SPEKY's part then is: the design system lives where `paths.design_system`
says; screens are cited by ID (`screen:<id>`, checked by `speky refs`); reviews and screenshots are
recorded as evidence for the item's done checks (`speky evidence <id> check:<name> ...`); design
follow-ups become tasks. Use the steps below when the project has no workflow of its own.

## Design for one change (`speky next` says design)

1. **Find before you make.** `speky design status --json` (design system, screens in
   `paths.design_screens`, catalogues, linked assets, UI items still needing a design, design folders
   not registered yet — register them with `speky config set paths.design_screens <folder>`); search the screen catalogue and design folders for this
   feature. Found → cite it in the item's `## Design` (`screen:<id>` or the file path, per state).
2. **None exists → create it** with the tool the project uses (its `ui` playbook) or what is
   available (Stitch, Figma, an HTML/CSS mock in the repo). Start from the design system and existing
   screens; use real content, not invented numbers. Save the result in the repo, give it an ID in
   the catalogue (or `speky design add <file> --for <id>`), then cite it.
3. **Review it** against the design system and the requirements (every state, keyboard, contrast).
4. **The owner approves new designs** before anything is built:
   `speky gate add <id> --type human --reason "approve the design"`; resolve it with their answer.
5. **No design system yet?** Write one from the existing UI (or the first approved screens) and
   `speky config set paths.design_system <file>`.

1. **Set up once:** `speky design init --tech <ui technology>`. Add assets:
   `speky design add <file-or-folder> --type system|hifi|lofi|icon [--for <item>]`.
   Link screens to the work they belong to: `speky design link <file> <item>`.
2. **Analyse each hi-fi screen** (you can read images): colours (hex), typography (family, sizes,
   weights), spacing scale, radii, shadows, layout dimensions, components and their states. Write the
   analysis to a markdown file and record it: `speky design analysis <file> --from <analysis.md>`.
   Report values you measured as measured, and say when you are estimating.
3. **Validate:** compare every analysis with the design-system document. Each mismatch:
   `speky design conflict <color|typography|spacing|radius|shadow|layout|component> "<where>"
   --existing "<system value>" --new "<screen value>"`.
4. **Resolve:** recommend a value per conflict (accessibility first: contrast ratios), but the choice
   is the owner's when it changes the look; then `speky design resolve <C#> --value ... --reason ...`
   (recorded as a decision) and update the design-system document.
5. **Implementation:** `speky context <item>` lists the linked screens and analyses. Hi-fi means match
   it; lo-fi means guidance. Reuse documented components before creating new ones.
6. **Sync:** after UI work, compare the code's tokens and components with the design-system document;
   add what was built (with file paths) to the document's component list, and file drift as tasks.
