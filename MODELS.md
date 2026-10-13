# Models & Providers

SPEKY talks to any LLM provider through `speky_llm.py`. Models are named
LiteLLM-style as **`provider/model`**:

| Example ref | What it uses |
|---|---|
| `anthropic/claude-sonnet-4-5` | Anthropic API (`ANTHROPIC_API_KEY`) |
| `openrouter/moonshotai/kimi-k2` | OpenRouter (`OPENROUTER_API_KEY`) |
| `nebius/deepseek-ai/DeepSeek-V3-0324` | Nebius Token Factory (`NEBIUS_API_KEY`) |
| `opencode-go/glm-5.2` | OpenCode Go subscription (`OPENCODE_API_KEY`) |
| `claude-code/sonnet` | Your Claude Pro/Max subscription, via the local `claude` CLI |
| `ollama/qwen3-coder` | Local Ollama, no key |
| `host` | No model: the agent running SPEKY answers each prompt (see [AUTOMATION.md](AUTOMATION.md#host-mode)) |

Built-in providers: `anthropic`, `openai`, `gemini`, `openrouter`, `nebius`,
`opencode-go`, `opencode`, `groq`, `together`, `fireworks`, `deepseek`,
`mistral`, `xai`, `ollama`, `lmstudio`, `claude-code`, `host`.

## Choosing a model

```bash
speky config --providers                                # which providers have keys set
speky config --model                                    # show current; interactive picker
speky config --model openrouter/moonshotai/kimi-k2      # set directly
speky spec my-feature --llm claude-code/opus            # one-off override
SPEKY_MODEL=claude-code/opus speky spec my-feature      # same, via env
```

The choice is saved to `~/.speky/models.yaml` and applies to every project.

Which model wins, highest first:

1. `SPEKY_MODEL` env var
2. `.speky/models.yaml` in the project
3. `~/.speky/models.yaml`
4. `model:` in `.speky/config.yaml` (older SPEKY versions)
5. Auto-detect from whichever API key is set (Anthropic → OpenAI → Gemini → OpenRouter → OpenCode Go → Nebius → `claude` CLI)

## models.yaml

```yaml
model: openrouter/moonshotai/kimi-k2

# Tried in order if the primary model errors or its provider has no key
fallbacks:
  - opencode-go/kimi-k2.6
  - claude-code/sonnet

providers:
  # Any OpenAI-compatible server
  my-vllm:
    type: openai                  # openai | anthropic | gemini | claude-code
    base_url: http://gpu-box:8000/v1
    api_key_env: MY_VLLM_KEY      # or api_key: literal, or ${ENV_VAR}
    models: [qwen3-coder-30b]     # optional; otherwise listed from /models

  # Override a built-in, e.g. point nebius somewhere else
  nebius:
    base_url: https://api.studio.nebius.com/v1

  # OpenCode Go models served on the Anthropic API (e.g. MiniMax)
  opencode-go-anthropic:
    type: anthropic
    base_url: https://opencode.ai/zen/go
    api_key_env: OPENCODE_API_KEY
```

Keys go in your shell profile or the project `.env`, as before.

## Using your Claude subscription (`claude-code/*`)

Anthropic does not allow Pro/Max subscription logins to be used directly by
third-party apps. `claude-code/*` therefore runs the official `claude` CLI
(`claude -p`) as a subprocess, on the login you already have. Notes:

- Models are the CLI aliases: `sonnet`, `opus`, `haiku`.
- It runs with no tools, no settings and no MCP servers, and
  `ANTHROPIC_API_KEY` is removed from its environment so your subscription
  is used, not the API.
- `max_tokens` and `temperature` can't be set. Calls are slower than the API
  and count against your plan's usage limits.
- These calls are not traced by TraceAI.
- Running the CLI yourself for your own work is fine. Don't use this to
  serve other users from your subscription.

## Observability

When `FI_API_KEY` and `FI_SECRET_KEY` are set, TraceAI traces every call made
through the OpenAI SDK (OpenAI and all OpenAI-compatible providers above), the
Anthropic SDK and google-genai. See [TRACEAI_SETUP.md](TRACEAI_SETUP.md).
