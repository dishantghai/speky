# Story Completion Feature

## Overview

The `speky complete` command now supports both **specs** and **stories**, automatically detecting which type of item you're completing.

## Usage

```bash
# Complete a spec (with drift detection)
speky complete 001

# Complete a story (simpler workflow)
speky complete F001
speky complete B001
speky complete T001
```

## How It Works

### Auto-Detection

The command automatically detects whether you're completing a spec or story:

- **Spec**: Numeric ID (e.g., `001`, `002`, `038`)
- **Story**: Prefixed ID (e.g., `F001`, `B001`, `T001`)

### Story Completion Workflow

When completing a story (`speky complete F001`):

1. ✅ **Marks story as completed** in `status.json`
2. ✅ **Adds completion timestamp**
3. ✅ **Shows epic progress** (if story is in an epic)
4. ✅ **Suggests next steps** (commit, check epic, implement next story)

**No drift detection** - Stories are smaller tasks that don't require full drift analysis.

### Spec Completion Workflow

When completing a spec (`speky complete 001`):

1. ✅ **Drift detection** - Categorized analysis of spec vs implementation
2. ✅ **Interactive resolution** - Fix drift issues interactively
3. ✅ **Sync context** - Update codebase understanding
4. ✅ **Mark complete** - Update status with completion timestamp
5. ✅ **Intelligent next steps** - Phase-aware, dependency-aware recommendations

## Example: Story Completion

```bash
$ speky complete F001

✅ Updated .windsurfrules

======================================================================
  ✅ Complete: F001
======================================================================

✅ Story completed: Connect Spaces to Sidebar Navigation
📝 Epic: E001 (1/9 stories completed)

──────────────────────────────────────────────────────────────────────
  Next Steps
──────────────────────────────────────────────────────────────────────

1. Commit your changes:
   git add .
   git commit -m "feat(F001): Connect Spaces to Sidebar Navigation"
   git push

2. Check epic progress:
   speky epic E001

3. Implement next story in epic:
   speky status  # See remaining stories
```

## Example: Spec Completion

```bash
$ speky complete 006

✅ Updated .windsurfrules

======================================================================
  ✅ Complete: 006
======================================================================

──────────────────────────────────────────────────────────────────────
  Drift Detection
──────────────────────────────────────────────────────────────────────
Analyzing spec vs implementation

✅ No drift detected - spec and implementation aligned

──────────────────────────────────────────────────────────────────────
  Syncing Context
──────────────────────────────────────────────────────────────────────
Updating codebase understanding

✅ Status updated: completed

──────────────────────────────────────────────────────────────────────
  Next Steps
──────────────────────────────────────────────────────────────────────

1. Commit your changes:
   speky commit 006
   speky commit 006 --edit  # to edit message

2. Next in implementation sequence:
   speky plan 007
   speky implement 007
   # Next feature name

3. View roadmap and what's next:
   speky sequence        # See full implementation order
   speky status          # See all specs status

4. Push to remote:
   git push
```

## Benefits

### For Stories
- ✅ **Quick completion** - No drift detection overhead
- ✅ **Epic-aware** - Shows progress within epic
- ✅ **Simple workflow** - Mark done and move on
- ✅ **Commit guidance** - Suggests proper commit message format

### For Specs
- ✅ **Quality assurance** - Drift detection ensures alignment
- ✅ **Interactive fixes** - Resolve issues before marking complete
- ✅ **Smart recommendations** - Phase and dependency-aware next steps
- ✅ **Context sync** - Keeps SPEKY's understanding up to date

## Migration Guide

If you have existing completed stories with manual status updates, they'll work seamlessly with the new command going forward.

### Before (Manual)
```bash
# Edit .speky/stories/F001-*/status.json manually
# Change "status": "draft" to "status": "completed"
```

### After (Automated)
```bash
# Just run the command
speky complete F001
```

## Integration with Epics

When completing a story that's part of an epic:

```bash
$ speky complete F001

✅ Story completed: Add Item Dialog
📝 Epic: E001 (3/9 stories completed)

Next Steps:
1. Commit your changes
2. Check epic progress: speky epic E001
3. Implement next story in epic
```

The epic automatically tracks completion progress:

```bash
$ speky epic E001

📦 Epic: E001 - Spaces Enhancements
   Related Spec: 006-spaces
   Priority: P1
   Stories: 9 total (3 completed, 2 in progress, 4 draft)
   
   Stories:
   ✅ F001 - Add Item Dialog (completed)
   ✅ F002 - Context Menus (completed)
   ✅ F003 - Drag-and-Drop (completed)
   🔄 F004 - Keyboard Shortcuts (in_progress)
   🔄 F005 - Bulk Actions (in_progress)
   ⬜ F006 - Search (draft)
   ⬜ F007 - Filters (draft)
   ⬜ F008 - Export (draft)
   ⬜ F009 - Import (draft)
```

## Technical Details

### Implementation

- **Method**: `cmd_complete(item_id)` - Main entry point
- **Story Handler**: `_complete_story(story_id)` - Handles story completion
- **Spec Handler**: `_complete_spec(spec_id)` - Handles spec completion (existing logic)

### Detection Logic

```python
is_story = item_id[0].isalpha() and len(item_id) >= 4
```

- Stories: Start with letter (F, B, T, E, S) + 3+ digits
- Specs: Pure numeric (001, 002, etc.)

### Status Update

Stories get a simple status update:

```json
{
  "id": "F001",
  "title": "Add Item Dialog",
  "type": "feature",
  "status": "completed",
  "related_epic": "E001",
  "created": "2025-12-28T10:00:00",
  "completed": "2025-12-30T18:00:00"
}
```

## See Also

- [EPIC_FEATURE.md](EPIC_FEATURE.md) - Complete epic documentation
- [README.md](README.md) - Full SPEKY documentation
- [IDE_CONTEXT.md](.speky/context/IDE_CONTEXT.md) - AI agent guide
