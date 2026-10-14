# TraceAI Observability Setup for SPEKY

This document explains how to set up and use TraceAI observability in the SPEKY project to monitor AI provider calls, latency, cost, and token usage.

## Overview

TraceAI integration allows you to:
- Monitor all LLM calls in the Future AGI Observe dashboard
- Track latency, cost, and token usage for each AI request
- Debug issues by tracing specific requests
- Analyze performance patterns across your AI-assisted development workflow

## Installation

### 1. Install Required Packages

The required packages are already added to `requirements.txt`:

```bash
pip install -r requirements.txt
```

Or install them individually:

```bash
pip install "fi-instrumentation-otel[grpc]" traceai-openai traceai-anthropic
```

### 2. Get Your API Keys

1. Visit the [Future AGI Dashboard](https://app.futureagi.com/dashboard/keys)
2. Create a new project or select an existing one
3. Copy your `FI_API_KEY` and `FI_SECRET_KEY`

### 3. Configure Environment Variables

Edit your `.env` file and add your TraceAI credentials:

```bash
# TraceAI Observability (Future AGI Observe)
FI_API_KEY="your-api-key-here"
FI_SECRET_KEY="your-secret-key-here"
```

**Important**: Uncomment these lines and replace with your actual keys.

## How It Works

### Automatic Initialization

TraceAI is automatically initialized when you run any SPEKY command:

1. The `.env` file is loaded via `_load_env()`
2. `traceai_config.py` checks for `FI_API_KEY` and `FI_SECRET_KEY`
3. If keys are present, TraceAI registers the project and instruments AI providers
4. All subsequent AI calls are automatically traced

### What Gets Traced

Currently instrumented:
- ✅ **OpenAI** and every OpenAI-compatible provider (OpenRouter, Nebius, OpenCode Go, Groq, Ollama, ...) — `traceai-openai`
- ✅ **Anthropic** calls — `traceai-anthropic`
- ✅ **Google Gemini** calls — via `traceai-openai` (SPEKY reaches Gemini through its OpenAI-compatible endpoint)
- ❌ `claude-code/*` (runs the `claude` CLI) and `host` mode (no LLM call) are not traced

### Silent Fallback

If TraceAI is not configured or packages are missing:
- SPEKY continues to work normally
- No error messages are shown (silent fallback)
- You can add the configuration later without any code changes

## Viewing Traces

Once configured, view your traces at:
- **Dashboard**: https://app.futureagi.com/dashboard/projects/observe
- **Project Name**: `SPEKY`

You'll see:
- Individual AI requests with full context
- Input/output content for each call
- Token usage and costs
- Latency metrics
- Request timestamps

## Verification

To verify TraceAI is working:

1. Ensure your `.env` has valid `FI_API_KEY` and `FI_SECRET_KEY`
2. Run any SPEKY command that uses AI (e.g., `speky spec "Test feature"`)
3. Look for the message: `✅ TraceAI observability enabled for project: SPEKY`
4. Check the Future AGI dashboard for new traces

## Troubleshooting

### No traces appearing in dashboard

**Check 1**: Verify environment variables are set
```bash
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('FI_API_KEY:', os.getenv('FI_API_KEY')[:10] if os.getenv('FI_API_KEY') else 'Not set')"
```

**Check 2**: Verify packages are installed
```bash
pip list | grep -E "fi-instrumentation|traceai"
```

**Check 3**: Look for initialization message when running SPEKY
```bash
speky status  # Should show "✅ TraceAI observability enabled" if configured
```

### Import errors

If you see import errors related to TraceAI:
```bash
pip install --upgrade "fi-instrumentation-otel[grpc]" traceai-openai traceai-anthropic
```

### Wrong API keys

If you see authentication errors:
1. Verify keys at https://app.futureagi.com/dashboard/keys
2. Ensure no extra spaces or quotes in `.env` file
3. Restart your terminal/IDE to reload environment variables

## Architecture

### Files Modified/Created

- **`requirements.txt`**: Added TraceAI packages
- **`traceai_config.py`**: TraceAI initialization and instrumentation logic
- **`speky.py`**: Integrated TraceAI initialization after env loading
- **`.env`**: Added FI_API_KEY and FI_SECRET_KEY configuration

### Code Flow

```
speky.py startup
    ↓
_load_env() - Load .env variables
    ↓
initialize_traceai() - Register with Future AGI
    ↓
_instrument_providers() - Instrument AI clients
    ↓
Normal SPEKY execution with automatic tracing
```

## Advanced Configuration

### Custom Project Name

Edit `speky.py` line 65 to change the project name:

```python
initialize_traceai(project_name="SPEKY-Production")
```

### Transport Protocol

The default transport is GRPC. To use HTTP instead, edit `traceai_config.py`:

```python
trace_provider = register(
    project_type=ProjectType.OBSERVE,
    project_name=project_name,
    transport=Transport.HTTP,  # Changed from GRPC
)
```

### Disable TraceAI Temporarily

Simply comment out or remove the `FI_API_KEY` and `FI_SECRET_KEY` from `.env`:

```bash
# FI_API_KEY="your-api-key-here"
# FI_SECRET_KEY="your-secret-key-here"
```

SPEKY will continue to work without tracing.

## Next Steps

After setting up basic observability, explore:

- **[Evals](https://docs.futureagi.com/docs/observe/features/evals)**: Run evaluations on traced spans
- **[Sessions](https://docs.futureagi.com/docs/observe/features/sessions)**: Group related traces
- **[Users](https://docs.futureagi.com/docs/observe/features/users)**: Track per-user metrics
- **[Alerts](https://docs.futureagi.com/docs/observe/features/alerts)**: Set up monitoring alerts

## Support

- **Documentation**: https://docs.futureagi.com/docs/observe/features/quickstart
- **Dashboard**: https://app.futureagi.com/dashboard
- **Issues**: Report TraceAI-specific issues in the SPEKY repository
