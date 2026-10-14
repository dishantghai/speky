# SPEKY

**Spec-driven development for AI coding agents**

SPEKY keeps your project's changes, requirements, decisions and evidence in `.speky/`, and
your coding agent (Claude Code, Codex, Cursor, OpenCode, …) does the work. Validation converges
instead of looping, nothing counts as done without evidence, and specs stay true after the code
ships. The classic v2 commands (init → spec → plan → implement), which call an AI model
themselves, are all still here.

## Installation

### macOS / Linux (one-liner)

```bash
curl -fsSL https://raw.githubusercontent.com/dishantghai/speky/main/scripts/install.sh | bash
```

### Manual download

Go to [releases](https://github.com/dishantghai/speky/releases/latest) and download the binary for your platform:

| Platform | File |
|---|---|
| macOS Apple Silicon (M1/M2/M3) | `speky-macos-arm64` |
| macOS Intel | `speky-macos-x86_64` |
| Linux x86_64 | `speky-linux-x86_64` |
| Windows | `speky-windows-x86_64.exe` |

```bash
chmod +x speky-macos-arm64
sudo mv speky-macos-arm64 /usr/local/bin/speky
```

## Quick Start

### With a coding agent (recommended, no API key needed)

```bash
cd your-project && git init            # if it isn't a repo yet
speky setup claude-code                # or: codex, agents-md
```

That installs SPEKY's skills, a 10-line block in `CLAUDE.md` / `AGENTS.md`, and (Claude Code)
a session hook that loads the workflow. Then just ask your agent for what you want built.
Behind the scenes it follows `speky next`:

```bash
speky next --json                      # the one next action, the skill to use, when it's done
speky new spec "Paste a video link"    # a change with requirements ### R1: + WHEN/THEN scenarios
speky check 001                        # rubric + findings ledger; says when validation has converged
speky start 001                        # records the base commit
speky evidence 001 R1 --status met --evidence "tests/test_import.py::test_valid_link"
speky verify 001 --run "pytest -q"     # passes only with evidence for every requirement
speky archive 001                      # merges the change into living specs (.speky/capabilities/)
```

Set `verify_command` in `.speky/speky.yaml` once you have tests. Existing v2 project?
`speky migrate` (dry run), then follow [docs/v3/MIGRATION.md](docs/v3/MIGRATION.md).
Reference: [docs/v3/CONTRACTS.md](docs/v3/CONTRACTS.md) · design notes: [docs/v3/PLAN.md](docs/v3/PLAN.md).

### Classic flow (SPEKY calls the model itself)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # or any provider — see "Models" below; or --llm claude-code/sonnet

speky init "Your product idea"           # product profile + tech stack
speky spec "Feature name"                # feature spec
speky validate-spec 001                  # converges: at most 2 rounds unless --force
speky plan 001                           # implementation plan
speky implement 001                      # hands the context to your IDE
speky complete 001                       # drift check, mark complete
speky commit 001                         # commit with a generated message
git push
```

> See [DEPLOYMENT.md](./DEPLOYMENT.md) for the full build, release, and developer setup guide.

## Models: any provider

SPEKY works with Anthropic, OpenAI, Gemini, OpenRouter, Nebius, OpenCode Go, Groq,
Together, DeepSeek, Mistral, xAI, Ollama, LM Studio, any OpenAI-compatible server,
and your Claude Pro/Max subscription (through the `claude` CLI).

```bash
speky config --providers                          # which providers are ready
speky config --model                              # pick provider → model interactively
speky config --model openrouter/moonshotai/kimi-k2
speky spec "Login" --llm claude-code/opus         # one run only
```

Fallbacks and custom providers live in `~/.speky/models.yaml`. See [MODELS.md](./MODELS.md).

## Scripts and AI agents

Every SPEKY command can run without a keyboard, and an agent such as Claude Code can
act as SPEKY's model itself (host mode, no API key needed):

```bash
speky spec "Login" -y --answer "Add to phase=phase-1"   # no prompts
speky spec "Login" --host -y                            # the calling agent answers SPEKY's prompts
speky init --from-project                               # existing repo: fill init from its README/docs/manifests
speky host guide                                        # instructions to give your agent
```

See [AUTOMATION.md](./AUTOMATION.md).

## Key Features

✅ **MVP-Focused Specs** - 1-2 stories, explicit out-of-scope, max 1-2 pages  
✅ **Research-Aware Init** - Import docs during init, extract tech stack, smart questions  
✅ **POC Code Import** - Import features from existing POC with AI-assisted analysis  
✅ **External Knowledge Import** - Import PRDs, tech specs, handoffs with interactive review  
✅ **Spec Sequencing** - Priority tracking (P0-P3), dependency management, implementation roadmap  
✅ **Phase Management** - Multi-spec coordination with deliverables, acceptance criteria, AI guides  
✅ **Epic Management** - Group related stories with shared context and documentation  
✅ **Story Context Linking** - Link stories to specs, epics, affected files  
✅ **Full Context Chain** - Implement command loads all relevant context layers  
✅ **AI Dependency Inference** - Automatically detect dependencies between specs  
✅ **Conflict Detection** - Resolve overlaps during POC import with AI recommendations  
✅ **Realistic Plans** - 3-8 tasks, 2-8 hours each, <40 hours total  
✅ **Tech-Aware** - AI understands your tech stack  
✅ **Collaborative** - AI suggests, you decide (full transparency)  
✅ **Drift Detection** - Ensures spec-code alignment  
✅ **Smart Commits** - Comprehensive messages with context  
✅ **Context-Aware Validation** - Tech decision enforcement, feature overlap detection, dependency validation  
✅ **Design System Management** - Import, analyze, validate designs with Vision AI  
✅ **Story Adoption** - Create stories in IDE, validate, adopt into SPEKY workflow  
✅ **Testing Integration** - Test generation, coverage tracking, spec-linked tests, stage-appropriate strategies  
✅ **Codebase Navigation Index** - Auto-maintained index of key directories, files, and patterns (NEW)  
✅ **Architecture Decision Tracking** - Document and enforce patterns, conventions, anti-patterns (NEW)  

## Story Adoption (IDE/Manual Creation)

Create stories directly in your IDE or manually, then adopt them into SPEKY workflow:

### Story Workflow Options

**Quick Path (Simple Stories):**
```bash
# 1. Create story folder and files in .speky/stories/F001-feature-name/
# 2. Adopt into SPEKY
speky adopt F001

# 3. Implement directly or via SPEKY
speky implement F001  # Optional

# 4. Complete
speky complete F001
```

**Full Path (Complex Stories):**
```bash
# 1. Create story folder and files
# 2. Validate (AI-powered completeness check)
speky validate-story F001

# 3. Fix any issues, then adopt
speky adopt F001

# 4. Generate task breakdown (optional)
speky plan F001

# 5. Implement
speky implement F001

# 6. Complete
speky complete F001
```

### Creating Stories Manually

**Folder Structure:**
```
.speky/stories/F001-feature-name/
├── story.md       # REQUIRED - Story definition
└── status.json    # Created by adopt or manually
```

**Folder Naming Convention:**
- `F001-name/` - Feature story
- `B001-name/` - Bug fix story
- `T001-name/` - Tech debt story
- `E001-name/` - Enhancement story
- `S001-name/` - Spike/research story

**story.md Template:**
```markdown
# Story Title

## Description
What needs to be done and why.

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Context
- **Related Spec**: 007
- **Dependencies**: F002

## Tasks
1. Task 1
2. Task 2

## Notes
Implementation hints, edge cases.
```

### Story Commands

| Command | Description |
|---------|-------------|
| `speky story "Title"` | Create story via SPEKY (AI-generated) |
| `speky adopt F001` | Adopt IDE-created story (auto-detects type) |
| `speky adopt F001 --type story` | Explicitly adopt as story |
| `speky validate-story F001` | AI validation for complex stories |
| `speky plan F001` | Generate task breakdown (optional) |
| `speky implement F001` | Hand off to IDE with context |
| `speky complete F001` | Mark story complete |

### Auto-Detection

The `adopt` command auto-detects item type from ID:
- **Story IDs**: Start with letter (F001, B001, T001, E001, S001)
- **Spec IDs**: Numeric only (001, 002, 003)

```bash
speky adopt F001    # Auto-detected as story
speky adopt 001     # Auto-detected as spec
```

## Design System Management

SPEKY provides comprehensive design system integration with AI-powered analysis, conflict detection, and implementation guidance. This enables pixel-perfect UI implementation with full traceability from design to code.

### Design System Commands

```bash
# Initialize design system for your project
speky design init --tech flutter

# Import design assets
speky design import ./designs --type hifi --spec 007
speky design import ./system.md --type system
speky design import ./icons --type icon

# Analyze designs with Vision AI (extracts colors, typography, spacing)
speky design analyze

# Validate design system against Hi-Fi images (detect conflicts)
speky design validate

# Resolve conflicts with AI recommendations
speky design resolve

# Check design system status
speky design status

# Link designs to specs/stories
speky design link screen.png --spec 007

# Sync design system with implementation code
speky design sync

# Apply sync results after IDE analysis
speky design sync --analyze
```

### Design System Features

| Feature | Description |
|---------|-------------|
| **Vision AI Analysis** | Extracts colors, typography, spacing, components from Hi-Fi images using Claude Vision API |
| **Conflict Detection** | Compares design system document vs Hi-Fi image analyses, detects discrepancies |
| **AI Recommendations** | Suggests resolutions with accessibility considerations (contrast ratios) |
| **Spec Integration** | Linked designs are loaded during `speky implement` for context |
| **Technology Templates** | Pre-built templates for Flutter, React, Vue with framework-specific code |
| **Component Library** | Documents implemented components with file paths for reuse |
| **Design Sync** | Detects gaps between design system doc and implementation code, updates doc automatically |

### Design System Workflow

```
1. Initialize design system
   speky design init --tech flutter
          ↓
2. Import design assets
   - Place design system markdown in .speky/design/system/source/
   - Place Hi-Fi images in .speky/design/hifi/source/
          ↓
3. Analyze Hi-Fi images
   speky design analyze
   → Creates .analysis.md files with extracted tokens
          ↓
4. Validate for conflicts
   speky design validate
   → Detects color, typography, spacing, layout conflicts
          ↓
5. Resolve conflicts
   speky design resolve
   → AI recommends, user decides, updates design system
          ↓
6. Link to specs/stories
   speky design link browser.png --spec 002
          ↓
7. Implement with context
   speky implement F012
   → Design system + linked designs loaded as context
```

### Design System Document Structure

A comprehensive design system document should include:

```markdown
# Project Design System

## Color System
- Primary colors with exact hex values
- Background colors (light/dark modes)
- Text colors (primary, secondary, muted)
- Status colors (success, warning, error, info)
- Space/category accent colors

## Typography
- Font family (e.g., Inter via google_fonts)
- Font weights (400, 500, 600, 700)
- Text styles with sizes and colors
- Semantic styles (heading, body, caption, button)

## Spacing & Layout
- Base spacing scale (4px increments)
- Semantic spacing (xs, sm, md, lg, xl)
- Layout constants (sidebar width, card width)
- Component-specific spacing

## Border Radius
- Base radius values
- Semantic radius (button, card, input, avatar)
- BorderRadius helpers

## Shadows
- Component shadows (card, dropdown, sidebar)
- Hover state shadows
- Shadow helpers

## Iconography
- Icon library (Lucide, Material Symbols)
- Icon sizes (xs, sm, md, lg, xl)
- Semantic sizes (treeItem, navButton, spaceIcon)

## Component Library
- Implemented components with file paths
- Code snippets for reuse
- Implementation checklist

## Animations
- Duration constants (hover, expand, transition)
- Curve definitions
- Animation patterns
```

### Folder Structure

```
.speky/design/
├── config.yaml               # Technology and settings
├── manifest.json             # All designs, links, conflicts
├── system/source/            # Design system documents
│   └── design_system.md      # Main design system doc
├── hifi/source/              # Hi-Fi designs (pixel-perfect)
│   ├── screen1.png
│   └── screen1.analysis.md   # AI-extracted tokens
├── lofi/source/              # Lo-Fi wireframes (guidance)
└── icons/source/             # Icon assets

.speky/context/design_system.md  # AI summary for context chain
```

### Conflict Types

| Type | Description | Example |
|------|-------------|---------|
| `color` | Color value mismatch | Doc: #0f0b1a vs Hi-Fi: #1a1b23 |
| `typography` | Font size/weight mismatch | Doc: 14px vs Hi-Fi: 12px |
| `spacing` | Spacing value mismatch | Doc: 16px vs Hi-Fi: 12px |
| `radius` | Border radius mismatch | Doc: 8px vs Hi-Fi: 12px |
| `shadow` | Shadow definition mismatch | Different blur/offset |
| `layout` | Layout dimension mismatch | Doc: 320px vs Hi-Fi: 280px |
| `component` | Component structure mismatch | Different hierarchy |

### Resolution Options

When resolving conflicts:

```
⚠️  CONFLICT: sidebar width
    Design System: 320px
    Hi-Fi Image: 280px

    AI Recommendation: use_design_system
    Reason: 320px is the established layout constant...

    [A] Accept AI recommendation
    [S] Use design system value
    [H] Use Hi-Fi value
    [C] Enter custom value
    [?] Ask AI for more context
```

### IDE Integration

When implementing with a design system, the IDE receives:

1. **Design System Summary** (`.speky/context/design_system.md`)
2. **Linked Design Analyses** (extracted tokens from Hi-Fi images)
3. **Resolved Conflicts** (authoritative values to use)
4. **Component Library** (implemented components for reuse)

The IDE rules template includes:

```markdown
### 🎨 CRITICAL: Design System

**BEFORE implementing any UI:**
1. Check `.speky/design/system/source/` for design system
2. Check `.speky/context/design_system.md` for AI summary
3. Use EXACT values from design system (colors, spacing, typography)
4. Reference implemented components in the design system doc

**Pixel-Perfect Implementation:**
- Use exact hex values (not approximations)
- Match dimensions precisely (320px sidebar, 16px indent)
- Follow component hierarchy from Hi-Fi analyses
```

### Example: Flutter Design System

```dart
// lib/core/theme/spayce_colors.dart
class SpayceColors {
  static const Color primary = Color(0xFF6D5AE6);
  static const Color backgroundDark = Color(0xFF0F0B1A);
  static const Color surfaceDark = Color(0xFF1A1628);
  static const Color textPrimary = Color(0xFFE5E7EB);
  // ... all colors with exact hex values
}

// lib/core/theme/spayce_typography.dart
class SpayceTypography {
  static TextStyle get navButton => GoogleFonts.inter(
    fontSize: 14,
    fontWeight: FontWeight.w500,
    color: SpayceColors.textPrimary,
  );
  // ... all text styles
}

// lib/core/theme/spayce_spacing.dart
class SpayceSpacing {
  static const double sidebarWidth = 320.0;
  static const double treeIndent = 16.0;
  static const double cardWidth = 288.0;
  // ... all spacing constants
}
```

### Keeping Design System in Sync

Use the `sync` command to detect and resolve gaps between design system document and implementation code:

```bash
# Generate sync analysis task for IDE
speky design sync

# Apply changes after IDE completes analysis
speky design sync --analyze
```

### Design Sync Workflow

```
1. Run sync command
   speky design sync
          ↓
2. SPEKY generates sync_task.md
   - Lists implementation files to analyze
   - Includes design system for reference
          ↓
3. IDE analyzes implementation
   - Scans theme files for tokens
   - Compares with design system doc
   - Writes sync_results.json
          ↓
4. Apply changes
   speky design sync --analyze
          ↓
5. Interactive review
   - Review additions (code → doc)
   - Resolve conflicts
   - Export report for manual review
          ↓
6. Update design system
   - AI incorporates changes
   - Backup created automatically
   - Context summary regenerated
```

### Sync Results Format

The IDE writes `sync_results.json` with:

```json
{
  "additions": [
    {
      "category": "colors",
      "name": "success",
      "value": "#10B981",
      "file": "lib/core/theme/colors.dart",
      "line": 27
    }
  ],
  "missing": [
    {
      "category": "typography",
      "name": "headingXL",
      "value": "32px bold",
      "doc_section": "Typography"
    }
  ],
  "conflicts": [
    {
      "category": "layout",
      "name": "sidebarWidth",
      "doc_value": "320px",
      "code_value": "256px",
      "severity": "high"
    }
  ]
}
```

### Sync Options

When applying sync results:

```
📋 Options:
   1) Update design system with ALL additions and conflicts (use code values)
   2) Review each change interactively
   3) Export changes to markdown for manual review
   4) Cancel
```

**Option 1**: Bulk update - AI incorporates all changes into design system
**Option 2**: Interactive - Review each addition/conflict individually
**Option 3**: Export - Creates `sync_report.md` for manual editing

## Initial Research During Init

When running `speky init`, you can provide existing documentation about your product:

```bash
speky init "Recipe sharing social network"

📚 Initial Research
   Do you have existing documentation?

   1. Yes, I'll place files in the research folder
   2. I'll paste notes directly
   3. No, start fresh
```

**What SPEKY extracts from your docs:**
- Product information (name, description, target users)
- Tech stack preferences (pre-populates tech stack discussion)
- Features mentioned (MVP vs future)
- Constraints and requirements
- Gaps that need clarification

**Smart Questions:**
- If docs are comprehensive → fewer questions (2-3)
- If docs have gaps → targeted questions about missing info
- Never asks about what's already in your docs

**Files created:**
```
.speky/imports/initial_research/
├── source/           # Your documents
├── analysis.md       # AI analysis (editable)
└── manifest.json     # Metadata
```

## POC Code Import

Import features from existing POC/prototype codebases with AI-assisted analysis:

```bash
# Start POC import
speky poc-import

# Or with path directly
speky poc-import --path /path/to/my-poc

# Resume incomplete session
speky poc-import --resume
```

### POC Import Workflow

```
1. Provide POC path(s)
          ↓
2. SPEKY creates task.md for IDE
          ↓
3. Tell IDE to analyze POC (write results.json)
          ↓
4. Select features (natural language: "auth and api but not admin")
          ↓
5. AI recommends: COPY_CODE or SPEC_ONLY for each feature
          ↓
6. SPEKY creates extraction_task.md
          ↓
7. Tell IDE to create specs
          ↓
8. Specs auto-adopted into SPEKY
```

### Feature Selection (Natural Language)

```
Which features to include?
  • Enter numbers: 1,2,4
  • Describe: 'auth and api but not admin'
  • 'all' to include everything
```

### AI Recommendations

SPEKY analyzes tech conflicts and recommends handling:

```
🤖 AI RECOMMENDATIONS

⚠️  Tech Conflicts:
   • backend_framework: Express → FastAPI [HIGH]

📋 Feature Handling:
   📋 User Authentication: SPEC_ONLY (tech conflict)
   📁 Database Models: COPY_CODE (compatible)
```

- **COPY_CODE**: Copy code as-is (compatible tech, production-ready)
- **SPEC_ONLY**: Create spec, reimplement fresh (conflicts or POC-quality)

### User Control at Every Step

Every step allows user intervention:
- Edit `task.md` before IDE analyzes
- Edit `results.json` to correct IDE findings
- Edit `recommendations.md` to override AI decisions
- Edit specs before adoption
- Resume interrupted sessions with `--resume`

### Files Created

```
.speky/imports/poc_import/
└── poc-20240115-1430/
    ├── state.json           # Workflow state (resumable)
    ├── task.md              # Instructions for IDE
    ├── results.json         # IDE analysis output
    ├── recommendations.md   # AI recommendations (editable)
    ├── extraction_task.md   # Extraction instructions
    └── specs/               # Generated specs
```

## Spec Sequencing & Dependencies

All specs now include **priority** and **dependencies** for proper implementation ordering:

### Priority Levels

- **P0**: Blocker - Must be done immediately
- **P1**: High - MVP features, core functionality
- **P2**: Medium - Important but not critical
- **P3**: Low - Nice-to-have, future enhancements

### How Dependencies Work

**Automatic Dependency Tracking:**
- **Initial Research**: Specs created with priority based on MVP vs Future
- **POC Import**: Feature dependencies from POC preserved in specs
- **External Import**: Dependencies from analysis included
- **Manual Specs**: Default P1, edit `status.json` to add dependencies

**Example status.json:**
```json
{
  "id": "002",
  "name": "api",
  "priority": "P1",
  "dependencies": ["001"],  // Depends on spec 001 (auth)
  "source": "poc_import"
}
```

### Viewing Spec Order

Check `status.json` in each spec directory to see:
- Priority level
- Dependencies (which specs must be done first)
- Source (where spec came from)

**Recommended Implementation Order:**
1. Implement specs with no dependencies first
2. Follow dependency chain (if 002 depends on 001, do 001 first)
3. Within same dependency level, prioritize by P0 → P1 → P2 → P3

**Example:**
```
001-auth [P1, no deps] ← START HERE
002-api [P1, needs 001]
003-notifications [P2, needs 001]
004-payments [P1, needs 002]

Order: 001 → 002 → 004 → 003
```

### Sequence Command

Use `speky sequence` to see a unified roadmap:

```bash
speky sequence              # Show roadmap in terminal
speky sequence --export     # Export to .speky/roadmap.md
```

**Features:**
- **Dependency Analysis**: Topological sort respecting dependencies
- **Circular Detection**: Warns about circular dependencies
- **Priority Grouping**: P0 → P1 → P2 → P3
- **Source Tracking**: See where each spec came from
- **Next Steps**: Suggests which spec to implement next

**Example Output:**
```
📊 Total Specs: 4
   P0 (Blocker): 0
   P1 (High): 3
   P2 (Medium): 1

📋 Recommended Implementation Order

⚡ P1 - HIGH PRIORITY (Core features):
   1. ⬜ 001-auth (initial_research)
   2. ⬜ 002-api (poc_import) [needs: 001]
   3. ⬜ 004-payments (poc_import) [needs: 002]

📋 P2 - MEDIUM PRIORITY:
   4. ⬜ 003-notifications (manual) [needs: 001]

📋 Next Steps:
   1. Run: speky plan 001
   2. Run: speky implement 001
```

### Conflict Resolution (POC Import)

When importing POC features that conflict with existing specs:

```
⚠️  SPEC CONFLICT DETECTED

📦 POC Feature: "User Authentication"
📄 Existing Spec: 001-auth (from initial_research)

🤖 AI Recommendation: MERGE
   Reason: Both approaches have merit. POC has OAuth, 
   existing has JWT. Combine for flexibility.

How would you like to resolve this conflict?
   1. Keep existing spec (skip POC feature)
   2. Replace with POC (deprecate 001)
   3. Merge both approaches (AI-assisted) [RECOMMENDED]
   4. Keep both as alternatives
   5. Show detailed comparison
```

**Resolution Options:**
- **Skip**: Keep existing, add note about POC alternative
- **Replace**: Deprecate existing, create new from POC
- **Merge**: AI combines best of both approaches
- **Keep Both**: Create both with cross-references

### AI Dependency Inference

Automatically detect dependencies between specs:

```bash
speky infer-deps              # Analyze all specs
speky infer-deps 003          # Analyze specific spec
```

**How it works:**
1. AI analyzes spec content against all existing specs
2. Identifies true dependencies (not just related specs)
3. Adds inferred dependencies to `status.json`
4. Preserves manually added dependencies

**Example Output:**
```
📋 Analyzing: 003-payments

🔗 Inferred dependencies:
   • 001: Needs authentication before payment can be secured
   • 002: Uses API endpoints defined in API spec

✅ Added dependencies: 001, 002
```

### Dependency Validation

When running `plan` or `implement`, SPEKY warns about unmet dependencies:

```
⚠️  DEPENDENCY WARNING for spec 003
   The following dependencies are not yet completed:

   • 001 (status: draft)
   • 002 (status: in_progress)

   Consider implementing these first, or proceed if you're sure.
   Run 'speky sequence' to see recommended order.

Continue anyway? [y/N]:
```

This prevents implementing specs out of order and ensures proper sequencing.

## Phase Management (Multi-Spec Coordination)

Group specs into coherent phases with clear deliverables, acceptance criteria, and AI implementation guides. **Phases are optional** - use them when coordinating multiple specs.

### When to Use Phases

| ✅ Use Phases | ❌ Skip Phases |
|---------------|----------------|
| 5+ specs | <5 specs |
| Clear milestones | Single feature |
| Team/multi-agent work | Solo development |
| Need AI implementation guides | Just building quickly |

### Phase Commands

```bash
# AI suggests phases from existing specs (RECOMMENDED)
speky phases suggest

# List all phases
speky phases list

# Show phase details
speky phases show phase-1

# Show overall progress
speky phases status

# Start a phase (validates prerequisites)
speky phases start phase-1

# Complete a phase (validates deliverables)
speky phases complete phase-1

# Generate AI implementation guide
speky phases guide phase-1

# Generate AI-optimized guide
speky phases guide phase-1 --for-ai

# Create a new phase manually
speky phases create phase-1

# Generate AI context for current phase
speky context

# Generate AI context for specific phase
speky context --phase phase-1
```

### Recommended Workflow: AI-Suggested Phases

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

### Alternative: Manual Phase Creation

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

### Auto-Suggestions During Import

When importing external documents or POC code, SPEKY automatically offers phase suggestions:

```
speky import --phase mvp
... creates 5 specs ...

📅 Phase Suggestions
   You've created 5 specs from external import.
   Would you like AI to suggest logical implementation phases?

   Phases help by:
   • Grouping related specs
   • Defining clear milestones
   • Generating AI implementation guides

Suggest phases? [Y/n]:
```

### Phase Manifest

Each phase has a `manifest.yaml` with comprehensive configuration:

```yaml
# .speky/phases/phase-1/manifest.yaml
id: phase-1
name: "MVP Browser + Spaces"
description: "Basic browser with content organization"
duration: "4 weeks"
status: not_started  # not_started | in_progress | complete

# Specs in this phase (with scope control)
specs:
  - id: "002"
    scope: "mvp"            # mvp | partial | full
    features:
      - "WebView integration"
      - "Navigation controls"
    excludes:
      - "Bookmarks (use Spaces)"
    implementation_priority: 1

# Tangible deliverables (testable)
deliverables:
  - id: "D1"
    name: "Browser loads pages"
    description: "WebView displays web content"
    test_steps:
      - "Launch app"
      - "Enter 'google.com'"
      - "Verify page displays"
    pass_criteria: "Can see Google homepage"

# Prerequisites
prerequisites:
  - description: "Flutter project initialized"
    validation: "pubspec.yaml exists"
  - description: "Drift database setup"
    validation: "lib/database/database.dart exists"

# Tech requirements (phase-specific)
tech_requirements:
  packages:
    - name: "flutter_inappwebview"
      version: "^6.0.0"
      reason: "Advanced WebView with cookie control"
  forbidden:
    - name: "webview_flutter"
      reason: "Use flutter_inappwebview instead"

# Files to create/modify
implementation_files:
  create:
    - "lib/features/browser/browser_screen.dart"
    - "lib/features/browser/browser_controller.dart"
  modify:
    - path: "lib/database/tables/spaces.dart"
      changes: "Add profile_id, favicon_url columns"

# Acceptance criteria
acceptance_criteria:
  - "All deliverables verified"
  - "No critical bugs"

# User review points
user_review_points:
  - after: "D1"
    type: "ux_review"
    questions:
      - "Is the navigation intuitive?"

# Phase dependencies
depends_on: []
unlocks: ["phase-2"]
```

### AI Implementation Guide

The `phases guide` command generates a comprehensive guide for AI agents:

```bash
$ speky phases guide phase-1 --for-ai

# Phase 1: MVP Browser + Spaces - Implementation Guide

## AI Agent Instructions

You are implementing **Phase 1**. This phase includes:
- **Spec 002** (mvp): WebView integration, Navigation controls

### Package Decisions (AUTHORITATIVE)
- **Frontend**: `Flutter`
- **Database**: `drift`

### What NOT To Do
- ❌ Bookmarks (use Spaces)
- ❌ Profiles (Phase 2)

### Required Packages
- `flutter_inappwebview` ^6.0.0 - Advanced WebView with cookie control

### Forbidden Packages (DO NOT USE)
- ❌ `webview_flutter` - Use flutter_inappwebview instead

### Files to Create
- `lib/features/browser/browser_screen.dart`
- `lib/features/browser/browser_controller.dart`

### Deliverables (test each)
- [ ] **D1**: Browser loads pages
  - WebView displays web content
  - Steps: Launch app, Enter 'google.com', Verify page displays
  - Pass: Can see Google homepage

### Implementation Order
1. **002**: Browser Module
   - WebView integration
   - Navigation controls

### Stop Conditions
Stop and ask user when:
- Unclear requirements
- Tech decision conflict
- Cross-spec integration unclear
```

### Phase Directory Structure

```
.speky/
├── phases/
│   ├── roadmap.yaml          # Master phase timeline
│   ├── phase-1/
│   │   ├── manifest.yaml     # Phase definition
│   │   ├── implementation.md # AI guidance (generated)
│   │   ├── ai_context.md     # AI context (generated)
│   │   └── status.json       # Progress tracking
│   └── phase-2/
│       └── manifest.yaml
├── specs/
│   ├── 002-browser-module/
│   │   └── spec.md
│   └── 006-spaces/
│       └── spec.md
```

## Epic Management (Story Grouping)

Group related stories with shared context and documentation. **Epics are optional** - use them when you have 3+ related stories that need coordination.

### When to Use Epics

| Use Epic | Don't Use Epic |
|----------|----------------|
| 3+ related stories | 1-2 standalone stories |
| Shared technical decisions | Unrelated changes |
| Coordinated implementation | Independent work |
| Enhancement suite for a feature | Simple bug fix |

### Epic Commands

```bash
# Create epic linked to a spec
speky epic "Spaces Enhancements" --spec 006

# Create epic with existing stories
speky epic "Auth Bug Fixes" --stories B001,B002,B003

# Show epic details
speky epic E001

# Add/remove stories
speky epic E001 --add F007
speky epic E001 --remove F007

# List all epics
speky epics
```

### Story Context Linking

Stories can link to specs, epics, and affected files:

```bash
# Story in epic (inherits epic's context)
speky story "Add Item Dialog" --epic E001

# Story linked to spec
speky story "Fix auth timeout" --type bug --spec 001

# Story linked to multiple specs
speky story "Refactor DB layer" --type tech_debt --specs 001,002,006

# Story with affected files
speky story "Fix crash" --type bug --spec 001 --files lib/auth/*.dart

# Standalone story (no linking)
speky story "Update README" --type enhancement --no-spec
```

### Context Chain (How AI Gets Full Context)

When implementing a story, SPEKY loads a complete context chain:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Project Context (always)                                  │
│    • context.json, tech_decisions.md                         │
├─────────────────────────────────────────────────────────────┤
│ 2. Phase Context (if in phase)                               │
│    • manifest.yaml, implementation.md                        │
├─────────────────────────────────────────────────────────────┤
│ 3. Related Specs (if story has related_specs)                │
│    • spec.md, plan.md                                        │
├─────────────────────────────────────────────────────────────┤
│ 4. Epic Context (if story in epic)                           │
│    • manifest.yaml, technical_spec.md, summary.md            │
├─────────────────────────────────────────────────────────────┤
│ 5. Affected Files (if specified)                             │
│    • Preview of files to modify                              │
├─────────────────────────────────────────────────────────────┤
│ 6. The Story (always)                                        │
│    • story.md                                                │
└─────────────────────────────────────────────────────────────┘
```

### Epic Directory Structure

```
.speky/epics/E001-spaces-enhancements/
├── manifest.yaml           # Required: Epic definition
├── technical_spec.md       # Optional: Shared technical decisions
└── summary.md              # Optional: Executive overview
```

### Example Workflow: Enhancement Suite

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

# 5. Implement each story (full context loaded)
speky implement F005
# ... implement ...
speky complete F005
```

**See [EPIC_FEATURE.md](EPIC_FEATURE.md) for complete guide.**

## Auto-Updating IDE Rules

When you run ANY speky command in a project, the IDE rules (`.windsurfrules`, `.cursorrules`, etc.) are automatically checked and updated if SPEKY has new capabilities.

**How it works:**
1. SPEKY compares current rules with latest version
2. If SPEKY section changed → updates automatically
3. If no changes → skips update (no git noise)
4. SPEKY writes only between its `BEGIN/END SPEKY MANAGED BLOCK` markers; everything else in the file is yours and is never changed (files written by older versions are backed up to `.speky/backups/` once, keeping your USER RULES)

**Example:**
```bash
cd recipe-app
speky status  # Automatically updates .windsurfrules with new commands
              # (validate-spec, adopt, etc.)
```

This means your projects always have the latest IDE guidance without manual updates!

## Importing External Knowledge

Import external documentation (PRDs, technical specs, implementation handoffs) and automatically decompose them into structured specs.

### Workflow

```bash
# Step 1: Create import folder (or run import to create it)
speky import --phase mvp

# Step 2: Place your documents in the created folder
# Location: .speky/imports/mvp/source/
# Supported: .md, .txt, .pdf, .docx

# Step 3: Run import again to process documents
speky import --phase mvp

# Show all imports
speky import-status

# Reconcile code with imported docs after implementation
speky reconcile mvp
```

### Folder Structure

```
.speky/
└── imports/
    └── mvp/
        └── source/           # ← Place your documents here
            ├── product_prd.md
            ├── technical_spec.md
            └── api_design.md
```

**Interactive Review Features:**
- ✅ Accept, modify, split, or remove proposed specs
- ❓ Ask AI clarifying questions about proposals
- 🔀 Merge related specs or split large ones
- 📝 Add notes and constraints

**See [IMPORT_FEATURE.md](IMPORT_FEATURE.md) for complete guide.**

## Using Existing Research

When creating a spec, SPEKY asks if you have existing research or documentation:

```bash
python3 speky.py spec "Agentic Drift Detection"

🔍 Research & Documentation
   Do you have existing research or documentation?

   1. Yes, I have files to include
   2. No, start fresh
   3. I'll paste notes directly
```

**Option 1: Include files**
```
File paths: docs/DRIFT_AGENT_PRD.md, .speky/temp/notes.md
```

**Option 2: Paste directly**
- Paste your research notes
- Press Ctrl+D (Mac/Linux) or Ctrl+Z then Enter (Windows) when done

SPEKY will:
- Load and summarize your research
- Use it as foundation for the spec
- Structure it into proper MVP format
- Identify gaps and ambiguities
- Keep scope minimal despite comprehensive research

## Commands

| Command | Purpose |
|---------|---------|
| `init "idea"` | Initialize project |
| `import --phase <name>` | Import docs from `.speky/imports/<phase>/source/` |
| `import-status` | Show all imports and their derived specs |
| `spec "name"` | Create feature spec (with optional research) |
| `plan 001` | Generate implementation plan |
| `epic "name" --spec 006` | Create epic linked to spec |
| `epic E001` | Show epic details |
| `epic E001 --add F005` | Add story to epic |
| `epics` | List all epics |
| `story "title" --epic E001` | Create story in epic |
| `story "title" --spec 001` | Create story linked to spec |
| `implement 001` or `implement F001` | Hand off to IDE (with full context chain) |
| `complete 001` or `complete F001` | Mark spec/story complete (drift detection for specs) |
| `commit 001` | Commit with comprehensive message |
| `reconcile <phase>` | Reconcile code with imported docs and specs |
| `status` | Show progress (includes epics) |
| `review 001` | Check drift |
| `sync` | Update context |
| `cleanup` | Remove clutter files from root |
| `validate-spec 001` | Validate spec quality and find gaps |
| `adopt 001` | Adopt IDE-created spec into SPEKY tracking |
| `backlog` | Review and manage deferred items |

## Deferring Items for Later

During validation, you can defer gaps/suggestions for later instead of fixing immediately:

```
Gap 1/5: Missing error handling details

1. Add to fix list (with comments) - Fix in this iteration
2. Not relevant / Skip
3. Get AI suggestions & fix now
4. Defer for later

Choice: 4

How important is this for the product?
1. High - Should be next iteration (creates story)
2. Medium - Future enhancement (adds to backlog)
3. Low - Nice to have someday (adds to backlog)
```

### Priority-Based Routing

| Priority | Action | Where It Goes |
|----------|--------|---------------|
| **High** | Creates story immediately | `.speky/stories/` |
| **Medium** | Adds to backlog | `.speky/backlog.md` |
| **Low** | Adds to backlog | `.speky/backlog.md` |

### Anti-Rot Mechanism

When you run `speky spec` to create a new spec, SPEKY checks your backlog:

```
📦 Backlog Check
   You have 5 deferred item(s):
      🔴 High priority: 2
      🟡 Medium priority: 2
      🟢 Low priority: 1

   1. Review backlog now
   2. Skip and create spec
   3. Show backlog summary
```

This prevents good ideas from rotting in a document!

### Managing Backlog

```bash
$ speky backlog

📦 Backlog Review
   Found 3 item(s):
   🔴 High priority: 1
   🟡 Medium priority: 2

   Item 1/3
   🔴 [HIGH] Add comprehensive error handling
   Source: spec-004-agentic-drift-detection
   Notes: Should handle provider-specific errors
   
   1. Promote to story now
   2. Keep in backlog
   3. Delete (no longer relevant)
```

### Status Integration

`speky status` shows backlog count:

```
📦 Backlog: 3 deferred item(s)
   🔴 High priority: 1
   🟡 Medium priority: 2
   Run 'speky backlog' to review
```

## IDE-Created Specs Workflow

When the IDE has context and creates a spec directly, use this flow:

### Flow 1: Validate First (Recommended)

```bash
# IDE creates spec at .speky/specs/004-feature-name/spec.md

# Validate quality before adopting
$ speky validate-spec .speky/specs/004-feature-name/spec.md

📋 Validate Specification
──────────────────────────────────────────────────
✅ Overview section
✅ MVP Scope section
✅ Requirements section
⚠️  Gaps Found:
   - Missing acceptance criteria for user story #2
💡 Suggestions:
   - Add specific testable criteria

🟡 Score: 7/10

# Fix issues, then adopt
$ speky adopt 004
✅ Spec adopted: 004-feature-name

# Continue normal workflow
$ speky plan 004
$ speky implement 004
```

### Flow 2: Quick Adopt (Trust IDE)

```bash
# IDE creates spec

# Adopt directly (basic validation only)
$ speky adopt 004
✅ Basic format check passed
✅ Spec adopted: 004-feature-name

# Optional: validate later
$ speky validate-spec 004
```

### What `validate-spec` Checks

- **Format**: Required sections present (Overview, MVP Scope, Requirements, Out of Scope)
- **MVP Focus**: Is scope achievable in 1-2 weeks?
- **Clarity**: Are requirements specific and unambiguous?
- **Testability**: Can acceptance criteria be verified?
- **Technical Feasibility**: Is the approach realistic?
- **Tech Decision Compliance**: Uses packages from `tech_decisions.md` (if exists)
- **Feature Overlap Detection**: Finds similar features in other specs
- **Dependency Validation**: Verifies referenced specs exist

### Context-Aware Validation (NEW)

Validation now automatically loads and uses project context:

```bash
$ speky validate-spec 002

🚨 TECH DECISION VIOLATIONS
   Spec uses packages that contradict project decisions
──────────────────────────────────────────────────
   ❌ Uses 'sqflite' but project decided on 'drift'
   ❌ Uses 'webview_flutter' but project decided on 'flutter_inappwebview'

   📋 Reference: .speky/context/tech_decisions.md

⚠️ Feature Overlaps Detected
   Similar features exist in other specs
──────────────────────────────────────────────────
   📋 'Save page to bookmarks...'
      Similar to: 006-spaces
      Similarity: 85%
```

**Context files automatically loaded:**
- `.speky/context/tech_decisions.md` - Authoritative tech choices
- `.speky/context/context.json` - Project metadata and tech stack
- `.speky/imports/poc_import/*/recommendations.md` - POC import decisions
- All existing specs - For overlap and conflict detection

### Creating `tech_decisions.md`

Create this file to enforce consistent technology choices:

```markdown
# Tech Decisions

## Database
**Decision**: Drift (not SQLite/sqflite)
**Rationale**: Type-safe, reactive, better DX

## WebView
**Decision**: flutter_inappwebview (not webview_flutter)
**Rationale**: More features, better JavaScript interop

## State Management
**Decision**: Riverpod (not Provider)
**Rationale**: Compile-time safety, better testing
```

Validation will flag any spec that uses deprecated packages.

### Interactive Validation Flow

By default, `validate-spec` walks you through each issue one by one with rich options:

```bash
$ speky validate-spec 004

📋 Validate Specification
ℹ️  Validating: 004-agentic-drift-detection

──────────────────────────────────────────────────
▶️  Gaps Found
   Let's review each issue
──────────────────────────────────────────────────
   Found 2 gap(s) to review

   ─────────────────────────────────────
   Gap 1/2
   ⚠️  Missing error handling details

   1. Add to fix list (with comments)
   2. Not relevant / Skip
   3. Get AI suggestions & fix now
   
   Choice: 1
   
   💬 Add your comments/context (press Enter twice when done):
   > Should handle provider-specific errors
   > Map to domain exceptions
   >
   
   ℹ️  Added to fix list ✓
```

### Option 1: Add to Fix List (with Comments)

Adds item to your action list with your own notes:

```
💬 Add your comments/context:
> Need to specify retry logic
> Consider exponential backoff
>

✅ Added to fix list
```

### Option 2: Skip

Ignores the gap (marks as not applicable to your spec).

### Option 3: Get AI Suggestions & Fix Now

Gets AI recommendations and lets you implement immediately:

```
💡 AI Suggestion:
Add an "Error Handling" subsection under Requirements with:
- Retryable errors: [list]
- Non-retryable errors: [list]
- Provider error mapping: [example]

❓ Implement this fix now? [Y/n]: y

📝 Spec file: .speky/specs/004-xxx/spec.md
Make your changes based on the AI suggestion above
Save the file, then press Enter to continue...

[You edit the spec, save, press Enter]

✅ Fixed: Missing error handling details
```

### Quick Mode (for Scripting)

```bash
$ speky validate-spec 004 --quick
# Shows all gaps/suggestions at once without prompts
```

### Final Output

All items (with your comments and AI suggestions) are compiled:

```
📋 Action Items (5):
   • Fix: Missing error handling details
     💭 User note: Should handle provider-specific errors
   • Consider: Add retry logic documentation
     💡 AI suggestion: Use exponential backoff pattern
   • Fixed: Acceptance criteria unclear
     ✅ Fixed based on AI suggestion
```

### What `adopt` Does

- Registers spec in SPEKY tracking (`.speky/context/context.json`)
- Creates `status.json` if missing
- Performs basic format validation

## All Commands Reference

### Core Workflow
| Command | Description |
|---------|-------------|
| `speky init "idea"` | Initialize project with tech stack discussion |
| `speky spec "name"` | Create feature specification (research-aware) |
| `speky plan <id>` | Generate implementation plan (validates dependencies) |
| `speky implement <id>` | Hand off to IDE (validates dependencies) |
| `speky complete <id>` | Mark complete with drift detection |
| `speky commit <id>` | Commit with comprehensive message |
| `speky status` | Show project status |

### Spec Sequencing & Dependencies
| Command | Description |
|---------|-------------|
| `speky sequence` | Show implementation roadmap with dependencies |
| `speky sequence --export` | Export roadmap to `.speky/roadmap.md` |
| `speky infer-deps` | AI-infer dependencies for all specs |
| `speky infer-deps <id>` | AI-infer dependencies for specific spec |

### External Knowledge Import
| Command | Description |
|---------|-------------|
| `speky import --phase <name>` | Import docs with interactive review |
| `speky import --phase <name> --no-review` | Import without review |
| `speky import-status` | Show all imports and derived specs |
| `speky reconcile <phase>` | Reconcile code with imported docs |
| `speky reconcile <phase> --spec <id>` | Reconcile specific spec |
| `speky reconcile <phase> --dry-run` | Preview changes |

### POC Code Import
| Command | Description |
|---------|-------------|
| `speky poc-import` | Import features from POC (interactive) |
| `speky poc-import --path <path>` | Provide POC path directly |
| `speky poc-import --resume` | Resume incomplete session |
| `speky poc-import --spec <id>` | Link POC to existing spec |

### Spec Quality & Validation
| Command | Description |
|---------|-------------|
| `speky validate-spec <ref>` | Validate spec quality (interactive) |
| `speky validate-spec <ref> --quick` | Quick validation (non-interactive) |
| `speky adopt <id>` | Adopt IDE-created spec into tracking |
| `speky backlog` | Review deferred validation items |

### Tech Decisions
| Command | Description |
|---------|-------------|
| `speky decisions` | View current tech decisions |
| `speky decisions --add` | Add a new tech decision interactively |
| `speky decisions --edit` | Open tech_decisions.md in editor |
| `speky decisions --generate` | Regenerate from context.json |

### Configuration & Multi-IDE Support

SPEKY supports multiple IDEs simultaneously. Configure which IDEs receive auto-generated rules:

| Command | Description |
|---------|-------------|
| `speky config` | Show current SPEKY configuration |
| `speky config --list-ides` | List all supported IDEs |
| `speky config --ides` | Show currently enabled IDEs |
| `speky config --ides add <ide>` | Add an IDE (e.g., `antigravity`) |
| `speky config --ides remove <ide>` | Remove an IDE |
| `speky config --ides set <ide1,ide2>` | Set specific IDEs (comma-separated) |

**Supported IDEs:**
- `windsurf` → `.windsurfrules`
- `cursor` → `.cursorrules`
- `claude-code` → `CLAUDE.md`
- `vscode` → `.github/copilot-instructions.md` (read by GitHub Copilot in VS Code)
- `antigravity` → `.agent/rules/` (multi-file, max 8000 chars each)
  - `01-speky-core.md` - Core workflow rules
  - `02-speky-structure.md` - Project structure
  - `03-speky-context.md` - Tech decisions, design system
  - `99-speky-task.md` - Active task context (only during implement)

**Example: Enable both Windsurf and Antigravity:**
```bash
speky config --ides set windsurf,antigravity
```

### Phase Management (Multi-Spec Coordination)
| Command | Description |
|---------|-------------|
| `speky phases suggest` | AI suggests phases from specs (RECOMMENDED) |
| `speky phases list` | List all phases |
| `speky phases show <id>` | Show phase details |
| `speky phases status` | Show overall phase progress |
| `speky phases start <id>` | Start a phase (validates prerequisites) |
| `speky phases complete <id>` | Complete a phase (validates deliverables) |
| `speky phases guide <id>` | Generate AI implementation guide |
| `speky phases guide <id> --for-ai` | Generate AI-optimized guide |
| `speky phases create [id]` | Create a new phase manually |
| `speky context` | Generate AI context for current phase |
| `speky context --phase <id>` | Generate AI context for specific phase |

### Testing Integration

SPEKY provides comprehensive testing integration with modular test runners, TDD workflow, and auto-generated testing guides.

**Key Features:**
- ✅ **Modular Test Runners** - Auto-detects Flutter, Python, JavaScript test suites
- ✅ **Real-Time Output** - Streams test results as they run
- ✅ **Coverage Parsing** - Automatic coverage extraction from lcov.info
- ✅ **TESTING_GUIDE.md Generation** - Auto-generates comprehensive project testing guide
- ✅ **Mid-Project Refresh** - Updates guide with actual test counts and coverage
- ✅ **TDD Workflow** - Complete RED-GREEN-REFACTOR cycle with state tracking
- ✅ **Spec-Linked Tests** - Traceability from tests to specs

#### Core Testing Commands
| Command | Description |
|---------|-------------|
| `speky test init` | Initialize testing infrastructure + generate TESTING_GUIDE.md |
| `speky test gen <spec-id>` | Generate test task for spec |
| `speky test run` | Run all tests (auto-detects tech stacks) |
| `speky test run --coverage` | Run tests with coverage reporting |
| `speky test run --spec <id>` | Run tests for specific spec |
| `speky test status` | Show test health dashboard |
| `speky test coverage` | Show coverage report |
| `speky test gaps` | Identify test coverage gaps |
| `speky test recommend` | Get test recommendations |
| `speky test link <file> --spec <id>` | Link test file to spec |
| `speky test refresh-context` | Refresh IDE testing context |
| `speky test refresh-guide` | Update TESTING_GUIDE.md with actual stats |

#### TDD Workflow Commands
| Command | Description |
|---------|-------------|
| `speky implement <id> --tdd` | Start TDD workflow (generate tests first) |
| `speky test tdd-red <spec-id>` | RED phase: verify tests fail (before implementation) |
| `speky test tdd-green <spec-id>` | GREEN phase: verify tests pass (after implementation) |
| `speky test tdd-status` | Show TDD status dashboard for all specs |
| `speky test tdd-status <spec-id>` | Show TDD status for specific spec |
| `speky complete <spec-id>` | Complete with TDD + regression test verification |

#### Test Failure Triage (NEW)
| Command | Description |
|---------|-------------|
| `speky test triage <spec-id>` | Analyze failing tests and categorize as regressions vs outdated tests |

**When tests fail, triage helps you understand WHY:**
- 🔴 **Regression** - Fix your implementation (you broke existing behavior)
- 🟡 **Outdated** - Update the test (spec changed, test expectations stale)
- 📝 **TDD Expected** - Continue implementing (TDD test should fail until done)
- ⚪ **Flaky** - Investigate timing/environment issues
- ❓ **Uncertain** - Manual review needed

**Automatic integration:** When `speky complete` fails due to test failures, it shows a triage hint suggesting which failures are likely regressions vs outdated tests.

#### Testing Guide Generation

**At Init Time:**
```bash
speky test init
# Creates:
# - .speky/testing/ infrastructure
# - TESTING_GUIDE.md with commands, TDD workflow, best practices
```

**Mid-Project Refresh:**
```bash
speky test refresh-guide
# Updates TESTING_GUIDE.md with:
# - Actual test counts (scans test files)
# - Real coverage data (parses lcov.info)
# - Test directory structure
# - Per-platform breakdown
```

**Generated Guide Includes:**
- Quick start commands
- Current test status with counts
- Coverage summary table
- Tech-specific testing sections (Flutter/Python/Jest)
- SPEKY test commands
- Complete TDD workflow
- Best practices
- Troubleshooting

#### TDD Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    TDD Workflow                             │
├─────────────────────────────────────────────────────────────┤
│  1. speky implement <spec-id> --tdd  → Generate test task   │
│  2. Create tests based on task       → IDE implements tests │
│  3. speky test tdd-red <spec-id>     → Verify tests FAIL    │
│  4. Implement the feature            → IDE implements code  │
│  5. speky test tdd-green <spec-id>   → Verify tests PASS    │
│  6. speky complete <spec-id>         → Run regression tests │
└─────────────────────────────────────────────────────────────┘
```

**TDD States:**
- `tests_generated` - Test task created
- `red_confirmed` - Tests failing (ready for implementation)
- `implementing` - Feature in progress
- `green_passed` - Tests passing (ready for completion)
- `regression_passed` - All tests passing including regression

#### Modular Test Runners

SPEKY automatically detects and runs tests for:
- **Flutter/Dart** - Detected via `pubspec.yaml`
- **Python/pytest** - Detected via `requirements.txt`, `pytest.ini`
- **JavaScript/Jest** - Detected via `package.json`

**Benefits:**
- 🚀 Auto-detection of tech stacks
- 📊 Real-time output streaming
- 🎯 Accurate test counts
- 📈 Automatic coverage parsing
- 🔧 Extensible architecture

### Context Management

SPEKY automatically maintains an always-up-to-date context for AI agents:

**Codebase Navigation Index:**
- `speky sync` analyzes your codebase and extracts:
  - **Key Directories** - Important folders and what they contain
  - **Key Files** - Critical files and their purpose
  - **Patterns Observed** - Code organization patterns
- This index is included in IDE context for easy navigation
- Updates automatically as your codebase grows

**Architecture Decisions:**
- `.speky/context/tech_decisions.md` contains:
  - **Tech Stack** - Authoritative package/framework choices
  - **Important Architecture Decisions** - Patterns, conventions, design decisions
  - **Anti-Patterns to Avoid** - What NOT to do
- The "Important Architecture Decisions" section is ALWAYS included in IDE context
- All implementations automatically conform to documented patterns
- Update this section when making architectural changes

**How It Works:**
```bash
# Update codebase analysis and IDE context
speky sync

# IDE context now includes:
# - Key Directories/Files/Patterns (from codebase.md)
# - Important Architecture Decisions (from tech_decisions.md)
# - Tech Stack, Design System, etc.
```

### Maintenance
| Command | Description |
|---------|-------------|
| `speky sync` | Update codebase context and IDE rules |
| `speky review [id]` | Check for spec-code drift |
| `speky cleanup` | Remove clutter files |
| `speky cleanup --dry-run` | Preview cleanup |

### Stories
| Command | Description |
|---------|-------------|
| `speky story "title"` | Create feature story |
| `speky story --type bug "title"` | Create bug story |
| `speky story --type enhancement "title"` | Create enhancement |
| `speky story --type tech_debt "title"` | Create tech debt story |

## Documentation

**📖 [DOCUMENTATION.md](DOCUMENTATION.md)** - Complete guide with all features, workflows, and troubleshooting

**🔗 [SEQUENCING.md](SEQUENCING.md)** - Detailed spec sequencing and dependency management guide

**📥 [IMPORT_FEATURE.md](IMPORT_FEATURE.md)** - External knowledge import guide

**🧪 [TESTING_GUIDE.md](TESTING_GUIDE.md)** - Comprehensive testing guide with workflows and best practices

**📊 [TESTING_ROADMAP.md](TESTING_ROADMAP.md)** - Stage-appropriate testing strategies as projects grow

**📋 [TESTING_PRD.md](TESTING_PRD.md)** - Detailed testing integration design and architecture

**🚀 [QUICKSTART.md](QUICKSTART.md)** - Step-by-step getting started

## Project Structure

```
your-project/
├── .speky/                          # SPEKY framework directory
│   ├── config.yaml                  # Configuration
│   ├── context/                     # Project context
│   │   ├── context.json             # Metadata & tracking
│   │   ├── product.md               # Product profile
│   │   ├── tech_decisions.md        # Tech stack + architecture decisions
│   │   ├── codebase.md              # Codebase navigation index
│   │   └── IDE_CONTEXT.md           # IDE guide
│   ├── specs/                       # Feature specifications
│   │   ├── 001-auth/
│   │   │   ├── spec.md              # Specification
│   │   │   ├── plan.md              # Implementation plan
│   │   │   └── status.json          # Priority, dependencies, status
│   │   └── 002-api/
│   │       └── status.json          # dependencies: ["001"]
│   ├── phases/                      # Phase coordination (NEW)
│   │   ├── roadmap.yaml             # Master phase timeline
│   │   ├── phase-1/
│   │   │   ├── manifest.yaml        # Phase definition
│   │   │   ├── implementation.md    # AI guidance
│   │   │   ├── ai_context.md        # AI context
│   │   │   └── status.json          # Progress tracking
│   │   └── phase-2/
│   │       └── manifest.yaml
│   ├── stories/                     # Bugs, enhancements, tech debt
│   │   ├── bug-001/
│   │   └── enhancement-001/
│   ├── imports/                     # External knowledge imports
│   │   ├── initial_research/        # From: speky init
│   │   ├── phase-mvp/               # From: speky import --phase mvp
│   │   └── poc_import/              # From: speky poc-import
│   ├── backlog/                     # Deferred validation items
│   │   └── backlog.json
│   ├── testing/                     # Testing integration (NEW)
│   │   ├── config.yaml              # Test configuration
│   │   ├── coverage/                # Coverage tracking
│   │   ├── tasks/                   # Test generation tasks
│   │   └── specs/                   # Test-spec linking
│   ├── roadmap.md                   # From: speky sequence --export
│   └── temp/                        # Temporary files
│
├── .windsurfrules                   # IDE rules (auto-updated)
├── .cursorrules                     # IDE rules (auto-updated)
├── CLAUDE.md                        # IDE rules (auto-updated)
├── .gitignore
├── .env                             # ANTHROPIC_API_KEY
└── ... (your code)
```

**Key Points:**
- All SPEKY files in `.speky/` directory
- Specs include priority (P0-P3) and dependencies
- Imports preserve source documents and traceability
- IDE rules auto-update with new SPEKY features
- Roadmap shows implementation order
- `codebase.md` maintains navigation index (Key Directories/Files/Patterns)
- `tech_decisions.md` includes architecture decisions always in IDE context

## Philosophy

- **Orchestrate, don't replace** — Use your IDE for coding, SPEKY for context
- **Tech/IDE/Scale agnostic** — No assumptions about your stack
- **MVP-first** — Realistic specs and plans that can actually be implemented
- **Human in the loop** — You decide, AI assists
- **Clean separation** — SPEKY for workflow, git for remote operations

## Requirements

- Python 3.8+
- `anthropic` package
- `ANTHROPIC_API_KEY` environment variable

---

**See [DOCUMENTATION.md](DOCUMENTATION.md) for complete guide** 📖
