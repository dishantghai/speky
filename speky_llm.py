"""
SPEKY LLM router — one interface over many AI providers.

Models are addressed LiteLLM-style as "provider/model":

    anthropic/claude-sonnet-4-5
    openrouter/moonshotai/kimi-k2
    nebius/deepseek-ai/DeepSeek-V3-0324
    opencode-go/glm-5.2
    claude-code/sonnet        (your Claude Pro/Max subscription, via the `claude` CLI)
    host                      (no model: the agent running SPEKY answers — see host mode below)

The active model, fallbacks and any extra providers are configured in
~/.speky/models.yaml, with per-project overrides in .speky/models.yaml.
See MODELS.md for the full format.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

GLOBAL_CONFIG = Path.home() / ".speky" / "models.yaml"
PROJECT_CONFIG_NAME = "models.yaml"

# Provider types:
#   openai      — any OpenAI-compatible /chat/completions endpoint
#   anthropic   — Anthropic Messages API (or an Anthropic-compatible base_url)
#   gemini      — Google Gemini via google-genai
#   claude-code — the local `claude` CLI, authenticated with your Claude subscription
#   host        — no LLM call: the prompt is handed to the agent that runs SPEKY (host mode)
BUILTIN_PROVIDERS: Dict[str, dict] = {
    "anthropic":   {"type": "anthropic", "api_key_env": "ANTHROPIC_API_KEY",
                    "default_model": "claude-sonnet-4-20250514"},
    "openai":      {"type": "openai", "api_key_env": "OPENAI_API_KEY",
                    "default_model": "gpt-4o"},
    "gemini":      {"type": "gemini", "api_key_env": "GEMINI_API_KEY",
                    "default_model": "gemini-2.0-flash"},
    "openrouter":  {"type": "openai", "base_url": "https://openrouter.ai/api/v1",
                    "api_key_env": "OPENROUTER_API_KEY",
                    "headers": {"HTTP-Referer": "https://github.com/dishantghai/speky", "X-Title": "SPEKY"}},
    "nebius":      {"type": "openai", "base_url": "https://api.tokenfactory.nebius.com/v1",
                    "api_key_env": "NEBIUS_API_KEY"},
    "opencode-go": {"type": "openai", "base_url": "https://opencode.ai/zen/go/v1",
                    "api_key_env": "OPENCODE_API_KEY"},
    "opencode":    {"type": "openai", "base_url": "https://opencode.ai/zen/v1",
                    "api_key_env": "OPENCODE_API_KEY"},
    "groq":        {"type": "openai", "base_url": "https://api.groq.com/openai/v1",
                    "api_key_env": "GROQ_API_KEY"},
    "together":    {"type": "openai", "base_url": "https://api.together.xyz/v1",
                    "api_key_env": "TOGETHER_API_KEY"},
    "fireworks":   {"type": "openai", "base_url": "https://api.fireworks.ai/inference/v1",
                    "api_key_env": "FIREWORKS_API_KEY"},
    "deepseek":    {"type": "openai", "base_url": "https://api.deepseek.com/v1",
                    "api_key_env": "DEEPSEEK_API_KEY"},
    "mistral":     {"type": "openai", "base_url": "https://api.mistral.ai/v1",
                    "api_key_env": "MISTRAL_API_KEY"},
    "xai":         {"type": "openai", "base_url": "https://api.x.ai/v1",
                    "api_key_env": "XAI_API_KEY"},
    "ollama":      {"type": "openai", "base_url": "http://localhost:11434/v1", "api_key": "ollama"},
    "lmstudio":    {"type": "openai", "base_url": "http://localhost:1234/v1", "api_key": "lmstudio"},
    "claude-code": {"type": "claude-code", "default_model": "sonnet",
                    "models": ["sonnet", "opus", "haiku"]},
    "host":        {"type": "host", "default_model": "agent", "models": ["agent"],
                    "timeout": 1800},
}

# Order used to auto-pick a provider when no model is configured anywhere
AUTO_DETECT_ORDER = ["anthropic", "openai", "gemini", "openrouter", "opencode-go", "nebius"]

# Legacy per-provider model env vars (ANTHROPIC_MODEL etc.), honoured during auto-detect
LEGACY_MODEL_ENV = {"anthropic": "ANTHROPIC_MODEL", "openai": "OPENAI_MODEL", "gemini": "GEMINI_MODEL"}


class LLMError(Exception):
    pass


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    import yaml
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _infer_provider(model: str) -> Optional[str]:
    """Guess the provider for a bare model name (pre-router configs stored these)."""
    m = model.lower()
    if m.startswith("claude-"):
        return "anthropic"
    if m.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-")):
        return "openai"
    if m.startswith("gemini-"):
        return "gemini"
    return None


class LLMRouter:
    """Routes completions to the configured provider/model, with retries and fallbacks."""

    def __init__(self, project_root: Path = None, legacy_model: str = None,
                 legacy_default: str = None, timeout: int = 120,
                 log: Callable[[str], None] = print):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.timeout = timeout
        self.log = log
        self._clients: Dict[str, object] = {}

        global_cfg = _load_yaml(GLOBAL_CONFIG)
        project_cfg = _load_yaml(self.project_root / ".speky" / PROJECT_CONFIG_NAME)

        self.providers: Dict[str, dict] = {k: dict(v) for k, v in BUILTIN_PROVIDERS.items()}
        for cfg in (global_cfg, project_cfg):
            for name, spec in (cfg.get("providers") or {}).items():
                merged = dict(self.providers.get(name, {"type": "openai"}))
                merged.update(spec or {})
                self.providers[name] = merged

        # Precedence: SPEKY_MODEL env > project models.yaml > global models.yaml
        #             > legacy `model:` in .speky/config.yaml > auto-detect from API keys
        explicit_legacy = legacy_model if legacy_model and legacy_model != legacy_default else None
        self.model_ref = (os.environ.get("SPEKY_MODEL") or project_cfg.get("model")
                          or global_cfg.get("model") or explicit_legacy or self._auto_detect())
        self.fallbacks: List[str] = list(project_cfg.get("fallbacks") or global_cfg.get("fallbacks") or [])

    # ------------------------------------------------------------------ resolution
    def _auto_detect(self) -> Optional[str]:
        for name in AUTO_DETECT_ORDER:
            if self.is_available(name):
                p = self.providers[name]
                model = os.environ.get(LEGACY_MODEL_ENV.get(name, ""), "") or p.get("default_model")
                if model:
                    return f"{name}/{model}"
        if shutil.which("claude"):
            return "claude-code/sonnet"
        return None

    def resolve(self, ref: str) -> Tuple[str, str]:
        """Split "provider/model" — the model part may itself contain slashes."""
        if ref in self.providers:  # bare provider name, e.g. "host"
            return ref, self.providers[ref].get("default_model", "")
        if "/" in ref:
            head, rest = ref.split("/", 1)
            if head in self.providers:
                return head, rest
        provider = _infer_provider(ref)
        if provider:
            return provider, ref
        raise LLMError(f"Unknown provider in model '{ref}'. Use provider/model, "
                       f"e.g. openrouter/{ref}. Providers: {', '.join(sorted(self.providers))}")

    @property
    def chain(self) -> List[str]:
        refs = [self.model_ref] + self.fallbacks if self.model_ref else list(self.fallbacks)
        return [r for i, r in enumerate(refs) if r and r not in refs[:i]]

    def api_key(self, name: str) -> Optional[str]:
        p = self.providers[name]
        if p.get("api_key"):
            return os.path.expandvars(str(p["api_key"]))
        if p.get("api_key_env"):
            return os.environ.get(p["api_key_env"])
        return None

    def is_available(self, name: str) -> bool:
        p = self.providers.get(name)
        if not p:
            return False
        if p["type"] == "claude-code":
            return shutil.which(p.get("command", "claude")) is not None
        if p["type"] == "host":
            return True
        return bool(self.api_key(name))

    def status(self, name: str) -> str:
        p = self.providers[name]
        if p["type"] == "claude-code":
            return "ready (claude CLI)" if self.is_available(name) else "claude CLI not found"
        if p["type"] == "host":
            return "ready (calling agent answers)"
        if p.get("api_key") and not p.get("api_key_env"):
            return "no key needed (local)" if "localhost" in p.get("base_url", "") else "ready"
        if self.is_available(name):
            return "ready"
        return f"set {p['api_key_env']}" if p.get("api_key_env") else "no api_key"

    # ------------------------------------------------------------------ clients
    def _client(self, name: str):
        if name in self._clients:
            return self._clients[name]
        p = self.providers[name]
        key = self.api_key(name)
        if p["type"] == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=key or "none", base_url=p.get("base_url"),
                            default_headers=p.get("headers"), timeout=self.timeout)
        elif p["type"] == "anthropic":
            from anthropic import Anthropic
            client = Anthropic(api_key=key, base_url=p.get("base_url"),
                               default_headers=p.get("headers"), timeout=self.timeout)
        elif p["type"] == "gemini":
            from google import genai
            client = genai.Client(api_key=key)
        else:
            client = None
        self._clients[name] = client
        return client

    def anthropic_client(self):
        """(client, model) for the primary model when it is Anthropic-typed, else (None, None)."""
        if not self.model_ref:
            return None, None
        name, model = self.resolve(self.model_ref)
        if self.providers[name]["type"] != "anthropic":
            return None, None
        return self._client(name), model

    # ------------------------------------------------------------------ completion
    def complete(self, prompt: str, system: str, max_tokens: int, temperature: float,
                 stream: bool = False, retries: int = 3, expect_json: bool = False) -> str:
        """Try the primary model, then each fallback; each gets `retries` attempts."""
        if not self.chain:
            raise LLMError("No model configured and no API key found. "
                           "Run `speky config --model` or see MODELS.md.")
        last_error = None
        for i, ref in enumerate(self.chain):
            if i > 0:
                self.log(f"Falling back to {ref}")
            try:
                name, model = self.resolve(ref)
            except LLMError as e:
                last_error = e
                continue
            if not self.is_available(name):
                last_error = LLMError(f"{ref}: provider '{name}' not ready ({self.status(name)})")
                self.log(str(last_error))
                continue
            if self.providers[name]["type"] == "host":
                try:
                    return self._call_host(name, prompt, system, max_tokens, expect_json)
                except LLMError as e:
                    last_error = e
                    self.log(str(e))
                    continue
            for attempt in range(retries):
                try:
                    return self._call(name, model, prompt, system, max_tokens, temperature, stream)
                except Exception as e:
                    last_error = e
                    msg = str(e)
                    if "streaming is required" in msg.lower() and not stream:
                        stream = True
                        continue
                    if attempt < retries - 1:
                        self.log(f"{ref} error (attempt {attempt + 1}): {msg}")
                        time.sleep(2)
        raise LLMError(str(last_error))

    def _call(self, name, model, prompt, system, max_tokens, temperature, stream) -> str:
        ptype = self.providers[name]["type"]
        if ptype == "openai":
            return self._call_openai(name, model, prompt, system, max_tokens, temperature, stream)
        if ptype == "anthropic":
            return self._call_anthropic(name, model, prompt, system, max_tokens, temperature, stream)
        if ptype == "gemini":
            return self._call_gemini(name, model, prompt, system, max_tokens, temperature)
        if ptype == "claude-code":
            return self._call_claude_code(name, model, prompt, system)
        raise LLMError(f"Unknown provider type '{ptype}' for '{name}'")

    def _call_openai(self, name, model, prompt, system, max_tokens, temperature, stream) -> str:
        client = self._client(name)
        params = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": prompt}]}
        for _ in range(3):
            try:
                if stream:
                    parts = []
                    for chunk in client.chat.completions.create(stream=True, **params):
                        if chunk.choices and chunk.choices[0].delta.content:
                            parts.append(chunk.choices[0].delta.content)
                    return "".join(parts)
                response = client.chat.completions.create(**params)
                return response.choices[0].message.content or ""
            except Exception as e:
                # Reasoning models reject max_tokens / temperature — adapt and retry once each
                msg = str(e)
                if "max_completion_tokens" in msg and "max_tokens" in params:
                    params["max_completion_tokens"] = params.pop("max_tokens")
                elif "temperature" in msg and "temperature" in params:
                    params.pop("temperature")
                else:
                    raise
        raise LLMError(f"{name}/{model}: request rejected")

    def _call_anthropic(self, name, model, prompt, system, max_tokens, temperature, stream) -> str:
        client = self._client(name)
        params = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                  "system": system, "messages": [{"role": "user", "content": prompt}]}
        for _ in range(2):
            try:
                if stream:
                    with client.messages.stream(**params) as s:
                        return "".join(s.text_stream)
                response = client.messages.create(**params)
                return "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
            except Exception as e:
                if "temperature" in str(e) and "temperature" in params:
                    params.pop("temperature")
                else:
                    raise
        raise LLMError(f"{name}/{model}: request rejected")

    def _call_gemini(self, name, model, prompt, system, max_tokens, temperature) -> str:
        from google.genai import types
        response = self._client(name).models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system,
                                               max_output_tokens=max_tokens,
                                               temperature=temperature))
        return response.text or ""

    def _call_claude_code(self, name, model, prompt, system) -> str:
        """Run one non-interactive turn through the `claude` CLI on your subscription login.

        max_tokens and temperature are not controllable here. Runs with no tools, no
        settings and no MCP servers, from a temp dir so no project CLAUDE.md is loaded.
        """
        p = self.providers[name]
        cmd = [p.get("command", "claude"), "-p", "--output-format", "json", "--model", model,
               "--tools", "", "--setting-sources", "", "--strict-mcp-config",
               "--no-session-persistence"]
        if system:
            cmd += ["--system-prompt", system]
        env = dict(os.environ)
        # An API key in the env would take priority over the subscription login
        env.pop("ANTHROPIC_API_KEY", None)
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=env,
                                cwd=tempfile.gettempdir(),
                                timeout=int(p.get("timeout", max(self.timeout, 600))))
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise LLMError(f"claude CLI failed (exit {result.returncode}): "
                           f"{(result.stderr or result.stdout).strip()[:500]}")
        if data.get("is_error"):
            raise LLMError(f"claude CLI error: {data.get('result') or data}")
        return data.get("result", "")

    def _call_host(self, name, prompt, system, max_tokens, expect_json) -> str:
        """Host mode: hand the prompt to whoever runs SPEKY (e.g. a Claude Code session)
        and block until they write the answer file. SPEKY then continues in-process, so
        nothing is re-run and no files are created twice."""
        host_dir = self.project_root / ".speky" / HOST_DIR_NAME
        host_dir.mkdir(parents=True, exist_ok=True)
        request_id = next_host_request_id(host_dir)
        prompt_file = host_dir / f"{request_id}.prompt.md"
        answer_file = host_dir / f"{request_id}.answer.md"
        fmt = "JSON only — no prose, no code fences" if expect_json else "Markdown/plain text as the prompt asks"
        prompt_file.write_text(HOST_PROMPT_TEMPLATE.format(
            id=request_id, answer=answer_file, fmt=fmt, max_tokens=max_tokens,
            system=system or "(none)", prompt=prompt))

        timeout = int(self.providers[name].get("timeout", 1800))
        print(f"\n⏸️  SPEKY host request {request_id} — waiting for the agent to answer "
              f"(up to {timeout // 60} min).\n"
              f"   Prompt:  {prompt_file}\n"
              f"   Answer:  speky host answer {request_id} --file <file>   "
              f"(or write {answer_file})\n", flush=True)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if answer_file.exists():
                time.sleep(0.5)  # let a non-atomic writer finish
                answer = answer_file.read_text().strip()
                done = host_dir / "done"
                done.mkdir(exist_ok=True)
                prompt_file.rename(done / prompt_file.name)
                answer_file.rename(done / answer_file.name)
                print(f"▶️  Got answer for host request {request_id}; continuing.", flush=True)
                return answer
            time.sleep(1)
        raise LLMError(f"host request {request_id}: no answer after {timeout}s ({answer_file})")

    # ------------------------------------------------------------------ discovery
    def list_models(self, name: str) -> List[str]:
        """Models the provider advertises (config `models:` list wins). Empty if unknown."""
        p = self.providers[name]
        if p.get("models"):
            return list(p["models"])
        try:
            if p["type"] == "openai":
                return sorted(m.id for m in self._client(name).models.list())
            if p["type"] == "anthropic":
                return [m.id for m in self._client(name).models.list(limit=100)]
            if p["type"] == "gemini":
                return [m.name.split("/", 1)[-1] for m in self._client(name).models.list()]
        except Exception as e:
            self.log(f"Could not list models for {name}: {e}")
        return []


# ---------------------------------------------------------------------- config file
STARTER_CONFIG = """\
# SPEKY model configuration (global). A project can override any key in .speky/models.yaml.
# Model refs are "provider/model". Env var SPEKY_MODEL overrides `model` for one run.

model: {model}

# Tried in order if the primary model fails.
# fallbacks:
#   - opencode-go/kimi-k2.6
#   - claude-code/sonnet

# Built-in providers: anthropic, openai, gemini, openrouter, nebius, opencode-go, opencode,
# groq, together, fireworks, deepseek, mistral, xai, ollama, lmstudio, claude-code, host.
# Add your own, or override a built-in (e.g. its base_url), here:
# providers:
#   my-vllm:
#     type: openai                 # openai | anthropic | gemini | claude-code
#     base_url: http://gpu-box:8000/v1
#     api_key_env: MY_VLLM_KEY     # or api_key: literal / ${{ENV_VAR}}
#     models: [qwen3-coder-30b]    # optional; otherwise fetched from /models
#   opencode-go-anthropic:         # OpenCode Go models served on the Anthropic API (e.g. MiniMax)
#     type: anthropic
#     base_url: https://opencode.ai/zen/go
#     api_key_env: OPENCODE_API_KEY
"""


def save_model(model_ref: str, path: Path = GLOBAL_CONFIG):
    """Set the top-level `model:` in a models.yaml, keeping the rest of the file and its comments."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(STARTER_CONFIG.format(model=model_ref))
        return
    lines = path.read_text().splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("model:"):
            lines[i] = f"model: {model_ref}\n"
            break
    else:
        lines.insert(0, f"model: {model_ref}\n")
    path.write_text("".join(lines))


# ---------------------------------------------------------------------- host mode
HOST_DIR_NAME = "host"

HOST_PROMPT_TEMPLATE = """\
<!-- SPEKY host request {id} -->
# SPEKY host request {id}

SPEKY is running in host mode: instead of calling an LLM it asks you, the agent
running it, to produce this answer. Act as the model described under "System"
and answer the "Prompt" below using your own knowledge of the project.

- Write ONLY the answer — it is used verbatim. Format: {fmt}.
- Aim for at most ~{max_tokens} tokens.
- Deliver it with:  speky host answer {id} --file <your-file>
  (or write it to {answer})
SPEKY is blocked until the answer arrives, then continues on its own.

## System

{system}

## Prompt

{prompt}
"""


def next_host_request_id(host_dir: Path) -> str:
    used = [int(f.name[:3]) for f in list(host_dir.glob("*.md")) + list((host_dir / "done").glob("*.md"))
            if f.name[:3].isdigit()]
    return f"{max(used, default=0) + 1:03d}"


def pending_host_requests(project_root: Path) -> List[Path]:
    """Prompt files that have no answer yet, oldest first."""
    host_dir = Path(project_root) / ".speky" / HOST_DIR_NAME
    if not host_dir.exists():
        return []
    return sorted(f for f in host_dir.glob("*.prompt.md")
                  if not (host_dir / f.name.replace(".prompt.md", ".answer.md")).exists())


def write_host_answer(project_root: Path, request_id: str, text: str) -> Path:
    """Atomically deliver an answer so a waiting SPEKY never reads half a file."""
    host_dir = Path(project_root) / ".speky" / HOST_DIR_NAME
    request_id = f"{int(request_id):03d}" if request_id.isdigit() else request_id
    if not (host_dir / f"{request_id}.prompt.md").exists():
        raise LLMError(f"No pending host request {request_id} in {host_dir}")
    tmp = host_dir / f"{request_id}.answer.md.tmp"
    tmp.write_text(text)
    final = host_dir / f"{request_id}.answer.md"
    tmp.replace(final)
    return final
