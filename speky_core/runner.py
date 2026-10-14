"""`speky run`: SPEKY's own agent, for working without a coding agent.

A small, provider-agnostic loop over SPEKY's model router (any provider in ~/.speky/models.yaml, an
API key, or a Claude subscription through the `claude` CLI). Each turn the model answers with one JSON
object naming a tool; the runner executes it and shows the result. It follows the same skills and
`speky next` protocol a coding agent would, so the work lands in the same files.

This is the only part of SPEKY that talks to a model or asks the user a question.

Safety: file tools are confined to the repository (never `.git/`); shell commands are limited to the
project's test commands and read-only git unless `--allow-shell` is given; `ask_user` needs a terminal
(otherwise the model is told to make an informed guess and record it as an assumption).
"""
import fnmatch
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional

from . import harness, protocol
from .errors import SpekyError
from .items import Project

MAX_OBSERVATION = 6000
MAX_TRANSCRIPT = 120_000
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "target"}

TOOLS_DOC = """Tools (answer with exactly ONE JSON object per turn, nothing else):
{"tool": "read_file", "args": {"path": "src/app.py", "start": 1, "limit": 200}}
{"tool": "list_files", "args": {"path": ".", "pattern": "*.py"}}
{"tool": "search", "args": {"pattern": "def login", "path": "src"}}
{"tool": "write_file", "args": {"path": "src/new.py", "content": "..."}}
{"tool": "edit_file", "args": {"path": "src/app.py", "old": "exact old text", "new": "replacement"}}
{"tool": "speky", "args": {"argv": ["next"]}}            -- any speky command; output is JSON
{"tool": "run", "args": {"command": "pytest -q"}}         -- tests and read-only git; others may be refused
{"tool": "skill", "args": {"name": "speky-test"}}       -- read another SPEKY skill
{"tool": "ask_user", "args": {"question": "...", "recommended": "..."}}   -- one question at a time
{"tool": "finish", "args": {"summary": "what was done, evidence, what is next"}}
Add "why": "<one short sentence>" to each call. Paths are relative to the repository root."""


class Runner:
    def __init__(self, project: Project, complete: Callable[[str, str], str], allow_shell: bool = False,
                 interactive: Optional[bool] = None, log: Callable[[str], None] = None,
                 max_steps: int = 60):
        self.project = project
        self.root = project.root.resolve()
        self.complete = complete
        self.allow_shell = allow_shell
        self.interactive = sys.stdin.isatty() if interactive is None else interactive
        self.log = log or (lambda m: print(m, file=sys.stderr, flush=True))
        self.max_steps = max_steps
        self.steps: List[dict] = []

    # ------------------------------------------------------------------ prompt
    def system_prompt(self, goal: str) -> str:
        skills_dir = harness.SKILLS_DIR
        nxt = protocol.next_action(self.project) if self.project.dir.is_dir() else {"skill": None}
        parts = ["You are SPEKY's built-in agent working in a software repository. Do the work the user "
                 "asked for by following SPEKY's workflow and skills below. Read before you write. Never "
                 "claim something passed without running it in this session. Stop with `finish`.",
                 TOOLS_DOC]
        if self.project.dir.is_dir():
            parts.append(protocol.prime(self.project))
        names = ["speky"] + ([nxt["skill"]] if nxt.get("skill") and nxt["skill"] != "speky" else [])
        for name in names:
            path = skills_dir / name / "SKILL.md"
            if path.exists():
                parts.append(f"## Skill: {name}\n" + path.read_text().split("---", 2)[-1].strip())
        others = [n for n in harness.skill_names() if n not in names]
        parts.append("Other skills (read one with the `skill` tool when the task needs it): " + ", ".join(others))
        return "\n\n".join(parts)

    # ------------------------------------------------------------------ tools
    def _path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise SpekyError("outside_repository", f"{rel} is outside the repository.")
        if ".git" in p.relative_to(self.root).parts:
            raise SpekyError("protected_path", "The .git folder is off limits.")
        return p

    def tool_read_file(self, path: str, start: int = 1, limit: int = 400) -> str:
        p = self._path(path)
        if not p.is_file():
            return f"(no file {path})"
        lines = p.read_text(errors="replace").splitlines()
        chunk = lines[max(start, 1) - 1:max(start, 1) - 1 + limit]
        more = f"\n… {len(lines)} lines in total" if len(lines) > start - 1 + limit else ""
        return "\n".join(f"{i}: {l}" for i, l in enumerate(chunk, max(start, 1))) + more

    def tool_list_files(self, path: str = ".", pattern: str = "*") -> str:
        base = self._path(path)
        out = []
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(self.root)
            if any(part in SKIP_DIRS for part in rel.parts) or not p.is_file():
                continue
            if fnmatch.fnmatch(p.name, pattern):
                out.append(str(rel))
            if len(out) >= 300:
                out.append("… (more)")
                break
        return "\n".join(out) or "(nothing)"

    def tool_search(self, pattern: str, path: str = ".") -> str:
        rx = re.compile(pattern)
        hits = []
        for p in sorted(self._path(path).rglob("*")):
            rel = p.relative_to(self.root)
            if any(part in SKIP_DIRS for part in rel.parts) or not p.is_file() or p.stat().st_size > 1_000_000:
                continue
            try:
                for n, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{rel}:{n}: {line.strip()[:200]}")
                        if len(hits) >= 100:
                            return "\n".join(hits) + "\n… (more)"
            except OSError:
                continue
        return "\n".join(hits) or "(no matches)"

    def tool_write_file(self, path: str, content: str) -> str:
        p = self._path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {path} ({len(content.splitlines())} lines)"

    def tool_edit_file(self, path: str, old: str, new: str) -> str:
        p = self._path(path)
        text = p.read_text()
        count = text.count(old)
        if count != 1:
            return f"edit refused: the old text occurs {count} times in {path}; it must occur exactly once"
        p.write_text(text.replace(old, new, 1))
        return f"edited {path}"

    def tool_speky(self, argv: List[str]) -> str:
        from . import cli
        if argv and argv[0] == "run":
            return "refused: `speky run` cannot be started from inside the runner"
        argv = [a for a in argv if a != "--json"]
        try:
            return json.dumps(cli.run(argv), default=str)
        except SpekyError as e:
            return json.dumps({"ok": False, "error": e.to_dict()})
        except SystemExit:
            return json.dumps({"ok": False, "error": {"code": "bad_usage", "message": "invalid arguments",
                                                      "fix": f"check `speky {argv[0] if argv else ''} --help`"}})

    def _allowed(self, command: str) -> bool:
        if self.allow_shell:
            return True
        cfg = self.project.config if self.project.dir.is_dir() else {}
        testing = cfg.get("testing") or {}
        allowed = [cfg.get("verify_command"), testing.get("coverage_command"), testing.get("e2e_command")]
        if any(c and command.strip().startswith(c) for c in allowed):
            return True
        try:
            words = shlex.split(command)
        except ValueError:
            return False
        if any(ch in command for ch in (";", "&&", "||", "|", ">", "<", "`", "$(")):
            return False
        return words[:2] in (["git", "status"], ["git", "diff"], ["git", "log"], ["git", "show"]) or \
            (words and words[0] in ("pytest", "ls", "cat"))

    def tool_run(self, command: str) -> str:
        if not self._allowed(command):
            return ("refused: only the project's test commands and read-only git are allowed "
                    "(the user can allow more with `speky run --allow-shell`)")
        proc = subprocess.run(command, shell=True, cwd=self.root, capture_output=True, text=True, timeout=1800)
        out = (proc.stdout + proc.stderr).strip()
        return f"exit {proc.returncode}\n{out[-MAX_OBSERVATION:]}"

    def tool_skill(self, name: str) -> str:
        path = harness.SKILLS_DIR / name / "SKILL.md"
        if not path.exists():
            return f"no skill {name}; skills: {', '.join(harness.skill_names())}"
        return path.read_text().split("---", 2)[-1].strip()

    def tool_ask_user(self, question: str, recommended: str = "") -> str:
        if not self.interactive:
            return ("no user is available: make an informed guess, record it with "
                    "`speky decide \"...\" --type assumption`, and continue")
        prompt = f"\n❓ {question}" + (f"\n   (recommended: {recommended})" if recommended else "") + "\n> "
        answer = input(prompt).strip()
        return answer or (recommended and f"(accepted the recommendation) {recommended}") or "(no answer)"

    # ------------------------------------------------------------------ loop
    def parse(self, text: str) -> dict:
        text = (text or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
        return {}

    def run(self, goal: str) -> dict:
        system = self.system_prompt(goal)
        transcript = [f"# Task from the user\n{goal}\n"]
        for step in range(1, self.max_steps + 1):
            prompt = "\n".join(transcript)
            if len(prompt) > MAX_TRANSCRIPT:  # keep the task and the latest turns
                keep = transcript[:1] + ["(earlier steps trimmed; re-read files if you need them)"] + transcript[-30:]
                transcript, prompt = keep, "\n".join(keep)
            reply = self.complete(prompt + "\n\nYour next tool call (one JSON object):", system)
            call = self.parse(reply)
            tool = call.get("tool")
            args = call.get("args") or {}
            if tool == "finish":
                summary = args.get("summary", "")
                self.log(f"✅ finished after {step - 1} tool call(s)")
                return {"finished": True, "summary": summary, "steps": self.steps}
            handler = getattr(self, f"tool_{tool}", None) if tool else None
            if not handler:
                observation = ("Your reply was not one JSON tool call. Answer with exactly one JSON object "
                               "from the tool list.")
            else:
                try:
                    observation = str(handler(**args))
                except TypeError as e:
                    observation = f"bad arguments for {tool}: {e}"
                except SpekyError as e:
                    observation = f"refused: {e.message}"
                except Exception as e:  # report, don't crash the loop
                    observation = f"error: {type(e).__name__}: {e}"
            self.log(f"[{step}] {tool or '?'} {json.dumps(args)[:120]}" + (f" — {call.get('why')}" if call.get("why") else ""))
            self.steps.append({"tool": tool, "args": args, "observation": observation[:500]})
            transcript.append(f"## Step {step}\nYou called: {json.dumps(call)[:2000]}\n"
                              f"Result:\n{observation[:MAX_OBSERVATION]}\n")
        self.log(f"⏹ stopped after {self.max_steps} steps")
        return {"finished": False, "summary": f"stopped after {self.max_steps} steps", "steps": self.steps}


def make_completer(project: Project, model: str = None) -> Callable[[str, str], str]:
    """A completion function over SPEKY's model router."""
    import os
    from speky_llm import LLMRouter
    if model:
        os.environ["SPEKY_MODEL"] = model
    router = LLMRouter(project_root=project.root, log=lambda m: print(m, file=sys.stderr))
    if not router.chain:
        raise SpekyError("no_model", "No model is configured for `speky run`.",
                         "Set one: `speky config model <provider/model>` (e.g. claude-code/sonnet uses your "
                         "Claude subscription), or export an API key such as ANTHROPIC_API_KEY.")

    from speky_llm import LLMError

    def complete(prompt: str, system: str) -> str:
        try:
            return router.complete(prompt, system, max_tokens=4096, temperature=0, expect_json=True)
        except LLMError as e:
            raise SpekyError("model_error", f"The model call failed: {e}",
                             "Check `speky config providers` and your API key or `claude` login.")

    return complete
