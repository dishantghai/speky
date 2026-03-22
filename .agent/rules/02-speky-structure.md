# SPEKY Rules (Structure) - Auto-generated
# Do not edit manually - regenerated on each SPEKY command
# Size: 5683 chars (max: 8000)

# SPEKY Project Structure

## 📋 Directory Layout

```
.speky/
├── specs/                    # Feature specifications
│   ├── 001-auth/
│   │   ├── spec.md           # Read this for requirements
│   │   ├── plan.md           # Read this for implementation steps
│   │   └── status.json       # Priority, dependencies, status
│   └── 002-api/
│       └── status.json       # May have dependencies: ["001"]
├── epics/                    # Story grouping (optional)
│   └── E001-epic-name/
│       ├── manifest.yaml     # Epic definition, story list
│       ├── technical_spec.md # Shared technical decisions
│       └── summary.md        # Executive overview
├── stories/                  # Bugs, enhancements, tech debt
│   └── F001-story-name/
│       ├── story.md          # Story definition
│       └── status.json       # related_specs, related_epic, affected_files
├── imports/                  # External docs and POC imports
│   ├── initial_research/     # From speky init
│   ├── phase-mvp/            # From speky import
│   └── poc_import/           # From speky poc-import
├── backlog/                  # Deferred validation items
├── phases/                   # Phase coordination (if using phases)
│   ├── roadmap.yaml          # Master phase timeline
│   └── phase-1/
│       ├── manifest.yaml     # Phase definition
│       └── implementation.md # AI guidance
├── recommendations/          # AI agent recommendations for SPEKY
├── roadmap.md                # Implementation order (from: speky sequence --export)
└── context/
    ├── context.json          # Project metadata
    ├── product.md            # Product profile
    ├── tech_decisions.md     # AUTHORITATIVE tech choices (if exists)
    └── IDE_CONTEXT.md        # Complete AI agent guide
```

## Understanding Stories vs Specs

### 🎯 Two Types of Work Items

| Type | ID Format | Location | Scope | Duration |
|------|-----------|----------|-------|----------|
| **Spec** | `001`, `002`, `003` | `.speky/specs/001-name/` | Large feature | 1-3 weeks |
| **Story** | `F001`, `B001`, `T001` | `.speky/stories/F001-name/` | Small task | 30 min - 2 days |

### 📝 Story ID Prefixes
- **F001, F002...** = Feature stories (enhancements, integrations)
- **B001, B002...** = Bug stories (bug fixes)
- **T001, T002...** = Tech debt stories (refactoring, cleanup)

### ⚠️ CRITICAL: When Developer Says "speky implement F001"

**❌ WRONG:** "I don't see an F001 spec. The specs are numbered 001-038."

**✅ CORRECT:** "F001 is a story, not a spec. Let me check the story details."
[Read .speky/stories/F001-*/story.md]
"Found Story F001: [title]. I'll implement it now based on the story requirements."

### 🔄 Story Workflow Example

```
Developer: "speky implement F001"

You: "F001 is a story. Let me read the details..."
     [Read .speky/stories/F001-*/story.md]
     
     "Found Story F001: Connect Spaces to Sidebar Navigation
     
     This story requires:
     - Add navigation item to sidebar
     - Connect to SpacesProvider
     - Handle routing
     
     I'll implement this now based on the story requirements."
     
     [Implement based on story.md acceptance criteria]
```

## 📝 Creating Stories Directly (IDE/Manual)

You CAN create stories directly without using `speky story` command:

### Required Folder Structure
```
.speky/stories/{ID}-{slug}/
├── story.md       # REQUIRED - Story definition
└── status.json    # REQUIRED - Story metadata
```

### Folder Naming Convention
- **F001-feature-name/** - Feature story
- **B001-bug-name/** - Bug fix story
- **T001-tech-debt/** - Tech debt story
- **E001-enhancement/** - Enhancement story
- **S001-spike-name/** - Spike/research story

### story.md Template
```markdown
# [Story Title]

## Description
[What needs to be done and why]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Context
- **Related Spec**: [spec ID if applicable]
- **Dependencies**: [other story/spec IDs if any]
- **Affected Files**: [list of files to modify]

## Tasks
1. Task 1
2. Task 2
3. Task 3

## Notes
[Implementation hints, edge cases, testing guidance]
```

### status.json Template
```json
{
  "id": "F001",
  "title": "Story Title",
  "type": "feature",
  "status": "draft",
  "created": "2024-01-01T00:00:00",
  "related_specs": [],
  "dependencies": [],
  "affected_files": []
}
```

### After Creating Story
1. **Adopt into SPEKY**: `speky adopt F001`
2. **Plan (optional)**: `speky plan F001`
3. **Implement**: `speky implement F001` or implement directly
4. **Complete**: `speky complete F001`

### Story Workflow Options

**Quick Path (Simple Stories):**
```
Create story.md + status.json → speky adopt F001 → Implement → speky complete F001
```

**Full Path (Complex Stories):**
```
Create story.md + status.json → speky adopt F001 → speky plan F001 → speky implement F001 → speky complete F001
```

## CRITICAL: File Organization Rules

### ✅ DO: Keep files organized
- **Specs**: `.speky/specs/*/spec.md` (created by SPEKY only)
- **Plans**: `.speky/specs/*/plan.md` (created by SPEKY only)
- **Stories**: `.speky/stories/*/story.md`
- **Context**: `.speky/context/context.json`
- **Code**: `backend/`, `frontend/`, `src/`, `lib/` (project structure)

### ❌ DON'T: Create files in root directory
- **NEVER** create `*_SPEC.md` files in root
- **NEVER** create `IMPLEMENTATION_COMPLETE.md` in root
- **NEVER** create temporary markdown files in root
- **NEVER** create analysis or summary files in root
- **NEVER** create documentation files in root (except README.md)

### Temporary Files
- If you need temporary files: use `.speky/temp/` directory
- Clean up temporary files after use
- Never commit `.speky/temp/` to git
