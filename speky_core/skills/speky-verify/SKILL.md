---
name: speky-verify
description: Use when `speky next` says archive, or before saying a SPEKY change is complete, fixed or passing. Checks evidence requirement by requirement, updates the living specs, and archives the change.
---

# Verify and archive

**No completion claims without fresh verification evidence.**

| Claim | Needs | Not enough |
|---|---|---|
| tests pass | the command's output from this session, exit 0 | an earlier run, "should pass" |
| requirement met | a test or observable result per `R<n>` | tests passing in general |
| bug fixed | the original symptom re-tested | code changed |
| agent finished | a diff showing the change | the agent saying so |

1. `speky verify <id> --json`. Every requirement must have `met` evidence; the verify command
   must pass on the current tree; no blocker open. Fix what is missing — don't argue with it.
2. If you can, review the diff (`changed_files`) in a fresh context against each requirement:
   missing, partial, contradicts the spec, or unrequested extra work. Unrequested work is either
   recorded as a new item or removed.
3. Living specs: if this change added or changed behaviour, write
   `<item folder>/deltas/<capability>.md` (capability = lowercase-kebab area name, e.g. `textkit`):
   ```markdown
   ## ADDED Requirements
   ### Requirement: Slugify text
   The library SHALL turn text into a URL slug.
   #### Scenario: Words and punctuation
   - WHEN slugify("Hello, World!") is called
   - THEN it returns "hello-world"

   ## MODIFIED Requirements
   ### textkit-R2: <title, using the ID from .speky/capabilities/textkit/spec.md>
   <full new text + scenarios>

   ## REMOVED Requirements
   ### textkit-R3: <title>
   Reason: <why>
   ```
   ADDED requirements get their `<capability>-R<n>` ID when archived. A heading SPEKY can't read
   is an error, not a silent skip.
4. `speky archive <id> --json` — merges deltas into `.speky/capabilities/` and closes the item.
   It refuses if the code changed since verification: verify again.
5. Report: requirements met, evidence, the verify command result, files changed, capabilities
   updated. Follow the session-close rule from `speky prime` for commits.
