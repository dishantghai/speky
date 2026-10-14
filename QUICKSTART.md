# SPEKY v2: Quick Start Guide

> **SPEKY v3 is available.** With a coding agent (Claude Code, Codex, Cursor, …) start with
> `speky setup claude-code` — no API key needed. See the Quick Start in [README.md](README.md) and [docs/v3/MIGRATION.md](docs/v3/MIGRATION.md) for existing projects.
> This guide covers the classic v2 commands, which still work unchanged.

## What is SPEKY v2?

SPEKY v2 is a **thin orchestration layer** for AI-assisted software development. It manages context, generates specs, and hands off to your IDE (Windsurf, Cursor, Claude Code) for implementation.

**Key differences from v1:**
- Command-based CLI (not a monolithic generator)
- IDE integration (updates `.windsurfrules`, `CLAUDE.md`, etc.)
- Supports ongoing development (stories, bugs, enhancements)
- Tech/IDE/Scale agnostic
- Fixed interactive flow (no hardcoded question limits)

---

## Installation

```bash
# 1. Install dependencies
pip install anthropic

# 2. Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 3. Create alias (optional but recommended)
alias speky="python /path/to/speky.py"
```

---

## Quick Start (5 minutes)

### Step 1: Initialize a Project

```bash
cd /path/to/your/project  # Can be empty or existing project
speky init "Your product idea"
```

Example:
```bash
speky init "A mobile app that converts cooking videos to step-by-step recipes"
```

SPEKY will:
1. Ask clarifying questions (answer all or skip some)
2. Build a product profile with features
3. **Collaborative Tech Stack Discussion** (NEW!)
   - AI suggests 3 options for Frontend, Backend, Database, Deployment
   - You review and choose (or defer decision)
   - Optional discussion/refinement for each choice
4. Create `.speky/` directory structure
5. Update your IDE context file (`.windsurfrules`)

### Step 2: Create a Feature Spec

```bash
speky spec "Feature name"
```

Example:
```bash
speky spec "Video transcription and step extraction"
```

SPEKY will:
1. **Generate MVP-focused spec** (NEW!)
   - 1-2 user stories (not 5+)
   - Explicit "MVP Scope" and "Out of Scope" sections
   - "Technical Approach" based on your tech stack
   - Max 1-2 pages (not 5+)
2. Save to `.speky/specs/001-feature-name/spec.md`

### Step 2.5: Generate Implementation Plan (Optional)

```bash
speky plan 001
```

SPEKY will:
1. **Generate realistic implementation plan** (NEW!)
   - 3-8 discrete tasks (not 10+)
   - Each task 2-8 hours (completable in 1 day)
   - Total <40 hours (implementable in 1-2 weeks)
   - Only blocking decisions
   - Top 2-3 risks with concrete mitigations
2. Save to `.speky/specs/001-feature-name/plan.md`

### Step 3: Implement

```bash
speky implement 001
```

SPEKY will:
1. Gather all context (product, spec, plan)
2. Update your IDE context file
3. Optionally open your IDE

Now code in Windsurf/Cursor with full context!

---

## All Commands

| Command | Description |
|---------|-------------|
| `speky init "idea"` | Initialize SPEKY with product idea |
| `speky spec "feature"` | Create feature specification |
| `speky plan <spec-id>` | Generate implementation plan |
| `speky story --type TYPE "title"` | Create story (bug/feature/enhancement) |
| `speky implement <id>` | Hand off to IDE |
| `speky status` | Show all specs and stories |
| `speky sync` | Analyze and sync codebase context |
| `speky review` | Check for spec-code drift |

---

## Story Types

For ongoing development after MVP:

```bash
# New feature
speky story --type feature "Add user preferences"

# Bug fix
speky story --type bug "Login fails on Safari"

# Enhancement
speky story --type enhancement "Improve video loading speed"

# Tech debt
speky story --type tech_debt "Refactor auth module"

# Research spike
speky story --type spike "Evaluate ML models for transcription"
```

---

## Directory Structure

After `speky init`, your project will have:

```
your-project/
├── .speky/
│   ├── config.yaml          # SPEKY settings
│   ├── context/
│   │   ├── context.json     # Machine-readable context
│   │   ├── product.md       # Human-readable product profile
│   │   └── codebase.md      # Codebase analysis (after sync)
│   ├── specs/
│   │   └── 001-feature/
│   │       ├── spec.md      # Feature specification
│   │       ├── plan.md      # Implementation plan
│   │       └── status.json  # Status tracking
│   └── stories/
│       └── B001-bug-fix/
│           ├── story.md
│           └── status.json
├── .windsurfrules           # Auto-generated IDE context
└── (your code)
```

---

## Configuration

Edit `.speky/config.yaml`:

```yaml
# AI model
model: claude-sonnet-4-20250514
max_tokens: 4096
temperature: 0.7

# IDE preference
ide: windsurf  # windsurf, cursor, claude-code, vscode

# MCP (coming soon)
mcp_enabled: false
```

---

## Workflow Example

### Initial Development

```bash
# 1. Initialize
speky init "Recipe video converter app"

# 2. Create first spec
speky spec "Video input and transcription"

# 3. Generate plan
speky plan 001

# 4. Implement
speky implement 001
# → Opens Windsurf with full context
# → Code your feature

# 5. Create next spec
speky spec "Step extraction from transcript"
# ... repeat
```

### Ongoing Development

```bash
# Bug reported
speky story --type bug "Video fails to load from TikTok"

# Implement fix
speky implement B001

# Enhancement requested
speky story --type enhancement "Support Instagram Reels"

# Check status
speky status
```

---

## IDE Integration

### Windsurf
SPEKY auto-generates `.windsurfrules` with:
- Product context
- Current spec/story
- Coding guidelines

### Cursor
Same as Windsurf, generates `.cursorrules`

### Claude Code
Generates `CLAUDE.md` for context

### Changing IDE
Edit `.speky/config.yaml`:
```yaml
ide: cursor  # or windsurf, claude-code, vscode
```

---

## Tips

1. **Always run from project root** - SPEKY looks for `.speky/` in current directory

2. **Review generated specs** - They're starting points, not gospel

3. **Use sync regularly** - Keeps codebase context up to date
   ```bash
   speky sync
   ```

4. **Check status often** - Track what's in progress
   ```bash
   speky status
   ```

5. **Specs are tech-agnostic** - Choose your stack during implementation

---

## Coming Soon

- **MCP Integration** - Direct codebase access for better context
- **Full Drift Detection** - Compare specs vs actual code
- **Parallel Execution** - Run multiple AI tasks simultaneously
- **Custom Agents** - Add domain-specific agents

---

## Troubleshooting

### "SPEKY not initialized"
Run `speky init "your idea"` first.

### API errors
Check `ANTHROPIC_API_KEY` is set correctly.

### IDE doesn't open
Manually open your IDE in the project directory.

---

## What's New in This Version

### MVP-Focused Specs & Plans
- **Specs** are now concise (1-2 pages max) with explicit scope boundaries
- **Plans** are realistic (3-8 tasks, <40 hours) and actually implementable
- Both are **tech-aware** and scoped to your chosen tech stack

### Collaborative Tech Stack Discussion
- AI suggests 3 options for each layer (Frontend, Backend, Database, Deployment)
- You review suggestions and make informed choices
- Optional discussion/refinement for each choice
- Your reasoning is captured in context

### Better Context Management
- Product profile now includes features list
- Tech stack is stored and used for all generation
- Specs and plans automatically consider your tech choices

See [IMPLEMENTATION_COMPLETE.md](IMPLEMENTATION_COMPLETE.md) and [TECH_STACK_DISCUSSION.md](TECH_STACK_DISCUSSION.md) for details.

## Philosophy

SPEKY v2 follows these principles:

1. **Orchestrate, don't replace** - Use Windsurf/Cursor for coding
2. **Context is king** - Manage and share context effectively  
3. **Human in the loop** - You make decisions, AI assists
4. **Ongoing, not one-shot** - Support continuous development
5. **Agnostic** - No assumptions about tech stack or scale
6. **MVP-first** - Realistic specs and plans that can actually be implemented
