# SPEKY Testing Integration PRD

## Implementation Status

> **Last Updated:** January 13, 2026

### ✅ Implemented Features

| Feature | Status | Notes |
|---------|--------|-------|
| **Modular Test Runners** | ✅ Complete | Auto-detects Flutter, Python, Jest via project markers |
| **Real-Time Test Output** | ✅ Complete | Streams test results with accurate counts |
| **Coverage Parsing** | ✅ Complete | Parses lcov.info for Flutter/Jest coverage |
| **TESTING_GUIDE.md Generation** | ✅ Complete | Auto-generates at init, tech-stack aware |
| **Mid-Project Guide Refresh** | ✅ Complete | `speky test refresh-guide` with actual stats |
| **TDD Workflow** | ✅ Complete | RED-GREEN-REFACTOR with state tracking |
| **TDD Commands** | ✅ Complete | `tdd-red`, `tdd-green`, `tdd-status` |
| **Spec-Linked Tests** | ✅ Complete | `speky test link` for traceability |
| **Test Recommendations** | ✅ Complete | AI-powered suggestions based on changes |
| **IDE Context Generation** | ✅ Complete | Testing context in `.windsurfrules` |
| **Test Failure Triage** | ✅ Complete | Categorizes failures as regressions vs outdated tests |

### 🚧 In Progress / Planned

| Feature | Status | Priority |
|---------|--------|----------|
| **Visual Testing** | 📋 Planned | Phase 2 |
| **Mobile E2E (Patrol)** | 📋 Planned | Phase 2 |
| **Go/Rust Test Runners** | 📋 Planned | Phase 3 |
| **Coverage Enforcement** | 📋 Planned | Soft warnings implemented |

---

## Executive Summary

This PRD defines a comprehensive **Testing Integration** capability for SPEKY that enables:
1. **100% code coverage** tracking and enforcement
2. **Regression testing** to prevent feature breakage during new development
3. **Multi-platform E2E testing** (Flutter, Web, Native Mobile, Backend APIs)
4. **AI-assisted test generation** delegated to IDE/coding agents
5. **Flexible test execution** (specific tests, feature tests, full harness)

The integration follows SPEKY's design philosophy: **thin orchestration layer** that delegates specialized tasks to AI IDEs/coding agents while maintaining context and traceability.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Goals & Non-Goals](#goals--non-goals)
3. [Design Decisions](#design-decisions)
4. [Architecture Overview](#architecture-overview)
5. [Tech Stack Coverage](#tech-stack-coverage)
6. [Core Features](#core-features)
7. [Command Reference](#command-reference)
8. [Folder Structure](#folder-structure)
9. [Integration Patterns](#integration-patterns)
10. [Workflow Scenarios](#workflow-scenarios)
11. [Implementation Phases](#implementation-phases)
12. [Resolved Questions](#resolved-questions)

---

## Design Decisions

> **Status:** ✅ All key decisions finalized (2026-01-12)

| Decision | Choice | Rationale |
|----------|--------|----------|
| **D1: Test Organization** | **B) Standard locations with manifest linking** | Tests stay in conventional project locations (`frontend/test/`, `backend/tests/`) but are linked to specs via `.speky/testing/specs/<id>/test_manifest.yaml` |
| **D2: Coverage Enforcement** | **B) Soft warning** | Warn on coverage below threshold but don't block CI. Allows gradual adoption without friction. |
| **D3: E2E Trigger** | **B) Explicit request + optional flag on complete** | E2E runs only when explicitly requested via `speky test e2e`. Added `--test` flag to `speky complete` for optional pre-completion testing. |
| **D4: Test Generation** | **A) Task file for IDE** | Follows SPEKY's thin orchestration philosophy. Generate `test_task.md` with full context; IDE/agent implements actual tests. |
| **D5: Platform Priority** | **C) Web primary, mobile Phase 2** | Web E2E (Playwright MCP) works now with existing IDE integrations. Mobile E2E (Patrol) added in later phase. |
| **D6: Visual Testing** | **B) Phase 2** | Core functionality first. Visual regression (Percy/Chromatic) added after E2E infrastructure is stable. |
| **D7: Test Data** | **D) Hybrid per test type** | Factories for unit tests (fast, isolated), fixtures for integration (reproducible), snapshots for E2E (realistic state). |

### Enhanced `speky complete` Command

```bash
# Standard completion (no tests)
speky complete 003

# Completion with test run before marking done
speky complete 003 --test

# Completion with specific test type
speky complete 003 --test --test-type unit
speky complete 003 --test --test-type e2e
```

When `--test` flag is used:
1. Run tests linked to the spec
2. If tests fail → show failures, do NOT mark complete
3. If tests pass → proceed with drift detection and completion
4. If no tests exist → warn and suggest `speky test gen <id>`

---

## Problem Statement

### Current Pain Points

1. **No systematic test coverage** - Projects grow without comprehensive tests
2. **Regression risk** - New features break existing functionality
3. **Manual E2E testing** - Time-consuming, error-prone, inconsistent
4. **Context loss** - When writing tests, AI agents lack spec/feature context
5. **Multi-platform complexity** - Different testing approaches for web, mobile, backend
6. **Coverage gaps** - No visibility into what's tested vs. untested
7. **Flaky tests** - Tests break due to timing, environment, or brittle selectors

### User Stories

> "As a developer implementing a new feature, I want to run related tests to ensure I haven't broken existing functionality."

> "As a developer completing a spec, I want to generate comprehensive tests that cover all acceptance criteria."

> "As a team lead, I want visibility into code coverage and test health across the project."

> "As a developer, I want AI to generate tests with full context of the feature spec and existing code."

---

## Goals & Non-Goals

### Goals

| Goal | Description |
|------|-------------|
| **G1** | Track and report code coverage per spec/feature |
| **G2** | Generate tests automatically via AI with full spec context |
| **G3** | Support multiple tech stacks (Flutter, React, FastAPI, etc.) |
| **G4** | Enable selective test runs (by spec, feature, or full harness) |
| **G5** | Integrate E2E testing for web and mobile with visual validation |
| **G6** | Provide clear task handoffs to IDE agents for test implementation |
| **G7** | Detect untested code paths and suggest test coverage |
| **G8** | Support CI/CD integration for automated test runs |

### Non-Goals

| Non-Goal | Reason |
|----------|--------|
| **NG1** | Replace existing test frameworks (we orchestrate, not replace) |
| **NG2** | Provide test infrastructure (use existing CI/CD) |
| **NG3** | Implement test runners inside SPEKY (delegate to native tools) |
| **NG4** | Visual test comparison storage (use Percy/Chromatic services) |
| **NG5** | Device farms or cloud testing infrastructure |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           SPEKY Testing Layer                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │  test init   │  │  test gen    │  │  test run    │  │ test status │ │
│  │              │  │              │  │              │  │             │ │
│  │ Setup test   │  │ AI-generate  │  │ Execute      │  │ Coverage &  │ │
│  │ harness      │  │ tests from   │  │ tests via    │  │ health      │ │
│  │ config       │  │ spec context │  │ native tools │  │ dashboard   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘ │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                        Test Context Management                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    .speky/testing/                               │   │
│  │  ├── config.yaml          # Test harness configuration          │   │
│  │  ├── coverage/            # Coverage reports & tracking         │   │
│  │  ├── specs/               # Test specs linked to feature specs  │   │
│  │  └── tasks/               # IDE task files for test generation  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                    Platform-Specific Integrations                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────────────┐│
│  │  Flutter   │  │    Web     │  │  Backend   │  │   Mobile Native    ││
│  │            │  │            │  │            │  │                    ││
│  │ • patrol   │  │ • Playwright│ │ • pytest   │  │ • Maestro (cross)  ││
│  │ • flutter  │  │   MCP      │  │ • Jest     │  │ • XCTest (iOS)     ││
│  │   test     │  │ • Cypress  │  │ • httpx    │  │ • Espresso (And)   ││
│  │ • mockito  │  │ • Percy    │  │ • fixtures │  │ • Appium           ││
│  └────────────┘  └────────────┘  └────────────┘  └────────────────────┘│
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                         IDE/Agent Delegation                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Windsurf / Cursor / Claude Code / Goose                        │   │
│  │                                                                  │   │
│  │  • Receives test_task.md with full context                      │   │
│  │  • Uses Playwright MCP for browser automation                   │   │
│  │  • Generates tests following spec acceptance criteria           │   │
│  │  • Reports results back to SPEKY                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Orchestration, not implementation** - SPEKY generates context and tasks; IDEs write tests
2. **Spec-linked testing** - Every test traces back to a spec/story acceptance criteria
3. **Coverage-aware** - Track what's tested vs. untested at spec level
4. **Platform-agnostic commands** - Same SPEKY commands, different underlying tools
5. **Incremental adoption** - Start with unit tests, add E2E progressively

---

## Tech Stack Coverage

### Frontend Testing

#### Flutter (Mobile/Web/Desktop)

| Test Type | Framework | Purpose | SPEKY Integration |
|-----------|-----------|---------|-------------------|
| **Unit** | `flutter_test` | Business logic, providers | Generate from spec |
| **Widget** | `flutter_test` | UI component isolation | Generate from design |
| **Integration** | `patrol` | Full app E2E with native | Task delegation |
| **Golden** | `golden_toolkit` | Visual regression | Compare with design |

**Key Tools:**
- `patrol` - Native feature testing (permissions, notifications, WebViews)
- `mockito` - Dependency mocking
- `mocktail` - Simpler mock syntax
- `flutter_driver` - Legacy integration tests

**Coverage Tool:** `flutter test --coverage` → `lcov`

#### Web (React/Vue/Next.js/Svelte)

| Test Type | Framework | Purpose | SPEKY Integration |
|-----------|-----------|---------|-------------------|
| **Unit** | Jest/Vitest | Component logic | Generate from spec |
| **Component** | Testing Library | UI behavior | Generate from spec |
| **E2E** | Playwright | Full browser flow | MCP delegation |
| **Visual** | Percy/Chromatic | Screenshot diff | CI integration |

**Key Tools:**
- `@playwright/test` - Cross-browser E2E
- `playwright-mcp` - AI agent browser control
- `@testing-library/react` - User-centric component tests
- `msw` - API mocking

**Coverage Tool:** `c8`, `istanbul`, `nyc`

### Backend Testing

#### Python (FastAPI/Django/Flask)

| Test Type | Framework | Purpose | SPEKY Integration |
|-----------|-----------|---------|-------------------|
| **Unit** | pytest | Function/class tests | Generate from spec |
| **Integration** | pytest + TestClient | API endpoint tests | Generate from spec |
| **Database** | pytest + fixtures | Data layer tests | Fixture generation |
| **Contract** | schemathesis | API schema validation | Auto from OpenAPI |

**Key Tools:**
- `pytest` - Core test framework
- `pytest-cov` - Coverage reporting
- `pytest-asyncio` - Async test support
- `httpx` - Async HTTP client for testing
- `factory_boy` - Test data factories
- `faker` - Synthetic data generation

**Coverage Tool:** `pytest-cov` → `coverage.py`

#### Node.js (Express/Nest.js)

| Test Type | Framework | Purpose | SPEKY Integration |
|-----------|-----------|---------|-------------------|
| **Unit** | Jest/Vitest | Function tests | Generate from spec |
| **Integration** | Supertest | API endpoint tests | Generate from spec |
| **Database** | Jest + fixtures | Data layer tests | Fixture generation |

**Coverage Tool:** `c8`, `istanbul`

### Mobile Native Testing

#### iOS (Swift/Objective-C)

| Test Type | Framework | Purpose | SPEKY Integration |
|-----------|-----------|---------|-------------------|
| **Unit** | XCTest | Logic tests | Task delegation |
| **UI** | XCUITest | UI automation | Task delegation |
| **Snapshot** | iOSSnapshotTestCase | Visual regression | CI integration |

#### Android (Kotlin/Java)

| Test Type | Framework | Purpose | SPEKY Integration |
|-----------|-----------|---------|-------------------|
| **Unit** | JUnit | Logic tests | Task delegation |
| **UI** | Espresso | UI automation | Task delegation |
| **Screenshot** | Screenshot Tests | Visual regression | CI integration |

#### Cross-Platform Mobile

| Framework | Pros | Cons | Best For |
|-----------|------|------|----------|
| **Maestro** | YAML-based, easy setup, reliable | Limited advanced scenarios | Quick E2E flows |
| **Appium** | Cross-platform, language agnostic | Slow, flaky | Legacy or complex |
| **Detox** | Fast, reliable for React Native | React Native only | RN projects |

---

## Core Features

### F1: Test Harness Initialization

**Command:** `speky test init`

**Purpose:** Set up testing infrastructure for a project based on its tech stack.

**Flow:**
1. Detect tech stack from `context.json`
2. Recommend testing frameworks
3. Generate `config.yaml` with test configuration
4. Create test directory structure
5. Generate sample test templates
6. Update `.gitignore` for coverage files

**Output:**
```yaml
# .speky/testing/config.yaml
version: "1.0"
project: "spayce"
tech_stack:
  frontend: flutter
  backend: fastapi
  
test_frameworks:
  frontend:
    unit: flutter_test
    widget: flutter_test
    integration: patrol
    coverage_tool: lcov
    coverage_threshold: 80
  backend:
    unit: pytest
    integration: pytest
    coverage_tool: pytest-cov
    coverage_threshold: 85
    
e2e:
  web:
    framework: playwright
    mcp_enabled: true
    visual_testing: percy
  mobile:
    framework: patrol
    platforms: [ios, android]
    
mock_data:
  strategy: factory
  seed_file: .speky/testing/seeds/test_data.yaml
  
ci_integration:
  provider: github_actions
  run_on: [push, pull_request]
  parallel: true
```

---

### F2: Test Generation from Specs

**Command:** `speky test gen <spec-id> [--type TYPE]`

**Purpose:** Generate tests that cover all acceptance criteria in a spec.

**Flow:**
1. Load spec from `.speky/specs/<id>/spec.md`
2. Parse acceptance criteria and user stories
3. Generate test task for IDE with full context
4. IDE implements tests following task instructions
5. Link generated tests to spec in coverage tracking

**Test Task Template:**
```markdown
# Test Generation Task: Spec 003 - User Authentication

## Context

### Spec Summary
[Extracted from spec.md]

### Acceptance Criteria to Cover
1. [ ] User can sign in with Google OAuth
2. [ ] Tokens are stored securely
3. [ ] Session persists across app restarts
4. [ ] Sign-out clears all credentials

### Tech Stack
- Frontend: Flutter with Riverpod
- Backend: FastAPI
- Auth: Firebase Auth + Google Sign-In

### Existing Tests
[List of existing test files]

### Related Code
[Key files to test]

## Test Requirements

### Unit Tests Required
For each acceptance criterion, create unit tests:

**AC1: Google OAuth Sign-In**
- Test: Auth provider returns user on successful sign-in
- Test: Auth provider handles cancellation gracefully
- Test: Auth provider handles network errors with retry

**AC2: Secure Token Storage**
- Test: Tokens are written to secure storage
- Test: Tokens are encrypted (mock verify)
- Test: Tokens are cleared on error

### Integration Tests Required
- Test: Full sign-in flow with mock Google
- Test: Token refresh before expiry
- Test: Session restoration on app restart

### E2E Tests Required
- Test: User can complete sign-in flow on web
- Test: User can complete sign-in flow on mobile
- Test: Sign-out returns user to login screen

## Output
Create tests in:
- `frontend/test/features/authentication/`
- `backend/tests/test_auth.py`

Use existing patterns from:
- `frontend/test/auth_test.dart`
- `backend/tests/test_auth.py`
```

---

### F3: Test Execution

**Command:** `speky test run [options]`

**Options:**
```
speky test run                    # Run full test harness
speky test run --spec 003         # Run tests for specific spec
speky test run --story F001       # Run tests for specific story
speky test run --type unit        # Run only unit tests
speky test run --type e2e         # Run only E2E tests
speky test run --affected         # Run tests affected by recent changes
speky test run --failed           # Re-run previously failed tests
speky test run --coverage         # Run with coverage reporting
speky test run --watch            # Watch mode for TDD
```

**Flow:**
1. Load test configuration from `config.yaml`
2. Determine which tests to run based on options
3. Execute tests using native test runners
4. Collect and aggregate results
5. Update coverage tracking
6. Report results with actionable output

**Execution Strategies:**

| Strategy | Description | Use Case |
|----------|-------------|----------|
| **Full Harness** | All tests across all platforms | Pre-release, CI main branch |
| **Spec-Scoped** | Tests linked to a specific spec | After implementing a spec |
| **Affected** | Tests for changed files + dependents | Fast feedback during dev |
| **Failed** | Previously failed tests only | Quick re-verification |
| **Type-Filtered** | Unit, widget, integration, or E2E | Targeted testing |

---

### F4: Coverage Tracking

**Command:** `speky test coverage [options]`

**Options:**
```
speky test coverage               # Show overall coverage
speky test coverage --spec 003    # Coverage for specific spec
speky test coverage --by-spec     # Coverage breakdown by spec
speky test coverage --gaps        # Show untested code
speky test coverage --trend       # Show coverage over time
```

**Coverage Model:**

```yaml
# .speky/testing/coverage/coverage.yaml
overall:
  line_coverage: 78.5
  branch_coverage: 72.3
  function_coverage: 85.2
  
by_spec:
  001-google-auth:
    coverage: 92.0
    files:
      - path: lib/features/authentication/data/auth_notifier.dart
        coverage: 95.0
        uncovered_lines: [45, 67, 89]
      - path: lib/features/authentication/domain/auth_state.dart
        coverage: 100.0
        
  002-browser-module:
    coverage: 65.0
    gaps:
      - description: "Tab persistence not tested"
        file: lib/features/browser/data/tab_manager.dart
        lines: [120-145]
        suggested_tests:
          - "Test tab state survives app restart"
          - "Test tab order persistence"

untested_specs:
  - 005-search-functionality
  - 006-notifications
```

**Coverage Dashboard Output:**
```
📊 Test Coverage Report
═══════════════════════════════════════════════════════════════

Overall Coverage: 78.5% ████████████████░░░░ (Target: 80%)

By Spec:
  ✅ 001-google-auth          92.0% ██████████████████░░
  ✅ 002-browser-module       85.0% █████████████████░░░
  ⚠️  003-spaces-management   72.0% ██████████████░░░░░░
  ❌ 004-learning-paths       45.0% █████████░░░░░░░░░░░
  ⏸️  005-search              0.0%  (no tests)

Coverage Gaps (Top 5):
  1. lib/features/spaces/data/space_provider.dart:120-145
     → Missing: CRUD operation tests
  2. lib/features/browser/data/tab_manager.dart:89-110
     → Missing: Tab reordering edge cases
  3. backend/app/routes/auth.py:45-67
     → Missing: Token refresh error handling

Run `speky test gen 004` to generate tests for Learning Paths
```

---

### F5: E2E Test Orchestration

**Command:** `speky test e2e [options]`

**Purpose:** Orchestrate end-to-end tests across platforms with proper app startup.

**Options:**
```
speky test e2e                    # Run all E2E tests
speky test e2e --platform web     # Web only (Playwright)
speky test e2e --platform mobile  # Mobile only (Patrol/Maestro)
speky test e2e --spec 003         # E2E for specific spec
speky test e2e --visual           # Include visual regression
speky test e2e --headed           # Run with visible browser
speky test e2e --record           # Record test execution
```

**E2E Execution Flow:**

```
┌─────────────────────────────────────────────────────────────┐
│                    E2E Test Execution                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. SETUP                                                    │
│     ├─ Start backend (mock or real)                         │
│     ├─ Start frontend dev server                            │
│     ├─ Seed test database                                   │
│     └─ Configure mock services                              │
│                                                              │
│  2. EXECUTE                                                  │
│     ├─ Launch browser/emulator/simulator                    │
│     ├─ Run test scenarios                                   │
│     ├─ Capture screenshots at key points                    │
│     └─ Record video (optional)                              │
│                                                              │
│  3. VALIDATE                                                 │
│     ├─ Assert expected outcomes                             │
│     ├─ Compare visual snapshots                             │
│     └─ Check accessibility                                  │
│                                                              │
│  4. CLEANUP                                                  │
│     ├─ Stop servers                                         │
│     ├─ Reset database                                       │
│     └─ Archive artifacts                                    │
│                                                              │
│  5. REPORT                                                   │
│     ├─ Generate test report                                 │
│     ├─ Upload to CI artifacts                               │
│     └─ Update SPEKY coverage tracking                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

### F6: Playwright MCP Integration

**Purpose:** Enable AI agents to automate browser testing via MCP.

**Configuration:**
```yaml
# .speky/testing/config.yaml
e2e:
  web:
    mcp:
      enabled: true
      server: "@playwright/mcp"
      options:
        browser: chromium
        headless: true
        viewport: { width: 1280, height: 720 }
        screenshot_on_failure: true
```

**MCP Task Template:**
```markdown
# E2E Test Task: Spec 003 - User Authentication Flow

## MCP Configuration
Use Playwright MCP server for browser automation.

## Test Scenarios

### Scenario 1: Successful Google Sign-In
1. Navigate to app URL
2. Click "Sign in with Google" button
3. Complete OAuth flow (mock or sandbox)
4. Verify redirect to home screen
5. Verify user name displayed in header

### Scenario 2: Sign-In Cancellation
1. Navigate to app URL
2. Click "Sign in with Google" button
3. Cancel OAuth flow
4. Verify user remains on login screen
5. Verify no error displayed (graceful handling)

### Scenario 3: Sign-Out Flow
1. Sign in successfully
2. Click user avatar
3. Click "Sign Out"
4. Verify redirect to login screen
5. Verify protected routes are inaccessible

## Assertions
Use `expect()` for all assertions. Capture screenshot on failure.

## Output
Save tests to: `frontend/test/e2e/auth_flow_test.dart`
```

---

### F7: Mobile E2E with Patrol

**Purpose:** Enable Flutter E2E tests with native feature access.

**Patrol Configuration:**
```yaml
# .speky/testing/config.yaml
e2e:
  mobile:
    framework: patrol
    config:
      app_id: com.spayce.spayce
      android:
        emulator: Pixel_6_API_33
      ios:
        simulator: iPhone 15 Pro
    features:
      - permissions
      - notifications
      - webview_interaction
```

**Patrol Test Task Template:**
```markdown
# Patrol E2E Test Task: Spec 002 - Browser Module

## Setup Requirements
- patrol_cli installed
- Emulator/Simulator running
- App built in debug mode

## Test Scenarios

### Scenario 1: Create New Tab
```dart
patrolTest('user can create new browser tab', ($) async {
  await $.pumpWidgetAndSettle(const SpayceApp());
  
  // Navigate to browser
  await $('Browser').tap();
  
  // Click new tab button
  await $('+').tap();
  
  // Verify new tab created
  expect($('New Tab'), findsOneWidget);
});
```

### Scenario 2: WebView Navigation
```dart
patrolTest('user can navigate in webview', ($) async {
  // Test actual WebView navigation
  await $.native.enterText(
    Selector(text: 'Search or enter URL'),
    'https://flutter.dev'
  );
  await $.native.tap(Selector(text: 'Go'));
  
  // Wait for page load
  await $.pump(Duration(seconds: 3));
  
  // Verify URL changed
  expect($('flutter.dev'), findsOneWidget);
});
```

## Native Feature Tests

### Permission Handling
```dart
patrolTest('app handles camera permission', ($) async {
  // Trigger permission request
  await $('Scan QR').tap();
  
  // Handle native permission dialog
  await $.native.grantPermissionWhenInUse();
  
  // Verify camera view opens
  expect($('Camera Preview'), findsOneWidget);
});
```
```

---

### F8: Test Data Management

**Command:** `speky test data [action]`

**Actions:**
```
speky test data seed              # Seed database with test data
speky test data reset             # Reset to clean state
speky test data snapshot          # Save current state as snapshot
speky test data restore <name>    # Restore from snapshot
speky test data generate          # Generate synthetic data
```

**Test Data Configuration:**
```yaml
# .speky/testing/seeds/test_data.yaml
users:
  - id: test-user-1
    email: test@example.com
    name: Test User
    created_at: "2024-01-01T00:00:00Z"
    
  - id: test-user-2
    email: admin@example.com
    name: Admin User
    role: admin

spaces:
  - id: space-1
    owner_id: test-user-1
    name: Learning Space
    items: []
    
browser_tabs:
  - id: tab-1
    user_id: test-user-1
    url: https://flutter.dev
    title: Flutter
    order: 0
```

**Mock Service Configuration:**
```yaml
# .speky/testing/mocks/services.yaml
services:
  google_auth:
    type: mock
    responses:
      sign_in_success:
        user_id: test-user-1
        email: test@example.com
        token: mock-token-12345
      sign_in_cancel:
        error: user_cancelled
        
  backend_api:
    type: local
    base_url: http://localhost:8000
    fixtures:
      - endpoint: /api/spaces
        method: GET
        response_file: fixtures/spaces.json
```

---

### F9: CI/CD Integration

**Command:** `speky test ci [action]`

**Actions:**
```
speky test ci setup               # Generate CI workflow files
speky test ci status              # Check CI test status
speky test ci artifacts           # Download CI test artifacts
```

**Generated CI Workflow (GitHub Actions):**
```yaml
# .github/workflows/test.yml (generated by SPEKY)
name: Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Flutter
        uses: subosito/flutter-action@v2
        with:
          flutter-version: '3.19.0'
          
      - name: Install dependencies
        run: flutter pub get
        working-directory: frontend
        
      - name: Run unit tests with coverage
        run: flutter test --coverage
        working-directory: frontend
        
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: frontend/coverage/lcov.info
          
  backend-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
          
      - name: Install dependencies
        run: pip install -r requirements.txt
        working-directory: backend
        
      - name: Run pytest with coverage
        run: pytest --cov=app --cov-report=xml
        working-directory: backend
        
  e2e-tests:
    runs-on: ubuntu-latest
    needs: [unit-tests, backend-tests]
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Flutter
        uses: subosito/flutter-action@v2
        
      - name: Install Playwright
        run: npx playwright install --with-deps chromium
        
      - name: Start backend
        run: |
          cd backend && python -m uvicorn app.main:app &
          sleep 5
          
      - name: Run E2E tests
        run: flutter test integration_test/
        working-directory: frontend
        
      - name: Upload screenshots
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: e2e-screenshots
          path: frontend/test/screenshots/
```

---

### F10: Test Health Dashboard

**Command:** `speky test status`

**Output:**
```
🧪 Test Health Dashboard
═══════════════════════════════════════════════════════════════

Test Suite Status
─────────────────
  Frontend Unit:        ✅ 156 passed, 0 failed
  Frontend Widget:      ✅ 43 passed, 0 failed
  Frontend Integration: ⚠️  12 passed, 2 flaky
  Backend Unit:         ✅ 89 passed, 0 failed
  Backend Integration:  ✅ 24 passed, 0 failed
  E2E Web:              ✅ 18 passed, 0 failed
  E2E Mobile:           ❌ 8 passed, 1 failed

Coverage Summary
────────────────
  Overall:              78.5% (Target: 80%)
  Frontend:             75.2%
  Backend:              85.3%

Recent Failures
───────────────
  ❌ test_tab_persistence (E2E Mobile)
     Last failed: 2 hours ago
     Failure rate: 3/10 runs (30%)
     → Likely flaky - investigate timing

Untested Specs
──────────────
  • 005-search-functionality (0% coverage)
  • 006-notifications (0% coverage)
  
  Run `speky test gen 005` to generate tests

Action Items
────────────
  1. Fix failing E2E test: test_tab_persistence
  2. Generate tests for spec 005
  3. Increase coverage to reach 80% target (+1.5%)
```

---

## Command Reference

### Core Testing Commands

| Command | Description |
|---------|-------------|
| `speky test init` | Initialize test harness for project |
| `speky test gen <id>` | Generate tests for spec/story |
| `speky test run [options]` | Execute tests |
| `speky test run --spec <id>` | Run tests for specific spec |
| `speky test run --affected` | Run only tests affected by changes |
| `speky test coverage` | Show coverage report |
| `speky test e2e [options]` | Run E2E tests |
| `speky test data <action>` | Manage test data |
| `speky test ci <action>` | CI/CD integration |
| `speky test status` | Show test health dashboard |
| `speky test link <test> --spec <id>` | Link existing test to spec |
| `speky test gaps` | Show untested acceptance criteria |
| `speky test recommend` | Get test recommendations based on changes |
| `speky test setup <tool>` | Get setup guide for testing tool |
| `speky test refresh-context` | Refresh IDE context for testing |

### TDD Workflow Commands

| Command | Description |
|---------|-------------|
| `speky implement <id> --tdd` | Start TDD workflow for a spec |
| `speky test tdd-red <id>` | RED phase: verify tests fail (before implementation) |
| `speky test tdd-green <id>` | GREEN phase: verify tests pass (after implementation) |
| `speky test tdd-status` | Show TDD dashboard for all specs |
| `speky test tdd-status <id>` | Show TDD status for specific spec |

### Completion with Testing

| Command | Description |
|---------|-------------|
| `speky complete <id>` | Complete spec (auto-runs tests for TDD specs) |
| `speky complete <id> --test` | Complete with explicit test verification |

### TDD Workflow

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

### TDD States

| State | Icon | Description |
|-------|------|-------------|
| `tests_generated` | 📝 | Test task created, waiting for test implementation |
| `red_confirmed` | 🔴 | Tests created and verified failing (ready for implementation) |
| `implementing` | 🔧 | Feature implementation in progress |
| `green_passed` | 🟢 | All TDD tests passing (ready for completion) |
| `regression_passed` | ✅ | All tests passing including regression |

---

## Folder Structure

```
.speky/
├── testing/
│   ├── config.yaml                 # Test harness configuration
│   ├── coverage/
│   │   ├── coverage.yaml           # Aggregated coverage data
│   │   ├── history/                # Historical coverage snapshots
│   │   │   ├── 2024-01-01.yaml
│   │   │   └── 2024-01-15.yaml
│   │   └── reports/                # Generated reports
│   │       ├── lcov.info
│   │       └── coverage.html
│   ├── specs/
│   │   ├── 001-auth/
│   │   │   ├── test_manifest.yaml  # Tests linked to this spec
│   │   │   └── test_task.md        # IDE task for test generation
│   │   └── 002-browser/
│   │       ├── test_manifest.yaml
│   │       └── test_task.md
│   ├── seeds/
│   │   ├── test_data.yaml          # Test data definitions
│   │   └── snapshots/              # Database snapshots
│   ├── mocks/
│   │   ├── services.yaml           # Mock service configs
│   │   └── fixtures/               # Response fixtures
│   │       ├── users.json
│   │       └── spaces.json
│   └── tasks/
│       ├── active/                 # Current IDE tasks
│       │   └── gen_tests_003.md
│       └── completed/              # Archived tasks
│           └── gen_tests_001.md

project/
├── frontend/
│   └── test/
│       ├── unit/                   # Unit tests
│       ├── widget/                 # Widget tests
│       ├── integration/            # Integration tests
│       └── e2e/                    # E2E tests (Patrol)
├── backend/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── fixtures/
└── .github/
    └── workflows/
        └── test.yml                # CI workflow (generated)
```

---

## Integration Patterns

### Pattern 1: Test Generation with Full Context

```
Developer                SPEKY                    IDE Agent
    │                      │                          │
    │ speky test gen 003   │                          │
    │─────────────────────>│                          │
    │                      │                          │
    │                      │ Load spec.md, plan.md    │
    │                      │ Load existing tests      │
    │                      │ Identify coverage gaps   │
    │                      │                          │
    │                      │ Generate test_task.md    │
    │                      │─────────────────────────>│
    │                      │                          │
    │                      │      "Implement tests    │
    │                      │       following task"    │
    │                      │                          │
    │                      │<─────────────────────────│
    │                      │     Tests created        │
    │                      │                          │
    │                      │ Update test_manifest     │
    │                      │ Link tests to spec       │
    │<─────────────────────│                          │
    │  "Tests generated    │                          │
    │   for spec 003"      │                          │
```

### Pattern 2: Regression Testing on Feature Change

```
Developer                SPEKY                    Test Runner
    │                      │                          │
    │ speky implement 003  │                          │
    │─────────────────────>│                          │
    │                      │                          │
    │      [Developer implements feature]             │
    │                      │                          │
    │ speky complete 003   │                          │
    │─────────────────────>│                          │
    │                      │                          │
    │                      │ Detect affected tests    │
    │                      │ Run: speky test run      │
    │                      │      --spec 003          │
    │                      │─────────────────────────>│
    │                      │                          │
    │                      │<─────────────────────────│
    │                      │     Test results         │
    │                      │                          │
    │<─────────────────────│                          │
    │  "All tests passed"  │                          │
    │  OR                  │                          │
    │  "3 tests failed -   │                          │
    │   fix before         │                          │
    │   marking complete"  │                          │
```

### Pattern 3: E2E with MCP Delegation

```
Developer                SPEKY                    IDE + MCP
    │                      │                          │
    │ speky test e2e       │                          │
    │   --spec 003         │                          │
    │─────────────────────>│                          │
    │                      │                          │
    │                      │ Start backend server     │
    │                      │ Start frontend server    │
    │                      │ Seed test database       │
    │                      │                          │
    │                      │ Generate E2E task        │
    │                      │ with MCP instructions    │
    │                      │─────────────────────────>│
    │                      │                          │
    │                      │    IDE uses Playwright   │
    │                      │    MCP to automate       │
    │                      │    browser interactions  │
    │                      │                          │
    │                      │<─────────────────────────│
    │                      │    Test results +        │
    │                      │    screenshots           │
    │                      │                          │
    │                      │ Cleanup servers          │
    │                      │ Update coverage          │
    │<─────────────────────│                          │
    │  "E2E tests complete │                          │
    │   12/12 passed"      │                          │
```

---

## Workflow Scenarios

### Scenario 1: New Project Setup

```bash
# 1. Initialize project
speky init "Learning Management System"

# 2. Initialize test harness
speky test init
# → Detects Flutter + FastAPI
# → Creates config.yaml
# → Sets up test directories
# → Generates CI workflow

# 3. Create first spec
speky spec "User Authentication"
speky plan 001
speky implement 001

# 4. Generate tests for spec
speky test gen 001
# → IDE receives task with full context
# → IDE creates unit, widget, integration tests
# → Tests linked to spec

# 5. Run tests
speky test run --spec 001
# → All tests pass ✅

# 6. Complete spec
speky complete 001
```

### Scenario 2: Adding Tests to Existing Project

```bash
# 1. Initialize test harness
speky test init
# → Scans existing tests
# → Creates config.yaml
# → Identifies coverage gaps

# 2. Check coverage
speky test coverage --by-spec
# → Shows 45% overall coverage
# → Lists untested specs

# 3. Generate tests for untested spec
speky test gen 003 --type unit
# → IDE generates unit tests

speky test gen 003 --type e2e
# → IDE generates E2E tests

# 4. Run full harness
speky test run --coverage
# → Coverage improved to 72%

# 5. Check remaining gaps
speky test gaps
# → Lists specific untested acceptance criteria
```

### Scenario 3: Regression Testing During Development

```bash
# 1. Start implementing new feature
speky implement 005

# 2. Make changes to shared code
# ... developer edits code ...

# 3. Run affected tests
speky test run --affected
# → Detects changed files
# → Runs tests that depend on those files
# → Reports: 2 tests failed ❌

# 4. Fix regressions
# ... developer fixes issues ...

# 5. Re-run affected tests
speky test run --failed
# → All previously failed tests now pass ✅

# 6. Complete feature
speky complete 005
```

### Scenario 4: E2E Testing with Visual Regression

```bash
# 1. Run E2E tests with visual comparison
speky test e2e --visual

# 2. Review visual changes
# → Percy/Chromatic shows screenshot diffs
# → Developer approves or rejects changes

# 3. Run E2E on specific platform
speky test e2e --platform mobile --headed
# → Patrol runs on visible simulator
# → Developer watches test execution

# 4. Record test for debugging
speky test e2e --spec 003 --record
# → Video recording saved
# → Useful for debugging flaky tests
```

---

## Implementation Phases

### Phase 1: Core Infrastructure (MVP)

**Duration:** 2 weeks

**Features:**
- `test init` - Basic configuration setup
- `test run` - Execute native test commands
- `test coverage` - Parse coverage reports
- `test status` - Basic dashboard

**Tech Stack Support:**
- Flutter (flutter_test)
- Python (pytest)

**Deliverables:**
- `.speky/testing/config.yaml` schema
- Coverage parsing for lcov and coverage.py
- Basic CLI commands

---

### Phase 2: Test Generation

**Duration:** 2 weeks

**Features:**
- `test gen` - Generate test tasks for IDE
- Spec-to-test linking
- Coverage gap analysis
- Test manifest tracking

**Deliverables:**
- Test task templates
- `test_manifest.yaml` schema
- Gap detection algorithm

---

### Phase 3: Web E2E Integration

**Duration:** 3 weeks

**Features:**
- `test e2e` - E2E orchestration (web-first)
- Playwright MCP integration for browser automation
- Server startup/teardown automation
- Test data seeding (hybrid: factories + fixtures)
- `--test` flag for `speky complete`

**Deliverables:**
- E2E task templates for web
- MCP configuration
- Mock service framework
- Integration with `speky complete --test`

**Note:** Mobile E2E (Patrol) deferred to Phase 5 per design decisions.

---

### Phase 4: CI/CD & Advanced Features

**Duration:** 2 weeks

**Features:**
- `test ci` - CI workflow generation
- Visual regression integration (Percy/Chromatic)
- Flaky test detection
- Historical tracking
- Parallel test execution

**Deliverables:**
- CI workflow templates (GitHub Actions, GitLab CI)
- Visual testing configuration
- Coverage trending

---

### Phase 5: Mobile E2E & Multi-Platform Expansion

**Duration:** 3 weeks

**Features:**
- **Mobile E2E:** Patrol integration for Flutter mobile
- **Mobile E2E:** Maestro integration for cross-platform mobile
- React/Vue/Next.js web testing support
- Native iOS (XCTest) support
- Native Android (Espresso) support

**Deliverables:**
- Patrol configuration and task templates
- Maestro YAML test generation
- Extended tech stack configurations
- Platform-specific task templates
- Cross-platform test orchestration

---

## TDD Workflow Feature (NEW)

> **Status:** 🚧 In Development (January 2026)

### Overview

SPEKY supports Test-Driven Development (TDD) workflow with the `--tdd` flag on the `implement` command. This enables a proper Red-Green-Refactor cycle integrated with spec-driven development.

### TDD Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TDD Workflow                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. INITIATE                                                           │
│     speky implement 003 --tdd                                          │
│     ├─ Load spec context (spec.md, plan.md)                            │
│     ├─ Generate comprehensive test task                                 │
│     └─ Hand off to IDE for test creation                               │
│                                                                         │
│  2. RED PHASE (Tests Should Fail)                                      │
│     ├─ User confirms tests are created                                 │
│     ├─ SPEKY runs tests automatically                                  │
│     ├─ Shows test failures (expected)                                  │
│     └─ Confirms TDD cycle started                                      │
│                                                                         │
│  3. GREEN PHASE (Implementation)                                       │
│     ├─ Hand off implementation task to IDE                             │
│     ├─ IDE/Agent implements feature                                    │
│     ├─ Each iteration can trigger test run                             │
│     └─ IDE signals "done" → auto-run tests                             │
│                                                                         │
│  4. COMPLETION                                                         │
│     speky complete 003                                                 │
│     ├─ Detect TDD was enabled                                          │
│     ├─ Run spec-related tests (GREEN check)                            │
│     ├─ Run regression tests (all other tests)                          │
│     ├─ If ALL pass → complete spec                                     │
│     └─ If ANY fail → BLOCK completion                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Commands

```bash
# Start TDD implementation
speky implement 003 --tdd

# Manual test run during implementation
speky test run --spec 003

# Complete with test verification (automatic for TDD)
speky complete 003

# View TDD status
speky test status --spec 003
```

### State Tracking

```json
// .speky/specs/003/status.json
{
  "status": "in_progress",
  "priority": "P1",
  "dependencies": ["001"],
  
  // TDD State
  "tdd": {
    "enabled": true,
    "state": "implementing",  // "tests_generated" | "red_confirmed" | "implementing" | "green_passed"
    "started_at": "2026-01-12T14:30:00Z",
    "tests": {
      "linked_files": [
        "test/unit/services/auth_service_test.dart",
        "test/widget/auth/login_widget_test.dart"
      ],
      "last_run": "2026-01-12T15:00:00Z",
      "last_result": "failed",
      "passed": 2,
      "failed": 3,
      "total": 5
    },
    "regression": {
      "last_run": null,
      "passed": 0,
      "failed": 0,
      "total": 0
    }
  }
}
```

### TDD vs Non-TDD Behavior

| Behavior | TDD Enabled (`--tdd`) | Non-TDD |
|----------|----------------------|---------|
| Test generation | Required first step | Optional |
| Red phase | Must run, must fail | N/A |
| Implementation | After red phase | Immediate |
| Test run on complete | Required, auto-run | Optional (`--test`) |
| Completion with failures | **BLOCKED** | Warning only |
| Regression testing | Required | Optional |

### Completion Enforcement

**TDD Enabled (Hard Block):**
```
❌ Cannot complete spec 003 - Browser Module

TDD Tests: 3 failing
  - test_tab_creation: FAILED
  - test_tab_close: FAILED  
  - test_url_navigation: PASSED

Regression Tests: 2 failing
  - test_auth_session: FAILED (REGRESSION!)
  - test_spaces_crud: FAILED (REGRESSION!)

Action Required:
  1. Fix failing TDD tests (3)
  2. Fix regression issues (2)
  3. Run: speky complete 003
```

**Non-TDD (Warning + Suggestion):**
```
⚠️  No tests linked to spec 003 - Browser Module

Recommendation: Consider adding tests before completing.
  Run: speky test gen 003

Options:
  [1] Complete anyway (no tests)
  [2] Generate tests first
  [3] Cancel

Choice: 
```

### Coverage Dashboard

```bash
speky test status
```

```
🧪 Test Coverage Dashboard
═══════════════════════════════════════════════════════════════

Overall Status
──────────────
  Total Tests: 54
  Passing: 48
  Failing: 6
  Coverage: 78.5%

Spec Coverage
─────────────
  ✅ 001-auth              TDD   5/5 tests passing
  🔴 003-browser           TDD   2/5 tests failing (implementing)
  ✅ 004-spaces            ---   8/8 tests passing
  ⏸️  005-search           ---   0 tests (not started)

TDD In Progress
───────────────
  003-browser: RED → implementing
    Started: 2026-01-12 14:30
    Tests: 2 passing, 3 failing
    State: Waiting for implementation

Untested Specs
──────────────
  • 005-search-functionality
  • 006-notifications

Run `speky test gen 005` to generate tests
```

### Modular Test Runner Architecture

```python
class TestRunner(ABC):
    """Abstract base class for tech-specific test runners."""
    
    @abstractmethod
    def detect(self, project_path: Path) -> bool:
        """Detect if this runner applies to the project."""
        pass
    
    @abstractmethod
    def run_tests(self, test_files: List[str] = None) -> TestResult:
        """Run tests and return results."""
        pass
    
    @abstractmethod
    def get_coverage(self) -> CoverageResult:
        """Get coverage data."""
        pass

class FlutterTestRunner(TestRunner):
    """Flutter test runner using flutter test."""
    pass

class PytestRunner(TestRunner):
    """Python test runner using pytest."""
    pass

class JestRunner(TestRunner):
    """JavaScript/TypeScript test runner using Jest."""
    pass

class NpmTestRunner(TestRunner):
    """Generic npm test runner."""
    pass
```

### Tech Stack Support

| Tech Stack | Test Command | Coverage Tool | Status |
|------------|-------------|---------------|--------|
| **Flutter** | `flutter test` | lcov | ✅ Implemented |
| **Python** | `pytest` | pytest-cov | ✅ Implemented |
| **Node.js** | `npm test` | c8/istanbul | ✅ Implemented |
| **React** | `npm test` | jest --coverage | ✅ Implemented |
| **Vue** | `npm test` | vitest | 🚧 Planned |
| **Go** | `go test` | go test -cover | 🚧 Planned |
| **Rust** | `cargo test` | cargo-tarpaulin | 🚧 Planned |

### Configuration

```yaml
# .speky/testing/config.yaml
version: "1.0"
project: "spayce"

tdd:
  enabled: true  # Allow --tdd flag
  default: false  # Don't require TDD by default
  
regression:
  scope: "all"  # "all" | "affected" | "spec_related"
  on_complete: true  # Run regression on complete
  
tech_runners:
  flutter:
    enabled: true
    command: "flutter test"
    coverage_command: "flutter test --coverage"
    test_pattern: "*_test.dart"
    test_dirs: ["test/"]
    
  python:
    enabled: true
    command: "pytest"
    coverage_command: "pytest --cov"
    test_pattern: "test_*.py"
    test_dirs: ["tests/"]
    
  node:
    enabled: true
    command: "npm test"
    coverage_command: "npm test -- --coverage"
    test_pattern: "*.test.js"
    test_dirs: ["__tests__/", "test/"]
```

### IDE Integration Task Template

When TDD is enabled, SPEKY generates a test task for the IDE:

```markdown
# TDD Test Task: Spec 003 - Browser Module

## Phase: RED (Create Failing Tests)

### Context
[Full spec context loaded]

### Acceptance Criteria to Cover
1. [ ] User can create new browser tab
2. [ ] User can close browser tab
3. [ ] User can navigate to URL
4. [ ] Tab state persists across sessions
5. [ ] Error handling for invalid URLs

### Required Tests

**Unit Tests:**
- `test/unit/services/tab_service_test.dart`
  - `test_createTab_shouldCreateNewTab`
  - `test_closeTab_shouldRemoveTab`
  - `test_navigateToUrl_shouldUpdateTabUrl`
  - `test_invalidUrl_shouldThrowError`

**Widget Tests:**
- `test/widget/browser/tab_bar_test.dart`
  - `test_tabBar_shouldDisplayTabs`
  - `test_tabBar_newTabButton_shouldCreateTab`
  - `test_tabBar_closeButton_shouldCloseTab`

### Test Patterns to Follow
[Existing test patterns from project]

### Output
Create test files that:
1. Follow existing project patterns
2. Cover ALL acceptance criteria
3. Use proper mocking/stubbing
4. Include edge cases
5. **Should FAIL initially** (no implementation yet)

### After Test Creation
Signal completion by creating: `.speky/testing/tasks/T003/tests_ready.signal`
```

---

## Real-World Learnings: Spayce Project

> **Status:** ✅ Validated approach (January 2026)

### Project Context

**Tech Stack:**
- Frontend: Flutter (macOS, Web)
- Backend: FastAPI
- Database: Drift (SQLite)
- State: Riverpod

**Initial State:**
- 44 unit tests (passing)
- 2 widget tests (failing - binding initialization)
- 11 E2E tests (blocked by Flutter architecture bug)
- No systematic test strategy

### Key Findings

#### ✅ What Worked

**1. Run All Tests Strategy**
- **Finding:** With 46 tests, running all tests takes ~10 seconds
- **Impact:** Fast enough to run before every commit
- **Recommendation:** Continue "run all tests" until 500+ tests
- **Validation:** Matches Stage 1 (MVP) strategy in roadmap

**2. Unit Tests First**
- **Finding:** Unit tests work without device/architecture issues
- **Impact:** Fast feedback, no infrastructure dependencies
- **Recommendation:** 70% unit tests as foundation
- **Validation:** Test pyramid approach is correct

**3. SPEKY Test Generation**
- **Finding:** `speky test gen` provides full spec context to IDE
- **Impact:** Tests cover all acceptance criteria
- **Recommendation:** Always use for new features
- **Validation:** Thin orchestration philosophy works

**4. Simple CI/CD**
- **Finding:** Basic GitHub Actions workflow sufficient for MVP
- **Impact:** Automated testing without complexity
- **Recommendation:** Start simple, add complexity later
- **Validation:** Stage-appropriate infrastructure

#### ❌ What Didn't Work

**1. E2E Tests from Terminal**
- **Issue:** Flutter debug mode has architecture bug on macOS
- **Error:** `Unable to find device matching { platform:macOS, arch:arm64 }`
- **Root Cause:** Flutter tooling bug, not SPEKY issue
- **Workaround:** Use release mode or Xcode GUI
- **Lesson:** E2E tests have platform-specific challenges

**2. Empty AI-Generated Tests**
- **Issue:** AI created empty test files (0 bytes)
- **Impact:** Tests fail with "Undefined name 'main'"
- **Solution:** Delete empty files, regenerate with SPEKY
- **Lesson:** Validate AI-generated tests before committing

**3. Widget Binding Initialization**
- **Issue:** Widget tests fail without `TestWidgetsFlutterBinding.ensureInitialized()`
- **Impact:** 2 tests failing unnecessarily
- **Solution:** Add initialization in test setup
- **Lesson:** Platform-specific test setup is critical

### Validated Decisions

| Decision | Validation | Status |
|----------|-----------|--------|
| **D2: Soft warning for coverage** | Allows gradual adoption without friction | ✅ Correct |
| **D3: Explicit E2E trigger** | E2E blocked by architecture bug, explicit trigger is right | ✅ Correct |
| **D4: Task file for IDE** | IDE receives full context, generates proper tests | ✅ Correct |
| **D5: Web primary, mobile Phase 2** | Mobile E2E has platform issues, web is more stable | ✅ Correct |

### Recommendations Based on Learnings

#### For SPEKY Users

**1. Start with Unit Tests**
```bash
# Initialize testing
speky test init

# Generate unit tests first
speky test gen 001 --type unit

# Run before every commit
flutter test  # or pytest, npm test
```

**2. Fix Infrastructure First**
- Resolve architecture issues
- Fix binding initialization
- Ensure native tools work
- Then add SPEKY orchestration

**3. Defer E2E Until Stable**
- Unit tests catch most bugs
- E2E tests are expensive
- Platform issues can block progress
- Add E2E when unit tests are solid

**4. Use Stage-Appropriate Strategy**
- MVP (0-100 tests): Run all tests
- Don't over-engineer for small projects
- Add complexity only when needed

#### For SPEKY Development

**1. Add Platform-Specific Troubleshooting**
- Document common issues (architecture, binding, etc.)
- Provide platform-specific fixes
- Link to troubleshooting guide

**2. Validate Test Generation**
- Check for empty files
- Verify test structure
- Ensure imports are correct
- Warn if tests are malformed

**3. Enhance Test Init**
- Detect platform-specific issues
- Suggest fixes for common problems
- Generate platform-specific setup code

**4. Add Test Health Checks**
```bash
speky test validate
# Checks:
# - All test files have main()
# - Required dependencies installed
# - Platform-specific setup correct
# - Coverage tools available
```

### Updated Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           SPEKY Testing Layer                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │  test init   │  │  test gen    │  │  test run    │  │ test status │ │
│  │              │  │              │  │              │  │             │ │
│  │ • Detect     │  │ • Load spec  │  │ • Delegate   │  │ • Coverage  │ │
│  │   platform   │  │ • Generate   │  │   to native  │  │ • Health    │ │
│  │ • Check      │  │   task       │  │   tools      │  │ • Gaps      │ │
│  │   issues     │  │ • Provide    │  │ • Aggregate  │  │             │ │
│  │ • Setup      │  │   context    │  │   results    │  │             │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘ │
│                                                                         │
│  NEW: Platform Issue Detection                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ • Flutter architecture check (macOS)                            │   │
│  │ • Widget binding validation                                     │   │
│  │ • Empty test file detection                                     │   │
│  │ • Coverage tool availability                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Metrics from Real Project

| Metric | Spayce Project | Target | Status |
|--------|---------------|--------|--------|
| Test Count | 46 | 50-100 (MVP) | ✅ On track |
| Test Runtime | 10 seconds | < 30 seconds | ✅ Excellent |
| Coverage | ~75% | 70% (MVP) | ✅ Above target |
| Failure Rate | 0% (after fixes) | < 5% | ✅ Excellent |
| Flaky Tests | 0 | < 1% | ✅ Excellent |

### Timeline

**Week 1: Infrastructure Setup**
- Fixed architecture issue (ARCHS x86_64 → arm64)
- Fixed widget binding initialization
- Deleted empty test files
- Result: 46/46 tests passing ✅

**Week 2: Strategy Documentation**
- Created test strategy guide
- Documented "run all tests" approach
- Set coverage target (80%)
- Established workflow

**Week 3: Expansion Plan**
- Generate test tasks for untested specs
- Focus on unit tests (fast, reliable)
- Add widget tests incrementally
- Defer E2E until architecture bug fixed

### Lessons for Future Projects

**✅ Do:**
1. Start with unit tests (70% of suite)
2. Run all tests before commit (if < 500 tests)
3. Fix infrastructure issues first
4. Use SPEKY for test generation
5. Follow stage-appropriate strategy
6. Validate AI-generated tests

**❌ Don't:**
1. Over-engineer for small projects
2. Add E2E tests too early
3. Ignore platform-specific issues
4. Skip test validation
5. Commit broken tests
6. Build complex infrastructure prematurely

### Conclusion

The Spayce project validated SPEKY's testing approach:
- ✅ Thin orchestration works
- ✅ Stage-appropriate strategy is correct
- ✅ Unit tests first is the right approach
- ✅ "Run all tests" scales to 500+ tests
- ✅ Platform-specific issues are real and need documentation

**Next Steps:**
1. Add platform issue detection to `test init`
2. Create troubleshooting guide
3. Validate test generation output
4. Document common platform issues

---

## Resolved Questions

> All key questions have been resolved. Decisions documented in [Design Decisions](#design-decisions) section.

| Question | Decision | Notes |
|----------|----------|-------|
| Q1: Test Ownership | **B) Standard locations + manifest** | Conventional project structure with SPEKY tracking |
| Q2: Coverage Enforcement | **B) Soft warning** | Non-blocking, gradual adoption |
| Q3: E2E Trigger | **B) Explicit + `--test` flag** | `speky complete --test` for optional pre-completion testing |
| Q4: Test Generation | **A) Task file for IDE** | Thin orchestration, IDE implements |
| Q5: Platform Priority | **C) Web first, mobile Phase 5** | Playwright MCP available now |
| Q6: Visual Testing | **B) Phase 4** | After core E2E is stable |
| Q7: Test Data | **D) Hybrid** | Factories/fixtures/snapshots per test type |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Code coverage | ≥80% | `speky test coverage` |
| Test pass rate | ≥98% | CI dashboard |
| Flaky test rate | <2% | Historical analysis |
| Time to generate tests | <30 min/spec | Manual tracking |
| Regression detection rate | 100% | Post-release bug analysis |
| E2E test stability | ≥95% | CI metrics |

---

## Appendix A: Testing Framework Comparison

### Unit Testing Frameworks

| Framework | Language | Pros | Cons |
|-----------|----------|------|------|
| `pytest` | Python | Powerful fixtures, plugins | Learning curve |
| `unittest` | Python | Built-in | Verbose |
| `Jest` | JavaScript | Fast, snapshots | Config complexity |
| `Vitest` | JavaScript | Fast, ESM native | Newer |
| `flutter_test` | Dart | Official, well integrated | Limited mocking |

### E2E Testing Frameworks

| Framework | Platform | Pros | Cons |
|-----------|----------|------|------|
| `Playwright` | Web | Fast, reliable, MCP | Complex setup |
| `Cypress` | Web | Great DX, time travel | Chrome-focused |
| `Patrol` | Flutter | Native access, Dart | Flutter only |
| `Maestro` | Mobile | YAML, easy | Limited advanced |
| `Appium` | Mobile | Universal | Slow, flaky |

### Visual Testing Services

| Service | Pros | Cons | Pricing |
|---------|------|------|---------|
| Percy | Mature, good integrations | Can be expensive | $$$$ |
| Chromatic | Great for Storybook | Less general | $$$ |
| BackstopJS | Free, self-hosted | Manual setup | Free |
| Applitools | AI-powered | Enterprise pricing | $$$$$ |

---

## Appendix B: Sample Test Task

```markdown
# Test Generation Task

## Metadata
- Spec: 003-spaces-management
- Generated: 2024-01-15T10:30:00Z
- Status: pending

## Spec Context

### Summary
Spaces are collections of learning resources that users can create, organize, and share.

### Acceptance Criteria
1. User can create a new space with name and description
2. User can add items (links, notes, files) to a space
3. User can reorder items within a space via drag-and-drop
4. User can delete a space (with confirmation)
5. Spaces persist across app restarts

### Technical Requirements
- State management: Riverpod
- Local storage: Drift database
- Backend sync: REST API

## Existing Tests
- `test/features/spaces/space_provider_test.dart` - Basic CRUD (60% coverage)

## Coverage Gaps
- AC3: Reorder items - NO TESTS
- AC4: Delete space - NO TESTS
- AC5: Persistence - NO TESTS

## Test Requirements

### Unit Tests (space_provider_test.dart)

**AC3: Reorder Items**
```dart
test('reorderItem moves item to new position', () {
  // Setup: Create space with 3 items
  // Action: Call reorderItem(fromIndex: 0, toIndex: 2)
  // Assert: Items are in new order
});

test('reorderItem handles same index gracefully', () {
  // No-op test
});

test('reorderItem handles invalid indices', () {
  // Error handling test
});
```

**AC4: Delete Space**
```dart
test('deleteSpace removes space from list', () {
  // ...
});

test('deleteSpace removes all items in space', () {
  // ...
});

test('deleteSpace handles non-existent space', () {
  // ...
});
```

**AC5: Persistence**
```dart
test('spaces persist after provider recreation', () {
  // Test Drift persistence
});
```

### Widget Tests (space_list_widget_test.dart)

```dart
testWidgets('delete button shows confirmation dialog', (tester) async {
  // Pump widget
  // Tap delete
  // Verify dialog appears
});

testWidgets('drag handle enables reordering', (tester) async {
  // Pump widget with 3 items
  // Drag first to last
  // Verify order changed
});
```

### Integration Tests (spaces_integration_test.dart)

```dart
patrolTest('full space lifecycle', ($) async {
  // Create space
  // Add items
  // Reorder items
  // Delete space
  // Verify removed
});
```

## Output Location
- Unit: `test/features/spaces/space_provider_test.dart` (extend existing)
- Widget: `test/features/spaces/space_list_widget_test.dart` (new file)
- Integration: `integration_test/spaces_test.dart` (new file)

## Notes
- Use existing `test/helpers/test_utils.dart` for setup
- Mock Drift with `MockSpaceDatabase` (exists)
- Follow existing test patterns in `test/features/authentication/`
```

---

*Document Version: 1.0*
*Last Updated: 2026-01-12*
*Author: SPEKY Testing Integration PRD*
