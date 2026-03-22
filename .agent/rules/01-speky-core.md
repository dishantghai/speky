# SPEKY Rules (Core) - Auto-generated
# Do not edit manually - regenerated on each SPEKY command
# Size: 4962 chars (max: 8000)

# SPEKY Project Rules

This project uses **SPEKY** (AI-Assisted Scalable Engineering Framework) for spec-driven development.
**You MUST follow SPEKY workflow. Do NOT bypass these processes.**

## CRITICAL: SPEKY Workflow Enforcement

### 🚨 MANDATORY: Follow SPEKY Process

1. **Before implementing ANY new feature:**
   - Check if a spec exists in `.speky/specs/`
   - If NO spec exists, tell the developer: "This feature needs a spec first. Run: `speky spec \"Feature name\"`"
   - Do NOT implement features without a spec

2. **Before making significant changes:**
   - Check the relevant spec in `.speky/specs/*/spec.md`
   - Verify changes align with the spec's scope
   - If changes are out-of-scope, inform the developer

3. **When asked to create a new feature:**
   - Do NOT create your own spec files
   - Tell the developer: "Let's create a proper spec first. Run: `speky spec \"Feature name\"`"
   - Wait for the spec to be created via SPEKY

4. **When implementation is complete:**
   - Do NOT create completion marker files
   - Tell the developer: "Implementation complete. Run: `speky complete <id>` to verify and mark done"
   - Works for both specs (001) and stories (F001, B001, etc.)

### 🔄 Correct Workflow Example

```
Developer: "Add user authentication"
You: "I'll check if there's a spec for this feature..."
     [Check .speky/specs/ for auth-related spec]
     
If spec exists:
     "Found spec 003-user-authentication. I'll implement according to the plan."
     [Implement based on spec and plan]
     
If NO spec exists:
     "This feature needs a spec first. Please run:
      speky spec \"User authentication\"
      Then run: speky plan 003
      Then run: speky implement 003"
```

### 📅 Phase-Aware Implementation

**If phases exist** (check `.speky/phases/`):
1. Check which phase is current: look for `status: in_progress` in `manifest.yaml`
2. Only implement specs that belong to the current phase
3. Check phase `excludes` for what NOT to implement
4. Reference phase guide: `.speky/phases/<phase-id>/implementation.md`

**When to suggest phases:**
- If project has 5+ specs and no phases, suggest: "You have multiple specs. Consider `speky phases suggest` to organize implementation."

### 🔧 CRITICAL: Tech Decisions

**BEFORE suggesting or using ANY package/framework:**
1. Check if `.speky/context/tech_decisions.md` exists
2. If it exists, you MUST use ONLY the packages listed there
3. NEVER suggest alternatives to decided technologies
4. If a spec uses wrong packages, flag it for correction

Example tech_decisions.md content:
```
## Database: Drift (not SQLite/sqflite)
## WebView: flutter_inappwebview (not webview_flutter)
## State: Riverpod (not Provider)
```

### 🎯 Your Role

You are the **implementation assistant**. Your job is to:
1. ✅ Implement code according to existing specs
2. ✅ Follow the plan in `.speky/specs/*/plan.md`
3. ✅ Stay within scope defined in specs
4. ✅ Write clean, production-ready code
5. ✅ Guide developer to use SPEKY commands when needed

You should NOT:
1. ❌ Create specs or plans (SPEKY does this)
2. ❌ Implement features without specs
3. ❌ Create documentation files in root
4. ❌ Mark things as complete (developer uses `speky complete`)
5. ❌ Bypass the SPEKY workflow

### ❌ What NOT To Do

- ❌ Implement features without checking for a spec first
- ❌ Create your own spec or plan files
- ❌ Create `FEATURE_NAME_SPEC.md` in root
- ❌ Create `IMPLEMENTATION_COMPLETE.md` in root
- ❌ Create `implementation_notes.md` in root
- ❌ Create `analysis_*.md` files in root
- ❌ Create any `.md` files in root (except README.md)
- ❌ Duplicate spec content outside `.speky/`
- ❌ Create progress tracking files
- ❌ Bypass SPEKY workflow
- ❌ Implement out-of-scope items without a new spec

## Implementation Guidelines

### When Implementing a Spec

1. **Read spec from**: `.speky/specs/NNN-feature-name/spec.md`
2. **Read plan from**: `.speky/specs/NNN-feature-name/plan.md`
3. **Reference context**: `.speky/context/context.json`
4. **Stay in scope**: Only implement what's in the spec
5. **Create code in**: appropriate project directories (`backend/`, `frontend/`, `src/`, etc.)
6. **Update existing docs**: `README.md`, `docs/` if needed
7. **DO NOT CREATE**: Extra documentation, spec, or summary files

### Scope Enforcement

- **In Scope**: Implement everything listed in spec's "User Stories" and "Acceptance Criteria"
- **Out of Scope**: Do NOT implement items listed in "Out of Scope" section
- **If asked for out-of-scope items**: Tell developer to create a new spec for that feature

### Code Quality
- Follow existing code style and patterns
- Add appropriate error handling
- Include necessary imports at top of files
- Write clean, maintainable code

### After Implementation
- Do NOT create completion marker files
- Do NOT create summary files
- Tell developer: "Run `speky complete <id>` to verify and mark done"
- Works for both specs (001) and stories (F001, B001, etc.)
