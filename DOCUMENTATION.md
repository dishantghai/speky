# SPEKY v2 - Complete Documentation

**AI-Assisted Scalable Engineering Framework**

A thin orchestration layer for AI-assisted software development. SPEKY manages context, generates specs, and integrates with your IDE (Windsurf, Cursor, Claude Code).

---

## Table of Contents

1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Philosophy](#philosophy)
4. [Installation](#installation)
5. [Quick Start](#quick-start)
6. [Complete Workflow](#complete-workflow)
7. [Commands Reference](#commands-reference)
8. [Features in Detail](#features-in-detail)
9. [Spec Sequencing Guide](#spec-sequencing-guide)
10. [Troubleshooting](#troubleshooting)
11. [Support](#support)

---

## Overview

SPEKY helps you:
- Create realistic, MVP-focused specifications
- Generate implementation plans with accurate timelines
- Track feature completion and progress
- Maintain spec-code alignment
- Collaborate with AI on technical decisions

### What SPEKY Does

✅ **Generate realistic specs** - MVP-focused, 1-2 pages, 1-2 stories  
✅ **Create accurate plans** - 3-8 tasks, <40 hours total  
✅ **Understand tech stack** - Scopes recommendations to your choices  
✅ **Track progress** - Status, completion, drift detection  
✅ **Sync documentation** - Keeps specs and code aligned  
✅ **Commit with context** - Comprehensive git messages  
✅ **Collaborate with AI** - Tech stack discussion, refinement  

### What SPEKY Does NOT Do (By Design)

❌ **Write production code** - That's your job (or your IDE's AI)  
❌ **Make architectural decisions** - You decide, SPEKY scopes  
❌ **Replace your IDE** - SPEKY is a companion, not a replacement  
❌ **Implement features end-to-end** - SPEKY plans, you implement  
❌ **Deploy automatically** - You control deployment  
❌ **Modify your code** - SPEKY only reads and analyzes  
❌ **Handle git push/pull/fetch** - Use standard git commands  

---

## Key Features

### MVP-Focused Specs & Plans

**Specs:**
- 1-2 user stories (not 5+)
- Explicit "Out of Scope" section
- Clear acceptance criteria
- Max 1-2 pages
- Research-aware generation (can incorporate existing docs)

**Plans:**
- 3-8 realistic tasks (not 10+)
- Each task 2-8 hours
- Total timeline <40 hours
- Top 2-3 risks with mitigations
- Dependency validation before planning

### Collaborative Tech Stack Discussion

- AI suggests 3 options for each layer (Frontend, Backend, Database, Deployment)
- Developer reviews suggestions and makes informed choices
- Optional discussion/refinement for each choice
- Developer reasoning captured in context
- Initial research integration (pre-populates from docs)

### Smart Context Management

- Product profile with features list
- Tech stack stored and used for all generation
- Automatic IDE context updates
- Spec-code drift detection
- Comprehensive commit messages
- Auto-updating IDE rules

### Spec Sequencing & Dependencies

- **Priority Tracking** (P0-P3) for all specs
- **Dependency Management** - Track which specs depend on others
- **AI Inference** - Automatically detect dependencies
- **Conflict Detection** - Resolve overlaps during POC import
- **Implementation Roadmap** - See optimal implementation order
- **Validation** - Warns before implementing out of order
- **Circular Detection** - Identifies dependency loops

### Testing Integration

SPEKY provides comprehensive testing integration with modular test runners, TDD workflow, and auto-generated testing guides.

**Core Capabilities:**
- **Modular Test Runners** - Auto-detects Flutter, Python, JavaScript test suites
- **Real-Time Output** - Streams test results as they run with accurate counts
- **Coverage Parsing** - Automatic coverage extraction from lcov.info
- **TESTING_GUIDE.md Generation** - Auto-generates comprehensive project testing guide
- **Mid-Project Refresh** - Updates guide with actual test counts and coverage
- **TDD Workflow** - Complete RED-GREEN-REFACTOR cycle with state tracking
- **Spec-Linked Tests** - Traceability from tests to specs
- **Test Recommendations** - AI-powered test suggestions based on changed files

**Testing Guide Generation:**
- **At Init**: Creates template guide with commands, TDD workflow, best practices
- **Mid-Project**: `speky test refresh-guide` updates with actual test counts, coverage data, and directory structure
- **Tech-Specific**: Includes sections only for detected tech stacks (Flutter/Python/Jest)

**TDD Workflow:**
1. `speky implement <id> --tdd` - Generate test task
2. Create tests based on task
3. `speky test tdd-red <id>` - Verify tests fail (RED phase)
4. Implement the feature
5. `speky test tdd-green <id>` - Verify tests pass (GREEN phase)
6. `speky complete <id>` - Run regression tests

**Modular Architecture:**
- Extensible `BaseTestRunner` interface
- Concrete runners: `FlutterTestRunner`, `PytestRunner`, `JestRunner`
- Auto-detection via project markers (pubspec.yaml, requirements.txt, package.json)
- Real-time output streaming to terminal
- Standardized `TestResult` format across platforms

### External Knowledge Import

- **Import PRDs/Specs** - From `.speky/imports/<phase>/source/`
- **Interactive Review** - Accept/modify/split/merge proposed specs
- **POC Import** - Extract features from existing codebases
- **Reconciliation** - Align code with imported documentation
- **Traceability** - Link specs back to source documents
- **Document Analysis** - AI categorizes and analyzes docs

### Spec Quality & Validation

- **Format Validation** - Check required sections
- **AI Quality Analysis** - Identify gaps and issues
- **Interactive Review** - Walk through issues one-by-one
- **Defer Management** - Route items by priority (story vs backlog)
- **Adoption** - Bring IDE-created specs into SPEKY tracking

---

## Philosophy

- **Orchestrate, don't replace** — Use your IDE for coding, SPEKY for context
- **Tech/IDE/Scale agnostic** — No assumptions about your stack
- **Ongoing development** — Supports continuous stories, not just initial scaffolding
- **Human in the loop** — You decide, AI assists
- **MVP-first** — Realistic specs and plans that can actually be implemented
- **Clean separation** — SPEKY for workflow, git for remote operations

---

## Installation

### Prerequisites

- Python 3.8+
- Git
- Anthropic API key

### Setup

1. **Install dependencies:**
   ```bash
   pip install anthropic
   ```

2. **Set API key:**
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

   Or create `.env` file:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

3. **Verify installation:**
   ```bash
   python3 speky.py
   ```

---

## Quick Start

### 1. Initialize Project

```bash
python3 speky.py init "Your product idea"
```

This will:
- Ask clarifying questions about your product
- Build a product profile
- Discuss tech stack with AI suggestions
- Create `.speky/` directory structure
- Generate `IDE_CONTEXT.md` explaining SPEKY

### 2. Create Feature Spec

```bash
python3 speky.py spec "Feature name"
```

Generates:
- 1-2 user stories (MVP-focused)
- Functional & non-functional requirements
- Clear out-of-scope items
- Technical approach using your tech stack

### 3. Generate Implementation Plan

```bash
python3 speky.py plan 001
```

Generates:
- 3-8 realistic tasks
- Time estimates per task (2-8 hours each)
- Total timeline <40 hours
- Top 2-3 risks with mitigations

### 4. Implement Feature

```bash
python3 speky.py implement 001
```

Prepares:
- Full context in `.windsurfrules`
- Spec and plan details
- Tech stack information
- Opens your IDE

### 5. Mark Complete and Commit

```bash
python3 speky.py complete 001 --commit
```

Does:
- Detects drift between spec and implementation
- Syncs codebase context
- Updates status to "completed"
- Generates comprehensive commit message
- Commits changes locally

### 6. Push to Remote

```bash
git push
```

Use standard git commands for all remote operations.

---

## Complete Workflow

### Example: Implement 3 Features

```bash
# 1. Initialize
python3 speky.py init "Cooking video processor"

# 2. Feature 1: Video Transcription
python3 speky.py spec "Video transcription"
python3 speky.py plan 001
python3 speky.py implement 001
# ... code in IDE ...
python3 speky.py complete 001 --commit

# 3. Feature 2: Step Extraction
python3 speky.py spec "Step extraction from transcript"
python3 speky.py plan 002
python3 speky.py implement 002
# ... code in IDE ...
python3 speky.py complete 002 --commit --edit
# Edit message, save

# 4. Feature 3: Ingredient Extraction
python3 speky.py spec "Ingredient extraction and categorization"
python3 speky.py plan 003
python3 speky.py implement 003
# ... code in IDE ...
python3 speky.py complete 003 --commit

# 5. Push all commits
git push

# 6. Check progress
python3 speky.py status
```

---

## Commands Reference

### Import Quick Start

Use the predefined import folder. No arbitrary paths.

```
# 1) Create (or ensure) the phase folder exists
speky import --phase <phase>

# 2) Place documents here
.speky/imports/<phase>/source/

# 3) Process documents (analyze + interactive review)
speky import --phase <phase>

# Next steps
speky validate-spec 001   # optional but recommended
speky plan 001
speky implement 001
```

Notes:
- Imported specs are already tracked in SPEKY (no adoption needed).
- Use `speky adopt <id>` only for IDE-created specs placed at `.speky/specs/<id>-<name>/spec.md`.

### Initialization

```bash
speky init "Your product idea"
```

Initialize SPEKY for a new project. Includes collaborative tech stack discussion.

### Specification

```bash
speky spec "Feature name"
```

Create a feature specification. Generates 1-2 user stories, requirements, and out-of-scope items.

### Planning

```bash
speky plan 001
```

Generate implementation plan for a spec. Creates 3-8 realistic tasks with time estimates.

### Stories

```bash
speky story --type bug "Bug title"
speky story --type enhancement "Enhancement title"
speky story --type tech_debt "Tech debt title"
```

Create additional stories (bugs, enhancements, tech debt, spikes).

### Implementation

```bash
speky implement 001
```

Hand off to IDE for implementation. Opens your IDE with full context.

### Completion

```bash
speky complete 001 --commit
speky complete 001 --commit --edit
```

Mark feature as complete, detect drift, sync context, and commit.

- `--commit` / `-c` - Commit changes to git
- `--edit` / `-e` - Edit commit message before committing

### Status

```bash
speky status
```

Show project status. Lists all specs and stories with their status.

### Sync

```bash
speky sync
```

Sync codebase context. Updates SPEKY's understanding of your code.

### Review

```bash
speky review 001
speky review
```

Check for spec-code drift. Verify implementation matches specification.

### Cleanup

```bash
speky cleanup           # Clean up clutter files
speky cleanup --dry-run # Show what would be deleted
```

Remove clutter files from project root. SPEKY generates comprehensive IDE rules that prevent file clutter, but if your IDE accidentally creates files like `*_SPEC.md` or `IMPLEMENTATION_COMPLETE.md` in the root directory, this command removes them.

**Files cleaned:**
- `*_SPEC.md` - Duplicate spec files
- `IMPLEMENTATION_COMPLETE.md` - Completion markers
- `implementation_notes.md` - Temporary notes
- `analysis_*.md` - Analysis files
- `.speky/temp/*` - Temporary directory

### Spec Validation & Quality

#### Validate Spec

```bash
speky validate-spec 001              # By spec ID
speky validate-spec .speky/specs/001-feature/spec.md  # By file path
speky validate-spec 001 --quick      # Quick mode (non-interactive)
```

Validate spec quality and find gaps. Checks:
- Required sections present (Overview, MVP Scope, Requirements, Out of Scope)
- MVP focus (achievable in 1-2 weeks)
- Clear requirements and acceptance criteria
- Technical feasibility
- Realistic scope

**Interactive Mode** (default): Walk through each issue one by one with options to:
- Add to fix list (with comments)
- Skip / Mark as not relevant
- Get AI suggestions and fix now
- Defer for later (with priority)

**Quick Mode** (`--quick`): Show all gaps and suggestions at once without prompts.

Works with ANY spec:
- Specs created with `speky spec`
- Specs imported with `speky import`
- Specs adopted with `speky adopt`

#### Adopt IDE-Created Spec

```bash
speky adopt 004                    # Adopt spec by ID
speky adopt 004 --skip-validation  # Skip validation
```

Adopt an IDE-created spec into SPEKY tracking. Use when:
- Your IDE creates a spec.md file directly
- You want to bring it into SPEKY workflow

Process:
1. Validates basic format (required sections)
2. Creates status.json if missing
3. Adds spec to SPEKY tracking
4. Enables plan/implement/complete commands

**Workflow Options:**
- **Validate First** (recommended): `validate-spec` → fix → `adopt` → `plan`
- **Quick Adopt**: `adopt` → (optional `validate-spec`) → `plan`

### Backlog Management

```bash
speky backlog
```

Review and manage deferred validation items. When validating specs, you can defer items by priority:
- **High Priority** → Convert to stories for next iteration
- **Medium/Low Priority** → Keep in backlog for later review

This prevents feature creep and helps prioritize work.

### External Knowledge Import

#### Import External Documentation

```bash
speky import --phase mvp                    # Import with interactive review
speky import --phase mvp --no-review        # Import without review
```

Import external documentation (PRD, tech specs, design docs, etc.) and automatically decompose into SPEKY specs.

**Process:**
1. Place documents in `.speky/imports/<phase>/source/`
2. Run `speky import --phase <phase>`
3. AI analyzes documents and proposes specs
4. Interactive review: accept/modify/split/remove each spec
5. Specs are created and automatically tracked

**Key Point:** Imported specs are already in SPEKY tracking. No adoption needed.

**Next steps after import:**
- Review roadmap: `.speky/imports/<phase>/roadmap.md`
- Validate specs (optional): `speky validate-spec 001`
- Generate plan: `speky plan 001`
- Implement: `speky implement 001`

#### Import Status

```bash
speky import-status
```

Show status of all imports and their derived specs. Displays:
- All import phases
- Number of documents per import
- Specs created from each import
- Import metadata and status

#### Reconcile Code with Imports

```bash
speky reconcile mvp                  # Reconcile all specs from import
speky reconcile mvp --spec 001       # Reconcile specific spec
speky reconcile mvp --dry-run        # Preview changes without applying
```

Reconcile code implementation with imported documentation and specs. Detects:
- Mismatches between spec and implementation
- Features implemented but not in spec
- Spec features not yet implemented
- Technical approach deviations

**Interactive Resolution:**
- Review each mismatch
- Get AI clarifying questions
- Update specs or create tasks
- Maintain traceability to source documents

### POC Code Import

```bash
speky poc-import                     # Interactive POC import
speky poc-import --path /path/to/poc # Provide POC path directly
speky poc-import --resume            # Resume incomplete session
speky poc-import --spec 003          # Link POC to existing spec
```

Import features from existing POC (proof-of-concept) codebase. Analyzes code, extracts features, and creates specs.

**Workflow:**
1. Provide POC path(s)
2. IDE analyzes POC code (follows `task.md`)
3. Select features to import (natural language: "auth and api but not admin")
4. AI resolves conflicts and recommends approach
5. IDE creates specs (follows `extraction_task.md`)
6. Specs automatically adopted into SPEKY

**Conflict Detection:**
- Detects when POC features overlap with existing specs
- Shows AI recommendation (Skip, Replace, Merge, Keep Both)
- Interactive resolution with detailed comparison
- Preserves traceability

**Key Features:**
- Feature-based selection (not module-based)
- Natural language parsing
- Resumable workflow (state saved)
- Transparent (all files editable)
- Dependency preservation from POC analysis

### Spec Sequencing & Dependencies

#### View Implementation Roadmap

```bash
speky sequence              # Show roadmap in terminal
speky sequence --export     # Export to .speky/roadmap.md
```

View unified implementation roadmap with dependency analysis. Shows:
- **Summary**: Total specs, count by priority/status
- **Circular Dependencies**: Warns about dependency loops
- **Implementation Order**: Sorted by dependencies and priority
- **Dependency Tree**: Foundation specs vs dependent specs
- **Specs by Source**: Grouped by origin (init, POC, import, manual)
- **Next Steps**: Suggests which spec to implement next

**Priority Levels:**
- **P0** (Blocker): Must be done immediately
- **P1** (High): Core functionality, MVP features
- **P2** (Medium): Important but not critical
- **P3** (Low): Nice-to-have, future enhancements

**Example Output:**
```
📊 Total Specs: 4
   P0 (Blocker): 0
   P1 (High): 3
   P2 (Medium): 1

📋 Recommended Implementation Order

⚡ P1 - HIGH PRIORITY:
   1. ⬜ 001-auth (initial_research)
   2. ⬜ 002-api (poc_import) [needs: 001]
   3. ⬜ 004-payments (poc_import) [needs: 002]

📋 P2 - MEDIUM PRIORITY:
   4. ⬜ 003-notifications (manual) [needs: 001]

📋 Next Steps:
   1. Run: speky plan 001
   2. Run: speky implement 001
```

#### AI Dependency Inference

```bash
speky infer-deps              # Analyze all specs
speky infer-deps 003          # Analyze specific spec
```

Automatically detect dependencies between specs using AI analysis. The AI:
- Analyzes spec content against all existing specs
- Identifies true dependencies (not just related specs)
- Shows reasoning for each dependency
- Adds to `status.json` (preserves manual dependencies)

**What Counts as Dependency:**
- Requires functionality from another spec
- Builds upon or extends another spec
- Cannot be implemented without the other being done first
- Uses data models, APIs, or services defined in another

**Example Output:**
```
📋 Analyzing: 003-payments

🔗 Inferred dependencies:
   • 001: Needs authentication before payment can be secured
   • 002: Uses API endpoints defined in API spec

✅ Added dependencies: 001, 002
```

#### Dependency Validation

SPEKY automatically validates dependencies before planning or implementing:

```bash
speky plan 003      # Validates dependencies first
speky implement 003 # Validates dependencies first
```

**Warning Example:**
```
⚠️  DEPENDENCY WARNING for spec 003
   The following dependencies are not yet completed:

   • 001 (status: draft)
   • 002 (status: in_progress)

   Consider implementing these first, or proceed if you're sure.
   Run 'speky sequence' to see recommended order.

Continue anyway? [y/N]:
```

**Benefits:**
- Prevents implementing specs out of order
- Avoids rework from missing dependencies
- Ensures stable foundations
- Reduces integration issues

---

## Features in Detail

### IDE Integration & File Organization

SPEKY automatically generates IDE rules (`.windsurfrules`, `.cursorrules`, `CLAUDE.md`) that:

1. **Prevent file clutter** - Instructs IDE to NOT create files in root
2. **Guide implementation** - Points to spec and plan locations
3. **Enforce organization** - All SPEKY artifacts stay in `.speky/`

**File Organization:**
```
project/
├── .speky/
│   ├── specs/001-feature/spec.md    # Specs go here
│   ├── specs/001-feature/plan.md    # Plans go here
│   ├── context/context.json         # Context here
│   └── temp/                        # Temporary files (cleaned up)
├── backend/                         # Your code
├── frontend/                        # Your code
├── README.md                        # Only allowed .md in root
└── .windsurfrules                   # Auto-generated IDE rules
```

**What IDE should NOT create:**
- ❌ `FEATURE_SPEC.md` in root
- ❌ `IMPLEMENTATION_COMPLETE.md` in root
- ❌ Any temporary `.md` files in root

### Drift Detection

When you run `speky complete`, it automatically:
1. Compares spec requirements with implementation status
2. Checks acceptance criteria completion
3. Verifies out-of-scope items not implemented
4. Detects technical approach alignment

If drift is found, you can:
- Continue with completion (drift is noted)
- Fix issues first (cancel and resolve)

### Commit Message Editing

Edit commit messages before committing:

```bash
speky complete 001 --commit --edit
```

Your default editor opens with the auto-generated message. You can:
- Add additional context
- Customize the message
- Follow your team's conventions

### Tech Stack Integration

SPEKY uses your tech stack to:
- Scope feature specifications
- Estimate task durations
- Suggest technical approaches
- Generate relevant recommendations

### IDE Context Guide

When you initialize a project, `.speky/context/IDE_CONTEXT.md` is created explaining:
- What SPEKY is and how to use it
- Your project details and tech stack
- All available commands
- What SPEKY CAN and CANNOT do
- Tips for success

### Comprehensive Commits

Commit messages include:
- Feature name and spec ID
- Summary of what was completed
- List of changes made
- Testing verification
- Drift notes (if any)
- Links to spec and plan files

Example:
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

---

## Workflow Patterns

### Pattern 1: Simple Linear

```bash
speky spec "Feature"
speky plan 001
speky implement 001
# ... code ...
speky complete 001 --commit
git push
```

### Pattern 2: Batch Commits

```bash
speky complete 001 --commit
speky complete 002 --commit
speky complete 003 --commit
git push
```

### Pattern 3: With Custom Messages

```bash
speky complete 001 --commit --edit
speky complete 002 --commit --edit
git push
```

### Pattern 4: Feature Branches

```bash
git checkout -b feature/name
speky spec "Feature"
speky plan 001
speky implement 001
# ... code ...
speky complete 001 --commit
git push origin feature/name
# Create pull request
```

---

## Git Integration

### SPEKY Handles

- Feature completion workflow
- Drift detection and sync
- Comprehensive commit messages
- Commit creation

### Git Handles

- Fetch, pull, push
- Branching and merging
- Rebasing and squashing
- All remote operations

### Git Commands

```bash
# Fetch latest
git fetch

# Pull latest
git pull

# Push commits
git push

# Check status
git status

# View commits
git log --oneline -10

# Create branch
git checkout -b feature/name

# Merge branch
git merge feature/name
```

---

## Project Structure

```
your-project/
├── .speky/                                    # SPEKY directory (all framework files)
│   ├── config.yaml                            # Configuration
│   │
│   ├── context/                               # Project context
│   │   ├── context.json                       # Project metadata & tracking
│   │   ├── product.md                         # Product profile
│   │   └── IDE_CONTEXT.md                     # IDE integration guide
│   │
│   ├── specs/                                 # Feature specifications
│   │   ├── 001-user-authentication/
│   │   │   ├── spec.md                        # Feature specification
│   │   │   ├── plan.md                        # Implementation plan
│   │   │   ├── status.json                    # Status, priority, dependencies
│   │   │   └── research/                      # Optional: research docs
│   │   ├── 002-api-endpoints/
│   │   │   ├── spec.md
│   │   │   ├── plan.md
│   │   │   └── status.json                    # dependencies: ["001"]
│   │   └── ...
│   │
│   ├── stories/                               # Additional stories
│   │   ├── bug-001-fix-login/
│   │   │   ├── story.md
│   │   │   ├── plan.md
│   │   │   └── status.json
│   │   ├── enhancement-001-dark-mode/
│   │   └── tech-debt-001-refactor-auth/
│   │
│   ├── imports/                               # External knowledge imports
│   │   ├── initial_research/                  # From speky init
│   │   │   ├── source/                        # Original documents
│   │   │   │   ├── prd.md
│   │   │   │   ├── requirements.pdf
│   │   │   │   └── notes.txt
│   │   │   ├── analysis.md                    # AI analysis (editable)
│   │   │   └── manifest.json                  # Import metadata
│   │   │
│   │   ├── phase-mvp/                         # From speky import --phase mvp
│   │   │   ├── source/                        # Original documents
│   │   │   │   ├── mvp-spec.md
│   │   │   │   └── tech-design.md
│   │   │   ├── analysis.md                    # AI analysis
│   │   │   ├── roadmap.md                     # Implementation roadmap
│   │   │   └── manifest.json                  # Import metadata
│   │   │
│   │   ├── phase-v2-features/                 # Additional phases
│   │   │   └── ...
│   │   │
│   │   └── poc_import/                        # POC code imports
│   │       └── poc-20241226-120000/           # Timestamped POC session
│   │           ├── state.json                 # Workflow state (resumable)
│   │           ├── task.md                    # IDE research task
│   │           ├── results.json               # POC analysis results
│   │           ├── recommendations.md         # AI recommendations
│   │           ├── extraction_task.md         # IDE extraction task
│   │           └── specs/                     # Extracted specs (before adoption)
│   │               ├── 001-auth/
│   │               └── 002-api/
│   │
│   ├── backlog/                               # Deferred validation items
│   │   └── backlog.json                       # Deferred issues by priority
│   │
│   ├── roadmap.md                             # Generated by: speky sequence --export
│   │
│   └── temp/                                  # Temporary files (gitignored)
│       └── ...
│
├── .windsurfrules                             # IDE rules (Windsurf)
├── .cursorrules                               # IDE rules (Cursor)
├── CLAUDE.md                                  # IDE rules (Claude Code)
│
├── .git/                                      # Git repository
├── .gitignore                                 # Git ignore rules
├── .env                                       # Environment variables (ANTHROPIC_API_KEY)
│
└── ... (your project code)                    # Your actual codebase
    ├── backend/
    ├── frontend/
    ├── src/
    └── ...
```

### Key Directories Explained

**`.speky/specs/`** - All feature specifications
- Each spec has: `spec.md`, `plan.md`, `status.json`
- `status.json` includes: priority (P0-P3), dependencies, source, status

**`.speky/imports/`** - External knowledge and POC imports
- `initial_research/` - Documents provided during `speky init`
- `phase-*/` - Documents imported via `speky import --phase <name>`
- `poc_import/` - POC code analysis via `speky poc-import`

**`.speky/stories/`** - Bug fixes, enhancements, tech debt
- Created via `speky story --type <type> "title"`
- Same structure as specs (story.md, plan.md, status.json)

**`.speky/backlog/`** - Deferred validation items
- Issues found during spec validation
- Organized by priority (High/Medium/Low)
- Reviewed via `speky backlog`

**`.speky/roadmap.md`** - Implementation roadmap
- Generated via `speky sequence --export`
- Shows dependency tree and recommended order

**IDE Rules Files** - Auto-generated and auto-updated
- `.windsurfrules` (Windsurf IDE)
- `.cursorrules` (Cursor IDE)
- `CLAUDE.md` (Claude Code)
- Contain SPEKY workflow rules and commands

---

## Troubleshooting

### API Key Issues

**Error:** `Could not resolve authentication method`

**Solution:**
1. Check `.env` file exists with `ANTHROPIC_API_KEY`
2. Or set environment variable: `export ANTHROPIC_API_KEY="sk-ant-..."`
3. Verify key is valid on Anthropic dashboard

### Git Issues

**Error:** `Git not found`

**Solution:**
1. Install git: `brew install git` (macOS) or `apt install git` (Linux)
2. Verify: `git --version`

**Error:** `Git repository not initialized`

**Solution:**
```bash
git init
git remote add origin <your-repo-url>
```

### Editor Issues

**Error:** `Failed to edit commit message`

**Solution:**
1. Set `$EDITOR`: `export EDITOR=vim`
2. Or use a full path: `export EDITOR=/usr/bin/vim`
3. Try again

### Drift Detection

**Issue:** Drift detected but you want to continue

**Solution:**
- When asked, press `y` to continue
- Drift notes are recorded in commit message
- Fix drift in next iteration

---

## Tips for Success

1. **Always start with a spec** - Don't code without one
2. **Follow the plan** - It's realistic and achievable
3. **Use `speky complete --commit`** - Ensures drift detection and proper tracking
4. **Edit messages when needed** - Use `--edit` for custom messages
5. **Review regularly** - Use `speky review` to catch drift early
6. **Sync often** - Keep codebase context up to date
7. **Ask AI for help** - SPEKY uses Claude for smart suggestions
8. **Push regularly** - Don't let commits pile up

---

## Files and Directories

### Main Files

- `speky.py` - Main framework
- `README.md` - Quick overview (this file)
- `DOCUMENTATION.md` - Complete documentation (this file)
- `.env` - API key configuration
- `requirements.txt` - Dependencies

### Project Files (Created by SPEKY)

- `.speky/config.yaml` - Configuration
- `.speky/context/context.json` - Project context
- `.speky/context/product.md` - Product profile
- `.speky/context/IDE_CONTEXT.md` - IDE guide
- `.speky/specs/*/spec.md` - Feature specifications
- `.speky/specs/*/plan.md` - Implementation plans
- `.speky/specs/*/status.json` - Status tracking

---

## Next Steps

1. **Install SPEKY:**
   ```bash
   pip install anthropic
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

2. **Initialize your project:**
   ```bash
   python3 speky.py init "Your product idea"
   ```

3. **Review the IDE context:**
   ```bash
   cat .speky/context/IDE_CONTEXT.md
   ```

4. **Create your first feature:**
   ```bash
   python3 speky.py spec "Your first feature"
   ```

5. **Generate a plan:**
   ```bash
   python3 speky.py plan 001
   ```

6. **Start implementing:**
   ```bash
   python3 speky.py implement 001
   ```

---

## External Knowledge Import

Import external documentation (PRDs, technical specs, implementation handoffs) and automatically decompose them into structured specs.

### Quick Start

```bash
# Step 1: Create import folder
speky import --phase mvp
# Creates: .speky/imports/mvp/source/

# Step 2: Place your documents in the folder
# Location: .speky/imports/mvp/source/
# Supported: .md, .txt, .pdf, .docx

# Step 3: Run import again to process
speky import --phase mvp

# Show all imports
speky import-status

# Reconcile code with imported docs after implementation
speky reconcile mvp
```

**Note:** Documents are always placed in `.speky/imports/<phase>/source/` - a predefined location within your project.

### Workflows

#### 1. Pre-Import Interactive Review

When you run `speky import`, SPEKY:
1. Scans folder for documents (.md, .txt, .pdf, .docx)
2. Auto-detects document type (product, technical, integration, security, implementation)
3. Analyzes content and proposes specs
4. Shows each proposal for interactive review

For each proposed spec, you can:
- **Accept** - Use as-is
- **Modify** - Change name, scope, estimate, or add notes
- **Split** - Break into multiple smaller specs
- **Merge** - Combine related specs
- **Remove** - Skip this spec
- **Question** - Ask AI clarifying questions

#### 2. Post-Implementation Reconciliation

After implementing specs from an import, run `speky reconcile <phase>` to:
1. Detect mismatches between code and imported docs
2. Interactively resolve each mismatch
3. Ask AI clarifying questions for ambiguities
4. Update specs/docs or create implementation tasks
5. Maintain traceability from specs to source documents

Use `--dry-run` to preview changes without applying.

### Folder Organization

Imports are stored in `.speky/imports/<phase>/`:
- `source/` - Original documents (preserved for reference)
- `manifest.json` - Import metadata and tracking
- `analysis.md` - AI analysis of documents
- `roadmap.md` - Implementation roadmap

Each derived spec includes `import_source` in its `status.json` for traceability.

### Document Type Detection

SPEKY automatically categorizes documents:
- **Product**: user stories, acceptance criteria, features
- **Technical**: architecture, API design, database schema
- **Integration**: external systems, webhooks, third-party APIs
- **Security**: compliance requirements, security constraints
- **Implementation**: step-by-step guides, handoff docs

### Use Cases

1. **New project with existing PRD**
   ```bash
   # Create/import phase folder (if not already created)
   speky import --phase mvp
   # Place PRD and related docs into .speky/imports/mvp/source/

   # Process documents (analyze + interactive review)
   speky import --phase mvp
   # Review proposed specs interactively
   # Create specs from import
   ```

2. **Mid-project integration handoff**
   ```bash
   # Create/import phase folder
   speky import --phase payments
   # Place handoff docs into .speky/imports/payments/source/

   # Process documents (analyze + interactive review)
   speky import --phase payments
   # Review and modify proposed specs
   # Plan and implement
   ```

3. **Phased implementation**
   ```bash
   # Phase A
   speky import --phase v2-features
   # Place technical PRD into .speky/imports/v2-features/source/
   speky import --phase v2-features
   # Import Phase A first

   # Phase B and C (separate folders)
   speky import --phase v2-phase-b
   # Place docs into .speky/imports/v2-phase-b/source/
   speky import --phase v2-phase-b
   # Import Phase B and C later as needed
   ```

4. **Post-implementation reconciliation**
   ```bash
   speky reconcile mvp
   # Detect mismatches between code and imported docs
   # Resolve with clarifying questions
   ```

### Best Practices

- **Use interactive review** - Catch misunderstandings early
- **Organize by phase** - Use meaningful phase names (mvp, v2-features, payments)
- **Keep source documents** - Reference them during planning
- **Reconcile after implementation** - Ensure code matches imported requirements
- **Leverage traceability** - Link specs back to requirements for audits

For complete details, see [IMPORT_FEATURE.md](IMPORT_FEATURE.md).

---

## Spec Sequencing Guide

SPEKY provides comprehensive spec sequencing and dependency management to ensure optimal implementation order.

### Quick Overview

**Commands:**
- `speky sequence` - View implementation roadmap
- `speky sequence --export` - Export roadmap to file
- `speky infer-deps` - AI-infer dependencies for all specs
- `speky infer-deps <id>` - AI-infer for specific spec

**Features:**
- **Priority Tracking** - P0 (Blocker) to P3 (Low)
- **Dependency Management** - Track which specs depend on others
- **AI Inference** - Automatically detect dependencies
- **Conflict Detection** - Resolve overlaps during POC import
- **Validation** - Warns before implementing out of order
- **Circular Detection** - Identifies dependency loops

### Priority Levels

| Priority | Name | When to Use |
|----------|------|-------------|
| **P0** | Blocker | Critical bugs, security issues, blockers |
| **P1** | High | Core functionality, MVP features |
| **P2** | Medium | Important but not critical |
| **P3** | Low | Nice-to-have, future enhancements |

### How Dependencies Work

Every spec can depend on other specs. SPEKY:
1. **Tracks** dependencies in `status.json`
2. **Validates** before planning/implementing
3. **Infers** using AI analysis
4. **Detects** circular dependencies
5. **Visualizes** in roadmap

### Example Workflow

```bash
# 1. Create specs from various sources
speky init "Recipe App"
speky poc-import --path /path/to/poc
speky spec "Admin Dashboard"

# 2. Infer dependencies
speky infer-deps

# 3. View roadmap
speky sequence

# 4. Implement in order (with validation)
speky plan 001      # Validates dependencies
speky implement 001
speky complete 001

# 5. Check updated roadmap
speky sequence
```

### Conflict Resolution (POC Import)

When importing POC features that overlap with existing specs:

**Options:**
1. **Skip** - Keep existing, add note about POC alternative
2. **Replace** - Deprecate existing, create new from POC
3. **Merge** - AI combines both approaches (RECOMMENDED)
4. **Keep Both** - Create both with cross-references

**AI Recommendation:**
- Analyzes both approaches
- Suggests best resolution
- Provides reasoning
- Shows merge strategy

### status.json Schema

```json
{
  "id": "001",
  "name": "User Authentication",
  "priority": "P1",
  "dependencies": ["002", "003"],
  "source": "initial_research|poc_import|external_import|manual",
  "status": "draft|planned|in_progress|completed",
  "created": "2024-01-01T00:00:00",
  "dependencies_inferred_at": "2024-01-02T00:00:00"
}
```

### For Complete Details

See [SEQUENCING.md](SEQUENCING.md) for:
- Detailed sequencing guide
- Dependency inference examples
- Conflict resolution workflows
- Best practices
- Troubleshooting circular dependencies
- Real-world examples

---

## Support

For issues or questions:
1. Check `.speky/context/IDE_CONTEXT.md` for detailed explanations
2. Review spec and plan files for context
3. Run `speky status` to see current progress
4. Use `speky review` to check for drift
5. See [IMPORT_FEATURE.md](IMPORT_FEATURE.md) for import-specific details

---

**Ready to build amazing products with realistic specs and plans!** 🚀
