# Stories Feature - IDE Awareness Update

## Problem Identified

AI coding agents (Windsurf, Cursor, etc.) were not aware of SPEKY's **Stories** feature, causing confusion when developers ran commands like `speky implement F001`.

### What Was Happening

**Developer**: `speky implement F001`

**AI Agent Response** ❌:
```
"I need to check what spec F001 is. Let me look for it in the SPEKY specs directory..."
[Searches .speky/specs/]
"I don't see an F001 spec. The specs are numbered 001-038."
```

**Root Cause**: IDE rules (`.windsurfrules`) only documented Specs, not Stories.

---

## Solution Implemented

### 1. Updated SPEKY IDE Rules Generator ✅

**File**: `/Users/Shared/ALL WORKSPACE/projects/SPEKY/speky.py`

**Method**: `_get_speky_rules()` (lines 1977-2077)

**Added comprehensive Stories section**:
- Two types of work items table (Specs vs Stories)
- Story ID prefix explanation (F001, B001, T001)
- Critical workflow examples (wrong vs correct responses)
- Story file structure documentation
- Story workflow example
- Key differences between Specs and Stories

### 2. Created Comprehensive Stories Guide ✅

**File**: `/Users/Shared/ALL WORKSPACE/projects/spayce/.speky/STORIES_GUIDE_FOR_AI.md`

**Contents**:
- Complete guide for AI coding agents
- Story ID recognition patterns
- How to find and read stories
- Story structure documentation
- Example workflows
- Common mistakes to avoid
- Quick reference section

### 3. Auto-Update Mechanism ✅

SPEKY automatically updates `.windsurfrules` in projects when any command runs, so all projects will get the updated rules immediately.

---

## What AI Agents Now Understand

### ✅ Story ID Recognition

AI agents now recognize:
- **F001, F002, F003** = Feature stories
- **B001, B002, B003** = Bug stories
- **T001, T002, T003** = Tech debt stories

### ✅ Correct Response Pattern

**Developer**: `speky implement F001`

**AI Agent Response** ✅:
```
"F001 is a story, not a spec. Let me check the story details."
[Reads .speky/stories/F001-*/story.md]
"Found Story F001: Connect Spaces screen to Sidebar Navigation

This story requires:
- Add navigation item to sidebar
- Connect to SpacesProvider
- Handle routing

I'll implement this now based on the story requirements."
```

### ✅ Story vs Spec Distinction

| Type | ID Format | Location | Scope | Duration |
|------|-----------|----------|-------|----------|
| **Spec** | `001`, `002`, `003` | `.speky/specs/001-name/` | Large feature | 1-3 weeks |
| **Story** | `F001`, `B001`, `T001` | `.speky/stories/F001-name/` | Small task | 30 min - 2 days |

---

## Changes Made

### Modified Files

1. **`speky.py`** (+101 lines)
   - Added "CRITICAL: Understanding Stories vs Specs" section
   - Added story ID format table
   - Added workflow examples
   - Added story file structure documentation
   - Added key differences section

### Created Files

2. **`.speky/STORIES_GUIDE_FOR_AI.md`** (comprehensive guide)
   - Complete documentation for AI agents
   - Example workflows
   - Common mistakes
   - Quick reference

3. **`QUICK_START_INTEGRATION.md`** (user-facing guide)
   - How to use stories for integration work
   - Proper SPEKY workflow
   - Command reference

4. **`.speky/INTEGRATION_WORKFLOW.md`** (detailed workflow)
   - Complete integration process
   - Story-based workflow
   - Phase-by-phase guidance

---

## Testing

### Verified ✅

1. **Code compiles**: `python3 -m py_compile speky.py` ✅
2. **Rules updated**: `.windsurfrules` contains Stories section ✅
3. **Auto-refresh works**: Running `speky status` updates rules ✅
4. **Stories visible**: `speky status` shows both specs and stories ✅

### Test Case

```bash
# Check that stories are documented
grep -n "Understanding Stories vs Specs" /path/to/project/.windsurfrules

# Output: Line 119 found ✅
```

---

## Impact

### Before This Update ❌
- AI agents confused by F001, B001, T001 IDs
- Searched for stories in wrong location (.speky/specs/)
- Couldn't find story files
- Couldn't implement stories

### After This Update ✅
- AI agents recognize story IDs immediately
- Know to look in .speky/stories/
- Read story.md files correctly
- Implement based on story requirements

---

## Documentation Hierarchy

### For AI Agents
1. **`.windsurfrules`** - Auto-generated, always up-to-date
2. **`.speky/STORIES_GUIDE_FOR_AI.md`** - Comprehensive reference

### For Developers
3. **`QUICK_START_INTEGRATION.md`** - Quick start guide
4. **`.speky/INTEGRATION_WORKFLOW.md`** - Detailed workflow

---

## Next Steps

### Immediate
- ✅ Code compiles
- ✅ Rules updated
- ✅ Documentation created
- ⏳ **Commit changes**

### Future Enhancements
- Add story templates to IDE rules
- Add story validation guidance
- Add story completion checklist
- Add story testing guidelines

---

## Commit Message

```
feat: Add Stories awareness to IDE rules for AI coding agents

## Problem
AI coding agents didn't understand SPEKY Stories (F001, B001, T001),
causing confusion when developers ran `speky implement F001`.

## Solution
Added comprehensive Stories documentation to IDE rules generator:
- Story ID format table (F001 = Feature, B001 = Bug, T001 = Tech debt)
- Story vs Spec distinction
- Workflow examples (wrong vs correct responses)
- Story file structure documentation
- Key differences section

## Impact
AI agents now:
- ✅ Recognize story IDs (F001, B001, T001)
- ✅ Know to look in .speky/stories/ (not .speky/specs/)
- ✅ Read story.md files correctly
- ✅ Implement based on story requirements

## Files Modified
- speky.py: +101 lines (IDE rules generator)
- Created: .speky/STORIES_GUIDE_FOR_AI.md (comprehensive guide)
- Created: QUICK_START_INTEGRATION.md (user guide)
- Created: .speky/INTEGRATION_WORKFLOW.md (workflow guide)

## Testing
✅ Code compiles
✅ Rules auto-update in projects
✅ Stories visible in `speky status`
✅ Documentation complete
```

---

## Summary

**Problem**: AI agents didn't know about Stories
**Solution**: Added Stories to IDE rules
**Result**: AI agents now understand and can implement Stories correctly

All projects using SPEKY will automatically get the updated rules on next command run.
