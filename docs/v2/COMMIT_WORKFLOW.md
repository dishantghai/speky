# SPEKY Commit Workflow - Flexible Git Integration ✅

## Overview

SPEKY handles the **commit** workflow with comprehensive context and drift detection. All other git operations (**fetch, pull, push**) are handled with standard git commands for maximum flexibility and independence.

## Workflow Philosophy

- **SPEKY manages:** Feature completion, drift detection, context sync, and commits
- **Git manages:** Fetch, pull, push, branching, merging, and all other git operations
- **Separation of concerns:** Each tool does what it does best
- **Flexibility:** Use any git workflow (rebase, merge, squash, etc.)
- **Independence:** No SPEKY dependencies on git operations

## Complete Workflow

### Step 1: Create Feature Spec
```bash
speky spec "Video transcription"
```

### Step 2: Generate Implementation Plan
```bash
speky plan 001
```

### Step 3: Implement the Feature
```bash
speky implement 001
# ... code in your IDE ...
```

### Step 4: Mark Complete and Commit
```bash
speky complete 001 && speky commit 001
```

Does:
- ✅ Detects drift between spec and implementation
- ✅ Syncs codebase context
- ✅ Updates status to "completed"
- ✅ Generates comprehensive commit message
- ✅ Commits changes locally

### Step 5: Use Git for Remote Operations
```bash
# Fetch latest changes from remote
git fetch

# Pull latest changes
git pull

# Push your commits
git push
```

## Command Reference

### SPEKY Commands (Workflow)

| Command | Purpose |
|---------|---------|
| `speky init "idea"` | Initialize project |
| `speky spec "name"` | Create feature spec |
| `speky plan 001` | Generate implementation plan |
| `speky implement 001` | Hand off to IDE |
| `speky complete 001 && speky commit 001` | Mark complete, then commit |
| `speky complete 001 && speky commit 001 --edit` | Mark complete + edit message + commit |
| `speky status` | Show project progress |
| `speky review 001` | Check spec-code alignment |

### Git Commands (Remote Operations)

| Command | Purpose |
|---------|---------|
| `git fetch` | Fetch latest from remote |
| `git pull` | Fetch and merge latest |
| `git push` | Push commits to remote |
| `git status` | Show git status |
| `git log` | Show commit history |
| `git branch` | Manage branches |
| `git merge` | Merge branches |
| `git rebase` | Rebase commits |

## Workflow Patterns

### Pattern 1: Simple Linear Workflow
```bash
# 1. Create and implement feature
speky spec "Feature 1"
speky plan 001
speky implement 001
# ... code ...

# 2. Commit locally
speky complete 001 && speky commit 001

# 3. Push when ready
git push
```

### Pattern 2: Multiple Features, Then Push
```bash
# 1. Create and implement multiple features
speky spec "Feature 1"
speky plan 001
speky implement 001
# ... code ...
speky complete 001 && speky commit 001

speky spec "Feature 2"
speky plan 002
speky implement 002
# ... code ...
speky complete 002 && speky commit 002

# 2. Push all at once
git push
```

### Pattern 3: With Custom Commit Messages
```bash
# 1. Implement feature
speky spec "Feature 1"
speky plan 001
speky implement 001
# ... code ...

# 2. Commit with custom message
speky complete 001 && speky commit 001 --edit
# Edit message in your editor
# Save and close

# 3. Push
git push
```

### Pattern 4: Feature Branches
```bash
# 1. Create feature branch
git checkout -b feature/video-transcription

# 2. Implement feature
speky spec "Video transcription"
speky plan 001
speky implement 001
# ... code ...

# 3. Commit with SPEKY
speky complete 001 && speky commit 001

# 4. Push feature branch
git push origin feature/video-transcription

# 5. Create pull request (on GitHub/GitLab)
# ... review and merge ...
```

### Pattern 5: Fetch Before Implementing
```bash
# 1. Get latest changes
git fetch
git pull

# 2. Implement feature
speky spec "Feature 1"
speky plan 001
speky implement 001
# ... code ...

# 3. Commit
speky complete 001 && speky commit 001

# 4. Push
git push
```

## Complete Example

```bash
# 1. Initialize SPEKY
speky init "Cooking video processor"

# 2. Create first feature
speky spec "Video transcription"
speky plan 001
speky implement 001
# ... code in IDE ...

# 3. Commit first feature
speky complete 001 && speky commit 001
# Output:
# ✅ Status updated: completed
# ✅ Committed: feat: Complete Video transcription (001)
# 
# To push your commits to remote:
#   git push
# 
# To fetch and pull latest changes:
#   git fetch
#   git pull

# 4. Create second feature
speky spec "Step extraction"
speky plan 002
speky implement 002
# ... code in IDE ...

# 5. Commit second feature with custom message
speky complete 002 && speky commit 002 --edit
# Edit message, save

# 6. Check git status
git status
# On branch main
# Your branch is ahead of 'origin/main' by 2 commits.

# 7. Push both commits
git push
# ✅ Pushed to origin/main

# 8. Check project status
speky status
# Shows both features as completed
```

## SPEKY Complete Command

### Basic Usage
```bash
speky complete 001 && speky commit 001
```

Does:
1. **Drift Detection** - Checks spec vs implementation
2. **Context Sync** - Updates codebase understanding
3. **Status Update** - Marks feature as completed
4. **Commit** - Creates comprehensive commit message

### With Custom Message
```bash
speky complete 001 && speky commit 001 --edit
```

Opens your editor to customize the commit message.

### Without Commit
```bash
speky complete 001
```

Just marks as complete, no commit (for review first).

## Git Operations

### Push Commits
```bash
git push
```

Pushes all local commits to remote.

### Fetch Latest
```bash
git fetch
```

Gets latest changes from remote without merging.

### Pull Latest
```bash
git pull
```

Fetches and merges latest changes.

### Check Status
```bash
git status
```

Shows current branch and uncommitted changes.

### View Commits
```bash
git log --oneline -10
```

Shows last 10 commits.

### Create Branch
```bash
git checkout -b feature/name
```

Creates and switches to new branch.

### Merge Branch
```bash
git merge feature/name
```

Merges feature branch into current branch.

## Commit Message Format

SPEKY generates comprehensive commit messages:

```
feat: Complete Video transcription (001)

## Summary
Completed implementation of: Video transcription
Spec ID: 001
Completed at: 2025-12-03T21:30:45

## Changes
- Implemented all acceptance criteria from spec
- Updated codebase context
- Synced documentation
- Verified spec-code alignment

## Testing
- All acceptance criteria verified
- Spec-code drift checked

## Related
Spec: .speky/specs/001/spec.md
Plan: .speky/specs/001/plan.md
```

You can edit this message with `--edit` flag.

## Workflow Benefits

✅ **Clear Separation** - SPEKY for workflow, git for operations  
✅ **Flexible** - Use any git workflow (rebase, merge, squash, etc.)  
✅ **Independent** - No SPEKY dependencies on git operations  
✅ **Comprehensive** - Drift detection + context sync + commits  
✅ **Professional** - Detailed commit messages with context  
✅ **Familiar** - Standard git commands for push/pull/fetch  

## Tips

1. **Always run `speky complete <id>` then `speky commit <id>`** - Don't commit manually
2. **Edit messages when needed** - Use `--edit` for custom messages
3. **Push regularly** - Don't let commits pile up
4. **Fetch before implementing** - Stay in sync with team
5. **Use feature branches** - For team collaboration
6. **Review before push** - Check `git log` before pushing
7. **Sync context** - Run `speky sync` regularly

## Troubleshooting

### "Git not found"
Install git or ensure it's in your PATH.

### "Git repository not initialized"
Initialize git:
```bash
git init
git remote add origin <url>
```

### "Commit failed"
Check git status:
```bash
git status
git add -A
git commit -m "message"
```

### "Push failed"
Check remote configuration:
```bash
git remote -v
git status
```

## Files Modified

- `/Users/Shared/ALL WORKSPACE/projects/SPEKY/speky.py`
  - Removed `cmd_push()` method
  - Removed `--push` flag from `complete` command
  - Updated `cmd_complete()` to show git command suggestions
  - Removed push-related CLI parser code

## Summary

**SPEKY handles:**
- Feature completion workflow
- Drift detection and sync
- Comprehensive commit messages
- Commit creation

**Git handles:**
- Fetch, pull, push
- Branching and merging
- Rebasing and squashing
- All remote operations

**Result:**
- Clean separation of concerns
- Maximum flexibility
- Professional workflow
- No SPEKY dependencies on git operations

---

**Use SPEKY for workflow, use git for remote operations!** 🚀
