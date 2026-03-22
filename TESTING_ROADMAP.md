# SPEKY Testing Roadmap

**Version:** 1.0  
**Last Updated:** January 12, 2026  
**Purpose:** Guide testing strategy as projects grow from MVP to enterprise scale

---

## Table of Contents

1. [Overview](#overview)
2. [Growth Stages](#growth-stages)
3. [Stage 1: MVP (0-100 tests)](#stage-1-mvp-0-100-tests)
4. [Stage 2: Early Growth (100-500 tests)](#stage-2-early-growth-100-500-tests)
5. [Stage 3: Scale (500-1000 tests)](#stage-3-scale-500-1000-tests)
6. [Stage 4: Enterprise (1000+ tests)](#stage-4-enterprise-1000-tests)
7. [Migration Paths](#migration-paths)
8. [Decision Trees](#decision-trees)
9. [Metrics & KPIs](#metrics--kpis)

---

## Overview

This roadmap provides **stage-appropriate testing strategies** as your project grows. Each stage has different needs, constraints, and optimal approaches.

### Key Principle

**Start simple, add complexity only when needed.**

Don't over-engineer testing for a 10-test MVP. Don't under-engineer for a 1000-test enterprise app.

---

## Growth Stages

| Stage | Test Count | Team Size | Strategy | Complexity |
|-------|-----------|-----------|----------|------------|
| **MVP** | 0-100 | 1-2 devs | Run all tests | Low |
| **Early Growth** | 100-500 | 2-5 devs | Run all tests | Low-Medium |
| **Scale** | 500-1000 | 5-10 devs | Targeted + CI | Medium |
| **Enterprise** | 1000+ | 10+ devs | Advanced | High |

---

## Stage 1: MVP (0-100 tests)

### Characteristics

- **Team:** 1-2 developers
- **Tests:** 0-100 tests
- **Runtime:** < 30 seconds
- **Focus:** Core features only

### Testing Strategy

**✅ DO:**
1. **Run all tests before every commit**
   ```bash
   flutter test  # or pytest, npm test
   ```
   
2. **Focus on unit tests (80%)**
   - Business logic
   - Services
   - Models
   - Utilities

3. **Minimal widget/component tests (15%)**
   - Critical UI components only
   - User flows

4. **Skip E2E tests (5% or 0%)**
   - Manual testing is fine at this stage
   - E2E is expensive to maintain

5. **Use SPEKY for test generation**
   ```bash
   speky test gen <spec-id>
   ```

**❌ DON'T:**
- Don't set up complex test infrastructure
- Don't parallelize tests (not needed)
- Don't use test sharding
- Don't implement visual regression testing
- Don't build custom test runners

### Workflow

```bash
# 1. Initialize testing
speky test init

# 2. Generate tests for each spec
speky test gen 001
speky test gen 002
speky test gen 003

# 3. Before every commit
flutter test  # Must pass!

# 4. Commit
git commit -m "feat: add feature"
```

### CI/CD Setup

**Simple GitHub Actions:**

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: subosito/flutter-action@v2
      - run: flutter pub get
      - run: flutter test
```

### Metrics

- **Coverage target:** 70%
- **Test runtime:** < 30 seconds
- **Failure rate:** < 5%

### When to Graduate to Stage 2

**Indicators:**
- ✅ Test count > 100
- ✅ Test runtime > 1 minute
- ✅ Team size > 2 developers
- ✅ Multiple features in production

---

## Stage 2: Early Growth (100-500 tests)

### Characteristics

- **Team:** 2-5 developers
- **Tests:** 100-500 tests
- **Runtime:** 1-3 minutes
- **Focus:** Feature expansion

### Testing Strategy

**✅ DO:**
1. **Continue running all tests locally**
   - Still fast enough (< 3 minutes)
   - Complete confidence

2. **Add widget/component tests (20%)**
   - More UI coverage
   - User interaction testing

3. **Introduce E2E tests (10%)**
   - Critical user flows only
   - Happy path scenarios

4. **Set up coverage tracking**
   ```bash
   speky test coverage --by-spec
   ```

5. **Add coverage to CI**
   ```yaml
   - run: flutter test --coverage
   - uses: codecov/codecov-action@v3
   ```

**❌ DON'T:**
- Don't implement test sharding yet
- Don't parallelize locally (CI can parallelize)
- Don't add visual regression testing yet
- Don't build complex test infrastructure

### Workflow

```bash
# 1. Generate tests for new specs
speky test gen 005

# 2. Run all tests before commit
flutter test  # 2-3 minutes

# 3. Check coverage periodically
speky test coverage --gaps

# 4. Generate tests for gaps
speky test gen 006 --type unit
```

### CI/CD Setup

**Enhanced with coverage:**

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: subosito/flutter-action@v2
      - run: flutter pub get
      - run: flutter test --coverage
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: coverage/lcov.info
          
      - name: Check coverage threshold
        run: |
          coverage=$(lcov --summary coverage/lcov.info | grep lines | awk '{print $2}' | sed 's/%//')
          if (( $(echo "$coverage < 70" | bc -l) )); then
            echo "Coverage $coverage% is below 70%"
            exit 1
          fi
```

### Metrics

- **Coverage target:** 75%
- **Test runtime:** 1-3 minutes
- **Failure rate:** < 3%
- **Flaky test rate:** < 1%

### When to Graduate to Stage 3

**Indicators:**
- ✅ Test count > 500
- ✅ Test runtime > 3 minutes
- ✅ Team size > 5 developers
- ✅ Multiple teams working on codebase

---

## Stage 3: Scale (500-1000 tests)

### Characteristics

- **Team:** 5-10 developers
- **Tests:** 500-1000 tests
- **Runtime:** 3-10 minutes
- **Focus:** Stability & velocity

### Testing Strategy

**✅ DO:**
1. **Implement targeted testing locally**
   ```bash
   # Run affected tests only
   speky test run --affected
   
   # Run tests for specific spec
   speky test run --spec 005
   ```

2. **CI runs full suite**
   - Parallel test execution
   - Test sharding
   - Matrix builds

3. **Add E2E tests (15%)**
   - Critical user flows
   - Integration points
   - Edge cases

4. **Implement flaky test detection**
   - Track failure patterns
   - Quarantine flaky tests
   - Fix or remove

5. **Add visual regression testing**
   - Percy, Chromatic, or similar
   - Critical UI components
   - Design system components

**❌ DON'T:**
- Don't run full suite locally every time
- Don't add E2E tests for everything
- Don't ignore flaky tests
- Don't skip coverage tracking

### Workflow

```bash
# 1. Generate tests for new feature
speky test gen 010

# 2. Run affected tests during development
speky test run --affected  # Fast feedback

# 3. Before commit, run spec tests
speky test run --spec 010  # ~30 seconds

# 4. CI runs full suite
# GitHub Actions runs all 800 tests in parallel
```

### CI/CD Setup

**Advanced with parallelization:**

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        shard: [1, 2, 3, 4]  # 4 parallel shards
    steps:
      - uses: actions/checkout@v3
      - uses: subosito/flutter-action@v2
      - run: flutter pub get
      - run: flutter test --coverage --shard-index ${{ matrix.shard }} --total-shards 4
      
  e2e-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v3
      - uses: subosito/flutter-action@v2
      - run: flutter test integration_test/
      
  visual-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v3
      - name: Percy visual tests
        run: npx percy exec -- flutter test
        env:
          PERCY_TOKEN: ${{ secrets.PERCY_TOKEN }}
```

### Metrics

- **Coverage target:** 80%
- **Local test runtime:** < 1 minute (affected tests)
- **CI test runtime:** < 5 minutes (parallelized)
- **Failure rate:** < 2%
- **Flaky test rate:** < 0.5%

### When to Graduate to Stage 4

**Indicators:**
- ✅ Test count > 1000
- ✅ CI runtime > 10 minutes
- ✅ Team size > 10 developers
- ✅ Multiple products/services

---

## Stage 4: Enterprise (1000+ tests)

### Characteristics

- **Team:** 10+ developers
- **Tests:** 1000+ tests
- **Runtime:** 10+ minutes (full suite)
- **Focus:** Efficiency & reliability

### Testing Strategy

**✅ DO:**
1. **Advanced test selection**
   ```bash
   # Intelligent affected test detection
   speky test run --affected --smart
   
   # Test impact analysis
   speky test analyze <file>
   ```

2. **Distributed test execution**
   - Cloud test runners
   - Parallel execution across machines
   - Test result caching

3. **Comprehensive E2E coverage (20%)**
   - All critical flows
   - Integration scenarios
   - Performance testing

4. **Advanced monitoring**
   - Test health dashboard
   - Flaky test tracking
   - Performance regression detection
   - Coverage trends

5. **Test data management**
   - Synthetic data generation
   - Database snapshots
   - Test environment management

**❌ DON'T:**
- Don't run full suite locally
- Don't ignore test performance
- Don't let flaky tests accumulate
- Don't skip test maintenance

### Workflow

```bash
# 1. Generate tests for new feature
speky test gen 050

# 2. Run smart affected tests
speky test run --affected --smart  # ~30 seconds

# 3. Before commit, run spec tests
speky test run --spec 050  # ~20 seconds

# 4. CI runs full suite with caching
# Only re-runs tests affected by changes
```

### CI/CD Setup

**Enterprise-grade:**

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test-selection:
    runs-on: ubuntu-latest
    outputs:
      affected-tests: ${{ steps.detect.outputs.tests }}
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0  # Full history for impact analysis
      - id: detect
        run: |
          # Detect affected tests
          affected=$(speky test analyze --changed-files)
          echo "tests=$affected" >> $GITHUB_OUTPUT

  unit-tests:
    runs-on: ubuntu-latest
    needs: test-selection
    strategy:
      matrix:
        shard: [1, 2, 3, 4, 5, 6, 7, 8]  # 8 parallel shards
    steps:
      - uses: actions/checkout@v3
      - uses: subosito/flutter-action@v2
      - name: Restore test cache
        uses: actions/cache@v3
        with:
          path: ~/.flutter-test-cache
          key: test-cache-${{ hashFiles('**/*.dart') }}
      - run: flutter test --shard-index ${{ matrix.shard }} --total-shards 8
      
  e2e-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    strategy:
      matrix:
        browser: [chromium, firefox, webkit]
    steps:
      - uses: actions/checkout@v3
      - name: Run E2E on ${{ matrix.browser }}
        run: flutter test integration_test/ --browser ${{ matrix.browser }}
        
  performance-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v3
      - name: Run performance benchmarks
        run: flutter test --performance
      - name: Check for regressions
        run: |
          # Compare with baseline
          speky test perf compare
```

### Advanced Features

**Test Impact Analysis:**
```bash
# Analyze which tests are affected by a file change
speky test analyze lib/features/auth/auth_service.dart

# Output:
# Affected tests:
#   - test/unit/auth_service_test.dart
#   - test/integration/auth_flow_test.dart
#   - test/e2e/login_e2e_test.dart
# Estimated runtime: 45 seconds
```

**Flaky Test Management:**
```bash
# Detect flaky tests
speky test flaky detect

# Quarantine flaky tests
speky test flaky quarantine test/e2e/tab_persistence_test.dart

# Run quarantined tests separately
speky test run --quarantined
```

**Test Data Management:**
```bash
# Generate synthetic test data
speky test data generate --count 1000

# Create database snapshot
speky test data snapshot production-like

# Restore snapshot for testing
speky test data restore production-like
```

### Metrics

- **Coverage target:** 85%
- **Local test runtime:** < 30 seconds (smart affected)
- **CI test runtime:** < 10 minutes (parallelized + cached)
- **Failure rate:** < 1%
- **Flaky test rate:** < 0.1%
- **Test maintenance time:** < 10% of dev time

---

## Migration Paths

### From Stage 1 to Stage 2

**Triggers:**
- Test count > 100
- Test runtime > 1 minute

**Actions:**
1. Add coverage tracking to CI
2. Start tracking coverage by spec
3. Add widget/component tests
4. Introduce first E2E tests

**Timeline:** 1-2 weeks

---

### From Stage 2 to Stage 3

**Triggers:**
- Test count > 500
- Test runtime > 3 minutes
- Team size > 5

**Actions:**
1. Implement targeted testing locally
2. Add test parallelization to CI
3. Set up flaky test detection
4. Add visual regression testing

**Timeline:** 2-4 weeks

---

### From Stage 3 to Stage 4

**Triggers:**
- Test count > 1000
- CI runtime > 10 minutes
- Team size > 10

**Actions:**
1. Implement smart test selection
2. Set up distributed test execution
3. Add test impact analysis
4. Implement advanced monitoring

**Timeline:** 4-8 weeks

---

## Decision Trees

### Should I Run All Tests Locally?

```
Test count < 100?
├─ YES → Run all tests (< 30 seconds)
└─ NO → Test count < 500?
    ├─ YES → Run all tests (< 3 minutes)
    └─ NO → Test count < 1000?
        ├─ YES → Run affected tests locally, all in CI
        └─ NO → Run smart affected tests locally, all in CI
```

### Should I Add E2E Tests?

```
MVP stage (< 100 tests)?
├─ YES → Skip E2E, manual testing is fine
└─ NO → Early Growth (100-500 tests)?
    ├─ YES → Add E2E for critical flows only (10%)
    └─ NO → Scale (500-1000 tests)?
        ├─ YES → Expand E2E coverage (15%)
        └─ NO → Enterprise (1000+ tests)
            └─ YES → Comprehensive E2E (20%)
```

### Should I Parallelize Tests?

```
Test runtime < 1 minute?
├─ YES → No parallelization needed
└─ NO → Test runtime < 5 minutes?
    ├─ YES → Parallelize in CI only
    └─ NO → Test runtime < 10 minutes?
        ├─ YES → Parallelize in CI + use test sharding
        └─ NO → Distributed execution + caching
```

---

## Metrics & KPIs

### Coverage Metrics

| Stage | Target | Enforcement |
|-------|--------|-------------|
| MVP | 70% | Soft warning |
| Early Growth | 75% | Soft warning |
| Scale | 80% | CI warning |
| Enterprise | 85% | CI block |

### Performance Metrics

| Stage | Local Runtime | CI Runtime | Acceptable? |
|-------|--------------|-----------|-------------|
| MVP | < 30s | < 1m | ✅ |
| Early Growth | < 3m | < 5m | ✅ |
| Scale | < 1m (affected) | < 5m | ✅ |
| Enterprise | < 30s (smart) | < 10m | ✅ |

### Quality Metrics

| Metric | Target | Critical Threshold |
|--------|--------|-------------------|
| Failure rate | < 2% | > 5% |
| Flaky test rate | < 0.5% | > 2% |
| Test maintenance time | < 10% | > 20% |
| Coverage trend | Increasing | Decreasing |

### Test Distribution

| Stage | Unit | Widget/Component | E2E |
|-------|------|------------------|-----|
| MVP | 80% | 15% | 5% |
| Early Growth | 70% | 20% | 10% |
| Scale | 65% | 20% | 15% |
| Enterprise | 60% | 20% | 20% |

---

## Summary

### Key Takeaways

1. **Start simple** - Run all tests at MVP stage
2. **Add complexity gradually** - Only when needed
3. **Optimize for feedback speed** - Fast tests = fast development
4. **Maintain test health** - Fix flaky tests immediately
5. **Track metrics** - Coverage, runtime, failure rate

### Stage Progression

```
MVP (0-100 tests)
  ↓ Test count > 100
Early Growth (100-500 tests)
  ↓ Test count > 500
Scale (500-1000 tests)
  ↓ Test count > 1000
Enterprise (1000+ tests)
```

### Testing Philosophy

**At every stage:**
- ✅ Unit tests are the foundation (60-80%)
- ✅ Run tests before every commit
- ✅ Link tests to specs for traceability
- ✅ Use SPEKY for test generation
- ✅ Fix failures immediately
- ✅ Keep tests fast and reliable

**Remember:**
> "The best test suite is the one that developers actually run."

---

## Next Steps

1. **Identify your current stage** - Count your tests
2. **Follow stage-appropriate strategy** - Don't over-engineer
3. **Track metrics** - Coverage, runtime, failure rate
4. **Plan for next stage** - When to migrate
5. **Read:** [TESTING_GUIDE.md](./TESTING_GUIDE.md) for detailed workflows

---

**Questions or feedback?** File an issue on GitHub or contribute to this roadmap.
