# Test Failure Triage

## Overview

Intelligent analysis of test failures to categorize them as **regressions** (fix code) vs **outdated tests** (update tests), enabling developers and AI agents to take the correct action when tests fail during feature implementation.

## Project Context

**Product**: SPEKY (AI-Assisted Software Engineering Framework)

**Target Users**: 
- Primary: Software developers implementing features across multiple codebases
- Secondary: Development teams streamlining test failure resolution

**Integration Requirements**: 
- Must work as CLI tool with existing development workflows
- Cross-language compatibility required (Flutter, Python, JavaScript)
- Terminal-based interface for seamless workflow integration

## File Access Patterns

### Specification Files
- **File Discovery**: 
  - Primary search: `./spec/` and `./specs/` directories from project root
  - Fallback search: Project root directory for spec files
  - Glob patterns: `**/*.{md,yml,yaml,json}` for recursive discovery
  - Naming convention: `<spec-id>.{md,yml,yaml,json}` for direct lookup
- **Supported Formats**: 
  - Markdown (.md) with YAML frontmatter or structured headings
  - YAML (.yml, .yaml) with defined schema
  - JSON (.json) with specification structure
- **Reading Strategy**: 
  - On-demand loading when spec-id is specified
  - Bulk discovery for complete flow validation
  - Stream reading for large specification files
- **Validation**: 
  - Format validation during read operations
  - Schema validation for YAML/JSON specs
  - Markdown structure validation for required sections
- **Error Handling**: 
  - Graceful fallback when primary location fails
  - Clear error messages for malformed specifications
  - Permission error handling with actionable guidance

### Test Files
- **Location Patterns**: 
  - Flutter: `test/**/*_test.dart` relative to project root
  - Python: `tests/**/*.py` and `test_*.py` patterns
  - JavaScript: `**/*.{test,spec}.{js,ts}` in test directories
  - Cross-platform: Follow framework conventions for each language
- **File Reading**: 
  - Direct file system access for test source code analysis
  - Integration with test runners for execution results
  - Metadata extraction from test file headers and comments
- **Test Metadata Extraction**: 
  - Creation timestamps from git history
  - Coverage scope from test imports and assertions
  - Test-to-spec associations from comments or naming patterns
  - Dependency analysis from import statements
- **Performance Considerations**: 
  - Lazy loading of test file content
  - Caching of parsed test metadata
  - Parallel reading for large test suites

### Git History Access
- **Command Execution Patterns**: 
  - `git diff --name-only HEAD~1..HEAD` for recent changes
  - `git log --oneline --since="<timestamp>" --follow <file>` for file history
  - `git show <commit>:<file>` for historical file content
  - `git blame <file>` for line-by-line change attribution
- **Data Extraction Methods**: 
  - Commit metadata: timestamp, author, message, hash
  - File change detection: added, modified, deleted, renamed
  - Diff analysis: line-level changes, function modifications
  - Branch analysis: feature branch vs main branch changes
- **Repository Validation**: 
  - Git repository detection in project root
  - Working directory clean state verification
  - Remote repository connectivity checks
- **Performance Optimization**: 
  - Shallow clone support for faster operations
  - Cached git command results with TTL
  - Batch git operations to reduce command overhead
- **Error Handling**: 
  - Git command failure recovery
  - Repository state validation
  - Network timeout handling for remote operations

### File System Monitoring
- **Change Detection**: 
  - File modification time tracking
  - Content hash comparison for change validation
  - Directory structure monitoring for new/deleted files
- **Caching Strategy**: 
  - LRU cache for frequently accessed files
  - Invalidation on file system changes
  - Memory-efficient caching for large codebases
- **Batch Operations**: 
  - Bulk file reading for initial analysis
  - Streaming for large file processing
  - Parallel I/O operations where safe

### Access Permissions & Security
- **File Permission Handling**: 
  - Read permission validation before file access
  - Graceful degradation when files are inaccessible
  - User guidance for permission issues
- **Path Security**: 
  - Path traversal prevention
  - Sandboxing to project directory
  - Validation of file paths before access
- **Resource Limits**: 
  - Maximum file size limits for processing
  - Timeout limits for file operations
  - Memory usage controls for large files

## Data Sources & Integration

### Test Results Access
- **Source**: Existing SPEKY test runner modules (FlutterTestRunner, PytestRunner, JestRunner)
- **Format**: Standardized JSON output from test execution
- **Access Method**: Direct API calls to test runner modules with structured result objects
- **Data Schema**: 
  ```json
  {
    "test_id": "string",
    "name": "string", 
    "status": "pass|fail|skip",
    "file_path": "string",
    "error_message": "string",
    "stack_trace": "string",
    "execution_time": "number",
    "coverage_files": ["string"]
  }
  ```

### Specification Files Access
- **Location**: Project root directory (`./spec/` or `./specs/`) or current working directory
- **Formats**: Markdown (.md), YAML (.yml, .yaml), JSON (.json)
- **Access Method**: Direct file system reads using relative paths from project root
- **File Resolution**: 
  - Primary: `<spec-id>.md` in spec directory
  - Fallback: Search project root for matching spec files
  - Validation: Parse and validate spec format before analysis

### File Change History Access
- **VCS Integration**: Git repository integration via `git` command-line interface
- **Tracking Scope**: 
  - Modified files since last commit or specified baseline
  - File diff analysis to identify changed functions/classes
  - Commit metadata (timestamp, author, message)
- **Access Method**: 
  - `git diff --name-only` for changed file list
  - `git log --oneline --since` for recent commit history
  - `git show <commit>` for specific change analysis
- **Update Frequency**: Real-time analysis on command execution

### TDD State Integration
- **Source**: Existing SPEKY TDD tracking system
- **Data**: Test creation timestamps, spec associations, test-to-requirement mappings
- **Access Method**: Query TDD state database/files to identify tests created for current spec
- **Format**: JSON metadata linking tests to specifications and implementation phases

## Requirements

### Functional Requirements
- FR-1: Analyze failing test cases and categorize them as regression, outdated, or flaky
- FR-2: Provide reasoning for each categorization decision based on test code, spec changes, and modified files
- FR-3: Support triage command `speky test triage <spec-id>` for detailed failure analysis
- FR-4: Integrate with existing test runners (Flutter, Python, JavaScript) to extract failure data
- FR-5: Display actionable recommendations for each failing test
- FR-6: Enhance `speky complete` flow with failure summary and triage suggestions
- FR-7: Parse test metadata including creation time and coverage scope
- FR-8: Include confidence scoring in categorization output with high/medium/low confidence levels
- FR-9: Implement progressive disclosure pattern with summary view and drill-down capabilities

### Non-Functional Requirements
- NFR-1: Performance - Complete triage analysis within 30 seconds for typical test suites
- NFR-2: Accuracy - Achieve 80%+ correct categorization of test failures
- NFR-3: Usability - Provide clear, actionable output in terminal-friendly text format
- NFR-4: Reliability - Handle edge cases gracefully without crashing the workflow
- NFR-5: Compatibility - Work seamlessly with existing SPEKY command structure

### Business Requirements
- BR-1: Reduce developer investigation time for test failures by 50%
- BR-2: Prevent bugs from being hidden by incorrectly updating tests instead of fixing code
- BR-3: Minimize time wasted fixing correct code when tests need updating
- BR-4: Enable faster feature completion cycles by streamlining test failure resolution

### Technical Requirements
- TR-1: Integration with existing modular test runners (FlutterTestRunner, PytestRunner, JestRunner)
- TR-2: Access to TDD state tracking for identifying tests created for current spec
- TR-3: Spec file parsing capabilities to understand requirement changes
- TR-4: File change tracking to correlate test failures with modified code
- TR-5: Terminal-based output formatting with clear categorization display

## User Interface & Progressive Disclosure

### Progressive Disclosure Pattern

**Default Summary View**:
- High-level metrics: total failures, category breakdown, overall confidence
- Critical failures requiring immediate attention (high-confidence regressions)
- Quick action buttons: "Show All Details", "Fix Regressions", "Update Tests"
- Expandable category summaries with failure counts and confidence indicators

**Drill-down Navigation**:
```
Summary View (Default)
├── Regressions (3) [EXPAND]
│   ├── High Confidence (2) [EXPAND]
│   └── Medium Confidence (1) [EXPAND]
├── Outdated Tests (5) [EXPAND]
│   ├── High Confidence (4) [EXPAND]
│   └── Medium Confidence (1) [EXPAND]
└── Uncertain (2) [EXPAND]
    └── Manual Review Required [EXPAND]

Detailed View (On Expand)
├── Test Name: specific_test_function
├── File: path/to/test_file.py
├── Category: Regression
├── Confidence: High (85%)
├── Reasoning: [Full explanation]
├── Error Message: [Complete stack trace]
├── Recommendation: [Specific action steps]
└── Related Files: [Modified files this test covers]
```

**Interaction Controls**:
- `[+]` / `[-]` Expand/collapse individual sections
- `--summary` flag for compact view (default)
- `--detailed` flag for full expanded view
- `--category=regression` to show only specific category
- Navigation breadcrumbs: `Summary > Regressions > High Confidence > test_name`

**State Management**:
- Preserve expansion state during session
- Remember user preferences for summary vs detailed view
- Cache expanded data to avoid re-analysis
- Provide "Back to Summary" option from any detail view

**Loading Strategy**:
- Summary data: Load immediately with basic metrics
- Category details: Load on-demand when user expands section
- Full test analysis: Lazy load when drilling into specific test
- Progress indicators for long-running detailed analysis

**Responsive Behavior**:
- Terminal width detection for optimal formatting
- Automatic text wrapping for narrow terminals
- Truncation with "..." and expand option for long content
- Keyboard navigation support (Tab, Enter, Esc)

### Output Format Examples

**Summary View (Default)**:
```
📊 Test Failure Triage Summary (12 total failures)

🔴 REGRESSIONS (3) - Fix Implementation Required
   ├── High Confidence: 2 tests [EXPAND with 'r']
   └── Medium Confidence: 1 test [EXPAND with 'r']

🟡 OUTDATED TESTS (5) - Update Tests Required  
   ├── High Confidence: 4 tests [EXPAND with 'o']
   └── Medium Confidence: 1 test [EXPAND with 'o']

⚪ UNCERTAIN (2) - Manual Investigation Required
   └── Low Confidence: 2 tests [EXPAND with 'u']

❓ FLAKY/UNRELATED (2) - Environment Issues
   └── Investigation needed [EXPAND with 'f']

Quick Actions:
  speky test triage <spec-id> --category=regression  (focus on regressions)
  speky test triage <spec-id> --detailed            (show all details)
```

**Expanded Category View**:
```
🔴 REGRESSIONS (High Confidence)

1. test_user_authentication_flow
   Confidence: 85% | File: test/auth_test.py
   Reason: Test covers modified authentication.py
   Action: Review changes to login validation logic
   [EXPAND for full details with 'd1']

2. test_payment_processing  
   Confidence: 90% | File: test/payment_test.py
   Reason: Error mentions modified PaymentService class
   Action: Check payment calculation changes
   [EXPAND for full details with 'd2']

[Back to Summary with 'b'] | [Show All Details with 'a']
```

**Full Detail View**:
```
📋 DETAILED ANALYSIS: test_user_authentication_flow

Category: REGRESSION (Fix Implementation)
Confidence: High (85%)
File: test/auth_test.py
Modified Files: src/authentication.py, src/user_service.py

Reasoning:
- Test directly covers authentication.py which was modified 2 hours ago
- Error message indicates AuthenticationError on line changed in recent commit
- Test was created before this feature (not a TDD test for current spec)
- No spec changes contradict this test's expectations

Error Message:
  AssertionError: Expected successful login, got AuthenticationError
  at authentication.py:45 in validate_credentials()

Stack Trace:
  [Full stack trace...]

Recommendation:
  1. Review changes to validate_credentials() method
  2. Check if new validation logic is too strict
  3. Verify test credentials are still valid format

Related Changes:
  - authentication.py: Modified validate_credentials() method
  - user_service.py: Updated user lookup logic

[Back to Category with 'b'] | [Back to Summary with 's']
```

## Technical Architecture

### System Overview Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Test Failure Triage System                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐ │
│  │   Test Runners  │    │  Spec Parser    │    │  Git History │ │
│  │                 │    │                 │    │   Tracker    │ │
│  │ • FlutterRunner │    │ • Markdown      │    │              │ │
│  │ • PytestRunner  │    │ • YAML          │    │ • File diffs │ │
│  │ • JestRunner    │    │ • JSON          │    │ • Timestamps │ │
│  └─────────┬───────┘    └─────────┬───────┘    └──────┬───────┘ │
│            │                      │                   │         │
│            └──────────┬───────────┴───────────────────┘         │
│                       │                                         │
│         ┌─────────────▼─────────────┐                           │
│         │    Data Aggregation       │                           │
│         │    & Preprocessing        │                           │
│         │                           │                           │
│         │ • Test result validation  │                           │
│         │ • Spec change detection   │                           │
│         │ • File correlation        │                           │
│         │ • TDD state lookup        │                           │
│         └─────────────┬─────────────┘                           │
│                       │                                         │
│         ┌─────────────▼─────────────┐                           │
│         │      AI Analysis          │                           │
│         │      Engine               │                           │
│         │                           │                           │
│         │ • Pattern recognition     │                           │
│         │ • Categorization logic    │                           │
│         │ • Reasoning generation    │                           │
│         │ • Confidence calculation  │                           │
│         └─────────────┬─────────────┘                           │
│                       │                                         │
│         ┌─────────────▼─────────────┐                           │
│         │   Results Processing      │                           │
│         │   & Formatting            │                           │
│         │                           │                           │
│         │ • Category assignment     │                           │
│         │ • Confidence scoring      │                           │
│         │ • Terminal formatting     │                           │
│         │ • Action recommendations  │                           │
│         └─────────────┬─────────────┘                           │
│                       │                                         │
│         ┌─────────────▼─────────────┐                           │
│         │    Output Delivery        │                           │
│         │                           │                           │
│         │ • CLI display             │                           │
│         │ • Complete flow integration│                           │
│         │ • Error handling          │                           │
│         └───────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow Description

1. **Test Data Collection**: 
   - Test runners execute and generate standardized JSON output
   - Results include test status, error messages, stack traces, and coverage data
   - Failed tests are filtered and prepared for analysis

2. **Context Gathering**:
   - Spec parser extracts current requirements and recent changes
   - Git tracker identifies modified files and change history
   - TDD state provides test creation metadata and spec associations

3. **Data Preprocessing**:
   - Validates and normalizes test result data
   - Correlates failing tests with modified files
   - Maps tests to specification requirements
   - Enriches data with historical context

4. **AI Analysis Pipeline**:
   - Pattern recognition identifies failure types based on test code and error patterns
   - Categorization logic applies rules and heuristics for classification
   - Confidence calculation evaluates certainty of categorization decision
   - Reasoning generation provides explanations for each categorization decision

5. **Results Processing**:
   - Assigns final categories (regression, outdated, flaky)
   - Calculates confidence scores and confidence levels
   - Formats output for terminal display with color coding and structure
   - Generates specific action recommendations for each test

6. **Output Delivery**:
   - CLI displays formatted triage results with confidence indicators
   - Integrates with `speky complete` workflow
   - Provides error handling and recovery options

### Integration Points

- **Test Runner APIs**: Direct integration with existing SPEKY test execution modules
- **File System**: Reads spec files and accesses project structure
- **Git Integration**: Command-line interface for version control operations
- **TDD State**: Database/file queries for test metadata
- **CLI Framework**: Terminal output formatting and command handling

### Data Contracts

**Test Runner Output**:
```json
{
  "failures": [
    {
      "test_id": "string",
      "name": "string",
      "file_path": "string",
      "error_message": "string",
      "stack_trace": "string",
      "coverage_files": ["string"]
    }
  ]
}
```

**Analysis Result**:
```json
{
  "test_id": "string",
  "category": "regression|outdated|flaky",
  "confidence": 0.85,
  "confidence_level": "high",
  "reasoning": "string",
  "recommendation": "string"
}
```

### Confidence Scoring System

**Confidence Calculation Methodology**:
- **Base confidence**: 0.5 (neutral starting point)
- **Evidence weighting**: Each categorization signal adds/subtracts confidence
- **Signal strength factors**:
  - Strong indicators: ±0.3 confidence adjustment
  - Medium indicators: ±0.2 confidence adjustment  
  - Weak indicators: ±0.1 confidence adjustment

**Confidence Level Thresholds**:
- **High confidence**: ≥0.7 (strong recommendation, auto-categorization)
- **Medium confidence**: 0.4-0.69 (moderate recommendation, user review suggested)
- **Low confidence**: <0.4 (uncertain, manual investigation required)

**Confidence Factors by Category**:

*Regression Indicators (increase confidence)*:
- Test covers modified files: +0.3
- Error message mentions changed function: +0.2
- Recent git history shows related changes: +0.1

*Outdated Test Indicators (increase confidence)*:
- Spec explicitly contradicts test assertion: +0.3
- Test created before spec change: +0.2
- API signature mismatch in error: +0.2

*Flaky Test Indicators (increase confidence)*:
- Intermittent failure history: +0.2
- Environment/timing related errors: +0.1
- No correlation with recent changes: +0.1

**Low Confidence Handling**:
- Display "UNCERTAIN" category with reasoning
- Suggest manual investigation steps
- Provide option to force categorization with user override
- Log low-confidence cases for model improvement

## MVP Scope

### Included in MVP
- Core triage command `speky test triage <spec-id>` for analyzing failing tests
- Categorization of failures into three types: regression, outdated, or flaky
- Confidence scoring with high/medium/low levels for each categorization
- Basic reasoning display for each categorization decision
- Integration with existing test runners (Flutter, Python, JavaScript)
- Enhanced `speky complete` flow with failure summary
- Text-based output format for terminal use
- Progressive disclosure with summary view and expandable details

### Excluded from MVP
- Auto-fixing or auto-updating of failing tests
- Visual/GUI interface for triage results
- Historical trend analysis of test failures
- CI/CD pipeline integration
- Advanced machine learning models for categorization
- Bulk test management operations

### MVP Success Criteria
- Successfully categorizes test failures with 80%+ accuracy
- Provides confidence scores for all categorizations
- Reduces developer investigation time by 50%
- Works reliably across Flutter, Python, and JavaScript test suites
- Provides actionable recommendations within 30 seconds
- Integrates seamlessly with existing SPEKY workflow
- Summary view loads within 5 seconds, detailed analysis within 15 seconds

### Timeline
- Core triage logic implementation: 2 weeks
- Confidence scoring system: 1 week
- Progressive disclosure UI implementation: 1 week
- Test runner integration: 1 week
- Enhanced complete flow: 1 week
- Testing and validation: 1 week

## Problem Statement

When implementing new features in projects with existing test suites, some tests may fail. Currently, SPEKY:
- Blocks completion when tests fail
- Reports pass/fail counts
- Does NOT help identify WHY tests fail

Developers must manually investigate each failure to determine:
1. **Regression**: New code broke existing functionality → Fix the implementation
2. **Outdated Test**: Test expectations don't match new requirements → Update the test
3. **Flaky Test**: Environment/timing issue → Investigate infrastructure

Making the wrong choice leads to:
- Updating tests when code is actually broken (hiding bugs)
- Wasting time fixing code when tests just need updating

## User Stories

### Story 1: Triage Failing Tests
> "As a developer completing a spec, when tests fail, I want SPEKY to analyze the failures and categorize them so I know whether to fix my code or update the tests."

**Acceptance Criteria:**
- [ ] New command `speky test triage <spec-id>` analyzes failing tests
- [ ] Categorizes each failure as: regression, outdated, or flaky
- [ ] Shows confidence score and level for each categorization
- [ ] Shows reasoning for each categorization
- [ ] Suggests specific action for each failing test
- [ ] Works with Flutter, Python, and JavaScript test suites
- [ ] Provides summary view by default with option to expand details

### Story 2: Enhanced Complete Flow
> "As a developer, when `speky complete` fails due to test failures, I want to see a quick summary of likely causes so I can take immediate action."

**Acceptance Criteria:**
- [ ] `speky complete` shows triage summary when tests fail
- [ ] Groups failures by category (regression vs outdated)
- [ ] Shows confidence levels for categorizations
- [ ] Suggests running `speky test triage <id>` for details
- [ ] Provides actionable next steps
- [ ] Uses progressive disclosure to avoid overwhelming output

## Error Handling

### Error Categories & Codes

**Test Output Errors**
- `TEST_MALFORMED_JSON`: Invalid JSON format in test runner output
- `TEST_MISSING_FIELDS`: Required fields missing from test results
- `TEST_CORRUPTED_DATA`: Test output data is unreadable or incomplete
- `TEST_RUNNER_CRASH`: Test runner process terminated unexpectedly

**File System Errors**
- `SPEC_FILE_NOT_FOUND`: Specification file does not exist at expected path
- `SPEC_PERMISSION_DENIED`: Insufficient permissions to read specification file
- `SPEC_INVALID_FORMAT`: Specification file format is invalid or corrupted
- `TEST_FILE_ACCESS_ERROR`: Cannot access test files for analysis

**AI Service Errors**
- `AI_API_TIMEOUT`: AI analysis request exceeded timeout limit
- `AI_QUOTA_EXCEEDED`: API rate limit or quota exceeded
- `AI_SERVICE_UNAVAILABLE`: AI service is temporarily unavailable
- `AI_ANALYSIS_FAILED`: AI categorization returned invalid results

**Confidence Scoring Errors**
- `CONFIDENCE_CALCULATION_FAILED`: Error in confidence score computation
- `INSUFFICIENT_SIGNALS`: Not enough data to calculate meaningful confidence
- `CONFIDENCE_THRESHOLD_ERROR`: Invalid confidence threshold configuration

### Handling Strategies

**Test Output Error Handling**
- **Malformed JSON**: Log detailed error with line/column info, display user-friendly message, provide manual retry option
- **Missing fields**: Highlight specific missing data fields, provide guidance on test runner configuration
- **Corrupted data**: Attempt partial analysis with available data, warn user of incomplete results
- **Runner crashes**: Capture crash logs, suggest test environment troubleshooting

**File System Error Handling**
- **Missing specs**: Display clear error with expected file path, suggest file location and creation steps
- **Permission issues**: Show access error with specific path, provide troubleshooting steps for permissions
- **Invalid format**: Validate spec format, show specific validation errors with line numbers
- **Access errors**: Check file existence and permissions, provide actionable resolution steps

**AI Service Error Handling**
- **API failures**: Implement exponential backoff (1s, 2s, 4s, 8s), fallback to cached results if available
- **Rate limiting**: Queue requests with progress indicator, estimate wait time for user
- **Service unavailable**: Provide manual categorization mode, cache request for retry
- **Analysis failures**: Log AI response, fallback to rule-based categorization

**Confidence Scoring Error Handling**
- **Calculation failures**: Fall back to default medium confidence (0.5), log error for investigation
- **Insufficient signals**: Mark as low confidence, suggest manual review
- **Threshold errors**: Use default thresholds, warn user of configuration issue

### User Experience During Errors

**Error Message Format**
```
❌ Error: [ERROR_CODE] Brief description
   
   Details: Specific technical information
   
   Suggested Actions:
   1. Immediate action user can take
   2. Alternative approach if available
   3. How to get additional help
   
   Run 'speky test triage --help' for more options
```

**Progress Indicators**
- Show analysis progress during long operations
- Display retry attempts with countdown timers
- Provide cancel option for user-initiated abort

**Graceful Degradation**
- Continue with partial analysis when some data unavailable
- Offer manual override options for critical workflows
- Preserve user work and state during error recovery
- Default to medium confidence when confidence calculation fails

### Recovery Actions

**Automatic Recovery**
- Retry failed operations with exponential backoff
- Cache successful results to avoid re-analysis
- Auto-save triage state for interrupted sessions

**Manual Recovery Options**
- `--force-retry`: Bypass cached results and retry analysis
- `--manual-mode`: Skip AI analysis, use rule-based categorization only
- `--partial-analysis`: Continue with incomplete data
- `--low-confidence-ok`: Accept low confidence categorizations

**Data Preservation**
- Save partial triage results before errors occur
- Maintain command history for easy re-execution
- Backup critical state to prevent data loss

### Logging & Monitoring Requirements

**Error Logging**
- Log all errors with timestamp, context, and stack trace
- Include user environment details (OS, test runner versions)
- Sanitize sensitive information from logs
- Track confidence score distributions and error patterns

**Monitoring Metrics**
- Track error frequency by category and type
- Monitor AI service response times and failure rates
- Measure user recovery success rates
- Monitor confidence score accuracy over time

**Debug Information**
- Provide verbose mode for detailed error diagnosis
- Include relevant file paths and permissions in error context
- Log AI request/response pairs for analysis debugging
- Include confidence calculation details in debug logs

## Technical Approach

### AI Analysis Inputs
1. **Failing test code** - What the test asserts
2. **Current spec** - What requirements changed
3. **Changed files** - What code was modified in this feature
4. **Test metadata** - When test was created, what it covers

### Categorization Logic

```
IF test was created FOR this spec (TDD test):
    → Valid failure: implementation incomplete
    → Confidence: High (0.8+)
    
ELIF test asserts something CONTRADICTED by current spec:
    → Invalid failure: test needs update
    → Confidence: High (0.8+) if explicit contradiction, Medium (0.6) if implicit
    
ELIF test covers files modified in this feature:
    → Likely regression: review changes
    → Confidence: Medium-High (0.7) if direct coverage, Medium (0.5) if indirect
    
ELSE:
    → Likely flaky or unrelated: investigate
    → Confidence: Low-Medium (0.4) - requires investigation
```

### Output Format

```
🔴 LIKELY REGRESSIONS (Fix Implementation)
   1. test_name - Confidence: High (85%) - Reason: covers modified file X

🟡 LIKELY OUTDATED (Update Tests)
   1. test_name - Confidence: High (90%) - Reason: spec changed return type
   
⚪ INVESTIGATE (Flaky/Unrelated)
   1. test_name - Confidence: Low (30%) - Reason: no obvious connection

❓ UNCERTAIN (Manual Review Required)
   1. test_name - Confidence: Low (25%) - Reason: conflicting signals detected
```

## Out of Scope

- **Auto-fixing tests** - Triage only, not automatic updates
- **Historical analysis** - Uses current state only
- **CI/CD integration** - Terminal command only for MVP
- **Visual test triage UI** - Text output only
- **Machine learning model training** - Uses rule-based confidence scoring

## Dependencies

- Existing modular test runners (FlutterTestRunner, PytestRunner, JestRunner)
- Existing TDD state tracking
- Spec file parsing

## Risks

| Risk | Mitigation |
|------|------------|
| AI miscategorizes failures | Show reasoning and confidence scores, let user override |
| Large test suites slow to analyze | Limit to failing tests only |
| Complex test relationships | Start simple, iterate |
| Low confidence scores confuse users | Clear documentation and fallback to manual review |
| Progressive disclosure adds complexity | Start with simple expand/collapse, iterate based on usage |

## Success Metrics

- Developers correctly identify regression vs outdated in <30 seconds
- Reduces time spent investigating test failures by 50%
- Accurate categorization in 80%+ of cases
- Confidence scores correlate with actual accuracy (high confidence = >90% accuracy)
- Users trust and act on high-confidence recommendations
- Summary view provides sufficient information for 70% of decisions without expansion

## Usage Guide: New Feature Implementation Scenario

### Scenario: Implementing a Feature with Existing Tests

You're implementing spec 003 (Browser Module) in a project with 50 existing tests. After implementation, some tests fail.

#### Step 1: Complete Implementation
```bash
# Try to complete the spec
speky complete 003
```

**Output:**
```
❌ Cannot complete: Regression tests failing

Regression failures: 3

🔴 2 likely regression(s) - fix implementation
🟡 1 likely outdated test(s) - update tests

Run 'speky test triage 003' for detailed analysis
```

#### Step 2: Run Triage Analysis
```bash
speky test triage 003
```

**Output:**
```
============================================================
  TEST FAILURE TRIAGE - Spec 003
  3 failing tests analyzed
============================================================

🔴 LIKELY REGRESSIONS (2) - Fix Implementation
--------------------------------------------------
  ●●● test_tab_close_saves_state
      File: test/browser/tab_management_test.dart
      Reason: Test covers files you modified: tab_manager.dart
      Modified: lib/browser/tab_manager.dart
      → Review your changes - you may have broken existing behavior

  ●●○ test_browser_state_persistence
      File: test/browser/state_test.dart
      Reason: Test covers files you modified: browser_service.dart
      → Review your changes to these files

🟡 LIKELY OUTDATED (1) - Update Tests
--------------------------------------------------
  ●●● test_max_tabs_is_10
      File: test/browser/tab_limits_test.dart
      Reason: Spec appears to change behavior: "Support up to 20 tabs"
      Spec: ...spec mentions changing behavior: 'max tabs increased to 20'...
      → Update test to match new spec requirements

============================================================
  SUMMARY
============================================================
  🔴 Regressions (fix code):     2
  🟡 Outdated (update tests):    1
  📝 TDD Expected:               0
  ⚪ Flaky:                      0
  ❓ Uncertain:                  0

  📋 SUGGESTED ACTIONS:
     1. Fix 2 regression(s) in your implementation
     2. Update 1 outdated test(s) to match new spec
```

#### Step 3: Take Action Based on Triage

**For Regressions (🔴):**
1. Review the modified files mentioned
2. Check if your changes broke existing behavior
3. Fix the implementation to preserve existing functionality

```bash
# Fix the code in lib/browser/tab_manager.dart
# Ensure tab state is saved before close
```

**For Outdated Tests (🟡):**
1. Review the spec changes mentioned
2. Update test expectations to match new requirements

```bash
# Update test/browser/tab_limits_test.dart
# Change: expect(maxTabs, 10) → expect(maxTabs, 20)
```

#### Step 4: Re-run Tests
```bash
# Run tests again to verify fixes
speky test run --spec 003
```

#### Step 5: Complete the Spec
```bash
# Try completion again
speky complete 003
```

**Output:**
```
✅ All TDD and regression tests passing
Spec 003 marked as complete
```

### When to Use Triage

**✅ Use triage when:**
- `speky complete` fails due to test failures
- Regression tests fail after implementing a feature
- You're unsure if a failure is your bug or an outdated test
- You have multiple test failures and need to prioritize

**❌ Don't use triage when:**
- TDD RED phase (tests SHOULD fail - that's expected)
- All tests are passing
- You haven't implemented anything yet

### Understanding Confidence Levels

| Confidence | Icon | Meaning | Action |
|------------|------|---------|--------|
| **High (≥70%)** | ●●● | Strong evidence | Trust the categorization |
| **Medium (40-69%)** | ●●○ | Moderate evidence | Review reasoning carefully |
| **Low (<40%)** | ●○○ | Uncertain | Manual investigation needed |

### Integration with TDD Workflow

If you're using TDD (`speky implement <id> --tdd`):

```bash
# 1. Start TDD
speky implement 003 --tdd

# 2. Create tests
# (IDE creates test files)

# 3. RED phase - tests should fail
speky test tdd-red 003
# ✅ Expected: Tests failing (good!)

# 4. Implement feature
# (IDE implements code)

# 5. GREEN phase - tests should pass
speky test tdd-green 003
# ❌ If this fails, use triage:
speky test triage 003

# 6. Complete with regression tests
speky complete 003
# ❌ If regression tests fail, triage shows:
#     📝 TDD Expected: 0 (your TDD tests passed)
#     🔴 Regressions: 2 (you broke existing tests)
```

### Common Triage Scenarios

**Scenario A: All Regressions**
```
🔴 Regressions: 5
🟡 Outdated: 0
```
**Action:** Your implementation broke existing functionality. Review and fix your code.

**Scenario B: All Outdated**
```
🔴 Regressions: 0
🟡 Outdated: 4
```
**Action:** Spec changed requirements. Update tests to match new behavior.

**Scenario C: Mixed**
```
🔴 Regressions: 2
🟡 Outdated: 3
```
**Action:** Fix regressions first (bugs), then update outdated tests.

**Scenario D: Uncertain**
```
❓ Uncertain: 3
```
**Action:** Manual investigation needed. Review test code and error messages.

### Tips for Best Results

1. **Commit frequently** - Triage uses git history to detect modified files
2. **Keep specs updated** - Triage compares test expectations with spec requirements
3. **Link TDD tests** - Use `speky test link <file> --spec <id>` for accurate categorization
4. **Trust high confidence** - High confidence (●●●) categorizations are usually correct
5. **Investigate uncertain** - Low confidence means conflicting signals - review manually

## Resolved Questions (Pre-Planning)
- **What is the exact data schema and API contract for accessing TDD state tracking system?** → This will differ from Project to Project and the system must adopt with that. In any Case the Actual Deep Work need to be offloaded to the AI IDE/ AI Coding Agent we need to prepare sufficient Context / Task for it to do its work properly.
- **What are the specific file path patterns and naming conventions for spec files across different project types?** → SPEKY already has a Spec Creation and naming mechanism, same should be used.
- **What is the exact command interface and data format for existing test runner modules?** → This differs from Project to Project and enough Context should be create for AI Coding Agent / AI IDE to be able to do the deep work.
- **How should the system handle mixed confidence signals that contradict each other?** → This Deep Work of fiat to be done with the confidence scoring  enough Context should be create for AI Coding Agent / AI IDE to be able to do the dee
- **What are the specific git command error scenarios and how should they be handled?** → Enumerate specific git command failure scenarios, define graceful degradation strategies (e.g., skip git history analysis), and specify user-facing error messages for each case.


## Implementation Notes

- ## TDD State Management

- **TDD Workflow States**: Tracks test development lifecycle through `TDDState` enum including `RED_CONFIRMED` (failing test written), `GREEN_PASSED` (implementation complete), and `REGRESSION_PASSED` (regression resolved)
- **State Transitions**: Manages progression from red → green → refactor phases with automatic state detection and manual override capabilities
- **Workflow Integration**: Provides TDD-aware test execution and failure analysis beyond basic triage functionality
