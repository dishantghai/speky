#!/usr/bin/env python3
"""
SPEKY Testing Integration Module

A standalone testing capability module for SPEKY that can be:
1. Used independently for testing operations
2. Integrated with main speky.py via lazy import
3. Enabled/disabled via config without affecting core SPEKY

Design Principles:
- Zero coupling with core speky.py (can run standalone)
- Feature-flagged (disabled by default until stable)
- Follows SPEKY's thin orchestration philosophy
- Delegates actual test implementation to IDE/coding agents

Commands (when integrated):
    speky test init                    - Initialize test harness
    speky test gen <spec-id>           - Generate test task for IDE
    speky test run [options]           - Execute tests
    speky test coverage                - Show coverage report
    speky test status                  - Show test health dashboard
    speky test e2e [options]           - Run E2E tests
    speky test link <test> <spec>      - Link test to spec
    speky test gaps                    - Show untested acceptance criteria

Standalone Usage:
    python speky_testing.py init
    python speky_testing.py gen 003
    python speky_testing.py run --spec 003
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Any, TYPE_CHECKING

# Conditional import for type hints only (avoids circular dependency)
if TYPE_CHECKING:
    from speky import SPEKY

# =============================================================================
# CONFIGURATION
# =============================================================================

TESTING_DIR = "testing"
TESTING_CONFIG_FILE = "config.yaml"
COVERAGE_DIR = "coverage"
SPECS_DIR = "specs"
TASKS_DIR = "tasks"
SEEDS_DIR = "seeds"
MOCKS_DIR = "mocks"
CACHE_DIR = "cache"
IDE_CONTEXT_FILE = "ide_context.md"

# Cache TTL in days (2 months)
SETUP_GUIDE_CACHE_TTL_DAYS = 60

DEFAULT_TESTING_CONFIG = {
    "enabled": False,  # Disabled by default until stable
    "version": "0.1.0",
    "coverage_threshold": 80,
    "frameworks": {
        "flutter": {
            "unit": "flutter_test",
            "widget": "flutter_test",
            "integration": "patrol",
            "coverage_tool": "lcov",
        },
        "python": {
            "unit": "pytest",
            "integration": "pytest",
            "coverage_tool": "pytest-cov",
        },
        "web": {
            "unit": "vitest",
            "e2e": "playwright",
            "coverage_tool": "c8",
        },
    },
    "e2e": {
        "web": {
            "framework": "playwright",
            "mcp_enabled": True,
            "headless": True,
        },
        "mobile": {
            "framework": "patrol",
            "enabled": False,  # Phase 5
        },
    },
    "data_strategy": "hybrid",  # factories, fixtures, snapshots, hybrid
}


# =============================================================================
# ENUMS
# =============================================================================

class TestType(Enum):
    UNIT = "unit"
    WIDGET = "widget"
    INTEGRATION = "integration"
    E2E = "e2e"
    ALL = "all"


class TestStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    FLAKY = "flaky"
    NOT_RUN = "not_run"


class CoverageLevel(Enum):
    EXCELLENT = "excellent"  # >= 90%
    GOOD = "good"            # >= 80%
    FAIR = "fair"            # >= 60%
    POOR = "poor"            # < 60%
    NONE = "none"            # 0%


class TDDState(Enum):
    """TDD workflow states"""
    NOT_STARTED = "not_started"
    TESTS_GENERATED = "tests_generated"
    RED_CONFIRMED = "red_confirmed"      # Tests created, verified they fail
    IMPLEMENTING = "implementing"         # Implementation in progress
    GREEN_PASSED = "green_passed"         # All TDD tests pass
    REGRESSION_PASSED = "regression_passed"  # All tests pass including regression


class TriageCategory(Enum):
    """Test failure triage categories"""
    REGRESSION = "regression"        # Fix implementation - test covers existing behavior
    OUTDATED = "outdated"            # Update test - spec changed, test expectations stale
    FLAKY = "flaky"                  # Investigate - timing/environment issue
    TDD_EXPECTED = "tdd_expected"    # Expected - TDD test should fail until implemented
    UNCERTAIN = "uncertain"          # Manual review needed


# =============================================================================
# TEST RESULT DATA CLASSES
# =============================================================================

class TestResult:
    """Standardized test result across all tech stacks"""
    def __init__(self, passed: bool = False, total: int = 0, failed: int = 0,
                 skipped: int = 0, output: str = "", duration_seconds: float = 0):
        self.passed = passed
        self.total = total
        self.failed = failed
        self.skipped = skipped
        self.output = output
        self.duration_seconds = duration_seconds
        self.test_details = []  # List of individual test results
    
    @property
    def passed_count(self) -> int:
        return self.total - self.failed - self.skipped
    
    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total": self.total,
            "failed": self.failed,
            "skipped": self.skipped,
            "passed_count": self.passed_count,
            "duration_seconds": self.duration_seconds,
            "summary": f"{self.passed_count}/{self.total} passed" if self.total > 0 else "No tests",
        }


class TriageResult:
    """Result of triaging a single failing test"""
    def __init__(self, test_name: str, test_file: str, category: TriageCategory,
                 confidence: float, reason: str, suggested_action: str,
                 related_files: List[str] = None, spec_context: str = None):
        self.test_name = test_name
        self.test_file = test_file
        self.category = category
        self.confidence = confidence  # 0.0 to 1.0
        self.reason = reason
        self.suggested_action = suggested_action
        self.related_files = related_files or []
        self.spec_context = spec_context  # Relevant spec text if applicable
    
    def to_dict(self) -> dict:
        return {
            "test_name": self.test_name,
            "test_file": self.test_file,
            "category": self.category.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
            "related_files": self.related_files,
            "spec_context": self.spec_context,
        }
    
    @property
    def confidence_level(self) -> str:
        """Return human-readable confidence level"""
        if self.confidence >= 0.7:
            return "high"
        elif self.confidence >= 0.4:
            return "medium"
        return "low"


class TriageSummary:
    """Summary of all triaged test failures"""
    def __init__(self, spec_id: str):
        self.spec_id = spec_id
        self.results: List[TriageResult] = []
        self.timestamp = datetime.now().isoformat()
    
    def add_result(self, result: TriageResult):
        self.results.append(result)
    
    @property
    def regressions(self) -> List[TriageResult]:
        return [r for r in self.results if r.category == TriageCategory.REGRESSION]
    
    @property
    def outdated(self) -> List[TriageResult]:
        return [r for r in self.results if r.category == TriageCategory.OUTDATED]
    
    @property
    def flaky(self) -> List[TriageResult]:
        return [r for r in self.results if r.category == TriageCategory.FLAKY]
    
    @property
    def tdd_expected(self) -> List[TriageResult]:
        return [r for r in self.results if r.category == TriageCategory.TDD_EXPECTED]
    
    @property
    def uncertain(self) -> List[TriageResult]:
        return [r for r in self.results if r.category == TriageCategory.UNCERTAIN]
    
    def to_dict(self) -> dict:
        return {
            "spec_id": self.spec_id,
            "timestamp": self.timestamp,
            "total_failures": len(self.results),
            "by_category": {
                "regressions": len(self.regressions),
                "outdated": len(self.outdated),
                "flaky": len(self.flaky),
                "tdd_expected": len(self.tdd_expected),
                "uncertain": len(self.uncertain),
            },
            "results": [r.to_dict() for r in self.results],
        }


# =============================================================================
# MODULAR TEST RUNNER ARCHITECTURE
# =============================================================================

from abc import ABC, abstractmethod

class BaseTestRunner(ABC):
    """Abstract base class for tech-specific test runners.
    
    Implement this class to add support for new tech stacks.
    Each runner handles detection, test execution, and coverage parsing.
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.name = "base"
    
    @abstractmethod
    def detect(self) -> bool:
        """Detect if this runner applies to the project."""
        pass
    
    @abstractmethod
    def get_test_command(self, test_files: List[str] = None, 
                         with_coverage: bool = False) -> List[str]:
        """Get the command to run tests."""
        pass
    
    @abstractmethod
    def get_test_directory(self) -> Path:
        """Get the directory containing tests."""
        pass
    
    @abstractmethod
    def parse_output(self, output: str, return_code: int) -> TestResult:
        """Parse test output into standardized TestResult."""
        pass
    
    def run_tests(self, test_files: List[str] = None, 
                  with_coverage: bool = False,
                  timeout: int = 300) -> TestResult:
        """Run tests and return results."""
        cmd = self.get_test_command(test_files, with_coverage)
        cwd = self.get_test_directory().parent
        
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return self.parse_output(result.stdout + result.stderr, result.returncode)
        except subprocess.TimeoutExpired:
            return TestResult(passed=False, output="Tests timed out")
        except FileNotFoundError as e:
            return TestResult(passed=False, output=f"Command not found: {e}")
        except Exception as e:
            return TestResult(passed=False, output=str(e))


class FlutterTestRunner(BaseTestRunner):
    """Flutter test runner using flutter test."""
    
    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.name = "flutter"
        self._flutter_root = None
    
    def detect(self) -> bool:
        """Detect Flutter project."""
        for path in [self.project_root, self.project_root / "frontend"]:
            if (path / "pubspec.yaml").exists():
                self._flutter_root = path
                return True
        return False
    
    def get_test_directory(self) -> Path:
        if not self._flutter_root:
            self.detect()
        return self._flutter_root / "test" if self._flutter_root else self.project_root / "test"
    
    def get_test_command(self, test_files: List[str] = None,
                         with_coverage: bool = False) -> List[str]:
        cmd = ["flutter", "test", "--reporter=expanded"]
        if with_coverage:
            cmd.append("--coverage")
        if test_files:
            # If flutter_root is a subdirectory (e.g., frontend/), strip that prefix from test paths
            # to avoid path doubling (frontend/frontend/test/...)
            if self._flutter_root and self._flutter_root != self.project_root:
                flutter_root_str = str(self._flutter_root.relative_to(self.project_root))
                adjusted_files = []
                for f in test_files:
                    if f.startswith(flutter_root_str + "/"):
                        # Strip the flutter_root prefix
                        adjusted_files.append(f[len(flutter_root_str) + 1:])
                    else:
                        adjusted_files.append(f)
                cmd.extend(adjusted_files)
            else:
                cmd.extend(test_files)
        return cmd
    
    def parse_output(self, output: str, return_code: int) -> TestResult:
        """Parse flutter test output."""
        result = TestResult(passed=(return_code == 0), output=output)
        
        # Clean up carriage returns that mess up parsing
        clean_output = output.replace('\r', '\n')
        
        # Parse test counts from output like "00:10 +44 -2: Some tests failed."
        # Use findall to get ALL matches, then take the LAST one (final count)
        import re
        matches = re.findall(r'\+(\d+)(?:\s+-(\d+))?:', clean_output)
        if matches:
            # Take the last match (final test count)
            last_match = matches[-1]
            passed_count = int(last_match[0])
            failed_count = int(last_match[1]) if last_match[1] else 0
            result.total = passed_count + failed_count
            result.failed = failed_count
        
        return result


class PytestRunner(BaseTestRunner):
    """Python test runner using pytest."""
    
    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.name = "pytest"
        self._python_root = None
    
    def detect(self) -> bool:
        """Detect Python project with pytest."""
        for path in [self.project_root, self.project_root / "backend"]:
            if (path / "requirements.txt").exists() or (path / "pytest.ini").exists() or (path / "pyproject.toml").exists():
                self._python_root = path
                return True
        return False
    
    def get_test_directory(self) -> Path:
        if not self._python_root:
            self.detect()
        return self._python_root / "tests" if self._python_root else self.project_root / "tests"
    
    def get_test_command(self, test_files: List[str] = None,
                         with_coverage: bool = False) -> List[str]:
        cmd = ["pytest", "-v"]
        if with_coverage:
            cmd.extend(["--cov=.", "--cov-report=term"])
        if test_files:
            cmd.extend(test_files)
        return cmd
    
    def parse_output(self, output: str, return_code: int) -> TestResult:
        """Parse pytest output."""
        result = TestResult(passed=(return_code == 0), output=output)
        
        # Parse test counts from output like "5 passed, 2 failed"
        import re
        passed_match = re.search(r'(\d+) passed', output)
        failed_match = re.search(r'(\d+) failed', output)
        skipped_match = re.search(r'(\d+) skipped', output)
        
        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        skipped = int(skipped_match.group(1)) if skipped_match else 0
        
        result.total = passed + failed + skipped
        result.failed = failed
        result.skipped = skipped
        
        return result


class JestRunner(BaseTestRunner):
    """JavaScript/TypeScript test runner using Jest/npm test."""
    
    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.name = "jest"
        self._node_root = None
    
    def detect(self) -> bool:
        """Detect Node.js project."""
        for path in [self.project_root, self.project_root / "frontend", self.project_root / "web"]:
            if (path / "package.json").exists():
                self._node_root = path
                return True
        return False
    
    def get_test_directory(self) -> Path:
        if not self._node_root:
            self.detect()
        return self._node_root / "__tests__" if self._node_root else self.project_root / "__tests__"
    
    def get_test_command(self, test_files: List[str] = None,
                         with_coverage: bool = False) -> List[str]:
        cmd = ["npm", "test", "--"]
        if with_coverage:
            cmd.append("--coverage")
        if test_files:
            cmd.extend(test_files)
        return cmd
    
    def parse_output(self, output: str, return_code: int) -> TestResult:
        """Parse Jest output."""
        result = TestResult(passed=(return_code == 0), output=output)
        
        # Parse test counts from Jest output
        import re
        match = re.search(r'Tests:\s+(\d+)\s+passed(?:,\s+(\d+)\s+failed)?', output)
        if match:
            passed = int(match.group(1))
            failed = int(match.group(2)) if match.group(2) else 0
            result.total = passed + failed
            result.failed = failed
        
        return result


# Test Runner Registry
TEST_RUNNERS = [FlutterTestRunner, PytestRunner, JestRunner]


def get_available_runners(project_root: Path) -> List[BaseTestRunner]:
    """Get all test runners that apply to this project."""
    runners = []
    for runner_class in TEST_RUNNERS:
        runner = runner_class(project_root)
        if runner.detect():
            runners.append(runner)
    return runners


# =============================================================================
# CONSOLE OUTPUT (Standalone - mirrors speky.py Console)
# =============================================================================

class TestConsole:
    """Console output utilities for testing module"""
    
    @staticmethod
    def info(msg: str):
        print(f"ℹ️  {msg}")
    
    @staticmethod
    def success(msg: str):
        print(f"✅ {msg}")
    
    @staticmethod
    def warning(msg: str):
        print(f"⚠️  {msg}")
    
    @staticmethod
    def error(msg: str):
        print(f"❌ {msg}")
    
    @staticmethod
    def step(msg: str):
        print(f"→ {msg}")
    
    @staticmethod
    def header(msg: str):
        print(f"\n{'='*60}")
        print(f"  {msg}")
        print(f"{'='*60}\n")
    
    @staticmethod
    def subheader(msg: str):
        print(f"\n{msg}")
        print(f"{'-'*len(msg)}")


# =============================================================================
# TEST PROMPTS (AI task generation)
# =============================================================================

class TestPrompts:
    """Prompt templates for test generation tasks"""
    
    @staticmethod
    def generate_test_task(
        spec_content: str,
        acceptance_criteria: List[str],
        tech_stack: dict,
        existing_tests: List[str],
        coverage_gaps: List[str]
    ) -> str:
        """Generate a test task for IDE/agent to implement"""
        
        ac_list = "\n".join([f"{i+1}. {ac}" for i, ac in enumerate(acceptance_criteria)])
        existing = "\n".join([f"- {t}" for t in existing_tests]) if existing_tests else "None"
        gaps = "\n".join([f"- {g}" for g in coverage_gaps]) if coverage_gaps else "None"
        
        tech_info = json.dumps(tech_stack, indent=2) if tech_stack else "Not specified"
        
        return f"""# Test Generation Task

## Spec Context

{spec_content}

## Acceptance Criteria to Cover

{ac_list}

## Tech Stack

```json
{tech_info}
```

## Existing Tests

{existing}

## Coverage Gaps

{gaps}

## Test Requirements

### Unit Tests
For each acceptance criterion, create unit tests that:
- Test the happy path
- Test edge cases
- Test error handling
- Use appropriate mocking

### Integration Tests (if applicable)
- Test component interactions
- Test data flow
- Test state management

### E2E Tests (if applicable)
- Test user flows end-to-end
- Test critical paths
- Use realistic test data

## Guidelines

1. Follow existing test patterns in the codebase
2. Use the project's testing frameworks
3. Ensure tests are deterministic (no flaky tests)
4. Add appropriate setup/teardown
5. Use descriptive test names
6. Group related tests logically

## Output

Create test files in the appropriate test directories following project conventions.
Report back which acceptance criteria are now covered.
"""

    @staticmethod
    def generate_e2e_task(
        spec_content: str,
        user_flows: List[str],
        platform: str,
        mock_config: dict
    ) -> str:
        """Generate E2E test task with MCP/Playwright instructions"""
        
        flows = "\n".join([f"### Flow {i+1}: {f}" for i, f in enumerate(user_flows)])
        mock_info = json.dumps(mock_config, indent=2) if mock_config else "{}"
        
        return f"""# E2E Test Generation Task

## Platform: {platform}

## Spec Context

{spec_content}

## User Flows to Test

{flows}

## Mock Configuration

```json
{mock_info}
```

## Instructions

{"Use Playwright MCP for browser automation." if platform == "web" else "Use Patrol for Flutter E2E testing."}

For each user flow:
1. Set up test data/mocks
2. Navigate to starting point
3. Execute user actions
4. Assert expected outcomes
5. Capture screenshots at key points
6. Clean up after test

## Guidelines

- Tests should be independent (can run in any order)
- Use stable selectors (data-testid, accessibility labels)
- Add appropriate waits for async operations
- Handle loading states gracefully
- Record video for debugging (optional)

## Output

Create E2E test files in the integration test directory.
"""


# =============================================================================
# TESTING INTEGRATION CLASS
# =============================================================================

class TestingIntegration:
    """
    SPEKY Testing Integration Module
    
    Can be used:
    1. Standalone: python speky_testing.py <command>
    2. Integrated: Loaded by main speky.py via lazy import
    
    All testing state is stored in .speky/testing/
    """
    
    def __init__(self, speky_instance: 'SPEKY' = None):
        """
        Initialize testing integration.
        
        Args:
            speky_instance: Optional SPEKY instance for integrated mode.
                           If None, runs in standalone mode.
        """
        self.speky = speky_instance
        self.standalone = speky_instance is None
        
        # Determine project root
        if self.speky:
            self.project_root = self.speky.project_root
        else:
            self.project_root = Path.cwd()
        
        # Set up paths
        self.speky_dir = self.project_root / ".speky"
        self.testing_dir = self.speky_dir / TESTING_DIR
        self.config_file = self.testing_dir / TESTING_CONFIG_FILE
        self.coverage_dir = self.testing_dir / COVERAGE_DIR
        self.specs_dir = self.testing_dir / SPECS_DIR
        self.tasks_dir = self.testing_dir / TASKS_DIR
        self.seeds_dir = self.testing_dir / SEEDS_DIR
        self.mocks_dir = self.testing_dir / MOCKS_DIR
        
        # Load config
        self.config = self._load_config()
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    def _load_config(self) -> dict:
        """Load testing configuration"""
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    # Simple YAML-like parsing (key: value)
                    config = {}
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and ":" in line:
                            key, value = line.split(":", 1)
                            key = key.strip()
                            value = value.strip()
                            # Parse booleans and numbers
                            if value.lower() == "true":
                                value = True
                            elif value.lower() == "false":
                                value = False
                            elif value.isdigit():
                                value = int(value)
                            config[key] = value
                    return {**DEFAULT_TESTING_CONFIG, **config}
            except Exception:
                pass
        return DEFAULT_TESTING_CONFIG.copy()
    
    def _save_config(self, config: dict):
        """Save testing configuration"""
        self.testing_dir.mkdir(parents=True, exist_ok=True)
        
        lines = [
            "# SPEKY Testing Configuration\n",
            "# Generated by speky test init\n",
            "\n",
        ]
        
        def write_dict(d: dict, prefix: str = ""):
            for key, value in d.items():
                if isinstance(value, dict):
                    lines.append(f"\n# {key}\n")
                    write_dict(value, f"{prefix}{key}.")
                else:
                    lines.append(f"{prefix}{key}: {value}\n")
        
        write_dict(config)
        
        with open(self.config_file, 'w') as f:
            f.writelines(lines)
    
    def is_enabled(self) -> bool:
        """Check if testing integration is enabled"""
        return self.config.get("enabled", False)
    
    def is_initialized(self) -> bool:
        """Check if testing harness is initialized"""
        return self.testing_dir.exists() and self.config_file.exists()
    
    # =========================================================================
    # COMMAND INTERFACE (for integration with main speky.py)
    # =========================================================================
    
    def get_commands(self) -> Dict[str, callable]:
        """
        Return commands to register with main CLI.
        Called by speky.py during CLI setup.
        """
        return {
            "test": self.cmd_test,
        }
    
    def get_subcommands(self) -> List[dict]:
        """
        Return subcommand definitions for argparse.
        Called by speky.py during CLI setup.
        """
        return [
            {
                "name": "test",
                "help": "Testing commands (init, gen, run, coverage, status, e2e, link, gaps)",
                "arguments": [
                    {
                        "name": "action",
                        "choices": ["init", "gen", "run", "coverage", "status", "e2e", "link", "gaps"],
                        "help": "Testing action to perform",
                    },
                    {
                        "name": "target",
                        "nargs": "?",
                        "help": "Target spec ID, test file, or other argument",
                    },
                    {
                        "name": "--type",
                        "dest": "test_type",
                        "choices": ["unit", "widget", "integration", "e2e", "all"],
                        "default": "all",
                        "help": "Type of tests to run/generate",
                    },
                    {
                        "name": "--spec",
                        "dest": "spec_id",
                        "help": "Filter by spec ID",
                    },
                    {
                        "name": "--affected",
                        "action": "store_true",
                        "help": "Run only tests affected by recent changes",
                    },
                    {
                        "name": "--failed",
                        "action": "store_true",
                        "help": "Re-run previously failed tests",
                    },
                    {
                        "name": "--coverage",
                        "action": "store_true",
                        "help": "Run with coverage reporting",
                    },
                    {
                        "name": "--platform",
                        "choices": ["web", "mobile", "all"],
                        "default": "all",
                        "help": "Platform for E2E tests",
                    },
                    {
                        "name": "--headed",
                        "action": "store_true",
                        "help": "Run E2E tests with visible browser",
                    },
                ],
            },
        ]
    
    # =========================================================================
    # MAIN COMMAND ROUTER
    # =========================================================================
    
    def cmd_test(self, args) -> bool:
        """Main test command router"""
        action = getattr(args, 'action', None)
        
        if action == "init":
            return self.cmd_test_init(args)
        elif action == "gen":
            return self.cmd_test_gen(args)
        elif action == "run":
            return self.cmd_test_run(args)
        elif action == "coverage":
            return self.cmd_test_coverage(args)
        elif action == "status":
            return self.cmd_test_status(args)
        elif action == "e2e":
            return self.cmd_test_e2e(args)
        elif action == "link":
            return self.cmd_test_link(args)
        elif action == "gaps":
            return self.cmd_test_gaps(args)
        else:
            TestConsole.error(f"Unknown test action: {action}")
            return False
    
    # =========================================================================
    # COMMAND IMPLEMENTATIONS
    # =========================================================================
    
    def cmd_test_init(self, args=None) -> bool:
        """Initialize test harness for project"""
        TestConsole.header("Initializing Test Harness")
        
        # Check for --e2e flag
        scaffold_e2e = getattr(args, 'e2e', False) if args else False
        
        # Check if SPEKY is initialized
        if not self.speky_dir.exists():
            TestConsole.error("SPEKY not initialized. Run 'speky init' first.")
            return False
        
        # Detect tech stack
        tech_stack = self._detect_tech_stack()
        TestConsole.info(f"Detected tech stack: {json.dumps(tech_stack, indent=2)}")
        
        # Create directory structure
        TestConsole.step("Creating test directories...")
        self.testing_dir.mkdir(exist_ok=True)
        self.coverage_dir.mkdir(exist_ok=True)
        self.specs_dir.mkdir(exist_ok=True)
        self.tasks_dir.mkdir(exist_ok=True)
        (self.tasks_dir / "active").mkdir(exist_ok=True)
        (self.tasks_dir / "completed").mkdir(exist_ok=True)
        self.seeds_dir.mkdir(exist_ok=True)
        self.mocks_dir.mkdir(exist_ok=True)
        
        # Scaffold E2E infrastructure if requested or if Flutter detected
        if scaffold_e2e or tech_stack.get("flutter"):
            self._scaffold_e2e_infrastructure(tech_stack)
        
        # Generate config based on detected tech stack
        config = DEFAULT_TESTING_CONFIG.copy()
        config["enabled"] = True
        config["detected_tech_stack"] = tech_stack
        
        # Save config
        self._save_config(config)
        self.config = config
        
        # Create initial coverage tracking file
        coverage_file = self.coverage_dir / "coverage.yaml"
        if not coverage_file.exists():
            self._save_coverage_data({
                "overall": {"line_coverage": 0, "branch_coverage": 0},
                "by_spec": {},
                "last_updated": datetime.now().isoformat(),
            })
        
        # Generate comprehensive TESTING_GUIDE.md
        self._generate_testing_guide(tech_stack)
        
        TestConsole.success("Test harness initialized!")
        TestConsole.info(f"Config: {self.config_file}")
        TestConsole.info(f"Coverage: {self.coverage_dir}")
        TestConsole.info(f"Tasks: {self.tasks_dir}")
        TestConsole.info(f"Guide: {self.project_root / 'TESTING_GUIDE.md'}")
        
        print("\nNext steps:")
        print("  1. Run 'speky test gen <spec-id>' to generate tests for a spec")
        print("  2. Run 'speky test run' to execute tests")
        print("  3. Run 'speky test coverage' to see coverage report")
        print("")
        print("🧪 TDD Workflow (recommended for new features):")
        print("  1. Run 'speky implement <spec-id> --tdd' to start TDD")
        print("  2. Create tests based on generated task")
        print("  3. Run 'speky test tdd-red <spec-id>' to verify tests fail")
        print("  4. Implement the feature")
        print("  5. Run 'speky test tdd-green <spec-id>' to verify tests pass")
        print("  6. Run 'speky test tdd-status' to view TDD dashboard")
        
        return True
    
    def cmd_test_gen(self, args) -> bool:
        """Generate test task for IDE/agent"""
        target = getattr(args, 'target', None)
        test_type = getattr(args, 'test_type', 'all')
        
        if not target:
            TestConsole.error("Please specify a spec ID: speky test gen <spec-id>")
            return False
        
        if not self.is_initialized():
            TestConsole.error("Test harness not initialized. Run 'speky test init' first.")
            return False
        
        TestConsole.header(f"Generating Test Task for Spec {target}")
        
        # Load spec
        spec_content, acceptance_criteria = self._load_spec(target)
        if not spec_content:
            TestConsole.error(f"Spec {target} not found")
            return False
        
        # Get tech stack
        tech_stack = self.config.get("detected_tech_stack", {})
        
        # Find existing tests
        existing_tests = self._find_existing_tests(target)
        
        # Identify coverage gaps
        coverage_gaps = self._identify_coverage_gaps(target, acceptance_criteria, existing_tests)
        
        # Generate task
        task_content = TestPrompts.generate_test_task(
            spec_content=spec_content,
            acceptance_criteria=acceptance_criteria,
            tech_stack=tech_stack,
            existing_tests=existing_tests,
            coverage_gaps=coverage_gaps,
        )
        
        # Save task file
        task_file = self.tasks_dir / "active" / f"test_task_{target}.md"
        with open(task_file, 'w') as f:
            f.write(task_content)
        
        # Update spec manifest
        self._update_spec_manifest(target, {
            "task_generated": datetime.now().isoformat(),
            "test_type": test_type,
            "status": "pending",
        })
        
        TestConsole.success(f"Test task generated: {task_file}")
        TestConsole.info("Hand off to IDE/agent to implement the tests.")
        
        return True
    
    def cmd_test_run(self, args) -> bool:
        """Execute tests using modular test runners"""
        spec_id = getattr(args, 'spec_id', None)
        test_type = getattr(args, 'test_type', 'all')
        affected = getattr(args, 'affected', False)
        failed = getattr(args, 'failed', False)
        with_coverage = getattr(args, 'coverage', False)
        
        if not self.is_initialized():
            TestConsole.error("Test harness not initialized. Run 'speky test init' first.")
            return False
        
        TestConsole.header("Running Tests")
        
        # Determine which tests to run
        if spec_id:
            TestConsole.info(f"Running tests for spec: {spec_id}")
        elif affected:
            TestConsole.info("Running affected tests...")
        elif failed:
            TestConsole.info("Re-running failed tests...")
        else:
            TestConsole.info("Running full test suite...")
        
        # Get all available test runners for this project
        runners = get_available_runners(self.project_root)
        
        if not runners:
            TestConsole.warning("No test runners detected.")
            print("\nSupported tech stacks:")
            print("  • Flutter (pubspec.yaml)")
            print("  • Python (requirements.txt, pytest.ini)")
            print("  • JavaScript/TypeScript (package.json)")
            print("\nRun 'speky test init' to set up testing.")
            return False
        
        # Run tests with each detected runner
        results = {}
        import sys
        
        for runner in runners:
            TestConsole.step(f"Running {runner.name.upper()} tests...")
            print(f"\n{'='*60}")
            print(f"{runner.name.upper()} Test Suite")
            print(f"{'='*60}\n")
            
            # Build command
            cmd = runner.get_test_command(with_coverage=with_coverage)
            cwd = runner.get_test_directory().parent
            
            try:
                # Run with real-time output streaming
                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    text=True,
                    timeout=600,
                )
                
                # Store result
                results[runner.name] = {
                    "passed": result.returncode == 0,
                    "summary": "All tests passed" if result.returncode == 0 else "Some tests failed",
                    "platform": runner.name.capitalize(),
                    "return_code": result.returncode,
                }
                
                # Parse coverage if requested
                if with_coverage:
                    coverage_pct = self._parse_coverage_for_runner(runner, cwd)
                    if coverage_pct is not None:
                        results[runner.name]["coverage"] = coverage_pct
                
            except subprocess.TimeoutExpired:
                results[runner.name] = {
                    "passed": False,
                    "summary": "Tests timed out (>10 min)",
                    "platform": runner.name.capitalize(),
                }
            except FileNotFoundError:
                results[runner.name] = {
                    "passed": False,
                    "summary": f"Command not found: {cmd[0]}",
                    "platform": runner.name.capitalize(),
                }
            except Exception as e:
                results[runner.name] = {
                    "passed": False,
                    "summary": str(e),
                    "platform": runner.name.capitalize(),
                }
        
        # Show results summary
        self._display_test_results(results)
        
        # Update coverage if requested
        if with_coverage:
            self._update_coverage_from_results(results)
        
        # Check if all passed
        all_passed = all(r.get("passed", False) for r in results.values())
        
        if all_passed:
            TestConsole.success("All tests passed!")
        else:
            TestConsole.error("Some tests failed. See details above.")
        
        return all_passed
    
    def cmd_test_coverage(self, args) -> bool:
        """Show coverage report"""
        spec_id = getattr(args, 'spec_id', None)
        
        if not self.is_initialized():
            TestConsole.error("Test harness not initialized. Run 'speky test init' first.")
            return False
        
        TestConsole.header("Test Coverage Report")
        
        coverage_data = self._load_coverage_data()
        
        # Overall coverage
        overall = coverage_data.get("overall", {})
        line_cov = overall.get("line_coverage", 0)
        threshold = self.config.get("coverage_threshold", 80)
        
        status = "✅" if line_cov >= threshold else "⚠️" if line_cov >= 60 else "❌"
        bar = self._coverage_bar(line_cov)
        
        print(f"\nOverall Coverage: {status} {line_cov:.1f}% {bar} (Target: {threshold}%)")
        
        # By spec
        by_spec = coverage_data.get("by_spec", {})
        if by_spec:
            print("\nBy Spec:")
            for sid, data in sorted(by_spec.items()):
                cov = data.get("coverage", 0)
                status = "✅" if cov >= threshold else "⚠️" if cov >= 60 else "❌"
                bar = self._coverage_bar(cov)
                print(f"  {status} {sid}: {cov:.1f}% {bar}")
        
        # Coverage gaps
        gaps = coverage_data.get("gaps", [])
        if gaps:
            print("\nCoverage Gaps (Top 5):")
            for i, gap in enumerate(gaps[:5], 1):
                print(f"  {i}. {gap.get('file', 'Unknown')}:{gap.get('lines', '?')}")
                print(f"     → {gap.get('description', 'Missing tests')}")
        
        return True
    
    def cmd_test_status(self, args) -> bool:
        """Show test health dashboard"""
        if not self.is_initialized():
            TestConsole.error("Test harness not initialized. Run 'speky test init' first.")
            return False
        
        TestConsole.header("Test Health Dashboard")
        
        coverage_data = self._load_coverage_data()
        
        # Test suite status (placeholder - would need actual test results)
        print("Test Suite Status")
        print("-" * 40)
        print("  (Run 'speky test run' to populate)")
        
        # Coverage summary
        overall = coverage_data.get("overall", {})
        line_cov = overall.get("line_coverage", 0)
        threshold = self.config.get("coverage_threshold", 80)
        
        print(f"\nCoverage Summary")
        print("-" * 40)
        print(f"  Overall: {line_cov:.1f}% (Target: {threshold}%)")
        
        # Untested specs
        untested = self._find_untested_specs()
        if untested:
            print(f"\nUntested Specs ({len(untested)})")
            print("-" * 40)
            for spec in untested[:5]:
                print(f"  • {spec}")
            if len(untested) > 5:
                print(f"  ... and {len(untested) - 5} more")
        
        return True
    
    def cmd_test_e2e(self, args) -> bool:
        """Run E2E tests"""
        platform = getattr(args, 'platform', 'all')
        spec_id = getattr(args, 'spec_id', None)
        headed = getattr(args, 'headed', False)
        
        if not self.is_initialized():
            TestConsole.error("Test harness not initialized. Run 'speky test init' first.")
            return False
        
        TestConsole.header(f"Running E2E Tests ({platform})")
        
        if platform in ["web", "all"]:
            TestConsole.step("Running web E2E tests (Playwright)...")
            # Placeholder - would invoke playwright
            TestConsole.info("Web E2E: Not yet implemented")
        
        if platform in ["mobile", "all"]:
            if not self.config.get("e2e", {}).get("mobile", {}).get("enabled", False):
                TestConsole.warning("Mobile E2E is disabled (Phase 5 feature)")
            else:
                TestConsole.step("Running mobile E2E tests (Patrol)...")
                TestConsole.info("Mobile E2E: Not yet implemented")
        
        return True
    
    def cmd_test_link(self, args) -> bool:
        """Link existing test to spec"""
        target = getattr(args, 'target', None)
        spec_id = getattr(args, 'spec_id', None)
        
        if not target or not spec_id:
            TestConsole.error("Usage: speky test link <test-file> --spec <spec-id>")
            return False
        
        TestConsole.info(f"Linking {target} to spec {spec_id}")
        
        # Update manifest
        self._update_spec_manifest(spec_id, {
            "linked_tests": [target],
            "linked_at": datetime.now().isoformat(),
        })
        
        TestConsole.success(f"Linked {target} to spec {spec_id}")
        return True
    
    def cmd_test_gaps(self, args) -> bool:
        """Show untested acceptance criteria"""
        spec_id = getattr(args, 'spec_id', None)
        
        if not self.is_initialized():
            TestConsole.error("Test harness not initialized. Run 'speky test init' first.")
            return False
        
        TestConsole.header("Untested Acceptance Criteria")
        
        # Get all specs or specific spec
        specs_to_check = [spec_id] if spec_id else self._get_all_spec_ids()
        
        total_gaps = 0
        for sid in specs_to_check:
            _, acceptance_criteria = self._load_spec(sid)
            existing_tests = self._find_existing_tests(sid)
            gaps = self._identify_coverage_gaps(sid, acceptance_criteria, existing_tests)
            
            if gaps:
                print(f"\nSpec {sid}:")
                for gap in gaps:
                    print(f"  ❌ {gap}")
                    total_gaps += 1
        
        if total_gaps == 0:
            TestConsole.success("All acceptance criteria have tests!")
        else:
            TestConsole.warning(f"Found {total_gaps} untested acceptance criteria")
            print("\nRun 'speky test gen <spec-id>' to generate tests")
        
        return True
    
    # =========================================================================
    # HELPER: Run tests for --test flag on speky complete
    # =========================================================================
    
    def run_tests_for_spec(self, spec_id: str, test_type: str = "all") -> dict:
        """
        Run tests for a specific spec.
        Called by speky.py cmd_complete when --test flag is used.
        
        Returns:
            dict with keys: passed (bool), summary (str), details (list)
        """
        if not self.is_initialized():
            return {
                "passed": False,
                "summary": "Test harness not initialized",
                "details": ["Run 'speky test init' first"],
            }
        
        # Check if spec has linked tests
        manifest = self._load_spec_manifest(spec_id)
        if not manifest.get("linked_tests") and not self._find_existing_tests(spec_id):
            return {
                "passed": False,
                "summary": f"No tests found for spec {spec_id}",
                "details": [f"Run 'speky test gen {spec_id}' to generate tests"],
            }
        
        # Run tests
        tech_stack = self.config.get("detected_tech_stack", {})
        results = {}
        
        if "flutter" in tech_stack:
            results["flutter"] = self._run_flutter_tests(spec_id=spec_id, test_type=test_type)
        
        if "python" in tech_stack:
            results["python"] = self._run_python_tests(spec_id=spec_id, test_type=test_type)
        
        # Aggregate results
        all_passed = all(r.get("passed", False) for r in results.values())
        total_tests = sum(r.get("total", 0) for r in results.values())
        failed_tests = sum(r.get("failed", 0) for r in results.values())
        
        return {
            "passed": all_passed,
            "summary": f"{total_tests - failed_tests}/{total_tests} tests passed",
            "details": [f"{k}: {v.get('summary', 'Unknown')}" for k, v in results.items()],
        }
    
    # =========================================================================
    # TDD WORKFLOW METHODS
    # =========================================================================
    
    def start_tdd_workflow(self, spec_id: str, spec_name: str = "") -> dict:
        """
        Start TDD workflow for a spec. Called by speky implement --tdd.
        
        Phase 1: Generate comprehensive test task for IDE.
        
        Returns:
            dict with keys: success, task_file, message, next_steps
        """
        TestConsole.header(f"TDD Workflow: Spec {spec_id}")
        
        if not self.is_initialized():
            return {
                "success": False,
                "message": "Test harness not initialized. Run 'speky test init' first.",
                "next_steps": ["Run: speky test init"],
            }
        
        # Load spec
        spec_content, acceptance_criteria = self._load_spec(spec_id)
        if not spec_content:
            return {
                "success": False,
                "message": f"Spec {spec_id} not found",
                "next_steps": [],
            }
        
        TestConsole.step("Phase 1: Generating comprehensive test task...")
        
        # Generate TDD test task
        tech_stack = self.config.get("detected_tech_stack", {})
        task_content = self._generate_tdd_test_task(
            spec_id=spec_id,
            spec_name=spec_name,
            spec_content=spec_content,
            acceptance_criteria=acceptance_criteria,
            tech_stack=tech_stack,
        )
        
        # Save task file
        task_dir = self.tasks_dir / f"T{spec_id}-tdd"
        task_dir.mkdir(parents=True, exist_ok=True)
        task_file = task_dir / "test_task.md"
        task_file.write_text(task_content)
        
        # Update TDD state in spec status
        self._update_tdd_state(spec_id, {
            "enabled": True,
            "state": TDDState.TESTS_GENERATED.value,
            "started_at": datetime.now().isoformat(),
            "tests": {
                "linked_files": [],
                "last_run": None,
                "last_result": None,
                "passed": 0,
                "failed": 0,
                "total": 0,
            },
        })
        
        TestConsole.success(f"TDD test task generated: {task_file}")
        
        return {
            "success": True,
            "task_file": str(task_file),
            "message": "TDD test task generated. Hand off to IDE to create tests.",
            "next_steps": [
                "1. Review test task and implement tests in IDE",
                "2. When tests are ready, run: speky test tdd-red <spec-id>",
                "3. Verify tests fail (RED phase)",
                "4. Then implement the feature",
            ],
        }
    
    def run_red_phase(self, spec_id: str) -> dict:
        """
        Run RED phase of TDD: Execute tests and verify they FAIL.
        
        In proper TDD, tests should fail before implementation.
        This confirms the tests are actually testing something.
        
        Returns:
            dict with keys: success, result, message, can_proceed
        """
        TestConsole.header(f"TDD RED Phase: Spec {spec_id}")
        
        # Check TDD state
        tdd_state = self._get_tdd_state(spec_id)
        if not tdd_state.get("enabled"):
            return {
                "success": False,
                "message": f"TDD not enabled for spec {spec_id}. Start with: speky implement {spec_id} --tdd",
                "can_proceed": False,
            }
        
        TestConsole.step("Running tests (expecting failures)...")
        
        # Run tests using modular runners
        runners = get_available_runners(self.project_root)
        if not runners:
            return {
                "success": False,
                "message": "No test runners detected for this project",
                "can_proceed": False,
            }
        
        # Get linked test files for this spec
        linked_files = tdd_state.get("tests", {}).get("linked_files", [])
        
        # Run tests
        all_results = []
        total_passed = 0
        total_failed = 0
        total_tests = 0
        
        for runner in runners:
            TestConsole.info(f"Running {runner.name} tests...")
            result = runner.run_tests(test_files=linked_files if linked_files else None)
            all_results.append((runner.name, result))
            total_passed += result.passed_count
            total_failed += result.failed
            total_tests += result.total
        
        # Update TDD state with results
        self._update_tdd_state(spec_id, {
            "tests": {
                **tdd_state.get("tests", {}),
                "last_run": datetime.now().isoformat(),
                "last_result": "failed" if total_failed > 0 else "passed",
                "passed": total_passed,
                "failed": total_failed,
                "total": total_tests,
            },
        })
        
        # Display results
        print("\n" + "="*50)
        print("RED PHASE RESULTS")
        print("="*50)
        
        for runner_name, result in all_results:
            status = "🔴" if result.failed > 0 else "🟢"
            print(f"\n{status} {runner_name.upper()}: {result.passed_count}/{result.total} passed, {result.failed} failed")
            if result.output and result.failed > 0:
                # Show first 500 chars of output
                print(f"   Output: {result.output[:500]}...")
        
        # Check if RED phase is valid (tests should FAIL)
        if total_failed > 0:
            TestConsole.success(f"✅ RED phase confirmed: {total_failed} tests failing (as expected)")
            
            # Update state to RED_CONFIRMED
            self._update_tdd_state(spec_id, {"state": TDDState.RED_CONFIRMED.value})
            
            return {
                "success": True,
                "result": {"passed": total_passed, "failed": total_failed, "total": total_tests},
                "message": f"RED phase complete. {total_failed} tests are failing as expected.",
                "can_proceed": True,
                "next_steps": [
                    "Tests are failing (good!). Now implement the feature.",
                    "After implementation, run: speky test tdd-green <spec-id>",
                ],
            }
        elif total_tests == 0:
            TestConsole.warning("⚠️ No tests found! Create tests first.")
            return {
                "success": False,
                "result": {"passed": 0, "failed": 0, "total": 0},
                "message": "No tests found. Create tests before RED phase.",
                "can_proceed": False,
            }
        else:
            TestConsole.warning("⚠️ All tests are passing! Tests should FAIL in RED phase.")
            return {
                "success": False,
                "result": {"passed": total_passed, "failed": 0, "total": total_tests},
                "message": "Tests are passing but should FAIL in RED phase. Check that tests actually test the unimplemented feature.",
                "can_proceed": False,
            }
    
    def run_green_phase(self, spec_id: str) -> dict:
        """
        Run GREEN phase of TDD: Execute tests and verify they PASS.
        
        After implementation, all TDD tests should pass.
        
        Returns:
            dict with keys: success, result, message, can_complete
        """
        TestConsole.header(f"TDD GREEN Phase: Spec {spec_id}")
        
        # Check TDD state
        tdd_state = self._get_tdd_state(spec_id)
        if not tdd_state.get("enabled"):
            return {
                "success": False,
                "message": f"TDD not enabled for spec {spec_id}",
                "can_complete": False,
            }
        
        TestConsole.step("Running tests (expecting all to pass)...")
        
        # Run tests
        runners = get_available_runners(self.project_root)
        linked_files = tdd_state.get("tests", {}).get("linked_files", [])
        
        all_results = []
        total_passed = 0
        total_failed = 0
        total_tests = 0
        
        for runner in runners:
            TestConsole.info(f"Running {runner.name} tests...")
            result = runner.run_tests(test_files=linked_files if linked_files else None)
            all_results.append((runner.name, result))
            total_passed += result.passed_count
            total_failed += result.failed
            total_tests += result.total
        
        # Update TDD state
        self._update_tdd_state(spec_id, {
            "tests": {
                **tdd_state.get("tests", {}),
                "last_run": datetime.now().isoformat(),
                "last_result": "passed" if total_failed == 0 else "failed",
                "passed": total_passed,
                "failed": total_failed,
                "total": total_tests,
            },
        })
        
        # Display results
        print("\n" + "="*50)
        print("GREEN PHASE RESULTS")
        print("="*50)
        
        for runner_name, result in all_results:
            status = "🟢" if result.failed == 0 else "🔴"
            print(f"\n{status} {runner_name.upper()}: {result.passed_count}/{result.total} passed, {result.failed} failed")
        
        # Check if GREEN phase passed
        if total_failed == 0 and total_tests > 0:
            TestConsole.success(f"✅ GREEN phase passed: {total_passed}/{total_tests} tests passing")
            
            # Update state to GREEN_PASSED
            self._update_tdd_state(spec_id, {"state": TDDState.GREEN_PASSED.value})
            
            return {
                "success": True,
                "result": {"passed": total_passed, "failed": 0, "total": total_tests},
                "message": f"GREEN phase complete. All {total_tests} tests passing!",
                "can_complete": True,
                "next_steps": [
                    "All TDD tests pass! Ready for completion.",
                    "Run: speky complete <spec-id> to complete with regression testing",
                ],
            }
        else:
            TestConsole.error(f"❌ GREEN phase failed: {total_failed} tests still failing")
            return {
                "success": False,
                "result": {"passed": total_passed, "failed": total_failed, "total": total_tests},
                "message": f"GREEN phase failed. {total_failed} tests still failing.",
                "can_complete": False,
                "next_steps": [
                    "Fix the implementation to make all tests pass.",
                    "Then run: speky test tdd-green <spec-id>",
                ],
            }
    
    def run_regression_tests(self, spec_id: str, scope: str = "all") -> dict:
        """
        Run regression tests to ensure no existing functionality was broken.
        
        Args:
            spec_id: The spec being completed
            scope: "all" | "affected" | "spec_related"
        
        Returns:
            dict with keys: success, result, message, regressions
        """
        TestConsole.header("Running Regression Tests")
        
        # Get config for regression scope
        config_scope = self.config.get("regression", {}).get("scope", "all")
        scope = scope or config_scope
        
        TestConsole.info(f"Regression scope: {scope}")
        
        # Run all tests
        runners = get_available_runners(self.project_root)
        
        all_results = []
        total_passed = 0
        total_failed = 0
        total_tests = 0
        
        for runner in runners:
            TestConsole.info(f"Running {runner.name} tests...")
            # Run ALL tests for regression check
            result = runner.run_tests()
            all_results.append((runner.name, result))
            total_passed += result.passed_count
            total_failed += result.failed
            total_tests += result.total
        
        # Display results
        print("\n" + "="*50)
        print("REGRESSION TEST RESULTS")
        print("="*50)
        
        for runner_name, result in all_results:
            status = "🟢" if result.failed == 0 else "🔴"
            print(f"\n{status} {runner_name.upper()}: {result.passed_count}/{result.total} passed")
        
        # Update TDD state if TDD was enabled
        tdd_state = self._get_tdd_state(spec_id)
        if tdd_state.get("enabled"):
            if total_failed == 0:
                self._update_tdd_state(spec_id, {"state": TDDState.REGRESSION_PASSED.value})
                self._update_tdd_state(spec_id, {
                    "regression": {
                        "last_run": datetime.now().isoformat(),
                        "passed": total_passed,
                        "failed": 0,
                        "total": total_tests,
                    },
                })
        
        if total_failed == 0:
            TestConsole.success(f"✅ No regressions: {total_passed}/{total_tests} tests passing")
            return {
                "success": True,
                "result": {"passed": total_passed, "failed": 0, "total": total_tests},
                "message": f"No regressions detected. All {total_tests} tests passing.",
                "regressions": [],
            }
        else:
            TestConsole.error(f"❌ Regressions detected: {total_failed} tests failing")
            return {
                "success": False,
                "result": {"passed": total_passed, "failed": total_failed, "total": total_tests},
                "message": f"Regressions detected! {total_failed} tests failing.",
                "regressions": [f"{total_failed} tests failed"],
            }
    
    def verify_completion(self, spec_id: str) -> dict:
        """
        Verify spec can be completed. Used by speky complete command.
        
        For TDD specs: Hard block if tests fail.
        For non-TDD specs: Warning with suggestions.
        
        Returns:
            dict with keys: can_complete, tdd_enabled, test_results, message, blockers
        """
        tdd_state = self._get_tdd_state(spec_id)
        tdd_enabled = tdd_state.get("enabled", False)
        
        result = {
            "can_complete": True,
            "tdd_enabled": tdd_enabled,
            "test_results": None,
            "message": "",
            "blockers": [],
        }
        
        if tdd_enabled:
            # TDD spec: Run green phase + regression
            TestConsole.header(f"TDD Completion Verification: Spec {spec_id}")
            
            # Run TDD tests (green phase)
            TestConsole.step("Running TDD tests...")
            green_result = self.run_green_phase(spec_id)
            
            if not green_result.get("success"):
                result["can_complete"] = False
                result["blockers"].append(f"TDD tests failing: {green_result.get('result', {}).get('failed', 0)} failures")
                result["message"] = "❌ Cannot complete: TDD tests are failing"
                result["test_results"] = green_result.get("result")
                
                # Add triage summary to help diagnose failures
                triage_summary = self._quick_triage_summary(spec_id)
                if triage_summary:
                    result["triage_summary"] = triage_summary.to_dict()
                    result["triage_hint"] = self._format_triage_hint(triage_summary)
                
                return result
            
            # Run regression tests
            TestConsole.step("Running regression tests...")
            regression_result = self.run_regression_tests(spec_id)
            
            if not regression_result.get("success"):
                result["can_complete"] = False
                result["blockers"].append(f"Regression failures: {regression_result.get('result', {}).get('failed', 0)}")
                result["message"] = "❌ Cannot complete: Regression tests failing"
                result["test_results"] = regression_result.get("result")
                
                # Add triage summary to help diagnose failures
                triage_summary = self._quick_triage_summary(spec_id)
                if triage_summary:
                    result["triage_summary"] = triage_summary.to_dict()
                    result["triage_hint"] = self._format_triage_hint(triage_summary)
                
                return result
            
            result["message"] = "✅ All TDD and regression tests passing"
            result["test_results"] = {
                "tdd": green_result.get("result"),
                "regression": regression_result.get("result"),
            }
        else:
            # Non-TDD spec: Check if tests exist, warn if not
            existing_tests = self._find_existing_tests(spec_id)
            
            if not existing_tests:
                result["message"] = "⚠️ No tests linked to this spec. Consider adding tests."
                result["blockers"] = []  # Non-blocking for non-TDD
            else:
                # Run existing tests
                test_result = self.run_tests_for_spec(spec_id)
                result["test_results"] = test_result
                
                if not test_result.get("passed"):
                    result["message"] = f"⚠️ Some tests failing: {test_result.get('summary')}"
                    # Non-blocking for non-TDD, but show warning
                else:
                    result["message"] = f"✅ Tests passing: {test_result.get('summary')}"
        
        return result
    
    def _quick_triage_summary(self, spec_id: str) -> Optional[TriageSummary]:
        """Generate a quick triage summary without re-running tests (uses cached output)"""
        try:
            # Get failures from most recent test run
            runners = get_available_runners(self.project_root)
            all_failures = []
            
            for runner in runners:
                # Run tests to get current state
                result = runner.run_tests()
                if result.failed > 0:
                    failures = self._extract_failing_tests(runner.name, result.output)
                    all_failures.extend(failures)
            
            if not all_failures:
                return None
            
            # Gather context
            spec_content = self._load_spec_content(spec_id)
            modified_files = self._get_modified_files_for_spec(spec_id)
            tdd_state = self._get_tdd_state(spec_id)
            tdd_test_files = tdd_state.get("tests", {}).get("linked_files", [])
            
            # Categorize failures
            summary = TriageSummary(spec_id)
            for failure in all_failures:
                result = self._categorize_test_failure(
                    failure=failure,
                    spec_content=spec_content,
                    modified_files=modified_files,
                    tdd_test_files=tdd_test_files,
                    tdd_enabled=tdd_state.get("enabled", False)
                )
                summary.add_result(result)
            
            return summary
        except Exception:
            return None
    
    def _format_triage_hint(self, summary: TriageSummary) -> str:
        """Format a brief triage hint for display in completion output"""
        hints = []
        
        if summary.regressions:
            hints.append(f"🔴 {len(summary.regressions)} likely regression(s) - fix implementation")
        if summary.outdated:
            hints.append(f"🟡 {len(summary.outdated)} likely outdated test(s) - update tests")
        if summary.tdd_expected:
            hints.append(f"📝 {len(summary.tdd_expected)} TDD test(s) - continue implementing")
        if summary.uncertain:
            hints.append(f"❓ {len(summary.uncertain)} uncertain - manual review needed")
        
        if hints:
            hints.append(f"\nRun 'speky test triage {summary.spec_id}' for detailed analysis")
        
        return "\n".join(hints)
    
    def link_test_to_tdd(self, spec_id: str, test_file: str) -> bool:
        """Link a test file to TDD tracking for a spec."""
        tdd_state = self._get_tdd_state(spec_id)
        
        linked_files = tdd_state.get("tests", {}).get("linked_files", [])
        if test_file not in linked_files:
            linked_files.append(test_file)
        
        self._update_tdd_state(spec_id, {
            "tests": {
                **tdd_state.get("tests", {}),
                "linked_files": linked_files,
            },
        })
        
        TestConsole.success(f"Linked {test_file} to TDD tracking for spec {spec_id}")
        return True
    
    def _generate_tdd_test_task(self, spec_id: str, spec_name: str, 
                                 spec_content: str, acceptance_criteria: List[str],
                                 tech_stack: dict) -> str:
        """Generate comprehensive TDD test task for IDE."""
        
        ac_list = "\n".join([f"{i+1}. [ ] {ac}" for i, ac in enumerate(acceptance_criteria)])
        tech_info = json.dumps(tech_stack, indent=2) if tech_stack else "Not specified"
        
        # Determine test file suggestions based on tech stack
        test_files = []
        if tech_stack.get("flutter"):
            test_files.extend([
                f"test/unit/services/{spec_id}_service_test.dart",
                f"test/widget/{spec_id}_widget_test.dart",
            ])
        if tech_stack.get("python"):
            test_files.extend([
                f"tests/test_{spec_id}.py",
                f"tests/integration/test_{spec_id}_integration.py",
            ])
        if tech_stack.get("web"):
            test_files.extend([
                f"__tests__/{spec_id}.test.ts",
                f"e2e/{spec_id}.spec.ts",
            ])
        
        test_files_list = "\n".join([f"- `{f}`" for f in test_files]) if test_files else "- Create in appropriate test directory"
        
        return f'''# TDD Test Task: Spec {spec_id} - {spec_name}

## Phase: RED (Create Failing Tests)

> **TDD Workflow**: Write tests FIRST, verify they FAIL, then implement.

## Spec Context

{spec_content}

## Acceptance Criteria to Cover

{ac_list}

## Tech Stack

```json
{tech_info}
```

## Required Test Files

{test_files_list}

## Test Requirements

### For Each Acceptance Criterion

Create tests that:
1. **Test the happy path** - Normal expected behavior
2. **Test edge cases** - Boundary conditions, empty inputs
3. **Test error handling** - Invalid inputs, network failures
4. **Use appropriate mocking** - Don't hit real APIs/databases

### Test Structure

```
describe('Feature: {spec_name}')
  describe('AC1: [Acceptance Criterion 1]')
    test('should [expected behavior]')
    test('should handle [edge case]')
    test('should throw error when [error condition]')
  
  describe('AC2: [Acceptance Criterion 2]')
    ...
```

## Guidelines

1. **Tests MUST FAIL initially** - We haven't implemented yet!
2. Follow existing test patterns in the codebase
3. Use the project's testing frameworks
4. Ensure tests are deterministic (no flaky tests)
5. Add appropriate setup/teardown
6. Use descriptive test names
7. Group related tests logically

## After Creating Tests

1. **Link tests to spec**: `speky test link <test-file> --spec {spec_id}`
2. **Run RED phase**: `speky test tdd-red {spec_id}`
3. **Verify tests FAIL** (expected in RED phase)
4. **Then implement the feature**

## Output Location

Create test files in:
{test_files_list}

Report back:
1. Which test files were created
2. How many tests were added
3. Which acceptance criteria are covered
'''
    
    def _get_tdd_state(self, spec_id: str) -> dict:
        """Get TDD state from spec status.json."""
        spec_dir = self.speky_dir / "specs"
        
        # Find spec directory
        status_file = None
        for d in spec_dir.iterdir() if spec_dir.exists() else []:
            if d.is_dir() and d.name.startswith(f"{spec_id}-"):
                status_file = d / "status.json"
                break
        
        if not status_file or not status_file.exists():
            return {"enabled": False}
        
        try:
            with open(status_file) as f:
                data = json.load(f)
                return data.get("tdd", {"enabled": False})
        except Exception:
            return {"enabled": False}
    
    def _update_tdd_state(self, spec_id: str, updates: dict):
        """Update TDD state in spec or story status.json."""
        # Try specs directory first
        spec_dir = self.speky_dir / "specs"
        status_file = None
        
        for d in spec_dir.iterdir() if spec_dir.exists() else []:
            if d.is_dir() and d.name.startswith(f"{spec_id}-"):
                status_file = d / "status.json"
                break
        
        # If not found in specs, try stories directory
        if not status_file:
            stories_dir = self.speky_dir / "stories"
            if stories_dir.exists():
                for d in stories_dir.iterdir():
                    if d.is_dir() and (d.name.startswith(f"{spec_id}-") or spec_id in d.name):
                        status_file = d / "status.json"
                        break
        
        if not status_file:
            TestConsole.warning(f"Spec/Story {spec_id} not found")
            return
        
        # Load existing status
        if status_file.exists():
            with open(status_file) as f:
                data = json.load(f)
        else:
            data = {}
        
        # Update TDD section
        if "tdd" not in data:
            data["tdd"] = {}
        
        # Deep merge updates
        for key, value in updates.items():
            if isinstance(value, dict) and key in data["tdd"]:
                data["tdd"][key] = {**data["tdd"][key], **value}
            else:
                data["tdd"][key] = value
        
        # Save
        with open(status_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _detect_tech_stack(self) -> dict:
        """Detect project tech stack from files"""
        tech_stack = {}
        
        # Flutter
        if (self.project_root / "pubspec.yaml").exists():
            tech_stack["flutter"] = True
        
        # Python
        if (self.project_root / "requirements.txt").exists() or \
           (self.project_root / "pyproject.toml").exists():
            tech_stack["python"] = True
        
        # Node.js / Web
        if (self.project_root / "package.json").exists():
            tech_stack["web"] = True
        
        # Check subdirectories
        for subdir in ["frontend", "backend", "src", "lib"]:
            subpath = self.project_root / subdir
            if subpath.exists():
                if (subpath / "pubspec.yaml").exists():
                    tech_stack["flutter"] = True
                if (subpath / "requirements.txt").exists():
                    tech_stack["python"] = True
                if (subpath / "package.json").exists():
                    tech_stack["web"] = True
        
        return tech_stack
    
    def _load_spec(self, spec_id: str) -> tuple:
        """Load spec or story content and extract acceptance criteria"""
        # Try specs directory first
        spec_dir = self.speky_dir / "specs"
        spec_path = None
        
        for d in spec_dir.iterdir() if spec_dir.exists() else []:
            if d.is_dir() and d.name.startswith(f"{spec_id}-"):
                spec_path = d / "spec.md"
                break
        
        # If not found in specs, try stories directory
        if not spec_path or not spec_path.exists():
            stories_dir = self.speky_dir / "stories"
            for d in stories_dir.iterdir() if stories_dir.exists() else []:
                if d.is_dir() and (d.name.startswith(f"{spec_id}-") or spec_id in d.name):
                    spec_path = d / "story.md"
                    break
        
        if not spec_path or not spec_path.exists():
            return None, []
        
        with open(spec_path) as f:
            content = f.read()
        
        # Extract acceptance criteria (simple parsing)
        acceptance_criteria = []
        in_ac_section = False
        for line in content.split("\n"):
            if "acceptance criteria" in line.lower() or "## ac" in line.lower():
                in_ac_section = True
                continue
            if in_ac_section:
                if line.startswith("##"):
                    break
                if line.strip().startswith("- ") or line.strip().startswith("* "):
                    ac = line.strip()[2:].strip()
                    if ac:
                        acceptance_criteria.append(ac)
        
        return content, acceptance_criteria
    
    def _find_existing_tests(self, spec_id: str) -> List[str]:
        """Find existing test files that might be related to a spec"""
        tests = []
        
        # Check manifest first
        manifest = self._load_spec_manifest(spec_id)
        if manifest.get("linked_tests"):
            tests.extend(manifest["linked_tests"])
        
        # Search common test directories
        test_dirs = [
            self.project_root / "test",
            self.project_root / "tests",
            self.project_root / "frontend" / "test",
            self.project_root / "backend" / "tests",
        ]
        
        for test_dir in test_dirs:
            if test_dir.exists():
                for f in test_dir.rglob("*test*.dart"):
                    tests.append(str(f.relative_to(self.project_root)))
                for f in test_dir.rglob("test_*.py"):
                    tests.append(str(f.relative_to(self.project_root)))
        
        return list(set(tests))
    
    def _identify_coverage_gaps(
        self, 
        spec_id: str, 
        acceptance_criteria: List[str], 
        existing_tests: List[str]
    ) -> List[str]:
        """Identify which acceptance criteria don't have tests"""
        # Simple heuristic: if no tests exist, all AC are gaps
        if not existing_tests:
            return acceptance_criteria
        
        # TODO: More sophisticated matching of tests to AC
        # For now, assume partial coverage
        return acceptance_criteria[len(existing_tests):]
    
    def _generate_testing_guide(self, tech_stack: dict):
        """Generate comprehensive TESTING_GUIDE.md for the project"""
        TestConsole.step("Generating TESTING_GUIDE.md...")
        
        guide_file = self.project_root / "TESTING_GUIDE.md"
        
        # Get project name from context or directory
        project_name = self.project_root.name.title()
        context_file = self.speky_dir / "context" / "context.json"
        if context_file.exists():
            try:
                context = json.loads(context_file.read_text())
                project_name = context.get("product_name", project_name)
            except:
                pass
        
        # Determine test directories based on tech stack
        frontend_test_dir = "test/"
        backend_test_dir = "tests/"
        
        if tech_stack.get("flutter"):
            for path in [self.project_root, self.project_root / "frontend"]:
                if (path / "pubspec.yaml").exists():
                    if path != self.project_root:
                        frontend_test_dir = "frontend/test/"
                    break
        
        if tech_stack.get("python"):
            for path in [self.project_root, self.project_root / "backend"]:
                if (path / "requirements.txt").exists() or (path / "pytest.ini").exists():
                    if path != self.project_root:
                        backend_test_dir = "backend/tests/"
                    break
        
        # Build tech-specific sections
        frontend_section = ""
        backend_section = ""
        quick_start_commands = ""
        
        if tech_stack.get("flutter"):
            frontend_section = self._get_flutter_testing_section(frontend_test_dir)
            quick_start_commands += f"cd {frontend_test_dir.rstrip('/').rsplit('/', 1)[0] if '/' in frontend_test_dir else '.'} && flutter test --coverage\n"
        
        if tech_stack.get("python"):
            backend_section = self._get_python_testing_section(backend_test_dir)
            quick_start_commands += f"cd {backend_test_dir.rstrip('/').rsplit('/', 1)[0] if '/' in backend_test_dir else '.'} && pytest --cov\n"
        
        if tech_stack.get("web"):
            backend_section += self._get_javascript_testing_section()
            quick_start_commands += "npm test\n"
        
        # Generate the guide
        guide_content = f'''# {project_name} Testing Guide

**Complete testing reference for this project**

Last Updated: {datetime.now().strftime("%Y-%m-%d")}  
Generated by: SPEKY Testing Integration

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Test Structure](#test-structure)
3. [Running Tests](#running-tests)
4. [SPEKY Test Commands](#speky-test-commands)
5. [TDD Workflow](#tdd-workflow)
6. [Coverage Tracking](#coverage-tracking)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Run All Tests

```bash
# Using SPEKY (recommended - auto-detects all tech stacks)
speky test run

# With coverage
speky test run --coverage

# Or manually:
{quick_start_commands.strip()}
```

### Current Test Status

Run `speky test status` to see current test health.

---

## Test Structure

```
{self._get_test_structure_diagram(tech_stack, frontend_test_dir, backend_test_dir)}
```

---

{frontend_section}

{backend_section}

## SPEKY Test Commands

SPEKY provides integrated test management for this project.

### Core Testing Commands

```bash
# Initialize test infrastructure
speky test init

# Generate tests for a spec
speky test gen <spec-id>

# Run all tests (auto-detects tech stacks)
speky test run

# Run tests with coverage
speky test run --coverage

# Run tests for specific spec
speky test run --spec <spec-id>

# Check coverage
speky test coverage

# View test status
speky test status

# Link tests to specs
speky test link <test-file> --spec <spec-id>

# Identify test gaps
speky test gaps

# Get test recommendations
speky test recommend

# Refresh test context
speky test refresh-context
```

### TDD Commands

```bash
# Start TDD workflow for a spec
speky implement <spec-id> --tdd

# RED phase: verify tests fail (before implementation)
speky test tdd-red <spec-id>

# GREEN phase: verify tests pass (after implementation)
speky test tdd-green <spec-id>

# View TDD status dashboard
speky test tdd-status

# Complete spec with TDD verification
speky complete <spec-id>
```

---

## TDD Workflow

SPEKY supports Test-Driven Development with the **RED-GREEN-REFACTOR** cycle.

### TDD Workflow Diagram

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

### When to Use TDD

**✅ Use TDD for:**
- New features with clear acceptance criteria
- Bug fixes (write failing test first)
- Complex business logic
- Critical functionality

**❌ Skip TDD for:**
- Simple UI tweaks without logic
- Config/documentation changes
- Exploratory/prototype work

---

## Coverage Tracking

### Coverage Goals

- **Target:** 80% line coverage
- **Minimum:** 60% for new code

### View Coverage

```bash
# SPEKY coverage report
speky test coverage

# Run tests with coverage
speky test run --coverage
```

### Modular Test Runner Architecture

SPEKY automatically detects and runs tests for multiple tech stacks:

**Detected Tech Stacks:**
{self._format_detected_tech_stacks(tech_stack)}

**Benefits:**
- 🚀 **Auto-detection** - Finds all applicable test runners
- 📊 **Real-time output** - See tests as they run
- 🎯 **Accurate counts** - Actual test numbers
- 🔧 **Extensible** - Easy to add new tech stacks
- 📈 **Coverage parsing** - Automatic coverage extraction

---

## Best Practices

### General

1. **Write tests first** (TDD) for new features
2. **Keep tests fast** - Unit tests < 100ms each
3. **Test one thing** - Each test should verify one behavior
4. **Use descriptive names** - Test names should describe what's being tested
5. **Mock external dependencies** - Don't test third-party code
6. **Run tests before commit** - Never commit failing tests

### Test Organization

```
test/
├── unit/           # Fast, isolated tests (70% of suite)
├── widget/         # UI component tests (20% of suite)
└── integration/    # End-to-end tests (10% of suite)
```

### Coverage Guidelines

| File Type | Recommended Coverage |
|-----------|---------------------|
| Business Logic | 90%+ |
| Data Models | 85%+ |
| UI Components | 70%+ |
| Utilities | 80%+ |
| Generated Code | Skip |

---

## Troubleshooting

### Tests Not Running

```bash
# Refresh SPEKY test context
speky test refresh-context

# Check test harness status
speky test status
```

### Coverage Not Generating

```bash
# Run with explicit coverage flag
speky test run --coverage

# Check if coverage tools are installed
# Flutter: Built-in
# Python: pip install pytest-cov
# JavaScript: npm install --save-dev jest
```

### TDD Phase Issues

**RED phase passes (should fail):**
- Tests aren't testing new code
- Implementation already exists
- Check test assertions

**GREEN phase fails:**
- Implementation incomplete
- Check error messages
- Run specific failing test

---

## Resources

### Documentation

- **SPEKY Testing:** `.speky/testing/`
- **IDE Context:** `.speky/context/IDE_CONTEXT.md`
- **Test Tasks:** `.speky/testing/tasks/`

### Related Files

- **Test Config:** `.speky/testing/config.yaml`
- **Coverage Data:** `.speky/testing/coverage/`
- **Test Tasks:** `.speky/testing/tasks/`

---

**Generated by SPEKY Testing Integration**  
**Last Updated:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
'''
        
        # Write the guide
        guide_file.write_text(guide_content)
        TestConsole.success(f"Generated TESTING_GUIDE.md")
    
    def _get_test_structure_diagram(self, tech_stack: dict, frontend_dir: str, backend_dir: str) -> str:
        """Generate test structure diagram based on detected tech stack"""
        lines = [f"{self.project_root.name}/"]
        
        if tech_stack.get("flutter"):
            prefix = frontend_dir.rstrip('/').split('/')[0] + "/" if '/' in frontend_dir else ""
            lines.extend([
                f"├── {prefix}test/",
                f"│   ├── unit/              # Unit tests",
                f"│   ├── widget/            # Widget tests",
                f"│   └── integration/       # Integration tests",
            ])
        
        if tech_stack.get("python"):
            prefix = backend_dir.rstrip('/').split('/')[0] + "/" if '/' in backend_dir else ""
            lines.extend([
                f"├── {prefix}tests/",
                f"│   ├── unit/              # Unit tests",
                f"│   ├── integration/       # Integration tests",
                f"│   └── conftest.py        # Pytest fixtures",
            ])
        
        if tech_stack.get("web"):
            lines.extend([
                f"├── __tests__/             # Jest tests",
                f"│   ├── unit/",
                f"│   └── integration/",
            ])
        
        lines.extend([
            f"└── .speky/",
            f"    └── testing/",
            f"        ├── config.yaml       # Test configuration",
            f"        ├── coverage/         # Coverage reports",
            f"        └── tasks/            # Test generation tasks",
        ])
        
        return "\n".join(lines)
    
    def _format_detected_tech_stacks(self, tech_stack: dict) -> str:
        """Format detected tech stacks as markdown list"""
        lines = []
        if tech_stack.get("flutter"):
            lines.append("- ✅ **Flutter/Dart** - Detected via `pubspec.yaml`")
        if tech_stack.get("python"):
            lines.append("- ✅ **Python/pytest** - Detected via `requirements.txt` or `pytest.ini`")
        if tech_stack.get("web"):
            lines.append("- ✅ **JavaScript/Jest** - Detected via `package.json`")
        
        if not lines:
            lines.append("- ⚠️ No tech stacks detected yet")
        
        return "\n".join(lines)
    
    def _get_flutter_testing_section(self, test_dir: str) -> str:
        """Generate Flutter-specific testing section"""
        return f'''## Frontend Testing (Flutter)

### Running Flutter Tests

```bash
# Run all tests
cd {test_dir.rstrip('/').rsplit('/', 1)[0] if '/' in test_dir else '.'}
flutter test

# Run with coverage
flutter test --coverage

# Run specific test file
flutter test {test_dir}unit/models/example_test.dart

# Run tests by directory
flutter test {test_dir}unit/

# Run with verbose output
flutter test --verbose
```

### Coverage Analysis

```bash
# Generate coverage report
flutter test --coverage

# View summary (requires lcov)
lcov --summary coverage/lcov.info

# Generate HTML report
genhtml coverage/lcov.info -o coverage/html
open coverage/html/index.html
```

### Flutter Test Best Practices

1. **Use `setUp` and `tearDown`** for test isolation
2. **Mock platform channels** for native dependencies
3. **Use `TestWidgetsFlutterBinding.ensureInitialized()`** for widget tests
4. **Group related tests** with `group()`
5. **Use descriptive test names** that explain the behavior

---

'''
    
    def _get_python_testing_section(self, test_dir: str) -> str:
        """Generate Python-specific testing section"""
        return f'''## Backend Testing (Python)

### Running Python Tests

```bash
# Run all tests
cd {test_dir.rstrip('/').rsplit('/', 1)[0] if '/' in test_dir else '.'}
pytest

# Run with coverage
pytest --cov --cov-report=term-missing

# Run specific test file
pytest {test_dir}test_example.py

# Run specific test function
pytest {test_dir}test_example.py::test_function_name

# Run with verbose output
pytest -v

# Run with print statements visible
pytest -s
```

### Coverage Analysis

```bash
# Generate coverage report
pytest --cov --cov-report=html

# View HTML report
open htmlcov/index.html
```

### Python Test Best Practices

1. **Use fixtures** for common setup (`@pytest.fixture`)
2. **Use markers** for test categories (`@pytest.mark.unit`)
3. **Parametrize tests** for multiple inputs (`@pytest.mark.parametrize`)
4. **Use `pytest-asyncio`** for async tests
5. **Mock external services** with `pytest-mock`

---

'''
    
    def _get_javascript_testing_section(self) -> str:
        """Generate JavaScript-specific testing section"""
        return '''## JavaScript Testing (Jest)

### Running JavaScript Tests

```bash
# Run all tests
npm test

# Run with coverage
npm test -- --coverage

# Run specific test file
npm test -- path/to/test.js

# Run in watch mode
npm test -- --watch
```

### Coverage Analysis

```bash
# Generate coverage report
npm test -- --coverage

# View HTML report
open coverage/lcov-report/index.html
```

### JavaScript Test Best Practices

1. **Use `describe` and `it`** for test organization
2. **Use `beforeEach` and `afterEach`** for setup/teardown
3. **Mock modules** with `jest.mock()`
4. **Use snapshots** for UI components
5. **Test async code** with `async/await`

---

'''
    
    def _scaffold_e2e_infrastructure(self, tech_stack: dict):
        """Create E2E test infrastructure files (test_config, mock_auth, etc.)"""
        TestConsole.step("Scaffolding E2E test infrastructure...")
        
        # Determine target directory
        if tech_stack.get("flutter"):
            flutter_root = None
            for path in [self.project_root, self.project_root / "frontend"]:
                if (path / "pubspec.yaml").exists():
                    flutter_root = path
                    break
            
            if not flutter_root:
                TestConsole.warning("Flutter project not found, skipping E2E scaffold")
                return
            
            e2e_dir = flutter_root / "integration_test" / "e2e"
        else:
            e2e_dir = self.project_root / "e2e"
        
        e2e_dir.mkdir(parents=True, exist_ok=True)
        
        if tech_stack.get("flutter"):
            self._create_flutter_test_config(e2e_dir)
            self._create_flutter_mock_auth(e2e_dir)
            self._create_flutter_test_keys(e2e_dir)
            TestConsole.success(f"Created E2E scaffolding in {e2e_dir}")
        elif tech_stack.get("python"):
            self._create_python_test_config(e2e_dir)
            TestConsole.success(f"Created E2E scaffolding in {e2e_dir}")
    
    def _create_flutter_test_config(self, e2e_dir: Path):
        """Create Flutter test_config.dart for environment isolation"""
        config_file = e2e_dir / "test_config.dart"
        if config_file.exists():
            return
        
        content = '''/// Test Environment Configuration - GENERATED BY SPEKY
import 'package:flutter/foundation.dart';
import 'dart:io';

enum TestEnvironment { production, isolated, inMemory }

class TestConfig {
  static TestEnvironment _environment = TestEnvironment.isolated;
  static String? _testDatabasePath;
  
  static bool get isTestMode => _environment != TestEnvironment.production;
  static String get testDatabasePath => _testDatabasePath ?? '';
  
  static Future<void> initialize({TestEnvironment env = TestEnvironment.isolated}) async {
    _environment = env;
    if (env == TestEnvironment.isolated) {
      final tempDir = Directory.systemTemp;
      _testDatabasePath = '${tempDir.path}/app_test_${DateTime.now().millisecondsSinceEpoch}';
      await Directory(_testDatabasePath!).create(recursive: true);
      debugPrint('🧪 Test database: $_testDatabasePath');
    }
  }
  
  static Future<void> cleanup() async {
    if (_testDatabasePath != null) {
      final dir = Directory(_testDatabasePath!);
      if (await dir.exists()) await dir.delete(recursive: true);
      _testDatabasePath = null;
    }
    _environment = TestEnvironment.production;
  }
}
'''
        config_file.write_text(content)
        TestConsole.info("Created test_config.dart")
    
    def _create_flutter_mock_auth(self, e2e_dir: Path):
        """Create Flutter mock_auth.dart for auth bypass"""
        mock_file = e2e_dir / "mock_auth.dart"
        if mock_file.exists():
            return
        
        content = '''/// Mock Authentication - GENERATED BY SPEKY
/// TODO: Customize with your actual auth provider
import 'package:flutter_riverpod/flutter_riverpod.dart';

class MockUser {
  final String uid, email, displayName;
  const MockUser({required this.uid, required this.email, required this.displayName});
  static const testUser = MockUser(uid: 'test-123', email: 'test@example.com', displayName: 'Test User');
}

class MockAuthState {
  final bool isAuthenticated, isLoading;
  final MockUser? user;
  const MockAuthState({this.isAuthenticated = false, this.isLoading = false, this.user});
  static const authenticated = MockAuthState(isAuthenticated: true, user: MockUser.testUser);
  static const unauthenticated = MockAuthState();
}

class MockAuthNotifier extends StateNotifier<MockAuthState> {
  MockAuthNotifier([MockAuthState initial = MockAuthState.authenticated]) : super(initial);
  Future<void> signIn() async { state = MockAuthState.authenticated; }
  Future<void> signOut() async { state = MockAuthState.unauthenticated; }
}

/// TODO: Implement with your actual auth provider
List<Override> getAuthOverrides({bool preAuthenticated = true}) => [];
'''
        mock_file.write_text(content)
        TestConsole.info("Created mock_auth.dart")
    
    def _create_flutter_test_keys(self, e2e_dir: Path):
        """Create Flutter test_keys.dart for widget finding"""
        keys_file = e2e_dir / "test_keys.dart"
        if keys_file.exists():
            return
        
        content = '''/// Test Keys for Widget Finding - GENERATED BY SPEKY
/// Add keys to your widgets: key: TestKeys.myWidget
import 'package:flutter/material.dart';

class TestKeys {
  static const sidebarToggle = Key('sidebar_toggle');
  static const signInButton = Key('sign_in_button');
  static const signOutButton = Key('sign_out_button');
  static Key listItem(String id) => Key('list_item_$id');
  static Key tabItem(String id) => Key('tab_item_$id');
  // TODO: Add more keys as you build features
}
'''
        keys_file.write_text(content)
        TestConsole.info("Created test_keys.dart")
    
    def _create_python_test_config(self, e2e_dir: Path):
        """Create Python test_config.py"""
        config_file = e2e_dir / "test_config.py"
        if config_file.exists():
            return
        
        content = '''"""Test Environment Configuration - GENERATED BY SPEKY"""
import os, tempfile, shutil
from enum import Enum

class TestEnvironment(Enum):
    PRODUCTION = "production"
    ISOLATED = "isolated"

class TestConfig:
    _environment = TestEnvironment.ISOLATED
    _test_db_path = None
    
    @classmethod
    def initialize(cls, env=TestEnvironment.ISOLATED):
        cls._environment = env
        if env == TestEnvironment.ISOLATED:
            cls._test_db_path = tempfile.mkdtemp(prefix="app_test_")
    
    @classmethod
    def cleanup(cls):
        if cls._test_db_path and os.path.exists(cls._test_db_path):
            shutil.rmtree(cls._test_db_path)
        cls._test_db_path = None
    
    @classmethod
    def is_test_mode(cls): return cls._environment != TestEnvironment.PRODUCTION
'''
        config_file.write_text(content)
        TestConsole.info("Created test_config.py")
    
    def _load_spec_manifest(self, spec_id: str) -> dict:
        """Load test manifest for a spec"""
        manifest_file = self.specs_dir / spec_id / "test_manifest.yaml"
        if manifest_file.exists():
            # Simple YAML parsing
            data = {}
            with open(manifest_file) as f:
                for line in f:
                    if ":" in line and not line.strip().startswith("#"):
                        key, value = line.split(":", 1)
                        data[key.strip()] = value.strip()
            return data
        return {}
    
    def _update_spec_manifest(self, spec_id: str, updates: dict):
        """Update test manifest for a spec"""
        spec_dir = self.specs_dir / spec_id
        spec_dir.mkdir(parents=True, exist_ok=True)
        
        manifest_file = spec_dir / "test_manifest.yaml"
        
        # Load existing
        existing = self._load_spec_manifest(spec_id)
        existing.update(updates)
        
        # Save
        with open(manifest_file, 'w') as f:
            f.write("# Test manifest for spec {}\n".format(spec_id))
            for key, value in existing.items():
                f.write(f"{key}: {value}\n")
    
    def _load_coverage_data(self) -> dict:
        """Load coverage tracking data"""
        coverage_file = self.coverage_dir / "coverage.yaml"
        if coverage_file.exists():
            # Simple YAML parsing
            data = {"overall": {}, "by_spec": {}, "gaps": []}
            with open(coverage_file) as f:
                content = f.read()
                # Very basic parsing - would use proper YAML in production
                if "line_coverage:" in content:
                    for line in content.split("\n"):
                        if "line_coverage:" in line:
                            try:
                                data["overall"]["line_coverage"] = float(line.split(":")[1].strip())
                            except:
                                pass
            return data
        return {"overall": {"line_coverage": 0}, "by_spec": {}, "gaps": []}
    
    def _save_coverage_data(self, data: dict):
        """Save coverage tracking data"""
        coverage_file = self.coverage_dir / "coverage.yaml"
        with open(coverage_file, 'w') as f:
            f.write("# SPEKY Coverage Tracking\n")
            f.write(f"# Last updated: {datetime.now().isoformat()}\n\n")
            f.write("overall:\n")
            f.write(f"  line_coverage: {data.get('overall', {}).get('line_coverage', 0)}\n")
            f.write(f"  branch_coverage: {data.get('overall', {}).get('branch_coverage', 0)}\n")
    
    def _coverage_bar(self, percentage: float, width: int = 20) -> str:
        """Generate a visual coverage bar"""
        filled = int(percentage / 100 * width)
        empty = width - filled
        return f"{'█' * filled}{'░' * empty}"
    
    def _get_all_spec_ids(self) -> List[str]:
        """Get all spec IDs from SPEKY"""
        specs_dir = self.speky_dir / "specs"
        if not specs_dir.exists():
            return []
        
        spec_ids = []
        for d in specs_dir.iterdir():
            if d.is_dir() and d.name[:3].isdigit():
                spec_ids.append(d.name[:3])
        return sorted(spec_ids)
    
    def _find_untested_specs(self) -> List[str]:
        """Find specs without any tests"""
        untested = []
        for spec_id in self._get_all_spec_ids():
            tests = self._find_existing_tests(spec_id)
            if not tests:
                untested.append(spec_id)
        return untested
    
    def _run_flutter_tests(
        self, 
        spec_id: str = None, 
        test_type: str = "all",
        with_coverage: bool = False
    ) -> dict:
        """DEPRECATED: Use modular test runners instead.
        
        This method is kept for backward compatibility but should not be used.
        Use get_available_runners() and the BaseTestRunner interface instead.
        """
        TestConsole.step("Running Flutter tests...")
        
        # Find Flutter project
        flutter_root = None
        for path in [self.project_root, self.project_root / "frontend"]:
            if (path / "pubspec.yaml").exists():
                flutter_root = path
                break
        
        if not flutter_root:
            return {"passed": False, "summary": "Flutter project not found", "total": 0, "failed": 0}
        
        # Build command
        cmd = ["flutter", "test"]
        if with_coverage:
            cmd.append("--coverage")
        
        try:
            # Run with real-time output
            import sys
            result = subprocess.run(
                cmd,
                cwd=flutter_root,
                stdout=sys.stdout,  # Stream to console
                stderr=sys.stderr,
                text=True,
                timeout=600,  # Increased timeout for large test suites
            )
            
            passed = result.returncode == 0
            
            # Parse coverage if generated
            coverage_pct = None
            if with_coverage:
                coverage_file = flutter_root / "coverage" / "lcov.info"
                if coverage_file.exists():
                    coverage_pct = self._parse_flutter_coverage(coverage_file)
            
            return {
                "passed": passed,
                "summary": "All tests passed" if passed else "Some tests failed",
                "coverage": coverage_pct,
                "platform": "Flutter",
            }
        except subprocess.TimeoutExpired:
            return {"passed": False, "summary": "Tests timed out (>10 min)", "total": 0, "failed": 0}
        except FileNotFoundError:
            return {"passed": False, "summary": "Flutter not found. Install: https://flutter.dev", "total": 0, "failed": 0}
        except Exception as e:
            return {"passed": False, "summary": str(e), "total": 0, "failed": 0}
    
    def _run_python_tests(
        self, 
        spec_id: str = None, 
        test_type: str = "all",
        with_coverage: bool = False
    ) -> dict:
        """DEPRECATED: Use modular test runners instead.
        
        This method is kept for backward compatibility but should not be used.
        Use get_available_runners() and the BaseTestRunner interface instead.
        """
        TestConsole.step("Running Python tests...")
        
        # Find Python project
        python_root = None
        for path in [self.project_root, self.project_root / "backend"]:
            if (path / "requirements.txt").exists() or (path / "pytest.ini").exists():
                python_root = path
                break
        
        if not python_root:
            return {"passed": False, "summary": "Python project not found", "total": 0, "failed": 0}
        
        # Build command
        cmd = ["pytest", "-v"]  # Verbose for better output
        if with_coverage:
            cmd.extend(["--cov", "--cov-report=term-missing"])
        
        try:
            # Run with real-time output
            import sys
            result = subprocess.run(
                cmd,
                cwd=python_root,
                stdout=sys.stdout,  # Stream to console
                stderr=sys.stderr,
                text=True,
                timeout=600,  # Increased timeout for large test suites
            )
            
            passed = result.returncode == 0
            
            return {
                "passed": passed,
                "summary": "All tests passed" if passed else "Some tests failed",
                "platform": "Python",
            }
        except subprocess.TimeoutExpired:
            return {"passed": False, "summary": "Tests timed out (>10 min)", "total": 0, "failed": 0}
        except FileNotFoundError:
            return {"passed": False, "summary": "pytest not found. Install: pip install pytest", "total": 0, "failed": 0}
        except Exception as e:
            return {"passed": False, "summary": str(e), "total": 0, "failed": 0}
    
    def _display_test_results(self, results: dict):
        """Display test results summary"""
        print("\n" + "=" * 60)
        print("Test Results Summary")
        print("=" * 60)
        
        for platform, data in results.items():
            status = "✅" if data.get("passed") else "❌"
            platform_name = data.get("platform", platform.upper())
            print(f"\n{status} {platform_name}")
            print(f"   Status: {data.get('summary', 'Unknown')}")
            
            # Show coverage if available
            if data.get("coverage") is not None:
                cov = data["coverage"]
                cov_status = "✅" if cov >= 80 else "⚠️" if cov >= 60 else "❌"
                print(f"   Coverage: {cov_status} {cov:.1f}%")
    
    def _parse_coverage_for_runner(self, runner: BaseTestRunner, cwd: Path) -> float:
        """Parse coverage report for a specific runner"""
        if runner.name == "flutter":
            lcov_file = cwd / "coverage" / "lcov.info"
            if lcov_file.exists():
                return self._parse_flutter_coverage(lcov_file)
        elif runner.name == "pytest":
            # Pytest outputs coverage to terminal, would need to parse from output
            # For now, check if .coverage file exists
            coverage_file = cwd / ".coverage"
            if coverage_file.exists():
                # Could use coverage.py API here to get percentage
                return None  # Placeholder
        elif runner.name == "jest":
            # Jest creates coverage/lcov.info similar to Flutter
            lcov_file = cwd / "coverage" / "lcov.info"
            if lcov_file.exists():
                return self._parse_flutter_coverage(lcov_file)  # Same format
        
        return None
    
    def _parse_flutter_coverage(self, lcov_file: Path) -> float:
        """Parse Flutter/Jest lcov.info coverage file and return percentage"""
        try:
            content = lcov_file.read_text()
            lines_found = 0
            lines_hit = 0
            
            for line in content.split('\n'):
                if line.startswith('LF:'):  # Lines Found
                    lines_found += int(line.split(':')[1])
                elif line.startswith('LH:'):  # Lines Hit
                    lines_hit += int(line.split(':')[1])
            
            if lines_found == 0:
                return 0.0
            
            return (lines_hit / lines_found) * 100
        except Exception:
            return None
    
    def _update_coverage_from_results(self, results: dict):
        """Update coverage data from test results"""
        # Placeholder - would parse actual coverage reports
        pass
    
    # =========================================================================
    # IDE CONTEXT MANAGEMENT (Self-Updating)
    # =========================================================================
    
    def generate_ide_context(self) -> str:
        """Generate IDE context for testing capabilities.
        This is called automatically and merged into IDE rules.
        """
        version = self.config.get("version", "0.1.0")
        tech_stack = self._detect_tech_stack()
        
        # Build tech-specific sections
        tech_sections = self._generate_tech_specific_sections(tech_stack)
        
        return f'''# 🧪 SPEKY Testing Context (v{version})

> Auto-generated by speky_testing.py - DO NOT EDIT MANUALLY
> Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## 🚨 CRITICAL: Anti-Clutter Rules

**NEVER create these files at project root:**
- ❌ `TEST_SETUP_SUMMARY.md` - Use `.speky/testing/` instead
- ❌ `TESTING.md` - Use `.speky/testing/` instead  
- ❌ `test_report.md` - Use `.speky/testing/reports/` instead
- ❌ Any `*_test_*.md` files at root

**All testing artifacts go in:**
- `.speky/testing/` - Config, reports, tasks
- `test/` or `frontend/test/` - Actual test files
- `integration_test/` - Integration tests

**DO NOT create bulk tests without being asked.** Follow the incremental workflow below.

## 🎯 AI Agent Instructions for Testing

When the user asks about testing, follow this workflow **step by step**:

### First-Time Setup (if `.speky/testing/` doesn't exist)

1. **Run**: `speky test init` - Let SPEKY detect tech stack
2. **Show user** the detected stack and ask what they want to set up first
3. **Get ONE setup guide**: `speky test setup <tool>` based on user choice
4. **Help install** that specific tool
5. **Verify** with a simple existing test before proceeding
6. **STOP and ask** what the user wants to do next

### When User Says "Set up testing"

**DO NOT** create all test infrastructure at once. Instead:
1. Run `speky test init`
2. Ask: "What would you like to set up first? (unit tests / widget tests / E2E)"
3. Help with ONE category at a time
4. Let the user drive the pace

### After Each Implementation (Spec-Driven Testing)

1. **Get test recommendations**: `speky test recommend`
2. **Show the output** to the user - don't just act on it
3. **Ask**: "Would you like me to generate a test task for spec XXX?"
4. **If yes**: `speky test gen <spec-id>` creates task in `.speky/testing/tasks/`
5. **Implement tests** based on the generated task
6. **Link tests**: `speky test link <test-file> --spec <id>`

### When User Says "I finished implementing"

```
Step 1: speky test recommend          # See what tests are needed
Step 2: speky test run --spec <id>    # Run existing tests
Step 3: speky complete <id> --test    # Complete with test verification
```

### 🧪 TDD Workflow (Test-Driven Development)

When the user wants to use TDD or says "implement with TDD":

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

**TDD Commands:**
| Command | Purpose |
|---------|---------|
| `speky implement <id> --tdd` | Start TDD workflow, generate test task |
| `speky test tdd-red <id>` | RED phase: verify tests fail (expected!) |
| `speky test tdd-green <id>` | GREEN phase: verify tests pass |
| `speky test tdd-status` | Show TDD dashboard for all specs |
| `speky test tdd-status <id>` | Show TDD status for specific spec |
| `speky test link <file> --spec <id>` | Link test file to TDD tracking |

**TDD Phase Rules:**
- **RED Phase**: Tests MUST fail. If they pass, they're not testing new code!
- **GREEN Phase**: All tests must pass. If any fail, fix implementation.
- **Completion**: Both TDD tests AND regression tests must pass.

**When to Suggest TDD:**
- ✅ New features with clear acceptance criteria
- ✅ Bug fixes (write failing test first)
- ✅ Complex business logic
- ❌ Simple UI tweaks without logic
- ❌ Config/docs changes
- ❌ Exploratory/prototype work

## ⚠️ What NOT To Do

- ❌ Create TEST_SETUP_SUMMARY.md or TESTING.md at root
- ❌ Generate all possible tests at once
- ❌ Add test dependencies without asking
- ❌ Create test files without a spec or user request
- ❌ Run full test suites without asking
- ✅ Follow incremental, user-driven workflow
- ✅ Use SPEKY commands for test generation
- ✅ Keep documentation in `.speky/testing/`

## Detected Tech Stack

{tech_sections['detected_stack']}

## Testing Commands Reference

### Core Testing Commands
| Command | When to Use |
|---------|-------------|
| `speky test init` | First-time setup, detect tech stack |
| `speky test recommend` | After implementation, before complete |
| `speky test gen <spec>` | Generate test task for IDE to implement |
| `speky test run` | Execute all tests |
| `speky test run --spec <id>` | Run tests for specific spec |
| `speky test run --affected` | Run only tests affected by changes |
| `speky test coverage` | View coverage report |
| `speky test status` | Show test health dashboard |
| `speky test setup <tool>` | Get setup guide with detailed steps |
| `speky test gaps` | Find untested acceptance criteria |
| `speky test link <file> --spec <id>` | Link test file to spec |

### TDD Commands
| Command | When to Use |
|---------|-------------|
| `speky implement <id> --tdd` | Start TDD workflow for a spec |
| `speky test tdd-red <id>` | Run RED phase (verify tests fail) |
| `speky test tdd-green <id>` | Run GREEN phase (verify tests pass) |
| `speky test tdd-status` | View TDD dashboard for all specs |
| `speky test tdd-status <id>` | View TDD status for specific spec |

### Completion Commands
| Command | When to Use |
|---------|-------------|
| `speky complete <id>` | Complete spec (auto-runs tests for TDD specs) |
| `speky complete <id> --test` | Complete with test verification |

## Test Type Guidelines

| Files Changed | Recommended Tests | Why |
|---------------|-------------------|-----|
{tech_sections['test_guidelines']}

## ❌ Avoid Overkill Testing

- **Minor logic change** → Unit tests only (not E2E)
- **Utility function** → Unit tests only (not integration)
- **Pure data layer** → Unit tests only (not widget)
- **Config/docs only** → Skip tests entirely
- **UI + data layer change** → Unit + Widget (consider E2E for critical paths)

## Test File Locations for This Project

{tech_sections['file_locations']}

## E2E Testing Status

- Web (Playwright MCP): {"✅ Available" if self.config.get("e2e", {}).get("web", {}).get("mcp_enabled") else "⏳ Run: `speky test setup playwright-mcp`"}
- Mobile (Patrol): {"✅ Available" if self.config.get("e2e", {}).get("mobile", {}).get("enabled") else "⏳ Run: `speky test setup patrol`"}

## Coverage

- Target: {self.config.get("coverage_threshold", 80)}%
- Enforcement: {self.config.get("coverage_enforcement", "soft")}

## Quick Reference: Common Scenarios

**"Set up testing for this project"**
```bash
speky test init
speky test setup flutter-test    # If Flutter
speky test setup pytest-cov      # If Python
```

**"What tests should I run?"**
```bash
speky test recommend
```

**"Run tests for spec 003"**
```bash
speky test run --spec 003
```

**"I need to write tests for this feature"**
```bash
speky test gen 003   # Creates test task for IDE
# Then implement tests based on the generated task
speky test link test/feature_test.dart --spec 003
```

**"Complete implementation with tests"**
```bash
speky complete 003 --test
```

## 🧪 TDD Scenarios

**"Implement this feature with TDD"**
```bash
# Step 1: Start TDD workflow
speky implement 003 --tdd

# Step 2: Create tests based on generated task
# (IDE creates test files)

# Step 3: Link test files
speky test link test/feature_test.dart --spec 003

# Step 4: Run RED phase (tests should FAIL)
speky test tdd-red 003

# Step 5: Implement the feature
# (IDE implements the code)

# Step 6: Run GREEN phase (tests should PASS)
speky test tdd-green 003

# Step 7: Complete with regression tests
speky complete 003
```

**"Check TDD status"**
```bash
speky test tdd-status           # All specs
speky test tdd-status 003       # Specific spec
```

**"TDD tests are failing, what do I do?"**
- If in RED phase: Good! Tests should fail. Now implement the feature.
- If in GREEN phase: Fix the implementation to make tests pass.

## 🔍 Test Failure Triage (NEW)

When tests fail during implementation, use triage to understand WHY:

**"Tests are failing, what should I do?"**
```bash
speky test triage <spec-id>    # Analyze and categorize failures
```

**Triage Categories:**
| Category | Icon | Action |
|----------|------|--------|
| **Regression** | 🔴 | Fix your implementation - you broke existing behavior |
| **Outdated** | 🟡 | Update the test - spec changed, test expectations are stale |
| **TDD Expected** | 📝 | Continue implementing - TDD test should fail until done |
| **Flaky** | ⚪ | Investigate timing/environment issues |
| **Uncertain** | ❓ | Manual review needed |

**When to Use Triage:**
- ✅ `speky complete` fails due to test failures
- ✅ Regression tests fail after implementing a feature
- ✅ Unsure if failure is your bug or outdated test
- ❌ TDD RED phase (tests SHOULD fail)

**Triage Output Example:**
```
🔴 LIKELY REGRESSIONS (1) - Fix Implementation
   ●●● test_tab_close_saves_state
       Reason: Test covers files you modified: tab_manager.dart
       → Review your changes - you may have broken existing behavior

🟡 LIKELY OUTDATED (2) - Update Tests  
   ●●○ test_max_tabs_is_10
       Reason: Spec mentions changing behavior: "Support up to 20 tabs"
       → Update test to match new spec requirements
```

**Integration with Complete:**
When `speky complete` fails, it now shows a triage hint:
```
❌ Cannot complete: Regression tests failing

🔴 2 likely regression(s) - fix implementation
🟡 1 likely outdated test(s) - update tests

Run 'speky test triage 003' for detailed analysis
```
- Run `speky test tdd-green <id>` to re-check after fixes.

**"I want to complete a TDD spec"**
```bash
speky complete 003
# This will:
# 1. Run TDD tests (must pass)
# 2. Run regression tests (must pass)
# 3. Block completion if any fail
```

## TDD State Reference

| State | Icon | Meaning |
|-------|------|---------|
| `tests_generated` | 📝 | Test task created, waiting for tests |
| `red_confirmed` | 🔴 | Tests created and failing (good!) |
| `implementing` | 🔧 | Implementation in progress |
| `green_passed` | 🟢 | All TDD tests passing |
| `regression_passed` | ✅ | All tests passing, ready to complete |
'''
    
    def _generate_tech_specific_sections(self, tech_stack: dict) -> dict:
        """Generate tech-stack-specific sections for IDE context"""
        sections = {
            "setup_commands": "",
            "detected_stack": "",
            "test_guidelines": "",
            "file_locations": "",
        }
        
        # Detected stack
        detected = []
        if tech_stack.get("flutter"):
            detected.append("- **Flutter/Dart** (frontend)")
        if tech_stack.get("python"):
            detected.append("- **Python** (backend)")
        if tech_stack.get("web"):
            detected.append("- **Web** (TypeScript/JavaScript)")
        sections["detected_stack"] = "\n".join(detected) if detected else "- Not detected yet (run `speky test init`)"
        
        # Setup commands
        setup_cmds = []
        if tech_stack.get("flutter"):
            setup_cmds.append("   - Flutter: `speky test setup flutter-test`")
            setup_cmds.append("   - E2E: `speky test setup patrol`")
        if tech_stack.get("python"):
            setup_cmds.append("   - Python: `speky test setup pytest-cov`")
        if tech_stack.get("web"):
            setup_cmds.append("   - Web E2E: `speky test setup playwright-mcp`")
            setup_cmds.append("   - Web Unit: `speky test setup vitest`")
        sections["setup_commands"] = "\n".join(setup_cmds) if setup_cmds else "   - Run `speky test init` first to detect tech stack"
        
        # Test guidelines
        guidelines = []
        if tech_stack.get("flutter"):
            guidelines.extend([
                "| **Providers/Notifiers** | Unit tests | Test state logic in isolation |",
                "| **Widgets/Pages** | Unit + Widget tests | Test UI rendering and interaction |",
                "| **Repositories/Services** | Unit + Integration | Mock API, test data flow |",
                "| **Models/Entities** | Unit tests | Test serialization, validation |",
            ])
        if tech_stack.get("python"):
            guidelines.extend([
                "| **API endpoints** | Unit + Integration | Test request/response handling |",
                "| **Services/Repositories** | Unit tests | Test business logic |",
                "| **Database models** | Unit + Integration | Test migrations, queries |",
            ])
        sections["test_guidelines"] = "\n".join(guidelines) if guidelines else "| **Logic files** | Unit tests | Fast, isolated |"
        
        # File locations
        locations = []
        if tech_stack.get("flutter"):
            locations.extend([
                "| Flutter Unit/Widget | `frontend/test/` |",
                "| Flutter Integration | `frontend/integration_test/` |",
            ])
        if tech_stack.get("python"):
            locations.extend([
                "| Python Unit | `backend/tests/` |",
                "| Python Integration | `backend/tests/integration/` |",
            ])
        if tech_stack.get("web"):
            locations.extend([
                "| Web Unit | `__tests__/` or `*.test.ts` |",
                "| Web E2E | `e2e/` or `playwright/` |",
            ])
        sections["file_locations"] = "| Platform/Type | Location |\n|---------------|----------|\n" + "\n".join(locations) if locations else "Run `speky test init` to detect project structure"
        
        return sections
    
    def save_ide_context(self):
        """Save IDE context to .speky/testing/ide_context.md"""
        if not self.testing_dir.exists():
            return
        
        context_file = self.testing_dir / IDE_CONTEXT_FILE
        context_content = self.generate_ide_context()
        
        # Check if content changed
        if context_file.exists():
            existing = context_file.read_text()
            # Compare without timestamp line
            existing_lines = [l for l in existing.split('\n') if not l.startswith('> Last Updated:')]
            new_lines = [l for l in context_content.split('\n') if not l.startswith('> Last Updated:')]
            if existing_lines == new_lines:
                return  # No change
        
        context_file.write_text(context_content)
        TestConsole.info(f"Updated IDE context: {context_file}")
    
    def merge_ide_context_to_rules(self):
        """Merge testing IDE context into main IDE rules file.
        Called by main speky.py during command execution.
        """
        context_file = self.testing_dir / IDE_CONTEXT_FILE
        if not context_file.exists():
            return
        
        testing_context = context_file.read_text()
        
        # Find IDE rules file
        rules_files = [
            self.project_root / ".windsurfrules",
            self.project_root / ".cursorrules",
            self.project_root / "CLAUDE.md",
        ]
        
        v3_managed = self._v3_managed_rules_files()
        for rules_file in rules_files:
            if rules_file.exists() and rules_file.name not in v3_managed:
                self._merge_context_to_file(rules_file, testing_context)

    def _v3_managed_rules_files(self) -> set:
        """Instruction files owned by `speky setup` (v3). v3 points agents to the testing context
        through `speky prime` instead of copying it into the file on every command."""
        path = self.project_root / ".speky" / "speky.yaml"
        if not path.exists():
            return set()
        try:
            import yaml
            harnesses = (yaml.safe_load(path.read_text()) or {}).get("harnesses") or []
        except Exception:
            return set()
        return {"CLAUDE.md"} if "claude-code" in harnesses else set()
    
    def _merge_context_to_file(self, rules_file: Path, testing_context: str):
        """Merge testing context into a specific rules file"""
        existing = rules_file.read_text()
        
        # Markers for testing section
        start_marker = "# 🧪 SPEKY Testing Context"
        end_marker = "# END SPEKY Testing Context"
        
        # Check if testing section exists
        if start_marker in existing:
            # Replace the existing section, consuming its end marker(s) so they don't pile up
            import re
            pattern = (f"{re.escape(start_marker)}.*?(?:(?:{re.escape(end_marker)}\\s*)+|$)")
            new_content = re.sub(pattern, lambda _: testing_context + "\n\n" + end_marker + "\n\n",
                                 existing, count=1, flags=re.DOTALL)
        elif "<!-- END SPEKY MANAGED BLOCK -->" in existing:
            # Keep SPEKY text inside SPEKY's managed block, never in the user's part of the file
            new_content = existing.replace(
                "<!-- END SPEKY MANAGED BLOCK -->",
                testing_context + "\n\n" + end_marker + "\n<!-- END SPEKY MANAGED BLOCK -->", 1)
        else:
            # Append at end (before USER RULES if exists)
            user_rules_marker = "# USER RULES"
            if user_rules_marker in existing:
                new_content = existing.replace(
                    user_rules_marker,
                    testing_context + "\n\n" + end_marker + "\n\n" + user_rules_marker
                )
            else:
                new_content = existing + "\n\n" + testing_context + "\n\n" + end_marker + "\n"
        
        if new_content != existing:
            rules_file.write_text(new_content)
    
    def cmd_refresh_context(self, args=None) -> bool:
        """Refresh IDE context for testing"""
        TestConsole.header("Refreshing Testing IDE Context")
        
        if not self.is_initialized():
            TestConsole.error("Test harness not initialized. Run 'speky test init' first.")
            return False
        
        self.save_ide_context()
        self.merge_ide_context_to_rules()
        
        TestConsole.success("IDE context updated!")
        return True
    
    def cmd_refresh_guide(self, args=None) -> bool:
        """Refresh TESTING_GUIDE.md with actual project data (test counts, coverage, structure)"""
        TestConsole.header("Refreshing TESTING_GUIDE.md")
        
        if not self.is_initialized():
            TestConsole.error("Test harness not initialized. Run 'speky test init' first.")
            return False
        
        tech_stack = self._detect_tech_stack()
        
        # Gather actual project data
        TestConsole.step("Gathering test statistics...")
        test_stats = self._gather_test_statistics(tech_stack)
        
        TestConsole.step("Parsing coverage data...")
        coverage_data = self._gather_coverage_data(tech_stack)
        
        TestConsole.step("Scanning test structure...")
        test_structure = self._scan_test_structure(tech_stack)
        
        # Generate comprehensive guide with actual data
        TestConsole.step("Generating comprehensive guide...")
        self._generate_comprehensive_testing_guide(tech_stack, test_stats, coverage_data, test_structure)
        
        TestConsole.success(f"TESTING_GUIDE.md updated with actual project data!")
        TestConsole.info(f"  Tests: {test_stats.get('total', 0)} total")
        TestConsole.info(f"  Coverage: {coverage_data.get('overall', 0):.1f}%")
        
        return True
    
    def _gather_test_statistics(self, tech_stack: dict) -> dict:
        """Gather actual test counts from the project"""
        stats = {"total": 0, "by_platform": {}}
        
        # Count Flutter tests
        if tech_stack.get("flutter"):
            flutter_count = self._count_flutter_tests()
            stats["by_platform"]["flutter"] = flutter_count
            stats["total"] += flutter_count.get("total", 0)
        
        # Count Python tests
        if tech_stack.get("python"):
            python_count = self._count_python_tests()
            stats["by_platform"]["python"] = python_count
            stats["total"] += python_count.get("total", 0)
        
        # Count JavaScript tests
        if tech_stack.get("web"):
            js_count = self._count_javascript_tests()
            stats["by_platform"]["javascript"] = js_count
            stats["total"] += js_count.get("total", 0)
        
        return stats
    
    def _count_flutter_tests(self) -> dict:
        """Count Flutter tests by scanning test files"""
        count = {"total": 0, "unit": 0, "widget": 0, "integration": 0, "files": 0}
        
        # Find Flutter test directory
        flutter_root = None
        for path in [self.project_root, self.project_root / "frontend"]:
            if (path / "pubspec.yaml").exists():
                flutter_root = path
                break
        
        if not flutter_root:
            return count
        
        test_dir = flutter_root / "test"
        if not test_dir.exists():
            return count
        
        # Count test functions in Dart files
        import re
        for test_file in test_dir.rglob("*_test.dart"):
            count["files"] += 1
            try:
                content = test_file.read_text()
                # Count test() and testWidgets() calls
                tests = len(re.findall(r'\btest\s*\(', content))
                widget_tests = len(re.findall(r'\btestWidgets\s*\(', content))
                
                count["total"] += tests + widget_tests
                count["widget"] += widget_tests
                count["unit"] += tests
                
                # Categorize by directory
                rel_path = str(test_file.relative_to(test_dir))
                if "widget" in rel_path.lower():
                    pass  # Already counted as widget
                elif "integration" in rel_path.lower():
                    count["integration"] += tests + widget_tests
            except:
                pass
        
        return count
    
    def _count_python_tests(self) -> dict:
        """Count Python tests by scanning test files"""
        count = {"total": 0, "unit": 0, "integration": 0, "files": 0}
        
        # Find Python test directory
        python_root = None
        for path in [self.project_root, self.project_root / "backend"]:
            if (path / "requirements.txt").exists() or (path / "pytest.ini").exists():
                python_root = path
                break
        
        if not python_root:
            return count
        
        test_dir = python_root / "tests"
        if not test_dir.exists():
            return count
        
        # Count test functions
        import re
        for test_file in test_dir.rglob("test_*.py"):
            count["files"] += 1
            try:
                content = test_file.read_text()
                # Count def test_ and async def test_ functions
                tests = len(re.findall(r'\bdef test_', content))
                async_tests = len(re.findall(r'\basync def test_', content))
                
                count["total"] += tests + async_tests
                
                # Categorize
                rel_path = str(test_file.relative_to(test_dir))
                if "integration" in rel_path.lower():
                    count["integration"] += tests + async_tests
                else:
                    count["unit"] += tests + async_tests
            except:
                pass
        
        return count
    
    def _count_javascript_tests(self) -> dict:
        """Count JavaScript tests by scanning test files"""
        count = {"total": 0, "unit": 0, "integration": 0, "files": 0}
        
        # Find JavaScript test directory
        js_root = None
        for path in [self.project_root, self.project_root / "frontend", self.project_root / "web"]:
            if (path / "package.json").exists():
                js_root = path
                break
        
        if not js_root:
            return count
        
        # Check __tests__ or test directories
        for test_dir_name in ["__tests__", "test", "tests"]:
            test_dir = js_root / test_dir_name
            if test_dir.exists():
                import re
                for test_file in test_dir.rglob("*.test.js"):
                    count["files"] += 1
                    try:
                        content = test_file.read_text()
                        # Count it() and test() calls
                        tests = len(re.findall(r'\bit\s*\(', content))
                        tests += len(re.findall(r'\btest\s*\(', content))
                        count["total"] += tests
                        count["unit"] += tests
                    except:
                        pass
        
        return count
    
    def _gather_coverage_data(self, tech_stack: dict) -> dict:
        """Gather coverage data from existing reports"""
        coverage = {"overall": 0, "by_module": {}}
        
        # Parse Flutter coverage
        if tech_stack.get("flutter"):
            flutter_root = None
            for path in [self.project_root, self.project_root / "frontend"]:
                if (path / "pubspec.yaml").exists():
                    flutter_root = path
                    break
            
            if flutter_root:
                lcov_file = flutter_root / "coverage" / "lcov.info"
                if lcov_file.exists():
                    cov = self._parse_flutter_coverage(lcov_file)
                    if cov is not None:
                        coverage["overall"] = cov
                        coverage["flutter"] = cov
        
        # Parse Python coverage
        if tech_stack.get("python"):
            python_root = None
            for path in [self.project_root, self.project_root / "backend"]:
                if (path / "requirements.txt").exists():
                    python_root = path
                    break
            
            if python_root:
                # Check for .coverage file or coverage.xml
                coverage_file = python_root / ".coverage"
                if coverage_file.exists():
                    # Would need coverage.py to parse, use placeholder
                    coverage["python"] = 0
        
        return coverage
    
    def _scan_test_structure(self, tech_stack: dict) -> dict:
        """Scan actual test directory structure"""
        structure = {"directories": [], "file_count": 0}
        
        if tech_stack.get("flutter"):
            flutter_root = None
            for path in [self.project_root, self.project_root / "frontend"]:
                if (path / "pubspec.yaml").exists():
                    flutter_root = path
                    break
            
            if flutter_root:
                test_dir = flutter_root / "test"
                if test_dir.exists():
                    for subdir in sorted(test_dir.iterdir()):
                        if subdir.is_dir() and not subdir.name.startswith('.'):
                            file_count = len(list(subdir.rglob("*_test.dart")))
                            structure["directories"].append({
                                "name": subdir.name,
                                "path": str(subdir.relative_to(self.project_root)),
                                "files": file_count,
                            })
                            structure["file_count"] += file_count
        
        if tech_stack.get("python"):
            python_root = None
            for path in [self.project_root, self.project_root / "backend"]:
                if (path / "requirements.txt").exists():
                    python_root = path
                    break
            
            if python_root:
                test_dir = python_root / "tests"
                if test_dir.exists():
                    file_count = len(list(test_dir.rglob("test_*.py")))
                    structure["directories"].append({
                        "name": "tests",
                        "path": str(test_dir.relative_to(self.project_root)),
                        "files": file_count,
                    })
                    structure["file_count"] += file_count
        
        return structure
    
    def _generate_comprehensive_testing_guide(self, tech_stack: dict, test_stats: dict, 
                                               coverage_data: dict, test_structure: dict):
        """Generate comprehensive TESTING_GUIDE.md with actual project data"""
        guide_file = self.project_root / "TESTING_GUIDE.md"
        
        # Get project name
        project_name = self.project_root.name.title()
        context_file = self.speky_dir / "context" / "context.json"
        if context_file.exists():
            try:
                context = json.loads(context_file.read_text())
                project_name = context.get("product_name", project_name)
            except:
                pass
        
        # Build platform-specific stats
        platform_stats = []
        for platform, stats in test_stats.get("by_platform", {}).items():
            if stats.get("total", 0) > 0:
                cov = coverage_data.get(platform, 0)
                platform_stats.append(f"- **{platform.title()}:** {stats['total']} tests ({stats.get('files', 0)} files), Coverage: {cov:.1f}%")
        
        platform_stats_str = "\n".join(platform_stats) if platform_stats else "- No tests found yet. Run `speky test gen <spec-id>` to generate tests."
        
        # Build test structure
        structure_lines = []
        for dir_info in test_structure.get("directories", []):
            structure_lines.append(f"- `{dir_info['path']}/` - {dir_info['files']} test files")
        structure_str = "\n".join(structure_lines) if structure_lines else "- No test directories found yet."
        
        # Determine test directories
        frontend_test_dir = "test/"
        backend_test_dir = "tests/"
        
        if tech_stack.get("flutter"):
            for path in [self.project_root, self.project_root / "frontend"]:
                if (path / "pubspec.yaml").exists():
                    if path != self.project_root:
                        frontend_test_dir = "frontend/test/"
                    break
        
        if tech_stack.get("python"):
            for path in [self.project_root, self.project_root / "backend"]:
                if (path / "requirements.txt").exists():
                    if path != self.project_root:
                        backend_test_dir = "backend/tests/"
                    break
        
        # Build quick start commands
        quick_start_commands = ""
        if tech_stack.get("flutter"):
            quick_start_commands += f"cd {frontend_test_dir.rstrip('/').rsplit('/', 1)[0] if '/' in frontend_test_dir else '.'} && flutter test --coverage\n"
        if tech_stack.get("python"):
            quick_start_commands += f"cd {backend_test_dir.rstrip('/').rsplit('/', 1)[0] if '/' in backend_test_dir else '.'} && pytest --cov\n"
        
        # Build tech-specific sections
        frontend_section = ""
        backend_section = ""
        
        if tech_stack.get("flutter"):
            flutter_stats = test_stats.get("by_platform", {}).get("flutter", {})
            frontend_section = self._get_flutter_testing_section_with_stats(frontend_test_dir, flutter_stats, coverage_data.get("flutter", 0))
        
        if tech_stack.get("python"):
            python_stats = test_stats.get("by_platform", {}).get("python", {})
            backend_section = self._get_python_testing_section_with_stats(backend_test_dir, python_stats, coverage_data.get("python", 0))
        
        # Generate the comprehensive guide
        guide_content = f'''# {project_name} Testing Guide

**Complete testing reference for this project**

Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}  
Generated by: SPEKY Testing Integration  
Total Tests: **{test_stats.get('total', 0)}**  
Overall Coverage: **{coverage_data.get('overall', 0):.1f}%**

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Current Test Status](#current-test-status)
3. [Test Structure](#test-structure)
4. [Running Tests](#running-tests)
5. [SPEKY Test Commands](#speky-test-commands)
6. [TDD Workflow](#tdd-workflow)
7. [Coverage Tracking](#coverage-tracking)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Run All Tests

```bash
# Using SPEKY (recommended - auto-detects all tech stacks)
speky test run

# With coverage
speky test run --coverage

# Or manually:
{quick_start_commands.strip()}
```

---

## Current Test Status

### Test Counts by Platform

{platform_stats_str}

### Test Directories

{structure_str}

### Coverage Summary

| Platform | Tests | Files | Coverage | Status |
|----------|-------|-------|----------|--------|
'''
        
        # Add coverage table rows
        for platform, stats in test_stats.get("by_platform", {}).items():
            total = stats.get("total", 0)
            files = stats.get("files", 0)
            cov = coverage_data.get(platform, 0)
            status = "✅" if cov >= 80 else "⚠️" if cov >= 60 else "❌" if total > 0 else "📝"
            guide_content += f"| {platform.title()} | {total} | {files} | {cov:.1f}% | {status} |\n"
        
        guide_content += f'''
**Coverage Legend:** ✅ Good (≥80%) | ⚠️ Moderate (≥60%) | ❌ Low (<60%) | 📝 No tests

---

## Test Structure

```
{self._get_test_structure_diagram(tech_stack, frontend_test_dir, backend_test_dir)}
```

---

{frontend_section}

{backend_section}

## SPEKY Test Commands

SPEKY provides integrated test management for this project.

### Core Testing Commands

```bash
# Initialize test infrastructure
speky test init

# Generate tests for a spec
speky test gen <spec-id>

# Run all tests (auto-detects tech stacks)
speky test run

# Run tests with coverage
speky test run --coverage

# Run tests for specific spec
speky test run --spec <spec-id>

# Check coverage
speky test coverage

# View test status
speky test status

# Link tests to specs
speky test link <test-file> --spec <spec-id>

# Identify test gaps
speky test gaps

# Get test recommendations
speky test recommend

# Refresh test context
speky test refresh-context

# Refresh this guide with latest data
speky test refresh-guide
```

### TDD Commands

```bash
# Start TDD workflow for a spec
speky implement <spec-id> --tdd

# RED phase: verify tests fail (before implementation)
speky test tdd-red <spec-id>

# GREEN phase: verify tests pass (after implementation)
speky test tdd-green <spec-id>

# View TDD status dashboard
speky test tdd-status

# Complete spec with TDD verification
speky complete <spec-id>
```

---

## TDD Workflow

SPEKY supports Test-Driven Development with the **RED-GREEN-REFACTOR** cycle.

### TDD Workflow Diagram

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

### When to Use TDD

**✅ Use TDD for:**
- New features with clear acceptance criteria
- Bug fixes (write failing test first)
- Complex business logic
- Critical functionality

**❌ Skip TDD for:**
- Simple UI tweaks without logic
- Config/documentation changes
- Exploratory/prototype work

---

## Coverage Tracking

### Current Coverage: {coverage_data.get('overall', 0):.1f}%

**Target:** 80% line coverage  
**Minimum:** 60% for new code

### View Coverage

```bash
# SPEKY coverage report
speky test coverage

# Run tests with coverage
speky test run --coverage

# Refresh this guide with latest coverage
speky test refresh-guide
```

### Modular Test Runner Architecture

SPEKY automatically detects and runs tests for multiple tech stacks:

**Detected Tech Stacks:**
{self._format_detected_tech_stacks(tech_stack)}

**Benefits:**
- 🚀 **Auto-detection** - Finds all applicable test runners
- 📊 **Real-time output** - See tests as they run
- 🎯 **Accurate counts** - Actual test numbers
- 🔧 **Extensible** - Easy to add new tech stacks
- 📈 **Coverage parsing** - Automatic coverage extraction

---

## Best Practices

### General

1. **Write tests first** (TDD) for new features
2. **Keep tests fast** - Unit tests < 100ms each
3. **Test one thing** - Each test should verify one behavior
4. **Use descriptive names** - Test names should describe what's being tested
5. **Mock external dependencies** - Don't test third-party code
6. **Run tests before commit** - Never commit failing tests

### Test Organization

```
test/
├── unit/           # Fast, isolated tests (70% of suite)
├── widget/         # UI component tests (20% of suite)
└── integration/    # End-to-end tests (10% of suite)
```

### Coverage Guidelines

| File Type | Recommended Coverage |
|-----------|---------------------|
| Business Logic | 90%+ |
| Data Models | 85%+ |
| UI Components | 70%+ |
| Utilities | 80%+ |
| Generated Code | Skip |

---

## Troubleshooting

### Tests Not Running

```bash
# Refresh SPEKY test context
speky test refresh-context

# Check test harness status
speky test status
```

### Coverage Not Generating

```bash
# Run with explicit coverage flag
speky test run --coverage

# Check if coverage tools are installed
# Flutter: Built-in
# Python: pip install pytest-cov
# JavaScript: npm install --save-dev jest
```

### TDD Phase Issues

**RED phase passes (should fail):**
- Tests aren't testing new code
- Implementation already exists
- Check test assertions

**GREEN phase fails:**
- Implementation incomplete
- Check error messages
- Run specific failing test

### Guide Out of Date

```bash
# Refresh guide with latest test data
speky test refresh-guide
```

---

## Resources

### Documentation

- **SPEKY Testing:** `.speky/testing/`
- **IDE Context:** `.speky/context/IDE_CONTEXT.md`
- **Test Tasks:** `.speky/testing/tasks/`

### Related Files

- **Test Config:** `.speky/testing/config.yaml`
- **Coverage Data:** `.speky/testing/coverage/`
- **Test Tasks:** `.speky/testing/tasks/`

---

**Generated by SPEKY Testing Integration**  
**Last Updated:** {datetime.now().strftime("%Y-%m-%d %H:%M")}  
**Refresh with:** `speky test refresh-guide`
'''
        
        # Write the guide
        guide_file.write_text(guide_content)
    
    def _get_flutter_testing_section_with_stats(self, test_dir: str, stats: dict, coverage: float) -> str:
        """Generate Flutter testing section with actual stats"""
        total = stats.get("total", 0)
        files = stats.get("files", 0)
        unit = stats.get("unit", 0)
        widget = stats.get("widget", 0)
        
        return f'''## Frontend Testing (Flutter)

### Current Status

- **Total Tests:** {total}
- **Test Files:** {files}
- **Unit Tests:** {unit}
- **Widget Tests:** {widget}
- **Coverage:** {coverage:.1f}%

### Running Flutter Tests

```bash
# Run all tests
cd {test_dir.rstrip('/').rsplit('/', 1)[0] if '/' in test_dir else '.'}
flutter test

# Run with coverage
flutter test --coverage

# Run specific test file
flutter test {test_dir}unit/models/example_test.dart

# Run tests by directory
flutter test {test_dir}unit/

# Run with verbose output
flutter test --verbose
```

### Coverage Analysis

```bash
# Generate coverage report
flutter test --coverage

# View summary (requires lcov)
lcov --summary coverage/lcov.info

# Generate HTML report
genhtml coverage/lcov.info -o coverage/html
open coverage/html/index.html
```

### Flutter Test Best Practices

1. **Use `setUp` and `tearDown`** for test isolation
2. **Mock platform channels** for native dependencies
3. **Use `TestWidgetsFlutterBinding.ensureInitialized()`** for widget tests
4. **Group related tests** with `group()`
5. **Use descriptive test names** that explain the behavior

---

'''
    
    def _get_python_testing_section_with_stats(self, test_dir: str, stats: dict, coverage: float) -> str:
        """Generate Python testing section with actual stats"""
        total = stats.get("total", 0)
        files = stats.get("files", 0)
        unit = stats.get("unit", 0)
        integration = stats.get("integration", 0)
        
        return f'''## Backend Testing (Python)

### Current Status

- **Total Tests:** {total}
- **Test Files:** {files}
- **Unit Tests:** {unit}
- **Integration Tests:** {integration}
- **Coverage:** {coverage:.1f}%

### Running Python Tests

```bash
# Run all tests
cd {test_dir.rstrip('/').rsplit('/', 1)[0] if '/' in test_dir else '.'}
pytest

# Run with coverage
pytest --cov --cov-report=term-missing

# Run specific test file
pytest {test_dir}test_example.py

# Run specific test function
pytest {test_dir}test_example.py::test_function_name

# Run with verbose output
pytest -v

# Run with print statements visible
pytest -s
```

### Coverage Analysis

```bash
# Generate coverage report
pytest --cov --cov-report=html

# View HTML report
open htmlcov/index.html
```

### Python Test Best Practices

1. **Use fixtures** for common setup (`@pytest.fixture`)
2. **Use markers** for test categories (`@pytest.mark.unit`)
3. **Parametrize tests** for multiple inputs (`@pytest.mark.parametrize`)
4. **Use `pytest-asyncio`** for async tests
5. **Mock external services** with `pytest-mock`

---

'''
    
    # =========================================================================
    # TEST RECOMMENDATION ENGINE
    # =========================================================================
    
    def get_changed_files(self, spec_id: str = None) -> List[dict]:
        """Get list of changed files from git with metadata"""
        try:
            # Get changed files compared to last commit
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
            )
            
            if result.returncode != 0:
                # Try unstaged changes
                result = subprocess.run(
                    ["git", "diff", "--name-only"],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                )
            
            files = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    file_path = line.strip()
                    files.append({
                        "path": file_path,
                        "type": self._classify_file(file_path),
                        "extension": Path(file_path).suffix,
                    })
            
            return files
        except Exception:
            return []
    
    def _classify_file(self, file_path: str) -> str:
        """Classify a file by its likely purpose"""
        path_lower = file_path.lower()
        
        # Documentation
        if path_lower.endswith(('.md', '.txt', '.rst')):
            return "documentation"
        
        # Configuration
        if any(x in path_lower for x in ['config', 'settings', '.yaml', '.yml', '.json', '.toml']):
            return "configuration"
        
        # Tests (shouldn't need tests for tests)
        if any(x in path_lower for x in ['test', 'spec', '__tests__']):
            return "test"
        
        # Flutter/Dart
        if path_lower.endswith('.dart'):
            if any(x in path_lower for x in ['widget', 'page', 'screen', 'view', 'component']):
                return "ui_component"
            if any(x in path_lower for x in ['provider', 'notifier', 'controller', 'bloc', 'cubit']):
                return "state_management"
            if any(x in path_lower for x in ['repository', 'service', 'api', 'client']):
                return "data_layer"
            if any(x in path_lower for x in ['model', 'entity', 'dto']):
                return "model"
            return "logic"
        
        # Python
        if path_lower.endswith('.py'):
            if any(x in path_lower for x in ['view', 'route', 'endpoint', 'api']):
                return "api_endpoint"
            if any(x in path_lower for x in ['model', 'schema']):
                return "model"
            if any(x in path_lower for x in ['service', 'repository']):
                return "data_layer"
            return "logic"
        
        # TypeScript/JavaScript
        if path_lower.endswith(('.ts', '.tsx', '.js', '.jsx')):
            if any(x in path_lower for x in ['component', 'page', 'view']):
                return "ui_component"
            if any(x in path_lower for x in ['hook', 'store', 'context']):
                return "state_management"
            if any(x in path_lower for x in ['api', 'service', 'client']):
                return "data_layer"
            return "logic"
        
        return "other"
    
    def recommend_tests(self, spec_id: str = None) -> dict:
        """Generate test recommendations based on changed files"""
        changed_files = self.get_changed_files(spec_id)
        
        if not changed_files:
            return {
                "risk_level": "NONE",
                "changed_files": 0,
                "recommendations": [],
                "skip_reason": "No changed files detected",
                "command": None,
            }
        
        # Classify changes
        file_types = {}
        for f in changed_files:
            ft = f["type"]
            file_types[ft] = file_types.get(ft, 0) + 1
        
        # Check for docs-only changes
        if set(file_types.keys()) <= {"documentation", "configuration", "test"}:
            return {
                "risk_level": "NONE",
                "changed_files": len(changed_files),
                "recommendations": [],
                "skip_reason": "Only documentation/config/test files changed",
                "command": None,
            }
        
        # Build recommendations
        recommendations = []
        test_types = set()
        
        # Logic changes -> Unit tests
        if any(ft in file_types for ft in ["logic", "data_layer", "model", "state_management"]):
            recommendations.append({
                "type": "unit",
                "reason": "Logic/data layer changes detected",
                "priority": "HIGH",
                "estimated_time": "2-5 min",
                "files": [f["path"] for f in changed_files if f["type"] in ["logic", "data_layer", "model", "state_management"]],
            })
            test_types.add("unit")
        
        # UI changes -> Widget/Component tests
        if "ui_component" in file_types:
            recommendations.append({
                "type": "widget",
                "reason": "UI component changes detected",
                "priority": "HIGH",
                "estimated_time": "3-5 min",
                "files": [f["path"] for f in changed_files if f["type"] == "ui_component"],
            })
            test_types.add("widget")
        
        # API changes -> Integration tests
        if "api_endpoint" in file_types or "data_layer" in file_types:
            recommendations.append({
                "type": "integration",
                "reason": "API/data layer changes detected",
                "priority": "MEDIUM",
                "estimated_time": "5-10 min",
                "files": [f["path"] for f in changed_files if f["type"] in ["api_endpoint", "data_layer"]],
            })
            test_types.add("integration")
        
        # Multiple component types -> Consider E2E
        if len([ft for ft in file_types if ft in ["ui_component", "state_management", "data_layer"]]) >= 2:
            recommendations.append({
                "type": "e2e",
                "reason": "Multi-layer changes (consider for critical paths only)",
                "priority": "LOW",
                "estimated_time": "10-15 min",
                "files": [],  # E2E tests the flow, not specific files
            })
            # Don't add e2e by default - it's optional
        
        # Calculate risk level
        if "ui_component" in file_types and ("state_management" in file_types or "data_layer" in file_types):
            risk_level = "HIGH"
        elif len(file_types) > 2:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
        
        # Build command
        if test_types:
            test_type_str = ",".join(sorted(test_types))
            command = f"speky test run --type {test_type_str}"
            if spec_id:
                command += f" --spec {spec_id}"
        else:
            command = None
        
        return {
            "risk_level": risk_level,
            "changed_files": len(changed_files),
            "file_breakdown": file_types,
            "recommendations": recommendations,
            "skip_reason": None,
            "command": command,
        }
    
    def cmd_test_recommend(self, args) -> bool:
        """Show test recommendations based on changes"""
        spec_id = getattr(args, 'spec_id', None) or getattr(args, 'target', None)
        
        TestConsole.header(f"Test Recommendations{f' for Spec {spec_id}' if spec_id else ''}")
        
        recommendations = self.recommend_tests(spec_id)
        
        # Display results
        print(f"Changed Files: {recommendations['changed_files']}")
        print(f"Risk Level: {recommendations['risk_level']}")
        
        if recommendations.get("skip_reason"):
            print(f"\n⏭️  Skip Reason: {recommendations['skip_reason']}")
            TestConsole.success("No tests needed for these changes!")
            return True
        
        if recommendations.get("file_breakdown"):
            print(f"\nFile Breakdown:")
            for ft, count in recommendations["file_breakdown"].items():
                print(f"  • {ft}: {count} file(s)")
        
        print("\nRecommended Tests:")
        for rec in recommendations.get("recommendations", []):
            priority_icon = "🔴" if rec["priority"] == "HIGH" else "🟡" if rec["priority"] == "MEDIUM" else "🟢"
            print(f"\n{priority_icon} {rec['type'].upper()} Tests ({rec['priority']})")
            print(f"   Reason: {rec['reason']}")
            print(f"   Estimated: {rec['estimated_time']}")
            if rec.get("files"):
                print(f"   Files:")
                for f in rec["files"][:5]:
                    print(f"     • {f}")
                if len(rec["files"]) > 5:
                    print(f"     ... and {len(rec['files']) - 5} more")
        
        if recommendations.get("command"):
            print(f"\n{'─'*50}")
            print(f"Run: {recommendations['command']}")
        
        return True
    
    # =========================================================================
    # DYNAMIC SETUP GUIDE FETCHING
    # =========================================================================
    
    SETUP_GUIDE_SOURCES = {
        "playwright-mcp": {
            "name": "Playwright MCP for Browser Automation",
            "search_query": "playwright MCP server setup windsurf cursor IDE 2024",
            "fallback_url": "https://github.com/anthropics/mcp-servers",
            "platform": "web",
        },
        "patrol": {
            "name": "Patrol for Flutter E2E Testing",
            "search_query": "patrol flutter E2E testing setup 2024",
            "fallback_url": "https://patrol.leancode.co/docs/getting-started",
            "platform": "mobile",
        },
        "pytest-cov": {
            "name": "pytest-cov for Python Coverage",
            "search_query": "pytest-cov coverage setup python 2024",
            "fallback_url": "https://pytest-cov.readthedocs.io/",
            "platform": "python",
        },
        "flutter-test": {
            "name": "Flutter Testing Framework",
            "search_query": "flutter test unit widget testing setup 2024",
            "fallback_url": "https://docs.flutter.dev/testing",
            "platform": "flutter",
        },
        "vitest": {
            "name": "Vitest for JavaScript/TypeScript Testing",
            "search_query": "vitest setup configuration 2024",
            "fallback_url": "https://vitest.dev/guide/",
            "platform": "web",
        },
        "maestro": {
            "name": "Maestro for Mobile E2E Testing",
            "search_query": "maestro mobile E2E testing setup 2024",
            "fallback_url": "https://maestro.mobile.dev/",
            "platform": "mobile",
        },
    }
    
    def _get_cache_path(self, tool: str) -> Path:
        """Get cache file path for a setup guide"""
        cache_dir = self.testing_dir / CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{tool}.json"
    
    def _is_cache_valid(self, cache_file: Path) -> bool:
        """Check if cached guide is still valid (< 60 days old)"""
        if not cache_file.exists():
            return False
        
        try:
            cache_data = json.loads(cache_file.read_text())
            cached_date = datetime.fromisoformat(cache_data.get("cached_at", "2000-01-01"))
            age_days = (datetime.now() - cached_date).days
            return age_days < SETUP_GUIDE_CACHE_TTL_DAYS
        except Exception:
            return False
    
    def _load_cached_guide(self, tool: str) -> Optional[dict]:
        """Load cached setup guide if valid"""
        cache_file = self._get_cache_path(tool)
        if self._is_cache_valid(cache_file):
            try:
                return json.loads(cache_file.read_text())
            except Exception:
                pass
        return None
    
    def _save_guide_to_cache(self, tool: str, guide: dict):
        """Save setup guide to cache"""
        cache_file = self._get_cache_path(tool)
        guide["cached_at"] = datetime.now().isoformat()
        cache_file.write_text(json.dumps(guide, indent=2))
    
    def _fetch_setup_guide(self, tool: str, refresh: bool = False) -> dict:
        """Fetch setup guide - from cache or generate dynamically"""
        if not refresh:
            cached = self._load_cached_guide(tool)
            if cached:
                return cached
        
        tool_info = self.SETUP_GUIDE_SOURCES.get(tool)
        if not tool_info:
            return {
                "name": tool,
                "error": f"Unknown tool: {tool}",
                "available_tools": list(self.SETUP_GUIDE_SOURCES.keys()),
            }
        
        # Generate guide (in production, would search web for latest)
        guide = self._generate_setup_guide(tool, tool_info)
        
        # Cache it
        self._save_guide_to_cache(tool, guide)
        
        return guide
    
    def _generate_setup_guide(self, tool: str, tool_info: dict) -> dict:
        """Generate setup guide for a tool.
        In production, this would use web search/Context7 for latest docs.
        For now, provides structured templates that can be enhanced.
        """
        name = tool_info["name"]
        platform = tool_info["platform"]
        fallback_url = tool_info["fallback_url"]
        
        # Platform-specific guides
        guides = {
            "playwright-mcp": {
                "name": name,
                "platform": platform,
                "documentation": fallback_url,
                "prerequisites": [
                    "Node.js 18+ installed",
                    "Windsurf/Cursor IDE with MCP support",
                    "npm or npx available in PATH",
                ],
                "steps": [
                    {
                        "step": 1,
                        "title": "Install Playwright MCP Server",
                        "command": "npm install -g @anthropic/mcp-server-playwright",
                        "notes": "Or use npx for on-demand execution",
                    },
                    {
                        "step": 2,
                        "title": "Configure IDE MCP Settings",
                        "command": None,
                        "notes": "Add to ~/.windsurf/mcp.json or ~/.cursor/mcp.json:\n{\n  \"playwright\": {\n    \"command\": \"npx\",\n    \"args\": [\"@anthropic/mcp-server-playwright\"]\n  }\n}",
                    },
                    {
                        "step": 3,
                        "title": "Restart IDE",
                        "command": None,
                        "notes": "Close and reopen your IDE to load MCP configuration",
                    },
                    {
                        "step": 4,
                        "title": "Verify Installation",
                        "command": None,
                        "notes": "Check MCP panel in IDE for 'playwright' server",
                    },
                ],
                "verification": "In IDE, check MCP panel shows 'playwright' as connected",
                "troubleshooting": [
                    "If MCP not connecting, check Node.js version: node --version",
                    "Ensure npx is available: npx --version",
                    "Check MCP config file syntax is valid JSON",
                ],
            },
            "patrol": {
                "name": name,
                "platform": platform,
                "documentation": fallback_url,
                "prerequisites": [
                    "Flutter SDK installed",
                    "Android SDK / Xcode for mobile testing",
                    "Physical device or emulator",
                ],
                "steps": [
                    {
                        "step": 1,
                        "title": "Add patrol to pubspec.yaml",
                        "command": "flutter pub add patrol --dev",
                        "notes": "Add as dev dependency",
                    },
                    {
                        "step": 2,
                        "title": "Add patrol_cli globally",
                        "command": "dart pub global activate patrol_cli",
                        "notes": "For running patrol commands",
                    },
                    {
                        "step": 3,
                        "title": "Create patrol config",
                        "command": "patrol bootstrap",
                        "notes": "Creates patrol.yaml configuration",
                    },
                    {
                        "step": 4,
                        "title": "Create test file",
                        "command": None,
                        "notes": "Create integration_test/app_test.dart with patrol imports",
                    },
                ],
                "verification": "patrol test -t integration_test/app_test.dart",
                "troubleshooting": [
                    "Ensure Android SDK path is set: echo $ANDROID_HOME",
                    "For iOS: xcode-select --install",
                    "Check Flutter doctor: flutter doctor -v",
                ],
            },
            "pytest-cov": {
                "name": name,
                "platform": platform,
                "documentation": fallback_url,
                "prerequisites": [
                    "Python 3.8+ installed",
                    "pip available",
                    "pytest installed",
                ],
                "steps": [
                    {
                        "step": 1,
                        "title": "Install pytest-cov",
                        "command": "pip install pytest-cov",
                        "notes": "Or add to requirements.txt: pytest-cov>=4.0",
                    },
                    {
                        "step": 2,
                        "title": "Run tests with coverage",
                        "command": "pytest --cov=app --cov-report=html",
                        "notes": "Replace 'app' with your package name",
                    },
                    {
                        "step": 3,
                        "title": "View HTML report",
                        "command": "open htmlcov/index.html",
                        "notes": "Or: python -m http.server --directory htmlcov",
                    },
                ],
                "verification": "pytest --cov=app should show coverage percentages",
                "troubleshooting": [
                    "If coverage shows 0%, check package name matches your code structure",
                    "Use --cov-config=.coveragerc for custom configuration",
                ],
            },
        }
        
        # Return specific guide or generic template
        if tool in guides:
            return guides[tool]
        
        # Generic template for unknown tools
        return {
            "name": name,
            "platform": platform,
            "documentation": fallback_url,
            "prerequisites": ["Check official documentation"],
            "steps": [
                {
                    "step": 1,
                    "title": "Visit Documentation",
                    "command": None,
                    "notes": f"See: {fallback_url}",
                },
            ],
            "verification": "Follow official getting started guide",
            "troubleshooting": ["Check official documentation for help"],
            "note": "This is a fallback guide. Run with --refresh to fetch latest.",
        }
    
    def cmd_test_setup(self, args) -> bool:
        """Show setup guide for a testing tool"""
        target = getattr(args, 'target', None)
        refresh = getattr(args, 'refresh', False)
        
        if not target:
            TestConsole.header("Available Setup Guides")
            print("\nTools with setup guides:")
            for tool, info in self.SETUP_GUIDE_SOURCES.items():
                print(f"  • {tool}: {info['name']}")
            print("\nUsage: speky test setup <tool>")
            print("Example: speky test setup playwright-mcp")
            return True
        
        TestConsole.header(f"Setup Guide: {target}")
        
        guide = self._fetch_setup_guide(target, refresh=refresh)
        
        if guide.get("error"):
            TestConsole.error(guide["error"])
            if guide.get("available_tools"):
                print("\nAvailable tools:")
                for tool in guide["available_tools"]:
                    print(f"  • {tool}")
            return False
        
        # Display guide
        cache_file = self._get_cache_path(target)
        cache_info = ""
        if cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text())
                cached_at = cache_data.get("cached_at", "Unknown")[:10]
                expires = datetime.fromisoformat(cache_data.get("cached_at", "2000-01-01"))
                expires_at = (expires + __import__('datetime').timedelta(days=SETUP_GUIDE_CACHE_TTL_DAYS)).strftime("%Y-%m-%d")
                cache_info = f"\nCached: {cached_at} (expires: {expires_at})"
            except Exception:
                pass
        
        print(f"📘 {guide.get('name', target)}")
        print(f"Platform: {guide.get('platform', 'Unknown')}")
        print(f"Documentation: {guide.get('documentation', 'N/A')}{cache_info}")
        
        # Prerequisites
        print("\n📋 Prerequisites:")
        for prereq in guide.get("prerequisites", []):
            print(f"  • {prereq}")
        
        # Steps
        print("\n📝 Steps:")
        for step in guide.get("steps", []):
            print(f"\n  {step['step']}. {step['title']}")
            if step.get("command"):
                print(f"     $ {step['command']}")
            if step.get("notes"):
                for line in step["notes"].split('\n'):
                    print(f"     {line}")
        
        # Verification
        if guide.get("verification"):
            print(f"\n✅ Verification:")
            print(f"   {guide['verification']}")
        
        # Troubleshooting
        if guide.get("troubleshooting"):
            print(f"\n🔧 Troubleshooting:")
            for tip in guide["troubleshooting"]:
                print(f"   • {tip}")
        
        print(f"\n{'─'*50}")
        print(f"Run with --refresh to fetch latest guide")
        
        return True
    
    # =========================================================================
    # UPDATED COMMAND ROUTER
    # =========================================================================
    
    def cmd_test(self, args) -> bool:
        """Main test command router"""
        action = getattr(args, 'action', None)
        
        if action == "init":
            result = self.cmd_test_init(args)
            # Auto-generate IDE context after init
            if result:
                self.save_ide_context()
            return result
        elif action == "gen":
            return self.cmd_test_gen(args)
        elif action == "run":
            return self.cmd_test_run(args)
        elif action == "coverage":
            return self.cmd_test_coverage(args)
        elif action == "status":
            return self.cmd_test_status(args)
        elif action == "e2e":
            return self.cmd_test_e2e(args)
        elif action == "link":
            return self.cmd_test_link(args)
        elif action == "gaps":
            return self.cmd_test_gaps(args)
        elif action == "recommend":
            return self.cmd_test_recommend(args)
        elif action == "setup":
            return self.cmd_test_setup(args)
        elif action == "refresh-context":
            return self.cmd_refresh_context(args)
        elif action == "refresh-guide":
            return self.cmd_refresh_guide(args)
        elif action == "tdd-red":
            return self.cmd_tdd_red(args)
        elif action == "tdd-green":
            return self.cmd_tdd_green(args)
        elif action == "tdd-status":
            return self.cmd_tdd_status(args)
        elif action == "complete":
            return self.cmd_test_complete(args)
        elif action == "triage":
            return self.cmd_triage(args)
        else:
            TestConsole.error(f"Unknown test action: {action}")
            return False
    
    # =========================================================================
    # TDD COMMAND IMPLEMENTATIONS
    # =========================================================================
    
    def cmd_tdd_red(self, args) -> bool:
        """Run TDD RED phase - verify tests fail"""
        target = getattr(args, 'target', None)
        if not target:
            TestConsole.error("Please specify a spec ID: speky test tdd-red <spec-id>")
            return False
        
        result = self.run_red_phase(target)
        
        if result.get("next_steps"):
            print("\nNext Steps:")
            for step in result["next_steps"]:
                print(f"  {step}")
        
        return result.get("success", False)
    
    def cmd_tdd_green(self, args) -> bool:
        """Run TDD GREEN phase - verify tests pass"""
        target = getattr(args, 'target', None)
        if not target:
            TestConsole.error("Please specify a spec ID: speky test tdd-green <spec-id>")
            return False
        
        result = self.run_green_phase(target)
        
        if result.get("next_steps"):
            print("\nNext Steps:")
            for step in result["next_steps"]:
                print(f"  {step}")
        
        return result.get("success", False)
    
    def cmd_tdd_status(self, args) -> bool:
        """Show TDD status for a spec or all specs"""
        target = getattr(args, 'target', None)
        spec_id = getattr(args, 'spec_id', None) or target
        
        TestConsole.header("TDD Status Dashboard")
        
        if spec_id:
            # Show status for specific spec
            tdd_state = self._get_tdd_state(spec_id)
            self._display_tdd_status_for_spec(spec_id, tdd_state)
        else:
            # Show status for all specs with TDD enabled
            self._display_all_tdd_status()
        
        return True
    
    def cmd_test_complete(self, args) -> bool:
        """Mark test task as complete"""
        target = getattr(args, 'target', None)
        if not target:
            TestConsole.error("Please specify a test task ID: speky test complete <task-id>")
            return False
        
        # Extract spec ID from task ID (T003-tdd -> 003)
        spec_id = target.replace("T", "").replace("-tdd", "")
        
        TestConsole.info(f"Marking test task {target} as complete")
        
        # Move task to completed
        active_task = self.tasks_dir / f"T{spec_id}-tdd"
        completed_task = self.tasks_dir / "completed" / f"T{spec_id}-tdd"
        
        if active_task.exists():
            completed_task.parent.mkdir(parents=True, exist_ok=True)
            active_task.rename(completed_task)
            TestConsole.success(f"Test task {target} marked as complete")
        else:
            TestConsole.warning(f"Test task {target} not found in active tasks")
        
        return True
    
    def _display_tdd_status_for_spec(self, spec_id: str, tdd_state: dict):
        """Display TDD status for a single spec"""
        print(f"\nSpec: {spec_id}")
        print("=" * 40)
        
        if not tdd_state.get("enabled"):
            print("  TDD: Not enabled")
            print(f"  Enable with: speky implement {spec_id} --tdd")
            return
        
        state = tdd_state.get("state", "unknown")
        state_icon = {
            TDDState.TESTS_GENERATED.value: "📝",
            TDDState.RED_CONFIRMED.value: "🔴",
            TDDState.IMPLEMENTING.value: "🔧",
            TDDState.GREEN_PASSED.value: "🟢",
            TDDState.REGRESSION_PASSED.value: "✅",
        }.get(state, "❓")
        
        print(f"  State: {state_icon} {state}")
        print(f"  Started: {tdd_state.get('started_at', 'Unknown')[:10]}")
        
        # Test results
        tests = tdd_state.get("tests", {})
        if tests.get("total", 0) > 0:
            print(f"\n  TDD Tests:")
            print(f"    Total: {tests.get('total', 0)}")
            print(f"    Passed: {tests.get('passed', 0)}")
            print(f"    Failed: {tests.get('failed', 0)}")
            print(f"    Last Run: {tests.get('last_run', 'Never')[:16] if tests.get('last_run') else 'Never'}")
        
        # Linked files
        linked_files = tests.get("linked_files", [])
        if linked_files:
            print(f"\n  Linked Test Files:")
            for f in linked_files[:5]:
                print(f"    • {f}")
            if len(linked_files) > 5:
                print(f"    ... and {len(linked_files) - 5} more")
        
        # Regression results
        regression = tdd_state.get("regression", {})
        if regression.get("total", 0) > 0:
            print(f"\n  Regression Tests:")
            print(f"    Total: {regression.get('total', 0)}")
            print(f"    Passed: {regression.get('passed', 0)}")
            print(f"    Failed: {regression.get('failed', 0)}")
    
    # =========================================================================
    # TEST FAILURE TRIAGE
    # =========================================================================
    
    def cmd_triage(self, args) -> bool:
        """Analyze failing tests and categorize them as regressions vs outdated tests"""
        target = getattr(args, 'target', None)
        spec_id = getattr(args, 'spec_id', None) or target
        
        if not spec_id:
            TestConsole.error("Please specify a spec ID: speky test triage <spec-id>")
            return False
        
        TestConsole.header(f"Test Failure Triage: Spec {spec_id}")
        
        # Step 1: Run tests and collect failures
        TestConsole.step("Running tests to collect failures...")
        runners = get_available_runners(self.project_root)
        
        if not runners:
            TestConsole.error("No test runners detected for this project")
            return False
        
        all_failures = []
        for runner in runners:
            result = runner.run_tests()
            if result.failed > 0:
                # Extract failure details from output
                failures = self._extract_failing_tests(runner.name, result.output)
                all_failures.extend(failures)
        
        if not all_failures:
            TestConsole.success("All tests passing! No triage needed.")
            return True
        
        TestConsole.info(f"Found {len(all_failures)} failing tests")
        
        # Step 2: Gather context for analysis
        TestConsole.step("Gathering context for analysis...")
        spec_content = self._load_spec_content(spec_id)
        modified_files = self._get_modified_files_for_spec(spec_id)
        tdd_state = self._get_tdd_state(spec_id)
        tdd_test_files = tdd_state.get("tests", {}).get("linked_files", [])
        
        # Step 3: Categorize each failure
        TestConsole.step("Analyzing failures...")
        summary = TriageSummary(spec_id)
        
        for failure in all_failures:
            result = self._categorize_test_failure(
                failure=failure,
                spec_content=spec_content,
                modified_files=modified_files,
                tdd_test_files=tdd_test_files,
                tdd_enabled=tdd_state.get("enabled", False)
            )
            summary.add_result(result)
        
        # Step 4: Display results
        self._display_triage_results(summary)
        
        return True
    
    def _extract_failing_tests(self, runner_name: str, output: str) -> List[dict]:
        """Extract failing test details from test runner output"""
        failures = []
        import re
        
        if runner_name == "flutter":
            # Parse Flutter test output for failures
            # Pattern: "00:05 +10 -2: test/some_test.dart: test description"
            # Or error blocks starting with "══╡ EXCEPTION CAUGHT BY..."
            test_pattern = re.compile(r'(?:FAILED|EXCEPTION).*?(?:test/\S+\.dart).*?(?::\s*(.+))?', re.MULTILINE)
            file_pattern = re.compile(r'(test/\S+\.dart)')
            
            # Simpler approach: look for test file paths in error context
            for match in file_pattern.finditer(output):
                test_file = match.group(1)
                # Extract test name from nearby context
                start = max(0, match.start() - 200)
                end = min(len(output), match.end() + 200)
                context = output[start:end]
                
                # Try to find test name
                name_match = re.search(r"'([^']+)'|\"([^\"]+)\"|test\s+(\w+)", context)
                test_name = name_match.group(1) or name_match.group(2) or name_match.group(3) if name_match else "unknown_test"
                
                failures.append({
                    "name": test_name,
                    "file": test_file,
                    "runner": runner_name,
                    "error_context": context.strip(),
                })
        
        elif runner_name == "pytest":
            # Parse pytest output for failures
            # Pattern: "FAILED test_file.py::test_name - AssertionError"
            pattern = re.compile(r'FAILED\s+(\S+)::(\S+)', re.MULTILINE)
            for match in pattern.finditer(output):
                test_file = match.group(1)
                test_name = match.group(2)
                
                # Get error context
                start = match.start()
                end = min(len(output), match.end() + 500)
                context = output[start:end]
                
                failures.append({
                    "name": test_name,
                    "file": test_file,
                    "runner": runner_name,
                    "error_context": context.strip(),
                })
        
        elif runner_name == "jest":
            # Parse Jest output for failures
            # Pattern: "● Test Suite › test name"
            pattern = re.compile(r'●\s+(.+?)\s+›\s+(.+?)(?:\n|$)', re.MULTILINE)
            for match in pattern.finditer(output):
                suite_name = match.group(1)
                test_name = match.group(2)
                
                # Get error context
                start = match.start()
                end = min(len(output), match.end() + 500)
                context = output[start:end]
                
                failures.append({
                    "name": test_name,
                    "file": suite_name,  # Jest doesn't always show file path
                    "runner": runner_name,
                    "error_context": context.strip(),
                })
        
        # Deduplicate
        seen = set()
        unique_failures = []
        for f in failures:
            key = f"{f['file']}::{f['name']}"
            if key not in seen:
                seen.add(key)
                unique_failures.append(f)
        
        return unique_failures
    
    def _load_spec_content(self, spec_id: str) -> str:
        """Load spec or story content for analysis"""
        # Try specs directory first
        spec_dir = self.speky_dir / "specs"
        for d in spec_dir.iterdir():
            if d.is_dir() and d.name.startswith(spec_id):
                spec_file = d / "spec.md"
                if spec_file.exists():
                    return spec_file.read_text()
        
        # If not found in specs, try stories directory
        stories_dir = self.speky_dir / "stories"
        if stories_dir.exists():
            for d in stories_dir.iterdir():
                if d.is_dir() and (d.name.startswith(f"{spec_id}-") or spec_id in d.name):
                    story_file = d / "story.md"
                    if story_file.exists():
                        return story_file.read_text()
        
        return ""
    
    def _get_modified_files_for_spec(self, spec_id: str) -> List[str]:
        """Get list of files modified for this spec or story (from git or status.json)"""
        modified = []
        
        # Try to get from spec status.json
        spec_dir = self.speky_dir / "specs"
        for d in spec_dir.iterdir():
            if d.is_dir() and d.name.startswith(spec_id):
                status_file = d / "status.json"
                if status_file.exists():
                    try:
                        status = json.loads(status_file.read_text())
                        modified = status.get("modified_files", [])
                        if modified:
                            return modified
                    except:
                        pass
        
        # If not found in specs, try stories directory
        stories_dir = self.speky_dir / "stories"
        if stories_dir.exists():
            for d in stories_dir.iterdir():
                if d.is_dir() and (d.name.startswith(f"{spec_id}-") or spec_id in d.name):
                    status_file = d / "status.json"
                    if status_file.exists():
                        try:
                            status = json.loads(status_file.read_text())
                            modified = status.get("affected_files", []) or status.get("modified_files", [])
                            if modified:
                                return modified
                        except:
                            pass
        
        # Fallback: get uncommitted changes from git
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                modified = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
        except:
            pass
        
        return modified
    
    def _categorize_test_failure(self, failure: dict, spec_content: str,
                                  modified_files: List[str], tdd_test_files: List[str],
                                  tdd_enabled: bool) -> TriageResult:
        """Categorize a single test failure using rule-based logic"""
        test_name = failure.get("name", "unknown")
        test_file = failure.get("file", "unknown")
        error_context = failure.get("error_context", "")
        
        # Rule 1: TDD test that's expected to fail
        if tdd_enabled and any(tdd_file in test_file for tdd_file in tdd_test_files):
            return TriageResult(
                test_name=test_name,
                test_file=test_file,
                category=TriageCategory.TDD_EXPECTED,
                confidence=0.9,
                reason="This is a TDD test for the current spec - expected to fail until implementation complete",
                suggested_action="Continue implementing the feature to make this test pass",
                related_files=tdd_test_files,
            )
        
        # Rule 2: Test file covers modified files (likely regression)
        test_covers_modified = self._test_covers_files(test_file, modified_files)
        if test_covers_modified:
            return TriageResult(
                test_name=test_name,
                test_file=test_file,
                category=TriageCategory.REGRESSION,
                confidence=0.75,
                reason=f"Test covers files you modified: {', '.join(test_covers_modified[:3])}",
                suggested_action="Review your changes to these files - you may have broken existing behavior",
                related_files=test_covers_modified,
            )
        
        # Rule 3: Spec mentions changing behavior that test asserts (likely outdated)
        if spec_content:
            outdated_indicators = self._check_spec_contradicts_test(spec_content, test_name, error_context)
            if outdated_indicators:
                return TriageResult(
                    test_name=test_name,
                    test_file=test_file,
                    category=TriageCategory.OUTDATED,
                    confidence=0.7,
                    reason=f"Spec appears to change behavior this test expects: {outdated_indicators}",
                    suggested_action="Update test to match new spec requirements",
                    spec_context=outdated_indicators,
                )
        
        # Rule 4: Check for flaky test indicators
        flaky_indicators = self._check_flaky_indicators(error_context)
        if flaky_indicators:
            return TriageResult(
                test_name=test_name,
                test_file=test_file,
                category=TriageCategory.FLAKY,
                confidence=0.6,
                reason=f"Test shows flaky indicators: {flaky_indicators}",
                suggested_action="Investigate timing/environment issues or re-run to confirm",
            )
        
        # Rule 5: Uncertain - needs manual review
        return TriageResult(
            test_name=test_name,
            test_file=test_file,
            category=TriageCategory.UNCERTAIN,
            confidence=0.3,
            reason="Could not determine cause - no clear connection to spec changes or modified files",
            suggested_action="Manually review this test failure",
        )
    
    def _test_covers_files(self, test_file: str, modified_files: List[str]) -> List[str]:
        """Check if test file likely covers any of the modified files"""
        covered = []
        
        # Extract base name patterns from test file
        # e.g., "test/browser/tab_manager_test.dart" -> "tab_manager"
        import re
        test_base = re.sub(r'_test\.(dart|py|js|ts|tsx)$', '', Path(test_file).stem)
        test_base = test_base.replace('test_', '')
        
        for mod_file in modified_files:
            mod_base = Path(mod_file).stem
            # Check if test name relates to modified file
            if test_base.lower() in mod_base.lower() or mod_base.lower() in test_base.lower():
                covered.append(mod_file)
            # Check if in same module/directory
            elif Path(test_file).parent.name in mod_file:
                covered.append(mod_file)
        
        return covered
    
    def _check_spec_contradicts_test(self, spec_content: str, test_name: str, error_context: str) -> str:
        """Check if spec mentions changing behavior that test expects"""
        spec_lower = spec_content.lower()
        
        # Look for change indicators in spec
        change_patterns = [
            (r'change.*from.*to', "spec mentions changing behavior"),
            (r'instead of', "spec mentions replacing behavior"),
            (r'no longer', "spec mentions removing behavior"),
            (r'now returns?', "spec mentions new return value"),
            (r'updated? to', "spec mentions updating behavior"),
            (r'replace', "spec mentions replacement"),
        ]
        
        import re
        for pattern, description in change_patterns:
            match = re.search(pattern, spec_lower)
            if match:
                # Get context around match
                start = max(0, match.start() - 50)
                end = min(len(spec_content), match.end() + 100)
                context = spec_content[start:end].strip()
                return f"{description}: '...{context}...'"
        
        return ""
    
    def _check_flaky_indicators(self, error_context: str) -> str:
        """Check for indicators of flaky tests"""
        flaky_patterns = [
            (r'timeout', "timeout error"),
            (r'timed out', "timed out"),
            (r'connection refused', "connection issue"),
            (r'network', "network error"),
            (r'async', "async timing issue"),
            (r'race condition', "race condition"),
            (r'intermittent', "intermittent failure"),
            (r'flaky', "marked as flaky"),
        ]
        
        error_lower = error_context.lower()
        import re
        for pattern, description in flaky_patterns:
            if re.search(pattern, error_lower):
                return description
        
        return ""
    
    def _display_triage_results(self, summary: TriageSummary):
        """Display triage results in a clear, actionable format"""
        print("\n" + "=" * 60)
        print(f"  TEST FAILURE TRIAGE - Spec {summary.spec_id}")
        print(f"  {len(summary.results)} failing tests analyzed")
        print("=" * 60)
        
        # TDD Expected (if any)
        if summary.tdd_expected:
            print(f"\n📝 TDD EXPECTED ({len(summary.tdd_expected)}) - Implementation in progress")
            print("-" * 50)
            for r in summary.tdd_expected:
                conf = "●●●" if r.confidence >= 0.7 else "●●○" if r.confidence >= 0.4 else "●○○"
                print(f"  {conf} {r.test_name}")
                print(f"      File: {r.test_file}")
                print(f"      → {r.suggested_action}")
        
        # Regressions (fix code)
        if summary.regressions:
            print(f"\n🔴 LIKELY REGRESSIONS ({len(summary.regressions)}) - Fix Implementation")
            print("-" * 50)
            for r in summary.regressions:
                conf = "●●●" if r.confidence >= 0.7 else "●●○" if r.confidence >= 0.4 else "●○○"
                print(f"  {conf} {r.test_name}")
                print(f"      File: {r.test_file}")
                print(f"      Reason: {r.reason}")
                if r.related_files:
                    print(f"      Modified: {', '.join(r.related_files[:3])}")
                print(f"      → {r.suggested_action}")
        
        # Outdated (update tests)
        if summary.outdated:
            print(f"\n🟡 LIKELY OUTDATED ({len(summary.outdated)}) - Update Tests")
            print("-" * 50)
            for r in summary.outdated:
                conf = "●●●" if r.confidence >= 0.7 else "●●○" if r.confidence >= 0.4 else "●○○"
                print(f"  {conf} {r.test_name}")
                print(f"      File: {r.test_file}")
                print(f"      Reason: {r.reason}")
                if r.spec_context:
                    print(f"      Spec: {r.spec_context[:100]}...")
                print(f"      → {r.suggested_action}")
        
        # Flaky
        if summary.flaky:
            print(f"\n⚪ POSSIBLY FLAKY ({len(summary.flaky)}) - Investigate")
            print("-" * 50)
            for r in summary.flaky:
                print(f"  ○○○ {r.test_name}")
                print(f"      File: {r.test_file}")
                print(f"      Reason: {r.reason}")
                print(f"      → {r.suggested_action}")
        
        # Uncertain
        if summary.uncertain:
            print(f"\n❓ UNCERTAIN ({len(summary.uncertain)}) - Manual Review Needed")
            print("-" * 50)
            for r in summary.uncertain:
                print(f"  ??? {r.test_name}")
                print(f"      File: {r.test_file}")
                print(f"      → {r.suggested_action}")
        
        # Summary and next steps
        print("\n" + "=" * 60)
        print("  SUMMARY")
        print("=" * 60)
        print(f"  🔴 Regressions (fix code):     {len(summary.regressions)}")
        print(f"  🟡 Outdated (update tests):    {len(summary.outdated)}")
        print(f"  📝 TDD Expected:               {len(summary.tdd_expected)}")
        print(f"  ⚪ Flaky:                      {len(summary.flaky)}")
        print(f"  ❓ Uncertain:                  {len(summary.uncertain)}")
        
        print("\n  📋 SUGGESTED ACTIONS:")
        if summary.regressions:
            print(f"     1. Fix {len(summary.regressions)} regression(s) in your implementation")
        if summary.outdated:
            print(f"     2. Update {len(summary.outdated)} outdated test(s) to match new spec")
        if summary.tdd_expected:
            print(f"     3. Continue implementing to pass {len(summary.tdd_expected)} TDD test(s)")
        if summary.uncertain:
            print(f"     4. Manually review {len(summary.uncertain)} uncertain failure(s)")
        
        print("")
    
    def get_triage_summary_for_complete(self, spec_id: str, test_results: dict) -> Optional[TriageSummary]:
        """Get a quick triage summary for use in speky complete flow"""
        if not test_results or test_results.get("passed", True):
            return None
        
        # Run lightweight triage
        runners = get_available_runners(self.project_root)
        all_failures = []
        
        for runner in runners:
            result = runner.run_tests()
            if result.failed > 0:
                failures = self._extract_failing_tests(runner.name, result.output)
                all_failures.extend(failures)
        
        if not all_failures:
            return None
        
        spec_content = self._load_spec_content(spec_id)
        modified_files = self._get_modified_files_for_spec(spec_id)
        tdd_state = self._get_tdd_state(spec_id)
        tdd_test_files = tdd_state.get("tests", {}).get("linked_files", [])
        
        summary = TriageSummary(spec_id)
        for failure in all_failures:
            result = self._categorize_test_failure(
                failure=failure,
                spec_content=spec_content,
                modified_files=modified_files,
                tdd_test_files=tdd_test_files,
                tdd_enabled=tdd_state.get("enabled", False)
            )
            summary.add_result(result)
        
        return summary
    
    def _display_all_tdd_status(self):
        """Display TDD status for all specs"""
        spec_dir = self.speky_dir / "specs"
        if not spec_dir.exists():
            print("No specs found")
            return
        
        tdd_specs = []
        non_tdd_specs = []
        
        for d in sorted(spec_dir.iterdir()):
            if d.is_dir() and d.name[:3].isdigit():
                spec_id = d.name[:3]
                tdd_state = self._get_tdd_state(spec_id)
                
                if tdd_state.get("enabled"):
                    tdd_specs.append((spec_id, d.name, tdd_state))
                else:
                    non_tdd_specs.append((spec_id, d.name))
        
        # TDD-enabled specs
        if tdd_specs:
            print("\n🧪 TDD-Enabled Specs")
            print("-" * 50)
            for spec_id, spec_name, tdd_state in tdd_specs:
                state = tdd_state.get("state", "unknown")
                tests = tdd_state.get("tests", {})
                
                state_icon = {
                    TDDState.TESTS_GENERATED.value: "📝",
                    TDDState.RED_CONFIRMED.value: "🔴",
                    TDDState.IMPLEMENTING.value: "🔧",
                    TDDState.GREEN_PASSED.value: "🟢",
                    TDDState.REGRESSION_PASSED.value: "✅",
                }.get(state, "❓")
                
                test_info = f"{tests.get('passed', 0)}/{tests.get('total', 0)} passing" if tests.get('total', 0) > 0 else "No tests yet"
                print(f"  {state_icon} {spec_name}: {state} ({test_info})")
        else:
            print("\nNo TDD-enabled specs yet")
            print("Start TDD with: speky implement <spec-id> --tdd")
        
        # Non-TDD specs summary
        if non_tdd_specs:
            print(f"\n📋 Non-TDD Specs: {len(non_tdd_specs)}")
            print("   Enable TDD: speky implement <spec-id> --tdd")


# =============================================================================
# STANDALONE CLI
# =============================================================================

def main():
    """Standalone CLI for testing module"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="SPEKY Testing Integration (Standalone Mode)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python speky_testing.py init              Initialize test harness
  python speky_testing.py gen 003           Generate tests for spec 003
  python speky_testing.py run               Run all tests
  python speky_testing.py run --spec 003    Run tests for spec 003
  python speky_testing.py coverage          Show coverage report
  python speky_testing.py status            Show test health dashboard
        """
    )
    
    parser.add_argument(
        "action",
        choices=["init", "gen", "run", "coverage", "status", "e2e", "link", "gaps", "recommend", "setup", "refresh-context", "refresh-guide", "tdd-red", "tdd-green", "tdd-status", "complete", "triage"],
        help="Action to perform"
    )
    parser.add_argument("target", nargs="?", help="Target spec ID or file")
    parser.add_argument("--spec", dest="spec_id", help="Filter by spec ID")
    parser.add_argument("--type", dest="test_type", default="all",
                       choices=["unit", "widget", "integration", "e2e", "all"])
    parser.add_argument("--coverage", action="store_true", help="Run with coverage")
    parser.add_argument("--affected", action="store_true", help="Run affected tests only")
    parser.add_argument("--failed", action="store_true", help="Re-run failed tests")
    parser.add_argument("--platform", default="all", choices=["web", "mobile", "all"])
    parser.add_argument("--headed", action="store_true", help="Run E2E with visible browser")
    parser.add_argument("--refresh", action="store_true", help="Refresh cached data (for setup command)")
    
    args = parser.parse_args()
    
    # Initialize testing integration in standalone mode
    testing = TestingIntegration(speky_instance=None)
    
    # Route to command
    success = testing.cmd_test(args)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
