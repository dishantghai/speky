# PRD: Codebase Analysis Problem

## Status: Research Complete, Quick Fix Implemented

**Created:** 2025-12-05  
**Related:** [DRIFT_AGENT_PRD](./DRIFT_AGENT_PRD.md) - Similar root cause  
**Priority:** High - Current implementation causes misinformation

---

## Problem Statement

SPEKY's pre-planning analysis attempts to check if a spec needs updates based on the current codebase state. However, **the analysis frequently produces incorrect conclusions** that can mislead users into making wrong changes to their specs and code.

### Example of the Problem

```
▶️  Pre-Planning Analysis
   Checking codebase state and spec alignment

⚠️  Codebase has changed. Spec may need updates.

Spec Update 1/4
📋 Change: Remove Google Cloud provider from MVP scope
📝 Reason: Based on the codebase structure and active specs, there's no 
   indication that Google Cloud transcription is currently implemented.
```

**Reality:** Google Cloud transcription WAS implemented. The AI made a wrong conclusion.

### Impact

| Severity | Description |
|----------|-------------|
| **High** | User applies "fix" that removes working functionality |
| **High** | Erodes trust in all SPEKY suggestions |
| **Medium** | Wastes time reviewing/rejecting false positives |
| **Medium** | May introduce bugs if user accepts wrong suggestions |

---

## Root Cause Analysis

### The Fundamental Flaw

SPEKY is a CLI tool with **no direct codebase access**. It relies on:

1. **Truncated snapshots** stored in `.speky/context/`
2. **AI inference** from limited context

The current implementation uses:

```python
# From speky.py lines 1669-1678
SPEC:
{spec_content[:2000]}           # Only first 2000 chars

CURRENT CODEBASE:
{codebase_info[:1500]}          # Only 1500 chars of structure

PRODUCT CONTEXT:
{product_context[:1000]}        # Only 1000 chars
```

**Total context: ~4500 characters** - Cannot represent a real codebase.

### Why This Fails

| Factor | Problem |
|--------|---------|
| **Information asymmetry** | IDE has full visibility; SPEKY has a small snapshot |
| **Context truncation** | 1500 chars can't represent file structure accurately |
| **No verification** | Can't grep, search files, or trace imports |
| **Stale data** | Context may be from days/weeks ago |
| **Hallucination** | AI fills gaps with confident but wrong assumptions |

### Comparison to DRIFT_AGENT_PRD

Both problems share the same root cause:

| Aspect | Drift Detection | Pre-Planning Analysis |
|--------|-----------------|----------------------|
| **Goal** | Check if code drifted from spec | Check if spec needs updates |
| **Method** | AI analyzes code samples | AI analyzes codebase structure |
| **Flaw** | Limited code visibility | Limited codebase visibility |
| **Result** | False positives/negatives | Wrong spec update suggestions |

**Common solution needed:** Leverage IDE's full codebase access instead of AI guessing.

---

## Current State (After Quick Fix)

### What Was Changed

Made pre-planning analysis **opt-in** instead of default:

```bash
speky plan 003              # Just plan, no analysis (safe, fast)
speky plan 003 --check      # Run pre-planning analysis (opt-in)
```

### Why This Is Only a Quick Fix

- Doesn't solve the underlying problem
- Just hides broken functionality behind a flag
- Users who opt-in still get wrong suggestions

---

## Proposed Long-Term Solutions

### Solution 1: IDE-Delegated Verification (Recommended)

**Concept:** SPEKY generates verification tasks; IDE executes them with full context.

#### How It Works

1. **SPEKY generates verification checklist:**
   ```markdown
   # .speky/specs/003/pre_plan_verification.md
   
   ## Pre-Planning Verification
   
   Before planning, verify these assumptions:
   
   1. [ ] Is Google Cloud transcription implemented?
      - Search: `class.*GoogleCloud.*Transcri` or `gcs.*transcri`
      - Check: `app/services/transcription/`
   
   2. [ ] What audio processing patterns exist?
      - Search: `def.*process.*audio` or `class.*Audio`
      - Check: existing interfaces/adapters
   
   3. [ ] Are there provider interface patterns to follow?
      - Search: `Protocol` or `ABC` in services/
   
   After verifying, update checkboxes and run:
   speky plan 003 --verified
   ```

2. **IDE rules detect and assist:**
   ```markdown
   # In .windsurfrules
   
   ## Pre-Plan Verification
   When pre_plan_verification.md exists for a spec:
   1. Help user verify each item using full codebase search
   2. Update checkboxes with findings
   3. Add notes on what was found
   4. Suggest proceeding with planning when complete
   ```

3. **SPEKY reads verified results:**
   - Parse the updated markdown
   - Incorporate accurate findings into plan generation
   - Skip items that were verified as "already implemented"

#### Advantages

- Uses the right tool (IDE) for codebase analysis
- Full visibility, accurate results
- User sees verification happening (transparency)
- Findings are documented for reference

#### Challenges

- Adds a step to the workflow
- Requires IDE cooperation (rules must be followed)
- User might skip verification

---

### Solution 2: Structured Codebase Index

**Concept:** Maintain a rich, queryable index of the codebase that SPEKY can search.

#### How It Works

1. **Periodic indexing:**
   ```bash
   speky index   # Scans codebase, builds searchable index
   ```
   
   Creates `.speky/index.json`:
   ```json
   {
     "files": {
       "app/services/transcription/google.py": {
         "classes": ["GoogleCloudTranscriber"],
         "functions": ["transcribe_audio", "init_client"],
         "imports": ["google.cloud.speech"],
         "last_modified": "2025-12-01"
       }
     },
     "symbols": {
       "GoogleCloudTranscriber": "app/services/transcription/google.py:15",
       "transcribe_audio": "app/services/transcription/google.py:42"
     }
   }
   ```

2. **Pre-planning queries the index:**
   - "Is Google Cloud transcription implemented?" → Search symbols for `Google.*Transcri`
   - Actual file evidence, not AI guessing

#### Advantages

- Accurate, evidence-based answers
- Fast (no AI calls for simple queries)
- Index can be version-controlled

#### Challenges

- Index can become stale
- Needs periodic refresh
- Storage overhead for large codebases

---

### Solution 3: Human-in-the-Loop Confirmation

**Concept:** Replace AI analysis with simple human confirmation.

#### How It Works

```
❓ Has codebase changed significantly since spec creation? [y/n]

If yes:
  → "Recommend running: speky validate-spec 003"
  → "Then re-run: speky plan 003"

If no:
  → Proceed with planning
```

#### Advantages

- Zero false positives
- Fast, no API calls
- User knows their codebase best

#### Challenges

- User might not remember changes
- Less "intelligent" feeling
- Doesn't catch subtle issues

---

### Solution 4: Validate-Spec as Gate

**Concept:** Track validation state; require recent validation before planning.

#### How It Works

1. `status.json` tracks last validation:
   ```json
   {
     "last_validated": "2025-12-05T10:30:00",
     "validation_score": 8,
     "codebase_hash": "abc123"
   }
   ```

2. `speky plan` checks:
   - If validated < 24 hours ago AND codebase hash matches → proceed
   - Otherwise → prompt to validate first

#### Advantages

- Uses existing validate-spec infrastructure
- Validation is thorough (includes AI review)
- Creates audit trail

#### Challenges

- Still has the fundamental AI visibility problem in validate-spec
- Adds friction to workflow

---

## Recommended Approach

### Phase 1: Quick Fix (DONE)
- [x] Make pre-planning analysis opt-in with `--check` flag
- [x] Default to safe, fast planning without analysis

### Phase 2: Human Confirmation (Easy Win)
- [ ] Add simple confirmation: "Has codebase changed significantly?"
- [ ] If yes, suggest validate-spec
- [ ] No AI guessing, no false positives

### Phase 3: IDE-Delegated Verification (Long-Term)
- [ ] Design verification checklist format
- [ ] Update IDE rules to assist with verification
- [ ] Implement `--verified` flag to incorporate findings
- [ ] Document workflow in README

### Phase 4: Unified Solution with Drift Detection
- [ ] Merge learnings from DRIFT_AGENT_PRD
- [ ] Single approach for all codebase analysis needs
- [ ] Possibly: dedicated "verification agent" in IDE rules

---

## Technical Notes

### Files Involved

| File | Purpose |
|------|---------|
| `speky.py:1605-1660` | Pre-planning analysis trigger |
| `speky.py:1660-1723` | `_analyze_codebase_for_spec()` |
| `speky.py:1725-1780` | `_handle_spec_updates()` |
| `.speky/context/` | Stale codebase snapshots |
| `.windsurfrules` | IDE integration rules |

### Key Functions

```python
def _analyze_codebase_for_spec(self, spec_content: str, product_context: str) -> dict:
    """PROBLEMATIC: Uses truncated context, AI guesses"""
    
def _handle_spec_updates(self, spec_file: Path, spec_content: str, analysis: dict) -> str:
    """Applies updates based on (potentially wrong) analysis"""
```

### Context Limits

| Context Type | Current Limit | Needed for Accuracy |
|--------------|---------------|---------------------|
| Spec content | 2000 chars | Full spec |
| Codebase info | 1500 chars | Full file tree + key files |
| Product context | 1000 chars | Full product.md |

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| False positive rate | ~50% (estimated) | < 5% |
| User trust in suggestions | Low | High |
| Time wasted on wrong suggestions | Significant | Minimal |
| Planning workflow speed | Slowed by review | Fast, accurate |

---

## Open Questions

1. **How to handle stale specs?** Specs created weeks ago may genuinely need updates.

2. **IDE cooperation?** Can we rely on IDE rules being followed?

3. **Verification workflow friction?** Will users skip verification?

4. **Unified solution?** Should drift detection and pre-planning share infrastructure?

---

## Related Work

- **DRIFT_AGENT_PRD** - Same root cause, different symptom
- **validate-spec command** - Existing validation infrastructure
- **IDE rules auto-refresh** - Prior art for IDE integration
