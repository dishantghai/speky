# Product Requirements Document: Agentic Drift Detection System

**Version**: 1.0  
**Date**: December 4, 2024  
**Author**: SPEKY Team  
**Status**: Draft

---

## Executive Summary

This document outlines the requirements for an **Agentic Drift Detection System** - a standalone, intelligent system that autonomously detects and reports discrepancies between software specifications and their implementations. Unlike traditional static analysis or rule-based approaches, this system leverages Large Language Models (LLMs) in an agentic architecture to perform semantic analysis, tool-augmented exploration, and iterative verification.

The system addresses a fundamental problem in software engineering: **specifications and code drift apart over time**, leading to outdated documentation, missed requirements, and technical debt that compounds with each release.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Research & Background](#2-research--background)
3. [Market Analysis](#3-market-analysis)
4. [Solution Options Analysis](#4-solution-options-analysis)
5. [Proposed Solution](#5-proposed-solution)
6. [Functional Requirements](#6-functional-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [Architecture Overview](#8-architecture-overview)
9. [Success Metrics](#9-success-metrics)
10. [Risks & Mitigations](#10-risks--mitigations)
11. [Implementation Roadmap](#11-implementation-roadmap)
12. [Open Questions](#12-open-questions)

---

## 1. Problem Statement

### 1.1 The Core Problem

**Specification-to-code drift** occurs when the documented requirements, specifications, or design documents no longer accurately reflect the actual implementation. This is a pervasive problem in software development that leads to:

- **Incorrect expectations**: Stakeholders rely on outdated specs
- **Onboarding friction**: New developers learn from inaccurate documentation
- **Compliance failures**: Audits reveal undocumented functionality
- **Technical debt**: Drift compounds over time, making future changes harder
- **Communication breakdowns**: Teams operate with different understandings

### 1.2 Real-World Example

From our own experience with SPEKY (AI-Assisted Scalable Engineering Framework):

**Specification stated:**
> "Maximum video length: 10 minutes"
> "Transcription must complete within 60 seconds for videos up to 5 minutes"

**Actual implementation:**
```python
MAX_VIDEO_DURATION = 55  # 55 seconds to stay under 1 minute limit
```

The implementation was constrained to 55 seconds (not 10 minutes) due to Google Speech-to-Text API's synchronous recognition limits. This is a **critical semantic drift** that:
- Traditional keyword matching cannot detect ("55 seconds" vs "10 minutes")
- Requires understanding of numeric values and their implications
- Needs context about API limitations to understand *why* the drift occurred

### 1.3 Why Current Solutions Fail

| Approach | Limitation |
|----------|------------|
| **Manual review** | Doesn't scale; humans miss semantic differences |
| **Keyword matching** | Can't understand "55 seconds" ≠ "10 minutes" |
| **Static analysis** | Only checks code structure, not business logic |
| **Test coverage** | Tests verify behavior, not specification alignment |
| **Documentation generators** | Create docs from code, don't verify existing specs |

### 1.4 The Abstraction Gap

Documentation and code operate at fundamentally different abstraction levels:

```
Specification:     "Support concurrent transcription of up to 3 videos"
                            ↓ (abstraction gap)
Implementation:    MAX_CONCURRENT_WORKERS = 2  # Local Docker
                   MAX_CONCURRENT_WORKERS = 5  # GCP deployment
```

Bridging this gap requires **semantic understanding**, not pattern matching.

---

## 2. Research & Background

### 2.1 Academic Foundations

#### 2.1.1 Documentation-to-Code Traceability (2024)

A comprehensive study by researchers evaluating LLMs for traceability tasks ([arxiv:2506.16440](https://arxiv.org/html/2506.16440v1)) found:

**Key Findings:**
- **LLMs achieve 80.4% F1-score** vs 36.2%-69.3% for traditional methods (TF-IDF, BM25, CodeBERT)
- **Claude Sonnet 3.5 performed best** among tested models (GPT-4o, o3-mini)
- **Context management is critical**: One-to-many matching achieved 79.4% F1, while many-to-many dropped to 5.3%
- **More context can hurt**: Providing entire documentation files increased false positives by 56.6%

**Traceability Challenges Identified:**
1. **Abstraction Gap**: Natural language describes concepts; code is formal and executable
2. **Evolution Mismatch**: Code refactors outpace documentation updates
3. **Format Differences**: Different languages and structures
4. **Implicit Knowledge**: Developers rely on tacit understanding that tools can't replicate

**Recommendations:**
- Break documentation into focused, manageable chunks
- Use one-to-many matching strategy (one spec segment → all relevant code)
- Combine LLM semantic understanding with static analysis precision
- Human-AI collaboration: LLMs identify, humans verify

#### 2.1.2 AI Agentic Programming (2025)

A survey on agentic AI for programming ([arxiv:2508.11126](https://arxiv.org/html/2508.11126v1)) establishes:

**Agentic vs Traditional:**
| Property | Traditional | Agentic |
|----------|-------------|---------|
| Execution | Single-shot | Multi-turn, iterative |
| Planning | None | Goal decomposition |
| Tools | None | Integrated (compilers, tests, etc.) |
| Feedback | None | Adaptive based on results |
| Autonomy | Human-driven | Goal-directed |

**Key Agentic Behaviors:**
1. **Reactivity vs Proactivity**: Proactive agents decompose tasks, plan execution
2. **Single-turn vs Multi-turn**: Multi-turn enables iterative refinement
3. **Tool-Augmented**: Integration with compilers, debuggers, test frameworks
4. **Adaptive**: Modify strategies based on feedback

**Recommended Architecture:**
- Execution loop with reasoning + tool use
- Structured feedback from tools (not just pass/fail)
- Memory for tracking state across iterations
- Goal-oriented stopping conditions

### 2.2 Technical Research

#### 2.2.1 Context Window Management

Modern LLMs support large context windows:
- **Claude 3.5**: 200K tokens
- **GPT-4o**: 128K tokens
- **Gemini**: 2M tokens

However, research shows:
- **Larger context ≠ better results** (56.6% more false positives with full files)
- **LLMs have output token limits** that truncate enumerated responses
- **Focused, chunked inputs** outperform full document dumps

#### 2.2.2 Semantic Understanding Capabilities

LLMs excel at:
- Understanding conceptual relationships
- Interpreting usage examples
- Connecting high-level descriptions to specific implementations
- Explaining *why* artifacts are related

LLMs struggle with:
- Precise execution path tracing (static analysis is better)
- Multi-hop dependency chains (13%-87% error rate on intermediate steps)
- Consistent enumeration of large result sets

### 2.3 Industry Patterns

#### 2.3.1 Existing Tool Categories

| Category | Examples | Limitation for Drift Detection |
|----------|----------|--------------------------------|
| **IaC Drift** | Terraform, driftctl | Infrastructure only, not specs |
| **Doc Generators** | Sphinx, JSDoc | Generate from code, don't verify |
| **Code Review AI** | Qodo, CodeRabbit | PR-focused, not spec alignment |
| **Requirements Tools** | Jira, Azure DevOps | Tracking, not verification |
| **Test Frameworks** | Jest, pytest | Behavior, not documentation |

#### 2.3.2 Gap in the Market

No existing tool provides:
- **Semantic spec-to-code drift detection**
- **Agentic exploration** of codebases
- **Numeric/constraint verification** ("10 minutes" vs "55 seconds")
- **Interactive resolution** with developer

---

## 3. Market Analysis

### 3.1 Target Users

| Segment | Pain Point | Value Proposition |
|---------|------------|-------------------|
| **Solo Developers** | Docs get stale, forget what was specified | Automated alignment checking |
| **Small Teams** | Specs written by one, implemented by another | Catch misunderstandings early |
| **Enterprises** | Compliance requires accurate documentation | Audit-ready traceability |
| **Open Source** | Contributors need accurate docs | Reduce onboarding friction |

### 3.2 Use Cases

1. **Pre-release verification**: "Does our code match the spec before shipping?"
2. **Continuous monitoring**: "Alert me when code changes don't update docs"
3. **Compliance audits**: "Prove our implementation matches requirements"
4. **Technical debt assessment**: "How much drift has accumulated?"
5. **Onboarding**: "Is this documentation still accurate?"

### 3.3 Competitive Landscape

| Competitor | Approach | Drift Detection? |
|------------|----------|------------------|
| **Terraform** | State file comparison | Infrastructure only |
| **Snyk driftctl** | Cloud resource drift | IaC, not specs |
| **Qodo** | AI code review | PR-level, not spec alignment |
| **Swimm** | Auto-update docs | Keeps docs in sync, doesn't verify specs |
| **ReadMe** | API documentation | API-specific |
| **Notion AI** | Doc management | No code integration |

**Gap**: No tool does semantic spec-to-code drift detection with agentic exploration.

---

## 4. Solution Options Analysis

### 4.1 Option A: Rule-Based Pattern Matching

**Approach**: Define patterns for common drift types (missing functions, renamed classes, changed constants).

**Pros:**
- Fast execution
- Deterministic results
- No API costs

**Cons:**
- Can't detect semantic drift ("55 seconds" vs "10 minutes")
- Requires manual rule creation for each pattern
- High false positive/negative rate
- Doesn't scale to new domains

**Verdict**: ❌ Insufficient for semantic understanding

### 4.2 Option B: Single-Shot LLM Analysis

**Approach**: Send spec + code to LLM, ask for drift analysis.

**Pros:**
- Semantic understanding
- Easy to implement
- Works across languages

**Cons:**
- Context window limits (can't fit large codebases)
- No verification of findings
- High false positive rate (56.6% increase with more context)
- Can't explore codebase dynamically

**Verdict**: ⚠️ Our current SPEKY approach - insufficient for complex cases

### 4.3 Option C: Multi-Pass Claim Verification

**Approach**: Extract claims from spec, verify each against code.

**Pros:**
- Structured, explainable
- Each claim independently verifiable
- Better precision

**Cons:**
- Still limited to what fits in context
- No dynamic exploration
- Can't handle implicit requirements

**Verdict**: ⚠️ Better, but still static

### 4.4 Option D: Agentic System with Tool Use

**Approach**: LLM agent with tools for code search, file reading, execution, and iterative verification.

**Pros:**
- Dynamic codebase exploration
- Verification through multiple passes
- Can follow semantic trails
- Adapts based on findings
- Human-in-the-loop for ambiguous cases

**Cons:**
- More complex architecture
- Higher API costs
- Requires careful tool design
- Potential for loops/divergence

**Verdict**: ✅ **Recommended** - addresses all key limitations

### 4.5 Option E: Hybrid Agentic + Static Analysis

**Approach**: Combine agentic LLM with traditional static analysis tools.

**Pros:**
- Best of both worlds
- LLM for semantics, static analysis for precision
- Verification through multiple methods
- Lower false positive rate

**Cons:**
- Most complex to implement
- Requires integration with language-specific tools
- Higher maintenance burden

**Verdict**: ✅ **Ideal end-state** - build toward this iteratively

---

## 5. Proposed Solution

### 5.1 Vision

**Drift Agent** is an autonomous, agentic system that:
1. **Understands** specifications semantically (not just keywords)
2. **Explores** codebases dynamically using tools
3. **Verifies** findings through multiple methods
4. **Interacts** with developers to resolve ambiguities
5. **Learns** from feedback to improve over time

### 5.2 Core Principles

1. **Claim-Centric**: Extract verifiable claims from specs, verify each independently
2. **Evidence-Based**: Every drift finding must cite specific code evidence
3. **Hypothesis-Driven**: Agent forms hypotheses and tests them
4. **Human-in-the-Loop**: Ambiguous findings escalate to developer
5. **Tool-Augmented**: Agent uses code search, file reading, AST analysis
6. **Iterative**: Agent refines understanding through multiple passes

### 5.3 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        DRIFT AGENT                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │   SPEC   │────▶│  CLAIM   │────▶│ VERIFIED │               │
│   │  PARSER  │     │ VERIFIER │     │ FINDINGS │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│        │                │                 │                     │
│        ▼                ▼                 ▼                     │
│   ┌──────────────────────────────────────────────┐             │
│   │              TOOL INTERFACE                    │             │
│   │  • grep_code()    • read_file()               │             │
│   │  • analyze_ast()  • search_semantic()         │             │
│   │  • run_tests()    • get_git_history()        │             │
│   └──────────────────────────────────────────────┘             │
│        │                │                 │                     │
│        ▼                ▼                 ▼                     │
│   ┌──────────────────────────────────────────────┐             │
│   │              CODEBASE                          │             │
│   └──────────────────────────────────────────────┘             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.4 Key Differentiators

| Feature | Current SPEKY | Drift Agent |
|---------|---------------|-------------|
| **Exploration** | Static file selection | Dynamic tool-based |
| **Context** | 12K chars truncated | Iterative retrieval |
| **Verification** | None (single pass) | Multi-step confirmation |
| **Numeric understanding** | None | Semantic comparison |
| **Evidence** | AI assertion | Code citations |
| **Interaction** | Post-hoc options | Conversational during analysis |

---

## 6. Functional Requirements

### 6.1 Specification Parsing

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | Parse SPEKY markdown specs (`.speky/specs/*/spec.md`) | P0 |
| FR-1.2 | Parse OpenAPI/Swagger specifications | P1 |
| FR-1.3 | Parse Gherkin/BDD feature files | P1 |
| FR-1.4 | Parse freeform markdown requirements | P1 |
| FR-1.5 | Extract structured claims from natural language specs | P0 |
| FR-1.6 | Identify numeric constraints (limits, thresholds, timeouts) | P0 |
| FR-1.7 | Identify technical requirements (libraries, APIs, patterns) | P0 |
| FR-1.8 | Identify behavioral requirements (user stories, acceptance criteria) | P0 |

### 6.2 Code Analysis Tools

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | Grep/regex search across codebase | P0 |
| FR-2.2 | Read specific files with line ranges | P0 |
| FR-2.3 | List directory structure | P0 |
| FR-2.4 | Semantic code search (embeddings-based) | P1 |
| FR-2.5 | AST parsing for Python | P1 |
| FR-2.6 | AST parsing for JavaScript/TypeScript | P1 |
| FR-2.7 | AST parsing for Dart | P2 |
| FR-2.8 | AST parsing for Go | P2 |
| FR-2.9 | Git history analysis (when did code change?) | P2 |
| FR-2.10 | Test execution and result analysis | P2 |

### 6.3 Drift Detection

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | Detect CODE_BEHIND: spec requirements not in code | P0 |
| FR-3.2 | Detect SPEC_BEHIND: code features not in spec | P0 |
| FR-3.3 | Detect NUMERIC_DRIFT: mismatched values/limits | P0 |
| FR-3.4 | Detect TECH_DEVIATION: different libraries/approaches | P0 |
| FR-3.5 | Detect SCOPE_CREEP: out-of-scope items implemented | P1 |
| FR-3.6 | Detect DOC_STALE: outdated inline comments | P1 |
| FR-3.7 | Confidence scoring for each finding | P0 |
| FR-3.8 | Evidence citation (file, line, snippet) for each finding | P0 |

### 6.4 Agent Behavior

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-4.1 | Multi-turn reasoning with tool use | P0 |
| FR-4.2 | Hypothesis formation and testing | P0 |
| FR-4.3 | Self-verification of findings | P0 |
| FR-4.4 | Graceful handling of ambiguous cases | P0 |
| FR-4.5 | Progress reporting during analysis | P1 |
| FR-4.6 | Ability to ask clarifying questions | P1 |
| FR-4.7 | Memory of past analyses for consistency | P2 |

### 6.5 User Interaction

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-5.1 | CLI interface for standalone use | P0 |
| FR-5.2 | Conversational resolution flow | P0 |
| FR-5.3 | Accept/reject/modify findings | P0 |
| FR-5.4 | Generate spec update suggestions | P1 |
| FR-5.5 | Generate code fix suggestions | P2 |
| FR-5.6 | Integration API for SPEKY | P0 |
| FR-5.7 | Web UI for visualization | P2 |
| FR-5.8 | IDE extension (VSCode/Windsurf) | P2 |

### 6.6 Output & Reporting

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-6.1 | Structured JSON output | P0 |
| FR-6.2 | Human-readable markdown report | P0 |
| FR-6.3 | Severity classification (critical/warning/info) | P0 |
| FR-6.4 | Actionable suggestions for each finding | P0 |
| FR-6.5 | Diff view of spec vs implementation | P1 |
| FR-6.6 | Historical drift tracking | P2 |

---

## 7. Non-Functional Requirements

### 7.1 Performance

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1.1 | Small project analysis (<10 specs) | < 2 minutes |
| NFR-1.2 | Medium project analysis (<50 specs) | < 10 minutes |
| NFR-1.3 | Large project analysis (<200 specs) | < 30 minutes |
| NFR-1.4 | Single spec analysis | < 30 seconds |
| NFR-1.5 | Quick mode (reduced accuracy) | < 10 seconds |

### 7.2 Accuracy

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-2.1 | Precision (true positives / all positives) | > 85% |
| NFR-2.2 | Recall (true positives / all actual drifts) | > 75% |
| NFR-2.3 | F1 Score | > 80% |
| NFR-2.4 | False positive rate | < 15% |

### 7.3 Reliability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-3.1 | Graceful degradation on API failures | Required |
| NFR-3.2 | Deterministic results (same input → same output) | Best effort |
| NFR-3.3 | Timeout handling for long analyses | Required |
| NFR-3.4 | Recovery from partial failures | Required |

### 7.4 Scalability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-4.1 | Codebase size | Up to 100K files |
| NFR-4.2 | Concurrent analyses | Up to 10 |
| NFR-4.3 | Spec complexity | Unlimited |

### 7.5 Cost

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-5.1 | API cost per spec analysis | < $0.10 |
| NFR-5.2 | API cost per full project | < $2.00 |
| NFR-5.3 | Self-hosted option available | P1 |

### 7.6 Security

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-6.1 | No code sent to external APIs without consent | P0 |
| NFR-6.2 | Support for local LLMs (Ollama, etc.) | P1 |
| NFR-6.3 | Credential/secret detection and exclusion | P0 |

---

## 8. Architecture Overview

### 8.1 System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DRIFT AGENT SYSTEM                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     ORCHESTRATOR                              │   │
│  │  • Agent loop management                                      │   │
│  │  • Tool dispatch                                              │   │
│  │  • State management                                           │   │
│  │  • Conversation handling                                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │              │                │              │              │
│       ▼              ▼                ▼              ▼              │
│  ┌─────────┐   ┌──────────┐   ┌────────────┐   ┌──────────┐       │
│  │  SPEC   │   │   CODE   │   │   DRIFT    │   │   USER   │       │
│  │ PARSER  │   │ EXPLORER │   │  ANALYZER  │   │INTERFACE │       │
│  └─────────┘   └──────────┘   └────────────┘   └──────────┘       │
│       │              │                │              │              │
│       ▼              ▼                ▼              ▼              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      TOOL REGISTRY                            │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐     │   │
│  │  │ grep   │ │ read   │ │  ast   │ │semantic│ │  git   │     │   │
│  │  │ search │ │ file   │ │ parser │ │ search │ │history │     │   │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    LLM INTERFACE                              │   │
│  │  • Anthropic Claude (primary)                                 │   │
│  │  • OpenAI GPT-4o (fallback)                                   │   │
│  │  • Local LLMs via Ollama (optional)                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 Agent Loop

```python
# Pseudocode for agent loop
class DriftAgent:
    def analyze_spec(self, spec_path: str) -> DriftReport:
        # Phase 1: Parse spec into claims
        spec = self.spec_parser.parse(spec_path)
        claims = self.extract_claims(spec)
        
        # Phase 2: Verify each claim
        findings = []
        for claim in claims:
            # Agent loop for this claim
            evidence = self.investigate_claim(claim)
            if evidence.indicates_drift:
                finding = self.create_finding(claim, evidence)
                findings.append(finding)
        
        # Phase 3: Validate and deduplicate
        validated = self.validate_findings(findings)
        
        return DriftReport(validated)
    
    def investigate_claim(self, claim: Claim) -> Evidence:
        """Agentic investigation loop"""
        context = AgentContext(claim)
        
        while not context.is_resolved():
            # LLM decides next action
            action = self.llm.decide_action(context)
            
            if action.type == "use_tool":
                result = self.tools.execute(action.tool, action.params)
                context.add_observation(result)
            
            elif action.type == "form_hypothesis":
                context.set_hypothesis(action.hypothesis)
            
            elif action.type == "conclude":
                return context.to_evidence()
            
            elif action.type == "ask_user":
                response = self.user.ask(action.question)
                context.add_clarification(response)
        
        return context.to_evidence()
```

### 8.3 Tool Definitions

```python
DRIFT_AGENT_TOOLS = [
    {
        "name": "grep_code",
        "description": "Search for pattern in codebase",
        "parameters": {
            "pattern": "regex pattern to search",
            "file_types": "optional file extensions filter",
            "max_results": "limit results (default 20)"
        }
    },
    {
        "name": "read_file",
        "description": "Read file contents",
        "parameters": {
            "path": "file path relative to project root",
            "start_line": "optional start line",
            "end_line": "optional end line"
        }
    },
    {
        "name": "list_directory",
        "description": "List files in directory",
        "parameters": {
            "path": "directory path",
            "recursive": "include subdirectories",
            "pattern": "optional glob pattern"
        }
    },
    {
        "name": "analyze_function",
        "description": "Get function signature, docstring, and body",
        "parameters": {
            "file_path": "path to source file",
            "function_name": "name of function/method"
        }
    },
    {
        "name": "find_definition",
        "description": "Find where a symbol is defined",
        "parameters": {
            "symbol": "class, function, or variable name"
        }
    },
    {
        "name": "find_usages",
        "description": "Find where a symbol is used",
        "parameters": {
            "symbol": "class, function, or variable name"
        }
    },
    {
        "name": "compare_values",
        "description": "Semantically compare spec value to code value",
        "parameters": {
            "spec_value": "value from specification",
            "code_value": "value from code",
            "context": "what this value represents"
        }
    }
]
```

### 8.4 Data Models

```python
@dataclass
class Claim:
    """A verifiable statement from a specification"""
    id: str
    text: str                    # Original text from spec
    type: ClaimType              # FUNCTIONAL, CONSTRAINT, TECHNICAL, BEHAVIORAL
    category: str                # e.g., "performance", "security", "api"
    values: dict                 # Extracted values (limits, names, etc.)
    source: SpecLocation         # Where in spec this came from

@dataclass
class Evidence:
    """Evidence gathered during investigation"""
    files_examined: List[str]
    code_snippets: List[CodeSnippet]
    search_results: List[SearchResult]
    hypothesis: str
    conclusion: str
    confidence: float            # 0.0 - 1.0

@dataclass
class DriftFinding:
    """A confirmed drift between spec and code"""
    id: str
    type: DriftType              # CODE_BEHIND, SPEC_BEHIND, NUMERIC_DRIFT, etc.
    severity: Severity           # CRITICAL, WARNING, INFO
    claim: Claim                 # The claim that was violated
    evidence: Evidence           # How we determined this
    suggestion: str              # How to resolve
    spec_location: SpecLocation  # Where in spec
    code_locations: List[CodeLocation]  # Where in code

@dataclass
class DriftReport:
    """Complete drift analysis report"""
    spec_path: str
    analyzed_at: datetime
    duration_seconds: float
    findings: List[DriftFinding]
    summary: str
    stats: AnalysisStats
```

---

## 9. Success Metrics

### 9.1 Detection Quality

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Precision** | > 85% | Manual review of sample findings |
| **Recall** | > 75% | Against known drift test cases |
| **F1 Score** | > 80% | Calculated from precision/recall |
| **Numeric drift detection** | > 90% | Specific test cases like "55s vs 10min" |

### 9.2 User Experience

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Time to first finding** | < 15 seconds | From command invocation |
| **Actionable findings** | > 90% | User can act on finding without confusion |
| **False positive frustration** | < 10% | User dismisses finding as irrelevant |

### 9.3 Operational

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Analysis completion rate** | > 99% | Successfully completes without error |
| **Cost per analysis** | < $0.10 | API costs per spec |
| **Adoption in SPEKY projects** | > 50% | Projects using drift detection |

---

## 10. Risks & Mitigations

### 10.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **LLM hallucination** | High | High | Multi-step verification, evidence requirements |
| **Context overflow** | Medium | Medium | Chunking strategy, iterative retrieval |
| **API cost explosion** | Medium | Medium | Token budgets, caching, quick mode |
| **Language support gaps** | Medium | Low | Focus on Python/JS first, extensible architecture |
| **Agent loops** | Low | High | Max iterations, timeout, human escalation |

### 10.2 Product Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Low adoption** | Medium | High | Integrate with existing SPEKY workflow |
| **User trust issues** | Medium | Medium | Explainable findings, evidence citations |
| **Spec format fragmentation** | Medium | Medium | Start with SPEKY format, expand later |

### 10.3 Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **API provider changes** | Low | High | Abstraction layer, multiple provider support |
| **Cost unpredictability** | Medium | Medium | Budget limits, usage monitoring |

---

## 11. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-4)

**Goal**: Basic agentic drift detection working end-to-end

**Deliverables**:
- [ ] Core agent loop with tool use
- [ ] Basic tools: grep_code, read_file, list_directory
- [ ] Claim extraction from SPEKY specs
- [ ] CODE_BEHIND and SPEC_BEHIND detection
- [ ] CLI interface
- [ ] Integration with SPEKY `complete` command

**Success Criteria**: Correctly detects the "55s vs 10min" drift case

### Phase 2: Enhanced Detection (Weeks 5-8)

**Goal**: Improved accuracy and coverage

**Deliverables**:
- [ ] NUMERIC_DRIFT detection with semantic comparison
- [ ] TECH_DEVIATION detection
- [ ] Multi-step verification
- [ ] Confidence scoring
- [ ] Evidence citation in findings
- [ ] Conversational resolution flow

**Success Criteria**: > 75% F1 score on test cases

### Phase 3: Polish & Integrate (Weeks 9-12)

**Goal**: Production-ready with full SPEKY integration

**Deliverables**:
- [ ] AST parsing for Python and JavaScript
- [ ] Semantic code search
- [ ] Historical drift tracking
- [ ] Web UI for visualization
- [ ] Multiple LLM provider support
- [ ] Documentation and examples

**Success Criteria**: > 80% F1 score, < $0.10 per analysis

### Phase 4: Expansion (Future)

**Potential features**:
- IDE extensions
- CI/CD integration
- Additional spec formats (OpenAPI, Gherkin)
- Auto-fix suggestions
- Team collaboration features
- Enterprise features (SSO, audit logs)

---

## 12. Open Questions

### 12.1 Technical

1. **Should we use a multi-agent architecture?** (Separate agents for parsing, searching, verifying)
2. **How to handle large monorepos?** (Project boundaries, selective analysis)
3. **What's the right balance between exploration depth and cost?**
4. **Should we maintain a code index for faster searching?**

### 12.2 Product

1. **Should drift findings block CI/CD?** (Or advisory only)
2. **How to handle spec ambiguity?** (Spec says "fast", code defines as 100ms)
3. **What's the right default for confidence thresholds?**
4. **Should we suggest spec updates or code changes?** (Or let user decide)

### 12.3 Business

1. **Standalone product or SPEKY feature only?**
2. **Pricing model if standalone?** (Per analysis, subscription, open source)
3. **What's the minimum viable integration for SPEKY?**

---

## Appendix A: Example Drift Report

```json
{
  "spec_path": ".speky/specs/002-transcription/spec.md",
  "analyzed_at": "2024-12-04T15:30:00Z",
  "duration_seconds": 18.5,
  "findings": [
    {
      "id": "drift-001",
      "type": "NUMERIC_DRIFT",
      "severity": "CRITICAL",
      "claim": {
        "text": "Maximum video length: 10 minutes",
        "type": "CONSTRAINT",
        "values": {"max_duration": "10 minutes"}
      },
      "evidence": {
        "files_examined": ["backend/app/services/audio_extractor.py"],
        "code_snippets": [
          {
            "file": "backend/app/services/audio_extractor.py",
            "line": 15,
            "code": "MAX_VIDEO_DURATION = 55  # 55 seconds"
          }
        ],
        "hypothesis": "Spec says 10 minutes, code limits to 55 seconds",
        "conclusion": "CONFIRMED: Implementation uses 55 seconds, not 10 minutes",
        "confidence": 0.95
      },
      "suggestion": "Update spec to reflect 55-second limit due to Google Speech-to-Text sync API constraints, or implement async API for longer videos"
    }
  ],
  "summary": "Found 1 critical drift: video duration limit mismatch",
  "stats": {
    "claims_extracted": 12,
    "claims_verified": 12,
    "drifts_found": 1,
    "api_calls": 8,
    "tokens_used": 15420
  }
}
```

---

## Appendix B: References

### Academic Papers

1. **"Evaluating the Use of LLMs for Documentation to Code Traceability"** (2024)
   - Key finding: Claude Sonnet 3.5 achieves 80.4% F1, one-to-many matching best
   - arXiv:2506.16440

2. **"AI Agentic Programming: A Survey of Techniques, Challenges, and Opportunities"** (2025)
   - Key finding: Agentic systems with tool use outperform single-shot approaches
   - arXiv:2508.11126

3. **"Agentic AI for Software: Thoughts from Software Engineering Community"** (2025)
   - Key finding: Agents working on program representations are most effective
   - arXiv:2508.17343

### Industry Resources

1. **Snyk driftctl** - Open source infrastructure drift detection
2. **Qodo** - AI code review with spec verification
3. **Swimm** - Documentation auto-update system

---

*Document prepared for SPEKY project. Last updated: December 4, 2024*
