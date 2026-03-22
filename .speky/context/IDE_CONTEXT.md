# SPEKY IDE Context - Complete AI Agent Guide

**Version:** 2.0  
**Last Updated:** December 30, 2025  
**Purpose:** Make AI coding agents (Windsurf, Cursor, Claude Code) fully aware of SPEKY philosophy and capabilities

---

## What is SPEKY?

**AI-Assisted Scalable Engineering Framework** - A thin orchestration layer for AI-assisted software development that manages context, generates specs, and integrates with your IDE.

### Core Philosophy

1. **Orchestrate, don't replace** - SPEKY manages workflow; IDE does coding
2. **Human in the loop** - AI suggests, developer decides
3. **MVP-first** - Realistic specs and plans that can actually be implemented
4. **Context is king** - Full context chain for every implementation
5. **Clean separation** - SPEKY for workflow, git for version control

### What SPEKY Does

- ✅ Generate realistic specs (1-2 pages, 1-2 stories)
- ✅ Create accurate plans (3-8 tasks, <40 hours)
- ✅ Track progress and completion
- ✅ Maintain spec-code alignment (drift detection)
- ✅ Provide full context for implementation
- ✅ Group related stories (Epics)

### What SPEKY Does NOT Do

- ❌ Write production code (that's your job)
- ❌ Make architectural decisions (you decide)
- ❌ Replace your IDE (SPEKY is a companion)
- ❌ Deploy automatically (you control deployment)

---

## Project Structure

```
.speky/
├── context/
│   ├── context.json          # Project metadata, tech stack
│   ├── product.md            # Product profile
│   ├── tech_decisions.md     # AUTHORITATIVE tech choices
│   └── IDE_CONTEXT.md        # This file
├── specs/
│   └── 001-feature-name/
│       ├── spec.md           # Feature specification
│       ├── plan.md           # Implementation plan
│       └── status.json       # Status and dependencies
├── epics/                    # Story grouping
│   └── E001-epic-name/
│       ├── manifest.yaml     # Epic definition
│       ├── technical_spec.md # Shared technical decisions
│       └── summary.md        # Executive overview
├── stories/
│   └── F001-story-name/
│       ├── story.md          # Story definition
│       └── status.json       # Status, related_specs, related_epic
├── phases/
│   └── phase-1/
│       ├── manifest.yaml     # Phase definition
│       └── implementation.md # AI implementation guide
├── imports/
│   ├── initial_research/     # From speky init
│   └── poc_import/           # From speky poc-import
└── config.yaml               # SPEKY configuration
```

---

## Key Constructs

### Specs (New Features)

**Use when:** Building something NEW that doesn't exist yet

```
Spec = Complete feature definition
├── Overview (what and why)
├── MVP Scope (what's included)
├── User Stories (1-2 only)
├── Requirements (functional + non-functional)
├── Out of Scope (IMPORTANT)
├── Technical Approach
└── Open Questions
```

**Commands:**
```bash
speky spec "Feature Name"           # Create spec
speky plan 001                      # Generate plan
speky implement 001                 # Hand off to IDE
speky complete 001                  # Mark complete
```

### Stories (Changes to Existing)

**Use when:** Changing something that ALREADY exists

**Types:**
- **Feature (F)** - New functionality
- **Bug (B)** - Fix broken behavior
- **Enhancement (E)** - Improve existing
- **Tech Debt (T)** - Refactoring
- **Spike (S)** - Research/exploration

**Commands:**
```bash
speky story "Title" --type bug --spec 001     # Bug linked to spec
speky story "Title" --epic E001               # Story in epic
speky story "Title" --specs 001,002           # Multi-spec story
speky story "Title" --files lib/auth/*.dart   # With affected files
```

### Epics (Story Grouping)

**Use when:** 3+ related stories need shared context

```
Epic = Container for related stories
├── manifest.yaml (stories list, related spec)
├── technical_spec.md (shared decisions)
└── summary.md (business context)
```

**Commands:**
```bash
speky epic "Epic Name" --spec 006             # Create epic
speky epic E001 --add F005                    # Add story
speky epic E001                               # Show details
speky epics                                   # List all
```

### Phases (Timeline Coordination)

**Use when:** Coordinating multiple specs across time

```
Phase = Timeline-based grouping of specs
├── manifest.yaml (specs, deliverables)
└── implementation.md (AI guide)
```

---

## Context Chain (How AI Gets Context)

When you run `speky implement <id>`, SPEKY builds a complete context chain:

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 1: Project Context (ALWAYS)                           │
│ • context.json - Product info, tech stack                   │
│ • tech_decisions.md - Package choices                       │
├─────────────────────────────────────────────────────────────┤
│ LAYER 2: Phase Context (IF IN PHASE)                        │
│ • manifest.yaml - Phase scope                               │
│ • implementation.md - Phase guide                           │
├─────────────────────────────────────────────────────────────┤
│ LAYER 3: Related Specs (IF STORY HAS related_specs)         │
│ • spec.md - Original requirements                           │
│ • plan.md - Architecture decisions                          │
├─────────────────────────────────────────────────────────────┤
│ LAYER 4: Epic Context (IF STORY IN EPIC)                    │
│ • manifest.yaml - Epic overview                             │
│ • technical_spec.md - Shared decisions                      │
│ • Other stories in epic                                     │
├─────────────────────────────────────────────────────────────┤
│ LAYER 5: Affected Files (IF SPECIFIED)                      │
│ • Preview of files to modify                                │
├─────────────────────────────────────────────────────────────┤
│ LAYER 6: The Item Itself (ALWAYS)                           │
│ • spec.md or story.md                                       │
│ • plan.md (if exists)                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Decision Framework

### When to Use What

```
┌─────────────────────────────────────────────────────────────┐
│                   DECISION TREE                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Does the feature/capability exist?                          │
│  ├── NO → Create SPEC (new capability)                       │
│  └── YES → Create STORY (change existing)                    │
│                                                              │
│  Are there 3+ related stories?                               │
│  ├── YES → Create EPIC (group them)                          │
│  └── NO → Standalone stories are fine                        │
│                                                              │
│  Need timeline coordination?                                 │
│  ├── YES → Use PHASES                                        │
│  └── NO → Just follow sequence                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Specs vs Stories vs Epics

| Aspect | Spec | Story | Epic |
|--------|------|-------|------|
| **Purpose** | Define NEW feature | Change EXISTING | Group RELATED stories |
| **Scope** | Complete capability | Incremental change | Coordination |
| **Duration** | 1-3 weeks | 30min - 2 days | Variable |
| **Plan** | Yes (plan.md) | No | No (use story plans) |
| **When** | Product doesn't have this | Improving what exists | 3+ related changes |

---

## Workflow Recommendations

### For New Features

```bash
# 1. Create spec
speky spec "User Authentication"

# 2. Generate plan
speky plan 001

# 3. Implement
speky implement 001

# 4. Complete
speky complete 001

# 5. Commit
speky commit 001
```

### For Bug Fixes

```bash
# Link to affected spec
speky story "Fix auth timeout" --type bug --spec 001

# Implement
speky implement B001
```

### For Feature Enhancement Suite

```bash
# 1. Create epic
speky epic "Spaces Enhancements" --spec 006

# 2. Create stories in epic
speky story "Add Item Dialog" --epic E001
speky story "Context Menus" --epic E001
speky story "Drag-and-Drop" --epic E001

# 3. Implement each story
speky implement F005
speky implement F006
speky implement F007
```

### For Tech Debt

```bash
# Multi-spec tech debt
speky story "Refactor DB error handling" --type tech_debt --specs 001,002,006

# Implement
speky implement T001
```

---

## Tech Decisions (CRITICAL)

**BEFORE suggesting or using ANY package/framework:**

1. Check if `.speky/context/tech_decisions.md` exists
2. If it exists, you MUST use ONLY the packages listed there
3. NEVER suggest alternatives to decided technologies

**Example tech_decisions.md:**
```markdown
## Database
**Decision**: Drift (not SQLite/sqflite)
**Rationale**: Type-safe, reactive, better DX

## WebView
**Decision**: flutter_inappwebview (not webview_flutter)
**Rationale**: More features, better JavaScript interop

## State Management
**Decision**: Riverpod (not Provider)
**Rationale**: Compile-time safety, better testing
```

---

## File Organization Rules

### DO ✅

- Keep specs in `.speky/specs/`
- Keep stories in `.speky/stories/`
- Keep epics in `.speky/epics/`
- Keep context in `.speky/context/`
- Create code in project directories (`lib/`, `src/`, etc.)

### DON'T ❌

- Create `*_SPEC.md` files in root
- Create `IMPLEMENTATION_COMPLETE.md` in root
- Create temporary markdown files in root
- Create your own spec/plan files (use SPEKY commands)
- Create documentation files in root (except README.md)

---

## AI Agent Recommendations

### When Implementing

1. **Read the full context chain** - All layers matter
2. **Follow tech decisions** - Never deviate from decided packages
3. **Stay in scope** - Check "Out of Scope" section
4. **Check epic context** - For shared patterns and decisions
5. **Don't create extra docs** - Focus on code

### When Suggesting Changes

1. **Check if spec exists** - Don't bypass SPEKY
2. **Recommend correct construct** - Spec vs Story vs Epic
3. **Link to related specs** - For context
4. **Follow the workflow** - spec → plan → implement → complete

### When Finding Gaps

If you identify a gap in SPEKY or have a recommendation:

1. **Document the gap clearly** - What's missing?
2. **Propose a solution** - How should it work?
3. **Create a blueprint** - Like the Epic feature proposal
4. **Save to `.speky/recommendations/`** - For review

**Blueprint format:**
```markdown
# SPEKY Enhancement Recommendation

## Gap Identified
[What's missing or problematic]

## Proposed Solution
[How to fix it]

## Implementation Approach
[Technical details]

## Impact
[What this enables]
```

---

## Quick Reference

### Commands Cheat Sheet

| Command | Purpose |
|---------|---------|
| `speky init "idea"` | Initialize project |
| `speky spec "name"` | Create spec |
| `speky plan 001` | Generate plan |
| `speky epic "name" --spec 006` | Create epic |
| `speky story "title" --epic E001` | Story in epic |
| `speky story "title" --spec 001` | Story linked to spec |
| `speky implement 001` | Hand off to IDE |
| `speky complete 001` | Mark complete |
| `speky status` | Show progress |
| `speky sequence` | Show roadmap |
| `speky epics` | List epics |

### Status Values

- `draft` - Just created
- `ready` - Ready for implementation
- `in_progress` - Being implemented
- `review` - In review
- `completed` - Done

### Priority Levels

- `P0` - Blocker (must do now)
- `P1` - High (MVP features)
- `P2` - Medium (important)
- `P3` - Low (nice-to-have)

---

## Summary

**SPEKY Philosophy:**
- Specs for NEW capabilities (horizontal expansion)
- Stories for EXISTING changes (vertical deepening)
- Epics for RELATED story groups (coordination)
- Phases for TIMELINE coordination (milestones)

**Always:**
- Check tech_decisions.md before suggesting packages
- Follow the context chain
- Stay within scope
- Use SPEKY commands, don't bypass

**Never:**
- Create ad-hoc documentation files
- Suggest packages that contradict tech decisions
- Implement without checking the spec
- Skip the SPEKY workflow

---

*This document is auto-generated and updated by SPEKY. AI agents should reference this for complete framework understanding.*
