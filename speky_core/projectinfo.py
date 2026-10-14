"""What an existing project says about itself — docs, manifests, structure, tech stack — read
deterministically (ported unchanged from v2's `init --from-project`). The agent uses this as the
starting evidence for the speky-init skill.
"""
import json
import re
from pathlib import Path
from typing import List

EVIDENCE_SKIP_DIRS = {".git", ".speky", "node_modules", "vendor", "dist", "build", "out",
                           ".next", ".venv", "venv", "env", "__pycache__", "target", ".idea",
                           ".vscode", "coverage", ".dart_tool", "Pods", ".gradle"}
EVIDENCE_MANIFESTS = ["package.json", "pyproject.toml", "requirements.txt", "setup.py",
                           "Pipfile", "go.mod", "Cargo.toml", "pubspec.yaml", "Gemfile",
                           "pom.xml", "build.gradle", "build.gradle.kts", "composer.json",
                           "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                           "compose.yaml", "vercel.json", "netlify.toml", "fly.toml",
                           "serverless.yml", "app.yaml", "firebase.json", "wrangler.toml"]


def collect_evidence(root: Path) -> dict:
        """Gather what an existing project says about itself: docs, manifests, structure.

        Returns {"docs": [Path], "manifests": [Path], "tree": str,
                 "detected_tech": dict, "summary": str}.
        """

        def skipped(path: Path) -> bool:
            return any(part in EVIDENCE_SKIP_DIRS or part.startswith(".")
                       for part in path.relative_to(root).parts[:-1])

        # Docs: agent/readme files first, then root markdown, then docs/ (smallest first)
        priority = ["README.md", "README.rst", "README.txt", "README", "CLAUDE.md", "AGENTS.md",
                    "GEMINI.md", ".cursorrules", ".windsurfrules", "CONTRIBUTING.md"]
        docs = [root / n for n in priority if (root / n).is_file()]
        boring = {"CHANGELOG.md", "LICENSE.md", "CODE_OF_CONDUCT.md", "SECURITY.md"}
        docs += sorted((f for f in root.glob("*.md")
                        if f not in docs and f.name not in boring), key=lambda f: f.stat().st_size)
        for folder in ("docs", "doc", "documentation", "design", "specs"):
            if (root / folder).is_dir():
                docs += sorted((f for f in (root / folder).rglob("*") if f.suffix in (".md", ".txt")
                                and f.is_file() and not skipped(f)), key=lambda f: f.stat().st_size)
        docs = docs[:25]

        manifests = [root / n for n in EVIDENCE_MANIFESTS if (root / n).is_file()]

        # Two-level directory outline
        lines = []
        for entry in sorted(root.iterdir()):
            if entry.name in EVIDENCE_SKIP_DIRS or entry.name.startswith("."):
                continue
            lines.append(f"{entry.name}/" if entry.is_dir() else entry.name)
            if entry.is_dir():
                children = sorted(c.name + ("/" if c.is_dir() else "") for c in entry.iterdir()
                                  if not c.name.startswith(".") and c.name not in EVIDENCE_SKIP_DIRS)
                lines += [f"  {c}" for c in children[:15]]
                if len(children) > 15:
                    lines.append(f"  … {len(children) - 15} more")
        tree = "\n".join(lines[:200])

        # One-line summary: first real paragraph of the README, else the folder name
        summary = f"Existing project '{root.name}'"
        if docs and docs[0].name.lower().startswith("readme"):
            try:
                text = docs[0].read_text(errors="ignore")
                title = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("# ")), "")
                para = next((l.strip() for l in text.splitlines()
                             if l.strip() and not l.lstrip().startswith(("#", "!", "[", "<", "```", "|", "-", ">"))), "")
                summary = " — ".join(x for x in (title or root.name, para.strip("*_ ")) if x)[:300]
            except OSError:
                pass

        return {"docs": docs, "manifests": manifests, "tree": tree,
                "detected_tech": detect_tech(manifests), "summary": summary}


def detect_tech(manifests: List[Path]) -> dict:
        """Read the tech stack straight from dependency/deploy files (no AI needed)."""
        found = {"frontend": [], "backend": [], "database": [], "deployment": []}

        def add(kind, name):
            if name not in found[kind]:
                found[kind].append(name)

        texts = {}
        for m in manifests:
            try:
                texts[m.name] = m.read_text(errors="ignore")
            except OSError:
                pass
        deps = ""
        if "package.json" in texts:
            try:
                pkg = json.loads(texts["package.json"])
                deps = " ".join(list(pkg.get("dependencies", {})) + list(pkg.get("devDependencies", {})))
            except json.JSONDecodeError:
                deps = texts["package.json"]
        py = " ".join(texts.get(n, "") for n in ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile")).lower().strip()
        dep_words = set(re.split(r"[\s\"',]+", deps.lower()))

        for pkg_name, label in [("next", "Next.js"), ("react-native", "React Native"), ("expo", "React Native (Expo)"),
                                ("nuxt", "Nuxt"), ("vue", "Vue"), ("@sveltejs/kit", "SvelteKit"), ("svelte", "Svelte"),
                                ("@angular/core", "Angular"), ("react", "React")]:
            if pkg_name in dep_words:
                add("frontend", label)
                if label in ("Next.js", "Nuxt", "SvelteKit") or "native" in label.lower():
                    break
        if "pubspec.yaml" in texts:
            add("frontend", "Flutter")
        for fullstack in ("Next.js", "Nuxt", "SvelteKit"):
            if fullstack in found["frontend"]:
                add("backend", f"{fullstack} server (API routes)")
        for pkg_name, label in [("@nestjs/core", "Node.js (NestJS)"), ("express", "Node.js (Express)"),
                                ("fastify", "Node.js (Fastify)"), ("hono", "Node.js (Hono)"), ("koa", "Node.js (Koa)")]:
            if pkg_name in dep_words:
                add("backend", label)
        for word, label in [("django", "Python (Django)"), ("fastapi", "Python (FastAPI)"), ("flask", "Python (Flask)")]:
            if re.search(rf"\b{word}\b", py):
                add("backend", label)
        if py and not found["backend"]:
            add("backend", "Python")
        for name, label in [("go.mod", "Go"), ("Cargo.toml", "Rust"), ("pom.xml", "Java/Kotlin (Maven)"),
                            ("build.gradle", "Java/Kotlin (Gradle)"), ("build.gradle.kts", "Kotlin (Gradle)"),
                            ("Gemfile", "Ruby"), ("composer.json", "PHP")]:
            if name in texts:
                add("backend", label + (" (Rails)" if name == "Gemfile" and "rails" in texts[name] else ""))

        everything = (deps + " " + py + " " + " ".join(texts.get(n, "") for n in
                      ("pubspec.yaml", "go.mod", "Cargo.toml", "docker-compose.yml", "docker-compose.yaml",
                       "compose.yaml", "Gemfile", "pom.xml", "build.gradle"))).lower()
        for needle, label in [("postgres", "PostgreSQL"), ("psycopg", "PostgreSQL"), ("prisma", "Prisma (SQL)"),
                              ("mongo", "MongoDB"), ("mysql", "MySQL"), ("sqlite", "SQLite"), ("redis", "Redis"),
                              ("supabase", "Supabase"), ("firebase", "Firebase"), ("firestore", "Firebase"),
                              ("dynamodb", "DynamoDB")]:
            if needle in everything:
                add("database", label)
        if dep_words & {"pg", "postgres", "pg-promise"}:
            add("database", "PostgreSQL")

        for name, label in [("vercel.json", "Vercel"), ("netlify.toml", "Netlify"), ("fly.toml", "Fly.io"),
                            ("serverless.yml", "Serverless (AWS Lambda)"), ("app.yaml", "Google App Engine"),
                            ("firebase.json", "Firebase Hosting"), ("wrangler.toml", "Cloudflare Workers"),
                            ("Dockerfile", "Docker"), ("docker-compose.yml", "Docker Compose"),
                            ("docker-compose.yaml", "Docker Compose"), ("compose.yaml", "Docker Compose")]:
            if name in texts:
                add("deployment", label)
        if "pubspec.yaml" in texts or "react-native" in dep_words or "expo" in dep_words:
            add("deployment", "Mobile app stores")

        return {k: ", ".join(v) for k, v in found.items() if v}
