"""
TraceAI Observability Configuration for SPEKY
Instruments AI provider calls for monitoring in Future AGI Observe dashboard
"""

import os
from typing import Optional

TRACEAI_ENABLED = False
trace_provider = None

def initialize_traceai(project_name: str = "SPEKY") -> Optional[object]:
    """
    Initialize TraceAI observability for the SPEKY project.
    
    Args:
        project_name: Name of the project in Future AGI Observe dashboard
        
    Returns:
        trace_provider object if successful, None otherwise
    """
    global TRACEAI_ENABLED, trace_provider
    
    fi_api_key = os.environ.get("FI_API_KEY")
    fi_secret_key = os.environ.get("FI_SECRET_KEY")
    
    if not fi_api_key or not fi_secret_key:
        return None
    
    try:
        from fi_instrumentation import register, Transport
        from fi_instrumentation.fi_types import ProjectType
        
        trace_provider = register(
            project_type=ProjectType.OBSERVE,
            project_name=project_name,
            transport=Transport.GRPC,
        )
        
        _instrument_providers(trace_provider)
        
        TRACEAI_ENABLED = True
        print(f"✅ TraceAI observability enabled for project: {project_name}")
        return trace_provider
        
    except ImportError as e:
        print(f"⚠️  TraceAI packages not installed: {e}")
        print('   Run: pip install "fi-instrumentation-otel[grpc]" traceai-openai traceai-anthropic traceai-google-genai')
        return None
    except Exception as e:
        print(f"⚠️  Failed to initialize TraceAI: {e}")
        return None


def _instrument_providers(tracer_provider):
    """Instrument available AI provider SDKs with TraceAI.

    The OpenAI instrumentor also covers every OpenAI-compatible provider in
    speky_llm (OpenRouter, Nebius, OpenCode Go, Groq, ...). claude-code/* models
    run through the `claude` CLI and are not traced.
    """
    instrumentors = [
        ("traceai_openai", "OpenAIInstrumentor", "OpenAI"),
        ("traceai_anthropic", "AnthropicInstrumentor", "Anthropic"),
        ("traceai_google_genai", "GoogleGenAIInstrumentor", "Google GenAI"),
    ]
    for module_name, class_name, label in instrumentors:
        try:
            module = __import__(module_name)
            getattr(module, class_name)().instrument(tracer_provider=tracer_provider)
        except ImportError:
            pass
        except Exception as e:
            print(f"⚠️  Failed to instrument {label}: {e}")


def is_traceai_enabled() -> bool:
    """Check if TraceAI is currently enabled"""
    return TRACEAI_ENABLED
