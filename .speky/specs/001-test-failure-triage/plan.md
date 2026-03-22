# Implementation Plan

## Approach
Build a rule-based test failure triage system that analyzes failing tests, modified files, and spec changes to categorize failures as regressions, outdated tests, or uncertain cases. Use simple heuristics with confidence scoring rather than complex AI, focusing on actionable terminal output with progressive disclosure.

## Tasks

- [ ] **Core Data Collection Module** (estimate: 6h)
  - Implement file readers for specs (markdown/yaml/json), test results (JSON from existing runners), and git history (via command execution)
  - Acceptance criteria: Can extract test failures, parse spec files, and get modified file lists from git
  - Dependencies: None

- [ ] **Test-Code-Spec Correlation Engine** (estimate: 8h)
  - Build logic to map failing tests to modified files and spec changes using file paths, imports, and test naming patterns
  - Acceptance criteria: Can identify which tests cover which modified files and detect spec contradictions
  - Dependencies: Data collection module

- [ ] **Rule-Based Categorization System** (estimate: 6h)
  - Implement categorization logic using the spec's decision tree (TDD tests, spec contradictions, file coverage)
  - Acceptance criteria: Assigns regression/outdated/uncertain categories with confidence scores 0-1
  - Dependencies: Correlation engine

- [ ] **Progressive Disclosure Terminal UI** (estimate: 8h)
  - Create summary view with expandable sections, keyboard navigation, and formatted output with color coding
  - Acceptance criteria: Shows collapsible categories, handles terminal width, supports drill-down navigation
  - Dependencies: Categorization system

- [ ] **CLI Command Integration** (estimate: 4h)
  - Add `speky test triage <spec-id>` command and enhance `speky complete` with failure summaries
  - Acceptance criteria: Commands execute successfully and integrate with existing SPEKY CLI structure
  - Dependencies: Terminal UI

- [ ] **Error Handling & Edge Cases** (estimate: 6h)
  - Implement graceful handling for missing files, malformed data, git errors, and low confidence scenarios
  - Acceptance criteria: System continues operating with degraded functionality rather than crashing
  - Dependencies: All previous tasks

- [ ] **Integration Testing & Validation** (estimate: 2h)
  - Test with real Flutter, Python, and JavaScript test suites to validate categorization accuracy
  - Acceptance criteria: Works end-to-end with existing test runners and produces expected output format
  - Dependencies: Complete system

## Architecture Decisions Needed
- **Test runner integration method**: Direct API calls vs subprocess execution vs shared file interface for accessing existing FlutterTestRunner, PytestRunner, JestRunner outputs
- **Confidence threshold values**: Specific numeric thresholds for high (≥0.7), medium (0.4-0.69), low (<0.4) confidence levels
- **Spec file discovery priority**: Order of searching ./spec/, ./specs/, project root, and fallback behavior when multiple matches exist

## Testing Approach
Create test fixtures with known failing tests, spec files, and git history scenarios. Validate categorization accuracy against expected outcomes for regression, outdated, and flaky test cases. Test terminal UI with various screen widths and expansion states.

## Risks & Mitigations
- **Rule-based logic may have low accuracy (< 80%)**: Start with conservative confidence scoring, mark uncertain cases for manual review, and iterate based on real usage patterns
- **Complex test suites may timeout (> 30 seconds)**: Implement analysis limits, parallel processing for independent operations, and progress indicators for long-running analysis
- **Progressive disclosure adds UI complexity**: Begin with simple expand/collapse, defer advanced navigation features, and focus on core triage functionality first