# SPEKY Phase Management Guide

> **Complete guide to organizing multi-spec projects with phases**

## Table of Contents

1. [What Are Phases?](#what-are-phases)
2. [Core Purpose & Benefits](#core-purpose--benefits)
3. [When to Use Phases](#when-to-use-phases)
4. [Mental Model: Phases vs Specs](#mental-model-phases-vs-specs)
5. [Phase Planning Strategies](#phase-planning-strategies)
6. [How to Think About Phase Boundaries](#how-to-think-about-phase-boundaries)
7. [Phase Commands Reference](#phase-commands-reference)
8. [Workflows](#workflows)
9. [Phase Structure & Files](#phase-structure--files)
10. [Best Practices](#best-practices)
11. [Common Patterns](#common-patterns)
12. [Troubleshooting](#troubleshooting)

---

## What Are Phases?

**Phases are SPEKY's way of organizing multiple specs into coherent, deliverable milestones.** Think of them as "releases" or "iterations" that group related work together.

### Key Characteristics

- **Optional** - Only use when managing 5+ specs
- **Deliverable-Focused** - Each phase produces working functionality
- **Dependency-Aware** - Respects spec dependencies automatically
- **AI-Assisted** - Can be auto-generated from existing specs
- **Time-Boxed** - Typically 2-6 weeks per phase

### Phases vs Other Concepts

| Concept | Purpose | Duration | Contains |
|---------|---------|----------|----------|
| **Phase** | Deliverable milestone | 2-6 weeks | Multiple specs |
| **Spec** | Single feature | 4-6 weeks | Requirements, tasks |
| **Epic** | Story grouping | 1-3 weeks | Related stories |
| **Story** | Bug/enhancement | Variable | Single change |

---

## Core Purpose & Benefits

### 1. Multi-Spec Coordination

When you have 5+ specs, phases help you implement them in logical groups rather than ad-hoc order.

**Without Phases:**
```
Specs: 001, 002, 003, 004, 005, 006, 007, 008
Order: ??? (unclear which to do first)
```

**With Phases:**
```
Phase 1: Foundation (001, 002, 003)
Phase 2: Core Features (004, 005, 006)
Phase 3: Polish (007, 008)
```

### 2. Clear Milestones

Define what "done" looks like for a chunk of work, not just individual specs.

**Example:**
- Phase 1 Deliverable: "Users can sign in and data persists"
- Not just: "Auth spec done, DB spec done"

### 3. AI Implementation Guides

Generate comprehensive context for AI agents working on multiple specs.

```bash
speky phases guide phase-1 --for-ai
# Creates implementation.md with:
# - All specs in this phase
# - Dependencies and order
# - Shared tech requirements
# - Acceptance criteria
# - Testing strategy
```

### 4. Team Alignment

Coordinate work across multiple developers or AI agents.

**Benefits:**
- Everyone knows what's in scope for current phase
- Clear handoff points between phases
- Shared understanding of deliverables

### 5. Progress Tracking

See phase-level progress, not just individual specs.

```bash
speky phases status
# Phase 1: 3/3 specs complete ✅
# Phase 2: 1/4 specs complete 🚧
# Phase 3: 0/2 specs pending ⏳
```

---

## When to Use Phases

### ✅ Use Phases When:

| Scenario | Why |
|----------|-----|
| **5+ specs** | Coordination becomes valuable |
| **Clear milestones** | Need to deliver in stages |
| **Team/multi-agent work** | Need shared context |
| **Complex dependencies** | Need to enforce order |
| **External stakeholders** | Need to show progress |
| **Long project (>8 weeks)** | Need to break into chunks |

### ❌ Skip Phases When:

| Scenario | Alternative |
|----------|-------------|
| **<5 specs** | Use `speky sequence` for order |
| **Single feature** | Just implement the spec |
| **Solo development** | Dependencies are in your head |
| **Rapid prototyping** | Too much overhead |
| **All specs independent** | No coordination needed |

### Decision Tree

```
Do you have 5+ specs?
├─ No → Skip phases, use speky sequence
└─ Yes → Do specs have dependencies?
    ├─ No → Skip phases (can implement in any order)
    └─ Yes → Do you need clear milestones?
        ├─ No → Skip phases, use speky sequence
        └─ Yes → ✅ USE PHASES
```

---

## Mental Model: Phases vs Specs

### Hierarchical Structure

```
Project: "Spayce Browser App"
│
├── Phase 1: Foundation (4 weeks)
│   ├── Spec 001: Authentication System
│   ├── Spec 002: Database Layer
│   └── Spec 003: API Core
│   └── 📦 Deliverable: "Users can sign in and data persists"
│
├── Phase 2: MVP Features (6 weeks)
│   ├── Spec 004: Browser Module
│   ├── Spec 005: Spaces System
│   └── Spec 006: Content Organization
│   └── 📦 Deliverable: "Users can browse and organize content"
│
└── Phase 3: Polish (2 weeks)
    ├── Spec 007: Settings Panel
    ├── Spec 008: Cloud Sync
    └── 📦 Deliverable: "Production-ready MVP"
```

### Key Principles

**1. Phases Define Deliverables**
- Not just "these specs are done"
- But "this VALUE is delivered to users"
- Example: "Users can browse web content" (not "Browser spec complete")

**2. Phases Respect Dependencies**
- Phase 1 specs should unlock Phase 2 specs
- Example: Auth (Phase 1) → User Dashboard (Phase 2)
- SPEKY validates dependencies automatically

**3. Phases Are Time-Boxed**
- Typical: 2-6 weeks per phase
- Too short (<2 weeks): Just implement specs directly
- Too long (>6 weeks): Split into smaller phases

**4. Phases Are Optional**
- Don't force phases if they don't add value
- Can add phases later as project grows
- Can reorganize phases without rewriting specs

---

## Phase Planning Strategies

### Strategy 1: Bottom-Up (Recommended for New Projects)

**Create specs first, then organize into phases using AI.**

#### Workflow

```bash
# 1. Create all your specs
speky spec "Authentication System"
speky spec "Database Layer"
speky spec "API Endpoints"
speky spec "Browser UI"
speky spec "Spaces Feature"
speky spec "Settings Panel"

# 2. Let AI suggest phases
speky phases suggest

# AI analyzes dependencies and suggests:
# Phase 1: Foundation (Auth, DB, API Core)
# Phase 2: Core Features (Browser, Spaces)
# Phase 3: Polish (Settings, Sync)

# 3. Review and accept/modify suggestions

# 4. Start implementing phase by phase
speky phases start phase-1
speky phases guide phase-1 --for-ai
```

#### Why This Works

- ✅ Specs are easier to define than phases
- ✅ AI understands dependencies better than you might
- ✅ Flexible - can reorganize phases without rewriting specs
- ✅ Natural workflow - focus on features first, organization second

#### Example Output

```
🤖 AI Phase Suggestions:

Phase 1: Foundation (4 weeks)
├── 001-authentication-system
├── 002-database-layer
└── 003-api-core
Rationale: These specs have no dependencies and are required by all other specs.
Deliverable: "Backend infrastructure ready for features"

Phase 2: Core Features (6 weeks)
├── 004-browser-module (depends on: 003)
├── 005-spaces-system (depends on: 002, 003)
└── 006-content-organization (depends on: 004, 005)
Rationale: Core user-facing features that depend on Phase 1.
Deliverable: "Users can browse and organize content"

Phase 3: Polish (2 weeks)
├── 007-settings-panel (depends on: 001, 005)
└── 008-cloud-sync (depends on: 002, 005)
Rationale: Enhancement features that improve UX.
Deliverable: "Production-ready MVP"

Accept these suggestions? [Y/n/e(dit)]:
```

### Strategy 2: Top-Down (For Imported Documentation)

**Import comprehensive docs, let SPEKY suggest phases automatically.**

#### Workflow

```bash
# Import your PRD/tech spec
speky import ./docs/mvp-spec.pdf --phase mvp

# SPEKY automatically:
# 1. Analyzes document
# 2. Proposes specs
# 3. Suggests phases
# 4. Shows roadmap

# You review and accept/modify
```

#### Why This Works

- ✅ External docs often have implicit phases
- ✅ AI extracts phase structure from document sections
- ✅ Traceability from phases → specs → source docs
- ✅ Preserves original document organization

#### Example

**Input:** `mvp-spec.pdf` with sections:
- Section 1: Core Infrastructure
- Section 2: User Features
- Section 3: Advanced Features

**SPEKY Output:**
```
📄 Imported: mvp-spec.pdf

Proposed Phases:

Phase 1: Core Infrastructure (from Section 1)
├── Spec 001: Auth System
├── Spec 002: Database
└── Spec 003: API Layer

Phase 2: User Features (from Section 2)
├── Spec 004: Browser
├── Spec 005: Spaces
└── Spec 006: Organization

Phase 3: Advanced Features (from Section 3)
├── Spec 007: Settings
└── Spec 008: Sync
```

### Strategy 3: Manual (For Experienced Users)

**Define phases explicitly, then create specs.**

#### Workflow

```bash
# 1. Create phase structure
speky phases create phase-1

# 2. Edit manifest manually
# .speky/phases/phase-1/manifest.yaml
# - Define deliverables
# - List specs (001, 002, 003)
# - Set acceptance criteria

# 3. Create specs that belong to this phase
speky spec "Auth" --phase phase-1
speky spec "DB" --phase phase-1
```

#### Why This Works

- ✅ Full control over structure
- ✅ Good for complex projects with known architecture
- ✅ Useful when you have a detailed roadmap already
- ✅ Can define phase-specific tech requirements

#### When to Use Manual

- You have a detailed technical roadmap
- You know the exact architecture upfront
- You're experienced with the domain
- You need precise control over phase boundaries

---

## How to Think About Phase Boundaries

### Good Phase Boundaries

#### ✅ Vertical Slices (Recommended)

**Deliver working functionality end-to-end.**

```
Phase 1: "Users can sign in and see their dashboard"
├── Auth (backend + frontend)
├── User DB (schema + API)
└── Dashboard UI (basic view)
```

**Why it works:**
- Users can actually USE the feature
- Demonstrates value immediately
- Can get feedback early
- Reduces integration risk

#### ✅ Technical Foundations

**Build infrastructure that unlocks future features.**

```
Phase 1: "Infrastructure is ready"
├── Database setup
├── API framework
└── Auth system
```

**Why it works:**
- All future features depend on this
- Clear completion criteria
- Reduces rework later
- Enables parallel development in Phase 2

#### ✅ Feature Sets

**Group related user-facing capabilities.**

```
Phase 2: "Content management works"
├── Browser module
├── Spaces system
└── Content organization
```

**Why it works:**
- Cohesive user experience
- Related functionality
- Can be tested as a unit
- Clear user value

### Poor Phase Boundaries

#### ❌ Horizontal Layers

**Don't split by tech layer.**

```
❌ Phase 1: "All backend work"
❌ Phase 2: "All frontend work"
```

**Why it fails:**
- No deliverable value until Phase 2 completes
- Can't test end-to-end until Phase 2
- Frontend might discover backend issues late
- No user value in Phase 1

**Better approach:**
```
✅ Phase 1: "Auth works end-to-end"
   ├── Auth backend
   ├── Auth frontend
   └── User can sign in
```

#### ❌ Arbitrary Grouping

**Don't group by convenience.**

```
❌ Phase 1: "First 5 specs alphabetically"
❌ Phase 2: "Specs assigned to Alice"
```

**Why it fails:**
- No logical relationship
- No clear deliverable
- Ignores dependencies
- Confusing for team

#### ❌ Too Granular

**Don't make phases too small.**

```
❌ Phase 1: Spec 001
❌ Phase 2: Spec 002
❌ Phase 3: Spec 003
```

**Why it fails:**
- Just use specs directly
- Phases add no value
- Extra overhead for no benefit

**Rule of thumb:** Each phase should have 2-5 specs minimum.

---

## Phase Commands Reference

### Discovery & Planning

```bash
# AI suggests phases from existing specs (RECOMMENDED)
speky phases suggest

# List all phases
speky phases list

# Show phase details
speky phases show phase-1

# Show overall progress
speky phases status
```

### Phase Lifecycle

```bash
# Create a new phase manually
speky phases create phase-1

# Start a phase (validates prerequisites)
speky phases start phase-1

# Complete a phase (validates deliverables)
speky phases complete phase-1
```

### AI Guides & Context

```bash
# Generate AI implementation guide
speky phases guide phase-1

# Generate AI-optimized guide
speky phases guide phase-1 --for-ai

# Generate AI context for current phase
speky context

# Generate AI context for specific phase
speky context --phase phase-1
```

### Integration with Other Commands

```bash
# Create spec for specific phase
speky spec "Feature Name" --phase phase-1

# Import docs into a phase
speky import ./docs --phase mvp

# See implementation order (phase-aware)
speky sequence

# Implement with phase context
speky implement 001  # Loads phase context automatically
```

---

## Workflows

### Workflow 1: AI-Suggested Phases (Recommended)

```
1. Create specs first
   speky spec "Auth"
   speky spec "API"
   speky spec "UI"
          ↓
2. Let AI suggest phases
   speky phases suggest
          ↓
   🤖 AI analyzes specs and suggests:
   - Phase 1: Foundation (Auth, DB)
   - Phase 2: MVP Core (API, UI)
   - Phase 3: Polish (Settings, Sync)
          ↓
3. Accept/modify suggestions
          ↓
4. Start implementing
   speky phases start phase-1
   speky phases guide phase-1 --for-ai
          ↓
5. Complete and continue
   speky phases complete phase-1
   speky phases start phase-2
```

### Workflow 2: Import-Driven Phases

```
1. Import external docs
   speky import ./docs/prd.pdf --phase mvp
          ↓
2. SPEKY auto-suggests phases
   (based on document structure)
          ↓
3. Review proposed specs and phases
          ↓
4. Accept/modify
          ↓
5. Start implementing
   speky phases start phase-1
```

### Workflow 3: Manual Phase Creation

```
1. Create phase:   speky phases create phase-1
          ↓
2. Edit manifest:  .speky/phases/phase-1/manifest.yaml
          ↓
3. Start phase:    speky phases start phase-1
          ↓
4. Generate guide: speky phases guide phase-1 --for-ai
          ↓
5. Implement specs
          ↓
6. Complete phase: speky phases complete phase-1
```

---

## Phase Structure & Files

### Directory Structure

```
.speky/
├── phases/
│   ├── roadmap.yaml              # Master phase timeline
│   ├── phase-1/
│   │   ├── manifest.yaml         # Phase definition
│   │   ├── implementation.md     # AI guidance (generated)
│   │   ├── ai_context.md         # AI context (generated)
│   │   └── status.json           # Progress tracking
│   └── phase-2/
│       └── manifest.yaml
```

### Phase Manifest (manifest.yaml)

Complete example with all options:

```yaml
# .speky/phases/phase-1/manifest.yaml
id: phase-1
name: "MVP Browser + Spaces"
description: "Basic browser with content organization"
duration: "4 weeks"
status: "in_progress"  # not_started, in_progress, completed

# Specs included in this phase
specs:
  - "002-browser-module"
  - "003-spaces-system"
  - "004-content-organization"

# What this phase delivers
deliverables:
  - description: "Users can browse web content"
    validation: "Browser opens and loads websites"
  - description: "Users can organize tabs into spaces"
    validation: "Can create spaces and move tabs"

# How we know phase is complete
acceptance_criteria:
  - description: "Browser module fully functional"
    validation: "All browser tests pass"
  - description: "Spaces system working"
    validation: "Can create/delete/switch spaces"
  - description: "Drift database setup"
    validation: "lib/database/database.dart exists"

# Tech requirements (phase-specific)
tech_requirements:
  packages:
    - name: "flutter_inappwebview"
      version: "^6.0.0"
      reason: "Browser engine"
  
  infrastructure:
    - name: "Drift database"
      setup: "Run: flutter pub add drift"
  
  environment:
    - name: "Flutter SDK"
      version: ">=3.0.0"

# Shared context for all specs in this phase
shared_context:
  architecture: "Clean Architecture with Riverpod"
  design_system: "Material Design 3"
  state_management: "Riverpod"
  
  key_decisions:
    - "Use flutter_inappwebview for browser (not webview_flutter)"
    - "Drift for local database (not sqflite)"
    - "Spaces are first-class entities, not folders"

# What NOT to include in this phase
excludes:
  - "Cloud sync (Phase 3)"
  - "Settings panel (Phase 3)"
  - "Advanced tab features (Phase 2)"

# Phase dependencies
depends_on: []
unlocks: ["phase-2"]

# Metadata
created: "2024-01-15T10:00:00Z"
started: "2024-01-15T10:30:00Z"
target_completion: "2024-02-12T17:00:00Z"
```

### Roadmap (roadmap.yaml)

Master timeline for all phases:

```yaml
# .speky/phases/roadmap.yaml
project: "Spayce Browser"
total_duration: "12 weeks"
start_date: "2024-01-15"

phases:
  - id: "phase-1"
    name: "Foundation"
    duration: "4 weeks"
    start: "2024-01-15"
    end: "2024-02-12"
    status: "completed"
  
  - id: "phase-2"
    name: "MVP Features"
    duration: "6 weeks"
    start: "2024-02-13"
    end: "2024-03-26"
    status: "in_progress"
  
  - id: "phase-3"
    name: "Polish"
    duration: "2 weeks"
    start: "2024-03-27"
    end: "2024-04-09"
    status: "not_started"

milestones:
  - date: "2024-02-12"
    description: "Foundation complete - backend ready"
  - date: "2024-03-26"
    description: "MVP complete - ready for beta"
  - date: "2024-04-09"
    description: "Production release"
```

---

## Best Practices

### 1. Start with Specs, Not Phases

**❌ Don't:**
```bash
# Create empty phases first
speky phases create phase-1
speky phases create phase-2
# Now what specs go where?
```

**✅ Do:**
```bash
# Create specs first
speky spec "Auth"
speky spec "API"
speky spec "UI"

# Let AI organize into phases
speky phases suggest
```

### 2. Define Clear Deliverables

**❌ Vague:**
```yaml
deliverables:
  - "Auth stuff done"
  - "Some UI work"
```

**✅ Specific:**
```yaml
deliverables:
  - description: "Users can sign in with email/password"
    validation: "Login form works, session persists"
  - description: "Dashboard shows user profile"
    validation: "User sees their name and avatar"
```

### 3. Keep Phases Focused

**❌ Too broad:**
```
Phase 1: "Everything for MVP" (10 specs, 12 weeks)
```

**✅ Focused:**
```
Phase 1: "Foundation" (3 specs, 4 weeks)
Phase 2: "Core Features" (4 specs, 6 weeks)
Phase 3: "Polish" (3 specs, 2 weeks)
```

### 4. Respect Dependencies

**❌ Ignoring dependencies:**
```
Phase 1: UI components
Phase 2: API endpoints
# UI needs API - wrong order!
```

**✅ Dependency-aware:**
```
Phase 1: API endpoints
Phase 2: UI components (depends on Phase 1)
```

### 5. Use AI Guides

**Always generate implementation guides:**
```bash
speky phases guide phase-1 --for-ai
```

This creates comprehensive context for AI agents including:
- All specs in phase
- Dependencies and order
- Shared tech requirements
- Acceptance criteria
- What to exclude

### 6. Update Phases as You Learn

Phases aren't set in stone. Update them as you learn:

```bash
# Discovered Phase 1 is too big
speky phases suggest  # Re-run to get new suggestions

# Or manually split
speky phases create phase-1a
# Move some specs from phase-1 to phase-1a
```

---

## Common Patterns

### Pattern 1: Foundation → Features → Polish

**Most common pattern for new products.**

```
Phase 1: Foundation (2-4 weeks)
├── Auth system
├── Database layer
└── API core
Deliverable: "Infrastructure ready"

Phase 2: Core Features (4-8 weeks)
├── Main user features
├── Core workflows
└── Essential UI
Deliverable: "MVP works end-to-end"

Phase 3: Polish (1-3 weeks)
├── Settings
├── Error handling
└── Performance
Deliverable: "Production ready"
```

### Pattern 2: Vertical Slices

**Best for continuous delivery.**

```
Phase 1: "Users can browse" (3 weeks)
├── Browser engine (backend)
├── Browser UI (frontend)
└── Basic navigation
Deliverable: Working browser

Phase 2: "Users can organize" (4 weeks)
├── Spaces backend
├── Spaces UI
└── Tab management
Deliverable: Full organization

Phase 3: "Users can sync" (2 weeks)
├── Sync backend
├── Sync UI
└── Conflict resolution
Deliverable: Multi-device support
```

### Pattern 3: Risk-First

**Tackle unknowns early.**

```
Phase 1: High-Risk Items (3 weeks)
├── Browser engine integration (unknown)
├── Performance testing (risky)
└── Third-party API integration (uncertain)
Deliverable: "Risks validated"

Phase 2: Core Features (5 weeks)
├── Known, straightforward features
└── Build on validated tech
Deliverable: "MVP complete"
```

### Pattern 4: Platform-Specific

**For multi-platform projects.**

```
Phase 1: Core Logic (3 weeks)
├── Shared business logic
├── API layer
└── Data models
Deliverable: "Platform-agnostic core"

Phase 2: Web Platform (4 weeks)
├── Web UI
├── Web-specific features
└── Web deployment
Deliverable: "Web app live"

Phase 3: Mobile Platform (4 weeks)
├── Mobile UI
├── Mobile-specific features
└── App store deployment
Deliverable: "Mobile apps live"
```

---

## Troubleshooting

### Issue: "I have 8 specs but phases seem like overkill"

**Solution:** Phases are optional. Try this instead:

```bash
# Just see the implementation order
speky sequence

# Implement in order
speky implement 001
speky implement 002
# etc.
```

If you later feel you need phases, run `speky phases suggest`.

### Issue: "AI suggested weird phase groupings"

**Solution:** AI suggestions are starting points, not gospel.

```bash
# Review suggestions
speky phases suggest

# Edit manually
# Modify .speky/phases/phase-1/manifest.yaml
# Move specs between phases as needed

# Or reject and create manually
speky phases create phase-1
```

### Issue: "Phase has too many specs (7+)"

**Solution:** Split into smaller phases.

```bash
# Create a new phase
speky phases create phase-1a

# Move some specs to new phase
# Edit manifest.yaml files to reassign specs

# Or let AI re-suggest
speky phases suggest --force
```

### Issue: "Specs have circular dependencies across phases"

**Solution:** This indicates a design issue.

```bash
# Check dependencies
speky sequence

# Look for circular dependencies
# Fix at spec level, not phase level

# Specs in same phase can depend on each other
# But Phase 2 specs shouldn't depend on Phase 3 specs
```

### Issue: "Phase completion validation failing"

**Solution:** Check acceptance criteria.

```bash
# See what's failing
speky phases complete phase-1

# Review acceptance criteria
speky phases show phase-1

# Either:
# 1. Fix the implementation to meet criteria
# 2. Update criteria if they were wrong
```

### Issue: "Don't know what deliverable to write"

**Solution:** Think from user perspective.

**❌ Technical:**
```
Deliverable: "Database schema created"
```

**✅ User-focused:**
```
Deliverable: "User data persists across app restarts"
```

Ask: "What can users DO after this phase?"

---

## Practical Example: Building Spayce Browser

### Step 1: Identify Core Value

**Question:** What's the MVP?
**Answer:** "Users can browse web content and organize it into spaces"

### Step 2: Create Specs

```bash
speky spec "Basic Browser Engine"
speky spec "Tab Management"
speky spec "Spaces System"
speky spec "Content Organization"
speky spec "State Persistence"
speky spec "Settings Panel"
speky spec "Cloud Sync"
```

### Step 3: Let AI Suggest Phases

```bash
speky phases suggest
```

**AI Output:**
```
🤖 Analyzing 7 specs...

Suggested Phases:

Phase 1: Foundation (2 weeks)
├── 001-basic-browser-engine
├── 002-tab-management
└── 003-state-persistence
Deliverable: "Users can browse websites with tabs"
Rationale: Core browsing functionality with no dependencies

Phase 2: Organization (3 weeks)
├── 004-spaces-system (depends on: 002)
├── 005-content-organization (depends on: 002, 004)
Deliverable: "Users can organize tabs into spaces"
Rationale: Builds on Phase 1 to add organization

Phase 3: Advanced (2 weeks)
├── 006-settings-panel (depends on: 004)
├── 007-cloud-sync (depends on: 003, 004)
Deliverable: "Production-ready with sync and settings"
Rationale: Polish and advanced features

Accept? [Y/n/e]:
```

### Step 4: Review and Modify

```bash
# Accept with modifications
e

# AI opens editor with manifest.yaml files
# You adjust:
# - Move state-persistence to Phase 2 (needed for spaces)
# - Add more specific acceptance criteria
# - Define tech requirements per phase
```

### Step 5: Start Implementing

```bash
# Start Phase 1
speky phases start phase-1

# Generate AI guide
speky phases guide phase-1 --for-ai

# Implement specs in order
speky implement 001
speky complete 001

speky implement 002
speky complete 002

# Complete phase
speky phases complete phase-1
```

### Step 6: Continue to Next Phase

```bash
# Start Phase 2
speky phases start phase-2

# Generate updated guide
speky phases guide phase-2 --for-ai

# Continue implementation...
```

---

## Summary

### Key Takeaways

1. **Phases = Deliverable Milestones**, not just spec groups
2. **Bottom-up is easiest**: Create specs → `speky phases suggest`
3. **Think in user value**: "What can users DO after this phase?"
4. **2-6 weeks per phase** is the sweet spot
5. **Phases are optional** - use them when they add value
6. **AI helps**: `speky phases suggest` analyzes your specs and proposes logical grouping

### Decision Matrix

| Your Situation | Recommendation |
|----------------|----------------|
| <5 specs | Skip phases, use `speky sequence` |
| 5-10 specs, clear dependencies | Use phases (AI-suggested) |
| 10+ specs, complex project | Definitely use phases |
| Importing external docs | Use phases (auto-suggested) |
| Solo, rapid prototyping | Skip phases |
| Team coordination needed | Use phases |

### Quick Start

```bash
# 1. Create your specs
speky spec "Feature 1"
speky spec "Feature 2"
# ... (create 5+ specs)

# 2. Let AI suggest phases
speky phases suggest

# 3. Start implementing
speky phases start phase-1
speky phases guide phase-1 --for-ai
speky implement 001

# 4. Complete and continue
speky phases complete phase-1
speky phases start phase-2
```

---

## Additional Resources

- **README.md** - Phase commands quick reference
- **DOCUMENTATION.md** - Complete SPEKY documentation
- **SEQUENCING.md** - Spec dependencies and ordering
- **IMPORT_FEATURE.md** - Importing docs with phase suggestions
- **EPIC_FEATURE.md** - Epics vs Phases comparison

---

**Last Updated:** January 14, 2026
**Version:** 1.0.0
