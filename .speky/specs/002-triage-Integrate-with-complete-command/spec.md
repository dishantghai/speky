# triage - Integrate with complete commandOverview

Integrate triage system with the `speky complete` command to display test failure summaries when tests fail during completion workflows.

## Priority

P1 - Critical gap between specification requirements and current implementation preventing proper test failure handling

## Context

- Source: test-failure-triage
- Depends on: Spec 001 (complete this first)
- Drift type: CODE_BEHIND

## Problem

The main speky.py file lacks any test failure handling or triage integration in the completion workflow, despite specification requirements for enhanced `speky complete` flow integration with triage summaries.

## Solution

Integrate the triage system with the complete command workflow by adding test failure detection and triage summary display when tests fail during completion.

## Acceptance Criteria

- [ ] `speky complete` command detects when tests fail during execution
- [ ] Triage summaries are automatically displayed when test failures occur
- [ ] Triage integration preserves existing complete command functionality
- [ ] Error handling gracefully manages triage system failures
- [ ] Integration follows the patterns established in test-failure-triage spec

## Technical Approach

- Modify the complete command handler in speky.py to include test result monitoring
- Add triage system calls when test failures are detected
- Implement summary display formatting within the completion workflow
- Ensure proper error handling and fallback behavior

## Out of Scope

- Modifications to the triage system itself
- Changes to test execution logic beyond failure detection
- UI/UX improvements not specified in requirements
