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
3. Living specs: if this change added or changed behaviour, make sure
   `deltas/<capability>.md` says so (`## ADDED|MODIFIED|REMOVED Requirements`, IDs from
   `.speky/capabilities/<capability>/spec.md`).
4. `speky archive <id> --json` — merges deltas into `.speky/capabilities/` and closes the item.
   It refuses if the code changed since verification: verify again.
5. Report: requirements met, evidence, the verify command result, files changed, capabilities
   updated. Follow the session-close rule from `speky prime` for commits.
