# Tech Stack Discussion - Collaborative Selection

## Overview

The tech stack selection is now a **collaborative discussion** between the developer and SPEKY (with AI suggestions), rather than a simple prompt-and-answer.

## Flow

### 1. Product Profile Built First
- AI generates product profile based on Q&A
- Profile includes: name, description, platform, scale, domain, features

### 2. AI Suggests Tech Stack Options
- AI analyzes the product profile
- Provides 3 options for each layer:
  - **Frontend**: React, React Native, Flutter, Vue, etc.
  - **Backend**: Node.js, Python, Go, Rust, Java, Serverless, etc.
  - **Database**: PostgreSQL, MongoDB, Firebase, DynamoDB, MySQL, Redis, etc.
  - **Deployment**: AWS, Vercel, Netlify, Docker, Kubernetes, Mobile app stores, etc.
- Includes rationale for why each option fits the product

### 3. Developer Reviews & Chooses
- Developer sees AI suggestions
- For each layer, developer can:
  - Accept one of the AI suggestions
  - Modify a suggestion
  - Provide their own choice
  - Choose "Not decided" to defer decision

### 4. Optional Discussion/Refinement
- For each tech choice, developer can opt into deeper discussion
- Prompts for: constraints, concerns, alternatives
- Captures developer's reasoning in context

### 5. Tech Stack Saved to Context
- Final tech stack stored in `context.json`
- Used by spec and plan generators for realistic scoping

## Implementation Details

### New Prompt Method: `suggest_tech_stack()`
```python
@staticmethod
def suggest_tech_stack(product_summary: str) -> str:
    """Suggest tech stack options based on product description"""
    # Returns 3 options for each layer with rationale
```

### Modified Flow in `cmd_init()`
```
1. Intent Clarification Q&A
2. Build Product Profile (AI)
3. Tech Stack Discussion (NEW)
   a. AI suggests options
   b. Developer chooses for each layer
   c. Optional discussion for each choice
4. Save to context
```

### Interactive Tech Stack Selection
```
For each layer (Frontend, Backend, Database, Deployment):
  - Show AI suggestions
  - Show examples
  - Prompt for developer choice
  - Offer discussion option
```

## Benefits

| Aspect | Before | After |
|--------|--------|-------|
| **AI Input** | ❌ None | ✅ 3 options per layer with rationale |
| **Developer Control** | ✅ Full | ✅ Full + informed by AI |
| **Discussion** | ❌ No | ✅ Optional refinement per choice |
| **Context Capture** | ❌ No | ✅ Reasoning captured for future reference |
| **Informed Decisions** | ❌ No | ✅ Decisions based on product profile |

## Example Interaction

```
──────────────────────────────────────────────────
🎯 Tech Stack Discussion
──────────────────────────────────────────────────

🎯 Product: CookClip
   Platform: mobile

🤖 AI will suggest tech stack options based on your product.
   You can accept suggestions, modify them, or provide your own choices.

📋 AI Tech Stack Suggestions:

# Tech Stack Recommendations

## Frontend
- **Option 1**: React Native - Cross-platform mobile development, large community
- **Option 2**: Flutter - Excellent performance, beautiful UI components
- **Option 3**: Native (Swift/Kotlin) - Best performance, platform-specific

## Backend
- **Option 1**: Node.js - Fast development, JavaScript ecosystem
- **Option 2**: Python - Great for AI/ML, easy to learn
- **Option 3**: Go - High performance, good for microservices

## Database
- **Option 1**: Firebase - Real-time, easy setup, good for MVP
- **Option 2**: PostgreSQL - Powerful, open-source, reliable
- **Option 3**: MongoDB - Flexible schema, good for rapid development

## Deployment
- **Option 1**: Firebase Hosting - Easy, integrated with backend
- **Option 2**: AWS - Scalable, many services available
- **Option 3**: Heroku - Simple deployment, good for MVP

## Rationale
For a mobile cooking app MVP, React Native + Node.js + Firebase provides
the fastest time-to-market with good scalability options.

───────────────────────────────────────────────

📌 Frontend framework/platform
   (See AI suggestions above)
   Examples: React, React Native, Flutter, Vue, Svelte, Next.js, Angular, None yet
Your choice for frontend: React Native

Discuss frontend choice further? (y/n): y
Your thoughts on frontend (constraints, concerns, alternatives): 
> Chose React Native for cross-platform support. Team has React experience.
> Could switch to Flutter later if performance becomes an issue.

📌 Backend/runtime
   (See AI suggestions above)
   Examples: Node.js, Python, Go, Rust, Java, Serverless (AWS Lambda), None yet
Your choice for backend: Node.js

Discuss backend choice further? (y/n): n

📌 Database/storage
   (See AI suggestions above)
   Examples: PostgreSQL, MongoDB, Firebase, DynamoDB, MySQL, Redis, None yet
Your choice for database: Firebase

Discuss database choice further? (y/n): n

📌 Deployment target
   (See AI suggestions above)
   Examples: AWS, Vercel, Netlify, Docker, Kubernetes, Mobile app stores, None yet
Your choice for deployment: Firebase Hosting

Discuss deployment choice further? (y/n): n

✅ Tech Stack saved: React Native + Node.js + Firebase + Firebase Hosting
```

## Files Modified

- `/Users/Shared/ALL WORKSPACE/projects/SPEKY/speky.py`
  - Added `suggest_tech_stack()` prompt method
  - Modified `cmd_init()` to include tech stack discussion after profile building
  - Captures developer reasoning in QA pairs

## Next Steps

1. Test with a new project to see collaborative tech stack discussion
2. Verify AI suggestions are helpful and realistic
3. Confirm tech stack is properly used in spec/plan generation
