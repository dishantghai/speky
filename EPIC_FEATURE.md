# Epic Feature Guide

**Version:** 1.0  
**Date:** December 30, 2025  
**Status:** Implemented

---

## Overview

Epics are **optional organizational containers** that group related stories with shared context and documentation. They bridge the gap between individual stories and complete specs.

### When to Use Epics

| Use Epic | Don't Use Epic |
|----------|----------------|
| 3+ related stories | 1-2 standalone stories |
| Shared technical decisions | Unrelated changes |
| Coordinated implementation | Independent work |
| Enhancement suite for a feature | Simple bug fix |

### Key Concepts

```
┌─────────────────────────────────────────────────────────────┐
│                    SPEKY HIERARCHY                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  SPEC (006-spaces)                                           │
│  └── Original feature definition                             │
│                                                              │
│  EPIC (E001-spaces-enhancements)                             │
│  ├── manifest.yaml (stories list)                            │
│  ├── technical_spec.md (shared decisions)                    │
│  └── summary.md (business context)                           │
│                                                              │
│  STORIES (F005, F006, F007, F008, F009)                      │
│  └── Individual implementation tasks                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Commands

### Create Epic

```bash
# Create epic linked to a spec
speky epic "Spaces Enhancements" --spec 006

# Create epic with existing stories
speky epic "Auth Bug Fixes" --stories B001,B002,B003

# Create empty epic
speky epic "Future Improvements"
```

### Manage Stories

```bash
# Add story to epic
speky epic E001 --add F007

# Remove story from epic
speky epic E001 --remove F007

# Create story directly in epic
speky story "Add Item Dialog" --epic E001
```

### View Epics

```bash
# List all epics
speky epics

# Show epic details
speky epic E001
```

---

## File Structure

```
.speky/epics/E001-spaces-enhancements/
├── manifest.yaml           # Required: Epic definition
├── technical_spec.md       # Optional: Shared technical decisions
└── summary.md              # Optional: Executive overview
```

### manifest.yaml

```yaml
id: E001
name: "Spaces Enhancements"
description: "Five major enhancements to transform Spaces"
created: "2025-12-30T10:00:00"
updated: "2025-12-30T15:30:00"
related_spec: "006"
priority: P1
stories:
  - F005
  - F006
  - F007
  - F008
  - F009
docs:
  - technical_spec.md
  - summary.md
```

### technical_spec.md (Optional)

Shared technical decisions that apply to all stories in the epic:

```markdown
# Technical Specification: Spaces Enhancements

## Database Changes
- Add `last_modified` column to SpaceItemsTable
- Add `sort_order` column for drag-and-drop

## Performance Targets
- All operations < 100ms
- Lazy loading for large spaces

## Shared Patterns
- Use SpaceItemController for all item operations
- Follow existing context menu pattern from TabsScreen

## Testing Strategy
- Widget tests for each new component
- Integration tests for drag-and-drop
```

### summary.md (Optional)

Executive overview for stakeholders:

```markdown
# Spaces Enhancements - Executive Summary

## Overview
Five major enhancements to transform Spaces from basic content
organization into a production-ready workspace management tool.

## Business Value
- Improved user productivity
- Better content organization
- Competitive feature parity

## Timeline
- Estimated: 12 weeks
- Stories: 5
- Total effort: 50 story points

## Success Metrics
- Time to add item: < 3 seconds
- Search latency: < 200ms
- User satisfaction: 4.5+ stars
```

---

## Story Context Linking

Stories can link to specs, epics, or both:

### Story in Epic

```bash
speky story "Add Item Dialog" --epic E001
```

Creates story with:
```json
{
  "id": "F005",
  "title": "Add Item Dialog",
  "type": "feature",
  "status": "draft",
  "related_specs": ["006"],  // Inherited from epic
  "related_epic": "E001",
  "affected_files": []
}
```

### Story with Spec (No Epic)

```bash
speky story "Fix auth timeout" --type bug --spec 001
```

Creates story with:
```json
{
  "id": "B001",
  "title": "Fix auth timeout",
  "type": "bug",
  "status": "draft",
  "related_specs": ["001"],
  "related_epic": null,
  "affected_files": []
}
```

### Story with Multiple Specs

```bash
speky story "Refactor DB layer" --type tech_debt --specs 001,002,006
```

### Story with Affected Files

```bash
speky story "Fix crash" --type bug --spec 001 \
  --files lib/auth/controller.dart,lib/auth/service.dart
```

---

## Context Chain

When implementing a story in an epic, SPEKY loads the full context chain:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Project Context                                           │
│    • context.json (product info, tech stack)                 │
│    • tech_decisions.md (package choices)                     │
├─────────────────────────────────────────────────────────────┤
│ 2. Phase Context (if applicable)                             │
│    • manifest.yaml (phase scope)                             │
│    • implementation.md (phase guide)                         │
├─────────────────────────────────────────────────────────────┤
│ 3. Related Spec                                              │
│    • spec.md (original requirements)                         │
│    • plan.md (architecture)                                  │
├─────────────────────────────────────────────────────────────┤
│ 4. Epic Context                                              │
│    • manifest.yaml (epic overview)                           │
│    • technical_spec.md (shared decisions)                    │
│    • Other stories in epic (for awareness)                   │
├─────────────────────────────────────────────────────────────┤
│ 5. Affected Files (if specified)                             │
│    • Preview of files to modify                              │
├─────────────────────────────────────────────────────────────┤
│ 6. The Story                                                 │
│    • story.md (the actual task)                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Workflows

### Workflow 1: Enhancement Suite

After completing a spec, create an epic for enhancements:

```bash
# 1. Spec 006 (Spaces) is complete

# 2. Create epic for enhancements
speky epic "Spaces Enhancements" --spec 006

# 3. Create stories in epic
speky story "Add Item Dialog" --epic E001
speky story "Context Menus" --epic E001
speky story "Drag-and-Drop" --epic E001

# 4. Add shared technical spec
# Edit: .speky/epics/E001-spaces-enhancements/technical_spec.md

# 5. Implement each story
speky implement F005
# ... implement ...
speky complete F005

speky implement F006
# ... etc
```

### Workflow 2: Bug Fix Campaign

Group related bugs into an epic:

```bash
# 1. Create standalone bugs first
speky story "Fix token refresh" --type bug --spec 001
speky story "Fix session timeout" --type bug --spec 001
speky story "Fix logout crash" --type bug --spec 001

# 2. Realize they're related, create epic
speky epic "Auth Bug Fixes" --stories B001,B002,B003 --spec 001

# 3. Add shared context
# Edit: .speky/epics/E002-auth-bug-fixes/technical_spec.md

# 4. Implement
speky implement B001
```

### Workflow 3: Tech Debt Initiative

```bash
# 1. Create epic
speky epic "Database Migration" --specs 001,002,006

# 2. Create tech debt stories
speky story "Migrate users table" --type tech_debt --epic E003
speky story "Migrate spaces table" --type tech_debt --epic E003
speky story "Add migration tests" --type tech_debt --epic E003

# 3. Implement in order
speky implement T001
```

---

## Best Practices

### DO ✅

1. **Create epic when you have 3+ related stories**
2. **Link epic to the original spec** for context
3. **Add technical_spec.md** for shared decisions
4. **Use consistent patterns** across epic stories
5. **Track progress** with `speky epic E001`

### DON'T ❌

1. **Don't create epic for 1-2 stories** - overhead not worth it
2. **Don't put unrelated stories in same epic** - defeats purpose
3. **Don't skip the epic context** when implementing
4. **Don't duplicate spec content** in epic - link instead

---

## Epic vs Other Constructs

| Aspect | Spec | Story | Epic | Phase |
|--------|------|-------|------|-------|
| **Purpose** | Define feature | Single task | Group stories | Timeline |
| **Contains** | Requirements | Tasks | Stories | Specs |
| **Duration** | 1-3 weeks | 30min-2days | Variable | 4-6 weeks |
| **Plan** | Yes | No | No | Yes |
| **Shared docs** | Self-contained | None | Yes | Phase-level |

---

## Troubleshooting

### Epic not found

```bash
$ speky epic E001
Error: Epic not found: E001
```

**Solution:** Check if epic exists in `.speky/epics/`

### Story not added to epic

```bash
$ speky epic E001 --add F007
Warning: Story F007 not found
```

**Solution:** Create the story first, then add to epic

### Context not loading

If epic context isn't loading during implement:

1. Check story's `status.json` has `related_epic: "E001"`
2. Check epic's `manifest.yaml` lists the story
3. Run `speky epic E001` to verify

---

## Migration

### From Ad-Hoc Files

If you have ad-hoc documentation files:

```bash
# Current state
.speky/stories/
├── SPACES_ENHANCEMENTS_SPEC.md    # Ad-hoc
├── SPACES_ENHANCEMENTS_INDEX.md   # Ad-hoc
└── F005-F009 stories

# Create epic
speky epic "Spaces Enhancements" --spec 006 --stories F005,F006,F007,F008,F009

# Move content
mv SPACES_ENHANCEMENTS_SPEC.md .speky/epics/E001-spaces-enhancements/technical_spec.md

# Clean up
rm SPACES_ENHANCEMENTS_INDEX.md
```

---

## Summary

**Epics are for grouping related stories with shared context.**

- Use when: 3+ related stories
- Provides: Shared technical decisions, coordinated tracking
- Context: Loaded automatically during `implement`
- Optional: Not required for simple work

**Key commands:**
```bash
speky epic "Name" --spec 006    # Create
speky epic E001 --add F005      # Add story
speky epic E001                 # Show details
speky epics                     # List all
```

---

*For complete SPEKY documentation, see README.md and DOCUMENTATION.md*
