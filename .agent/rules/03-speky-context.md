# SPEKY Rules (Context) - Auto-generated
# Do not edit manually - regenerated on each SPEKY command
# Size: 7670 chars (max: 8000)

# SPEKY Context & Commands

## 🎨 CRITICAL: Design System

**BEFORE implementing ANY UI:**
1. Check if `.speky/context/design_system.md` exists
2. If it exists, you MUST follow the design system for:
   - Colors (use EXACT hex values, e.g., `Color(0xFF6D5AE6)`)
   - Typography (font family, sizes, weights from design system classes)
   - Spacing (use design system constants, e.g., `Spacing.md`)
   - Border radius values (use design system constants)
   - Shadows and elevation (use design system shadow definitions)
   - Animation durations and curves
3. Check `.speky/design/manifest.json` for linked Hi-Fi designs
4. If Hi-Fi designs exist for the spec, match them PIXEL-PERFECT

**Design System Files:**
```
.speky/design/
├── config.yaml               # Technology and settings
├── manifest.json             # All designs, links, resolved conflicts
├── system/source/            # Design system documents (AUTHORITATIVE)
│   └── design_system.md      # Complete token definitions
├── hifi/source/              # Hi-Fi designs (pixel-perfect)
│   └── *.analysis.md         # AI-extracted tokens from images
├── lofi/source/              # Lo-Fi wireframes (guidance)
└── icons/source/             # Icon assets

.speky/context/design_system.md  # AI summary for quick reference
```

**When implementing UI:**
- Use design system colors, NEVER arbitrary values
- Use design system spacing constants (xs, sm, md, lg, xl)
- Use design system typography styles (navButton, treeItem, etc.)
- Use design system radius values (button, card, input)
- Use design system shadows (sidebarEmbossed, cardSubtle, etc.)
- If conflict between spec and design system, follow design system

**Reusing Implemented Components:**
- Check the Implementation Checklist in the design system doc
- Look for existing widgets before creating new ones
- Reference file paths in the checklist for component locations
- Follow established patterns from existing components

**Design System Commands:**
```bash
speky design status    # Check design system coverage
speky design validate  # Detect conflicts with Hi-Fi
speky design resolve   # Resolve conflicts with AI
```

## 🔧 SPEKY Commands Reference

Tell the developer to use these commands:

**Core Workflow:**
- `speky init "idea"` - Initialize project with tech stack discussion
- `speky spec "name"` - Create a new feature spec (research-aware)
- `speky plan 001` - Generate implementation plan (validates dependencies)
- `speky implement 001` - Start implementation (validates dependencies, updates this file)
- `speky complete 001` - Verify and mark complete with drift detection
- `speky commit 001` - Commit with comprehensive message
- `speky status` - Check project progress

**Spec Sequencing & Dependencies:**
- `speky sequence` - Show implementation roadmap with dependencies
- `speky sequence --export` - Export roadmap to `.speky/roadmap.md`
- `speky infer-deps` - AI-infer dependencies for all specs
- `speky infer-deps 003` - AI-infer dependencies for specific spec

**External Knowledge Import:**
- `speky import --phase mvp` - Import docs with interactive review
- `speky import-status` - Show all imports and derived specs
- `speky reconcile mvp` - Reconcile code with imported docs
- `speky poc-import` - Import features from POC codebase

**Spec Quality & Validation:**
- `speky validate-spec 001` - Validate spec quality (interactive)
- `speky validate-spec 001 --quick` - Quick validation (non-interactive)
- `speky adopt 001` - Adopt IDE-created spec into SPEKY tracking
- `speky backlog` - Review deferred validation items

**Phase Management (Multi-Spec Coordination):**
- `speky phases suggest` - AI suggests phases from existing specs
- `speky phases list` - List all phases
- `speky phases show phase-1` - Show phase details
- `speky phases status` - Show overall phase progress
- `speky phases start phase-1` - Start a phase
- `speky phases guide phase-1 --for-ai` - Generate AI implementation guide
- `speky context --phase phase-1` - Generate AI context for phase

**Epic Management (Story Grouping):**
- `speky epic "Epic Name" --spec 006` - Create epic linked to spec
- `speky epic E001` - Show epic details
- `speky epic E001 --add F005` - Add story to epic
- `speky epic E001 --remove F005` - Remove story from epic
- `speky epics` - List all epics with status

**Stories:**
- `speky story "title"` - Create feature story
- `speky story --type bug "title"` - Create bug story
- `speky story "title" --epic E001` - Create story in epic
- `speky story "title" --spec 001` - Create story linked to spec
- `speky story "title" --specs 001,002` - Create story linked to multiple specs
- `speky story "title" --files lib/*.dart` - Create story with affected files

**Maintenance:**
- `speky sync` - Sync codebase context
- `speky review 001` - Check for spec-code drift
- `speky cleanup` - Remove any clutter files

## Creating Specs Directly (Advanced)

If the developer asks you to create a spec directly, you MAY create it:

### Step 1: Create Directory
`.speky/specs/NNN-feature-name/` (NNN = next available number)

### Step 2: Create spec.md with this template:
```markdown
# Feature Name

## Overview
2-3 sentences explaining what this feature does and why.

## MVP Scope
Explicit list of what IS included in this MVP version.

## User Stories
1-2 core user stories only:
- As a [user], I want [action], so that [benefit]
  - Acceptance: [specific, testable criteria]

## Requirements

### Functional Requirements (MVP only)
- Essential behaviors only
- Remove nice-to-haves

### Non-Functional Requirements
- Only if critical

## Out of Scope
Explicitly list what is NOT included (prevents scope creep).

## Open Questions
- Specific decisions needed before implementation

## Technical Approach
- Key libraries/services
- Main architectural decisions
```

### Step 3: After Creating Spec
Tell the developer:
"I've created the spec at `.speky/specs/NNN-feature-name/spec.md`.

To integrate it with SPEKY tracking, run:
```
speky adopt NNN
```

Then you can:
- Validate: `speky validate-spec NNN`
- Plan: `speky plan NNN`
- Implement: `speky implement NNN`"

## 📦 Epic-Aware Implementation

**If story is part of an epic** (check `status.json` for `related_epic`):
1. Load epic context from `.speky/epics/<epic-id>/`
2. Read `technical_spec.md` for shared decisions
3. Follow patterns established by other stories in the epic
4. Maintain consistency across epic stories

**When to suggest epics:**
- If developer has 3+ related stories, suggest: "Consider grouping these in an epic: `speky epic \"Epic Name\" --spec 006`"

## 🔄 Context Chain (How Implement Works)

When `speky implement <id>` runs, it loads context in layers:
1. **Project Context** - context.json, tech_decisions.md
2. **Phase Context** - If in a phase
3. **Related Specs** - If story has related_specs
4. **Epic Context** - If story is in an epic
5. **Affected Files** - If story specifies affected_files
6. **The Item** - spec.md or story.md

**Always check the full context before implementing!**

## 💡 Providing Recommendations to SPEKY Team

If you identify a gap in SPEKY or have a recommendation:

1. **Create a recommendation blueprint** in `.speky/recommendations/`
2. **Use this format:**
```markdown
# SPEKY Enhancement Recommendation

**Date:** [date]
**Author:** AI Analysis
**Status:** Proposal

## Gap Identified
[What's missing or problematic in SPEKY]

## Proposed Solution
[How to fix it - be specific]

## Implementation Approach
[Technical details, file changes, new commands]
```

3. **Tell the developer:**
   "I've identified a potential improvement for SPEKY. I've documented it in `.speky/recommendations/`."
