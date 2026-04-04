# speky — Usage Guide

speky is an AI-assisted engineering orchestration tool. It sits between your idea and your IDE — generating specs, plans, and context so AI coding tools (Windsurf, Cursor, Claude Code) have everything they need to build it right.

---

## Core Concept

```
Your idea  →  speky init  →  speky spec  →  speky plan  →  speky implement  →  Code in your IDE
```

speky doesn't write code. It manages the thinking layer — product context, feature specs, stories, and codebase awareness — so your IDE's AI always has accurate, focused context.

---

## All Commands

| Command | What it does |
|---|---|
| `speky init "idea"` | Start a new project — AI interviews you, builds product profile, picks tech stack |
| `speky spec "Feature"` | Create a focused feature specification |
| `speky plan <id>` | Generate a realistic implementation plan for a spec |
| `speky story --type TYPE "Title"` | Create a story (bug, feature, enhancement, etc.) |
| `speky implement <id>` | Load context into your IDE and start building |
| `speky status` | Show all specs and stories with their status |
| `speky sync` | Analyze codebase and update context |
| `speky review` | Check for drift between specs and actual code |

---

## 1. `speky init` — Start a Project

**Use when:** Starting something new, or adding speky to an existing project.

```bash
cd my-project
speky init "A mobile app that converts cooking videos to step-by-step recipes"
```

speky will:
1. Ask 5 clarifying questions (problem, MVP scope, platform, scale, constraints)
2. Build a product profile from your answers
3. Suggest 3 tech stack options per layer (Frontend, Backend, Database, Deployment)
4. Let you pick each one and discuss trade-offs
5. Create the `.speky/` directory structure
6. Generate an IDE context file (`.windsurfrules`, `CLAUDE.md`, or `.cursorrules`)

**Example session:**

```
speky init "A team task tracker with AI prioritization"

→ What specific problem does this solve and for whom?
  > Developers on small teams lose track of priorities when context-switching

→ What would the MVP include?
  > Just task creation, assignment, and AI-suggested priority order

→ Platform?
  > Web app

→ Scale?
  > Small team, 5-10 people

→ Constraints?
  > Must be deployable on a $5/month server

✅ Product profile created
✅ Tech stack configured
✅ .speky/ initialized
✅ .windsurfrules updated
```

**What gets created:**

```
your-project/
├── .speky/
│   ├── config.yaml            # Model, IDE, MCP settings
│   ├── context/
│   │   ├── context.json       # Machine-readable product context
│   │   ├── product.md         # Human-readable product profile
│   │   └── tech_decisions.md  # Your tech stack choices + rationale
│   ├── specs/                 # Feature specs live here
│   └── stories/               # Bug/feature/enhancement stories
└── .windsurfrules             # Auto-generated IDE context file
```

---

## 2. `speky spec` — Create a Feature Spec

**Use when:** You want to build a new feature.

```bash
speky spec "Video transcription and step extraction"
```

speky generates a **concise, MVP-focused spec** (1-2 pages max):
- 1-2 user stories with acceptance criteria
- Explicit "MVP Scope" and "Out of Scope" sections
- Technical approach based on your chosen stack
- Open questions that block implementation

The spec is saved to `.speky/specs/001-video-transcription/spec.md`.

**Example output structure:**

```markdown
# Video Transcription and Step Extraction

## Overview
Converts a cooking video URL into a time-stamped transcript, then extracts
discrete steps using Claude AI.

## MVP Scope
- Accept YouTube and TikTok URLs
- Transcribe audio using Whisper API
- Extract 5-15 cooking steps from transcript

## User Stories
- As a user, I paste a video URL and receive step-by-step instructions
  - Acceptance: Steps are numbered, actionable, and cover the full recipe

## Out of Scope
Analytics, video caching, multi-language support, mobile optimization

## Open Questions
- Should steps include timestamps from the video?
- Max video length supported in MVP?

## Technical Approach
- Use yt-dlp to download audio
- OpenAI Whisper for transcription
- Claude claude-sonnet-4-20250514 for step extraction
```

**Import existing research:**

If you have notes, a PRD, or existing documentation, speky can use it as the spec foundation:

```bash
speky spec "Authentication System"
# → speky asks if you have existing research to import
# → Paste or point to your docs
# → Spec is generated incorporating your material
```

---

## 3. `speky plan` — Generate Implementation Plan

**Use when:** You have a spec and want a realistic task breakdown before coding.

```bash
speky plan 001
```

speky generates a **practical plan** (not an exhaustive one):
- 3-8 discrete tasks
- Each task completable in 2-8 hours
- Total under 40 hours (1-2 weeks of actual work)
- Top 2-3 risks with concrete mitigations
- Only the decisions that actually block progress

Plan saved to `.speky/specs/001-feature/plan.md`.

**Example:**

```bash
speky plan 001

✅ Plan generated: .speky/specs/001-video-transcription/plan.md

Tasks:
  Task 1 (3h): Set up yt-dlp audio extraction — handles YouTube/TikTok
  Task 2 (4h): Whisper transcription pipeline — async job queue
  Task 3 (5h): Claude step extraction prompt — tuning for cooking domain
  Task 4 (2h): API endpoint: POST /transcribe returns job_id
  Task 5 (3h): Polling endpoint: GET /job/:id returns status + steps
  Task 6 (4h): Frontend: URL input → loading state → results display

Total: ~21 hours

Risks:
  - yt-dlp rate limits on TikTok (mitigation: add delays, rotate user-agents)
  - Whisper accuracy on background music (mitigation: test 5 videos upfront)
```

---

## 4. `speky story` — Create Development Stories

**Use when:** You're past MVP and tracking ongoing work — bugs, enhancements, tech debt.

### Story Types

```bash
# New feature work
speky story --type feature "Add user preferences panel"

# Bug fix
speky story --type bug "Login fails on Safari 17"

# Improvement to existing functionality
speky story --type enhancement "Improve video loading speed by 40%"

# Code quality / technical cleanup
speky story --type tech_debt "Refactor auth module to use middleware pattern"

# Research / exploration
speky story --type spike "Evaluate ML models for cooking step classification"
```

Each story gets saved under `.speky/stories/` with its own `story.md` and `status.json`.

**Example:**

```bash
speky story --type bug "Step extraction returns empty array for short videos"

✅ Story created: B001-step-extraction-empty-array
   Type: bug
   Status: draft
   File: .speky/stories/B001-step-extraction-empty-array/story.md
```

Stories go through statuses: `draft → ready → in_progress → review → done`

---

## 5. `speky implement` — Hand Off to IDE

**Use when:** You're ready to start coding on a spec or story.

```bash
# Implement a spec
speky implement 001

# Implement a story
speky implement B001
```

speky:
1. Loads the spec or story context
2. Pulls in product profile, tech decisions, and codebase analysis (if synced)
3. Updates your IDE context file with everything the AI needs
4. Optionally opens your IDE

Your IDE's AI then has full, accurate context — no copy-pasting, no re-explaining.

**Supported IDEs** (set in `.speky/config.yaml`):
- Windsurf → updates `.windsurfrules`
- Cursor → updates `.cursorrules`
- Claude Code → updates `CLAUDE.md`
- VS Code → updates `.vscode/`

---

## 6. `speky status` — Project Dashboard

**Use when:** You want to see what's in progress, what's pending, what's done.

```bash
speky status
```

```
======================================================================
  SPEKY Status — Recipe Video Converter
======================================================================

SPECS
  ID  | Name                              | Status
  001 | Video transcription               | in_progress
  002 | Step extraction from transcript   | ready
  003 | User recipe library               | draft

STORIES
  ID   | Type        | Title                         | Status
  B001 | bug         | Empty array on short videos   | in_progress
  E001 | enhancement | Support Instagram Reels       | draft
  T001 | tech_debt   | Refactor audio pipeline       | draft
```

---

## 7. `speky sync` — Update Codebase Context

**Use when:** You've been coding for a while and want speky's context to reflect the actual state of the codebase.

```bash
speky sync
```

speky analyzes your project files and updates `.speky/context/codebase.md` with:
- Directory structure and key files
- Patterns observed (naming conventions, architectural patterns)
- Areas most relevant to upcoming specs

Run `sync` periodically — especially before creating new specs on an existing codebase.

```bash
speky sync
✅ Codebase analyzed
   Files scanned: 142
   Key directories identified: src/api, src/components, src/lib
   Patterns noted: REST endpoints follow /api/v1/ prefix, React functional components
   Context updated: .speky/context/codebase.md
```

---

## 8. `speky review` — Check Spec vs Code Drift

**Use when:** You want to verify that what was built matches what was specced — especially useful before shipping or during code review.

```bash
speky review
```

speky compares your specs against the current codebase and surfaces:
- Features specced but not yet implemented
- Implementation decisions that diverged from the spec
- Out-of-scope items that were built anyway

---

## Full Workflow Example

### Starting a New Product

```bash
mkdir recipe-app && cd recipe-app

# 1. Initialize with your idea
speky init "An app that converts cooking videos to step-by-step recipes"

# 2. Create your first feature spec
speky spec "Video URL input and transcription"

# 3. Generate a plan
speky plan 001

# 4. Load context into your IDE and start coding
speky implement 001
# → Open Windsurf/Cursor — it already has all context

# 5. Create next spec
speky spec "Recipe step extraction and display"
speky plan 002
speky implement 002
```

### Ongoing Development (Post-MVP)

```bash
# Bug reported by user
speky story --type bug "TikTok videos fail to transcribe"
speky implement B001

# Product team requests new feature
speky story --type feature "Save recipes to personal library"
speky implement F001

# Tech debt accumulating
speky story --type tech_debt "Replace polling with WebSockets for job status"
speky implement T001

# Check overall status
speky status

# Sync after a sprint of coding
speky sync
```

---

## Configuration

Edit `.speky/config.yaml` in your project:

```yaml
# AI model — speky auto-selects based on which key is set
# Anthropic (default):  claude-sonnet-4-20250514
# OpenAI fallback:      gpt-4o
# Gemini fallback:      gemini-1.5-pro
model: claude-sonnet-4-20250514
max_tokens: 4096
temperature: 0.7

# Your preferred IDE: windsurf, cursor, claude-code, vscode
ide: windsurf

# Enable multiple IDE rule files simultaneously
enabled_ides: [windsurf, cursor]
```

### AI Provider Selection

speky picks the provider automatically based on environment variables:

| Priority | Provider | Key to set |
|---|---|---|
| 1st | Anthropic Claude (recommended) | `ANTHROPIC_API_KEY` |
| 2nd | OpenAI GPT | `OPENAI_API_KEY` |
| 3rd | Google Gemini | `GEMINI_API_KEY` |

Set the key in your shell profile or in a `.env` file at the project root.
speky uses the first key it finds — no other configuration needed.

> **Note:** Design image analysis (`speky design`) requires Anthropic Claude.
> All other commands work with any provider.

---

## Tips

1. **Always run speky from your project root** — it looks for `.speky/` in the current directory.

2. **Specs are starting points** — edit `spec.md` after generation. The AI output is a draft, not gospel.

3. **Sync after coding sprints** — keeps context accurate for new specs.

4. **Use `Out of Scope` seriously** — it prevents AI from building things you didn't ask for.

5. **One spec, one feature** — keep specs focused. Broad specs produce vague context.

6. **`.env` in project root** — the cleanest way to manage your API key per project without touching shell profiles.

---

## How speky Fits in Your Stack

```
┌─────────────────────────────────────────────┐
│                  YOU                        │
│  (product decisions, reviews, direction)    │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│               speky                         │
│  (context management, specs, plans,         │
│   stories, codebase awareness)              │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│         Your IDE + AI (Windsurf /           │
│         Cursor / Claude Code)               │
│  (actual code generation, refactoring,      │
│   debugging)                                │
└─────────────────────────────────────────────┘
```

speky makes the top layer (you) more effective by ensuring the bottom layer (your IDE AI) always has accurate, focused context.
