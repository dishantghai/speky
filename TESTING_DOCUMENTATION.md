# SPEKY Testing Integration Documentation

> **Version:** 0.1.0 (Development)  
> **Status:** Phase 1 - Core Infrastructure  
> **Last Updated:** 2026-01-12

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Architecture](#architecture)
4. [Commands Reference](#commands-reference)
5. [Test Recommendation Engine](#test-recommendation-engine)
6. [Setup Guides](#setup-guides)
7. [IDE Integration](#ide-integration)
8. [Progressive Testing Strategy](#progressive-testing-strategy)
9. [Troubleshooting](#troubleshooting)

---

## Overview

SPEKY Testing Integration provides **intelligent, context-aware testing capabilities** that evolve with your project. Unlike static test frameworks, this system:

- **Recommends appropriate tests** based on what you just implemented
- **Avoids overkill testing** by understanding code impact
- **Dynamically fetches setup guides** for tools like Playwright MCP, Patrol, etc.
- **Self-updates IDE context** as testing capabilities evolve
- **Scales with your project** from simple unit tests to complex E2E suites

### Design Principles

| Principle | Description |
|-----------|-------------|
| **Progressive** | Start simple, add complexity as needed |
| **Context-Aware** | Tests recommended based on actual changes |
| **Dynamic** | Setup guides fetched and cached, not hardcoded |
| **Decoupled** | Testing module independent of core SPEKY |
| **IDE-First** | AI agents receive testing context automatically |

---

## Quick Start

### 1. Initialize Test Harness

```bash
# In your project directory
speky test init
```

This creates:
```
.speky/testing/
├── config.yaml           # Testing configuration
├── coverage/             # Coverage tracking
├── specs/                # Test manifests per spec
├── tasks/                # Generated test tasks
│   ├── active/           # Pending test tasks
│   └── completed/        # Completed test tasks
├── seeds/                # Test data factories
├── mocks/                # Mock configurations
└── cache/                # Cached setup guides (2-month TTL)
```

### 2. Generate Tests for a Spec

```bash
speky test gen 003
```

Creates a test task file that your IDE/AI agent can implement.

### 3. Run Tests

```bash
# All tests
speky test run

# Tests for specific spec
speky test run --spec 003

# Only affected tests (based on git diff)
speky test run --affected
```

### 4. Complete with Tests

```bash
# Run tests before marking complete
speky complete 003 --test
```

---

## Architecture

### Module Independence

```
┌─────────────────────────────────────────────────────────────┐
│                         speky.py                            │
│                    (Core Orchestration)                     │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Lazy Import (try/except)                │   │
│  └─────────────────────┬───────────────────────────────┘   │
│                        │                                    │
│                        ▼                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │            speky_testing.py                          │   │
│  │         (Standalone Testing Module)                  │   │
│  │                                                      │   │
│  │  • Can run independently                             │   │
│  │  • Self-updates IDE context                          │   │
│  │  • Manages own state in .speky/testing/              │   │
│  │  • Fetches & caches setup guides                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### IDE Context Flow

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  speky_testing   │────▶│  .speky/testing/ │────▶│  IDE Rules File  │
│  (generates)     │     │  ide_context.md  │     │  (.windsurfrules)│
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │  AI Coding Agent │
                         │  (reads context) │
                         └──────────────────┘
```

---

## Commands Reference

### Core Commands

| Command | Description | Example |
|---------|-------------|---------|
| `test init` | Initialize test harness | `speky test init` |
| `test gen <spec>` | Generate test task | `speky test gen 003` |
| `test run` | Run tests | `speky test run --spec 003` |
| `test coverage` | Show coverage report | `speky test coverage` |
| `test status` | Test health dashboard | `speky test status` |
| `test e2e` | Run E2E tests | `speky test e2e --platform web` |
| `test link` | Link test to spec | `speky test link test.dart --spec 003` |
| `test gaps` | Show untested criteria | `speky test gaps` |

### Advanced Commands

| Command | Description | Example |
|---------|-------------|---------|
| `test recommend` | Get test recommendations | `speky test recommend` |
| `test setup <tool>` | Get setup guide | `speky test setup playwright-mcp` |
| `test refresh-context` | Update IDE context | `speky test refresh-context` |

---

## Test Recommendation Engine

### How It Works

When you complete an implementation, SPEKY analyzes:

1. **Changed Files** - What files were modified (from git diff)
2. **File Types** - UI components vs business logic vs data layer
3. **Spec Context** - What acceptance criteria were addressed
4. **Existing Tests** - What's already covered
5. **Risk Assessment** - Critical paths vs low-risk utilities

### Recommendation Categories

| Category | When to Run | Trigger |
|----------|-------------|---------|
| **Unit Tests** | Always for changed logic | Any `.dart`, `.py`, `.ts` change |
| **Widget Tests** | UI component changes | Flutter widget files |
| **Integration Tests** | Cross-module changes | Multiple file changes |
| **E2E Tests** | User flow changes | Critical path modifications |
| **Skip Tests** | Documentation only | Only `.md` files changed |

### Recommendation Output

```
┌─────────────────────────────────────────────────────────────┐
│ 🧪 Test Recommendations for Spec 003                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Changed Files: 5                                            │
│ Risk Level: MEDIUM                                          │
│                                                             │
│ Recommended Tests:                                          │
│ ✅ Unit Tests (estimated: 2 min)                            │
│    • lib/features/spaces/space_provider.dart                │
│    • lib/features/spaces/space_repository.dart              │
│                                                             │
│ ⚠️  Widget Tests (estimated: 3 min)                         │
│    • lib/features/spaces/widgets/space_card.dart            │
│                                                             │
│ ⏭️  E2E Tests (skip - no critical path changes)             │
│                                                             │
│ Run: speky test run --spec 003 --type unit,widget           │
└─────────────────────────────────────────────────────────────┘
```

### Avoiding Overkill

The engine explicitly avoids:
- Running E2E for minor changes
- Full test suite for documentation updates
- Widget tests for pure logic changes
- Integration tests when unit tests suffice

---

## Setup Guides

### Dynamic Guide System

Setup guides are **not hardcoded**. They are:

1. **Fetched on demand** from official documentation
2. **Cached locally** for 2 months
3. **Refreshed automatically** when cache expires
4. **Project-aware** (adjusts for tech stack)

### Requesting a Setup Guide

```bash
# Get setup guide for Playwright MCP in Windsurf
speky test setup playwright-mcp

# Get setup guide for Patrol (Flutter E2E)
speky test setup patrol

# Get setup guide for pytest coverage
speky test setup pytest-cov
```

### Guide Output Example

```
┌─────────────────────────────────────────────────────────────┐
│ 📘 Setup Guide: Playwright MCP for Windsurf                 │
│ Source: Official Playwright MCP Docs                        │
│ Cached: 2026-01-12 (expires: 2026-03-12)                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Prerequisites:                                              │
│ • Node.js 18+ installed                                     │
│ • Windsurf IDE with MCP support                             │
│                                                             │
│ Steps:                                                      │
│                                                             │
│ 1. Install Playwright MCP Server                            │
│    npm install -g @anthropic/mcp-server-playwright          │
│                                                             │
│ 2. Configure Windsurf MCP                                   │
│    Add to ~/.windsurf/mcp.json:                             │
│    {                                                        │
│      "playwright": {                                        │
│        "command": "npx",                                    │
│        "args": ["@anthropic/mcp-server-playwright"]         │
│      }                                                      │
│    }                                                        │
│                                                             │
│ 3. Restart Windsurf                                         │
│                                                             │
│ 4. Verify                                                   │
│    In Windsurf, check MCP panel for "playwright"            │
│                                                             │
│ Documentation: https://github.com/anthropics/mcp-servers    │
└─────────────────────────────────────────────────────────────┘
```

### Available Setup Guides

| Tool | Platform | Command |
|------|----------|---------|
| Playwright MCP | Web E2E | `speky test setup playwright-mcp` |
| Patrol | Flutter E2E | `speky test setup patrol` |
| pytest-cov | Python | `speky test setup pytest-cov` |
| flutter_test | Flutter | `speky test setup flutter-test` |
| Vitest | Web | `speky test setup vitest` |
| Maestro | Mobile E2E | `speky test setup maestro` |

---

## IDE Integration

### Self-Updating IDE Context

The testing module maintains its own IDE context file:

```
.speky/testing/ide_context.md
```

This file is:
- **Auto-generated** when testing evolves
- **Merged into IDE rules** on each SPEKY command
- **Separate from core SPEKY** (no speky.py changes needed)

### IDE Context Content

The generated context includes:

```markdown
# 🧪 SPEKY Testing Context

## Available Commands
- `speky test init` - Initialize test harness
- `speky test gen <spec>` - Generate test task
- `speky test run` - Execute tests
- `speky test recommend` - Get smart test recommendations

## After Implementation

When implementation is complete, ALWAYS:
1. Check what files changed: `git diff --name-only`
2. Get test recommendations: `speky test recommend`
3. Run recommended tests: `speky test run --spec <id> --type <recommended>`
4. If tests pass: `speky complete <id>`

## Test Recommendation Guidelines

| Change Type | Recommended Tests |
|-------------|-------------------|
| Logic files (providers, services) | Unit tests |
| UI components (widgets, views) | Unit + Widget tests |
| API endpoints | Unit + Integration tests |
| User flows | Unit + Widget + E2E tests |
| Config/docs only | Skip tests |

## Do NOT

❌ Run full E2E suite for minor changes
❌ Skip unit tests for logic changes
❌ Ignore test recommendations
❌ Mark complete without running recommended tests
```

### Merging with IDE Rules

When any SPEKY command runs, it checks:

1. Does `.speky/testing/ide_context.md` exist?
2. Has it changed since last merge?
3. If yes, merge into `.windsurfrules` / `.cursorrules`

This happens **automatically** - no manual intervention.

---

## Progressive Testing Strategy

### Phase 1: Foundation (Current)

- ✅ Test harness initialization
- ✅ Test task generation for IDE
- ✅ Basic test execution
- ✅ Coverage tracking
- ✅ `--test` flag for `speky complete`

### Phase 2: Intelligence

- 🔲 Smart test recommendations based on git diff
- 🔲 Risk-based test prioritization
- 🔲 Test impact analysis
- 🔲 Flaky test detection

### Phase 3: Automation

- 🔲 Auto-run recommended tests on complete
- 🔲 CI/CD workflow generation
- 🔲 Visual regression integration
- 🔲 Performance testing hooks

### Phase 4: E2E Mastery

- 🔲 Web E2E with Playwright MCP
- 🔲 Mobile E2E with Patrol/Maestro
- 🔲 Cross-platform test orchestration
- 🔲 Test data management

### Phase 5: Evolution

- 🔲 AI-powered test generation
- 🔲 Mutation testing integration
- 🔲 Test maintenance suggestions
- 🔲 Coverage optimization

---

## Troubleshooting

### Testing Module Not Found

```
❌ Testing module not available
```

**Solution:** Ensure `speky_testing.py` is in the same directory as `speky.py`.

### Tests Not Running

```
❌ No tests found for spec 003
```

**Solution:**
1. Generate tests: `speky test gen 003`
2. Have IDE implement the test task
3. Link tests: `speky test link path/to/test.dart --spec 003`

### Setup Guide Not Found

```
⚠️ Could not fetch setup guide for <tool>
```

**Solution:**
1. Check internet connection
2. Try: `speky test setup <tool> --refresh`
3. Check if tool name is correct

### Cache Issues

```bash
# Clear all cached guides
rm -rf .speky/testing/cache/

# Or clear specific guide
rm .speky/testing/cache/playwright-mcp.json
```

---

## Configuration Reference

### `.speky/testing/config.yaml`

```yaml
# Testing Configuration
enabled: true
version: 0.1.0

# Coverage thresholds
coverage_threshold: 80
coverage_enforcement: soft  # soft | hard

# Test recommendations
recommendations:
  enabled: true
  risk_based: true
  skip_docs_only: true

# E2E settings
e2e:
  web:
    framework: playwright
    mcp_enabled: true
    headless: true
  mobile:
    framework: patrol
    enabled: false  # Phase 5

# Cache settings
cache:
  setup_guides_ttl_days: 60  # 2 months
  recommendations_ttl_hours: 24

# IDE context
ide_context:
  auto_update: true
  merge_on_command: true
```

---

## Appendix: File Structure

```
.speky/
├── testing/
│   ├── config.yaml           # Main configuration
│   ├── ide_context.md        # Auto-generated IDE context
│   ├── coverage/
│   │   ├── coverage.yaml     # Coverage tracking
│   │   └── history/          # Historical coverage data
│   ├── specs/
│   │   └── 003/
│   │       └── test_manifest.yaml  # Tests linked to spec
│   ├── tasks/
│   │   ├── active/
│   │   │   └── test_task_003.md    # Pending test tasks
│   │   └── completed/
│   │       └── test_task_001.md    # Completed tasks
│   ├── seeds/
│   │   ├── factories.py      # Test data factories
│   │   └── fixtures/         # Static fixtures
│   ├── mocks/
│   │   └── api_mocks.yaml    # Mock configurations
│   └── cache/
│       ├── playwright-mcp.json    # Cached setup guide
│       └── patrol.json            # Cached setup guide
├── specs/
├── stories/
└── context/
```

---

*This documentation auto-updates as testing capabilities evolve.*
