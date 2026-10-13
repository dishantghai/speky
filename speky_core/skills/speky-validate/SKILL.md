---
name: speky-validate
description: Use when `speky next` says validate or fix_structure, or when asked to review or validate a SPEKY spec or story. Reviews a change once, records only verified findings, and stops when speky reports converged.
---

# Validate a change — and stop

Validation exists to remove guesses an implementer would have to make. It is not a hunt for
every possible improvement. SPEKY caps the rounds and remembers every finding; your job is to make
round 1 thorough and then stop.

## Each round
1. `speky check <id> --json`. Fix every rubric blocker in the document.
2. Read the document once through this checklist and note gaps:
   scope and non-goals · users and roles · data and its lifecycle · main flow, error and empty
   states · limits (size, rate, time) · external services and their failures · security and
   privacy · terminology (match `.speky/glossary.md`) · success signal · conflicts with
   `.speky/adr/`, `decisions.md` and other specs.
3. **Verify each gap before recording it.** Does the document really leave it open? Would a wrong
   guess change user-visible behaviour or stored data? If not, drop it.
4. Record what survives:
   `speky finding add <id> --severity blocker|major|minor --text "..." [--kind question]`
   - blocker: an implementer must guess and a wrong guess changes behaviour or data.
   - major: likely rework if left open. minor: polish — note it, never loop on it.
   - Drop findings whose fix adds complexity for a case users won't meet.
   - Questions are capped (5). Past the cap, make an informed guess and add it under `## Assumptions`.
5. Fix what you can in the document; then close each finding:
   `speky finding resolve <id> <F#> --as fixed` — or `--as accepted|wontfix|deferred --ruling
   "<decision> — <why> — <cost if wrong>"`.
6. `speky check <id> --json` again.

## Stop when
`speky check` says **converged** (no open blocker/major), or reports **converged by cap**.
Do not start another round on an unchanged document; SPEKY will return the cached result.
Never re-raise a finding that was closed — the ledger rejects duplicates.

Report: rounds used, findings fixed, rulings made, assumptions added. Then `speky next`.
