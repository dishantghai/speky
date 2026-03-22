# Spec Sequencing & Dependencies - Complete Guide

**AI-Assisted Implementation Ordering for SPEKY**

This guide explains how SPEKY manages spec dependencies, detects conflicts, and guides you through the optimal implementation order.

---

## Table of Contents

1. [Overview](#overview)
2. [Priority Levels](#priority-levels)
3. [Dependency Tracking](#dependency-tracking)
4. [Sequence Command](#sequence-command)
5. [AI Dependency Inference](#ai-dependency-inference)
6. [Dependency Validation](#dependency-validation)
7. [Conflict Detection & Resolution](#conflict-detection--resolution)
8. [Complete Workflow](#complete-workflow)
9. [Examples](#examples)
10. [Best Practices](#best-practices)

---

## Overview

SPEKY's sequencing system helps you:
- **Track dependencies** between specs automatically
- **Prioritize** specs by importance (P0-P3)
- **Detect conflicts** when importing POC features
- **Infer dependencies** using AI analysis
- **Validate** dependencies before implementation
- **Visualize** implementation order with roadmap

### Key Concepts

- **Priority**: How important a spec is (P0=Blocker, P1=High, P2=Medium, P3=Low)
- **Dependencies**: Which specs must be completed before this one
- **Source**: Where the spec came from (initial_research, poc_import, external_import, manual)
- **Conflict**: When a new spec overlaps with an existing one
- **Circular Dependency**: When specs depend on each other in a loop

---

## Priority Levels

Every spec has a priority level that determines its urgency:

| Priority | Name | Description | When to Use |
|----------|------|-------------|-------------|
| **P0** | Blocker | Must be done immediately | Critical bugs, security issues, blockers |
| **P1** | High | Core functionality, MVP features | Essential features for product to work |
| **P2** | Medium | Important but not critical | Nice-to-have features, improvements |
| **P3** | Low | Future enhancements | Polish, optimizations, future ideas |

### Priority Assignment

SPEKY automatically assigns priorities based on source:

| Source | Priority Assignment |
|--------|---------------------|
| **Initial Research** | MVP features → P1, Future features → P2 |
| **POC Import** | Large complexity → P0, Medium → P1, Small → P2 |
| **External Import** | From AI analysis of documents |
| **Manual** | Default P1 (user can edit) |

### Editing Priority

Edit `status.json` in any spec directory:

```json
{
  "id": "001",
  "name": "User Authentication",
  "priority": "P0",  // Change this
  "dependencies": ["002"],
  "source": "poc_import",
  "status": "draft"
}
```

---

## Dependency Tracking

Dependencies define which specs must be completed before others.

### How Dependencies Work

A spec depends on another if:
- It requires functionality from the other spec
- It builds upon or extends the other spec
- It cannot be implemented without the other being done first
- It uses data models, APIs, or services defined in the other

### Dependency Sources

| Source | How Dependencies Are Set |
|--------|--------------------------|
| **Initial Research** | Empty by default (can add manually) |
| **POC Import** | Extracted from POC analysis automatically |
| **External Import** | From document analysis |
| **Manual** | Edit `status.json` or use `infer-deps` |

### Example Dependencies

```json
{
  "id": "002",
  "name": "API Endpoints",
  "dependencies": ["001"],  // Depends on 001-auth
  "priority": "P1"
}
```

This means:
- Spec 002 (API Endpoints) cannot be implemented until 001 (Authentication) is completed
- SPEKY will warn you if you try to implement 002 before 001

### Viewing Dependencies

Check any spec's `status.json`:

```bash
cat .speky/specs/002-api-endpoints/status.json
```

Or use the sequence command:

```bash
speky sequence
```

---

## Sequence Command

The `sequence` command shows a unified roadmap with dependency analysis.

### Basic Usage

```bash
speky sequence              # Show roadmap in terminal
speky sequence --export     # Export to .speky/roadmap.md
```

### What It Shows

1. **Summary Statistics**
   - Total specs
   - Count by priority (P0, P1, P2, P3)
   - Count by status (draft, planned, in_progress, completed)

2. **Circular Dependency Detection**
   - Warns if specs depend on each other in a loop
   - Shows the cycle path

3. **Recommended Implementation Order**
   - Specs sorted by dependencies first, then priority
   - Shows which specs each one depends on
   - Groups by priority level

4. **Dependency Tree**
   - Foundation specs (no dependencies)
   - Dependent specs with their dependencies

5. **Specs by Source**
   - Groups specs by where they came from
   - Helps understand project composition

6. **Next Steps**
   - Suggests which spec to implement next
   - Provides exact commands to run

### Example Output

```
🗺️  Spec Sequencing & Implementation Roadmap

📊 Total Specs: 5
   P0 (Blocker): 1
   P1 (High): 3
   P2 (Medium): 1
   P3 (Low): 0

   Status:
   • Draft: 3
   • Planned: 1
   • In Progress: 0
   • Completed: 1

⚠️  CIRCULAR DEPENDENCIES DETECTED:
   🔄 002 → 003 → 002
   
   Please review and fix these dependencies manually.

📋 Recommended Implementation Order

⚡ P0 - BLOCKER (Critical):
   1. ⬜ 005-security-patch (manual) [needs: 001]

⚡ P1 - HIGH PRIORITY (Core features):
   2. ✅ 001-auth (initial_research)
   3. ⬜ 002-api (poc_import) [needs: 001]
   4. ⬜ 004-payments (poc_import) [needs: 002]

📋 P2 - MEDIUM PRIORITY:
   5. ⬜ 003-notifications (manual) [needs: 001]

🌳 Dependency Tree

📌 Foundation Specs (no dependencies):
   • 001-auth

🔗 Dependent Specs:
   • 002-api → depends on: 001
   • 003-notifications → depends on: 001
   • 004-payments → depends on: 002
   • 005-security-patch → depends on: 001

📦 Specs by Source

🔬 initial_research (1):
   • 001-auth [P1, completed]

🧪 poc_import (2):
   • 002-api [P1, draft]
   • 004-payments [P1, draft]

✍️  manual (2):
   • 003-notifications [P2, draft]
   • 005-security-patch [P0, planned]

📋 Next Steps:
   1. Run: speky plan 005
   2. Run: speky implement 005
   3. After completing 005, run 'speky sequence' again
```

### Exported Roadmap

When using `--export`, a markdown file is created at `.speky/roadmap.md` with:
- All the information from terminal output
- Formatted for sharing with team
- Can be committed to git
- Updated each time you run `sequence --export`

---

## AI Dependency Inference

SPEKY can automatically detect dependencies between specs using AI analysis.

### Command

```bash
speky infer-deps              # Analyze all specs
speky infer-deps 003          # Analyze specific spec
```

### How It Works

1. **Reads Spec Content**: Analyzes the spec's requirements, technical details, and scope
2. **Compares with Existing Specs**: Checks all other specs in the project
3. **Identifies Dependencies**: Determines which specs this one truly depends on
4. **Shows Reasoning**: Explains why each dependency was identified
5. **Updates status.json**: Adds inferred dependencies (preserves manual ones)

### What Counts as a Dependency

The AI looks for:
- **Functionality Requirements**: "Needs authentication before API can be secured"
- **Data Model Usage**: "Uses user model defined in user management"
- **Service Dependencies**: "Requires payment gateway integration"
- **Technical Prerequisites**: "Builds on existing REST API"

### What Does NOT Count

The AI avoids:
- **Just Related**: Specs that are related but not dependent
- **Optional Integrations**: Features that could work independently
- **Parallel Features**: Things that can be built at the same time

### Example Output

```
🔗 Dependency Inference

Analyzing 3 spec(s) for dependencies...

📋 Analyzing: 003-payments

🔗 Inferred dependencies:
   • 001: Needs authentication before payment can be secured
   • 002: Uses API endpoints defined in API spec

✅ Added dependencies: 001, 002

📋 Analyzing: 004-notifications

🔗 Inferred dependencies:
   • 001: Requires user authentication to send notifications

✅ Added dependencies: 001

📋 Analyzing: 005-admin-panel

   No dependencies detected

✅ Updated 2 spec(s) with new dependencies

💡 Run 'speky sequence' to see updated implementation order
```

### When to Use

- **After creating multiple specs**: To automatically link them
- **After POC import**: If POC analysis missed some dependencies
- **Before starting implementation**: To ensure correct order
- **When refactoring**: To update dependencies after changes

### Preserves Manual Dependencies

If you manually added dependencies to `status.json`, `infer-deps` will:
- ✅ Keep your manual dependencies
- ✅ Add new inferred dependencies
- ✅ Not remove anything you added
- ✅ Merge both lists

---

## Dependency Validation

SPEKY validates dependencies before you start planning or implementing.

### When Validation Runs

Automatically runs before:
- `speky plan <spec-id>` - Before generating implementation plan
- `speky implement <spec-id>` - Before handing off to IDE

### What It Checks

For each dependency, validates:
- **Exists**: The dependency spec exists
- **Status**: The dependency is completed
- **Not Deprecated**: The dependency hasn't been deprecated

### Warning Example

```
🛠️  Generate Plan: 003

⚠️  DEPENDENCY WARNING for spec 003
   The following dependencies are not yet completed:

   • 001 (status: draft)
   • 002 (status: in_progress)

   Consider implementing these first, or proceed if you're sure.
   Run 'speky sequence' to see recommended order.

Continue anyway? [y/N]:
```

### Options

1. **No (default)**: Stop and implement dependencies first
2. **Yes**: Continue anyway (useful for parallel work or prototyping)

### Why This Matters

Implementing specs out of order can cause:
- **Rework**: Building on unstable foundations
- **Integration Issues**: Missing APIs or services
- **Wasted Time**: Implementing features that depend on unfinished work
- **Technical Debt**: Workarounds for missing dependencies

### Best Practice

Follow the recommended order from `speky sequence` to avoid these issues.

---

## Conflict Detection & Resolution

When importing POC features, SPEKY detects conflicts with existing specs.

### When Conflicts Are Detected

During `speky poc-import` when adopting specs:
- Compares POC feature name with existing spec names
- Uses word overlap similarity (>60% match)
- Checks for similar functionality

### Conflict Example

```
⚠️  SPEC CONFLICT DETECTED

📦 POC Feature: "User Authentication"
   Complexity: Medium
   Approach: OAuth 2.0 with JWT tokens

📄 Existing Spec: 001-auth (from initial_research)
   Priority: P1
   Status: draft
   Approach: Session-based authentication

🤖 AI Recommendation: MERGE
   Confidence: High
   
   Reason: Both approaches have merit. The POC's OAuth implementation
   is more modern and scalable, while the existing spec has detailed
   session management. Recommend combining OAuth for API access with
   session management for web interface.
   
   Merge Strategy: Use OAuth as primary, add session support for web

How would you like to resolve this conflict?
   1. Keep existing spec (skip POC feature)
   2. Replace with POC (deprecate 001)
   3. Merge both approaches (AI-assisted) [RECOMMENDED]
   4. Keep both as alternatives
   5. Show detailed comparison
   
Your choice [1-5]:
```

### Resolution Options

#### 1. Keep Existing (Skip POC)

- **What Happens**: POC feature is skipped, existing spec unchanged
- **Note Added**: Existing spec gets note about POC alternative
- **When to Use**: Existing spec is better or more complete

#### 2. Replace with POC

- **What Happens**: Existing spec marked as deprecated, new spec created from POC
- **Deprecation**: Old spec gets deprecation notice with reason
- **When to Use**: POC implementation is significantly better

#### 3. Merge Both (AI-Assisted)

- **What Happens**: AI combines both approaches into existing spec
- **Merge Strategy**: AI provides reasoning and combined approach
- **When to Use**: Both have valuable aspects (RECOMMENDED)

#### 4. Keep Both as Alternatives

- **What Happens**: Creates both specs with cross-references
- **Links**: Each spec references the other as alternative
- **When to Use**: Want to evaluate both approaches

#### 5. Show Detailed Comparison

- **What Happens**: Shows side-by-side comparison
- **Details**: Requirements, approach, complexity, pros/cons
- **Then**: Returns to resolution menu

### Detailed Comparison Example

```
📊 DETAILED COMPARISON

POC Feature: "User Authentication"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Complexity: Medium
Estimated Effort: 20 hours

Approach:
- OAuth 2.0 with JWT tokens
- Social login integration (Google, GitHub)
- Refresh token rotation
- Rate limiting on auth endpoints

Key Features:
- Stateless authentication
- Mobile-friendly
- Third-party integration ready

Existing Spec: 001-auth
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Priority: P1
Status: draft
Source: initial_research

Approach:
- Session-based authentication
- Email/password login
- Remember me functionality
- Password reset flow

Key Features:
- Simple implementation
- Server-side session management
- Traditional web app pattern

Press Enter to return to resolution menu...
```

### After Resolution

Depending on your choice:
- **Skip**: POC feature ignored, existing spec unchanged
- **Replace**: Old spec deprecated, new spec created
- **Merge**: Existing spec updated with merged content
- **Keep Both**: Two specs created with cross-references

---

## Complete Workflow

Here's how to use all sequencing features together:

### 1. Create Specs from Various Sources

```bash
# From initial research
speky init "Recipe sharing app"
# → Creates specs from research with P1/P2 priorities

# From POC
speky poc-import --path /path/to/poc
# → Imports features with dependencies
# → Detects conflicts with existing specs
# → Interactive resolution

# Manual specs
speky spec "Admin Dashboard"
# → Creates spec with default P1 priority
```

### 2. Infer Dependencies

```bash
# Analyze all specs for dependencies
speky infer-deps

# Or analyze specific spec
speky infer-deps 005
```

Output:
```
📋 Analyzing: 005-admin-dashboard

🔗 Inferred dependencies:
   • 001: Requires authentication for admin access
   • 002: Uses API endpoints for data management

✅ Added dependencies: 001, 002
```

### 3. View Implementation Roadmap

```bash
# See recommended order
speky sequence

# Export for team
speky sequence --export
```

### 4. Implement in Order

```bash
# Start with first spec (no dependencies)
speky plan 001
speky implement 001
speky complete 001

# Continue with next
speky plan 002  # Validates that 001 is complete
speky implement 002
speky complete 002

# Check updated roadmap
speky sequence
```

### 5. Handle Warnings

If you try to implement out of order:

```bash
speky plan 005
```

Output:
```
⚠️  DEPENDENCY WARNING for spec 005
   The following dependencies are not yet completed:

   • 001 (status: completed) ✅
   • 002 (status: draft) ❌

   Consider implementing these first, or proceed if you're sure.
   Run 'speky sequence' to see recommended order.

Continue anyway? [y/N]: n
```

Follow the recommendation:
```bash
speky plan 002
speky implement 002
speky complete 002

# Now 005 is ready
speky plan 005
```

---

## Examples

### Example 1: E-commerce App

**Initial State** (after init and POC import):

```
001-auth [P1, draft] - no dependencies
002-product-catalog [P1, draft] - no dependencies
003-shopping-cart [P1, draft] - depends on: 001, 002
004-checkout [P1, draft] - depends on: 003
005-payment [P0, draft] - depends on: 001, 004
006-admin [P2, draft] - depends on: 001, 002
```

**Sequence Output**:

```bash
speky sequence
```

```
📋 Recommended Implementation Order

⚡ P0 - BLOCKER:
   5. ⬜ 005-payment [needs: 001, 004]

⚡ P1 - HIGH PRIORITY:
   1. ⬜ 001-auth
   2. ⬜ 002-product-catalog
   3. ⬜ 003-shopping-cart [needs: 001, 002]
   4. ⬜ 004-checkout [needs: 003]

📋 P2 - MEDIUM PRIORITY:
   6. ⬜ 006-admin [needs: 001, 002]

📋 Next Steps:
   1. Run: speky plan 001
   2. Run: speky implement 001
```

**Implementation Order**:
1. 001-auth (foundation)
2. 002-product-catalog (foundation)
3. 003-shopping-cart (depends on 1, 2)
4. 004-checkout (depends on 3)
5. 005-payment (P0 blocker, depends on 1, 4)
6. 006-admin (P2, depends on 1, 2)

### Example 2: Circular Dependency

**Problem**:

```
001-api [P1] - depends on: 002
002-auth [P1] - depends on: 001
```

**Detection**:

```bash
speky sequence
```

```
⚠️  CIRCULAR DEPENDENCIES DETECTED:
   🔄 001 → 002 → 001
   
   Please review and fix these dependencies manually.
```

**Solution**:

Edit `status.json` files to break the cycle:

```json
// 001-api/status.json
{
  "id": "001",
  "dependencies": []  // Remove dependency on 002
}

// 002-auth/status.json
{
  "id": "002",
  "dependencies": ["001"]  // Auth depends on API
}
```

Or restructure:
- Create 001-core-api (no auth)
- Create 002-auth (depends on 001)
- Create 003-secured-api (depends on 002)

### Example 3: POC Conflict Resolution

**Scenario**: You have an existing auth spec from initial research, then import a POC with a different auth implementation.

**Conflict Detected**:

```
⚠️  SPEC CONFLICT DETECTED

📦 POC Feature: "Authentication System"
📄 Existing Spec: 001-auth (from initial_research)

🤖 AI Recommendation: MERGE
```

**Choose Merge**:

```
Your choice [1-5]: 3

🔄 Merging specs...

✅ Merged successfully!
   Updated: 001-auth
   Combined: Session-based auth + OAuth 2.0
   
   The merged spec now includes:
   - Traditional session auth for web
   - OAuth 2.0 for API and mobile
   - Unified user model
   - Flexible authentication strategy
```

**Result**: Single comprehensive spec with best of both approaches.

---

## Best Practices

### 1. Use Sequence Early and Often

```bash
# After creating specs
speky sequence

# Before starting implementation
speky sequence

# After completing each spec
speky sequence
```

### 2. Infer Dependencies After Bulk Creation

```bash
# Create multiple specs
speky spec "Feature A"
speky spec "Feature B"
speky spec "Feature C"

# Then infer relationships
speky infer-deps

# Review and adjust
speky sequence
```

### 3. Trust Dependency Warnings

When you see a dependency warning:
- ✅ **Do**: Follow the recommended order
- ❌ **Don't**: Skip warnings unless you have a good reason
- ✅ **Do**: Check `speky sequence` for context
- ❌ **Don't**: Implement specs in random order

### 4. Resolve Conflicts Thoughtfully

When POC conflicts arise:
- **Merge** is usually the best option (combines strengths)
- **Replace** if POC is clearly superior
- **Keep Both** if genuinely different approaches
- **Skip** if existing spec is sufficient

### 5. Keep Priorities Updated

```bash
# Edit status.json when priorities change
vim .speky/specs/003-feature/status.json

# Update priority field
{
  "priority": "P0"  // Changed from P2 to P0
}

# Check updated order
speky sequence
```

### 6. Export Roadmap for Team

```bash
# Export roadmap
speky sequence --export

# Commit to git
git add .speky/roadmap.md
git commit -m "docs: update implementation roadmap"
git push
```

### 7. Break Circular Dependencies

If you see circular dependencies:
1. Identify the cycle in `sequence` output
2. Determine which dependency is optional
3. Remove the optional dependency
4. Or restructure into smaller specs

### 8. Document Manual Dependencies

When manually adding dependencies:

```json
{
  "dependencies": ["001", "002"],
  "dependencies_note": "Needs auth (001) and API (002) for data access"
}
```

### 9. Use Priorities Meaningfully

- **P0**: Only for true blockers (security, critical bugs)
- **P1**: Core MVP features
- **P2**: Important enhancements
- **P3**: Nice-to-haves

### 10. Review Inferred Dependencies

After `infer-deps`:
1. Check `status.json` files
2. Verify dependencies make sense
3. Remove any incorrect ones
4. Add any missing ones manually

---

## Summary

SPEKY's sequencing system provides:

✅ **Automatic Priority Assignment** - Based on source and complexity  
✅ **Dependency Tracking** - From POC, imports, or AI inference  
✅ **Conflict Detection** - When POC overlaps with existing specs  
✅ **AI-Assisted Resolution** - Smart recommendations for conflicts  
✅ **Implementation Roadmap** - Clear order with dependency analysis  
✅ **Circular Detection** - Warns about dependency loops  
✅ **Validation** - Prevents out-of-order implementation  
✅ **Export** - Share roadmap with team  

Use these features to:
- Avoid rework from wrong implementation order
- Understand project structure at a glance
- Make informed decisions about conflicts
- Keep team aligned on priorities
- Maintain clean dependency graphs

---

## Quick Reference

```bash
# View roadmap
speky sequence

# Export roadmap
speky sequence --export

# Infer dependencies
speky infer-deps

# Infer for specific spec
speky infer-deps 003

# Plan with validation
speky plan 001

# Implement with validation
speky implement 001

# Import POC (with conflict detection)
speky poc-import
```

**Files to Check**:
- `.speky/specs/<id>-<name>/status.json` - Priority and dependencies
- `.speky/roadmap.md` - Exported roadmap
- `.speky/imports/poc_import/*/recommendations.md` - POC analysis

**Key Fields in status.json**:
```json
{
  "id": "001",
  "name": "Feature Name",
  "priority": "P0|P1|P2|P3",
  "dependencies": ["002", "003"],
  "source": "initial_research|poc_import|external_import|manual",
  "status": "draft|planned|in_progress|completed",
  "created": "2024-01-01T00:00:00",
  "dependencies_inferred_at": "2024-01-02T00:00:00"
}
```

## Project Structure for Sequencing

```
.speky/
├── specs/                           # All specs with dependencies
│   ├── 001-auth/
│   │   ├── spec.md
│   │   ├── plan.md
│   │   └── status.json              # priority: "P1", dependencies: []
│   ├── 002-api/
│   │   ├── spec.md
│   │   ├── plan.md
│   │   └── status.json              # priority: "P1", dependencies: ["001"]
│   └── 003-payments/
│       ├── spec.md
│       ├── plan.md
│       └── status.json              # priority: "P0", dependencies: ["001", "002"]
│
├── imports/                         # Source tracking
│   ├── initial_research/            # Specs from init
│   │   ├── source/
│   │   ├── analysis.md
│   │   └── manifest.json
│   ├── phase-mvp/                   # Specs from import
│   │   ├── source/
│   │   ├── analysis.md
│   │   ├── roadmap.md
│   │   └── manifest.json
│   └── poc_import/                  # Specs from POC
│       └── poc-20241226-120000/
│           ├── state.json
│           ├── results.json         # Feature dependencies
│           ├── recommendations.md   # Conflict resolutions
│           └── specs/
│
└── roadmap.md                       # Generated by: speky sequence --export
```

---

For more information, see:
- [README.md](README.md) - Quick start guide
- [DOCUMENTATION.md](DOCUMENTATION.md) - Complete documentation
- [IMPORT_FEATURE.md](IMPORT_FEATURE.md) - External knowledge import guide
