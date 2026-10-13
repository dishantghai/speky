#!/usr/bin/env python3
"""
SPEKY v2: AI-Assisted Scalable Engineering Framework
Orchestration layer for AI-assisted software development

Commands:
    speky init "Product idea"           - Initialize new project
    speky spec "Feature name"           - Create feature specification  
    speky plan <spec-id>                 - Generate implementation plan
    speky story --type <type> "Title"   - Create story (feature/bug/enhancement)
    speky implement <id>                 - Hand off to IDE (Windsurf/Cursor/Claude Code)
    speky status                         - Show all specs and stories
    speky sync                           - Update codebase context
    speky review                         - Check spec-code drift

Design Principles:
    - Tech/IDE/Scale agnostic
    - Thin orchestration layer (not a replacement for AI coding tools)
    - MCP-ready for context management
    - Supports ongoing development (not just initial scaffolding)
"""

import json
import os
import re
import signal
import subprocess
import sys
import difflib
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable
import argparse

# Handle Ctrl+C gracefully
def _signal_handler(sig, frame):
    """Handle interrupt signal gracefully"""
    print("\n\n🛑 Interrupted by user. Exiting gracefully...")
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)

# Load .env file if it exists
def _load_env():
    """Load environment variables from .env file"""
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    # Remove quotes if present
                    value = value.strip('"').strip("'")
                    if key not in os.environ:
                        os.environ[key] = value

_load_env()

# Initialize TraceAI observability (optional)
try:
    from traceai_config import initialize_traceai
    initialize_traceai(project_name="SPEKY")
except ImportError:
    pass
except Exception as e:
    print(f"⚠️  TraceAI disabled: {e}")

# Multi-provider model routing (provider/model refs, configured in ~/.speky/models.yaml)
from speky_llm import (LLMRouter, LLMError, GLOBAL_CONFIG, save_model,
                       pending_host_requests, write_host_answer)

# =============================================================================
# CONFIGURATION
# =============================================================================

HOST_AGENT_GUIDE = """\
SPEKY host mode — instructions for the AI agent running SPEKY
==============================================================
You (the agent) are SPEKY's model: SPEKY makes no LLM calls of its own, it asks you.

1. Start the command in the background, in host mode and without prompts:
       speky <command> ... --host -y [--answer "question=value" ...]
   (Claude Code: run it with run_in_background. It must keep running while you answer.)
2. Watch its output. When it prints "⏸️  SPEKY host request NNN", read the prompt:
       speky host show NNN
3. Write the answer exactly as the prompt asks (JSON only when it says JSON), using
   your knowledge of this codebase, to a file and deliver it:
       speky host answer NNN --file /path/to/answer.md
4. SPEKY continues by itself; repeat 2-3 for each new request until the command exits.

In an existing repository, initialize with:
       speky init --from-project --host -y
SPEKY reads the README/docs/manifests itself; when it asks you to answer its
clarifying questions, use what you can see in the code, and leave unknowns blank.

Rules
- The answer is used verbatim — no preamble, no "Here is...".
- Do not edit files under .speky/ yourself while SPEKY is running; let SPEKY write them.
- If SPEKY exits with code 4 it needs an answer to a question: re-run the same command
  adding the --answer it printed.
- `speky host status` lists waiting requests. Requests time out after 30 minutes.
"""

# Exit codes (also listed in `speky --help`)
EXIT_NEEDS_INPUT = 4   # a question had no --answer and no usable default (non-interactive mode)


DEFAULT_CONFIG = {
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 4096,
    "max_tokens_spec_edit": 32768,  # Higher limit for spec file edits to prevent truncation (increased from 16384)
    "temperature": 0.7,
    "api_timeout": 120,
    "ide": "windsurf",  # Primary IDE (legacy, for backward compatibility)
    "enabled_ides": ["windsurf"],  # List of IDEs to generate rules for (windsurf, cursor, claude-code, vscode, antigravity)
    "mcp_enabled": False,  # Enable when MCP servers are configured
}

SPEKY_DIR = ".speky"
CONTEXT_DIR = "context"
SPECS_DIR = "specs"
STORIES_DIR = "stories"
PHASES_DIR = "phases"
EPICS_DIR = "epics"
DESIGN_DIR = "design"

# Supported design file extensions
DESIGN_IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".svg"]
DESIGN_DOC_EXTENSIONS = [".md", ".txt", ".json"]


# =============================================================================
# ENUMS
# =============================================================================

class StoryType(Enum):
    FEATURE = "feature"
    BUG = "bug"
    ENHANCEMENT = "enhancement"
    TECH_DEBT = "tech_debt"
    SPIKE = "spike"


class ItemStatus(Enum):
    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    COMPLETED = "completed"


class PhaseStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    TESTING = "testing"
    COMPLETE = "complete"
    BLOCKED = "blocked"


class DesignType(Enum):
    """Types of design files"""
    HIFI = "hifi"           # High-fidelity designs (pixel-perfect required)
    LOFI = "lofi"           # Low-fidelity wireframes (guidance only)
    ICON = "icon"           # Icon assets
    SYSTEM = "system"       # Design system documents


class DesignSourceMode(Enum):
    """How design system was created"""
    DOCUMENT = "document"   # From design system document
    IMAGES = "images"       # Generated from Hi-Fi images
    HYBRID = "hybrid"       # Both document and images


class DesignConflictType(Enum):
    """Types of design conflicts"""
    COLOR = "color"
    TYPOGRAPHY = "typography"
    SPACING = "spacing"
    RADIUS = "radius"
    SHADOW = "shadow"
    COMPONENT = "component"
    LAYOUT = "layout"


# =============================================================================
# VALIDATION SESSION (tracks context across validation)
# =============================================================================

class ValidationSession:
    """Tracks decisions and context across a validation session.
    
    This enables context-aware validation where:
    - User corrections apply to subsequent gaps (e.g., "bookmark = spaces")
    - Referenced specs are loaded and considered
    - Tech decisions are respected throughout
    """
    
    def __init__(self):
        self.terminology_mappings: Dict[str, str] = {}  # e.g., {"bookmark": "spaces"}
        self.referenced_specs: Dict[str, str] = {}  # spec_id -> brief content
        self.decisions_made: List[dict] = []
        self.project_context: dict = {}
        self.related_specs: List[dict] = []  # Auto-detected related specs
    
    def add_terminology_mapping(self, term: str, maps_to: str):
        """Track when user says 'X is actually Y'"""
        self.terminology_mappings[term.lower()] = maps_to.lower()
    
    def add_referenced_spec(self, spec_id: str, content: str):
        """Add a spec that was referenced by user"""
        self.referenced_specs[spec_id] = content
    
    def add_decision(self, gap: str, action: str, notes: str = ""):
        """Track a decision made during validation"""
        self.decisions_made.append({
            "gap": gap,
            "action": action,
            "notes": notes,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_context_for_ai(self) -> str:
        """Get accumulated context for AI prompts"""
        context_parts = []
        
        if self.terminology_mappings:
            mappings = [f"'{k}' = '{v}'" for k, v in self.terminology_mappings.items()]
            context_parts.append(f"TERMINOLOGY MAPPINGS (from user):\n{', '.join(mappings)}")
        
        if self.referenced_specs:
            specs_summary = []
            for spec_id, content in self.referenced_specs.items():
                # Truncate content for context
                brief = content[:500] + "..." if len(content) > 500 else content
                specs_summary.append(f"Spec {spec_id}:\n{brief}")
            context_parts.append(f"REFERENCED SPECS:\n" + "\n\n".join(specs_summary))
        
        if self.decisions_made:
            recent = self.decisions_made[-5:]  # Last 5 decisions
            decisions_str = "\n".join([f"- {d['gap'][:50]}... → {d['action']}" for d in recent])
            context_parts.append(f"RECENT DECISIONS:\n{decisions_str}")
        
        return "\n\n".join(context_parts) if context_parts else ""
    
    def to_dict(self) -> dict:
        """Serialize session to dict for JSON storage
        
        Enables persistence of user decisions and context across validation sessions.
        """
        return {
            "terminology_mappings": self.terminology_mappings,
            "referenced_specs": self.referenced_specs,
            "decisions_made": self.decisions_made,
            "related_specs": self.related_specs,
            # project_context is not serialized - it's reconstructed on load
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ValidationSession':
        """Deserialize session from dict
        
        Restores user decisions and context from previous validation sessions.
        """
        session = cls()
        session.terminology_mappings = data.get("terminology_mappings", {})
        session.referenced_specs = data.get("referenced_specs", {})
        session.decisions_made = data.get("decisions_made", [])
        session.related_specs = data.get("related_specs", [])
        return session


# =============================================================================
# SHARED CONTEXT MEMORY (JSON-based)
# =============================================================================

class ContextMemory:
    """Manages shared context for SPEKY - works within any project directory"""

    def __init__(self, project_root: Path = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.speky_dir = self.project_root / SPEKY_DIR
        self.context_dir = self.speky_dir / CONTEXT_DIR
        self.specs_dir = self.speky_dir / SPECS_DIR
        self.stories_dir = self.speky_dir / STORIES_DIR
        self.phases_dir = self.speky_dir / PHASES_DIR
        self.epics_dir = self.speky_dir / EPICS_DIR
        self.config_file = self.speky_dir / "config.yaml"
        self.context_file = self.context_dir / "context.json"
        
    def is_initialized(self) -> bool:
        """Check if SPEKY is initialized in this directory"""
        return self.speky_dir.exists() and self.context_file.exists()
    
    def initialize(self):
        """Create SPEKY directory structure"""
        self.speky_dir.mkdir(exist_ok=True)
        self.context_dir.mkdir(exist_ok=True)
        self.specs_dir.mkdir(exist_ok=True)
        self.stories_dir.mkdir(exist_ok=True)
        self.phases_dir.mkdir(exist_ok=True)
        self.epics_dir.mkdir(exist_ok=True)
        
        if not self.context_file.exists():
            self._save_json(self.context_file, self._empty_context())
        
        if not self.config_file.exists():
            self._save_config(DEFAULT_CONFIG)

    def _load(self) -> dict:
        """Load context from file or initialize empty"""
        if self.context_file.exists():
            return self._load_json(self.context_file)
        return self._empty_context()

    def _empty_context(self) -> dict:
        """Initialize empty context structure - simplified for v2"""
        return {
            "product": {
                "name": "",
                "description": "",
                "target_users": "",
                "problem": "",
                "scale": "mvp",  # mvp, growth, enterprise
                "domain": "",    # e.g., "cooking", "finance", "education"
            },
            "architecture": {
                "type": "",      # monolith, microservices, serverless
                "tech_stack": {},
                "decisions": [],
            },
            "specs": [],         # List of spec IDs
            "stories": [],       # List of story IDs  
            "codebase": {
                "structure": "",
                "last_synced": None,
            },
            "decisions": [],     # Decision log
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
    
    def _load_json(self, path: Path) -> dict:
        """Load JSON file"""
        with open(path, 'r') as f:
            return json.load(f)
    
    def _save_json(self, path: Path, data: dict):
        """Save JSON file"""
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _save_config(self, config: dict):
        """Save config as YAML-like format (simple key: value)"""
        lines = ["# SPEKY Configuration\n"]
        for key, value in config.items():
            lines.append(f"{key}: {value}\n")
        with open(self.config_file, 'w') as f:
            f.writelines(lines)
    
    def load_config(self) -> dict:
        """Load config file"""
        if not self.config_file.exists():
            return DEFAULT_CONFIG.copy()
        
        config = DEFAULT_CONFIG.copy()
        with open(self.config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    # Type conversion
                    if value.lower() in ('true', 'false'):
                        value = value.lower() == 'true'
                    elif value.isdigit():
                        value = int(value)
                    else:
                        # Try to convert to float (for temperature, etc.)
                        try:
                            value = float(value)
                        except ValueError:
                            # Keep as string if not a number
                            pass
                    config[key] = value
        return config

    @property
    def data(self) -> dict:
        """Load and return context data"""
        return self._load()
    
    def save(self, data: dict):
        """Save context data"""
        data["updated_at"] = datetime.now().isoformat()
        self._save_json(self.context_file, data)

    def update(self, key: str, value: Any):
        """Update context key using dot notation"""
        data = self.data
        keys = key.split('.')
        current = data
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value
        self.save(data)

    def get(self, key: str, default=None) -> Any:
        """Get context value using dot notation"""
        data = self.data
        keys = key.split('.')
        current = data
        for k in keys:
            if isinstance(current, dict):
                current = current.get(k)
            else:
                return default
        return current if current is not None else default
    
    def get_product_context(self) -> str:
        """Get formatted product context for prompts"""
        data = self.data
        product = data.get("product", {})
        arch = data.get("architecture", {})
        
        # Use architecture.tech_stack with actual keys (not frontend/backend/etc)
        tech_stack = arch.get("tech_stack", {})
        
        # Format tech stack from actual keys
        tech_stack_str = ""
        if tech_stack:
            tech_items = []
            for key, value in tech_stack.items():
                # Capitalize key for display
                display_key = key.replace('_', ' ').title()
                tech_items.append(f"- **{display_key}**: {value}")
            tech_stack_str = "\n".join(tech_items)
        
        # If no tech stack in JSON, try to extract summary from tech_decisions.md
        if not tech_stack_str:
            tech_decisions_file = self.context_dir / "tech_decisions.md"
            if tech_decisions_file.exists():
                tech_stack_str = "See `.speky/context/tech_decisions.md` for full stack"
            else:
                tech_stack_str = "Not configured"
        
        # Get key decisions from context
        decisions = data.get("decisions", arch.get("decisions", []))
        decisions_str = ""
        if decisions:
            decisions_str = "\n## Key Decisions\n"
            for dec in decisions[:5]:  # Limit to 5 most important
                decisions_str += f"- {dec}\n"
        
        context = f"""## Product Context
**Name**: {product.get('name', 'Not set')}
**Description**: {product.get('description', 'Not set')}
**Target Users**: {product.get('target_users', 'Not set')}
**Scale**: {product.get('scale', 'mvp')}

## Tech Stack
{tech_stack_str}

## Architecture
**Type**: {arch.get('type', 'monolith')}
"""
        
        if decisions_str:
            context += decisions_str
        
        # Add codebase navigation index from codebase.md
        codebase_index = self._get_codebase_navigation_index()
        if codebase_index:
            context += codebase_index
        
        # Add important architecture decisions from tech_decisions.md
        arch_decisions = self._get_architecture_decisions()
        if arch_decisions:
            context += arch_decisions
        
        return context
    
    def _get_codebase_navigation_index(self) -> str:
        """Extract Key Directories, Key Files, and Patterns from codebase.md
        
        This provides an always-available index for AI agents to navigate the codebase.
        """
        codebase_file = self.context_dir / "codebase.md"
        if not codebase_file.exists():
            return ""
        
        content = codebase_file.read_text()
        
        # Extract specific sections
        sections_to_extract = ["Key Directories", "Key Files", "Patterns Observed"]
        extracted = []
        
        for section_name in sections_to_extract:
            section_content = self._extract_markdown_section(content, section_name)
            if section_content:
                extracted.append(f"## {section_name}\n{section_content}")
        
        if not extracted:
            return ""
        
        return "\n\n" + "\n\n".join(extracted) + "\n"
    
    def _get_architecture_decisions(self) -> str:
        """Extract Important Architecture Decisions from tech_decisions.md
        
        These decisions should always be in IDE context so implementations conform to them.
        """
        tech_decisions_file = self.context_dir / "tech_decisions.md"
        if not tech_decisions_file.exists():
            return ""
        
        content = tech_decisions_file.read_text()
        
        # Extract the "Important Architecture Decisions" section
        arch_section = self._extract_markdown_section(content, "Important Architecture Decisions")
        if not arch_section:
            return ""
        
        return f"""
## Important Architecture Decisions

> These are authoritative architecture patterns. All implementations MUST follow these.
> Full details in `.speky/context/tech_decisions.md`

{arch_section}
"""
    
    def _extract_markdown_section(self, content: str, section_name: str) -> str:
        """Extract content of a markdown section by header name
        
        Finds ## Section Name and returns content until next ## or end of file.
        """
        import re
        
        # Match ## Section Name (case insensitive)
        pattern = rf'^##\s+{re.escape(section_name)}\s*$'
        lines = content.split('\n')
        
        in_section = False
        section_lines = []
        
        for line in lines:
            if re.match(pattern, line, re.IGNORECASE):
                in_section = True
                continue
            elif in_section:
                # Check if we hit another section header
                if re.match(r'^##\s+', line):
                    break
                section_lines.append(line)
        
        # Clean up - remove leading/trailing empty lines
        result = '\n'.join(section_lines).strip()
        return result


# =============================================================================
# CONSOLE OUTPUT
# =============================================================================

class Console:
    """Clean console output utilities"""
    
    @staticmethod
    def header(title: str):
        """Print a header"""
        width = 70
        print(f"\n{'='*width}")
        print(f"  {title}")
        print(f"{'='*width}\n")
    
    @staticmethod
    def section(title: str, description: str = ""):
        """Print a section header"""
        print(f"\n{'─'*50}")
        print(f"▶️  {title}")
        if description:
            print(f"   {description}")
        print(f"{'─'*50}\n")
    
    @staticmethod
    def log(message: str, prefix: str = "ℹ️ "):
        print(f"{prefix} {message}")
    
    @staticmethod
    def success(message: str):
        print(f"✅ {message}")
    
    @staticmethod
    def error(message: str):
        print(f"❌ {message}")
    
    @staticmethod
    def warning(message: str):
        print(f"⚠️  {message}")
    
    # ---- Non-interactive answering ------------------------------------------
    # Set from the global --yes / --non-interactive / --answer / --answers flags
    # (or automatically when stdin is not a terminal). Every question SPEKY asks
    # goes through prompt/confirm/choose/text_block/pause below, so scripts and
    # AI agents can drive any command without a keyboard.
    non_interactive = False
    assume_yes = False
    answers: List[tuple] = []          # (question substring, answer), in order given
    _asked: Dict[str, int] = {}

    @classmethod
    def configure(cls, non_interactive: bool = False, assume_yes: bool = False,
                  answers: List[tuple] = None):
        cls.non_interactive = non_interactive or assume_yes
        cls.assume_yes = assume_yes
        cls.answers = list(answers or [])

    @classmethod
    def _preset_answer(cls, message: str) -> Optional[str]:
        """First --answer whose key appears in the question (case-insensitive).
        A key given several times is used once per entry, in order."""
        question = " ".join(message.split()).lower()
        for i, (key, value) in enumerate(cls.answers):
            if key.lower() in question:
                if sum(1 for k, _ in cls.answers if k == key) > 1:
                    cls.answers.pop(i)
                return value
        return None

    @classmethod
    def has_answer(cls, message: str) -> bool:
        """True if some --answer would match this question (without using it up)."""
        question = " ".join(message.split()).lower()
        return any(key.lower() in question for key, _ in cls.answers)

    @classmethod
    def _unattended(cls, message: str, value: str, how: str) -> str:
        """Log an answer chosen without a human, and stop if a question keeps repeating."""
        question = " ".join(message.split())
        cls._asked[question] = cls._asked.get(question, 0) + 1
        # Distinct questions can share a prompt ("Your answer"), so only a long run means a loop
        if cls._asked[question] > 20:
            cls.needs_input(question, "SPEKY keeps asking this question; the automatic answer is not accepted.")
        print(f"   ↳ {question} → {value!r} ({how})", flush=True)
        return value

    @staticmethod
    def needs_input(question: str, reason: str = "", options: List[str] = None):
        """Exit with EXIT_NEEDS_INPUT, telling the caller exactly which --answer to add."""
        print(f"\n❓ SPEKY needs an answer it cannot get without a terminal.", flush=True)
        print(f"   Question: {question}")
        if reason:
            print(f"   {reason}")
        if options:
            for i, opt in enumerate(options, 1):
                print(f"     {i}. {opt}")
        key = re.sub(r"[^\w ()/-]", "", question).strip()[:40] or "question"
        print(f"   Re-run the same command with:  --answer \"{key}=<value>\"")
        sys.exit(EXIT_NEEDS_INPUT)

    @classmethod
    def prompt(cls, message: str, default: str = None) -> str:
        """Get user input with prompt"""
        preset = cls._preset_answer(message)
        if preset is not None:
            return cls._unattended(message, preset, "--answer")
        if cls.non_interactive:
            return cls._unattended(message, default or "", "default" if default else "empty, no default")
        if default:
            response = input(f"📝 {message} [{default}]: ").strip()
            return response if response else default
        return input(f"📝 {message}: ").strip()

    @classmethod
    def confirm(cls, message: str, default: bool = True) -> bool:
        """Ask for confirmation"""
        preset = cls._preset_answer(message)
        if preset is not None:
            return cls._unattended(message, preset, "--answer").strip().lower() in ('y', 'yes', 'true', '1')
        # --yes says yes once; a repeat of the same confirmation ("Add another?") takes its default
        if cls.assume_yes and not cls._asked.get(" ".join(message.split())):
            return cls._unattended(message, "yes", "--yes") == "yes"
        if cls.non_interactive:
            return cls._unattended(message, "yes" if default else "no", "default") == "yes"
        suffix = "[Y/n]" if default else "[y/N]"
        response = input(f"❓ {message} {suffix}: ").strip().lower()
        if not response:
            return default
        return response in ('y', 'yes')

    @classmethod
    def choose(cls, message: str, options: List[str]) -> int:
        """Present options and get choice. Answers may be an option number or part of its text."""
        preset = cls._preset_answer(message)
        if preset is not None:
            if preset.strip().isdigit() and 1 <= int(preset) <= len(options):
                index = int(preset) - 1
            else:
                matches = [i for i, opt in enumerate(options) if preset.lower() in opt.lower()]
                if not matches:
                    cls.needs_input(message.strip(), f"--answer {preset!r} matches none of the options:", options)
                index = matches[0]
            cls._unattended(message, options[index], "--answer")
            return index
        if cls.non_interactive:
            cls.needs_input(message.strip(), "Choose one of (number or part of the text):", options)
        print(f"\n{message}")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        
        while True:
            try:
                choice = int(input("\n📝 Enter number: ").strip())
                if 1 <= choice <= len(options):
                    return choice - 1
                print(f"Please enter 1-{len(options)}")
            except ValueError:
                print("Please enter a number")

    @classmethod
    def text_block(cls, message: str, line_prompt: str = "", stop_on_blank: bool = False) -> str:
        """Read multi-line text: until EOF (Ctrl+D), or until a blank line if stop_on_blank."""
        preset = cls._preset_answer(message)
        if preset is not None:
            return cls._unattended(message, preset, "--answer")
        if cls.non_interactive:
            return cls._unattended(message, "", "empty, no default")
        lines = []
        try:
            while True:
                line = input(line_prompt)
                if stop_on_blank and not line.strip():
                    break
                lines.append(line)
        except EOFError:
            pass
        return "\n".join(lines).strip()

    @classmethod
    def pause(cls, message: str = "Press Enter to continue..."):
        if cls.non_interactive:
            return
        input(message)

    @staticmethod
    def files_created(files: List[str]):
        """Show created files"""
        print(f"\n📦 Files created:")
        for f in files:
            print(f"   • {f}")
    
    @staticmethod
    def status_table(items: List[dict], columns: List[str]):
        """Print a simple status table"""
        if not items:
            print("   (none)")
            return
        
        # Calculate column widths
        widths = {col: len(col) for col in columns}
        for item in items:
            for col in columns:
                widths[col] = max(widths[col], len(str(item.get(col, ""))))
        
        # Header
        header = " | ".join(col.ljust(widths[col]) for col in columns)
        print(f"   {header}")
        print(f"   {'-' * len(header)}")
        
        # Rows
        for item in items:
            row = " | ".join(str(item.get(col, "")).ljust(widths[col]) for col in columns)
            print(f"   {row}")


# =============================================================================
# PROMPT TEMPLATES (Agnostic)
# =============================================================================

class Prompts:
    """Agnostic prompt templates - no hardcoded tech stacks or assumptions"""

    @staticmethod
    def intent_clarification(product_idea: str) -> str:
        """Generate clarifying questions for any product idea"""
        return f"""You are a product strategist helping understand a product idea. 

PRODUCT IDEA: {product_idea}

Generate exactly 5 clarifying questions to understand:
1. What specific problem does this solve and for whom?
2. What would the MVP (minimum viable product) include?
3. What platform/medium is this for? (web, mobile, desktop, API, hardware, etc.)
4. What scale are you targeting initially? (personal use, small team, startup, enterprise)
5. Any specific constraints? (budget, timeline, existing systems, regulations)

Format as a numbered list. Keep questions conversational and open-ended.
Do NOT assume any technology choices - this should work for any product type."""

    @staticmethod
    def answer_questions_from_project(product_idea: str, questions: List[str], evidence: str) -> str:
        """Answer init's clarifying questions from an existing project's own files"""
        numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
        return f"""You are documenting an EXISTING software project. Answer each question below
the way the project's owner would, using ONLY the evidence (its docs, manifests and
structure) — and, if you are an agent working inside this repository, what you can
see in the code itself. Do not invent facts.

PRODUCT: {product_idea}

QUESTIONS:
{numbered}

EVIDENCE FROM THE PROJECT:
{evidence}

Return ONLY JSON:
{{"answers": [{{"question": 1, "answer": "concise answer in the owner's voice", "source": "README.md, package.json"}}]}}

Rules:
- One entry per question, using its number.
- If the evidence does not support an answer, use "answer": "" (it will be left for the owner).
- "source" names the files the answer came from."""

    @staticmethod
    def build_product_profile(idea: str, qa_pairs: List[dict]) -> str:
        """Build product profile from Q&A - completely agnostic"""
        qa_text = "\n".join([f"Q: {qa['question']}\nA: {qa['answer']}" for qa in qa_pairs])
        return f"""Based on this conversation, create a structured product profile.

ORIGINAL IDEA: {idea}

QUESTIONS & ANSWERS:
{qa_text}

Output ONLY a valid JSON object:
{{
    "name": "Short product name",
    "description": "2-3 sentence description",
    "target_users": "Who will use this",
    "problem": "Core problem being solved",
    "platform": "web/mobile/desktop/api/cli/hardware/other",
    "scale": "personal/team/startup/enterprise",
    "domain": "The industry or context (e.g., cooking, finance, education, healthcare)",
    "features": ["Feature 1: Brief description", "Feature 2: Brief description"],
    "constraints": "Any mentioned constraints",
    "mvp_scope": "What's included in MVP"
}}

Output ONLY the JSON, no other text or markdown."""

    @staticmethod
    def suggest_tech_stack(product_summary: str) -> str:
        """Suggest tech stack options based on product description"""
        return f"""Based on this product description, suggest a tech stack with options and rationale.

PRODUCT SUMMARY:
{product_summary}

Provide recommendations in this format:

# Tech Stack Recommendations

## Frontend
- **Option 1**: [Framework] - Why it fits
- **Option 2**: [Framework] - Why it fits
- **Option 3**: [Framework] - Why it fits

## Backend
- **Option 1**: [Runtime/Language] - Why it fits
- **Option 2**: [Runtime/Language] - Why it fits
- **Option 3**: [Runtime/Language] - Why it fits

## Database
- **Option 1**: [Database] - Why it fits
- **Option 2**: [Database] - Why it fits
- **Option 3**: [Database] - Why it fits

## Deployment
- **Option 1**: [Platform] - Why it fits
- **Option 2**: [Platform] - Why it fits
- **Option 3**: [Platform] - Why it fits

## Rationale
Brief explanation of why these options work well together for this product.

Be concise and practical. Focus on options that are realistic for MVP development."""

    @staticmethod
    def generate_spec(feature_name: str, product_context: str, existing_code: str = "", tech_stack: dict = None) -> str:
        """Generate feature specification - MVP-focused with tech constraints"""
        code_section = f"\n\nEXISTING CODEBASE:\n{existing_code}" if existing_code else ""
        tech_section = ""
        if tech_stack:
            tech_section = f"""\nTECH STACK:
- Frontend: {tech_stack.get('frontend', 'Not decided')}
- Backend: {tech_stack.get('backend', 'Not decided')}
- Database: {tech_stack.get('database', 'Not decided')}
- Deployment: {tech_stack.get('deployment', 'Not decided')}

IMPORTANT: Scope this feature to be achievable in 1-2 weeks with the above tech stack."""
        
        return f"""You are writing a feature specification for an MVP.

FEATURE: {feature_name}

{product_context}
{code_section}
{tech_section}

CREATE A MINIMAL VIABLE SPECIFICATION:

# {feature_name}

## Overview
What this feature does and why (2-3 sentences max).

## MVP Scope
Explicitly state what IS included in this MVP version (be specific and minimal).

## User Stories
Include 1-2 core user stories ONLY (not 3-5+). Each with acceptance criteria.
Example:
- As a [user], I want [minimal action], so that [core benefit]
  - Acceptance: [specific, testable criteria]

## Requirements
### Functional Requirements (MVP only)
- List ONLY essential behaviors for this feature to work
- Remove nice-to-haves

### Non-Functional Requirements
- Only if critical (e.g., "must load in <2s")

## Out of Scope (IMPORTANT)
Explicitly list what is NOT included (e.g., "Analytics, advanced filtering, mobile optimization, etc.")
This prevents scope creep.

## Open Questions
List specific decisions needed before implementation:
- [Specific question that blocks development]
- [Not vague - must be answerable]

## Technical Approach
Given the tech stack above, describe the minimal approach:
- Key libraries/services to use
- Main architectural decisions
- Any platform-specific constraints

Format as clean markdown. KEEP IT SHORT - this should be 1-2 pages max."""

    @staticmethod
    def generate_spec_with_research(feature_name: str, product_context: str, existing_code: str = "", tech_stack: dict = None, research: str = "") -> str:
        """Generate feature specification using existing research/documentation"""
        code_section = f"\n\nEXISTING CODEBASE:\n{existing_code}" if existing_code else ""
        tech_section = ""
        if tech_stack:
            tech_section = f"""\nTECH STACK:
- Frontend: {tech_stack.get('frontend', 'Not decided')}
- Backend: {tech_stack.get('backend', 'Not decided')}
- Database: {tech_stack.get('database', 'Not decided')}
- Deployment: {tech_stack.get('deployment', 'Not decided')}

IMPORTANT: Scope this feature to be achievable in 1-2 weeks with the above tech stack."""
        
        research_section = ""
        if research:
            research_section = f"""\nEXISTING RESEARCH & DOCUMENTATION:
{research}

INSTRUCTIONS FOR USING RESEARCH:
- Extract key insights, decisions, and constraints from the research
- Use it as foundation for the spec
- Identify gaps or ambiguities that need clarification
- Structure the research into proper spec format
- Keep the MVP scope minimal despite comprehensive research"""
        
        return f"""You are writing a feature specification for an MVP, using existing research as foundation.

FEATURE: {feature_name}

{product_context}{code_section}{tech_section}{research_section}

CREATE A MINIMAL VIABLE SPECIFICATION:

# {feature_name}

## Overview
What this feature does and why (2-3 sentences max).

## MVP Scope
Explicitly state what IS included in this MVP version (be specific and minimal).
Note: Even if research suggests more, focus on the absolute minimum for MVP.

## User Stories
Include 1-2 core user stories ONLY (not 3-5+). Each with acceptance criteria.
Example:
- As a [user], I want [minimal action], so that [core benefit]
  - Acceptance: [specific, testable criteria]

## Requirements
### Functional Requirements (MVP only)
- List ONLY essential behaviors for this feature to work
- Remove nice-to-haves, even if mentioned in research

### Non-Functional Requirements
- Only if critical (e.g., "must load in <2s")

## Out of Scope (IMPORTANT)
Explicitly list what is NOT included (e.g., "Analytics, advanced filtering, mobile optimization, etc.")
This prevents scope creep. Note any advanced features from research that are out of scope.

## Open Questions
List specific decisions needed before implementation:
- [Specific question that blocks development]
- [Not vague - must be answerable]
Include any ambiguities found in the research.

## Technical Approach
Given the tech stack above, describe the minimal approach:
- Key libraries/services to use
- Main architectural decisions
- Any platform-specific constraints
Reference decisions from research where applicable.

## Research Summary
Brief note on how research informed this spec (1-2 sentences).

Format as clean markdown. KEEP IT SHORT - this should be 1-2 pages max."""

    @staticmethod
    def generate_plan(spec_content: str, product_context: str, tech_stack: dict = None) -> str:
        """Generate implementation plan - MVP-focused with realistic timelines"""
        tech_section = ""
        if tech_stack:
            tech_section = f"""\nTECH STACK:
- Frontend: {tech_stack.get('frontend', 'Not decided')}
- Backend: {tech_stack.get('backend', 'Not decided')}
- Database: {tech_stack.get('database', 'Not decided')}
- Deployment: {tech_stack.get('deployment', 'Not decided')}

IMPORTANT: All tasks must be implementable with the above tech stack in 1-2 weeks total."""
        
        return f"""You are creating an implementation plan for an MVP feature.

{product_context}{tech_section}

SPECIFICATION:
{spec_content}

Create a REALISTIC implementation plan:

# Implementation Plan

## Approach
Minimal approach to implementing ONLY what's in the spec (2-3 sentences).

## Tasks
Break down into 3-8 discrete, achievable tasks (NOT 10-15). For each task:
- [ ] **Task title** (estimate: 2-8h)
  - What specifically needs to be done
  - Acceptance criteria (testable)
  - Dependencies

Each task should be completable in 1 day or less.
Total should not exceed 40 hours.

## Architecture Decisions Needed
List ONLY decisions that block implementation:
- [Specific decision needed]
- [Not vague - must be answerable before coding starts]

## Testing Approach
Minimal testing needed to verify the spec works.

## Risks & Mitigations
Top 2-3 risks only, with concrete mitigations.

Focus on FEASIBILITY. If something seems unrealistic, call it out in Risks.
The implementing engineer will choose specific tools based on the tech stack."""

    @staticmethod
    def generate_story(story_type: str, title: str, product_context: str, related_spec: str = "") -> str:
        """Generate story (bug/enhancement/feature) - for ongoing development"""
        spec_section = f"\n\nRELATED SPECIFICATION:\n{related_spec}" if related_spec else ""
        return f"""You are creating a development story.

STORY TYPE: {story_type}
TITLE: {title}

{product_context}
{spec_section}

Create a story document:

# [{story_type.upper()}] {title}

## Description
What needs to be done and why.

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
(Be specific and testable)

## Context
Any relevant context for the implementer.

## Tasks
- [ ] Task 1
- [ ] Task 2
(Break down if helpful)

## Notes
Any additional notes.

Format as markdown. Keep it concise and actionable."""

    @staticmethod
    def suggest_fix_for_gap(gap: str) -> str:
        """Suggest specific fixes for a validation gap"""
        return f"""A feature specification has the following gap/issue:

GAP: {gap}

Provide specific, actionable suggestions to fix this gap. Be concise and practical.
Include:
1. What needs to be added/changed
2. Where in the spec it should go
3. Example or template if helpful

Keep it brief (2-3 sentences max)."""

    @staticmethod
    def apply_validation_fix(spec_content: str, spec_name: str, issue_description: str, ai_suggestion: str) -> str:
        """Generate updated spec content with AI-suggested fix applied"""
        line_count = len(spec_content.splitlines())
        return f"""You are updating a feature specification to fix a validation issue.

CURRENT SPEC ({line_count} lines - YOU MUST PRESERVE ALL CONTENT):
{spec_content}

ISSUE TO FIX:
{issue_description}

AI SUGGESTION FOR FIX:
{ai_suggestion}

CRITICAL INSTRUCTIONS:
1. Return the COMPLETE updated specification - every single line
2. DO NOT truncate, summarize, or omit ANY existing content
3. ADD the fix content in the appropriate location
4. PRESERVE all existing sections, code blocks, and text exactly as they are
5. The output should have AT LEAST {line_count} lines (original) plus any new additions
6. If you cannot fit everything, return the original spec unchanged

Update Rules:
- Keep ALL existing content that doesn't need changing
- Integrate the fix naturally into the appropriate section
- Maintain markdown formatting exactly
- Ensure the fix addresses the issue completely
- DO NOT remove any existing sections or content

Return ONLY the complete updated spec content, no explanations or comments.
The output must be the full specification document."""

    @staticmethod
    def validate_spec(spec_content: str, project_context: str = "", 
                      related_specs: str = "", tech_stack: str = "",
                      tech_decisions: str = "", poc_recommendations: str = "") -> str:
        """Validate a specification and identify gaps - context-aware version"""
        
        context_section = ""
        if project_context or tech_stack:
            context_section = f"""
PROJECT CONTEXT:
{project_context}

TECH STACK (respect these decisions):
{tech_stack}
"""
        
        # Tech decisions are AUTHORITATIVE - must be followed
        tech_decisions_section = ""
        if tech_decisions:
            tech_decisions_section = f"""
=== AUTHORITATIVE TECH DECISIONS (MUST FOLLOW) ===
The following technology decisions have been made for this project.
You MUST NOT suggest alternatives to these. Flag any spec content that uses different packages.

{tech_decisions[:3000]}
=== END TECH DECISIONS ===
"""
        
        # POC recommendations provide additional context
        poc_section = ""
        if poc_recommendations:
            poc_section = f"""
POC IMPORT RECOMMENDATIONS (for reference):
{poc_recommendations[:1500]}
"""
        
        related_section = ""
        if related_specs:
            related_section = f"""
RELATED SPECS IN PROJECT (check for overlaps/conflicts):
{related_specs}
"""
        
        return f"""Analyze this feature specification for quality and completeness.
{context_section}
{tech_decisions_section}
{poc_section}
{related_section}
SPECIFICATION TO VALIDATE:
{spec_content}

VALIDATION RULES:
1. **MVP Focus**: Is the scope minimal and achievable in 1-2 weeks?
2. **Clarity**: Are requirements specific and unambiguous?
3. **Completeness**: Are all necessary sections present and filled?
4. **Testability**: Can acceptance criteria be verified?
5. **Technical Feasibility**: Is the technical approach realistic?
6. **Tech Stack Alignment**: Does it use the project's chosen technologies? (Don't suggest alternatives)
7. **Cross-Spec Consistency**: Does it conflict with or duplicate other specs?
8. **Tech Decision Compliance**: Does it follow the authoritative tech decisions?

CRITICAL INSTRUCTIONS:
- BEFORE making ANY tech recommendations, check the AUTHORITATIVE TECH DECISIONS section
- Do NOT suggest different packages/frameworks than what's in tech_decisions.md
- If the spec uses a package that contradicts tech decisions, flag it as a TECH VIOLATION
- If a feature overlaps with another spec, flag it as a potential duplicate
- Use consistent terminology with other specs in the project
- Check POC recommendations for context on why certain tech choices were made

Provide your analysis in this format:

## Tech Violations
List any violations of authoritative tech decisions (if any):
- [VIOLATION: Spec uses X but project decided on Y]

## Gaps/Issues
For each gap, provide the issue AND how to fix it:
- **Gap**: [Specific gap or issue]
  **Fix**: [What to add/change and where it should go]

- **Gap**: [Another gap]
  **Fix**: [Specific fix recommendation]

## Cross-Spec Concerns
List any overlaps or conflicts with other specs (if any):
- [Overlap with spec XXX: description]

## Suggestions
List improvements to consider (ONLY using approved tech stack):
- [Specific suggestion]
- [Another suggestion]

## Summary
One sentence overall assessment.

Be specific and actionable. If the spec is good, say so briefly.
For gaps, always provide both the issue AND the fix so users have immediate guidance."""

    @staticmethod
    def validate_story(story_content: str, project_context: str = "", 
                       related_specs: str = "", tech_stack: str = "") -> str:
        """Validate a story for completeness - used when user wants thorough validation of complex stories"""
        
        context_section = ""
        if project_context or tech_stack:
            context_section = f"""
PROJECT CONTEXT:
{project_context}

TECH STACK:
{tech_stack}
"""
        
        related_section = ""
        if related_specs:
            related_section = f"""
RELATED SPECS (for context):
{related_specs}
"""
        
        return f"""Analyze this story for completeness and quality. The user is validating this story because they believe it may be complex and want to ensure it's well-defined before implementation.
{context_section}
{related_section}
STORY TO VALIDATE:
{story_content}

VALIDATION CRITERIA:
1. **Clarity**: Is the description clear and unambiguous?
2. **Scope**: Is the scope appropriate for a story (not too large)?
3. **Acceptance Criteria**: Are all acceptance criteria specific and testable?
4. **Dependencies**: Are dependencies clearly identified?
5. **Technical Feasibility**: Is the technical approach realistic?
6. **Completeness**: Are all necessary details provided?

Provide your analysis in this format:

## Gaps/Issues
List specific problems that should be fixed:
- [Specific gap or issue]

## Suggestions
List improvements to consider:
- [Specific suggestion]

## Scope Assessment
Is this story appropriately scoped? Should it be:
- Kept as-is
- Split into multiple stories
- Promoted to a spec (if too large)

## Quality Score
Rate 1-10 with brief justification.

## Summary
One sentence overall assessment.

Be specific and actionable. If the story is good, say so briefly."""

    @staticmethod
    def generate_story_plan(story_content: str, product_context: str, tech_stack: dict) -> str:
        """Generate a task breakdown plan for a story"""
        tech_info = json.dumps(tech_stack, indent=2) if tech_stack else "Not specified"
        
        return f"""Generate a concise implementation plan for this story.

STORY:
{story_content}

PROJECT CONTEXT:
{product_context[:2000]}

TECH STACK:
{tech_info}

Create a focused task breakdown with 2-5 tasks. Each task should be:
- Specific and actionable
- Completable in 30 minutes to 2 hours
- In logical implementation order

FORMAT:
# Implementation Plan

## Tasks

### Task 1: [Title]
- **Estimate**: [time]
- **Description**: What to do
- **Files**: Likely files to modify

### Task 2: [Title]
...

## Implementation Notes
Any important technical considerations or gotchas.

## Testing Checklist
- [ ] Test case 1
- [ ] Test case 2

Keep it concise - stories are meant to be quick implementations."""

    @staticmethod
    def suggest_fix_with_full_context(gap: str, user_context: str, 
                                       session_context: str, tech_stack: str,
                                       related_specs: str = "") -> str:
        """Get AI suggestion with full project and session context"""
        
        related_section = ""
        if related_specs:
            related_section = f"""
RELATED SPECS (user mentioned or auto-detected):
{related_specs}

If the gap relates to features in these specs, suggest:
- Referencing the related spec instead of duplicating
- Using consistent terminology
- Adding dependencies if appropriate
"""
        
        return f"""A feature specification has the following gap/issue:

GAP: {gap}

USER'S CONTEXT/CONCERNS:
{user_context}

PROJECT TECH STACK (use only these technologies):
{tech_stack}

SESSION CONTEXT (decisions made earlier in this validation):
{session_context}
{related_section}
Provide specific, actionable suggestions to fix this gap.

RULES:
1. ONLY suggest technologies from the project's tech stack
2. If user mentioned another spec, reference it properly
3. Apply any terminology mappings from session context
4. Don't duplicate features that exist in related specs
5. Suggest adding dependencies to related specs if needed

Include:
1. What needs to be added/changed (addressing user's concerns)
2. Where in the spec it should go
3. If this overlaps with another spec, how to handle it
4. Example or template if helpful

Keep it brief but address the user's specific concerns and project context."""

    @staticmethod
    def analyze_codebase(file_list: str, tech_decisions: str = "") -> str:
        """Analyze codebase structure - for sync command"""
        tech_context = ""
        if tech_decisions:
            tech_context = f"""
AUTHORITATIVE TECH DECISIONS (use this as the source of truth):
{tech_decisions}

IMPORTANT: The tech decisions above are AUTHORITATIVE. Use them to accurately describe the stack.
Do NOT guess or assume technologies from file names alone. For example, if tech decisions say 
"SQLite" but you see a file named "surrealdb.ts", the project uses SQLite (the file may be legacy).
"""
        
        return f"""Analyze this codebase structure and create a summary.

FILES:
{file_list}
{tech_context}
Create a codebase map with:

# Codebase Structure

## Project Type
What kind of project this appears to be.

## Key Directories
- `dir/` - What it contains

## Key Files
- `file` - What it does (only list files that actually exist and are relevant)

## Patterns Observed
Any patterns in the codebase structure.

## Notes for AI Assistants
Helpful context for AI tools working on this codebase.
- Use ONLY the technologies from Tech Decisions if provided
- Do NOT mention technologies that aren't in Tech Decisions
- Keep notes factual and based on actual project structure

Keep it concise. This will be used as context for future development."""

    @staticmethod
    def check_drift(spec_content: str, current_code: str) -> str:
        """Check for spec-code drift"""
        return f"""Compare this specification with the actual implementation.

SPECIFICATION:
{spec_content}

CURRENT CODE:
{current_code}

Analyze and report:

# Drift Analysis

## Status
[IN_SYNC / MINOR_DRIFT / MAJOR_DRIFT / NOT_IMPLEMENTED]

## Implemented Features
What from the spec is implemented.

## Missing Features
What from the spec is NOT yet implemented.

## Deviations
Where implementation differs from spec (not necessarily wrong).

## Recommendations
- Update spec to match reality, OR
- Update code to match spec

Be concise and actionable."""

    @staticmethod 
    def generate_ide_context(product_context: str, active_task: str = "") -> str:
        """Generate context file for IDE (.windsurfrules, CLAUDE.md, etc.)"""
        task_section = f"\n\n## Current Task\n{active_task}" if active_task else ""
        return f"""Generate a context file for AI coding assistants.

{product_context}
{task_section}

Create a markdown file that helps AI coding assistants understand:
1. What this project is
2. Key architectural decisions
3. Coding conventions to follow
4. Current focus/task (if any)

Keep it under 500 words. Focus on what an AI needs to write good code.
Do NOT include specific tool instructions (the format will be adapted for each IDE)."""

    @staticmethod
    def analyze_external_documents(doc_content: str, product_context: str) -> str:
        """Analyze external documents and extract implementation roadmap"""
        return f"""Analyze these external documents and create a structured implementation roadmap.

PRODUCT CONTEXT:
{product_context}

DOCUMENTS:
{doc_content}

Provide analysis in this format:

# Document Analysis

## Key Findings
- Main features/requirements identified
- Scope and scale assessment
- Dependencies and constraints

## Proposed Implementation Phases
For each phase, list:
- Phase name
- Features included
- Estimated effort
- Dependencies on other phases

## Risks & Considerations
- Technical challenges
- Scope ambiguities
- Missing information

Be specific and actionable."""

    @staticmethod
    def propose_specs_from_analysis(analysis: str, tech_stack: dict = None) -> str:
        """Generate spec proposals from document analysis"""
        tech_section = ""
        if tech_stack:
            tech_section = f"""\nTECH STACK:
- Frontend: {tech_stack.get('frontend', 'Not decided')}
- Backend: {tech_stack.get('backend', 'Not decided')}
- Database: {tech_stack.get('database', 'Not decided')}
- Deployment: {tech_stack.get('deployment', 'Not decided')}"""
        
        return f"""Based on this analysis, propose individual specs for implementation.

ANALYSIS:
{analysis}
{tech_section}

For each proposed spec, respond in this format:

SPEC: <Feature Name>
SCOPE: <What's included in this spec (2-3 sentences)>
ESTIMATE: <Estimated hours (e.g., 8-12h)>
SOURCE: <Which document section this came from>
---

Propose 3-8 specs total. Each should be:
- Achievable in 1-2 weeks
- Independent or clearly dependent on others
- Aligned with the tech stack above

Keep specs focused on MVP scope."""

    # -------------------------------------------------------------------------
    # Initial Research Prompts (Enhanced Init)
    # -------------------------------------------------------------------------
    
    @staticmethod
    def analyze_initial_research(product_idea: str, documents: List[dict]) -> str:
        """Analyze initial research documents and extract structured information"""
        doc_list = "\n".join([f"- {d['name']} ({d.get('type', 'unknown')}): {d.get('size', 'unknown')}" for d in documents])
        doc_content = ""
        for doc in documents:
            try:
                content = Path(doc['path']).read_text()
                doc_content += f"\n\n--- {doc['name']} ---\n{content[:5000]}"
            except:
                doc_content += f"\n\n--- {doc['name']} ---\n[Could not read content]"
        
        return f"""Analyze these research documents for a new product.

PRODUCT IDEA: {product_idea}

DOCUMENTS FOUND:
{doc_list}

DOCUMENT CONTENTS:
{doc_content}

Analyze and extract:

## Product Information
- Product name (if mentioned)
- Description/vision
- Target users
- Problem being solved
- Platform (web/mobile/desktop/etc)
- Scale expectations

## Tech Stack (from documents)
Extract any tech preferences or requirements mentioned:
- Frontend: [mentioned tech or "not specified"]
- Backend: [mentioned tech or "not specified"]
- Database: [mentioned tech or "not specified"]
- Infrastructure: [mentioned tech or "not specified"]
- Other technologies mentioned

## Features (from documents)
List features mentioned, categorize as:
- Core/MVP features
- Future/nice-to-have features

## Constraints & Requirements
- Business constraints
- Technical constraints
- Compliance/security requirements
- Timeline mentions

## Gaps & Ambiguities
What's unclear or missing that we should ask about?
- List specific gaps
- Note contradictions if any

## Summary
2-3 sentence summary of what these documents tell us about the product.

Be thorough but concise. Focus on actionable information."""

    @staticmethod
    def smart_clarifying_questions(product_idea: str, research_analysis: str, gaps: List[str]) -> str:
        """Generate smart clarifying questions based on research gaps"""
        gaps_text = "\n".join([f"- {gap}" for gap in gaps]) if gaps else "No specific gaps identified"
        
        return f"""Based on the research analysis, generate clarifying questions.

PRODUCT IDEA: {product_idea}

RESEARCH ANALYSIS:
{research_analysis}

IDENTIFIED GAPS:
{gaps_text}

Generate 2-5 focused clarifying questions that:
1. Address the gaps identified above
2. Clarify any ambiguities in the research
3. Fill in missing critical information
4. Do NOT ask about things already covered in the research

If the research is comprehensive and covers most aspects, generate fewer questions (2-3).
If there are many gaps, generate more questions (4-5).

Format as a numbered list. Questions should be:
- Specific and answerable
- Not redundant with research
- Focused on decisions that impact implementation

If research already covers everything well, just output:
"Research is comprehensive. Only confirm: [1 key confirmation question]" """

    # -------------------------------------------------------------------------
    # POC Import Prompts
    # -------------------------------------------------------------------------
    
    @staticmethod
    def poc_research_task(poc_paths: List[str], project_tech_stack: dict = None) -> str:
        """Generate comprehensive POC research task for IDE"""
        paths_text = "\n".join([f"- {p}" for p in poc_paths])
        tech_text = ""
        if project_tech_stack:
            tech_text = f"""
## Current Project Tech Stack (for conflict detection)
- Frontend: {project_tech_stack.get('frontend', 'Not decided')}
- Backend: {project_tech_stack.get('backend', 'Not decided')}
- Database: {project_tech_stack.get('database', 'Not decided')}
- Deployment: {project_tech_stack.get('deployment', 'Not decided')}
"""
        
        return f"""# POC Code Research Task

## POC Project(s) to Analyze
{paths_text}
{tech_text}
## Instructions for IDE/Coding Agent

Perform a COMPLETE code analysis of the POC project(s). Do NOT rely on documentation - analyze the actual code.

### 1. Features Analysis
Identify all FEATURES (user-facing functionality) implemented:

For each feature:
- **Name**: Clear, descriptive name
- **Description**: What it does (1-2 sentences)
- **Sub-features**: Any sub-components (e.g., "Auth" might have "JWT", "OAuth", "Sessions")
- **Complexity**: S (small, <1 day), M (medium, 1-3 days), L (large, 3+ days)
- **Quality Notes**: Is this production-ready or POC-quality? Any shortcuts/hacks?

### 2. Tech Stack (from code analysis)
Identify from actual code:
- Languages and versions
- Frameworks (frontend, backend)
- Databases/storage
- External services/APIs
- Key dependencies (with versions)

### 3. Feature Dependencies
Which features depend on which:
- Internal dependencies (feature A needs feature B)
- Shared code/utilities used across features

### 4. Multi-POC Analysis (if multiple POCs)
If analyzing multiple POCs:
- Overlapping features (same functionality in both)
- Conflicting implementations
- Complementary features

## Output Format

Write results to `results.json` in this structure:

```json
{{
  "pocs": [
    {{
      "path": "/path/to/poc",
      "name": "POC Name (derived from folder or package.json)",
      "tech_stack": {{
        "language": "TypeScript 5.0",
        "framework": "Express 4.18",
        "database": "PostgreSQL",
        "key_dependencies": [
          {{"name": "bcrypt", "version": "5.1.0", "purpose": "Password hashing"}}
        ]
      }},
      "features": [
        {{
          "id": "auth",
          "name": "User Authentication",
          "description": "JWT-based login, registration, password reset",
          "sub_features": ["jwt_login", "registration", "password_reset"],
          "complexity": "M",
          "quality": "production-ready",
          "notes": "Well-tested, uses industry best practices",
          "code_paths": ["src/auth/", "src/middleware/auth.ts"]
        }}
      ]
    }}
  ],
  "feature_dependencies": [
    {{"from": "api", "to": "auth", "reason": "API routes require auth middleware"}}
  ],
  "multi_poc": {{
    "overlaps": [],
    "conflicts": [],
    "complementary": []
  }}
}}
```

Be thorough. This analysis drives which features get imported."""

    @staticmethod
    def poc_auto_resolve(selected_features: List[dict], poc_tech: dict, project_tech: dict) -> str:
        """Generate AI recommendations for POC import conflicts and handling"""
        features_text = json.dumps(selected_features, indent=2)
        
        return f"""Analyze these selected POC features and recommend how to handle them.

SELECTED FEATURES:
{features_text}

POC TECH STACK:
{json.dumps(poc_tech, indent=2)}

PROJECT TECH STACK:
{json.dumps(project_tech, indent=2)}

For each feature, recommend:

## Tech Conflict Analysis
For each technology in POC vs Project:
- Is there a conflict? (e.g., Express vs FastAPI)
- Severity: NONE, LOW (minor adaptation), HIGH (full rewrite)
- Recommendation: What to do about it

## Feature Handling Recommendations
For each feature:
- **COPY_CODE**: Copy code as-is (no conflicts, production-ready)
- **SPEC_ONLY**: Create spec, reimplement fresh (conflicts or POC-quality)

Consider:
- Tech conflicts (HIGH conflict = SPEC_ONLY)
- Code quality (POC shortcuts = SPEC_ONLY)
- Compatibility (same tech = COPY_CODE likely)

## New Dependencies
List any new dependencies the project needs to add.

## Output Format
```json
{{
  "tech_conflicts": [
    {{
      "component": "backend_framework",
      "poc": "Express",
      "project": "FastAPI",
      "severity": "HIGH",
      "recommendation": "Create specs for functionality, reimplement in FastAPI"
    }}
  ],
  "feature_handling": [
    {{
      "feature_id": "auth",
      "feature_name": "User Authentication",
      "action": "SPEC_ONLY",
      "reason": "Backend framework conflict - needs reimplementation",
      "notes": "Port JWT logic, keep same token structure"
    }}
  ],
  "new_dependencies": [
    {{"name": "python-jose", "purpose": "JWT handling in FastAPI"}}
  ],
  "summary": "2 features to copy, 3 features need specs due to tech conflicts"
}}
```

Be practical. Minimize work while ensuring compatibility."""

    @staticmethod
    def poc_extraction_task(selected_features: List[dict], resolutions: dict, spec_template: str = "") -> str:
        """Generate extraction task for IDE to create specs from POC"""
        features_text = ""
        for f in selected_features:
            handling = next((h for h in resolutions.get('feature_handling', []) if h['feature_id'] == f['id']), {})
            action = handling.get('action', 'SPEC_ONLY')
            features_text += f"""
### Feature: {f['name']}
- **ID**: {f['id']}
- **Action**: {action}
- **Source Paths**: {', '.join(f.get('code_paths', ['unknown']))}
- **Notes**: {handling.get('notes', 'None')}
"""
        
        return f"""# POC Extraction Task

## Features to Extract
{features_text}

## Instructions for IDE/Coding Agent

For each feature above, create a detailed spec.

### Spec Format
Create a file in `specs/<feature-id>/spec.md` with:

```markdown
# <Feature Name>

## Source
- POC: <path>
- Original Code: <paths>
- Action: COPY_CODE | SPEC_ONLY

## Overview
What this feature does (from POC analysis).

## Functionality
Detailed list of what this feature does:
- List each function/behavior
- Include edge cases handled
- Note any limitations

## Interfaces
### Inputs
- API endpoints (if any)
- Function signatures
- Expected data formats

### Outputs
- Response formats
- Events emitted
- Side effects

## Dependencies
- Internal: Other features this depends on
- External: Packages/services needed

## Code Reference (for COPY_CODE)
Key code snippets to preserve:
```<language>
// Important code from POC
```

## Implementation Notes
- POC shortcuts to fix
- Tech translations needed (e.g., Express → FastAPI)
- Quality improvements to make
- Security considerations

## Testing Approach
How to verify this feature works correctly.
```

### For COPY_CODE Features
1. Copy relevant source files to project
2. Update imports to match project structure
3. Create the spec documenting what was copied

### For SPEC_ONLY Features
1. Create detailed spec from code analysis
2. Do NOT copy code
3. Document functionality for fresh implementation

## Output
- Specs: Create in `specs/` folder with one folder per feature
- Report: Write `extraction_report.json`:
```json
{{
  "features_processed": ["auth", "api"],
  "specs_created": ["specs/auth/spec.md", "specs/api/spec.md"],
  "code_copied": ["src/models/"],
  "errors": []
}}
```

Be thorough in specs - they drive implementation."""

    # -------------------------------------------------------------------------
    # Phase Management Prompts
    # -------------------------------------------------------------------------
    
    @staticmethod
    def suggest_phases_from_specs(specs_summary: str, product_context: str, tech_stack: dict = None) -> str:
        """AI suggests logical phase groupings from existing specs"""
        tech_section = ""
        if tech_stack:
            tech_section = f"""
TECH STACK:
- Frontend: {tech_stack.get('frontend', 'Not decided')}
- Backend: {tech_stack.get('backend', 'Not decided')}
- Database: {tech_stack.get('database', 'Not decided')}"""

        return f"""Analyze these specs and suggest logical implementation phases.

PRODUCT CONTEXT:
{product_context}
{tech_section}

EXISTING SPECS:
{specs_summary}

Suggest 2-4 phases that group specs logically. Consider:
1. Dependencies between specs (what must be built first)
2. User value milestones (what creates testable value)
3. Technical foundations (database, auth usually first)
4. Risk mitigation (critical features early)

Output ONLY valid JSON:
{{
  "phases": [
    {{
      "id": "phase-1",
      "name": "Foundation",
      "goal": "Core infrastructure and authentication",
      "duration_estimate": "2 weeks",
      "specs": ["001", "002"],
      "rationale": "These specs provide the foundation for all other features",
      "deliverables": ["User can sign up and log in", "Database schema deployed"],
      "success_criteria": "Auth flow works end-to-end"
    }},
    {{
      "id": "phase-2", 
      "name": "MVP Core",
      "goal": "Basic user-facing functionality",
      "duration_estimate": "3 weeks",
      "specs": ["003", "004"],
      "rationale": "These provide the core user value",
      "deliverables": ["Users can perform main action", "Basic UI working"],
      "success_criteria": "User can complete primary workflow"
    }}
  ],
  "recommendation": "Brief explanation of why this phasing makes sense"
}}

Output ONLY the JSON, no other text."""

    @staticmethod
    def suggest_phases_from_import(analysis: str, product_context: str, num_specs: int) -> str:
        """Suggest phases during external document import"""
        return f"""Based on this document analysis, suggest implementation phases.

PRODUCT CONTEXT:
{product_context}

DOCUMENT ANALYSIS:
{analysis}

NUMBER OF PROPOSED SPECS: {num_specs}

Suggest 2-4 phases for implementing these specs. Each phase should:
1. Deliver tangible user value
2. Have clear success criteria
3. Group related functionality
4. Respect dependencies

Output ONLY valid JSON:
{{
  "phases": [
    {{
      "id": "phase-1",
      "name": "Phase name",
      "goal": "What this phase achieves",
      "duration_estimate": "X weeks",
      "spec_criteria": "Which types of specs belong here (e.g., 'foundation and auth specs')",
      "deliverables": ["Testable outcome 1", "Testable outcome 2"],
      "success_criteria": "How to know phase is complete"
    }}
  ],
  "recommendation": "Brief explanation of phasing strategy"
}}

Output ONLY the JSON."""

    @staticmethod
    def generate_phase_implementation_guide(phase: dict, specs: List[dict], tech_stack: dict = None, tech_decisions: str = "") -> str:
        """Generate AI implementation guide for a phase"""
        specs_section = ""
        for spec in specs:
            specs_section += f"""
### Spec {spec.get('id')}: {spec.get('name', 'Unknown')}
- Scope: {spec.get('phase_scope', 'full')}
- Features: {', '.join(spec.get('phase_features', ['All']))}
- Excludes: {', '.join(spec.get('phase_excludes', ['None']))}
"""
        
        tech_section = ""
        if tech_stack:
            tech_section = f"""
## Tech Stack (AUTHORITATIVE)
- Frontend: {tech_stack.get('frontend', 'Not decided')}
- Backend: {tech_stack.get('backend', 'Not decided')}
- Database: {tech_stack.get('database', 'Not decided')}
"""
        
        decisions_section = ""
        if tech_decisions:
            decisions_section = f"""
## Tech Decisions (FOLLOW THESE)
{tech_decisions[:2000]}
"""
        
        deliverables = phase.get('deliverables', [])
        deliverables_section = ""
        if deliverables:
            deliverables_section = "## Deliverables (Test Each)\n"
            for d in deliverables:
                if isinstance(d, dict):
                    deliverables_section += f"- [ ] **{d.get('id', 'D')}**: {d.get('name', '')} - Test: {d.get('test', 'Manual verification')}\n"
                else:
                    deliverables_section += f"- [ ] {d}\n"
        
        return f"""Generate a comprehensive AI implementation guide for this phase.

PHASE INFORMATION:
- ID: {phase.get('id', 'unknown')}
- Name: {phase.get('name', 'Unknown Phase')}
- Goal: {phase.get('description', phase.get('goal', 'No description'))}
- Duration: {phase.get('duration', 'TBD')}

SPECS IN THIS PHASE:
{specs_section}
{tech_section}
{decisions_section}
{deliverables_section}

Generate a markdown guide with:

# Phase: {phase.get('name', 'Unknown')} - Implementation Guide

## AI Agent Instructions
Clear instructions for what to implement and what to skip.

## Implementation Order
Recommended order to implement specs within this phase.

## What NOT To Do
Explicit list of out-of-scope items for this phase.

## Cross-Spec Integrations
How specs in this phase connect to each other.

## Deliverables Checklist
How to verify each deliverable.

## Stop Conditions
When to pause and ask user for clarification.

Keep it actionable and specific. Focus on guiding AI agents."""

    # -------------------------------------------------------------------------
    # Design System Prompts
    # -------------------------------------------------------------------------
    
    @staticmethod
    def get_design_system_template(technology: str) -> str:
        """Get comprehensive design system template for a technology"""
        
        if technology.lower() == "flutter":
            return '''# Design System - [Project Name]

## Metadata
- Version: 1.0
- Technology: Flutter
- Last Updated: [date]
- Status: draft

---

## 1. COLOR SYSTEM

### 1.1 Background Colors
| Token | Value | Usage |
|-------|-------|-------|
| `backgroundPrimary` | | Main app background |
| `backgroundSecondary` | | Secondary surfaces |
| `backgroundDark` | | Dark mode background |
| `backgroundElevated` | | Cards, modals |

### 1.2 Surface Colors
| Token | Value | Usage |
|-------|-------|-------|
| `surfaceLight` | | Light mode surfaces |
| `surfaceDark` | | Dark mode surfaces |
| `surfaceHover` | | Hover state |
| `surfacePressed` | | Pressed state |

### 1.3 Text Colors
| Token | Value | Usage |
|-------|-------|-------|
| `textPrimary` | | Main text |
| `textSecondary` | | Secondary text |
| `textMuted` | | Disabled/hint text |
| `textInverse` | | Text on dark backgrounds |
| `textLink` | | Clickable text |

### 1.4 Brand Colors
| Token | Value | Usage |
|-------|-------|-------|
| `primary` | | Primary actions |
| `primaryHover` | | Primary hover |
| `primaryPressed` | | Primary pressed |
| `secondary` | | Secondary actions |

### 1.5 Semantic Colors
| Token | Value | Usage |
|-------|-------|-------|
| `success` | | Success states |
| `warning` | | Warning states |
| `error` | | Error states |
| `info` | | Info states |

### 1.6 Border Colors
| Token | Value | Usage |
|-------|-------|-------|
| `borderDefault` | | Default borders |
| `borderSubtle` | | Subtle borders |
| `borderFocus` | | Focus ring |

---

## 2. TYPOGRAPHY

### 2.1 Font Family
```dart
static const String fontFamily = 'Inter'; // or your chosen font
// Load via: google_fonts package
```

### 2.2 Font Scale
| Token | Size | Weight | Line Height | Usage |
|-------|------|--------|-------------|-------|
| `displayLarge` | 32px | 700 | 1.2 | Hero text |
| `displayMedium` | 28px | 700 | 1.2 | Page titles |
| `headlineLarge` | 24px | 600 | 1.3 | Section headers |
| `headlineMedium` | 20px | 600 | 1.3 | Card headers |
| `titleLarge` | 18px | 600 | 1.4 | Large titles |
| `titleMedium` | 16px | 500 | 1.4 | Medium titles |
| `bodyLarge` | 16px | 400 | 1.5 | Main body text |
| `bodyMedium` | 14px | 400 | 1.5 | Default body |
| `bodySmall` | 12px | 400 | 1.5 | Small body |
| `labelLarge` | 14px | 500 | 1.4 | Button text |
| `labelMedium` | 12px | 500 | 1.4 | Small buttons |
| `caption` | 11px | 400 | 1.4 | Captions |

### 2.3 Custom Text Styles
| Token | Spec | Usage |
|-------|------|-------|
| | | |

---

## 3. SPACING SYSTEM

### 3.1 Base Unit
```dart
static const double baseUnit = 4.0; // All spacing is multiple of 4
```

### 3.2 Spacing Scale
| Token | Value | CSS Equivalent |
|-------|-------|----------------|
| `space0` | 0px | - |
| `space1` | 4px | 0.25rem |
| `space2` | 8px | 0.5rem |
| `space3` | 12px | 0.75rem |
| `space4` | 16px | 1rem |
| `space5` | 20px | 1.25rem |
| `space6` | 24px | 1.5rem |
| `space8` | 32px | 2rem |
| `space10` | 40px | 2.5rem |
| `space12` | 48px | 3rem |
| `space16` | 64px | 4rem |
| `space20` | 80px | 5rem |

### 3.3 Semantic Spacing
| Token | Value | Usage |
|-------|-------|-------|
| `paddingXs` | 4px | Minimal padding |
| `paddingSm` | 8px | Small padding |
| `paddingMd` | 16px | Medium padding |
| `paddingLg` | 24px | Large padding |
| `paddingXl` | 32px | Extra large padding |
| `gapSm` | 8px | Small gaps |
| `gapMd` | 16px | Medium gaps |
| `gapLg` | 24px | Large gaps |

---

## 4. LAYOUT DIMENSIONS

### 4.1 Breakpoints
| Token | Value | Description |
|-------|-------|-------------|
| `mobileMax` | 480px | Mobile devices |
| `tabletMin` | 481px | Tablet start |
| `tabletMax` | 1024px | Tablet end |
| `desktopMin` | 1025px | Desktop start |
| `wideMin` | 1440px | Wide screens |

### 4.2 Fixed Dimensions
| Token | Value | Usage |
|-------|-------|-------|
| `sidebarWidth` | | Main sidebar |
| `sidebarCollapsed` | | Collapsed sidebar |
| `headerHeight` | | Top header |
| `bottomBarHeight` | | Bottom navigation |
| `cardWidth` | | Standard card |

### 4.3 Tree/List Dimensions
| Token | Value | Usage |
|-------|-------|-------|
| `treeIndent` | 16px | Tree level indent |
| `listItemHeight` | 40px | Standard list item |
| `listItemHeightSm` | 32px | Compact list item |

---

## 5. BORDER RADIUS

### 5.1 Radius Scale
| Token | Value | Usage |
|-------|-------|-------|
| `radiusNone` | 0px | Sharp corners |
| `radiusSm` | 4px | Small elements |
| `radiusMd` | 8px | Default radius |
| `radiusLg` | 12px | Cards, dialogs |
| `radiusXl` | 16px | Large containers |
| `radiusFull` | 9999px | Circular/pill |

### 5.2 Semantic Radius
| Token | Value | Usage |
|-------|-------|-------|
| `radiusButton` | 8px | Buttons |
| `radiusInput` | 8px | Input fields |
| `radiusCard` | 12px | Cards |
| `radiusModal` | 16px | Modals/dialogs |
| `radiusAvatar` | 9999px | Avatars |

---

## 6. SHADOWS

### 6.1 Shadow Scale
| Token | Value | Usage |
|-------|-------|-------|
| `shadowNone` | none | No shadow |
| `shadowSm` | 0 1px 2px rgba(0,0,0,0.05) | Subtle elevation |
| `shadowMd` | 0 4px 6px rgba(0,0,0,0.1) | Default elevation |
| `shadowLg` | 0 10px 15px rgba(0,0,0,0.1) | High elevation |
| `shadowXl` | 0 25px 50px rgba(0,0,0,0.25) | Maximum elevation |

### 6.2 Semantic Shadows
| Token | Value | Usage |
|-------|-------|-------|
| `shadowCard` | | Card shadow |
| `shadowDropdown` | | Dropdown menus |
| `shadowModal` | | Modal overlay |
| `shadowSidebar` | | Sidebar shadow |

---

## 7. ANIMATIONS

### 7.1 Duration Scale
| Token | Value | Usage |
|-------|-------|-------|
| `durationInstant` | 0ms | No animation |
| `durationFast` | 150ms | Quick feedback |
| `durationNormal` | 200ms | Default transitions |
| `durationSlow` | 300ms | Emphasis |
| `durationSlowest` | 500ms | Major transitions |

### 7.2 Easing Curves
| Token | Value | Usage |
|-------|-------|-------|
| `easeDefault` | Curves.easeInOut | Default easing |
| `easeIn` | Curves.easeIn | Enter animations |
| `easeOut` | Curves.easeOut | Exit animations |
| `easeBounce` | Curves.bounceOut | Playful feedback |

---

## 8. ICONOGRAPHY

### 8.1 Icon Library
```dart
// Primary: Lucide Icons (recommended)
// Fallback: Material Icons
dependencies:
  lucide_icons: ^0.257.0
```

### 8.2 Icon Sizes
| Token | Value | Usage |
|-------|-------|-------|
| `iconXs` | 14px | Inline icons |
| `iconSm` | 16px | Small UI elements |
| `iconMd` | 20px | Default icons |
| `iconLg` | 24px | Large icons |
| `iconXl` | 32px | Feature icons |

### 8.3 Icon Color Mapping
| Context | Color Token |
|---------|-------------|
| Navigation active | `textPrimary` |
| Navigation inactive | `textSecondary` |
| Action buttons | `primary` |
| Destructive | `error` |

---

## 9. COMPONENT PATTERNS

### 9.1 Buttons
| Variant | Background | Text | Border |
|---------|------------|------|--------|
| Primary | `primary` | `textInverse` | none |
| Secondary | transparent | `primary` | `primary` |
| Ghost | transparent | `textSecondary` | none |
| Destructive | `error` | `textInverse` | none |

### 9.2 Inputs
| State | Background | Border | Text |
|-------|------------|--------|------|
| Default | `surfaceLight` | `borderDefault` | `textPrimary` |
| Focus | `surfaceLight` | `borderFocus` | `textPrimary` |
| Error | `surfaceLight` | `error` | `textPrimary` |
| Disabled | `backgroundSecondary` | `borderDefault` | `textMuted` |

### 9.3 Cards
```dart
Container(
  decoration: BoxDecoration(
    color: [surfaceColor],
    borderRadius: BorderRadius.circular([radiusCard]),
    border: Border.all(color: [borderColor]),
    boxShadow: [shadowCard],
  ),
  padding: EdgeInsets.all([paddingMd]),
)
```

---

## 10. DARK MODE

### 10.1 Color Mappings
| Token | Light Mode | Dark Mode |
|-------|------------|-----------|
| `background` | | |
| `surface` | | |
| `textPrimary` | | |
| `textSecondary` | | |

---

## 11. COMPONENT CATALOG

| Component | Path | Status |
|-----------|------|--------|
| | | |

---

## 12. VALIDATION RULES

1. ❌ NO hardcoded color values - use design system constants
2. ❌ NO hardcoded spacing - use spacing constants
3. ❌ NO inline TextStyle - use typography constants
4. ❌ NO magic numbers for dimensions - use layout constants
5. ✅ Reuse components from component catalog
6. ✅ Follow dark mode color mappings
'''
        
        elif technology.lower() in ["react", "vue", "svelte", "web"]:
            return '''# Design System - [Project Name]

## Metadata
- Version: 1.0
- Technology: {technology}
- Last Updated: [date]
- Status: draft

---

## 1. CSS VARIABLES / TOKENS

### Colors
```css
:root {
  /* Background */
  --color-bg-primary: ;
  --color-bg-secondary: ;
  --color-bg-elevated: ;
  
  /* Text */
  --color-text-primary: ;
  --color-text-secondary: ;
  --color-text-muted: ;
  
  /* Brand */
  --color-primary: ;
  --color-primary-hover: ;
  --color-secondary: ;
  
  /* Semantic */
  --color-success: ;
  --color-warning: ;
  --color-error: ;
  --color-info: ;
  
  /* Border */
  --color-border-default: ;
  --color-border-subtle: ;
}
```

### Typography
```css
:root {
  --font-family: 'Inter', sans-serif;
  
  --font-size-xs: 0.75rem;
  --font-size-sm: 0.875rem;
  --font-size-base: 1rem;
  --font-size-lg: 1.125rem;
  --font-size-xl: 1.25rem;
  --font-size-2xl: 1.5rem;
  --font-size-3xl: 2rem;
  
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --font-weight-bold: 700;
}
```

### Spacing
```css
:root {
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.25rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-10: 2.5rem;
  --space-12: 3rem;
}
```

### Border Radius
```css
:root {
  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
  --radius-xl: 1rem;
  --radius-full: 9999px;
}
```

### Shadows
```css
:root {
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
  --shadow-xl: 0 25px 50px rgba(0,0,0,0.25);
}
```

---

## 2. COMPONENT CATALOG

| Component | Path | Status |
|-----------|------|--------|
| | | |

---

## 3. VALIDATION RULES

1. ❌ NO hardcoded color values - use CSS variables
2. ❌ NO hardcoded spacing - use spacing variables
3. ❌ NO inline styles for typography - use typography classes
4. ✅ Reuse components from component catalog
'''
        
        else:
            # Generic template
            return f'''# Design System - [Project Name]

## Metadata
- Version: 1.0
- Technology: {technology}
- Last Updated: [date]
- Status: draft

---

## 1. COLOR PALETTE

### Primary Colors
| Name | Value | Usage |
|------|-------|-------|
| | | |

### Semantic Colors
| Name | Value | Usage |
|------|-------|-------|
| success | | |
| warning | | |
| error | | |
| info | | |

---

## 2. TYPOGRAPHY

### Font Family
- Primary: 
- Monospace: 

### Font Scale
| Name | Size | Weight | Usage |
|------|------|--------|-------|
| | | | |

---

## 3. SPACING

### Scale
| Token | Value |
|-------|-------|
| xs | 4px |
| sm | 8px |
| md | 16px |
| lg | 24px |
| xl | 32px |

---

## 4. COMPONENT CATALOG

| Component | Path | Status |
|-----------|------|--------|
| | | |

---

## 5. VALIDATION RULES

1. Use design system tokens for all visual properties
2. Reuse components from catalog
3. Follow established patterns
'''

    @staticmethod
    def analyze_design_document(content: str, technology: str) -> str:
        """Analyze a design system document and extract structured tokens"""
        return f"""Analyze this design system document and extract all design tokens.

TECHNOLOGY: {technology}

DOCUMENT CONTENT:
{content[:15000]}

EXTRACTION TASK:
Extract all design tokens into structured categories:

## 1. COLORS
For each color found:
- Token name (create if not specified)
- Hex value
- Usage/purpose

## 2. TYPOGRAPHY
For each text style:
- Token name
- Font family
- Font size (in px)
- Font weight
- Line height
- Usage

## 3. SPACING
For each spacing value:
- Token name
- Value (in px)
- Usage

## 4. LAYOUT DIMENSIONS
Fixed dimensions like sidebar width, header height, etc.

## 5. BORDER RADIUS
All radius values used

## 6. SHADOWS
All shadow definitions

## 7. ANIMATIONS
Duration and easing values

## 8. COMPONENTS
List of UI components described

## 9. DESIGN PRINCIPLES
Key design principles or rules mentioned

## 10. GAPS IDENTIFIED
What's missing from this design system that a {technology} project would need?

Output as structured markdown with exact values extracted.
Flag any ambiguities or missing information."""

    @staticmethod
    def summarize_design_system(full_content: str, technology: str) -> str:
        """Create a concise summary of design system for context loading"""
        return f"""Create a concise summary of this design system for use as AI context.

TECHNOLOGY: {technology}

FULL DESIGN SYSTEM:
{full_content[:20000]}

Create a summary that includes:

1. **Core Identity** (2-3 sentences about the visual style)

2. **Color Palette** (key colors with hex values)
   - Background colors
   - Primary/brand colors
   - Text colors
   - Semantic colors (success, error, etc.)

3. **Typography** (font family and key sizes)

4. **Key Dimensions** (important fixed values)

5. **Available Components** (list with file paths if known)

6. **Validation Rules** (what to check during implementation)

Keep it under 2000 words. Focus on actionable information for implementation.
Use exact values (hex codes, pixel values) not descriptions."""

    @staticmethod
    def design_sync_task(technology: str, design_system_path: str, 
                         implementation_paths: list, design_system_content: str) -> str:
        """Generate IDE task for design system sync analysis"""
        paths_str = "\n".join([f"   - {p}" for p in implementation_paths])
        return f"""# Design System Sync Analysis Task

## Objective
Analyze the implementation code and compare it against the design system document to identify:
1. **Additions**: Tokens in code but NOT in design system doc (need to add to doc)
2. **Missing**: Tokens in design system doc but NOT in code (need to implement)
3. **Conflicts**: Tokens with different values between doc and code

## Technology
{technology}

## Files to Analyze

### Design System Document
{design_system_path}

### Implementation Files
{paths_str}

## Design System Content (Reference)
```
{design_system_content[:15000]}
```

## Analysis Instructions

### Step 1: Scan Implementation Files
For each implementation file, extract:
- Color constants (hex values)
- Typography definitions (font family, sizes, weights)
- Spacing values (padding, margin, gap constants)
- Border radius values
- Shadow definitions
- Animation durations and curves
- Icon sizes
- Layout constants (widths, heights)

### Step 2: Compare with Design System
For each token found in code:
1. Check if it exists in the design system document
2. If exists, verify values match exactly
3. If not exists, mark as "addition"

For each token in design system:
1. Check if it's implemented in code
2. If not implemented, mark as "missing"

### Step 3: Output Results
Write results to: `.speky/design/sync_results.json`

Use this EXACT format:
```json
{{
  "analyzed_at": "ISO timestamp",
  "technology": "{technology}",
  "additions": [
    {{
      "category": "colors|typography|spacing|radius|shadows|animations|icons|layout",
      "name": "token name",
      "value": "actual value from code",
      "file": "relative file path",
      "line": line_number,
      "code_snippet": "the actual code line"
    }}
  ],
  "missing": [
    {{
      "category": "colors|typography|spacing|radius|shadows|animations|icons|layout",
      "name": "token name",
      "value": "value from design system doc",
      "doc_section": "section in design system where defined"
    }}
  ],
  "conflicts": [
    {{
      "category": "colors|typography|spacing|radius|shadows|animations|icons|layout",
      "name": "token name",
      "doc_value": "value in design system doc",
      "code_value": "value in implementation",
      "file": "relative file path",
      "line": line_number,
      "severity": "high|medium|low"
    }}
  ],
  "summary": {{
    "total_additions": number,
    "total_missing": number,
    "total_conflicts": number,
    "files_analyzed": number
  }}
}}
```

## Important Notes
- Be precise with values (exact hex codes, exact pixel values)
- Include file paths relative to project root
- Include line numbers for easy navigation
- For conflicts, severity is:
  - high: core colors, primary dimensions
  - medium: secondary colors, typography
  - low: minor spacing differences

## When Complete
After writing sync_results.json, inform the developer:
"Design sync analysis complete. Run: speky design sync --apply"
"""

    @staticmethod
    def design_sync_apply(additions: list, missing: list, conflicts: list, 
                          design_system_content: str, technology: str) -> str:
        """Generate updated design system content with sync changes"""
        additions_str = json.dumps(additions[:20], indent=2) if additions else "[]"
        conflicts_str = json.dumps(conflicts[:10], indent=2) if conflicts else "[]"
        
        return f"""Update this design system document to incorporate the following changes.

## TECHNOLOGY
{technology}

## CURRENT DESIGN SYSTEM
{design_system_content}

## ADDITIONS TO INCORPORATE
These tokens exist in code but are missing from the design system. Add them to the appropriate sections:
{additions_str}

## CONFLICTS TO RESOLVE (use code values)
These tokens have different values. Update the design system to match the code:
{conflicts_str}

## INSTRUCTIONS
1. Add each addition to the appropriate section of the design system
2. Update conflicting values to match the code values
3. Maintain the existing document structure and formatting
4. Add code snippets where appropriate
5. Keep the document clean and well-organized

## OUTPUT
Return the COMPLETE updated design system document.
Do not truncate or summarize - output the full document with all changes incorporated."""


# =============================================================================
# AI CLIENT (Agnostic wrapper)
# =============================================================================

class AIClient:
    """Wrapper around the LLM router with JSON extraction.

    The model is a "provider/model" ref (e.g. openrouter/moonshotai/kimi-k2,
    claude-code/sonnet) chosen in ~/.speky/models.yaml or via `speky config --model`.
    See speky_llm.py for providers, retries and fallbacks.
    """

    def __init__(self, config: dict = None, project_root: Path = None):
        self.config = dict(config or DEFAULT_CONFIG)
        self.router = LLMRouter(project_root=project_root,
                                legacy_model=self.config.get("model"),
                                legacy_default=DEFAULT_CONFIG["model"],
                                timeout=self.config.get("api_timeout", 120),
                                log=Console.warning)
        self.model_ref = self.router.model_ref
        self.provider, self.model = None, None
        if self.model_ref:
            try:
                self.provider, self.model = self.router.resolve(self.model_ref)
            except LLMError as e:
                Console.error(str(e))

    def query(self, prompt: str, system: str = None, max_tokens: int = None, use_streaming: bool = None,
              expect_json: bool = False) -> Optional[str]:
        """Query the configured model (falling back through `fallbacks`) and return the text."""
        if system is None:
            system = "You are an expert AI assistant. Be concise and actionable."
        tokens = max_tokens or self.config["max_tokens"]
        # Auto-enable streaming for large token requests (>8192) to avoid timeouts
        if use_streaming is None:
            use_streaming = tokens > 8192
        try:
            return self.router.complete(prompt, system, tokens, self.config["temperature"],
                                        stream=use_streaming, expect_json=expect_json)
        except LLMError as e:
            Console.error(f"AI request failed: {e}")
            return None

    def query_json(self, prompt: str, max_retries: int = 3) -> Optional[dict]:
        """Query AI and parse JSON response with retry"""
        for attempt in range(max_retries):
            response = self.query(prompt, expect_json=True)
            if not response:
                return None
            
            # Try to extract JSON from response
            json_data = self._extract_json(response)
            if json_data:
                return json_data
            
            if attempt < max_retries - 1:
                Console.warning(f"JSON parse failed (attempt {attempt + 1}), retrying...")
                # Ask AI to fix the JSON
                fix_prompt = (f"ORIGINAL REQUEST:\n{prompt}\n\n"
                              f"Your previous response to it was not valid JSON. Answer the original "
                              f"request again, outputting ONLY valid JSON (no markdown, no other text). "
                              f"Previous response:\n\n{response}")
                response = self.query(fix_prompt, expect_json=True)
                json_data = self._extract_json(response)
                if json_data:
                    return json_data
        
        Console.error("Failed to get valid JSON from AI")
        return None

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from text (handles markdown code blocks)"""
        if not text:
            return None
        
        # Try direct parse
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON in code blocks
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'\{[\s\S]*\}'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue
        
        return None


# =============================================================================
# IDE INTEGRATION
# =============================================================================

class IDEIntegration:
    """Handles integration with various IDEs"""
    
    # Maximum characters per rule file for multi-file IDEs
    MAX_CHARS_PER_FILE = 8000
    
    # IDE configurations: maps IDE name to its rules location
    # "file" type: single file in project root
    # "folder" type: folder containing multiple rule files (for size-limited IDEs)
    #   - multi_file: True = split rules into semantic categories
    #   - files: list of rule file definitions with categories
    IDE_CONFIGS = {
        "windsurf": {"type": "file", "path": ".windsurfrules"},
        "cursor": {"type": "file", "path": ".cursorrules"}, 
        "claude-code": {"type": "file", "path": "CLAUDE.md"},
        "vscode": {"type": "file", "path": ".github/copilot-instructions.md"},  # read by Copilot in VS Code
        "antigravity": {
            "type": "folder", 
            "path": ".agent/rules",
            "multi_file": True,
            "files": [
                {"name": "01-speky-core.md", "category": "core"},
                {"name": "02-speky-structure.md", "category": "structure"},
                {"name": "03-speky-context.md", "category": "context"},
                {"name": "99-speky-task.md", "category": "task"},  # Dynamic, only during implement
            ]
        },
    }
    
    # Legacy mapping for backward compatibility
    RULES_FILES = {
        "windsurf": ".windsurfrules",
        "cursor": ".cursorrules", 
        "claude-code": "CLAUDE.md",
        "vscode": ".github/copilot-instructions.md",
        "antigravity": ".agent/rules/01-speky-core.md",
    }
    
    def __init__(self, project_root: Path, ide: str = "windsurf", enabled_ides: List[str] = None):
        self.project_root = project_root
        self.ide = ide  # Primary IDE (legacy)
        self.enabled_ides = enabled_ides or [ide]  # All enabled IDEs
        self.implementation_mode = False  # True during speky implement
        self.implementation_context = None  # Comprehensive task context during implement
    
    def set_implementation_mode(self, enabled: bool, task_context: dict = None):
        """Enable/disable implementation mode for focused IDE context
        
        During implementation mode:
        - IDE rules are condensed to essentials only (~2K chars)
        - Task context is comprehensive with all related info
        - Maximizes context window for actual code
        
        Args:
            enabled: True to enable implementation mode
            task_context: Dict with comprehensive task info (when enabling)
        """
        self.implementation_mode = enabled
        self.implementation_context = task_context if enabled else None
    
    def update_context_file(self, content: str, active_task: str = "", target_ide: str = None):
        """Update the IDE-specific context file with SPEKY rules
        
        Args:
            content: Product context content
            active_task: Current active task description
            target_ide: Specific IDE to update (None = use self.ide for backward compat)
        """
        ide_to_update = target_ide or self.ide
        ide_config = self.IDE_CONFIGS.get(ide_to_update)
        
        if not ide_config:
            Console.warning(f"Unknown IDE: {ide_to_update}")
            return
        
        full_content = self.build_rules_content(ide_to_update, content, active_task)
        
        # Handle file vs folder-based IDEs
        if ide_config["type"] == "folder":
            self._write_folder_rules(ide_to_update, ide_config, full_content, active_task)
        else:
            self._write_file_rules(ide_config["path"], full_content)
        
        Console.success(f"Updated {ide_config['path']}")
    
    def update_all_enabled_ides(self, content: str, active_task: str = ""):
        """Update rules for all enabled IDEs"""
        for ide in self.enabled_ides:
            self.update_context_file(content, active_task, target_ide=ide)
    
    def build_rules_content(self, ide_name: str, content: str, active_task: str = "") -> str:
        """The SPEKY-managed text for an IDE rules file (what goes between the markers)."""
        return (self._get_ide_header(ide_name) + self._get_speky_rules(active_task)
                + "\n\n---\n\n## Project Context\n\n" + content)

    # Single-file rules (CLAUDE.md, .cursorrules, ...) are shared with the user: SPEKY owns only
    # the text between these markers and leaves everything else in the file alone.
    BLOCK_BEGIN = "<!-- BEGIN SPEKY MANAGED BLOCK: text between these markers is rewritten by speky -->"
    BLOCK_END = "<!-- END SPEKY MANAGED BLOCK -->"
    # Text of the old "USER RULES" template, used to find what users added to pre-marker files
    _LEGACY_USER_RULES_TEMPLATE = [
        "Add your custom IDE rules below this line. They will be preserved when SPEKY updates.",
        "Example:", "- Always use TypeScript strict mode", "- Prefer async/await over promises",
        "- Use descriptive variable names",
    ]

    @classmethod
    def extract_managed_block(cls, text: str) -> Optional[str]:
        """Content between the SPEKY markers, or None when the file has no managed block."""
        start, end = text.find(cls.BLOCK_BEGIN), text.find(cls.BLOCK_END)
        if start == -1 or end == -1 or end < start:
            return None
        return text[start + len(cls.BLOCK_BEGIN):end].strip("\n")

    @staticmethod
    def _is_legacy_speky_file(text: str) -> bool:
        """A rules file written by SPEKY before managed blocks existed (it owned the whole file)."""
        return "# SPEKY Project Rules" in text and "# USER RULES" in text

    @classmethod
    def _legacy_user_rules(cls, text: str) -> str:
        """Rules a user added under the old '# USER RULES' heading, minus the template lines."""
        start = text.find("# USER RULES")
        end = text.find("\n---\n\n## Project Context", start)
        section = text[start + len("# USER RULES"):end if end != -1 else len(text)]
        lines = [l for l in section.splitlines() if l.strip() not in cls._LEGACY_USER_RULES_TEMPLATE]
        return "\n".join(lines).strip()

    def _write_file_rules(self, rules_path: str, content: str):
        """Write SPEKY's rules into a managed block, preserving everything else in the file.

        - No file: create it with just the block.
        - File with a block: replace the block only.
        - File SPEKY wrote before blocks existed: back it up under .speky/backups/, keep any rules
          the user added under "USER RULES", and replace the rest with the block.
        - Any other file (the user's own CLAUDE.md, etc.): append the block, change nothing else.
        """
        filepath = self.project_root / rules_path
        filepath.parent.mkdir(parents=True, exist_ok=True)
        block = f"{self.BLOCK_BEGIN}\n{content.strip(chr(10))}\n{self.BLOCK_END}\n"
        existing = filepath.read_text() if filepath.exists() else ""

        if not existing.strip():
            new_text = block
        elif self.extract_managed_block(existing) is not None:
            start = existing.find(self.BLOCK_BEGIN)
            end = existing.find(self.BLOCK_END) + len(self.BLOCK_END)
            new_text = existing[:start] + block.rstrip("\n") + existing[end:]
        elif self._is_legacy_speky_file(existing):
            backup_dir = self.project_root / SPEKY_DIR / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = backup_dir / f"{filepath.name.lstrip('.')}.{stamp}.bak"
            backup.write_text(existing)
            user_rules = self._legacy_user_rules(existing)
            new_text = (f"# Project rules\n\n{user_rules}\n\n" if user_rules else "") + block
            Console.log(f"Moved {rules_path} to a SPEKY managed block (previous file saved to "
                        f"{backup.relative_to(self.project_root)})")
        else:
            new_text = existing.rstrip("\n") + "\n\n" + block

        with open(filepath, 'w') as f:
            f.write(new_text)
    
    def _write_folder_rules(self, ide_name: str, ide_config: dict, content: str, active_task: str = ""):
        """Write rules to a folder-based IDE (like Antigravity)
        
        For multi-file IDEs, splits content into semantic categories to stay under size limits.
        """
        folder_path = self.project_root / ide_config["path"]
        folder_path.mkdir(parents=True, exist_ok=True)
        
        # Check if this is a multi-file IDE
        if ide_config.get("multi_file"):
            self._write_multi_file_rules(folder_path, ide_config, active_task)
        else:
            # Legacy: single file in folder
            main_file = folder_path / ide_config.get("main_file", "rules.md")
            with open(main_file, 'w') as f:
                f.write(content)
    
    def _write_multi_file_rules(self, folder_path: Path, ide_config: dict, active_task: str = ""):
        """Write rules split across multiple files for size-limited IDEs
        
        - Writes all category files (core, structure, context)
        - Task file only when active_task is set
        """
        
        # Full SPEKY rules for all modes
        rules_by_category = self._get_speky_rules_split()
        
        for file_def in ide_config.get("files", []):
            filename = file_def["name"]
            category = file_def["category"]
            
            # Skip task file if no active task
            if category == "task" and not active_task:
                # Remove stale task file if it exists
                task_file = folder_path / filename
                if task_file.exists():
                    task_file.unlink()
                continue
            
            # Get content for this category
            if category == "task":
                file_content = self._get_task_context_content(active_task)
            else:
                file_content = rules_by_category.get(category, "")
            
            if not file_content:
                continue
            
            # Add header
            header = f"# SPEKY Rules ({category.title()}) - Auto-generated\n"
            header += f"# Do not edit manually - regenerated on each SPEKY command\n"
            header += f"# Size: {len(file_content)} chars (max: {self.MAX_CHARS_PER_FILE})\n\n"
            
            full_content = header + file_content
            
            # Write file
            filepath = folder_path / filename
            with open(filepath, 'w') as f:
                f.write(full_content)
    
    def _write_implementation_mode_files(self, folder_path: Path, ide_config: dict):
        """Write focused implementation mode files for multi-file IDEs
        
        Creates:
        - 01-speky-essentials.md: Minimal essential rules (~2K chars)
        - 99-speky-task.md: Comprehensive task context with all related info
        
        Removes other rule files to maximize context window.
        """
        # Remove existing rule files (except essentials and task)
        for file_def in ide_config.get("files", []):
            filename = file_def["name"]
            if filename not in ["01-speky-essentials.md", "99-speky-task.md"]:
                filepath = folder_path / filename
                if filepath.exists():
                    filepath.unlink()
        
        # Also remove old core/structure/context files
        for old_file in ["01-speky-core.md", "02-speky-structure.md", "03-speky-context.md"]:
            filepath = folder_path / old_file
            if filepath.exists():
                filepath.unlink()
        
        # Write essentials file
        essentials_content = self._get_implementation_essentials()
        essentials_header = "# SPEKY Implementation Essentials - Auto-generated\n"
        essentials_header += "# Focused rules for implementation phase\n"
        essentials_header += f"# Size: {len(essentials_content)} chars\n\n"
        
        essentials_file = folder_path / "01-speky-essentials.md"
        with open(essentials_file, 'w') as f:
            f.write(essentials_header + essentials_content)
        
        # Write comprehensive task context
        task_content = self._get_comprehensive_task_context()
        task_header = "# Implementation Context - Auto-generated\n"
        task_header += "# PRIORITY: This is your implementation focus\n"
        task_header += f"# Size: {len(task_content)} chars\n\n"
        
        task_file = folder_path / "99-speky-task.md"
        with open(task_file, 'w') as f:
            f.write(task_header + task_content)
    
    def _get_task_context_content(self, active_task: str) -> str:
        """Generate content for the active task context file"""
        if not active_task:
            return ""
        
        return f"""# 🎯 Current Active Task

**PRIORITY: Focus on this task. Other rules provide context.**

{active_task}

---

## Quick Reference

When implementing this task:
1. Follow the spec/story requirements exactly
2. Check tech_decisions.md before choosing packages
3. Check design_system.md before implementing UI
4. Do NOT create completion marker files
5. Tell developer to run `speky complete <id>` when done
"""
    
    def _get_implementation_essentials(self) -> str:
        """Minimal essential SPEKY rules for implementation phase (~2K chars)
        
        During implementation, the AI needs maximum context for code, not SPEKY commands.
        This provides only the critical rules needed while coding.
        """
        return """# SPEKY Implementation Essentials

**You are in IMPLEMENTATION MODE.** Focus on coding the current task.

## 🎯 Your Mission
Implement the spec/story in the task context file. Stay focused on the requirements.

## ⚠️ Critical Rules

### 1. Follow Tech & Architecture Decisions
Check `.speky/context/tech_decisions.md` BEFORE choosing any package/framework.
If it exists, you MUST use ONLY the packages listed there. No alternatives.

**This file also contains "Important Architecture Decisions"** - patterns, conventions, 
and design decisions that ALL implementations MUST follow. Check this section before
implementing any significant logic.

### 2. Follow Design System
If implementing UI, check `.speky/context/design_system.md`:
- Use EXACT color values (e.g., `Color(0xFF6D5AE6)`)
- Use design system spacing constants
- Use design system typography styles
- Match Hi-Fi designs PIXEL-PERFECT if they exist

### 3. Scope Enforcement
- **IN SCOPE**: Implement everything in spec's requirements and acceptance criteria
- **OUT OF SCOPE**: Do NOT implement items in "Out of Scope" section
- If asked for out-of-scope items, tell developer to create a new spec

### 4. Code Quality
- Follow existing code patterns in the codebase
- Maintain consistent naming conventions
- Add appropriate error handling
- Keep functions focused and testable

### 5. Testing & TDD
If this is a TDD workflow (`speky implement --tdd`):
- **RED Phase**: Write failing tests first from acceptance criteria
- **GREEN Phase**: Implement minimum code to pass tests
- **REFACTOR Phase**: Clean up while keeping tests green
- Run tests frequently: `speky test run --spec <id>`

Available testing commands:
- `speky test gen <id>` - Generate tests for spec
- `speky test run` - Run all tests
- `speky test coverage` - Show coverage
- `speky complete <id> --test` - Run tests before marking complete

### 6. File Organization
- **NEVER** create files in project root (except README.md)
- **NEVER** create `*_SPEC.md`, `IMPLEMENTATION_COMPLETE.md`, or analysis files
- Use `.speky/temp/` for any temporary files

### 7. When Done
Tell the developer: "Implementation complete. Run `speky complete <id>` to verify."
Do NOT create completion marker files.

---

**Now focus on the task context below. The spec/story details are your implementation guide.**
"""
    
    def _get_comprehensive_task_context(self) -> str:
        """Generate comprehensive task context for implementation mode
        
        Includes all relevant context from implementation_context dict:
        - Task summary and item details
        - Full spec/story content
        - Implementation plan
        - Tech decisions
        - Design system
        - Related specs
        - Affected files preview
        - Epic context
        """
        if not self.implementation_context:
            return "No implementation context available."
        
        ctx = self.implementation_context
        sections = []
        
        # Task Header
        item_id = ctx.get("item_id", "Unknown")
        item_type = ctx.get("item_type", "spec")
        item_title = ctx.get("item_title", item_id)
        
        sections.append(f"""# 🎯 IMPLEMENT: {item_title}

**ID**: {item_id}
**Type**: {item_type.title()}
**Path**: `.speky/{'stories' if item_type == 'story' else 'specs'}/{ctx.get('item_dir_name', item_id)}/`
""")
        
        # Phase context if applicable
        if ctx.get("phase_name"):
            sections.append(f"""## 📅 Phase Context
**Phase**: {ctx.get('phase_name')} ({ctx.get('phase_id', 'unknown')})
Stay within phase scope. Check phase excludes before implementing.
""")
        
        # Spec/Story Content (most important)
        if ctx.get("spec_content"):
            sections.append(f"""## 📋 Specification

{ctx.get('spec_content')}
""")
        
        if ctx.get("story_content"):
            sections.append(f"""## 📋 Story

{ctx.get('story_content')}
""")
        
        # Implementation Plan
        if ctx.get("plan_content"):
            sections.append(f"""## 📝 Implementation Plan

{ctx.get('plan_content')}
""")
        
        # Tech Decisions (critical for package choices)
        if ctx.get("tech_decisions"):
            sections.append(f"""## 🔧 Tech Decisions (MUST FOLLOW)

{ctx.get('tech_decisions')}
""")
        
        # Design System (critical for UI)
        if ctx.get("design_system"):
            sections.append(f"""## 🎨 Design System (MUST FOLLOW)

{ctx.get('design_system')}
""")
        
        # Related Specs
        if ctx.get("related_specs"):
            sections.append(f"""## 🔗 Related Specs

{ctx.get('related_specs')}
""")
        
        # Epic Context
        if ctx.get("epic_context"):
            sections.append(f"""## 📦 Epic Context

{ctx.get('epic_context')}
""")
        
        # Affected Files Preview
        if ctx.get("affected_files"):
            sections.append(f"""## 📁 Affected Files

{ctx.get('affected_files')}
""")
        
        # Context summary for stories
        if ctx.get("context_summary"):
            sections.append(f"""## 📊 Context Summary

{ctx.get('context_summary')}
""")
        
        return "\n".join(sections)
    
    def _get_speky_rules_split(self) -> dict:
        """Generate SPEKY rules split into semantic categories
        
        Returns dict mapping category name to content string.
        Each category content is designed to stay under MAX_CHARS_PER_FILE.
        """
        return {
            "core": self._get_core_rules(),
            "structure": self._get_structure_rules(),
            "context": self._get_context_rules(),
        }
    
    def _get_core_rules(self) -> str:
        """Core workflow enforcement rules (~7800 chars)"""
        return """# SPEKY Project Rules

This project uses **SPEKY** (AI-Assisted Scalable Engineering Framework) for spec-driven development.
**You MUST follow SPEKY workflow. Do NOT bypass these processes.**

## CRITICAL: SPEKY Workflow Enforcement

### 🚨 MANDATORY: Follow SPEKY Process

1. **Before implementing ANY new feature:**
   - Check if a spec exists in `.speky/specs/`
   - If NO spec exists, tell the developer: "This feature needs a spec first. Run: `speky spec \\"Feature name\\"`"
   - Do NOT implement features without a spec

2. **Before making significant changes:**
   - Check the relevant spec in `.speky/specs/*/spec.md`
   - Verify changes align with the spec's scope
   - If changes are out-of-scope, inform the developer

3. **When asked to create a new feature:**
   - Do NOT create your own spec files
   - Tell the developer: "Let's create a proper spec first. Run: `speky spec \\"Feature name\\"`"
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
      speky spec \\"User authentication\\"
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

### 🔧 CRITICAL: Tech & Architecture Decisions

**BEFORE suggesting or using ANY package/framework:**
1. Check if `.speky/context/tech_decisions.md` exists
2. If it exists, you MUST use ONLY the packages listed there
3. NEVER suggest alternatives to decided technologies
4. If a spec uses wrong packages, flag it for correction

**BEFORE implementing significant logic:**
1. Check the "Important Architecture Decisions" section in `tech_decisions.md`
2. Follow documented patterns, conventions, and design decisions
3. Avoid documented anti-patterns
4. If making architectural changes, update this section first

This file contains:
- **Tech Stack**: Authoritative package/framework choices
- **Important Architecture Decisions**: Patterns, conventions, design decisions
- **Anti-Patterns to Avoid**: What NOT to do

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
"""
    
    def _get_structure_rules(self) -> str:
        """Project structure, stories, and file organization (~7800 chars)"""
        return """# SPEKY Project Structure

## 📋 Directory Layout

```
.speky/
├── specs/                    # Feature specifications
│   ├── 001-auth/
│   │   ├── spec.md           # Read this for requirements
│   │   ├── plan.md           # Read this for implementation steps
│   │   └── status.json       # Priority, dependencies, status
│   └── 002-api/
│       └── status.json       # May have dependencies: ["001"]
├── epics/                    # Story grouping (optional)
│   └── E001-epic-name/
│       ├── manifest.yaml     # Epic definition, story list
│       ├── technical_spec.md # Shared technical decisions
│       └── summary.md        # Executive overview
├── stories/                  # Bugs, enhancements, tech debt
│   └── F001-story-name/
│       ├── story.md          # Story definition
│       └── status.json       # related_specs, related_epic, affected_files
├── imports/                  # External docs and POC imports
│   ├── initial_research/     # From speky init
│   ├── phase-mvp/            # From speky import
│   └── poc_import/           # From speky poc-import
├── backlog/                  # Deferred validation items
├── phases/                   # Phase coordination (if using phases)
│   ├── roadmap.yaml          # Master phase timeline
│   └── phase-1/
│       ├── manifest.yaml     # Phase definition
│       └── implementation.md # AI guidance
├── recommendations/          # AI agent recommendations for SPEKY
├── roadmap.md                # Implementation order (from: speky sequence --export)
└── context/
    ├── context.json          # Project metadata
    ├── product.md            # Product profile
    ├── tech_decisions.md     # AUTHORITATIVE tech choices (if exists)
    └── IDE_CONTEXT.md        # Complete AI agent guide
```

## Understanding Stories vs Specs

### 🎯 Two Types of Work Items

| Type | ID Format | Location | Scope | Duration |
|------|-----------|----------|-------|----------|
| **Spec** | `001`, `002`, `003` | `.speky/specs/001-name/` | Large feature | 1-3 weeks |
| **Story** | `F001`, `B001`, `T001` | `.speky/stories/F001-name/` | Small task | 30 min - 2 days |

### 📝 Story ID Prefixes
- **F001, F002...** = Feature stories (enhancements, integrations)
- **B001, B002...** = Bug stories (bug fixes)
- **T001, T002...** = Tech debt stories (refactoring, cleanup)

### ⚠️ CRITICAL: When Developer Says "speky implement F001"

**❌ WRONG:** "I don't see an F001 spec. The specs are numbered 001-038."

**✅ CORRECT:** "F001 is a story, not a spec. Let me check the story details."
[Read .speky/stories/F001-*/story.md]
"Found Story F001: [title]. I'll implement it now based on the story requirements."

### 🔄 Story Workflow Example

```
Developer: "speky implement F001"

You: "F001 is a story. Let me read the details..."
     [Read .speky/stories/F001-*/story.md]
     
     "Found Story F001: Connect Spaces to Sidebar Navigation
     
     This story requires:
     - Add navigation item to sidebar
     - Connect to SpacesProvider
     - Handle routing
     
     I'll implement this now based on the story requirements."
     
     [Implement based on story.md acceptance criteria]
```

## 📝 Creating Stories Directly (IDE/Manual)

You CAN create stories directly without using `speky story` command:

### Required Folder Structure
```
.speky/stories/{ID}-{slug}/
├── story.md       # REQUIRED - Story definition
└── status.json    # REQUIRED - Story metadata
```

### Folder Naming Convention
- **F001-feature-name/** - Feature story
- **B001-bug-name/** - Bug fix story
- **T001-tech-debt/** - Tech debt story
- **E001-enhancement/** - Enhancement story
- **S001-spike-name/** - Spike/research story

### story.md Template
```markdown
# [Story Title]

## Description
[What needs to be done and why]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Context
- **Related Spec**: [spec ID if applicable]
- **Dependencies**: [other story/spec IDs if any]
- **Affected Files**: [list of files to modify]

## Tasks
1. Task 1
2. Task 2
3. Task 3

## Notes
[Implementation hints, edge cases, testing guidance]
```

### status.json Template
```json
{
  "id": "F001",
  "title": "Story Title",
  "type": "feature",
  "status": "draft",
  "created": "2024-01-01T00:00:00",
  "related_specs": [],
  "dependencies": [],
  "affected_files": []
}
```

### After Creating Story
1. **Adopt into SPEKY**: `speky adopt F001`
2. **Plan (optional)**: `speky plan F001`
3. **Implement**: `speky implement F001` or implement directly
4. **Complete**: `speky complete F001`

### Story Workflow Options

**Quick Path (Simple Stories):**
```
Create story.md + status.json → speky adopt F001 → Implement → speky complete F001
```

**Full Path (Complex Stories):**
```
Create story.md + status.json → speky adopt F001 → speky plan F001 → speky implement F001 → speky complete F001
```

## CRITICAL: File Organization Rules

### ✅ DO: Keep files organized
- **Specs**: `.speky/specs/*/spec.md` (created by SPEKY only)
- **Plans**: `.speky/specs/*/plan.md` (created by SPEKY only)
- **Stories**: `.speky/stories/*/story.md`
- **Context**: `.speky/context/context.json`
- **Code**: `backend/`, `frontend/`, `src/`, `lib/` (project structure)

### ❌ DON'T: Create files in root directory
- **NEVER** create `*_SPEC.md` files in root
- **NEVER** create `IMPLEMENTATION_COMPLETE.md` in root
- **NEVER** create temporary markdown files in root
- **NEVER** create analysis or summary files in root
- **NEVER** create documentation files in root (except README.md)

### Temporary Files
- If you need temporary files: use `.speky/temp/` directory
- Clean up temporary files after use
- Never commit `.speky/temp/` to git
"""
    
    def _get_context_rules(self) -> str:
        """Design system, commands reference, specs, recommendations (~7800 chars)"""
        return """# SPEKY Context & Commands

## 🎨 CRITICAL: Design System

**BEFORE implementing ANY UI:**
1. Check if `.speky/context/design_system.md` exists
2. If it exists, you MUST follow the design system for:
   - Colors (use EXACT hex values, e.g., `Color(0xFF6D5AE6)`)
   - Typography (font family, sizes, weights from design system classes)
   - Spacing (use design system constants, e.g., `Spacing.md`)
   - Border radius values (use design system constants)
   - Shadows and elevation (use design system shadow definitions)
   - Animation durations and curves
3. Check `.speky/design/manifest.json` for linked Hi-Fi designs
4. If Hi-Fi designs exist for the spec, match them PIXEL-PERFECT

**Design System Files:**
```
.speky/design/
├── config.yaml               # Technology and settings
├── manifest.json             # All designs, links, resolved conflicts
├── system/source/            # Design system documents (AUTHORITATIVE)
│   └── design_system.md      # Complete token definitions
├── hifi/source/              # Hi-Fi designs (pixel-perfect)
│   └── *.analysis.md         # AI-extracted tokens from images
├── lofi/source/              # Lo-Fi wireframes (guidance)
└── icons/source/             # Icon assets

.speky/context/design_system.md  # AI summary for quick reference
```

**When implementing UI:**
- Use design system colors, NEVER arbitrary values
- Use design system spacing constants (xs, sm, md, lg, xl)
- Use design system typography styles (navButton, treeItem, etc.)
- Use design system radius values (button, card, input)
- Use design system shadows (sidebarEmbossed, cardSubtle, etc.)
- If conflict between spec and design system, follow design system

**Reusing Implemented Components:**
- Check the Implementation Checklist in the design system doc
- Look for existing widgets before creating new ones
- Reference file paths in the checklist for component locations
- Follow established patterns from existing components

**Design System Commands:**
```bash
speky design status    # Check design system coverage
speky design validate  # Detect conflicts with Hi-Fi
speky design resolve   # Resolve conflicts with AI
```

## 🔧 SPEKY Commands Reference

Tell the developer to use these commands:

**Core Workflow:**
- `speky init "idea"` - Initialize project with tech stack discussion
- `speky spec "name"` - Create a new feature spec (research-aware)
- `speky plan 001` - Generate implementation plan (validates dependencies)
- `speky implement 001` - Start implementation (validates dependencies, updates this file)
- `speky complete 001` - Verify and mark complete with drift detection
- `speky commit 001` - Commit with comprehensive message
- `speky status` - Check project progress

**Spec Sequencing & Dependencies:**
- `speky sequence` - Show implementation roadmap with dependencies
- `speky sequence --export` - Export roadmap to `.speky/roadmap.md`
- `speky infer-deps` - AI-infer dependencies for all specs
- `speky infer-deps 003` - AI-infer dependencies for specific spec

**External Knowledge Import:**
- `speky import --phase mvp` - Import docs with interactive review
- `speky import-status` - Show all imports and derived specs
- `speky reconcile mvp` - Reconcile code with imported docs
- `speky poc-import` - Import features from POC codebase

**Spec Quality & Validation:**
- `speky validate-spec 001` - Validate spec quality (interactive)
- `speky validate-spec 001 --quick` - Quick validation (non-interactive)
- `speky adopt 001` - Adopt IDE-created spec into SPEKY tracking
- `speky backlog` - Review deferred validation items

**Phase Management (Multi-Spec Coordination):**
- `speky phases suggest` - AI suggests phases from existing specs
- `speky phases list` - List all phases
- `speky phases show phase-1` - Show phase details
- `speky phases status` - Show overall phase progress
- `speky phases start phase-1` - Start a phase
- `speky phases guide phase-1 --for-ai` - Generate AI implementation guide
- `speky context --phase phase-1` - Generate AI context for phase

**Epic Management (Story Grouping):**
- `speky epic "Epic Name" --spec 006` - Create epic linked to spec
- `speky epic E001` - Show epic details
- `speky epic E001 --add F005` - Add story to epic
- `speky epic E001 --remove F005` - Remove story from epic
- `speky epics` - List all epics with status

**Stories:**
- `speky story "title"` - Create feature story
- `speky story --type bug "title"` - Create bug story
- `speky story "title" --epic E001` - Create story in epic
- `speky story "title" --spec 001` - Create story linked to spec

**Testing & TDD:**
- `speky implement 001 --tdd` - Start TDD workflow (tests first)
- `speky test init` - Initialize testing infrastructure
- `speky test gen 001` - Generate tests for spec
- `speky test run` - Run all tests
- `speky test coverage` - Show test coverage
- `speky test tdd-red 001` - Generate failing tests (Red phase)
- `speky test tdd-green 001` - Verify tests pass (Green phase)
- `speky complete 001 --test` - Run tests before complete

**Configuration:**
- `speky config --ides` - Show/manage enabled IDEs
- `speky decisions` - View/manage tech decisions
- `speky validate-story F001` - Validate story quality

**Maintenance:**
- `speky sync` - Sync codebase context
- `speky review 001` - Check for spec-code drift
- `speky cleanup` - Remove any clutter files

## 🧪 TDD Workflow

**When developer says `speky implement 001 --tdd`:**

### Red-Green-Refactor Cycle:
1. **RED**: `speky test tdd-red 001` - Generate failing tests from acceptance criteria
2. **GREEN**: Implement minimum code to pass tests
3. **REFACTOR**: Clean up while keeping tests green

### TDD Example:
```
Developer: "speky implement 001 --tdd"

You: "Starting TDD workflow.
1. Running: speky test tdd-red 001
2. Tests generated - they should fail
3. Implementing minimum code to pass
4. Refactoring while keeping tests green"
```

## Creating Specs Directly (Advanced)

If the developer asks you to create a spec directly, you MAY create it:

### Step 1: Create Directory
`.speky/specs/NNN-feature-name/` (NNN = next available number)

### Step 2: Create spec.md with this template:
```markdown
# Feature Name

## Overview
2-3 sentences explaining what this feature does and why.

## MVP Scope
Explicit list of what IS included in this MVP version.

## User Stories
1-2 core user stories only:
- As a [user], I want [action], so that [benefit]
  - Acceptance: [specific, testable criteria]

## Requirements

### Functional Requirements (MVP only)
- Essential behaviors only
- Remove nice-to-haves

### Non-Functional Requirements
- Only if critical

## Out of Scope
Explicitly list what is NOT included (prevents scope creep).

## Open Questions
- Specific decisions needed before implementation

## Technical Approach
- Key libraries/services
- Main architectural decisions
```

### Step 3: After Creating Spec
Tell the developer:
"I've created the spec at `.speky/specs/NNN-feature-name/spec.md`.

To integrate it with SPEKY tracking, run:
```
speky adopt NNN
```

Then you can:
- Validate: `speky validate-spec NNN`
- Plan: `speky plan NNN`
- Implement: `speky implement NNN`"

## 📦 Epic-Aware Implementation

**If story is part of an epic** (check `status.json` for `related_epic`):
1. Load epic context from `.speky/epics/<epic-id>/`
2. Read `technical_spec.md` for shared decisions
3. Follow patterns established by other stories in the epic
4. Maintain consistency across epic stories

**When to suggest epics:**
- If developer has 3+ related stories, suggest: "Consider grouping these in an epic: `speky epic \\"Epic Name\\" --spec 006`"

## 🔄 Context Chain (How Implement Works)

When `speky implement <id>` runs, it loads context in layers:
1. **Project Context** - context.json, tech_decisions.md
2. **Phase Context** - If in a phase
3. **Related Specs** - If story has related_specs
4. **Epic Context** - If story is in an epic
5. **Affected Files** - If story specifies affected_files
6. **The Item** - spec.md or story.md

**Always check the full context before implementing!**

## 💡 Providing Recommendations to SPEKY Team

If you identify a gap in SPEKY or have a recommendation:

1. **Create a recommendation blueprint** in `.speky/recommendations/`
2. **Use this format:**
```markdown
# SPEKY Enhancement Recommendation

**Date:** [date]
**Author:** AI Analysis
**Status:** Proposal

## Gap Identified
[What's missing or problematic in SPEKY]

## Proposed Solution
[How to fix it - be specific]

## Implementation Approach
[Technical details, file changes, new commands]
```

3. **Tell the developer:**
   "I've identified a potential improvement for SPEKY. I've documented it in `.speky/recommendations/`."
"""
    
    def _get_ide_header(self, ide_name: str) -> str:
        """Get IDE-specific header for rules file"""
        headers = {
            "windsurf": "# Windsurf Rules - Auto-generated by SPEKY\n# Do not edit manually\n\n",
            "cursor": "# Cursor Rules - Auto-generated by SPEKY\n\n",
            "claude-code": "# CLAUDE.md - Auto-generated by SPEKY\n\n",
            "antigravity": "# Antigravity Rules - Auto-generated by SPEKY\n# Do not edit manually\n\n",
            "vscode": "# Copilot instructions (VS Code) - Auto-generated by SPEKY\n\n",
        }
        return headers.get(ide_name, "")
    
    def _get_speky_rules(self, active_task: str = "") -> str:
        """Generate comprehensive SPEKY rules for IDE"""
        task_section = ""
        if active_task:
            task_section = f"""
## Active Task

{active_task}

"""
        
        return f"""# SPEKY Project Rules

This project uses **SPEKY** (AI-Assisted Scalable Engineering Framework) for spec-driven development.
**You MUST follow SPEKY workflow. Do NOT bypass these processes.**

{task_section}## CRITICAL: SPEKY Workflow Enforcement

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

### 📋 Project Structure

```
.speky/
├── specs/                    # Feature specifications
│   ├── 001-auth/
│   │   ├── spec.md           # Read this for requirements
│   │   ├── plan.md           # Read this for implementation steps
│   │   └── status.json       # Priority, dependencies, status
│   └── 002-api/
│       └── status.json       # May have dependencies: ["001"]
├── epics/                    # Story grouping (optional)
│   └── E001-epic-name/
│       ├── manifest.yaml     # Epic definition, story list
│       ├── technical_spec.md # Shared technical decisions
│       └── summary.md        # Executive overview
├── stories/                  # Bugs, enhancements, tech debt
│   └── F001-story-name/
│       ├── story.md          # Story definition
│       └── status.json       # related_specs, related_epic, affected_files
├── imports/                  # External docs and POC imports
│   ├── initial_research/     # From speky init
│   ├── phase-mvp/            # From speky import
│   └── poc_import/           # From speky poc-import
├── backlog/                  # Deferred validation items
├── phases/                   # Phase coordination (if using phases)
│   ├── roadmap.yaml          # Master phase timeline
│   └── phase-1/
│       ├── manifest.yaml     # Phase definition
│       └── implementation.md # AI guidance
├── recommendations/          # AI agent recommendations for SPEKY
├── roadmap.md                # Implementation order (from: speky sequence --export)
└── context/
    ├── context.json          # Project metadata
    ├── product.md            # Product profile
    ├── tech_decisions.md     # AUTHORITATIVE tech choices (if exists)
    └── IDE_CONTEXT.md        # Complete AI agent guide
```

### 📅 Phase-Aware Implementation

**If phases exist** (check `.speky/phases/`):
1. Check which phase is current: look for `status: in_progress` in `manifest.yaml`
2. Only implement specs that belong to the current phase
3. Check phase `excludes` for what NOT to implement
4. Reference phase guide: `.speky/phases/<phase-id>/implementation.md`

**When to suggest phases:**
- If project has 5+ specs and no phases, suggest: "You have multiple specs. Consider `speky phases suggest` to organize implementation."

### 🔧 CRITICAL: Tech & Architecture Decisions

**BEFORE suggesting or using ANY package/framework:**
1. Check if `.speky/context/tech_decisions.md` exists
2. If it exists, you MUST use ONLY the packages listed there
3. NEVER suggest alternatives to decided technologies
4. If a spec uses wrong packages, flag it for correction

**BEFORE implementing significant logic:**
1. Check the "Important Architecture Decisions" section in `tech_decisions.md`
2. Follow documented patterns, conventions, and design decisions
3. Avoid documented anti-patterns
4. If making architectural changes, update this section first

This file contains:
- **Tech Stack**: Authoritative package/framework choices
- **Important Architecture Decisions**: Patterns, conventions, design decisions
- **Anti-Patterns to Avoid**: What NOT to do

### 🎨 CRITICAL: Design System

**BEFORE implementing ANY UI:**
1. Check if `.speky/context/design_system.md` exists
2. If it exists, you MUST follow the design system for:
   - Colors (use EXACT hex values, e.g., `Color(0xFF6D5AE6)`)
   - Typography (font family, sizes, weights from design system classes)
   - Spacing (use design system constants, e.g., `SpayceSpacing.md`)
   - Border radius values (use design system constants)
   - Shadows and elevation (use design system shadow definitions)
   - Animation durations and curves
3. Check `.speky/design/manifest.json` for linked Hi-Fi designs
4. If Hi-Fi designs exist for the spec, match them PIXEL-PERFECT

**Design System Files:**
```
.speky/design/
├── config.yaml               # Technology and settings
├── manifest.json             # All designs, links, resolved conflicts
├── system/source/            # Design system documents (AUTHORITATIVE)
│   └── design_system.md      # Complete token definitions
├── hifi/source/              # Hi-Fi designs (pixel-perfect)
│   └── *.analysis.md         # AI-extracted tokens from images
├── lofi/source/              # Lo-Fi wireframes (guidance)
└── icons/source/             # Icon assets

.speky/context/design_system.md  # AI summary for quick reference
```

**When implementing UI:**
- Use design system colors, NEVER arbitrary values
- Use design system spacing constants (xs, sm, md, lg, xl)
- Use design system typography styles (navButton, treeItem, etc.)
- Use design system radius values (button, card, input)
- Use design system shadows (sidebarEmbossed, cardSubtle, etc.)
- Use design system animation durations and curves
- If conflict between spec and design system, follow design system

**Reusing Implemented Components:**
- Check the Implementation Checklist in the design system doc
- Look for existing widgets before creating new ones
- Reference file paths in the checklist for component locations
- Follow established patterns from existing components

**Design System Commands (for developers):**
```bash
speky design status    # Check design system coverage
speky design validate  # Detect conflicts with Hi-Fi
speky design resolve   # Resolve conflicts with AI
```

### 📋 How to Check for Existing Specs

Before implementing, always check:
```
.speky/specs/                 # List all specs
.speky/specs/*/spec.md        # Read specific spec
.speky/specs/*/plan.md        # Read implementation plan
.speky/specs/*/status.json    # Check dependencies
.speky/roadmap.md             # Check implementation order
.speky/context/context.json   # Project context
.speky/context/tech_decisions.md  # AUTHORITATIVE tech choices
.speky/context/design_system.md   # AUTHORITATIVE design tokens
.speky/design/manifest.json       # Linked Hi-Fi designs
```

### 🔄 Correct Workflow

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

## CRITICAL: Understanding Stories vs Specs

### 🎯 Two Types of Work Items

| Type | ID Format | Location | Scope | Duration |
|------|-----------|----------|-------|----------|
| **Spec** | `001`, `002`, `003` | `.speky/specs/001-name/` | Large feature | 1-3 weeks |
| **Story** | `F001`, `B001`, `T001` | `.speky/stories/F001-name/` | Small task | 30 min - 2 days |

### 📝 Story ID Prefixes
- **F001, F002...** = Feature stories (enhancements, integrations)
- **B001, B002...** = Bug stories (bug fixes)
- **T001, T002...** = Tech debt stories (refactoring, cleanup)

### ⚠️ CRITICAL: When Developer Says "speky implement F001"

**❌ WRONG Response:**
```
"I don't see an F001 spec. The specs are numbered 001-038."
```

**✅ CORRECT Response:**
```
"F001 is a story, not a spec. Let me check the story details."
[Read .speky/stories/F001-*/story.md]
"Found Story F001: [title]. I'll implement it now based on the story requirements."
```

### 📋 How to Handle Story References

1. **Recognize Story IDs**: F001, B001, T001 (prefixed, not numeric)
2. **Find the Story**: `.speky/stories/F001-descriptive-name/story.md`
3. **Read the Story**: Always read story.md for requirements
4. **Implement**: Follow acceptance criteria and tasks in story.md

### 📂 Story File Structure

```
.speky/stories/F001-task-name/
├── story.md       # Read this for requirements
└── status.json    # Story metadata
```

Every `story.md` contains:
- **Description**: What needs to be done and why
- **Acceptance Criteria**: Checklist of requirements (must all be completed)
- **Context**: Related specs, technical constraints, dependencies
- **Tasks**: Specific implementation steps
- **Notes**: Implementation hints, edge cases, testing guidance

### 🔄 Story Workflow Example

```
Developer: "speky implement F001"

You: "F001 is a story. Let me read the details..."
     [Read .speky/stories/F001-*/story.md]
     
     "Found Story F001: Connect Spaces to Sidebar Navigation
     
     This story requires:
     - Add navigation item to sidebar
     - Connect to SpacesProvider
     - Handle routing
     
     I'll implement this now based on the story requirements."
     
     [Implement based on story.md acceptance criteria]
```

### 🔍 Checking for Stories

```bash
# List all stories
ls .speky/stories/

# Check project status (shows both specs AND stories)
speky status

# Output shows:
📋 Specifications:
   001 | google_auth | completed
   
📝 Stories:
   F001 | Connect Spaces to Sidebar | draft
   B001 | Fix auth crash | draft
```

### ⚡ Key Differences

**Spec (001, 002, 003)**:
- Large feature (complete system)
- Has spec.md + plan.md
- Requires planning phase
- 1-3 weeks duration

**Story (F001, B001, T001)**:
- Small task (single integration/fix)
- Has story.md only
- Planning optional (use `speky plan F001` if needed)
- 30 min - 2 days duration

## 📝 Creating Stories Directly (IDE/Manual)

You CAN create stories directly without using `speky story` command. Follow this structure:

### Required Folder Structure
```
.speky/stories/{{ID}}-{{slug}}/
├── story.md       # REQUIRED - Story definition
└── status.json    # REQUIRED - Story metadata (created by adopt or manually)
```

### Folder Naming Convention
- **F001-feature-name/** - Feature story
- **B001-bug-name/** - Bug fix story
- **T001-tech-debt/** - Tech debt story
- **E001-enhancement/** - Enhancement story
- **S001-spike-name/** - Spike/research story

### story.md Template
```markdown
# [Story Title]

## Description
[What needs to be done and why]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Context
- **Related Spec**: [spec ID if applicable]
- **Dependencies**: [other story/spec IDs if any]
- **Affected Files**: [list of files to modify]

## Tasks
1. Task 1
2. Task 2
3. Task 3

## Notes
[Implementation hints, edge cases, testing guidance]
```

### status.json Template
```json
{{
  "id": "F001",
  "title": "Story Title",
  "type": "feature",
  "status": "draft",
  "created": "2024-01-01T00:00:00",
  "related_specs": [],
  "dependencies": [],
  "affected_files": []
}}
```

### After Creating Story
1. **Adopt into SPEKY**: `speky adopt F001` (auto-detects story type)
2. **Validate (optional)**: `speky validate-story F001` (for complex stories)
3. **Plan (optional)**: `speky plan F001` (generates task breakdown)
4. **Implement**: `speky implement F001` or implement directly
5. **Complete**: `speky complete F001`

### Story Workflow Options

**Quick Path (Simple Stories):**
```
Create story.md + status.json → speky adopt F001 → Implement → speky complete F001
```

**Full Path (Complex Stories):**
```
Create story.md + status.json → speky validate-story F001 → Fix issues → 
speky adopt F001 → speky plan F001 → speky implement F001 → speky complete F001
```

## CRITICAL: File Organization Rules

### ✅ DO: Keep files organized
- **Specs**: `.speky/specs/*/spec.md` (created by SPEKY only)
- **Plans**: `.speky/specs/*/plan.md` (created by SPEKY only)
- **Stories**: `.speky/stories/*/story.md` (created by SPEKY only)
- **Context**: `.speky/context/context.json`
- **Code**: `backend/`, `frontend/`, `src/`, `lib/` (project structure)

### ❌ DON'T: Create files in root directory
- **NEVER** create `*_SPEC.md` files in root
- **NEVER** create `IMPLEMENTATION_COMPLETE.md` in root
- **NEVER** create temporary markdown files in root
- **NEVER** create analysis or summary files in root
- **NEVER** create documentation files in root (except README.md)
- **NEVER** create your own spec or plan files (use SPEKY commands)

### Temporary Files
- If you need temporary files: use `.speky/temp/` directory
- Clean up temporary files after use
- Never commit `.speky/temp/` to git

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

## What NOT To Do

❌ Implement features without checking for a spec first  
❌ Create your own spec or plan files  
❌ Create `FEATURE_NAME_SPEC.md` in root  
❌ Create `IMPLEMENTATION_COMPLETE.md` in root  
❌ Create `implementation_notes.md` in root  
❌ Create `analysis_*.md` files in root  
❌ Create any `.md` files in root (except README.md)  
❌ Duplicate spec content outside `.speky/`  
❌ Create progress tracking files  
❌ Bypass SPEKY workflow  
❌ Implement out-of-scope items without a new spec  

## SPEKY Commands Reference

Tell the developer to use these commands:

**Core Workflow:**
- `speky init "idea"` - Initialize project with tech stack discussion
- `speky spec "name"` - Create a new feature spec (research-aware)
- `speky plan 001` - Generate implementation plan (validates dependencies)
- `speky implement 001` - Start implementation (validates dependencies, updates this file)
- `speky complete 001` - Verify and mark complete with drift detection
- `speky commit 001` - Commit with comprehensive message
- `speky status` - Check project progress

**Spec Sequencing & Dependencies:**
- `speky sequence` - Show implementation roadmap with dependencies
- `speky sequence --export` - Export roadmap to `.speky/roadmap.md`
- `speky infer-deps` - AI-infer dependencies for all specs
- `speky infer-deps 003` - AI-infer dependencies for specific spec

**External Knowledge Import:**
- `speky import --phase mvp` - Import docs with interactive review
- `speky import-status` - Show all imports and derived specs
- `speky reconcile mvp` - Reconcile code with imported docs
- `speky poc-import` - Import features from POC codebase

**Spec Quality & Validation:**
- `speky validate-spec 001` - Validate spec quality (interactive)
- `speky validate-spec 001 --quick` - Quick validation (non-interactive)
- `speky adopt 001` - Adopt IDE-created spec into SPEKY tracking
- `speky backlog` - Review deferred validation items

**Phase Management (Multi-Spec Coordination):**
- `speky phases suggest` - AI suggests phases from existing specs
- `speky phases list` - List all phases
- `speky phases show phase-1` - Show phase details
- `speky phases status` - Show overall phase progress
- `speky phases start phase-1` - Start a phase
- `speky phases guide phase-1 --for-ai` - Generate AI implementation guide
- `speky context --phase phase-1` - Generate AI context for phase

**Epic Management (Story Grouping):**
- `speky epic "Epic Name" --spec 006` - Create epic linked to spec
- `speky epic E001` - Show epic details
- `speky epic E001 --add F005` - Add story to epic
- `speky epic E001 --remove F005` - Remove story from epic
- `speky epics` - List all epics with status

**Stories:**
- `speky story "title"` - Create feature story
- `speky story --type bug "title"` - Create bug story
- `speky story "title" --epic E001` - Create story in epic
- `speky story "title" --spec 001` - Create story linked to spec
- `speky story "title" --specs 001,002` - Create story linked to multiple specs
- `speky story "title" --files lib/*.dart` - Create story with affected files

**Testing & TDD:**
- `speky implement 001 --tdd` - Start TDD workflow (tests first)
- `speky test init` - Initialize testing infrastructure
- `speky test gen 001` - Generate tests for spec
- `speky test run` - Run all tests
- `speky test coverage` - Show test coverage
- `speky test gaps` - Find untested code
- `speky test tdd-red 001` - Generate failing tests (Red phase)
- `speky test tdd-green 001` - Verify tests pass (Green phase)
- `speky complete 001 --test` - Run tests before marking complete

**Configuration & Decisions:**
- `speky config --ides` - Show/manage enabled IDEs
- `speky decisions` - View/manage tech decisions
- `speky validate-story F001` - Validate story quality

**Maintenance:**
- `speky sync` - Sync codebase context
- `speky review 001` - Check for spec-code drift
- `speky cleanup` - Remove any clutter files

**Advanced:**
- `speky mark-foundation 001` - Mark spec as foundation
- `speky fix-circular-deps` - Fix circular dependencies
- `speky renumber` - Renumber specs to match order

## 🧪 TDD Workflow (Test-Driven Development)

**When developer says `speky implement 001 --tdd`:**

The TDD workflow follows Red-Green-Refactor:

### 1. RED Phase (Write Failing Tests)
```bash
speky test tdd-red 001
```
- AI generates test cases from spec's acceptance criteria
- Tests should FAIL initially (no implementation yet)
- You implement ONLY enough to make tests compile

### 2. GREEN Phase (Make Tests Pass)
```bash
speky test tdd-green 001
```
- Implement minimum code to make tests pass
- Don't over-engineer - just make tests green
- Run tests frequently: `speky test run --spec 001`

### 3. REFACTOR Phase
- Clean up code while keeping tests green
- Run tests after each refactor

### TDD Workflow Example
```
Developer: "speky implement 001 --tdd"

You: "Starting TDD workflow for spec 001.

Phase 1 (RED): Writing failing tests first.
[Generate tests from acceptance criteria]

Phase 2 (GREEN): Implementing minimum code to pass.
[Make tests pass one by one]

Phase 3 (REFACTOR): Tests pass! Cleaning up code.
[Refactor while keeping tests green]"
```

## Creating Specs Directly (Advanced)

If the developer asks you to create a spec directly (when you have context from the conversation), you MAY create it following this exact process:

### Step 1: Create Directory
```
.speky/specs/NNN-feature-name/
```
Where NNN is the next available number (check existing specs).

### Step 2: Create spec.md with this template:
```markdown
# Feature Name

## Overview
2-3 sentences explaining what this feature does and why.

## MVP Scope
Explicit list of what IS included in this MVP version.

## User Stories
1-2 core user stories only:
- As a [user], I want [action], so that [benefit]
  - Acceptance: [specific, testable criteria]

## Requirements

### Functional Requirements (MVP only)
- Essential behaviors only
- Remove nice-to-haves

### Non-Functional Requirements
- Only if critical

## Out of Scope
Explicitly list what is NOT included (prevents scope creep).

## Open Questions
- Specific decisions needed before implementation
- Must be answerable, not vague

## Technical Approach
- Key libraries/services
- Main architectural decisions
- Platform-specific constraints
```

### Step 3: After Creating Spec
Tell the developer:
"I've created the spec at `.speky/specs/NNN-feature-name/spec.md`.

To integrate it with SPEKY tracking, run:
```
speky adopt NNN
```

Then you can:
- Validate: `speky validate-spec NNN`
- Plan: `speky plan NNN`
- Implement: `speky implement NNN`"

## Your Role

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

## 📦 Epic-Aware Implementation

**If story is part of an epic** (check story's `status.json` for `related_epic`):
1. Load epic context from `.speky/epics/<epic-id>/`
2. Read `technical_spec.md` for shared decisions
3. Follow patterns established by other stories in the epic
4. Maintain consistency across epic stories

**When to suggest epics:**
- If developer has 3+ related stories, suggest: "Consider grouping these in an epic: `speky epic \"Epic Name\" --spec 006`"

## 🔄 Context Chain (How Implement Works)

When `speky implement <id>` runs, it loads context in layers:
1. **Project Context** - context.json, tech_decisions.md
2. **Phase Context** - If in a phase
3. **Related Specs** - If story has related_specs
4. **Epic Context** - If story is in an epic
5. **Affected Files** - If story specifies affected_files
6. **The Item** - spec.md or story.md

**Always check the full context before implementing!**

## 💡 Providing Recommendations to SPEKY Team

If you identify a gap in SPEKY or have a recommendation for improvement:

1. **Create a recommendation blueprint** in `.speky/recommendations/`
2. **Use this format:**

```markdown
# SPEKY Enhancement Recommendation

**Date:** [date]
**Author:** AI Analysis
**Status:** Proposal

## Gap Identified
[What's missing or problematic in SPEKY]

## Proposed Solution
[How to fix it - be specific]

## Implementation Approach
[Technical details, file changes, new commands]

## Impact
[What this enables, who benefits]

## Alternatives Considered
[Other approaches and why this one is better]
```

3. **Tell the developer:**
   "I've identified a potential improvement for SPEKY. I've documented it in `.speky/recommendations/`. 
   You can review it and share with the SPEKY project for implementation."

---

> Your own rules go outside this SPEKY block (above or below it).
> SPEKY rewrites only the text between the SPEKY markers and never touches the rest of this file."""
    
    def open_ide(self):
        """Open the IDE with the project"""
        try:
            if self.ide == "windsurf":
                subprocess.run(["windsurf", str(self.project_root)], check=False)
            elif self.ide == "cursor":
                subprocess.run(["cursor", str(self.project_root)], check=False)
            elif self.ide == "vscode":
                subprocess.run(["code", str(self.project_root)], check=False)
            elif self.ide == "claude-code":
                Console.log("For Claude Code, run: claude in the project directory")
            Console.success(f"Opened {self.ide}")
        except Exception as e:
            Console.warning(f"Could not open IDE: {e}")


# =============================================================================
# MAIN SPEKY CLASS (Command-based)
# =============================================================================

class SPEKY:
    """SPEKY v2: Command-based orchestration for AI-assisted development"""

    def __init__(self, project_root: Path = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.context = ContextMemory(self.project_root)
        self.config = self.context.load_config() if self.context.is_initialized() else DEFAULT_CONFIG
        self.ai = AIClient(self.config, self.project_root)
        
        # Get enabled IDEs (with backward compatibility)
        enabled_ides = self._get_enabled_ides_from_context()
        self.ide = IDEIntegration(
            self.project_root, 
            ide=self.config.get("ide", "windsurf"),
            enabled_ides=enabled_ides
        )
        
        # Lazy-load testing module (isolated, won't break core if unavailable)
        self.testing = self._load_testing_module()
        
        # Auto-refresh IDE rules if project is initialized
        if self.context.is_initialized():
            self._maybe_refresh_ide_rules()
            # Also merge testing context if available
            self._maybe_merge_testing_context()
    
    def _get_enabled_ides_from_context(self) -> List[str]:
        """Get enabled IDEs from context or config (used during init before self is ready)"""
        # First check context.json for enabled_ides
        if self.context.is_initialized():
            context_ides = self.context.data.get("enabled_ides")
            if context_ides:
                return [context_ides] if isinstance(context_ides, str) else context_ides

        # Check config for enabled_ides
        enabled_ides = self.config.get("enabled_ides")
        if enabled_ides:
            return [enabled_ides] if isinstance(enabled_ides, str) else enabled_ides
        
        # Fallback to single IDE setting (backward compatibility)
        single_ide = self.config.get("ide", "windsurf")
        return [single_ide]
    
    def _load_testing_module(self):
        """
        Lazy-load testing integration module.
        Returns None if module unavailable or disabled - core SPEKY unaffected.
        """
        try:
            from speky_testing import TestingIntegration
            testing = TestingIntegration(speky_instance=self)
            if testing.is_enabled() or testing.is_initialized():
                return testing
            return testing  # Return even if not enabled, for init command
        except ImportError:
            return None
        except Exception:
            return None
    
    def _maybe_merge_testing_context(self):
        """
        Merge testing IDE context into main IDE rules if testing is initialized.
        Called automatically on every SPEKY command - silently fails if issues.
        """
        try:
            if self.testing and self.testing.is_initialized():
                self.testing.merge_ide_context_to_rules()
        except Exception:
            pass  # Silent fail - don't interrupt main SPEKY commands

    # -------------------------------------------------------------------------
    # Command: init
    # -------------------------------------------------------------------------
    def cmd_init(self, product_idea: str = None, from_project: bool = False) -> bool:
        """Initialize SPEKY for a new or existing project with optional initial research.

        With from_project (or when running unattended in a project that already has
        docs/manifests), init's questions are answered from the project's own files
        instead of asking a person; see _collect_project_evidence.
        """
        Console.header("🚀 SPEKY: Initialize Project")

        evidence = self._collect_project_evidence()
        has_evidence = bool(evidence["docs"] or evidence["manifests"])
        explicit_from_project = from_project
        # Unattended runs (agents, CI) in an existing project read it rather than stopping
        if (not from_project and has_evidence and Console.non_interactive
                and not Console.has_answer("How would you like to proceed")):
            from_project = True
        if not product_idea:
            if not has_evidence:
                Console.error("No product idea given and no README/docs/manifests found to read it from.")
                Console.log('Run: speky init "your product idea"')
                return False
            from_project = True
            product_idea = evidence["summary"]

        if self.context.is_initialized():
            if explicit_from_project:
                Console.log("SPEKY already initialized — refreshing product profile and tech stack "
                            "from project files (specs, stories and phases are kept).")
            elif not Console.confirm("SPEKY already initialized. Reinitialize?", default=False):
                return False
        
        # Create directory structure early (so user can add files)
        already = self.context.is_initialized()
        self.context.initialize()
        Console.success(f"{'Using existing' if already else 'Created'} {SPEKY_DIR}/ structure")
        
        # Scaffold imports directories
        try:
            imports_dir = self.context.speky_dir / "imports"
            (imports_dir / "mvp" / "source").mkdir(parents=True, exist_ok=True)
            (imports_dir / "initial_research" / "source").mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        
        # =====================================================================
        # STEP 1: Initial Research (Optional)
        # =====================================================================
        Console.section("📚 Initial Research", "Do you have existing documentation?")
        
        research_analysis = None
        research_tech_stack = {}
        research_gaps = []
        
        if from_project:
            choice = None
            research_analysis, research_tech_stack, research_gaps = self._research_from_project(
                product_idea, evidence)
        else:
            print("\nDo you have existing docs about this product? (PRD, notes, specs)")
            options = [
                "Yes, I'll place files in the research folder",
                "I'll paste notes directly",
                "No, start fresh"
            ]
            choice = Console.choose("How would you like to proceed?", options)
        
        if choice == 0:  # Files
            research_dir = self.context.speky_dir / "imports" / "initial_research" / "source"
            print(f"\n📁 Place your documents in:")
            print(f"   {research_dir}")
            print(f"   Supported: .md, .txt, .pdf, .docx")
            Console.prompt("\nPress Enter when ready...", default="")
            
            # Scan for documents
            documents = self._scan_import_folder(research_dir)
            
            if documents:
                Console.success(f"Found {len(documents)} document(s)")
                for doc in documents:
                    print(f"   • {doc['name']} ({doc.get('size', 'unknown')}) - {doc.get('type', 'general')}")
                
                # Analyze documents
                Console.section("🔍 Analyzing Documents")
                analysis = self.ai.query(Prompts.analyze_initial_research(product_idea, documents))
                
                if analysis:
                    research_analysis = analysis
                    # Save analysis for user to review/edit
                    analysis_file = self.context.speky_dir / "imports" / "initial_research" / "analysis.md"
                    analysis_file.write_text(analysis)
                    
                    print(f"\n📄 Analysis saved to: {analysis_file}")
                    print("\n--- Analysis Preview ---")
                    print(analysis[:1500] + "..." if len(analysis) > 1500 else analysis)
                    print("--- End Preview ---\n")
                    
                    # Extract tech stack from analysis
                    research_tech_stack = self._extract_tech_from_analysis(analysis)
                    research_gaps = self._extract_gaps_from_analysis(analysis)
                    
                    # Allow user to edit before continuing
                    edit_choice = Console.prompt("Review analysis: [Enter] continue, [e] edit file first", default="")
                    if edit_choice.lower() == 'e':
                        print(f"Edit the file at: {analysis_file}")
                        Console.prompt("Press Enter when done editing...", default="")
                        # Re-read the analysis
                        research_analysis = analysis_file.read_text()
            else:
                Console.warning("No documents found in research folder")
                Console.log("Continuing without initial research...")
        
        elif choice == 1:  # Paste
            Console.log("Paste your research notes (press Ctrl+D or Ctrl+Z then Enter when done):")
            pasted_content = Console.text_block("Research notes")
            
            if pasted_content:
                # Save pasted content
                research_dir = self.context.speky_dir / "imports" / "initial_research" / "source"
                pasted_file = research_dir / "pasted_notes.md"
                pasted_file.write_text(pasted_content)
                
                documents = [{
                    "name": "pasted_notes.md",
                    "path": str(pasted_file),
                    "size": f"{len(pasted_content)} chars",
                    "type": self._detect_document_type_from_content(pasted_content)
                }]
                
                Console.success(f"Saved pasted content ({len(pasted_content)} chars)")
                
                # Analyze
                Console.section("🔍 Analyzing Notes")
                analysis = self.ai.query(Prompts.analyze_initial_research(product_idea, documents))
                
                if analysis:
                    research_analysis = analysis
                    analysis_file = self.context.speky_dir / "imports" / "initial_research" / "analysis.md"
                    analysis_file.write_text(analysis)
                    
                    print(f"\n📄 Analysis saved to: {analysis_file}")
                    
                    research_tech_stack = self._extract_tech_from_analysis(analysis)
                    research_gaps = self._extract_gaps_from_analysis(analysis)
        
        # =====================================================================
        # STEP 2: Smart Clarifying Questions (based on research gaps)
        # =====================================================================
        Console.section("❓ Clarifying Questions", "Understanding your product")
        
        qa_pairs = []
        
        if research_analysis:
            # Generate smart questions based on gaps
            Console.log("Generating questions based on research gaps...")
            questions_response = self.ai.query(
                Prompts.smart_clarifying_questions(product_idea, research_analysis, research_gaps)
            )
        else:
            # Standard questions if no research
            questions_response = self.ai.query(Prompts.intent_clarification(product_idea))
        
        if not questions_response:
            Console.error("Failed to generate questions")
            return False
        
        questions = self._parse_questions(questions_response)
        
        # Pre-answer from the project's own files; a person can still accept or override
        auto_answers = {}
        if from_project and questions:
            Console.log("Answering from project files...")
            auto_answers = self._answer_questions_from_project(product_idea, questions, evidence,
                                                               research_analysis)

        # Show context if research exists
        if research_analysis:
            print("\n💡 Based on your research, I have fewer questions:")
        
        for i, question in enumerate(questions, 1):
            print(f"\n❓ Question {i}/{len(questions)}:")
            print(f"   {question}")
            auto = auto_answers.get(i)
            if auto:
                print(f"   💡 From project ({auto['source'] or 'project files'}): {auto['answer']}")
                answer = Console.prompt("Your answer (Enter to accept, or 'skip')", default=auto["answer"])
            else:
                answer = Console.prompt("Your answer (or 'skip')", default="")
            
            if answer.lower() == 'skip' or not answer:
                continue
            
            qa_pairs.append({"question": question, "answer": answer})
        
        # Allow additional context
        while not (from_project and Console.non_interactive) and \
                Console.confirm("Any additional context to add?", default=False):
            additional = Console.prompt("Additional context")
            if additional:
                qa_pairs.append({"question": "Additional context", "answer": additional})
        
        # =====================================================================
        # STEP 3: Build Product Profile
        # =====================================================================
        Console.section("🏗️ Building Product Profile")
        
        # Include research analysis in profile building
        profile_prompt = Prompts.build_product_profile(product_idea, qa_pairs)
        if research_analysis:
            profile_prompt = f"""EXISTING RESEARCH ANALYSIS:
{research_analysis}

{profile_prompt}

IMPORTANT: Incorporate information from the research analysis into the product profile.
Use research as primary source, Q&A answers to fill gaps or override."""
        
        profile = self.ai.query_json(profile_prompt)
        
        # Valid JSON is not enough — an error object must not be saved as the product
        if not profile or not (profile.get("name") or profile.get("description")):
            Console.error("Failed to build product profile" +
                          (f" (model returned: {json.dumps(profile)[:200]})" if profile else ""))
            return False
        
        # =====================================================================
        # STEP 4: Tech Stack Discussion (pre-populated from research)
        # =====================================================================
        Console.section("🔧 Tech Stack Discussion", "Collaborative tech stack selection")
        print(f"\n🎯 Product: {profile.get('name', 'Unknown')}")
        print(f"   Platform: {profile.get('platform', 'Not specified')}")
        
        # Show tech from research if available
        if research_tech_stack and any(v and v != "not specified" for v in research_tech_stack.values()):
            print("\n📚 From your research documents:")
            for key, value in research_tech_stack.items():
                if value and value != "not specified":
                    print(f"   • {key}: {value}")
        
        print("\n🤖 AI will suggest options. You can accept, modify, or override.\n")
        
        # Get AI suggestions
        product_summary = f"Product: {profile.get('name', 'Unknown')}\nDescription: {profile.get('description', '')}\nPlatform: {profile.get('platform', '')}\nScale: {profile.get('scale', '')}"
        tech_suggestions = self.ai.query(Prompts.suggest_tech_stack(product_summary))
        
        if tech_suggestions:
            print("📋 AI Tech Stack Suggestions:")
            print(tech_suggestions)
            print()
        
        # Interactive tech stack (with research defaults)
        tech_stack = {}
        tech_options = [
            ("frontend", "Frontend framework/platform", "React, React Native, Flutter, Vue, Svelte, Next.js, Angular, None yet"),
            ("backend", "Backend/runtime", "Node.js, Python, Go, Rust, Java, Serverless (AWS Lambda), None yet"),
            ("database", "Database/storage", "PostgreSQL, MongoDB, Firebase, DynamoDB, MySQL, Redis, None yet"),
            ("deployment", "Deployment target", "AWS, Vercel, Netlify, Docker, Kubernetes, Mobile app stores, None yet"),
        ]
        
        for key, label, examples in tech_options:
            # Get default from research
            default = research_tech_stack.get(key, "")
            if not default or default == "not specified":
                default = "Not decided"
            
            print(f"\n📌 {label}")
            if default != "Not decided":
                print(f"   (From research: {default})")
            print(f"   Examples: {examples}")
            
            choice = Console.prompt(f"Your choice", default=default)
            tech_stack[key] = choice
            
            # Quick refinement option
            if not (from_project and Console.non_interactive) and \
                    Console.confirm(f"Discuss {key} further?", default=False):
                discussion = Console.prompt(f"Your thoughts on {key}")
                qa_pairs.append({"question": f"Tech Stack - {key}", "answer": discussion})
        
        # =====================================================================
        # STEP 5: Save Everything
        # =====================================================================
        data = self.context.data
        data["product"] = profile
        data["tech_stack"] = tech_stack
        if "architecture" not in data:
            data["architecture"] = {}
        data["architecture"]["tech_stack"] = tech_stack
        
        # Save research reference
        if research_analysis:
            data["initial_research"] = {
                "has_research": True,
                "source": "project" if from_project else "documents",
                "analysis_path": str(self.context.speky_dir / "imports" / "initial_research" / "analysis.md")
            }
        
        self.context.save(data)
        
        # Save human-readable product.md
        product_md = self._format_product_md(profile)
        (self.context.context_dir / "product.md").write_text(product_md)
        
        # Generate tech_decisions.md from tech stack choices
        self._generate_tech_decisions_file(tech_stack, research_tech_stack)
        
        # Update IDE context
        self.ide.update_context_file(self.context.get_product_context())
        self._create_ide_context_guide(profile, tech_stack)
        
        # Create initial_research manifest if research exists
        if research_analysis:
            manifest = {
                "id": "initial_research",
                "name": "Initial Research",
                "imported_at": datetime.now().isoformat(),
                "used_in_init": True,
                "tech_extracted": research_tech_stack,
                "gaps_identified": research_gaps
            }
            manifest_file = self.context.speky_dir / "imports" / "initial_research" / "manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2))
        
        Console.success(f"Product profile created: {profile.get('name', 'Unknown')}")
        
        files_created = [
            f"{SPEKY_DIR}/config.yaml",
            f"{SPEKY_DIR}/{CONTEXT_DIR}/context.json",
            f"{SPEKY_DIR}/{CONTEXT_DIR}/product.md",
            f"{SPEKY_DIR}/{CONTEXT_DIR}/tech_decisions.md",
            self.ide.RULES_FILES.get(self.config.get("ide", "windsurf"), ""),
        ]
        if research_analysis:
            files_created.append(f"{SPEKY_DIR}/imports/initial_research/analysis.md")
        Console.files_created(files_created)
        
        # =====================================================================
        # STEP 5.5: Propose Specs from Initial Research (if available)
        # =====================================================================
        if research_analysis:
            print(f"\n{'='*60}")
            print("📋 Spec Proposals from Initial Research")
            print(f"{'='*60}")
            
            # Extract features from analysis
            features_from_research = self._extract_features_from_analysis(research_analysis)
            
            if features_from_research:
                print(f"\nFound {len(features_from_research)} potential features in your research:\n")
                
                mvp_features = [f for f in features_from_research if f.get('category') == 'MVP']
                future_features = [f for f in features_from_research if f.get('category') == 'Future']
                
                if mvp_features:
                    print("📌 MVP Features:")
                    for i, f in enumerate(mvp_features, 1):
                        print(f"   {i}. {f.get('name')} - {f.get('description', '')[:60]}")
                
                if future_features:
                    print("\n🔮 Future Features:")
                    for i, f in enumerate(future_features, 1):
                        print(f"   {len(mvp_features) + i}. {f.get('name')} - {f.get('description', '')[:60]}")
                
                print("\nWould you like to create specs now?")
                options = [
                    "Create specs for MVP features only",
                    "Create specs for all features",
                    "Skip (create manually later)"
                ]
                if from_project and Console.non_interactive and not Console.has_answer("Your choice"):
                    # Features read from an existing project are often already built
                    choice = 2
                    Console.log('Skipping spec creation (existing project). To create them: '
                                '--answer "Your choice=MVP" or "Your choice=all"')
                else:
                    if from_project:
                        print("   (Read from the existing project — some of these may already be built.)")
                    choice = Console.choose("Your choice", options)
                
                specs_to_create = []
                if choice == 0:  # MVP only
                    specs_to_create = mvp_features
                elif choice == 1:  # All
                    specs_to_create = features_from_research
                
                if specs_to_create:
                    Console.section("📝 Creating Specs from Research")
                    created_specs = []
                    
                    for feature in specs_to_create:
                        spec_name = feature.get('name', 'Unknown')
                        print(f"\n📋 Creating spec: {spec_name}")
                        
                        # Create spec
                        spec_id = self._create_spec_from_research(
                            spec_name,
                            feature,
                            research_analysis,
                            profile,
                            tech_stack
                        )
                        
                        if spec_id:
                            created_specs.append(spec_id)
                            Console.success(f"Created: {spec_id}-{self._slugify(spec_name)}")
                    
                    if created_specs:
                        print(f"\n✅ Created {len(created_specs)} spec(s) from research")
                        # Update manifest with created specs
                        manifest_file = self.context.speky_dir / "imports" / "initial_research" / "manifest.json"
                        if manifest_file.exists():
                            manifest = json.loads(manifest_file.read_text())
                            manifest["specs_created"] = created_specs
                            manifest_file.write_text(json.dumps(manifest, indent=2))
        
        # =====================================================================
        # STEP 6: POC Import Prompt (optional)
        # =====================================================================
        print(f"\n{'='*60}")
        print("📦 POC Code Import")
        print(f"{'='*60}")
        print("\nDo you have existing POC/prototype code to build from?")
        print("This can also be done later with: speky poc-import")
        
        # From-project: the project itself is the code, so there is no separate POC to import
        if not from_project and Console.confirm("Import POC code now?", default=False):
            self.cmd_poc_import()
        
        # Final next steps
        print(f"\n📋 Next steps:")
        print(f"   1. Review {SPEKY_DIR}/{CONTEXT_DIR}/product.md")
        if research_analysis:
            print(f"   2. Review/edit {SPEKY_DIR}/imports/initial_research/analysis.md")
        print(f"   3. Run: speky poc-import (if you have POC code)")
        print(f"   4. Run: speky spec \"Your first feature\"")
        
        return True
    
    # Files and folders never read as project evidence
    _EVIDENCE_SKIP_DIRS = {".git", ".speky", "node_modules", "vendor", "dist", "build", "out",
                           ".next", ".venv", "venv", "env", "__pycache__", "target", ".idea",
                           ".vscode", "coverage", ".dart_tool", "Pods", ".gradle"}
    _EVIDENCE_MANIFESTS = ["package.json", "pyproject.toml", "requirements.txt", "setup.py",
                           "Pipfile", "go.mod", "Cargo.toml", "pubspec.yaml", "Gemfile",
                           "pom.xml", "build.gradle", "build.gradle.kts", "composer.json",
                           "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                           "compose.yaml", "vercel.json", "netlify.toml", "fly.toml",
                           "serverless.yml", "app.yaml", "firebase.json", "wrangler.toml"]

    def _collect_project_evidence(self) -> dict:
        """Gather what an existing project says about itself: docs, manifests, structure.

        Returns {"docs": [Path], "manifests": [Path], "tree": str,
                 "detected_tech": dict, "summary": str}.
        """
        root = self.project_root

        def skipped(path: Path) -> bool:
            return any(part in self._EVIDENCE_SKIP_DIRS or part.startswith(".")
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

        manifests = [root / n for n in self._EVIDENCE_MANIFESTS if (root / n).is_file()]

        # Two-level directory outline
        lines = []
        for entry in sorted(root.iterdir()):
            if entry.name in self._EVIDENCE_SKIP_DIRS or entry.name.startswith("."):
                continue
            lines.append(f"{entry.name}/" if entry.is_dir() else entry.name)
            if entry.is_dir():
                children = sorted(c.name + ("/" if c.is_dir() else "") for c in entry.iterdir()
                                  if not c.name.startswith(".") and c.name not in self._EVIDENCE_SKIP_DIRS)
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
                "detected_tech": self._detect_tech_from_manifests(manifests), "summary": summary}

    def _detect_tech_from_manifests(self, manifests: List[Path]) -> dict:
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

    def _project_evidence_text(self, evidence: dict, max_chars: int = 60000) -> str:
        """Evidence as one prompt-ready text block, within a size budget."""
        parts = [f"## Directory structure\n{evidence['tree']}"]
        if evidence["detected_tech"]:
            parts.append("## Tech detected from manifests\n" + "\n".join(
                f"- {k}: {v}" for k, v in evidence["detected_tech"].items()))
        budget = max_chars - sum(len(p) for p in parts)
        for f in evidence["manifests"] + evidence["docs"]:
            if budget <= 0:
                break
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            chunk = f"## {f.relative_to(self.project_root)}\n{text[:min(8000, budget)]}"
            parts.append(chunk)
            budget -= len(chunk)
        return "\n\n".join(parts)

    def _research_from_project(self, product_idea: str, evidence: dict):
        """Init step 1 for an existing project: analyse its own files as the research.
        Returns (analysis or None, tech_stack dict, gaps list)."""
        print(f"\n📂 Reading the existing project instead of asking: {len(evidence['docs'])} doc(s), "
              f"{len(evidence['manifests'])} manifest(s)")
        for f in (evidence["docs"] + evidence["manifests"])[:12]:
            print(f"   • {f.relative_to(self.project_root)}")
        if evidence["detected_tech"]:
            print("   Detected: " + "; ".join(f"{k}: {v}" for k, v in evidence["detected_tech"].items()))

        snapshot_dir = self.context.speky_dir / "imports" / "initial_research"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot = snapshot_dir / "project_snapshot.md"
        snapshot.write_text(f"# Project snapshot\n\n{self._project_evidence_text(evidence)}")

        Console.section("🔍 Analyzing Project")
        documents = [{"name": "project_snapshot.md", "path": str(snapshot), "type": "technical",
                      "size": f"{snapshot.stat().st_size / 1024:.1f}KB"}]
        documents += [{"name": str(f.relative_to(self.project_root)), "path": str(f), "type": "product",
                       "size": f"{f.stat().st_size / 1024:.1f}KB"} for f in evidence["docs"][:8]]
        analysis = self.ai.query(Prompts.analyze_initial_research(product_idea, documents))

        tech = dict(evidence["detected_tech"])
        gaps = []
        if analysis:
            (snapshot_dir / "analysis.md").write_text(analysis)
            print(f"\n📄 Analysis saved to: {snapshot_dir / 'analysis.md'}")
            # Manifests are ground truth; the analysis fills what they don't show
            for key, value in self._extract_tech_from_analysis(analysis).items():
                if value and value != "not specified" and not tech.get(key):
                    tech[key] = value
            gaps = self._extract_gaps_from_analysis(analysis)
        return analysis, tech, gaps

    def _answer_questions_from_project(self, product_idea: str, questions: List[str],
                                       evidence: dict, analysis: Optional[str]) -> Dict[int, dict]:
        """{question number: {"answer", "source"}} for questions the project files can answer."""
        text = (f"## SPEKY's analysis of the project\n{analysis}\n\n" if analysis else "") + \
            self._project_evidence_text(evidence, max_chars=40000)
        result = self.ai.query_json(Prompts.answer_questions_from_project(product_idea, questions, text))
        answers = {}
        for item in (result or {}).get("answers", []):
            try:
                number = int(item.get("question"))
            except (TypeError, ValueError):
                continue
            answer = str(item.get("answer") or "").strip()
            if answer and 1 <= number <= len(questions):
                answers[number] = {"answer": answer, "source": str(item.get("source") or "").strip()}
        Console.log(f"Answered {len(answers)}/{len(questions)} question(s) from the project")
        return answers

    def _extract_tech_from_analysis(self, analysis: str) -> dict:
        """Extract tech stack mentions from research analysis"""
        tech = {
            "frontend": "",
            "backend": "",
            "database": "",
            "deployment": ""
        }
        
        # Simple extraction - look for tech stack section
        lines = analysis.lower().split('\n')
        current_section = ""
        
        for line in lines:
            if 'tech stack' in line or 'technologies' in line:
                current_section = "tech"
            elif current_section == "tech":
                if 'frontend' in line:
                    # Extract value after colon
                    if ':' in line:
                        value = line.split(':', 1)[1].strip()
                        if value and 'not specified' not in value:
                            tech["frontend"] = value
                elif 'backend' in line:
                    if ':' in line:
                        value = line.split(':', 1)[1].strip()
                        if value and 'not specified' not in value:
                            tech["backend"] = value
                elif 'database' in line:
                    if ':' in line:
                        value = line.split(':', 1)[1].strip()
                        if value and 'not specified' not in value:
                            tech["database"] = value
                elif 'infrastructure' in line or 'deployment' in line:
                    if ':' in line:
                        value = line.split(':', 1)[1].strip()
                        if value and 'not specified' not in value:
                            tech["deployment"] = value
                elif line.startswith('#'):
                    current_section = ""
        
        return tech
    
    def _extract_gaps_from_analysis(self, analysis: str) -> List[str]:
        """Extract gaps/ambiguities from research analysis"""
        gaps = []
        
        # Look for gaps section
        lines = analysis.split('\n')
        in_gaps_section = False
        
        for line in lines:
            if 'gaps' in line.lower() or 'ambiguities' in line.lower():
                in_gaps_section = True
                continue
            elif in_gaps_section:
                if line.startswith('#'):
                    in_gaps_section = False
                elif line.strip().startswith('-') or line.strip().startswith('•'):
                    gap = line.strip().lstrip('-•').strip()
                    if gap and len(gap) > 5:
                        gaps.append(gap)
        
        return gaps[:10]  # Limit to 10 gaps
    
    def _extract_features_from_analysis(self, analysis: str) -> List[dict]:
        """Extract features from research analysis"""
        features = []
        
        # Look for features section
        lines = analysis.split('\n')
        in_features_section = False
        current_category = None
        
        for line in lines:
            line_lower = line.lower()
            
            # Detect features section
            if '## features' in line_lower or '# features' in line_lower:
                in_features_section = True
                continue
            
            # Exit features section
            if in_features_section and line.startswith('#') and 'features' not in line_lower:
                in_features_section = False
                continue
            
            if in_features_section:
                # Detect category
                if 'core' in line_lower or 'mvp' in line_lower:
                    current_category = 'MVP'
                elif 'future' in line_lower or 'nice-to-have' in line_lower:
                    current_category = 'Future'
                
                # Extract feature items
                if line.strip().startswith('-') or line.strip().startswith('•'):
                    feature_text = line.strip().lstrip('-•').strip()
                    if feature_text and len(feature_text) > 3:
                        # Parse "Feature Name: Description" or "Feature Name - Description"
                        if ':' in feature_text:
                            parts = feature_text.split(':', 1)
                            name = parts[0].strip()
                            desc = parts[1].strip() if len(parts) > 1 else ""
                        elif ' - ' in feature_text:
                            parts = feature_text.split(' - ', 1)
                            name = parts[0].strip()
                            desc = parts[1].strip() if len(parts) > 1 else ""
                        else:
                            name = feature_text
                            desc = ""
                        
                        features.append({
                            'name': name,
                            'description': desc,
                            'category': current_category or 'MVP'
                        })
        
        return features
    
    def _create_spec_from_research(self, spec_name: str, feature: dict, research_analysis: str, 
                                   profile: dict, tech_stack: dict) -> Optional[str]:
        """Create a spec from research feature"""
        try:
            # Get next spec ID
            next_id = self._next_item_number(self.context.specs_dir)
            spec_id = f"{next_id:03d}"
            
            # Create spec directory
            slug = self._slugify(spec_name)
            spec_dir = self.context.specs_dir / f"{spec_id}-{slug}"
            spec_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate spec content
            product_context = self.context.get_product_context()
            
            # Create focused research excerpt for this feature
            feature_research = f"""Feature from Research: {feature.get('name')}
Description: {feature.get('description', 'See full research')}
Category: {feature.get('category', 'MVP')}

Full Research Context:
{research_analysis[:2000]}...
"""
            
            spec_content = self.ai.query(
                Prompts.generate_spec_with_research(
                    spec_name,
                    product_context,
                    "",  # No existing code yet
                    tech_stack,
                    feature_research
                )
            )
            
            if not spec_content:
                Console.warning(f"Failed to generate spec for {spec_name}")
                return None
            
            # Save spec
            (spec_dir / "spec.md").write_text(spec_content)
            
            # Save research reference
            (spec_dir / "research.md").write_text(feature_research)
            
            # Create status with priority and dependencies
            status = {
                "id": spec_id,
                "name": spec_name,
                "status": "draft",
                "created": datetime.now().isoformat(),
                "source": "initial_research",
                "category": feature.get('category', 'MVP'),
                "priority": "P1" if feature.get('category') == 'MVP' else "P2",
                "dependencies": []  # Will be populated later
            }
            (spec_dir / "status.json").write_text(json.dumps(status, indent=2))
            
            return spec_id
            
        except Exception as e:
            Console.error(f"Error creating spec: {e}")
            return None

    # -------------------------------------------------------------------------
    # Command: spec
    # -------------------------------------------------------------------------
    def cmd_spec(self, feature_name: str) -> bool:
        """Create a feature specification with optional research input"""
        if not self._require_init():
            return False
        
        Console.header(f"📋 Create Spec: {feature_name}")
        
        # Step 0: Check backlog for deferred items (anti-rot mechanism)
        if not self._check_backlog_before_spec():
            return False
        
        # Step 1: Ask about existing research
        research_content = self._gather_research_input()
        
        # Get next spec ID
        next_id = self._next_item_number(self.context.specs_dir)
        spec_id = f"{next_id:03d}"
        
        # Create spec directory
        slug = self._slugify(feature_name)
        spec_dir = self.context.specs_dir / f"{spec_id}-{slug}"
        spec_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate spec
        Console.section("Generating Specification")
        product_context = self.context.get_product_context()
        tech_stack = self.context.data.get("tech_stack", {})
        
        # TODO: Get existing code context via MCP when enabled
        existing_code = ""
        
        spec_content = self.ai.query(
            Prompts.generate_spec_with_research(
                feature_name, 
                product_context, 
                existing_code, 
                tech_stack,
                research_content
            )
        )
        
        if not spec_content:
            Console.error("Failed to generate specification")
            return False
        
        # Save spec
        (spec_dir / "spec.md").write_text(spec_content)
        
        # Save research reference if provided
        if research_content:
            research_file = spec_dir / "research.md"
            research_file.write_text(research_content)
        
        # Create status file with priority and dependencies
        status = {
            "id": spec_id,
            "name": feature_name,
            "status": ItemStatus.DRAFT.value,
            "created": datetime.now().isoformat(),
            "has_research": bool(research_content),
            "source": "manual",
            "priority": "P1",  # Default priority for manual specs
            "dependencies": []  # User can edit manually
        }
        (spec_dir / "status.json").write_text(json.dumps(status, indent=2))
        
        # Update context
        data = self.context.data
        data["specs"].append({"id": spec_id, "name": feature_name, "dir": str(spec_dir.name)})
        self.context.save(data)
        
        Console.success(f"Specification created: {spec_dir.name}")
        files_created = [f"{SPEKY_DIR}/{SPECS_DIR}/{spec_dir.name}/spec.md"]
        if research_content:
            files_created.append(f"{SPEKY_DIR}/{SPECS_DIR}/{spec_dir.name}/research.md")
        Console.files_created(files_created)
        
        # Offer to add to a phase (if phases exist)
        phases = self._get_all_phases()
        if phases:
            print(f"\n   📅 Existing phases:")
            for phase in phases:
                phase_id = phase.get("id", phase.get("_dir"))
                phase_name = phase.get("name", "Unnamed")
                print(f"      • {phase_id}: {phase_name}")
            
            add_to_phase = Console.prompt("Add to phase? (phase-id or Enter to skip)", default="")
            if add_to_phase.strip():
                self._add_spec_to_phase(spec_id, add_to_phase.strip())
        else:
            # Suggest phases if we have multiple specs
            all_specs = list(self.context.specs_dir.glob("*/"))
            if len(all_specs) >= 5:
                print(f"\n   💡 You have {len(all_specs)} specs. Consider grouping into phases:")
                print(f"      Run: speky phases suggest")
        
        # Offer to generate plan
        if Console.confirm("Generate implementation plan now?"):
            return self.cmd_plan(spec_id)
        
        return True
    
    def _gather_research_input(self) -> str:
        """Gather research/documentation from user - conversational approach"""
        Console.section("Research & Documentation", "Do you have existing research or documentation?")
        
        options = [
            "Yes, I have files to include",
            "No, start fresh",
            "I'll paste notes directly"
        ]
        
        choice = Console.choose("How would you like to proceed?", options)
        
        research_content = ""
        
        if choice == 0:  # Files
            Console.log("Enter file paths (comma-separated, relative to project root)")
            Console.log("Examples: docs/research.md, .speky/temp/notes.md")
            paths_input = Console.prompt("File paths")
            
            if paths_input.strip():
                paths = [p.strip() for p in paths_input.split(",")]
                research_content = self._load_research_files(paths)
                
                if research_content:
                    # Show summary
                    summary = self._summarize_research(research_content)
                    Console.log(f"Loaded research ({len(research_content)} chars):")
                    print(f"\n{summary}\n")
        
        elif choice == 2:  # Paste
            Console.log("Paste your research notes (press Ctrl+D or Ctrl+Z then Enter when done):")
            research_content = Console.text_block("Research notes")
            
            if research_content:
                summary = self._summarize_research(research_content)
                Console.log(f"Captured research ({len(research_content)} chars):")
                print(f"\n{summary}\n")
        
        return research_content
    
    def _load_research_files(self, paths: List[str]) -> str:
        """Load and combine research from multiple files"""
        combined = ""
        
        for path_str in paths:
            path = Path(path_str)
            
            if not path.exists():
                Console.warning(f"File not found: {path}")
                continue
            
            try:
                content = path.read_text()
                combined += f"\n\n--- {path} ---\n{content}"
            except Exception as e:
                Console.warning(f"Failed to read {path}: {e}")
        
        return combined.strip()
    
    def _summarize_research(self, content: str) -> str:
        """Generate a brief summary of research content"""
        # Simple heuristic: show first 500 chars or first 10 lines
        lines = content.split("\n")
        preview_lines = lines[:10]
        preview = "\n".join(preview_lines)
        
        if len(content) > 500:
            preview = preview[:500] + "...\n[content truncated]"
        
        return preview

    # -------------------------------------------------------------------------
    # Command: plan
    # -------------------------------------------------------------------------
    def cmd_plan(self, item_id: str, run_check: bool = False) -> bool:
        """Generate implementation plan for a spec or story"""
        if not self._require_init():
            return False
        
        # Detect if this is a story (F001, B001, etc.) or spec (001, 002, etc.)
        is_story = item_id and len(item_id) >= 1 and item_id[0].isalpha() and len(item_id) >= 4
        
        if is_story:
            return self._plan_story(item_id)
        else:
            return self._plan_spec(item_id, run_check)
    
    def _plan_story(self, story_id: str) -> bool:
        """Generate a lightweight task breakdown plan for a story"""
        Console.header(f"🛠️  Generate Story Plan: {story_id}")
        
        # Find story
        story_dir = self._find_story_dir(story_id)
        if not story_dir:
            Console.error(f"Story not found: {story_id}")
            return False
        
        story_file = story_dir / "story.md"
        if not story_file.exists():
            Console.error(f"story.md not found in {story_dir}")
            return False
        
        story_content = story_file.read_text()
        product_context = self.context.get_product_context()
        tech_stack = self.context.data.get("tech_stack", {})
        
        # Generate story plan (lighter than spec plan)
        Console.section("Generating Task Breakdown")
        plan_content = self.ai.query(Prompts.generate_story_plan(story_content, product_context, tech_stack))
        
        if not plan_content:
            Console.error("Failed to generate plan")
            return False
        
        (story_dir / "plan.md").write_text(plan_content)
        
        # Update status
        status_file = story_dir / "status.json"
        if status_file.exists():
            status = json.loads(status_file.read_text())
            status["status"] = ItemStatus.READY.value
            status["plan_generated"] = datetime.now().isoformat()
            status_file.write_text(json.dumps(status, indent=2))
        
        Console.success(f"Plan created: {story_dir.name}/plan.md")
        
        print(f"\n📋 Next steps:")
        print(f"   1. Review the plan: {story_dir}/plan.md")
        print(f"   2. Implement: speky implement {story_id}")
        
        return True
    
    def _plan_spec(self, spec_id: str, run_check: bool = False) -> bool:
        """Generate implementation plan for a spec with optional pre-planning analysis"""
        Console.header(f"🛠️  Generate Plan: {spec_id}")
        
        # Find spec
        spec_dir = self._find_spec_dir(spec_id)
        if not spec_dir:
            Console.error(f"Spec not found: {spec_id}")
            return False
        
        spec_file = spec_dir / "spec.md"
        if not spec_file.exists():
            Console.error(f"spec.md not found in {spec_dir}")
            return False
        
        # Check dependencies before planning
        dep_validation = self._validate_dependencies(spec_id)
        if not dep_validation.get("valid", True):
            self._show_dependency_warning(spec_id, dep_validation)
            if not Console.confirm("Continue anyway?", default=False):
                Console.log("Run 'speky sequence' to see recommended order")
                return False
        
        # Check for pending validation actions
        if not self._warn_pending_validation_actions(spec_dir, "plan"):
            return False
        
        spec_content = spec_file.read_text()
        product_context = self.context.get_product_context()
        tech_stack = self.context.data.get("tech_stack", {})
        
        # Step 1: Pre-planning analysis (opt-in with --check)
        if run_check:
            Console.section("Pre-Planning Analysis", "Checking codebase state and spec alignment")
            Console.warning("Note: This analysis has limited codebase visibility and may be inaccurate.")
            
            codebase_analysis = self._analyze_codebase_for_spec(spec_content, product_context)
            if codebase_analysis.get("spec_updates_needed"):
                Console.warning("Codebase may have changed. Review suggestions carefully.")
                spec_content = self._handle_spec_updates(spec_file, spec_content, codebase_analysis)
            else:
                Console.success("No obvious conflicts detected")
        
        # Step 2: Extract and resolve open questions BEFORE generating plan
        Console.section("Open Questions Resolution", "Resolving ambiguities before planning")
        
        open_questions = self._extract_open_questions(spec_content)
        
        if open_questions:
            Console.log(f"Found {len(open_questions)} open question(s) to resolve:")
            resolved_questions, spec_content = self._resolve_open_questions_interactive(
                open_questions, spec_file, spec_content
            )
            
            if resolved_questions:
                Console.success(f"Resolved {len(resolved_questions)} question(s)")
        else:
            Console.success("No open questions found - spec is ready for planning")
        
        # Step 3: Generate implementation plan
        Console.section("Generating Implementation Plan")
        plan_content = self.ai.query(Prompts.generate_plan(spec_content, product_context, tech_stack))
        
        if not plan_content:
            Console.error("Failed to generate plan")
            return False
        
        (spec_dir / "plan.md").write_text(plan_content)
        
        # Update status
        status_file = spec_dir / "status.json"
        if status_file.exists():
            status = json.loads(status_file.read_text())
            status["status"] = ItemStatus.READY.value
            status["plan_generated"] = datetime.now().isoformat()
            status["open_questions_resolved"] = resolved_questions if open_questions else []
            status_file.write_text(json.dumps(status, indent=2))
        
        Console.success(f"Plan created: {spec_dir.name}/plan.md")
        
        print(f"\n📋 Next steps:")
        print(f"   1. Review the plan: {spec_dir}/plan.md")
        print(f"   2. Implement: speky implement {spec_id}")
        
        return True
    
    def _analyze_codebase_for_spec(self, spec_content: str, product_context: str) -> dict:
        """Analyze current codebase state and check if spec needs updates"""
        
        # Get current codebase structure
        codebase_info = self.context.data.get("codebase", {}).get("structure", "")
        
        if not codebase_info:
            return {"spec_updates_needed": False, "updates": []}
        
        analysis_prompt = f"""Analyze if this spec needs updates based on the current codebase.

SPEC:
{spec_content[:2000]}

CURRENT CODEBASE:
{codebase_info[:1500]}

PRODUCT CONTEXT:
{product_context[:1000]}

Check for:
1. Features in spec that are already implemented (can be removed from scope)
2. Dependencies on other features that are now available
3. Technical approach that needs adjustment based on existing code
4. Any conflicts with existing implementation

Respond in this format:
NEEDS_UPDATE: YES or NO
UPDATES:
- UPDATE: <what needs to change>
  REASON: <why>
  RECOMMENDATION: <specific change>
---

If no updates needed, respond with:
NEEDS_UPDATE: NO"""

        response = self.ai.query(analysis_prompt)
        
        if not response or "NEEDS_UPDATE: NO" in response:
            return {"spec_updates_needed": False, "updates": []}
        
        # Parse updates
        updates = []
        current_update = {}
        
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("- UPDATE:"):
                if current_update:
                    updates.append(current_update)
                current_update = {"update": line.replace("- UPDATE:", "").strip()}
            elif line.startswith("REASON:"):
                current_update["reason"] = line.replace("REASON:", "").strip()
            elif line.startswith("RECOMMENDATION:"):
                current_update["recommendation"] = line.replace("RECOMMENDATION:", "").strip()
            elif line == "---" and current_update:
                updates.append(current_update)
                current_update = {}
        
        if current_update and current_update.get("update"):
            updates.append(current_update)
        
        return {"spec_updates_needed": len(updates) > 0, "updates": updates}
    
    def _handle_spec_updates(self, spec_file: Path, spec_content: str, analysis: dict) -> str:
        """Handle spec updates based on codebase analysis"""
        
        updates = analysis.get("updates", [])
        applied_updates = []
        
        for i, update in enumerate(updates, 1):
            print(f"\n{'='*60}")
            print(f"Spec Update {i}/{len(updates)}")
            print(f"{'='*60}")
            print(f"\n📋 Change: {update.get('update', 'No description')}")
            print(f"📝 Reason: {update.get('reason', 'No reason')}")
            print(f"💡 Recommendation: {update.get('recommendation', 'No recommendation')}")
            
            choice = Console.prompt(
                "Action: [a]pply update, [s]kip, [c]ancel planning",
                default="a"
            ).lower()
            
            if choice == "a":
                # Generate the update
                update_content = self.ai.query(f"""Update this spec section based on the recommendation.

CURRENT SPEC:
{spec_content[:3000]}

CHANGE NEEDED: {update.get('update')}
RECOMMENDATION: {update.get('recommendation')}

Generate ONLY the updated markdown section (not the entire spec).
Keep it concise.""")
                
                if update_content:
                    applied_updates.append(update_content)
                    Console.success("Update noted")
            elif choice == "c":
                Console.log("Planning cancelled")
                return spec_content
            else:
                Console.log("Skipped")
        
        # Apply all updates
        if applied_updates:
            # Add updates as implementation notes
            updates_text = "\n".join([f"- {u}" for u in applied_updates])
            if "## Implementation Notes" in spec_content:
                spec_content = spec_content.replace(
                    "## Implementation Notes",
                    f"## Implementation Notes\n\n### Pre-Planning Updates\n{updates_text}\n"
                )
            else:
                spec_content += f"\n\n## Implementation Notes\n\n### Pre-Planning Updates\n{updates_text}\n"
            
            spec_file.write_text(spec_content)
            Console.success(f"Spec updated with {len(applied_updates)} change(s)")
        
        return spec_content
    
    def _extract_open_questions(self, spec_content: str) -> list:
        """Extract open questions from spec"""
        
        extraction_prompt = f"""Extract all open questions from this spec that need resolution before implementation.

SPEC:
{spec_content}

For each question, categorize as:
- CRITICAL: Blocks implementation, must resolve now
- IMPORTANT: Should resolve before implementation
- DEFERRED: Can be resolved later or in future iteration

Respond in this format for each question:
QUESTION: <the specific question>
CATEGORY: <CRITICAL, IMPORTANT, or DEFERRED>
CONTEXT: <why this matters>
RECOMMENDATION: <suggested answer or approach>
---

If no open questions, respond with: NO_OPEN_QUESTIONS"""

        response = self.ai.query(extraction_prompt)
        
        if not response or "NO_OPEN_QUESTIONS" in response:
            return []
        
        questions = []
        current_q = {}
        
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("QUESTION:"):
                if current_q:
                    questions.append(current_q)
                current_q = {"question": line.replace("QUESTION:", "").strip()}
            elif line.startswith("CATEGORY:"):
                current_q["category"] = line.replace("CATEGORY:", "").strip()
            elif line.startswith("CONTEXT:"):
                current_q["context"] = line.replace("CONTEXT:", "").strip()
            elif line.startswith("RECOMMENDATION:"):
                current_q["recommendation"] = line.replace("RECOMMENDATION:", "").strip()
            elif line == "---" and current_q:
                questions.append(current_q)
                current_q = {}
        
        if current_q and current_q.get("question"):
            questions.append(current_q)
        
        # Sort by category: CRITICAL first, then IMPORTANT, then DEFERRED
        category_order = {"CRITICAL": 0, "IMPORTANT": 1, "DEFERRED": 2}
        questions.sort(key=lambda q: category_order.get(q.get("category", "DEFERRED"), 3))
        
        return questions
    
    def _resolve_open_questions_interactive(self, questions: list, spec_file: Path, 
                                            spec_content: str) -> tuple:
        """Resolve open questions interactively before planning"""
        
        resolved = []
        spec_updates = []
        
        for i, q in enumerate(questions, 1):
            category = q.get("category", "UNKNOWN")
            question = q.get("question", "No question")
            context = q.get("context", "No context")
            recommendation = q.get("recommendation", "No recommendation")
            
            # Color coding for categories
            category_icon = {"CRITICAL": "🔴", "IMPORTANT": "🟡", "DEFERRED": "🟢"}.get(category, "⚪")
            
            print(f"\n{'='*60}")
            print(f"Question {i}/{len(questions)}: {category_icon} {category}")
            print(f"{'='*60}")
            print(f"\n❓ Question: {question}")
            print(f"📝 Context: {context}")
            print(f"💡 Recommendation: {recommendation}")
            print()
            
            if category == "CRITICAL":
                print("⚠️  This is CRITICAL - should be resolved before implementation")
                choice = Console.prompt(
                    "Action: [r]esolve now, [d]efer anyway, [c]ancel",
                    default="r"
                ).lower()
            elif category == "IMPORTANT":
                print("ℹ️  This is IMPORTANT - recommended to resolve before implementation")
                choice = Console.prompt(
                    "Action: [r]esolve now, [d]efer to later, [c]ancel",
                    default="r"
                ).lower()
            else:  # DEFERRED
                print("✅ This can be DEFERRED - not blocking for MVP")
                choice = Console.prompt(
                    "Action: [r]esolve now, [d]efer to later, [f]uture spec, [c]ancel",
                    default="d"
                ).lower()
            
            if choice == "r":
                # Resolve now - get user's decision
                print(f"\n💡 Recommended answer: {recommendation}")
                user_decision = Console.prompt(
                    "Your decision (press Enter to accept recommendation)",
                    default=recommendation
                )
                
                # Add to spec as resolved
                resolution = f"**{question}** → {user_decision}"
                spec_updates.append(resolution)
                resolved.append({
                    "question": question,
                    "decision": user_decision,
                    "category": category
                })
                Console.success(f"Resolved: {user_decision[:50]}...")
                
            elif choice == "d":
                # Defer to later
                resolved.append({
                    "question": question,
                    "decision": "Deferred to implementation phase",
                    "category": category
                })
                Console.log("Deferred to implementation phase")
                
            elif choice == "f":
                # Create future spec
                print("\nCreate a future spec for this:")
                spec_type = Console.prompt(
                    "Spec type: [s]hort (1-liner), [d]etailed (full spec)",
                    default="s"
                ).lower()
                
                if spec_type == "d":
                    # Will create full spec later
                    resolved.append({
                        "question": question,
                        "decision": f"Future spec to be created: {question}",
                        "category": category,
                        "future_spec": True
                    })
                    Console.success(f"Marked for future detailed spec")
                else:
                    # Short spec - just note it
                    resolved.append({
                        "question": question,
                        "decision": f"Future enhancement: {question}",
                        "category": category,
                        "future_short": True
                    })
                    Console.success("Marked as future enhancement")
                    
            elif choice == "c":
                Console.log("Planning cancelled")
                return [], spec_content
        
        # Apply spec updates
        if spec_updates:
            updates_text = "\n".join([f"- {u}" for u in spec_updates])
            
            # Replace Open Questions section or add Resolved Questions
            if "## Open Questions" in spec_content:
                # Add resolved questions after open questions
                spec_content = spec_content.replace(
                    "## Open Questions",
                    f"## Resolved Questions (Pre-Planning)\n{updates_text}\n\n## Open Questions"
                )
            else:
                spec_content += f"\n\n## Resolved Questions (Pre-Planning)\n{updates_text}\n"
            
            spec_file.write_text(spec_content)
            Console.success(f"Spec updated with {len(spec_updates)} resolved question(s)")
        
        return resolved, spec_content

    # -------------------------------------------------------------------------
    # Command: epic (Create or manage epics)
    # -------------------------------------------------------------------------
    def cmd_epic(self, name: str = None, epic_id: str = None, 
                 spec: str = None, stories: str = None,
                 add: str = None, remove: str = None) -> bool:
        """Create or manage epics for grouping related stories"""
        if not self._require_init():
            return False
        
        # Case 1: Show epic details (epic_id provided, no other flags)
        if epic_id and not name and not add and not remove:
            return self._show_epic(epic_id)
        
        # Case 2: Create new epic (name provided)
        if name:
            return self._create_epic(name, spec, stories)
        
        # Case 3: Add story to epic
        if epic_id and add:
            return self._add_story_to_epic(epic_id, add)
        
        # Case 4: Remove story from epic
        if epic_id and remove:
            return self._remove_story_from_epic(epic_id, remove)
        
        # No valid action
        Console.error("Invalid epic command.")
        print("\n Usage:")
        print("   speky epic \"Epic Name\" --spec 006     # Create epic")
        print("   speky epic E001                        # Show epic details")
        print("   speky epic E001 --add F005             # Add story to epic")
        print("   speky epic E001 --remove F005          # Remove story from epic")
        return False

    def _create_epic(self, name: str, related_spec: str = None, stories_str: str = None) -> bool:
        """Create a new epic"""
        Console.header(f"Create Epic: {name}")
        
        # Get next epic ID
        next_num = self._next_item_number(self.context.epics_dir, "E")
        epic_id = f"E{next_num:03d}"
        
        # Create epic directory
        slug = self._slugify(name)
        epic_dir = self.context.epics_dir / f"{epic_id}-{slug}"
        epic_dir.mkdir(parents=True, exist_ok=True)
        
        # Parse stories if provided
        story_list = []
        if stories_str:
            story_list = [s.strip() for s in stories_str.split(',') if s.strip()]
            # Validate stories exist
            valid_stories = []
            for sid in story_list:
                if self._find_story_dir(sid):
                    valid_stories.append(sid)
                else:
                    Console.warning(f"Story {sid} not found, skipping")
            story_list = valid_stories
        
        # Create manifest
        manifest = {
            "id": epic_id,
            "name": name,
            "description": f"Epic for grouping related stories",
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
            "related_spec": related_spec,
            "priority": "P1",
            "stories": story_list,
            "docs": []
        }
        
        # Save manifest
        import yaml
        manifest_file = epic_dir / "manifest.yaml"
        with open(manifest_file, 'w') as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        
        # Update stories to reference this epic
        for sid in story_list:
            story_dir = self._find_story_dir(sid)
            if story_dir:
                status_file = story_dir / "status.json"
                if status_file.exists():
                    status = json.loads(status_file.read_text())
                    status['related_epic'] = epic_id
                    status_file.write_text(json.dumps(status, indent=2))
        
        Console.success(f"Epic created: {epic_id} - {name}")
        Console.files_created([
            f"{SPEKY_DIR}/{EPICS_DIR}/{epic_dir.name}/manifest.yaml"
        ])
        
        print(f"\n Next steps:")
        print(f"   - Add stories: speky epic {epic_id} --add F001")
        print(f"   - Create story in epic: speky story \"Title\" --epic {epic_id}")
        print(f"   - Add shared docs: Create files in .speky/epics/{epic_dir.name}/")
        
        if related_spec:
            print(f"\n Related to Spec {related_spec}")
        
        return True

    def _show_epic(self, epic_id: str) -> bool:
        """Show epic details with story status"""
        epic = self._load_epic(epic_id)
        if not epic:
            Console.error(f"Epic not found: {epic_id}")
            return False
        
        Console.header(f"Epic: {epic['name']} ({epic['id']})")
        
        print(f"\n Description: {epic.get('description', '(none)')}")
        print(f" Related Spec: {epic.get('related_spec') or '(none)'}")
        print(f" Priority: {epic.get('priority', 'P1')}")
        print(f" Created: {epic.get('created', 'unknown')[:10]}")
        
        # Show progress
        status = self._get_epic_status(epic_id)
        total = status['total']
        completed = status['completed']
        in_progress = status['in_progress']
        pending = status['pending']
        
        print(f"\n Progress: {completed}/{total} stories complete")
        if total > 0:
            pct = int((completed / total) * 100)
            bar = "=" * (pct // 5) + "-" * (20 - pct // 5)
            print(f"   [{bar}] {pct}%")
        
        # Show stories
        print(f"\n Stories:")
        story_ids = epic.get('stories', [])
        if not story_ids:
            print("   (no stories yet)")
        else:
            for sid in story_ids:
                story_dir = self._find_story_dir(sid)
                if story_dir:
                    status_file = story_dir / "status.json"
                    if status_file.exists():
                        s = json.loads(status_file.read_text())
                        if s.get('status') in ['completed', 'done']:
                            icon = "[DONE]"
                        elif s.get('status') == 'in_progress':
                            icon = "[WIP]"
                        else:
                            icon = "[ ]"
                        print(f"   {icon} {sid}: {s.get('title', 'Untitled')}")
                else:
                    print(f"   [?] {sid}: (not found)")
        
        # Show shared docs
        epic_dir = epic.get('_dir')
        if epic_dir:
            docs = [f for f in epic_dir.iterdir() if f.suffix == '.md']
            if docs:
                print(f"\n Shared Documents:")
                for doc in docs:
                    print(f"   - {doc.name}")
        
        return True

    def _add_story_to_epic(self, epic_id: str, story_id: str) -> bool:
        """Add a story to an epic"""
        epic = self._load_epic(epic_id)
        if not epic:
            Console.error(f"Epic not found: {epic_id}")
            return False
        
        story_dir = self._find_story_dir(story_id)
        if not story_dir:
            Console.error(f"Story not found: {story_id}")
            return False
        
        # Add to epic manifest
        stories = epic.get('stories', [])
        if story_id in stories:
            Console.warning(f"Story {story_id} already in epic {epic_id}")
            return True
        
        stories.append(story_id)
        epic['stories'] = stories
        epic['updated'] = datetime.now().isoformat()
        self._save_epic(epic_id, epic)
        
        # Update story status.json
        status_file = story_dir / "status.json"
        if status_file.exists():
            status = json.loads(status_file.read_text())
            status['related_epic'] = epic_id
            # Also add epic's related spec to story's related_specs
            if epic.get('related_spec'):
                related_specs = status.get('related_specs', [])
                if epic['related_spec'] not in related_specs:
                    related_specs.append(epic['related_spec'])
                status['related_specs'] = related_specs
            status_file.write_text(json.dumps(status, indent=2))
        
        Console.success(f"Added {story_id} to epic {epic_id}")
        return True

    def _remove_story_from_epic(self, epic_id: str, story_id: str) -> bool:
        """Remove a story from an epic"""
        epic = self._load_epic(epic_id)
        if not epic:
            Console.error(f"Epic not found: {epic_id}")
            return False
        
        # Remove from epic manifest
        stories = epic.get('stories', [])
        if story_id not in stories:
            Console.warning(f"Story {story_id} not in epic {epic_id}")
            return True
        
        stories.remove(story_id)
        epic['stories'] = stories
        epic['updated'] = datetime.now().isoformat()
        self._save_epic(epic_id, epic)
        
        # Update story status.json
        story_dir = self._find_story_dir(story_id)
        if story_dir:
            status_file = story_dir / "status.json"
            if status_file.exists():
                status = json.loads(status_file.read_text())
                status['related_epic'] = None
                status_file.write_text(json.dumps(status, indent=2))
        
        Console.success(f"Removed {story_id} from epic {epic_id}")
        return True

    # -------------------------------------------------------------------------
    # Command: epics (List all epics)
    # -------------------------------------------------------------------------
    def cmd_epics(self) -> bool:
        """List all epics with status"""
        if not self._require_init():
            return False
        
        Console.header("Epics")
        
        epics = self._get_all_epics()
        if not epics:
            print("   No epics found.")
            print("\n Create one: speky epic \"Epic Name\" --spec 001")
            return True
        
        for epic in epics:
            epic_id = epic['id']
            status = epic.get('status', {})
            total = status.get('total', 0)
            completed = status.get('completed', 0)
            
            # Status indicator
            if total == 0:
                indicator = "(empty)"
            elif completed == total:
                indicator = "[COMPLETE]"
            elif status.get('in_progress', 0) > 0:
                indicator = f"({completed}/{total} done)"
            else:
                indicator = f"({completed}/{total} done)"
            
            print(f"\n   {epic_id}: {epic['name']} {indicator}")
            if epic.get('related_spec'):
                print(f"   Related to Spec {epic['related_spec']}")
            
            # Show first 3 stories
            story_ids = epic.get('stories', [])[:3]
            for sid in story_ids:
                story_dir = self._find_story_dir(sid)
                if story_dir:
                    status_file = story_dir / "status.json"
                    if status_file.exists():
                        s = json.loads(status_file.read_text())
                        icon = "[x]" if s.get('status') in ['completed', 'done'] else "[ ]"
                        print(f"      {icon} {sid}: {s.get('title', 'Untitled')[:40]}")
            
            if len(epic.get('stories', [])) > 3:
                remaining = len(epic['stories']) - 3
                print(f"      ... and {remaining} more")
        
        return True

    # -------------------------------------------------------------------------
    # Command: story
    # -------------------------------------------------------------------------
    def cmd_story(self, title: str, story_type: str = "feature", 
                  epic: str = None, spec: str = None, specs: str = None,
                  files: str = None, no_spec: bool = False,
                  from_backlog: bool = False, backlog_source: dict = None) -> bool:
        """Create a story (feature, bug, enhancement, etc.) for ongoing development"""
        if not self._require_init():
            return False
        
        # Validate story type
        try:
            stype = StoryType(story_type.lower())
        except ValueError:
            Console.error(f"Invalid story type: {story_type}")
            print(f"   Valid types: {', '.join(t.value for t in StoryType)}")
            return False
        
        Console.header(f"Create Story: [{stype.value.upper()}] {title}")
        
        # Determine related specs
        related_specs = []
        if not no_spec:
            if spec:
                related_specs = [spec]
            elif specs:
                related_specs = [s.strip() for s in specs.split(',') if s.strip()]
            elif epic:
                # Get spec from epic
                epic_data = self._load_epic(epic)
                if epic_data and epic_data.get('related_spec'):
                    related_specs = [epic_data['related_spec']]
            else:
                # Auto-detect related specs
                detected = self._detect_related_specs(title)
                if detected:
                    print(f"\n Detected related spec(s): {', '.join(detected)}")
                    if Console.confirm("Link to these specs?"):
                        related_specs = detected
        
        # Parse affected files
        affected_files = []
        if files:
            affected_files = [f.strip() for f in files.split(',') if f.strip()]
        
        # Get next story ID with prefix
        prefix = stype.value[0].upper()  # F, B, E, T, S
        next_num = self._next_item_number(self.context.stories_dir, prefix)
        story_id = f"{prefix}{next_num:03d}"
        
        # Create story directory
        slug = self._slugify(title)
        story_dir = self.context.stories_dir / f"{story_id}-{slug}"
        story_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate story with context
        Console.section("Generating Story")
        product_context = self.context.get_product_context()
        
        # Build extra context
        extra_context = ""
        if from_backlog and backlog_source:
            extra_context += f"""
This story originated from a deferred validation item:
- Original issue: {backlog_source.get('item', '')}
- Type: {backlog_source.get('type', '')}
- Source spec: {backlog_source.get('source_spec', '')}
- User notes: {backlog_source.get('notes', '')}
"""
        
        # Add related spec context
        if related_specs:
            extra_context += "\n\nRELATED SPECIFICATIONS:\n"
            for spec_id in related_specs[:2]:  # Limit to 2 specs for context
                spec_content = self._get_spec_content_brief(spec_id)
                if spec_content:
                    extra_context += f"\n--- Spec {spec_id} ---\n{spec_content}\n"
        
        # Add epic context
        if epic:
            epic_data = self._load_epic(epic)
            if epic_data:
                extra_context += f"\n\nEPIC CONTEXT:\n"
                extra_context += f"Epic: {epic_data['name']}\n"
                extra_context += f"Description: {epic_data.get('description', '')}\n"
        
        story_content = self.ai.query(Prompts.generate_story(stype.value, title, product_context + extra_context))
        
        if not story_content:
            Console.error("Failed to generate story")
            return False
        
        (story_dir / "story.md").write_text(story_content)
        
        # Create status with new fields
        status = {
            "id": story_id,
            "title": title,
            "type": stype.value,
            "status": ItemStatus.DRAFT.value,
            "created": datetime.now().isoformat(),
            "related_specs": related_specs,
            "related_epic": epic,
            "affected_files": affected_files
        }
        
        # Add backlog source if from deferred item
        if from_backlog and backlog_source:
            status["from_backlog"] = True
            status["backlog_source"] = backlog_source.get("source_spec", "")
        
        (story_dir / "status.json").write_text(json.dumps(status, indent=2))
        
        # If epic specified, add story to epic
        if epic:
            self._add_story_to_epic(epic, story_id)
        
        # Update context
        data = self.context.data
        data["stories"].append({"id": story_id, "title": title, "type": stype.value, "dir": str(story_dir.name)})
        self.context.save(data)
        
        Console.success(f"Story created: {story_dir.name}")
        Console.files_created([f"{SPEKY_DIR}/{STORIES_DIR}/{story_dir.name}/story.md"])
        
        # Show context info
        if related_specs:
            print(f"\n Linked to spec(s): {', '.join(related_specs)}")
        if epic:
            print(f" Part of epic: {epic}")
        if affected_files:
            print(f" Affected files: {len(affected_files)} file(s)")
        
        return True

    def _detect_related_specs(self, title: str, description: str = "") -> List[str]:
        """AI-powered detection of related specs based on story title"""
        # Get all specs summary
        all_specs = []
        for spec_dir in self.context.specs_dir.glob("*/"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    all_specs.append(f"{status.get('id', spec_dir.name[:3])}: {status.get('name', spec_dir.name)}")
                except:
                    pass
        
        if not all_specs:
            return []
        
        # Simple keyword matching (no AI call for speed)
        title_lower = title.lower()
        matches = []
        
        for spec_info in all_specs:
            spec_id = spec_info.split(':')[0].strip()
            spec_name = spec_info.split(':')[1].strip().lower() if ':' in spec_info else ""
            
            # Check if any word from spec name appears in title
            spec_words = spec_name.split()
            for word in spec_words:
                if len(word) > 3 and word in title_lower:
                    matches.append(spec_id)
                    break
        
        return matches[:3]  # Max 3 suggestions

    def _get_spec_content_brief(self, spec_id: str) -> Optional[str]:
        """Get brief spec content for context (first 1000 chars)"""
        spec_dir = self._find_spec_dir(spec_id)
        if not spec_dir:
            return None
        
        spec_file = spec_dir / "spec.md"
        if not spec_file.exists():
            return None
        
        content = spec_file.read_text()
        if len(content) > 1000:
            return content[:1000] + "\n... (truncated)"
        return content

    # -------------------------------------------------------------------------
    # Context Chain Builder (for enhanced implement)
    # -------------------------------------------------------------------------
    def _build_context_chain(self, item_id: str, item_dir: Path) -> dict:
        """Build complete context chain for implementation
        
        Context layers (from broad to specific):
        1. Project context (always)
        2. Tech decisions (always)
        3. Phase context (if in phase)
        4. Related spec(s) (if story has related_specs)
        5. Epic context (if story is part of epic)
        6. Affected files preview (if specified)
        7. The item itself (spec or story)
        """
        is_story = self._find_story_dir(item_id) is not None
        
        chain = {
            "item_id": item_id,
            "item_type": "story" if is_story else "spec",
            "layers": []
        }
        
        # Layer 1: Project context (always)
        chain["layers"].append({
            "name": "Project Context",
            "content": self.context.get_product_context()
        })
        
        # Layer 2: Tech decisions (always)
        tech_decisions_file = self.context.context_dir / "tech_decisions.md"
        if tech_decisions_file.exists():
            chain["layers"].append({
                "name": "Tech Decisions",
                "content": tech_decisions_file.read_text()
            })
        
        # Layer 2.5: Design System (if exists)
        design_system_file = self.context.context_dir / "design_system.md"
        if design_system_file.exists():
            design_content = design_system_file.read_text()
            
            # Also load spec-specific designs if available
            spec_designs = self._get_spec_designs(item_id)
            if spec_designs:
                design_content += f"\n\n## Hi-Fi Designs for {item_id}\n"
                design_content += "⚠️ Match these designs PIXEL-PERFECT\n\n"
                design_content += spec_designs
            
            chain["layers"].append({
                "name": "Design System",
                "content": design_content
            })
        
        # Layer 3: Phase context (if applicable)
        phase = self._get_spec_phase(item_id)
        if not phase and is_story:
            phase = self._get_story_phase(item_id)
        
        if phase:
            phase_id = phase.get("id", phase.get("_dir", "unknown"))
            phase_guide = self.context.phases_dir / phase_id / "implementation.md"
            phase_content = f"Phase: {phase.get('name', phase_id)}\n"
            if phase_guide.exists():
                phase_content += phase_guide.read_text()
            chain["layers"].append({
                "name": f"Phase: {phase.get('name', phase_id)}",
                "content": phase_content
            })
        
        # For stories, load additional context
        if is_story:
            status_file = item_dir / "status.json"
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    
                    # Layer 4: Related specs
                    related_specs = status.get("related_specs", [])
                    for spec_id in related_specs[:2]:  # Limit to 2 specs
                        spec_content = self._get_spec_content_brief(spec_id)
                        if spec_content:
                            chain["layers"].append({
                                "name": f"Related Spec: {spec_id}",
                                "content": spec_content
                            })
                    
                    # Layer 5: Epic context
                    epic_id = status.get("related_epic")
                    if epic_id:
                        epic_context = self._get_epic_context_for_implementation(epic_id)
                        if epic_context:
                            chain["layers"].append({
                                "name": f"Epic: {epic_id}",
                                "content": epic_context
                            })
                    
                    # Layer 6: Affected files preview
                    affected_files = status.get("affected_files", [])
                    if affected_files:
                        files_preview = self._preview_affected_files(affected_files)
                        if files_preview:
                            chain["layers"].append({
                                "name": "Affected Files",
                                "content": files_preview
                            })
                except:
                    pass
        
        # Layer 7: The item itself (spec or story)
        spec_file = item_dir / "spec.md"
        story_file = item_dir / "story.md"
        plan_file = item_dir / "plan.md"
        
        item_content = ""
        if spec_file.exists():
            item_content += f"## Specification\n\n{spec_file.read_text()}\n\n"
        if story_file.exists():
            item_content += f"## Story\n\n{story_file.read_text()}\n\n"
        if plan_file.exists():
            item_content += f"## Implementation Plan\n\n{plan_file.read_text()}\n\n"
        
        if item_content:
            chain["layers"].append({
                "name": f"{'Story' if is_story else 'Spec'}: {item_id}",
                "content": item_content
            })
        
        return chain

    def _build_implementation_context(self, item_id: str, item_dir: Path, is_story: bool, 
                                       task_title: str, context_chain: dict) -> dict:
        """Build comprehensive implementation context for focused IDE rules
        
        This context is used during implementation mode to provide all relevant
        information directly in the task context file, while keeping SPEKY rules minimal.
        
        Args:
            item_id: The spec or story ID
            item_dir: Path to the item directory
            is_story: True if this is a story, False if spec
            task_title: Title of the task
            context_chain: The context chain from _build_context_chain()
            
        Returns:
            Dict with all context needed for implementation
        """
        ctx = {
            "item_id": item_id,
            "item_type": "story" if is_story else "spec",
            "item_title": task_title,
            "item_dir_name": item_dir.name,
        }
        
        # Extract content from context chain layers
        for layer in context_chain.get("layers", []):
            layer_name = layer.get("name", "")
            content = layer.get("content", "")
            
            if "Tech Decisions" in layer_name:
                ctx["tech_decisions"] = content
            elif "Design System" in layer_name:
                ctx["design_system"] = content
            elif layer_name.startswith("Phase:"):
                ctx["phase_name"] = layer_name.replace("Phase:", "").strip()
                ctx["phase_id"] = layer_name.split("(")[-1].rstrip(")") if "(" in layer_name else ""
            elif layer_name.startswith("Related Spec:"):
                existing = ctx.get("related_specs", "")
                ctx["related_specs"] = existing + f"\n### {layer_name}\n{content}\n"
            elif layer_name.startswith("Epic:"):
                ctx["epic_context"] = content
            elif "Affected Files" in layer_name:
                ctx["affected_files"] = content
            elif layer_name.startswith("Spec:") or layer_name.startswith("Story:"):
                # This is the main item content - parse it
                if "## Specification" in content:
                    spec_start = content.find("## Specification")
                    spec_end = content.find("## ", spec_start + 1)
                    ctx["spec_content"] = content[spec_start:spec_end if spec_end > 0 else None].strip()
                if "## Story" in content:
                    story_start = content.find("## Story")
                    story_end = content.find("## ", story_start + 1)
                    ctx["story_content"] = content[story_start:story_end if story_end > 0 else None].strip()
                if "## Implementation Plan" in content:
                    plan_start = content.find("## Implementation Plan")
                    ctx["plan_content"] = content[plan_start:].strip()
        
        # Load spec/story content directly if not in chain
        spec_file = item_dir / "spec.md"
        story_file = item_dir / "story.md"
        plan_file = item_dir / "plan.md"
        
        if not ctx.get("spec_content") and spec_file.exists():
            ctx["spec_content"] = spec_file.read_text()
        if not ctx.get("story_content") and story_file.exists():
            ctx["story_content"] = story_file.read_text()
        if not ctx.get("plan_content") and plan_file.exists():
            ctx["plan_content"] = plan_file.read_text()
        
        # Load tech decisions directly if not in chain
        if not ctx.get("tech_decisions"):
            tech_file = self.context.context_dir / "tech_decisions.md"
            if tech_file.exists():
                ctx["tech_decisions"] = tech_file.read_text()
        
        # Load design system directly if not in chain
        if not ctx.get("design_system"):
            design_file = self.context.context_dir / "design_system.md"
            if design_file.exists():
                ctx["design_system"] = design_file.read_text()
        
        # Build context summary for stories
        if is_story:
            status_file = item_dir / "status.json"
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    summary_parts = []
                    if status.get("related_specs"):
                        summary_parts.append(f"Related Specs: {', '.join(status['related_specs'])}")
                    if status.get("related_epic"):
                        summary_parts.append(f"Epic: {status['related_epic']}")
                    if status.get("affected_files"):
                        summary_parts.append(f"Affected Files: {len(status['affected_files'])} file(s)")
                    if summary_parts:
                        ctx["context_summary"] = " | ".join(summary_parts)
                except:
                    pass
        
        return ctx

    def _get_story_phase(self, story_id: str) -> Optional[dict]:
        """Get phase for a story (via epic or related spec)"""
        story_dir = self._find_story_dir(story_id)
        if not story_dir:
            return None
        
        status_file = story_dir / "status.json"
        if not status_file.exists():
            return None
        
        try:
            status = json.loads(status_file.read_text())
            
            # Check if story is in an epic
            epic_id = status.get("related_epic")
            if epic_id:
                epic = self._load_epic(epic_id)
                if epic and epic.get("related_spec"):
                    return self._get_spec_phase(epic["related_spec"])
            
            # Check if story has related specs
            related_specs = status.get("related_specs", [])
            if related_specs:
                return self._get_spec_phase(related_specs[0])
        except:
            pass
        
        return None

    def _get_spec_designs(self, item_id: str) -> Optional[str]:
        """Get design analyses linked to a spec"""
        design_dir = self.context.speky_dir / DESIGN_DIR
        manifest_file = design_dir / "manifest.json"
        
        if not manifest_file.exists():
            return None
        
        try:
            manifest = json.loads(manifest_file.read_text())
        except:
            return None
        
        # Find designs linked to this spec
        linked_analyses = []
        
        for img_type in ["hifi", "lofi"]:
            for img in manifest.get(f"{img_type}_images", []):
                related_specs = img.get("related_specs", [])
                # Match by spec ID (e.g., "007" matches "007-feature-name")
                if any(item_id.startswith(spec) or spec.startswith(item_id) for spec in related_specs):
                    # Load analysis if available
                    if img.get("analysis_path"):
                        analysis_path = self.context.speky_dir / img["analysis_path"]
                        if analysis_path.exists():
                            analysis_content = analysis_path.read_text()
                            linked_analyses.append(
                                f"### {img['filename']} ({img_type.upper()})\n\n{analysis_content[:2000]}"
                            )
        
        if linked_analyses:
            return "\n\n---\n\n".join(linked_analyses)
        
        return None

    def _get_epic_context_for_implementation(self, epic_id: str) -> Optional[str]:
        """Get epic context including shared docs for implementation"""
        epic = self._load_epic(epic_id)
        if not epic:
            return None
        
        epic_dir = epic.get('_dir')
        if not epic_dir:
            return None
        
        context_parts = []
        
        # Epic overview
        context_parts.append(f"# Epic: {epic['name']}")
        context_parts.append(f"Description: {epic.get('description', '(none)')}")
        
        # Related spec
        if epic.get('related_spec'):
            context_parts.append(f"\nThis epic enhances Spec {epic['related_spec']}")
        
        # Shared technical spec
        tech_spec = epic_dir / "technical_spec.md"
        if tech_spec.exists():
            context_parts.append(f"\n## Shared Technical Decisions\n\n{tech_spec.read_text()}")
        
        # Summary
        summary = epic_dir / "summary.md"
        if summary.exists():
            context_parts.append(f"\n## Epic Summary\n\n{summary.read_text()}")
        
        # Other stories in epic (for context)
        stories = epic.get('stories', [])
        if stories:
            context_parts.append(f"\n## Other Stories in Epic")
            for sid in stories[:5]:
                story_dir = self._find_story_dir(sid)
                if story_dir:
                    status_file = story_dir / "status.json"
                    if status_file.exists():
                        try:
                            s = json.loads(status_file.read_text())
                            status_icon = "[DONE]" if s.get('status') in ['completed', 'done'] else "[ ]"
                            context_parts.append(f"- {status_icon} {sid}: {s.get('title', 'Untitled')}")
                        except:
                            pass
        
        return "\n".join(context_parts)

    def _preview_affected_files(self, file_paths: List[str]) -> str:
        """Preview affected files (first 30 lines each)"""
        previews = []
        
        for file_path in file_paths[:3]:  # Max 3 files
            full_path = self.context.project_root / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text()
                    lines = content.split('\n')[:30]
                    preview = '\n'.join(lines)
                    if len(content.split('\n')) > 30:
                        preview += "\n... (truncated)"
                    previews.append(f"### {file_path}\n```\n{preview}\n```")
                except:
                    previews.append(f"### {file_path}\n(Could not read file)")
        
        return "\n\n".join(previews) if previews else ""

    # -------------------------------------------------------------------------
    # Command: implement
    # -------------------------------------------------------------------------
    def cmd_implement(self, item_id: str, tdd: bool = False) -> bool:
        """Hand off spec or story to IDE for implementation with full context chain"""
        if not self._require_init():
            return False
        
        # Header based on mode
        if tdd:
            Console.header(f"Implement: {item_id} (TDD Mode)")
        else:
            Console.header(f"Implement: {item_id}")
        
        # Find the item (spec or story)
        item_dir = self._find_spec_dir(item_id) or self._find_story_dir(item_id)
        
        if not item_dir:
            Console.error(f"Item not found: {item_id}")
            return False
        
        is_story = self._find_story_dir(item_id) is not None
        
        # Check dependencies before implementing (only for specs)
        if not is_story:
            dep_validation = self._validate_dependencies(item_id)
            if not dep_validation.get("valid", True):
                self._show_dependency_warning(item_id, dep_validation)
                if not Console.confirm("Continue anyway?", default=False):
                    Console.log("Run 'speky sequence' to see recommended order")
                    return False
            
            # Check for pending validation actions (specs only)
            if not self._warn_pending_validation_actions(item_dir, "implement"):
                return False
        
        # Build context chain
        Console.section("Building Context Chain")
        context_chain = self._build_context_chain(item_id, item_dir)
        
        # Show what context is being loaded
        print(f"   Loading {len(context_chain['layers'])} context layers:")
        for layer in context_chain['layers']:
            print(f"   - {layer['name']}")
        
        # Combine context for AI
        combined_context = ""
        for layer in context_chain['layers']:
            combined_context += f"\n{'='*60}\n"
            combined_context += f"CONTEXT: {layer['name']}\n"
            combined_context += f"{'='*60}\n\n"
            combined_context += layer['content']
            combined_context += "\n\n"
        
        # Generate IDE context (brief summary for product context section)
        Console.section("Preparing IDE Context (Implementation Mode)")
        ide_context = self.ai.query(Prompts.generate_ide_context(
            self.context.get_product_context(), 
            combined_context
        ))
        
        # Build active task summary for IDE rules
        status_file = item_dir / "status.json"
        task_name = item_id
        task_title = item_id
        if status_file.exists():
            status_data = json.loads(status_file.read_text())
            task_name = status_data.get("name", status_data.get("title", item_id))
            task_title = status_data.get("title", item_id)
        
        # Build comprehensive implementation context for focused IDE rules
        impl_context = self._build_implementation_context(
            item_id=item_id,
            item_dir=item_dir,
            is_story=is_story,
            task_title=task_title,
            context_chain=context_chain
        )
        
        # Set implementation mode with comprehensive context
        # This makes IDE rules focused on implementation, not SPEKY commands
        self.ide.set_implementation_mode(enabled=True, task_context=impl_context)
        
        # Build legacy active_task string for backward compat with single-file IDEs
        context_summary = []
        if is_story:
            status = json.loads(status_file.read_text()) if status_file.exists() else {}
            if status.get("related_specs"):
                context_summary.append(f"Related Specs: {', '.join(status['related_specs'])}")
            if status.get("related_epic"):
                context_summary.append(f"Epic: {status['related_epic']}")
            if status.get("affected_files"):
                context_summary.append(f"Affected Files: {len(status['affected_files'])} file(s)")
        
        # Check if spec/story is part of a phase
        phase_context = ""
        current_phase = self._get_spec_phase(item_id)
        if not current_phase and is_story:
            current_phase = self._get_story_phase(item_id)
        
        if current_phase:
            phase_id = current_phase.get("id", current_phase.get("_dir", "unknown"))
            phase_name = current_phase.get("name", "Unnamed")
            phase_context = f"""
**Phase**: {phase_name} ({phase_id})
**Phase Guide**: `.speky/phases/{phase_id}/implementation.md` (if exists)

Stay within phase scope. Check phase excludes before implementing."""
        
        item_type = "Story" if is_story else "Spec"
        item_path = f".speky/{'stories' if is_story else 'specs'}/{item_dir.name}"
        
        active_task = f"""**Implementing**: {task_title} (ID: {item_id})

**{item_type}**: `{item_path}/{'story' if is_story else 'spec'}.md`"""
        
        if context_summary:
            active_task += f"\n**Context**: {' | '.join(context_summary)}"
        
        active_task += phase_context
        active_task += "\n\nFocus on implementing the code. Do NOT create extra documentation files."
        
        # Update all enabled IDEs with implementation-focused context
        if ide_context:
            self.ide.update_all_enabled_ides(ide_context, active_task)
        
        # Update status to in_progress
        if status_file.exists():
            status = json.loads(status_file.read_text())
            status["status"] = ItemStatus.IN_PROGRESS.value
            status["implementation_started"] = datetime.now().isoformat()
            status_file.write_text(json.dumps(status, indent=2))
        
        Console.success("IDE context updated with full context chain")
        
        # If TDD mode, now start the TDD workflow (after context is loaded)
        if tdd:
            try:
                from speky_testing import TestingIntegration
                testing = TestingIntegration(speky_instance=self)
                result = testing.start_tdd_workflow(item_id, task_title)
                
                if result.get("success"):
                    print(f"\n📋 TDD Task: {result.get('task_file')}")
                    print("\n📝 Next Steps:")
                    for step in result.get("next_steps", []):
                        print(f"   {step}")
                else:
                    Console.error(result.get("message", "TDD workflow failed"))
                    return False
                
                # Offer to open IDE
                if Console.confirm(f"Open {self.config.get('ide', 'windsurf')}?"):
                    self.ide.open_ide()
                
                return True
                
            except ImportError:
                Console.error("Testing integration not available. Install with: pip install -r requirements.txt")
                return False
            except Exception as e:
                Console.error(f"Failed to start TDD workflow: {e}")
                return False
        
        # Regular (non-TDD) flow: Offer to open IDE
        if Console.confirm(f"Open {self.config.get('ide', 'windsurf')}?"):
            self.ide.open_ide()
        
        print(f"\n Implementation context written to: {self.ide.RULES_FILES.get(self.config.get('ide'))}")
        print(f"   Start coding in your IDE with full context!")
        
        return True

    # -------------------------------------------------------------------------
    # Drift Types
    # -------------------------------------------------------------------------
    DRIFT_TYPES = {
        "SPEC_BEHIND": "Implementation has features not in spec (spec needs update)",
        "CODE_BEHIND": "Spec has features not yet implemented (for next iteration)",
        "SCOPE_CREEP": "Implemented out-of-scope items (document or remove)",
        "TECH_DEVIATION": "Different technical approach than specified (update spec or refactor)",
        "DOC_STALE": "Documentation doesn't match implementation (update docs)",
    }

    # -------------------------------------------------------------------------
    # Command: complete
    # -------------------------------------------------------------------------
    def cmd_complete(self, item_id: str, run_tests: bool = False, test_type: str = "all") -> bool:
        """Mark a spec or story as complete (with drift detection for specs)
        
        Args:
            item_id: Spec ID (001) or Story ID (F001, B001, etc.)
            run_tests: If True, run tests before marking complete
            test_type: Type of tests to run (unit, integration, e2e, all)
        """
        if not self._require_init():
            return False
        
        Console.header(f"✅ Complete: {item_id}")
        
        # Run tests if requested (via --test flag)
        if run_tests:
            if self.testing:
                Console.section("🧪 Running Tests", f"Testing before completion (type: {test_type})")
                test_result = self.testing.run_tests_for_spec(item_id, test_type)
                
                if not test_result.get("passed", False):
                    Console.error(f"Tests failed: {test_result.get('summary', 'Unknown error')}")
                    for detail in test_result.get("details", []):
                        print(f"   • {detail}")
                    Console.warning("Fix failing tests before marking complete.")
                    Console.log(f"Run 'speky test run --spec {item_id}' to see details")
                    return False
                else:
                    Console.success(f"Tests passed: {test_result.get('summary', 'All tests passed')}")
            else:
                Console.warning("Testing module not available. Skipping tests.")
                Console.log("Run 'speky test init' to set up testing.")
        
        # Determine if this is a spec or story
        is_story = item_id[0].isalpha() and len(item_id) >= 4  # F001, B001, etc.
        
        if is_story:
            return self._complete_story(item_id)
        else:
            return self._complete_spec(item_id)
    
    def _restore_full_ide_context(self):
        """Clear implementation mode and restore full SPEKY rules to all enabled IDEs
        
        Called after speky complete to restore comprehensive SPEKY guidance
        for normal workflow (spec creation, stories, commands, etc.)
        """
        # Clear implementation mode
        self.ide.set_implementation_mode(enabled=False)
        
        # Restore full context to all enabled IDEs
        Console.log("Restoring full SPEKY context to IDE rules...")
        product_context = self.context.get_product_context()
        self.ide.update_all_enabled_ides(product_context, active_task="")
        Console.success("IDE rules restored to full SPEKY mode")
    
    def _complete_story(self, story_id: str) -> bool:
        """Mark a story as complete (simpler workflow than specs)"""
        # Find story
        story_dir = self._find_story_dir(story_id)
        if not story_dir:
            Console.error(f"Story not found: {story_id}")
            return False
        
        status_file = story_dir / "status.json"
        if not status_file.exists():
            Console.error(f"Status file not found: {status_file}")
            return False
        
        status = json.loads(status_file.read_text())
        story_title = status.get("title", story_id)
        
        # Update status
        status["status"] = ItemStatus.COMPLETED.value
        status["completed"] = datetime.now().isoformat()
        status_file.write_text(json.dumps(status, indent=2))
        
        Console.success(f"Story completed: {story_title}")
        
        # Clear implementation mode and restore full SPEKY rules
        self._restore_full_ide_context()
        
        # Check if story is part of an epic
        related_epic = status.get("related_epic")
        if related_epic:
            epic_dir = self._find_epic_dir(related_epic)
            if epic_dir:
                epic_status = self._get_epic_status(related_epic)
                Console.log(f"Epic: {related_epic} ({epic_status['completed']}/{epic_status['total']} stories completed)")
        
        # Show next steps
        Console.section("Next Steps")
        print("1. Commit your changes:")
        print(f"   git add <the files you changed>")
        print(f"   git commit -m \"feat({story_id}): {story_title}\"")
        print(f"   git push")
        
        if related_epic:
            print(f"\n2. Check epic progress:")
            print(f"   speky epic {related_epic}")
            print(f"\n3. Implement next story in epic:")
            print(f"   speky status  # See remaining stories")
        else:
            print(f"\n2. Check overall status:")
            print(f"   speky status")
        
        return True
    
    def _complete_spec(self, spec_id: str) -> bool:
        """Mark a spec as complete with categorized drift detection and interactive resolution"""
        # Find spec
        spec_dir = self._find_spec_dir(spec_id)
        if not spec_dir:
            Console.error(f"Spec not found: {spec_id}")
            return False
        
        status_file = spec_dir / "status.json"
        if not status_file.exists():
            Console.error(f"Status file not found: {status_file}")
            return False
        
        status = json.loads(status_file.read_text())
        feature_name = status.get("name", spec_id)
        spec_file = spec_dir / "spec.md"
        
        if not spec_file.exists():
            Console.error(f"Spec file not found: {spec_file}")
            return False
        
        spec_content = spec_file.read_text()
        product_context = self.context.get_product_context()
        
        # Step 1: Categorized Drift Detection
        Console.section("Drift Detection", "Analyzing spec vs implementation")
        
        drift_analysis = self._detect_categorized_drift(spec_content, product_context, feature_name)
        
        if not drift_analysis["has_drift"]:
            Console.success("No drift detected - spec and implementation aligned")
        else:
            # Step 2: Interactive Drift Resolution
            Console.section("Drift Resolution", "Resolving detected drift interactively")
            
            resolved_drift = self._resolve_drift_interactively(
                drift_analysis, spec_file, spec_content, status
            )
            
            if not resolved_drift:
                Console.log("Completion cancelled. Please resolve drift manually.")
                return False
            
            # Reload spec if it was updated
            spec_content = spec_file.read_text()
        
        # Step 3: Sync codebase context
        Console.section("Syncing Context", "Updating codebase understanding")
        self.cmd_sync()
        
        # Step 4: Update status
        status["status"] = ItemStatus.COMPLETED.value
        status["completed_at"] = datetime.now().isoformat()
        status["drift_resolved"] = drift_analysis.get("resolutions", [])
        status_file.write_text(json.dumps(status, indent=2))
        Console.success(f"Status updated: {ItemStatus.COMPLETED.value}")
        
        # Step 4.5: Clear implementation mode and restore full SPEKY rules
        self._restore_full_ide_context()
        
        # Step 5: Show intelligent next steps based on plan/phase/dependencies
        Console.section("Next Steps")
        
        # Always show commit step first
        print("1. Commit your changes:")
        print(f"   speky commit {spec_id}")
        print(f"   speky commit {spec_id} --edit  # to edit message")
        
        # Get intelligent recommendations
        next_recommendations = self._get_next_spec_recommendations(spec_id)
        
        # Check if phase is complete
        if next_recommendations["phase_completed"]:
            phase_info = next_recommendations["phase_complete_info"]
            print(f"\n🎉 PHASE COMPLETE: {phase_info['phase_name']} 🎉")
            print(f"   ✅ All {phase_info['specs_completed']} specs completed!")
            
            # Show deliverables if any
            deliverables = phase_info.get("deliverables", [])
            if deliverables:
                print(f"\n   📦 Phase Deliverables ({len(deliverables)}):")
                for d in deliverables[:3]:
                    print(f"      • {d.get('name', 'Unknown')}")
                if len(deliverables) > 3:
                    print(f"      ... and {len(deliverables) - 3} more")
            
            print(f"\n2. Complete the phase:")
            print(f"   speky phases complete {phase_info['phase_id']}")
            print(f"   # This will verify deliverables and acceptance criteria")
            
            if phase_info.get("next_phase_id"):
                print(f"\n3. Start next phase:")
                print(f"   speky phases start {phase_info['next_phase_id']}")
                if phase_info.get("next_phase_name"):
                    print(f"   # Next: {phase_info['next_phase_name']}")
            else:
                print(f"\n3. View all phases:")
                print(f"   speky phases list")
            
            print(f"\n4. Push to remote:")
            print("   git push")
        
        elif next_recommendations["phase_blocked"]:
            # Phase exists but all remaining specs are blocked
            phase_info = next_recommendations["phase_info"]
            blocked_specs = next_recommendations["blocked_specs"]
            
            print(f"\n⚠️  PHASE BLOCKED: {phase_info['name']}")
            print(f"   All remaining specs in this phase have unmet dependencies")
            print(f"   Phase progress: {phase_info['progress']}%")
            
            # Show blocked specs with their dependencies
            print(f"\n   Blocked specs in phase:")
            for spec in blocked_specs[:3]:
                deps_str = ", ".join(spec["unmet_deps"])
                print(f"   ⛔ {spec['id']}: {spec['name']}")
                print(f"      Waiting for: {deps_str}")
                
                # Highlight dependencies outside phase
                if spec["deps_outside_phase"]:
                    outside_deps = ", ".join(spec["deps_outside_phase"])
                    print(f"      ⚠️  Dependencies OUTSIDE phase: {outside_deps}")
            
            if len(blocked_specs) > 3:
                print(f"   ... and {len(blocked_specs) - 3} more blocked specs")
            
            print(f"\n2. Recommended actions:")
            print(f"   Option A: Implement dependencies first (recommended)")
            
            # Find the first unmet dependency
            first_blocked = blocked_specs[0]
            if first_blocked["deps_outside_phase"]:
                first_dep = first_blocked["deps_outside_phase"][0]
                print(f"   speky plan {first_dep}")
                print(f"   speky implement {first_dep}")
                print(f"   # This will unblock {first_blocked['id']} in the phase")
            
            print(f"\n   Option B: Fix phase configuration")
            print(f"   # Edit .speky/phases/{phase_info.get('phase_id', 'phase-1')}/manifest.yaml")
            print(f"   # Add missing dependencies to phase OR remove blocked specs")
            
            print(f"\n3. View full dependency tree:")
            print("   speky sequence        # See optimal implementation order")
            print("   speky status          # See all specs status")
            
            print(f"\n4. Push to remote:")
            print("   git push")
        
        elif next_recommendations["next_in_phase"]:
            print(f"\n2. Continue with current phase:")
            next_spec = next_recommendations["next_in_phase"]
            print(f"   speky plan {next_spec['id']}")
            print(f"   speky implement {next_spec['id']}")
            print(f"   # Next: {next_spec['name']}")
            
            if next_recommendations["phase_info"]:
                phase_info = next_recommendations["phase_info"]
                print(f"   # Phase: {phase_info['name']} ({phase_info['progress']}% complete)")
            
            print(f"\n3. View roadmap and what's next:")
            print("   speky sequence        # See full implementation order")
            print("   speky status          # See all specs status")
            if next_recommendations["has_phases"]:
                print("   speky phases list     # See phase progress")
            
            print(f"\n4. Push to remote:")
            print("   git push")
        
        elif next_recommendations["unblocked_specs"]:
            print(f"\n2. Specs now unblocked (dependencies met):")
            for spec in next_recommendations["unblocked_specs"][:3]:
                print(f"   speky plan {spec['id']}  # {spec['name']}")
            if len(next_recommendations["unblocked_specs"]) > 3:
                print(f"   # ... and {len(next_recommendations['unblocked_specs']) - 3} more")
            
            print(f"\n3. View roadmap and what's next:")
            print("   speky sequence        # See full implementation order")
            print("   speky status          # See all specs status")
            if next_recommendations["has_phases"]:
                print("   speky phases list     # See phase progress")
            
            print(f"\n4. Push to remote:")
            print("   git push")
        
        elif next_recommendations["next_in_sequence"]:
            print(f"\n2. Next in implementation sequence:")
            next_spec = next_recommendations["next_in_sequence"]
            print(f"   speky plan {next_spec['id']}")
            print(f"   speky implement {next_spec['id']}")
            print(f"   # {next_spec['name']}")
            
            print(f"\n3. View roadmap and what's next:")
            print("   speky sequence        # See full implementation order")
            print("   speky status          # See all specs status")
            if next_recommendations["has_phases"]:
                print("   speky phases list     # See phase progress")
            
            print(f"\n4. Push to remote:")
            print("   git push")
        
        else:
            print(f"\n2. Create next feature:")
            print("   speky spec \"Next feature name\"")
            
            print(f"\n3. View roadmap and what's next:")
            print("   speky sequence        # See full implementation order")
            print("   speky status          # See all specs status")
            if next_recommendations["has_phases"]:
                print("   speky phases list     # See phase progress")
            
            print(f"\n4. Push to remote:")
            print("   git push")
        
        # Show test recommendations if testing is available
        self._show_test_recommendations_after_complete(spec_id)
        
        return True
    
    def _show_test_recommendations_after_complete(self, spec_id: str):
        """Show test recommendations after completing a spec (if testing module available)"""
        if not self.testing:
            return
        
        try:
            if not self.testing.is_initialized():
                # Gentle nudge to set up testing
                print(f"\n{'─'*50}")
                print("💡 Tip: Set up testing with: speky test init")
                return
            
            # Get test recommendations
            recommendations = self.testing.recommend_tests(spec_id)
            
            if recommendations.get("skip_reason"):
                # No tests needed
                return
            
            if recommendations.get("recommendations"):
                print(f"\n{'─'*50}")
                print("🧪 Test Recommendations")
                print(f"   Risk Level: {recommendations['risk_level']}")
                print(f"   Changed Files: {recommendations['changed_files']}")
                
                # Show top recommendation
                top_rec = recommendations["recommendations"][0]
                print(f"\n   Suggested: {top_rec['type'].upper()} tests ({top_rec['estimated_time']})")
                
                if recommendations.get("command"):
                    print(f"\n   Run: {recommendations['command']}")
                    print(f"   Or:  speky test recommend  # for full analysis")
        except Exception:
            pass  # Silent fail - don't interrupt completion flow
    
    def _check_phase_blocking(self, phase: dict, all_specs: list) -> list:
        """Check if phase has specs blocked by external dependencies
        
        Returns list of blocked specs with their dependency info
        """
        phase_specs_raw = [s.get("id") if isinstance(s, dict) else s for s in phase.get("specs", [])]
        
        # Normalize phase spec IDs (handle both "006" and "006-name" formats)
        phase_specs = []
        for spec_ref in phase_specs_raw:
            # Extract just the numeric ID (e.g., "006" from "006-spaces")
            spec_id = spec_ref.split("-")[0] if "-" in spec_ref else spec_ref
            phase_specs.append(spec_id)
        
        blocked_specs = []
        
        for spec_id in phase_specs:
            spec_status = next((s for s in all_specs if s.get("id") == spec_id), None)
            if not spec_status or spec_status.get("status") == "completed":
                continue
            
            deps = spec_status.get("dependencies", [])
            if not deps:
                continue
            
            # Check which dependencies are unmet and outside phase
            unmet_deps = []
            deps_outside_phase = []
            
            for dep in deps:
                dep_spec = next((s for s in all_specs if s.get("id") == dep), None)
                if dep_spec and dep_spec.get("status") != "completed":
                    unmet_deps.append(dep)
                    # Check if dependency is outside phase (normalize comparison)
                    if dep not in phase_specs:
                        deps_outside_phase.append(dep)
            
            # Only track if there are unmet dependencies
            if unmet_deps:
                blocked_specs.append({
                    "id": spec_id,
                    "name": spec_status.get("name", spec_id),
                    "unmet_deps": unmet_deps,
                    "deps_outside_phase": deps_outside_phase
                })
        
        return blocked_specs
    
    def _get_next_spec_recommendations(self, completed_spec_id: str) -> dict:
        """Get intelligent recommendations for what to work on next"""
        recommendations = {
            "next_in_phase": None,
            "phase_info": None,
            "phase_completed": False,
            "phase_complete_info": None,
            "phase_blocked": False,
            "blocked_specs": [],
            "unblocked_specs": [],
            "next_in_sequence": None,
            "has_phases": False
        }
        
        # Load all specs
        all_specs = []
        for spec_dir in self.context.specs_dir.glob("*/"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    if status.get("status") != "deprecated":
                        all_specs.append(status)
                except Exception:
                    continue
        
        if not all_specs:
            return recommendations
        
        # Check if phases exist
        phases = self._get_all_phases()
        recommendations["has_phases"] = len(phases) > 0
        
        # 1. Check for next spec in current phase
        if phases:
            roadmap = self._load_roadmap()
            current_phase_id = roadmap.get("current_phase") if roadmap else None
            
            if current_phase_id:
                # Find current phase
                current_phase = None
                for phase in phases:
                    phase_id = phase.get("id", phase.get("_dir"))
                    if phase_id == current_phase_id:
                        current_phase = phase
                        break
                
                if current_phase:
                    phase_specs_raw = [s.get("id") if isinstance(s, dict) else s for s in current_phase.get("specs", [])]
                    
                    # Normalize phase spec IDs (handle both "006" and "006-name" formats)
                    phase_specs = []
                    for spec_ref in phase_specs_raw:
                        # Extract just the numeric ID (e.g., "006" from "006-spaces")
                        spec_id = spec_ref.split("-")[0] if "-" in spec_ref else spec_ref
                        phase_specs.append(spec_id)
                    
                    # Check if phase is now complete
                    phase_specs_status = [next((s for s in all_specs if s.get("id") == spec_id), None) 
                                         for spec_id in phase_specs]
                    all_phase_specs_complete = all(
                        s and s.get("status") == "completed" 
                        for s in phase_specs_status if s
                    )
                    
                    if all_phase_specs_complete and len(phase_specs) > 0:
                        # Phase is complete!
                        recommendations["phase_completed"] = True
                        progress = self._calculate_phase_progress(current_phase)
                        
                        # Check for next phase
                        unlocks = current_phase.get("unlocks", [])
                        next_phase_name = None
                        if unlocks:
                            next_phase = next((p for p in phases if p.get("id") == unlocks[0]), None)
                            if next_phase:
                                next_phase_name = next_phase.get("name")
                        
                        recommendations["phase_complete_info"] = {
                            "phase_id": current_phase_id,
                            "phase_name": current_phase.get("name"),
                            "specs_completed": len([s for s in phase_specs_status if s and s.get("status") == "completed"]),
                            "total_specs": len(phase_specs),
                            "next_phase_id": unlocks[0] if unlocks else None,
                            "next_phase_name": next_phase_name,
                            "deliverables": current_phase.get("deliverables", [])
                        }
                        return recommendations
                    
                    # Find next incomplete spec in this phase
                    # Track specs with unmet dependencies for warning
                    blocked_specs = []
                    
                    for spec_id in phase_specs:
                        spec_status = next((s for s in all_specs if s.get("id") == spec_id), None)
                        if spec_status and spec_status.get("status") != "completed":
                            # Check if dependencies are met
                            deps = spec_status.get("dependencies", [])
                            
                            if not deps:
                                # No dependencies - can implement now
                                recommendations["next_in_phase"] = {
                                    "id": spec_status.get("id"),
                                    "name": spec_status.get("name")
                                }
                                
                                # Calculate phase progress
                                progress = self._calculate_phase_progress(current_phase)
                                recommendations["phase_info"] = {
                                    "name": current_phase.get("name"),
                                    "progress": progress["specs_percent"]
                                }
                                return recommendations
                            
                            # Check which dependencies are met
                            unmet_deps = []
                            deps_outside_phase = []
                            
                            for dep in deps:
                                dep_spec = next((s for s in all_specs if s.get("id") == dep), None)
                                if dep_spec:
                                    if dep_spec.get("status") != "completed":
                                        unmet_deps.append(dep)
                                        # Check if dependency is outside current phase
                                        if dep not in phase_specs:
                                            deps_outside_phase.append(dep)
                            
                            if not unmet_deps:
                                # All dependencies met - can implement now
                                recommendations["next_in_phase"] = {
                                    "id": spec_status.get("id"),
                                    "name": spec_status.get("name")
                                }
                                
                                # Calculate phase progress
                                progress = self._calculate_phase_progress(current_phase)
                                recommendations["phase_info"] = {
                                    "name": current_phase.get("name"),
                                    "progress": progress["specs_percent"]
                                }
                                return recommendations
                            else:
                                # Track blocked specs
                                blocked_specs.append({
                                    "id": spec_id,
                                    "name": spec_status.get("name"),
                                    "unmet_deps": unmet_deps,
                                    "deps_outside_phase": deps_outside_phase
                                })
                    
                    # If we get here, all remaining specs in phase are blocked
                    if blocked_specs:
                        recommendations["phase_blocked"] = True
                        recommendations["blocked_specs"] = blocked_specs
                        recommendations["phase_info"] = {
                            "phase_id": current_phase_id,
                            "name": current_phase.get("name"),
                            "progress": self._calculate_phase_progress(current_phase)["specs_percent"]
                        }
        
        # 2. Find specs that are now unblocked (dependencies met)
        for spec in all_specs:
            if spec.get("status") == "completed" or spec.get("id") == completed_spec_id:
                continue
            
            deps = spec.get("dependencies", [])
            if not deps:
                continue
            
            # Check if this spec was just unblocked
            if completed_spec_id in deps:
                # Check if all other dependencies are met
                all_deps_met = all(
                    dep == completed_spec_id or 
                    any(s.get("id") == dep and s.get("status") == "completed" for s in all_specs)
                    for dep in deps
                )
                
                if all_deps_met:
                    recommendations["unblocked_specs"].append({
                        "id": spec.get("id"),
                        "name": spec.get("name"),
                        "priority": spec.get("priority", "P1")
                    })
        
        # Sort unblocked by priority
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        recommendations["unblocked_specs"].sort(
            key=lambda x: priority_order.get(x.get("priority", "P1"), 1)
        )
        
        if recommendations["unblocked_specs"]:
            return recommendations
        
        # 3. Get next in sequence (topological sort)
        try:
            ordered_specs = self._topological_sort_specs(all_specs)
            
            # Find first incomplete spec
            for spec in ordered_specs:
                if spec.get("status") != "completed":
                    # Check dependencies
                    deps = spec.get("dependencies", [])
                    deps_met = all(
                        any(s.get("id") == dep and s.get("status") == "completed" for s in all_specs)
                        for dep in deps
                    )
                    
                    if deps_met or not deps:
                        recommendations["next_in_sequence"] = {
                            "id": spec.get("id"),
                            "name": spec.get("name")
                        }
                        break
        except Exception:
            pass
        
        return recommendations
    
    def _detect_categorized_drift(self, spec_content: str, product_context: str, feature_name: str) -> dict:
        """Detect and categorize drift between spec and implementation"""
        
        # Get actual codebase structure for comparison
        codebase_info = self.context.data.get("codebase", {}).get("structure", "")
        
        # Also try to get relevant code files
        relevant_code = self._get_relevant_code_for_spec(spec_content)
        
        drift_prompt = f"""Analyze the drift between this feature specification and the ACTUAL implementation.

FEATURE: {feature_name}

SPECIFICATION:
{spec_content}

ACTUAL CODEBASE STRUCTURE:
{codebase_info[:2000] if codebase_info else "No codebase info available"}

RELEVANT CODE SNIPPETS:
{relevant_code[:12000] if relevant_code else "No code snippets available"}

PRODUCT CONTEXT:
{product_context[:500]}

Compare the SPECIFICATION against the ACTUAL CODE and categorize any drift:

1. SPEC_BEHIND - Implementation has features/improvements NOT documented in spec
   (e.g., code has error handling, caching, or features not in spec)
   
2. CODE_BEHIND - Spec has requirements NOT yet implemented in code
   (e.g., spec mentions features that don't exist in codebase)
   
3. SCOPE_CREEP - Implementation includes items explicitly marked "Out of Scope" in spec
   (e.g., code implements something spec says is out of scope)
   
4. TECH_DEVIATION - Implementation uses different technical approach than specified
   (e.g., spec says use library X but code uses library Y)
   
5. DOC_STALE - Documentation/comments in code don't match implementation

For each drift found, respond in this EXACT format:
DRIFT_TYPE: <type>
DESCRIPTION: <specific description of what differs between spec and code>
SUGGESTION: <how to resolve it>
---

If no drift is detected (spec and implementation are aligned), respond with exactly: NO_DRIFT_DETECTED

IMPORTANT:
- Only flag REAL differences between spec and actual code
- Do NOT flag items explicitly marked as "Out of Scope" in spec
- Do NOT flag "Open Questions" as drift - those are expected
- Be specific about what code exists vs what spec says"""

        response = self.ai.query(drift_prompt)
        
        if not response or "NO_DRIFT_DETECTED" in response:
            return {"has_drift": False, "drifts": []}
        
        # Parse drift items
        drifts = []
        current_drift = {}
        
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("DRIFT_TYPE:"):
                if current_drift:
                    drifts.append(current_drift)
                current_drift = {"type": line.replace("DRIFT_TYPE:", "").strip()}
            elif line.startswith("DESCRIPTION:"):
                current_drift["description"] = line.replace("DESCRIPTION:", "").strip()
            elif line.startswith("SUGGESTION:"):
                current_drift["suggestion"] = line.replace("SUGGESTION:", "").strip()
            elif line == "---" and current_drift:
                drifts.append(current_drift)
                current_drift = {}
        
        if current_drift and current_drift.get("type"):
            drifts.append(current_drift)
        
        return {"has_drift": len(drifts) > 0, "drifts": drifts, "resolutions": []}
    
    def _get_relevant_code_for_spec(self, spec_content: str) -> str:
        """Get relevant code snippets based on spec content"""
        
        import re
        from collections import Counter
        
        spec_lower = spec_content.lower()
        keywords = set()
        
        # 1. Extract ALL meaningful words from spec (frequency-based)
        # Remove code blocks first to avoid noise
        clean_spec = re.sub(r'```[\s\S]*?```', '', spec_lower)
        
        # Find all words 4+ chars (likely meaningful)
        all_words = re.findall(r'\b([a-z][a-z_]{3,})\b', clean_spec)
        
        # Count frequency - words appearing 2+ times are likely important
        word_counts = Counter(all_words)
        frequent_words = {word for word, count in word_counts.items() if count >= 2}
        keywords.update(frequent_words)
        
        # 2. Extract from backticks (file names, code references)
        backtick_content = re.findall(r'`([^`]+)`', spec_content)
        for content in backtick_content:
            # Extract file names
            if '.' in content:
                base_name = content.split('/')[-1].rsplit('.', 1)[0].lower()
                if len(base_name) > 2:
                    keywords.add(base_name)
            # Extract snake_case identifiers
            snake_words = re.findall(r'\b([a-z][a-z_]{2,})\b', content.lower())
            keywords.update(snake_words)
        
        # 3. Extract from spec title (first heading)
        title_match = re.search(r'^#\s*(.+)$', spec_content, re.MULTILINE)
        if title_match:
            title_words = re.findall(r'\b([a-z]{3,})\b', title_match.group(1).lower())
            keywords.update(title_words)
        
        # 4. Extract from User Stories section (feature-specific terms)
        if "user stor" in spec_lower:
            stories_section = spec_lower.split("user stor")[1][:1500]
            story_words = re.findall(r'\b([a-z][a-z_]{3,})\b', stories_section)
            # Take top words from stories
            story_counts = Counter(story_words)
            keywords.update(word for word, _ in story_counts.most_common(15))
        
        # 5. Extract from Technical Approach section
        if "technical approach" in spec_lower:
            tech_section = spec_lower.split("technical approach")[1][:2000]
            # Get snake_case words (likely code identifiers)
            tech_words = re.findall(r'\b([a-z]+(?:_[a-z]+)+)\b', tech_section)
            keywords.update(tech_words)
            # Also get regular words
            regular_words = re.findall(r'\b([a-z]{4,})\b', tech_section)
            keywords.update(word for word in regular_words if word not in {'with', 'that', 'this', 'from', 'will', 'should', 'would', 'could', 'have', 'been', 'being', 'when', 'where', 'which', 'what', 'into', 'using', 'used', 'uses'})
        
        # 6. Remove common stop words that aren't useful for file matching
        stop_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'has', 'have', 'been', 'being', 'some', 'than', 'them', 'then', 'these', 'they', 'this', 'will', 'with', 'would', 'about', 'after', 'before', 'between', 'each', 'from', 'into', 'more', 'other', 'such', 'that', 'their', 'there', 'through', 'under', 'very', 'when', 'where', 'which', 'while', 'should', 'could', 'must', 'need', 'also', 'just', 'only', 'first', 'last', 'same', 'both', 'well', 'back', 'even', 'still', 'over', 'down', 'here', 'most', 'make', 'made', 'like', 'time', 'very', 'just', 'know', 'take', 'come', 'good', 'give', 'most', 'only', 'over', 'such', 'want', 'because', 'does', 'during', 'example', 'following', 'however', 'include', 'including', 'instead', 'like', 'might', 'note', 'notes', 'please', 'required', 'requires', 'section', 'since', 'spec', 'specification', 'status', 'support', 'supports', 'update', 'updates', 'user', 'users', 'using', 'value', 'values', 'work', 'works'}
        keywords = {kw for kw in keywords if kw not in stop_words and len(kw) > 2}
        
        # Find relevant files in project
        code_snippets = []
        extensions = [".py", ".dart", ".ts", ".tsx", ".js", ".jsx"]
        skip_dirs = {"__pycache__", "node_modules", ".git", "venv", ".venv",
                     "build", "dist", ".dart_tool", ".speky"}
        
        try:
            all_code_files = []
            for ext in extensions:
                for file_path in self.project_root.rglob(f"*{ext}"):
                    # Skip common non-relevant directories
                    if any(skip in file_path.parts for skip in skip_dirs):
                        continue
                    all_code_files.append(file_path)
            
            # Score files by relevance
            scored_files = []
            for file_path in all_code_files:
                file_name = file_path.name.lower()
                file_stem = file_path.stem.lower()
                
                score = 0
                # Check if filename matches any keyword
                for kw in keywords:
                    if kw in file_stem:
                        score += 3
                    elif kw in file_name:
                        score += 2
                
                # Boost implementation files (services are more important than tasks for drift detection)
                if "service" in file_stem:
                    score += 5  # Services contain core implementation
                elif "model" in file_stem:
                    score += 4  # Models define data structures
                elif any(term in file_stem for term in ["handler", "controller", "router", "route"]):
                    score += 3  # API layer
                elif any(term in file_stem for term in ["task", "worker", "job"]):
                    score += 2  # Background tasks
                
                # Also include files even with score 0 if they're in key directories
                parent_dir = file_path.parent.name.lower()
                if parent_dir in {"services", "models", "handlers", "controllers", "routers", "tasks"}:
                    score += 1
                
                if score > 0:
                    scored_files.append((score, file_path))
            
            # Sort by score descending
            scored_files.sort(key=lambda x: x[0], reverse=True)
            
            # Read top files - increased to 12 for better coverage
            for score, file_path in scored_files[:12]:
                try:
                    content = file_path.read_text()
                    # Get first 200 lines for better context
                    lines = content.split("\n")[:200]
                    snippet = f"\n--- {file_path.relative_to(self.project_root)} (relevance: {score}) ---\n"
                    snippet += "\n".join(lines)
                    code_snippets.append(snippet)
                except:
                    pass
                    
        except Exception as e:
            return f"Error reading code: {str(e)}"
        
        return "\n".join(code_snippets) if code_snippets else ""
    
    def _resolve_drift_interactively(self, drift_analysis: dict, spec_file: Path, 
                                      spec_content: str, status: dict) -> bool:
        """Interactively resolve each drift item with navigation support"""
        
        drifts = drift_analysis.get("drifts", [])
        if not drifts:
            return True
        
        # Use dict keyed by index to track resolutions (allows updates)
        resolutions_map = {}  # {index: resolution_dict}
        spec_updates_map = {}  # {index: spec_update}
        
        spec_id = status.get("id", "")
        feature_name = status.get("name", "")
        
        current_index = 0
        total = len(drifts)
        
        while True:
            drift = drifts[current_index]
            drift_type = drift.get("type", "UNKNOWN")
            description = drift.get("description", "No description")
            suggestion = drift.get("suggestion", "No suggestion")
            
            # Check if this item is already resolved
            is_resolved = current_index in resolutions_map
            resolution_status = "✅ RESOLVED" if is_resolved else "⬜ UNRESOLVED"
            current_resolution = resolutions_map.get(current_index, {}).get("action", "")
            
            # Display header with navigation info
            print(f"\n{'='*60}")
            print(f"[Drift {current_index + 1}/{total}] {drift_type} - {resolution_status}")
            if is_resolved:
                print(f"   Current: {current_resolution}")
            print(f"{'='*60}")
            print(f"\n📋 Description: {description}")
            print(f"💡 Suggestion: {suggestion}")
            print()
            
            # Show navigation hint
            nav_hint = []
            if current_index > 0:
                nav_hint.append("[p]rev")
            if current_index < total - 1:
                nav_hint.append("[n]ext")
            nav_hint.append("[c]ancel")
            nav_str = " | ".join(nav_hint)
            
            # Handle based on drift type
            result = self._handle_drift_item(
                drift_type, description, suggestion, 
                spec_content, status, spec_id, feature_name,
                is_resolved, current_resolution, nav_str
            )
            
            if result == "cancel":
                return False
            elif result == "prev":
                if current_index > 0:
                    current_index -= 1
                else:
                    Console.warning("Already at first item")
                continue
            elif result == "next":
                if current_index < total - 1:
                    current_index += 1
                else:
                    Console.warning("Already at last item")
                continue
            elif result is not None:
                # Got a resolution
                resolution, spec_update = result
                resolutions_map[current_index] = resolution
                if spec_update:
                    spec_updates_map[current_index] = spec_update
                
                # Auto-advance to next unresolved or next item
                if current_index < total - 1:
                    current_index += 1
                else:
                    # At last item, check if all resolved
                    break
        
        # Check for unresolved items
        unresolved_indices = [i for i in range(total) if i not in resolutions_map]
        
        if unresolved_indices:
            Console.section("⚠️  Unresolved Items")
            print(f"You have {len(unresolved_indices)} unresolved drift item(s):")
            for idx in unresolved_indices:
                drift = drifts[idx]
                print(f"   [{idx + 1}] {drift.get('type', 'UNKNOWN')}: {drift.get('description', '')[:50]}...")
            
            print("\nOptions:")
            print("  [r] Review unresolved items")
            print("  [s] Skip all unresolved (mark as skipped)")
            print("  [c] Cancel completion")
            
            choice = Console.prompt("Action", default="r").lower()
            
            if choice == "c":
                return False
            elif choice == "s":
                # Mark all unresolved as skipped
                for idx in unresolved_indices:
                    drift = drifts[idx]
                    resolutions_map[idx] = {
                        "type": drift.get("type", "UNKNOWN"),
                        "action": "skipped",
                        "description": drift.get("description", "")
                    }
                Console.log(f"Marked {len(unresolved_indices)} item(s) as skipped")
            else:
                # Go back to review - start at first unresolved
                current_index = unresolved_indices[0]
                # Recursive call to continue review
                return self._continue_drift_review(
                    drifts, resolutions_map, spec_updates_map,
                    spec_content, status, spec_id, feature_name,
                    current_index
                )
        
        # Final summary before applying
        Console.section("📋 Resolution Summary")
        print(f"\nReviewed {total} drift item(s):\n")
        
        p0_count = sum(1 for r in resolutions_map.values() if r.get("action") == "p0_blocker")
        p1_count = sum(1 for r in resolutions_map.values() if r.get("action") == "p1_high")
        p2_count = sum(1 for r in resolutions_map.values() if r.get("action") == "p2_medium")
        p3_count = sum(1 for r in resolutions_map.values() if r.get("action") == "p3_low")
        spec_update_count = sum(1 for r in resolutions_map.values() if "spec_updated" in r.get("action", ""))
        out_of_scope_count = sum(1 for r in resolutions_map.values() if r.get("action") == "out_of_scope")
        skipped_count = sum(1 for r in resolutions_map.values() if r.get("action") == "skipped")
        
        if p0_count:
            print(f"   🚨 P0 BLOCKER specs to create: {p0_count}")
        if p1_count:
            print(f"   ⚡ P1 HIGH specs to create: {p1_count}")
        if p2_count:
            print(f"   📋 P2 MEDIUM backlog items: {p2_count}")
        if p3_count:
            print(f"   📝 P3 LOW notes: {p3_count}")
        if spec_update_count:
            print(f"   📄 Spec updates: {spec_update_count}")
        if out_of_scope_count:
            print(f"   ⭕ Out of scope: {out_of_scope_count}")
        if skipped_count:
            print(f"   ⏭️  Skipped: {skipped_count}")
        
        print()
        
        # Confirm before applying
        if not Console.confirm("Apply these resolutions?", default=True):
            # Allow going back to review
            if Console.confirm("Go back to review?", default=True):
                return self._continue_drift_review(
                    drifts, resolutions_map, spec_updates_map,
                    spec_content, status, spec_id, feature_name,
                    0
                )
            return False
        
        # Convert maps to lists for downstream processing
        resolutions = list(resolutions_map.values())
        spec_updates = list(spec_updates_map.values())
        
        # Store in drift_analysis for downstream use
        drift_analysis["resolutions"] = resolutions
        drift_analysis["spec_updates"] = spec_updates
        
        # Apply spec updates if any
        if spec_updates:
            Console.section("Applying Spec Updates")
            updated_spec = self._apply_spec_updates(spec_content, spec_updates)
            if updated_spec:
                spec_file.write_text(updated_spec)
                Console.success(f"Spec updated with {len(spec_updates)} change(s)")
        
        drift_analysis["resolutions"] = resolutions
        
        # Apply resolutions (create specs or store in backlog)
        priority_actions = ["p0_blocker", "p1_high", "p2_medium", "p3_low", "detailed_spec", "short_spec"]
        resolutions_to_apply = [res for res in resolutions if res.get("action") in priority_actions]
        
        if resolutions_to_apply:
            Console.section("Creating Priority Specs & Backlog Items")
            for res in resolutions_to_apply:
                self._apply_resolution(res)
        
        # Summary
        Console.section("Drift Resolution Summary")
        for res in resolutions:
            action_icon = "✅" if res["action"] != "skipped" else "⏭️"
            print(f"  {action_icon} {res['type']}: {res['action']}")
        
        return True
    
    def _handle_drift_item(self, drift_type: str, description: str, suggestion: str,
                           spec_content: str, status: dict, spec_id: str, feature_name: str,
                           is_resolved: bool, current_resolution: str, nav_str: str):
        """Handle a single drift item and return resolution or navigation command"""
        
        # Handle based on drift type
        if drift_type == "SPEC_BEHIND":
            print("The implementation has improvements not in the spec.")
            print(f"\nOptions: [u]pdate spec | [s]kip | {nav_str}")
            
            choice = Console.prompt("Action", default="u").lower()
            
            if choice == "p":
                return "prev"
            elif choice == "n":
                return "next"
            elif choice == "c":
                return "cancel"
            elif choice == "u":
                update = self._generate_spec_update(spec_content, description, suggestion)
                if update:
                    Console.success(f"Will update spec with: {description[:50]}...")
                    return ({"type": drift_type, "action": "spec_updated", "description": description}, update)
                else:
                    Console.warning("Could not generate spec update. Skipping.")
                    return ({"type": drift_type, "action": "skipped", "description": description}, None)
            else:
                Console.log("Skipped")
                return ({"type": drift_type, "action": "skipped", "description": description}, None)
                
        elif drift_type == "CODE_BEHIND":
            print("Some spec items are not yet implemented.")
            print("\n📋 Priority Options:")
            print("  [0] P0 BLOCKER - Create spec NOW, implement immediately after this")
            print("  [1] P1 HIGH    - Create spec with full context, next in queue")
            print("  [2] P2 MEDIUM  - Add to backlog with details for later")
            print("  [3] P3 LOW     - Quick note for future reference")
            print("  [o] Out of scope - Not needed for this feature")
            print("  [k] Skip - Don't track")
            print(f"\nNavigation: {nav_str}")
            
            choice = Console.prompt("Action", default="2").lower()
            
            if choice == "p":
                return "prev"
            elif choice == "n":
                return "next"
            elif choice == "c":
                return "cancel"
            elif choice == "0":
                Console.section("🚨 P0 BLOCKER Spec")
                spec_name = Console.prompt("Spec name", default=description[:50])
                print("\n📝 Adding context for the spec:")
                why_blocker = Console.prompt(
                    "Why is this a blocker? (impact if not fixed)",
                    default="Required for feature to work correctly"
                )
                Console.success(f"🚨 P0 spec will be created: {spec_name}")
                Console.warning("This will be created immediately after completion")
                return ({
                    "type": drift_type, 
                    "action": "p0_blocker", 
                    "description": description,
                    "suggestion": suggestion,
                    "spec_name": spec_name,
                    "priority": "P0",
                    "why_blocker": why_blocker,
                    "depends_on": status.get("id", spec_id),
                    "source_spec": feature_name
                }, None)
                
            elif choice == "1":
                Console.section("⚡ P1 HIGH Priority Spec")
                spec_name = Console.prompt("Spec name", default=description[:50])
                print("\n📝 Adding context:")
                acceptance = Console.prompt(
                    "Key acceptance criteria (what 'done' looks like)",
                    default="Implementation matches spec requirements"
                )
                Console.success(f"⚡ P1 spec queued: {spec_name}")
                return ({
                    "type": drift_type, 
                    "action": "p1_high", 
                    "description": description,
                    "suggestion": suggestion,
                    "spec_name": spec_name,
                    "priority": "P1",
                    "acceptance": acceptance,
                    "depends_on": status.get("id", spec_id),
                    "source_spec": feature_name
                }, None)
                
            elif choice == "2":
                spec_name = Console.prompt("Name for backlog item", default=description[:50])
                Console.success(f"📋 P2 added to backlog: {spec_name}")
                return ({
                    "type": drift_type, 
                    "action": "p2_medium", 
                    "description": description,
                    "suggestion": suggestion,
                    "spec_name": spec_name,
                    "priority": "P2",
                    "source_spec": feature_name
                }, None)
                
            elif choice == "3":
                note = Console.prompt("Short note for future reference", default=description[:100])
                Console.success("📝 P3 noted for future")
                return ({
                    "type": drift_type, 
                    "action": "p3_low", 
                    "description": description,
                    "note": note,
                    "priority": "P3"
                }, None)
                
            elif choice == "o":
                Console.success("Marked as out of scope for this feature")
                return ({"type": drift_type, "action": "out_of_scope", "description": description}, None)
            else:
                Console.log("Skipped")
                return ({"type": drift_type, "action": "skipped", "description": description}, None)
                
        elif drift_type == "SCOPE_CREEP":
            print("Out-of-scope items were implemented.")
            print(f"\nOptions: [d]ocument in spec | [r]emove note | [s]kip | {nav_str}")
            
            choice = Console.prompt("Action", default="d").lower()
            
            if choice == "p":
                return "prev"
            elif choice == "n":
                return "next"
            elif choice == "c":
                return "cancel"
            elif choice == "d":
                update = self._generate_spec_update(spec_content, description, "Add to scope")
                if update:
                    Console.success("Will document in spec")
                    return ({"type": drift_type, "action": "documented", "description": description}, update)
                return ({"type": drift_type, "action": "skipped", "description": description}, None)
            elif choice == "r":
                Console.warning("Noted for removal in next iteration")
                return ({"type": drift_type, "action": "noted_for_removal", "description": description}, None)
            else:
                Console.log("Skipped")
                return ({"type": drift_type, "action": "skipped", "description": description}, None)
                
        elif drift_type == "TECH_DEVIATION":
            print("Technical approach differs from spec.")
            print(f"\nOptions: [u]pdate spec to match | [s]kip | {nav_str}")
            
            choice = Console.prompt("Action", default="u").lower()
            
            if choice == "p":
                return "prev"
            elif choice == "n":
                return "next"
            elif choice == "c":
                return "cancel"
            elif choice == "u":
                update = self._generate_spec_update(spec_content, description, suggestion)
                if update:
                    Console.success("Will update spec")
                    return ({"type": drift_type, "action": "spec_updated", "description": description}, update)
                return ({"type": drift_type, "action": "skipped", "description": description}, None)
            else:
                Console.log("Skipped")
                return ({"type": drift_type, "action": "skipped", "description": description}, None)
                
        elif drift_type == "DOC_STALE":
            print("Documentation needs updating.")
            print(f"\nOptions: [u]pdate docs | [s]kip | {nav_str}")
            
            choice = Console.prompt("Action", default="u").lower()
            
            if choice == "p":
                return "prev"
            elif choice == "n":
                return "next"
            elif choice == "c":
                return "cancel"
            elif choice == "u":
                Console.success("Will update documentation")
                return ({"type": drift_type, "action": "docs_updated", "description": description}, None)
            else:
                Console.log("Skipped")
                return ({"type": drift_type, "action": "skipped", "description": description}, None)
        else:
            # Unknown drift type
            print(f"\nOptions: [s]kip | {nav_str}")
            choice = Console.prompt("Action", default="s").lower()
            
            if choice == "p":
                return "prev"
            elif choice == "n":
                return "next"
            elif choice == "c":
                return "cancel"
            return ({"type": drift_type, "action": "skipped", "description": description}, None)
    
    def _continue_drift_review(self, drifts: list, resolutions_map: dict, spec_updates_map: dict,
                                spec_content: str, status: dict, spec_id: str, feature_name: str,
                                start_index: int) -> bool:
        """Continue drift review from a specific index (used for re-review)"""
        
        total = len(drifts)
        current_index = start_index
        
        while True:
            drift = drifts[current_index]
            drift_type = drift.get("type", "UNKNOWN")
            description = drift.get("description", "No description")
            suggestion = drift.get("suggestion", "No suggestion")
            
            is_resolved = current_index in resolutions_map
            resolution_status = "✅ RESOLVED" if is_resolved else "⬜ UNRESOLVED"
            current_resolution = resolutions_map.get(current_index, {}).get("action", "")
            
            print(f"\n{'='*60}")
            print(f"[Drift {current_index + 1}/{total}] {drift_type} - {resolution_status}")
            if is_resolved:
                print(f"   Current: {current_resolution}")
            print(f"{'='*60}")
            print(f"\n📋 Description: {description}")
            print(f"💡 Suggestion: {suggestion}")
            print()
            
            nav_hint = []
            if current_index > 0:
                nav_hint.append("[p]rev")
            if current_index < total - 1:
                nav_hint.append("[n]ext")
            nav_hint.append("[f]inish review")
            nav_hint.append("[c]ancel")
            nav_str = " | ".join(nav_hint)
            
            # Add finish option for re-review
            print(f"Navigation: {nav_str}")
            
            result = self._handle_drift_item(
                drift_type, description, suggestion, 
                spec_content, status, spec_id, feature_name,
                is_resolved, current_resolution, nav_str
            )
            
            if result == "cancel":
                return False
            elif result == "prev":
                if current_index > 0:
                    current_index -= 1
                else:
                    Console.warning("Already at first item")
                continue
            elif result == "next":
                if current_index < total - 1:
                    current_index += 1
                else:
                    Console.warning("Already at last item")
                continue
            elif isinstance(result, str) and result.startswith("f"):
                # Finish review
                break
            elif result is not None:
                resolution, spec_update = result
                resolutions_map[current_index] = resolution
                if spec_update:
                    spec_updates_map[current_index] = spec_update
                
                if current_index < total - 1:
                    current_index += 1
                else:
                    break
        
        # Check for remaining unresolved
        unresolved_indices = [i for i in range(total) if i not in resolutions_map]
        
        if unresolved_indices:
            Console.section("⚠️  Unresolved Items")
            print(f"You have {len(unresolved_indices)} unresolved drift item(s):")
            for idx in unresolved_indices:
                drift = drifts[idx]
                print(f"   [{idx + 1}] {drift.get('type', 'UNKNOWN')}: {drift.get('description', '')[:50]}...")
            
            print("\nOptions:")
            print("  [r] Review unresolved items")
            print("  [s] Skip all unresolved (mark as skipped)")
            print("  [c] Cancel completion")
            
            choice = Console.prompt("Action", default="r").lower()
            
            if choice == "c":
                return False
            elif choice == "s":
                for idx in unresolved_indices:
                    drift = drifts[idx]
                    resolutions_map[idx] = {
                        "type": drift.get("type", "UNKNOWN"),
                        "action": "skipped",
                        "description": drift.get("description", "")
                    }
                Console.log(f"Marked {len(unresolved_indices)} item(s) as skipped")
            else:
                current_index = unresolved_indices[0]
                return self._continue_drift_review(
                    drifts, resolutions_map, spec_updates_map,
                    spec_content, status, spec_id, feature_name,
                    current_index
                )
        
        # Final summary
        Console.section("📋 Resolution Summary")
        print(f"\nReviewed {total} drift item(s):\n")
        
        p0_count = sum(1 for r in resolutions_map.values() if r.get("action") == "p0_blocker")
        p1_count = sum(1 for r in resolutions_map.values() if r.get("action") == "p1_high")
        p2_count = sum(1 for r in resolutions_map.values() if r.get("action") == "p2_medium")
        p3_count = sum(1 for r in resolutions_map.values() if r.get("action") == "p3_low")
        spec_update_count = sum(1 for r in resolutions_map.values() if "spec_updated" in r.get("action", ""))
        out_of_scope_count = sum(1 for r in resolutions_map.values() if r.get("action") == "out_of_scope")
        skipped_count = sum(1 for r in resolutions_map.values() if r.get("action") == "skipped")
        
        if p0_count:
            print(f"   🚨 P0 BLOCKER specs to create: {p0_count}")
        if p1_count:
            print(f"   ⚡ P1 HIGH specs to create: {p1_count}")
        if p2_count:
            print(f"   📋 P2 MEDIUM backlog items: {p2_count}")
        if p3_count:
            print(f"   📝 P3 LOW notes: {p3_count}")
        if spec_update_count:
            print(f"   📄 Spec updates: {spec_update_count}")
        if out_of_scope_count:
            print(f"   ⭕ Out of scope: {out_of_scope_count}")
        if skipped_count:
            print(f"   ⏭️  Skipped: {skipped_count}")
        
        print()
        
        if not Console.confirm("Apply these resolutions?", default=True):
            if Console.confirm("Go back to review?", default=True):
                return self._continue_drift_review(
                    drifts, resolutions_map, spec_updates_map,
                    spec_content, status, spec_id, feature_name,
                    0
                )
            return False
        
        return True
    
    def _generate_spec_update(self, spec_content: str, description: str, suggestion: str) -> str:
        """Generate a spec update based on drift"""
        
        update_prompt = f"""Based on this drift, generate a concise update to add to the spec.

CURRENT SPEC:
{spec_content[:2000]}...

DRIFT DESCRIPTION: {description}
SUGGESTION: {suggestion}

Generate a SHORT markdown snippet (2-5 lines) to add to the spec that documents this change.
Format as a bullet point or short paragraph. Be concise.
Respond with ONLY the markdown to add, nothing else."""

        return self.ai.query(update_prompt)
    
    def _apply_spec_updates(self, spec_content: str, updates: list) -> str:
        """Apply updates to spec content"""
        
        # Add updates section if there are any
        updates_text = "\n".join([f"- {u}" for u in updates if u])
        
        if "## Implementation Notes" in spec_content:
            # Append to existing section
            spec_content = spec_content.replace(
                "## Implementation Notes",
                f"## Implementation Notes\n\n{updates_text}\n"
            )
        else:
            # Add new section at the end
            spec_content += f"\n\n## Implementation Notes\n\n{updates_text}\n"
        
        return spec_content

    # -------------------------------------------------------------------------
    # Command: commit
    # -------------------------------------------------------------------------
    def cmd_commit(self, spec_id: str, edit: bool = False) -> bool:
        """Commit changes for a completed feature with comprehensive message"""
        if not self._require_init():
            return False
        
        Console.header(f"📝 Commit Feature: {spec_id}")
        
        # Find spec
        spec_dir = self._find_spec_dir(spec_id)
        if not spec_dir:
            Console.error(f"Spec not found: {spec_id}")
            return False
        
        status_file = spec_dir / "status.json"
        if not status_file.exists():
            Console.error(f"Status file not found: {status_file}")
            return False
        
        status = json.loads(status_file.read_text())
        feature_name = status.get("name", spec_id)
        
        # Check if feature is completed
        if status.get("status") != ItemStatus.COMPLETED.value:
            Console.warning(f"Feature is not marked as complete. Current status: {status.get('status')}")
            if not Console.confirm("Run 'speky complete' first?", default=True):
                Console.log("Please run 'speky complete {spec_id}' first")
                return False
            # Run complete first
            if not self.cmd_complete(spec_id):
                return False
            # Reload status
            status = json.loads(status_file.read_text())
        
        Console.section("Version Control", "Preparing comprehensive commit")
        
        # Generate commit message
        commit_msg = self._generate_commit_message(spec_id, feature_name, status)
        
        # Allow user to edit commit message
        if edit:
            commit_msg = self._edit_commit_message(commit_msg)
        else:
            # Show message and ask if they want to edit
            print("\n📝 Commit Message Preview:")
            print("-" * 40)
            print(commit_msg[:500] + ("..." if len(commit_msg) > 500 else ""))
            print("-" * 40)
            
            if Console.confirm("Edit commit message?", default=False):
                commit_msg = self._edit_commit_message(commit_msg)
        
        try:
            # Update status with commit info BEFORE staging
            status["committed_at"] = datetime.now().isoformat()
            status_file.write_text(json.dumps(status, indent=2))
            
            # Stage only what the user chose (never a blind `git add -A`)
            if not self._stage_files_for_commit(status_file):
                return False
            
            # Commit with comprehensive message
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=self.project_root, check=True)
            Console.success(f"Committed: {commit_msg.split(chr(10))[0]}")
            
            Console.section("Next Steps")
            print("To push your commits to remote:")
            print("  git push")
            print("\nTo create next feature:")
            print("  speky spec \"Next feature name\"")
            print("\nTo check project status:")
            print("  speky status")
                
        except subprocess.CalledProcessError as e:
            Console.warning(f"Git commit failed: {e}")
            Console.log("You can commit manually with:")
            print(f"  git add <files>")
            print(f"  git commit -m '{commit_msg.split(chr(10))[0]}'")
            return False
        except FileNotFoundError:
            Console.warning("Git not found. Please commit manually.")
            return False
        
        return True
    
    # Untracked files that are never staged automatically (likely secrets)
    SECRET_FILE_PATTERNS = (".env", ".env.*", "*.env", "*.pem", "*.key", "*.p12", "*.pfx",
                            "*.keystore", "*.jks", "id_rsa*", "id_ed25519*", "id_ecdsa*",
                            "credentials*", "*credentials.json", "secrets.*", "*.secret", ".npmrc", ".pypirc",
                            ".netrc")

    @classmethod
    def _looks_like_secret(cls, path: str) -> bool:
        import fnmatch
        name = Path(path).name.lower()
        return any(fnmatch.fnmatch(name, pattern) for pattern in cls.SECRET_FILE_PATTERNS)

    def _git_changed_files(self) -> List[tuple]:
        """(status, path) for every changed, deleted or untracked file, from `git status`."""
        out = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                             cwd=self.project_root, capture_output=True, text=True, check=True).stdout
        entries, parts, i = [], out.split("\0"), 0
        while i < len(parts):
            entry = parts[i]
            i += 1
            if len(entry) < 4:
                continue
            code, path = entry[:2], entry[3:]
            if code[0] in "RC":  # rename/copy: the old path follows as its own field
                i += 1
            entries.append((code, path))
        return entries

    def _stage_files_for_commit(self, status_file: Path) -> bool:
        """Stage files for `speky commit` without sweeping in unrelated work or secrets.

        If the user already staged files, commit exactly those (plus the item's status.json).
        Otherwise list the changed files, leave likely-secret untracked files out, and ask
        before staging. Returns False when the user declines.
        """
        status_rel = str(status_file.relative_to(self.project_root))
        staged = subprocess.run(["git", "diff", "--cached", "--name-only", "-z"], cwd=self.project_root,
                                capture_output=True, text=True, check=True).stdout.split("\0")
        staged = [p for p in staged if p]
        if staged:
            Console.log(f"Committing the {len(staged)} file(s) you already staged.")
            if subprocess.run(["git", "check-ignore", "-q", "--", status_rel],
                              cwd=self.project_root).returncode != 0:
                subprocess.run(["git", "add", "--", status_rel], cwd=self.project_root, check=True)
            return True

        changes = self._git_changed_files()
        held_back = [p for code, p in changes if code == "??" and self._looks_like_secret(p)]
        to_stage = [p for code, p in changes if p not in held_back]
        status_ignored = subprocess.run(["git", "check-ignore", "-q", "--", status_rel],
                                        cwd=self.project_root).returncode == 0
        if status_rel not in to_stage and not status_ignored:
            to_stage.append(status_rel)
        if not to_stage:
            Console.warning("Nothing to commit.")
            return False

        print(f"\nFiles to commit ({len(to_stage)}):")
        for path in to_stage[:30]:
            print(f"   {path}")
        if len(to_stage) > 30:
            print(f"   ... and {len(to_stage) - 30} more")
        if held_back:
            Console.warning("Not staged (looks like a secret — add it yourself if you mean to):")
            for path in held_back:
                print(f"   {path}")

        if not Console.confirm(f"Stage and commit these {len(to_stage)} file(s)?", default=True):
            Console.log("Nothing committed. Stage the files you want with `git add`, then run this again "
                        "— SPEKY commits exactly what is staged.")
            return False
        subprocess.run(["git", "add", "--", *to_stage], cwd=self.project_root, check=True)
        return True

    def _generate_commit_message(self, spec_id: str, feature_name: str, status: dict) -> str:
        """Generate comprehensive commit message with context from spec and plan"""
        completed_at = status.get("completed_at", "")
        drift_notes = status.get("drift_notes", "")
        
        # Read spec and plan for detailed context
        spec_dir = self._find_spec_dir(spec_id)
        spec_content = ""
        plan_content = ""
        
        if spec_dir:
            spec_file = spec_dir / "spec.md"
            plan_file = spec_dir / "plan.md"
            
            if spec_file.exists():
                spec_content = spec_file.read_text()
            if plan_file.exists():
                plan_content = plan_file.read_text()
        
        # Extract key information from spec and plan
        user_stories = self._extract_user_stories(spec_content)
        acceptance_criteria = self._extract_acceptance_criteria(spec_content)
        implementation_tasks = self._extract_implementation_tasks(plan_content)
        
        # Build comprehensive message
        lines = [
            f"feat: {feature_name} ({spec_id})",
            "",
            "## Summary",
            f"Completed implementation of: {feature_name}",
            f"Spec ID: {spec_id}",
            f"Completed at: {completed_at}",
        ]
        
        # Add user stories if available
        if user_stories:
            lines.extend([
                "",
                "## User Stories Implemented",
            ])
            for story in user_stories[:5]:  # Limit to first 5
                lines.append(f"- {story}")
        
        # Add implementation details from plan
        if implementation_tasks:
            lines.extend([
                "",
                "## Implementation",
            ])
            for task in implementation_tasks[:8]:  # Limit to first 8
                lines.append(f"- {task}")
        
        # Add acceptance criteria if available
        if acceptance_criteria:
            lines.extend([
                "",
                "## Acceptance Criteria Met",
            ])
            for criteria in acceptance_criteria[:5]:  # Limit to first 5
                lines.append(f"- {criteria}")
        
        # Add drift notes if present
        if drift_notes:
            lines.extend([
                "",
                "## Implementation Notes",
                drift_notes,
            ])
        
        lines.extend([
            "",
            "## Related",
            f"Spec: .speky/specs/{spec_id}/spec.md",
            f"Plan: .speky/specs/{spec_id}/plan.md",
        ])
        
        return "\n".join(lines)
    
    def _extract_user_stories(self, spec_content: str) -> list:
        """Extract user stories from spec content"""
        stories = []
        if not spec_content:
            return stories
        
        # Look for user stories section
        lines = spec_content.split('\n')
        in_stories_section = False
        
        for line in lines:
            line_lower = line.lower().strip()
            
            # Detect user stories section
            if 'user stories' in line_lower or 'user story' in line_lower:
                in_stories_section = True
                continue
            
            # Stop at next major section
            if in_stories_section and line.startswith('##'):
                break
            
            # Extract story items
            if in_stories_section:
                if line.strip().startswith('-') or line.strip().startswith('*'):
                    story = line.strip().lstrip('-*').strip()
                    if story and len(story) > 10:  # Filter out very short items
                        stories.append(story)
                elif line.strip().startswith('As a') or line.strip().startswith('As an'):
                    stories.append(line.strip())
        
        return stories
    
    def _extract_acceptance_criteria(self, spec_content: str) -> list:
        """Extract acceptance criteria from spec content"""
        criteria = []
        if not spec_content:
            return criteria
        
        lines = spec_content.split('\n')
        in_criteria_section = False
        
        for line in lines:
            line_lower = line.lower().strip()
            
            # Detect acceptance criteria section
            if 'acceptance criteria' in line_lower or 'acceptance criterion' in line_lower:
                in_criteria_section = True
                continue
            
            # Stop at next major section
            if in_criteria_section and line.startswith('##'):
                break
            
            # Extract criteria items
            if in_criteria_section:
                if line.strip().startswith('-') or line.strip().startswith('*'):
                    criterion = line.strip().lstrip('-*').strip()
                    if criterion and len(criterion) > 10:
                        criteria.append(criterion)
        
        return criteria
    
    def _extract_implementation_tasks(self, plan_content: str) -> list:
        """Extract implementation tasks from plan content"""
        tasks = []
        if not plan_content:
            return tasks
        
        lines = plan_content.split('\n')
        
        for line in lines:
            line_stripped = line.strip()
            
            # Extract task items (bullets or numbered)
            if line_stripped.startswith('-') or line_stripped.startswith('*'):
                task = line_stripped.lstrip('-*').strip()
                # Filter out section headers and very short items
                if task and len(task) > 15 and not task.endswith(':'):
                    # Remove task numbers if present (e.g., "1. Task" -> "Task")
                    if task[0].isdigit() and '. ' in task[:5]:
                        task = task.split('. ', 1)[1]
                    tasks.append(task)
            elif line_stripped and line_stripped[0].isdigit() and '. ' in line_stripped[:5]:
                task = line_stripped.split('. ', 1)[1].strip()
                if len(task) > 15 and not task.endswith(':'):
                    tasks.append(task)
        
        return tasks
    
    def _edit_commit_message(self, commit_msg: str) -> str:
        """Allow user to edit commit message in their default editor"""
        import tempfile
        
        # Create temporary file with commit message
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(commit_msg)
            temp_file = f.name
        
        try:
            # Determine editor
            editor = os.environ.get('EDITOR', os.environ.get('VISUAL', 'nano'))
            
            # Open editor
            Console.log(f"Opening editor ({editor}) for commit message...")
            subprocess.run([editor, temp_file], check=False)
            
            # Read edited message
            with open(temp_file, 'r') as f:
                edited_msg = f.read().strip()
            
            if edited_msg:
                Console.success("Commit message updated")
                return edited_msg
            else:
                Console.warning("Commit message is empty, using original")
                return commit_msg
                
        except Exception as e:
            Console.warning(f"Failed to edit commit message: {e}")
            Console.log("Using original commit message")
            return commit_msg
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_file)
            except:
                pass
    
    def _create_ide_context_guide(self, profile: dict, tech_stack: dict) -> None:
        """Create IDE context guide explaining SPEKY capabilities"""
        product_name = profile.get("name", "Product")
        
        guide = f"""# IDE Context Guide - SPEKY Integration

## What is SPEKY?

SPEKY (AI-Assisted Scalable Engineering Framework) helps you:
- Create realistic, MVP-focused specifications
- Generate implementation plans with accurate timelines
- Track feature completion and progress
- Maintain spec-code alignment
- Collaborate with AI on technical decisions

## Your Project: {product_name}

**Product:** {profile.get('description', 'N/A')}  
**Platform:** {profile.get('platform', 'N/A')}  
**Scale:** {profile.get('scale', 'N/A')}  

### Tech Stack
- **Frontend:** {tech_stack.get('frontend', 'Not decided')}
- **Backend:** {tech_stack.get('backend', 'Not decided')}
- **Database:** {tech_stack.get('database', 'Not decided')}
- **Deployment:** {tech_stack.get('deployment', 'Not decided')}

## Workflows

### Workflow A: Import External Knowledge
**When:** You have external documentation (PRD, tech spec, design docs, etc.)

```bash
# 1. Place docs in predefined location
.speky/imports/<phase>/source/
# (e.g., .speky/imports/mvp/source/)

# 2. Import and analyze (creates specs automatically)
speky import --phase mvp
# → Analyzes docs, proposes specs, creates them in SPEKY tracking
# → Specs are ALREADY tracked (no adoption needed)

# 3. Validate quality (optional but recommended)
speky validate-spec 001

# 4. Generate implementation plan
speky plan 001

# 5. Start implementation
speky implement 001
```

**Key Point:** Imported specs are automatically added to SPEKY tracking. No adoption needed.

### Workflow B: IDE Creates Spec Directly
**When:** You or your IDE creates a spec.md file manually

```bash
# 1. Create spec file at correct location
.speky/specs/004-feature-name/spec.md

# 2. Adopt into SPEKY tracking
speky adopt 004
# → Validates format, creates status.json, adds to tracking

# 3. Validate quality (optional but recommended)
speky validate-spec 004

# 4. Generate implementation plan
speky plan 004

# 5. Start implementation
speky implement 004
```

**Key Point:** IDE-created specs must be adopted before planning.

### Workflow C: SPEKY Creates Spec
**When:** You use SPEKY to generate specs from scratch

```bash
# 1. Create feature spec
speky spec "Feature name"
# → Creates spec in SPEKY tracking automatically

# 2. Validate quality (optional but recommended)
speky validate-spec 001

# 3. Generate implementation plan
speky plan 001

# 4. Start implementation
speky implement 001
```

**Key Point:** SPEKY-created specs are automatically tracked.

## Spec Quality & Validation

### Using `validate-spec`

Works with ANY spec (imported, adopted, or SPEKY-created):

```bash
# By spec ID
speky validate-spec 001

# By file path
speky validate-spec .speky/specs/001-feature/spec.md

# Quick mode (non-interactive)
speky validate-spec 001 --quick
```

Checks:
- ✅ Required sections present
- ✅ MVP focus (achievable in 1-2 weeks)
- ✅ Clear requirements and acceptance criteria
- ✅ Technical feasibility
- ✅ Realistic scope

## How to Use SPEKY

### 1. Create Feature Specifications
```bash
speky spec "Feature name"
```
Generates:
- 1-2 user stories (MVP-focused)
- Functional & non-functional requirements
- Clear out-of-scope items
- Technical approach using your tech stack

### 2. Generate Implementation Plans
```bash
speky plan 001
```
Generates:
- 3-8 realistic tasks (not 10+)
- Time estimates per task (2-8 hours each)
- Total timeline <40 hours
- Top 2-3 risks with mitigations

### 3. Implement Features
```bash
speky implement 001
```
Prepares:
- Full context in .windsurfrules
- Spec and plan details
- Tech stack information
- Opens your IDE

### 4. Mark Features Complete
```bash
speky complete 001 --commit
```
Does:
- Detects and syncs drift
- Updates codebase context
- Generates comprehensive commit message
- Optionally commits to git

### 5. Track Progress
```bash
speky status
```
Shows:
- All specs and their status
- Completion timestamps
- Ready-to-implement items

## What SPEKY CAN Do

✅ **Generate realistic specs** - MVP-focused, 1-2 pages, 1-2 stories  
✅ **Create accurate plans** - 3-8 tasks, <40 hours total  
✅ **Understand tech stack** - Scopes recommendations to your choices  
✅ **Track progress** - Status, completion, drift detection  
✅ **Sync documentation** - Keeps specs and code aligned  
✅ **Commit with context** - Comprehensive git messages  
✅ **Collaborate with AI** - Tech stack discussion, refinement  
✅ **Import external knowledge** - Analyze docs, propose specs  
✅ **Validate specs** - Quality checks, gap detection, suggestions  

## What SPEKY CANNOT Do (By Design)

❌ **Write production code** - That's your job (or your IDE's AI)  
❌ **Make architectural decisions** - You decide, SPEKY scopes  
❌ **Replace your IDE** - SPEKY is a companion, not a replacement  
❌ **Implement features end-to-end** - SPEKY plans, you implement  
❌ **Deploy automatically** - You control deployment  
❌ **Modify your code** - SPEKY only reads and analyzes  

## What You Should NOT Do

❌ **Skip the spec** - Always create a spec first  
❌ **Ignore out-of-scope** - Prevents feature creep  
❌ **Deviate from plan** - Stick to tasks for accurate tracking  
❌ **Skip drift detection** - Always run `speky complete` before committing  
❌ **Ignore tech stack** - It's used to scope all recommendations  
❌ **Commit without SPEKY** - Use `speky complete` for proper tracking  

## Commands Reference

| Command | Purpose | When to Use |
|---------|---------|------------|
| `speky init "idea"` | Initialize SPEKY | Project setup |
| `speky spec "name"` | Create feature spec | New feature (SPEKY-created) |
| `speky import --phase <name>` | Import external docs | Have PRD/tech docs |
| `speky validate-spec 001` | Validate spec quality | Before planning any spec |
| `speky adopt 001` | Adopt IDE-created spec | IDE created spec.md |
| `speky plan 001` | Generate implementation plan | After spec is ready |
| `speky implement 001` | Hand off to IDE for coding | Ready to code |
| `speky complete 001 --commit` | Mark complete + drift detection | Feature finished |
| `speky status` | Show project progress | Check overall status |
| `speky sync` | Update codebase context | After major code changes |
| `speky review 001` | Check spec-code alignment | Verify implementation matches spec |
| `speky cleanup` | Remove clutter files | Clean up root directory |
| `speky backlog` | Review deferred items | Check deferred validation items |

## Tips for Success

1. **Choose your workflow** - Import (A), IDE-created (B), or SPEKY-created (C)
2. **Always validate** - Use `validate-spec` before planning
3. **Follow the plan** - It's realistic and achievable
4. **Use `speky complete`** - Ensures drift detection and proper tracking
5. **Commit with SPEKY** - Comprehensive messages for better history
6. **Review regularly** - Use `speky review` to catch drift early
7. **Sync often** - Keep codebase context up to date
8. **Ask AI for help** - SPEKY uses Claude for smart suggestions

## Questions?

- Check `.speky/context/product.md` for product details
- Review spec files in `.speky/specs/*/spec.md`
- Read plan files in `.speky/specs/*/plan.md`
- Run `speky status` to see current progress

## Next Steps

1. Review the product profile: `.speky/context/product.md`
2. Choose your workflow (A, B, or C above)
3. Create your first spec or import external docs
4. Generate a plan: `speky plan 001`
5. Start implementing: `speky implement 001`

Happy building! 🚀
"""
        
        # Save to context directory
        context_dir = self.context.context_dir
        (context_dir / "IDE_CONTEXT.md").write_text(guide)

    # -------------------------------------------------------------------------
    # Command: status
    # -------------------------------------------------------------------------
    def cmd_status(self) -> bool:
        """Show status of all specs and stories"""
        if not self._require_init():
            return False
        
        Console.header("📊 Project Status")
        
        data = self.context.data
        product = data.get("product", {})
        
        print(f"Product: {product.get('name', 'Not set')}")
        print(f"Domain: {product.get('domain', 'Not set')}")
        print(f"Scale: {product.get('scale', 'Not set')}")
        
        # Specs
        print(f"\n📋 Specifications:")
        specs = []
        for spec_dir in sorted(self.context.specs_dir.glob("*/")):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                status = json.loads(status_file.read_text())
                specs.append({
                    "ID": status.get("id", "?"),
                    "Name": status.get("name", spec_dir.name)[:30],
                    "Status": status.get("status", "?"),
                })
        Console.status_table(specs, ["ID", "Name", "Status"])
        
        # Epics
        epics = self._get_all_epics()
        if epics:
            print(f"\n📦 Epics:")
            for epic in epics:
                epic_id = epic['id']
                status = epic.get('status', {})
                total = status.get('total', 0)
                completed = status.get('completed', 0)
                
                if total == 0:
                    progress = "(empty)"
                elif completed == total:
                    progress = "[COMPLETE]"
                else:
                    progress = f"({completed}/{total} done)"
                
                print(f"   {epic_id}: {epic['name'][:35]} {progress}")
                
                # Show first 3 stories
                for sid in epic.get('stories', [])[:3]:
                    story_dir = self._find_story_dir(sid)
                    if story_dir:
                        status_file = story_dir / "status.json"
                        if status_file.exists():
                            try:
                                s = json.loads(status_file.read_text())
                                icon = "[x]" if s.get('status') in ['completed', 'done'] else "[ ]"
                                print(f"      {icon} {sid}: {s.get('title', 'Untitled')[:30]}")
                            except:
                                pass
                
                if len(epic.get('stories', [])) > 3:
                    print(f"      ... and {len(epic['stories']) - 3} more")
        
        # Stories (standalone - not in epics)
        print(f"\n📝 Stories:")
        stories = []
        epic_story_ids = set()
        for epic in epics:
            epic_story_ids.update(epic.get('stories', []))
        
        for story_dir in sorted(self.context.stories_dir.glob("*/")):
            status_file = story_dir / "status.json"
            if status_file.exists():
                status = json.loads(status_file.read_text())
                story_id = status.get("id", "?")
                
                # Mark if in epic
                epic_marker = ""
                if story_id in epic_story_ids:
                    epic_marker = f" (in epic)"
                
                stories.append({
                    "ID": story_id,
                    "Type": status.get("type", "?"),
                    "Title": status.get("title", story_dir.name)[:25] + epic_marker,
                    "Status": status.get("status", "?"),
                })
        Console.status_table(stories, ["ID", "Type", "Title", "Status"])
        
        # Backlog
        counts = self._get_backlog_count()
        if counts["total"] > 0:
            print(f"\n📦 Backlog: {counts['total']} deferred item(s)")
            if counts["high"]:
                print(f"   🔴 High priority: {counts['high']}")
            if counts["medium"]:
                print(f"   🟡 Medium priority: {counts['medium']}")
            if counts["low"]:
                print(f"   🟢 Low priority: {counts['low']}")
            print(f"   Run 'speky backlog' to review")
        
        return True

    # -------------------------------------------------------------------------
    # Command: sync
    # -------------------------------------------------------------------------
    def cmd_sync(self) -> bool:
        """Sync codebase context (analyze project structure)"""
        if not self._require_init():
            return False
        
        Console.header("🔄 Sync Codebase Context")
        
        # Get list of files (excluding common ignores)
        Console.section("Scanning Codebase")
        
        ignore_patterns = {'.git', 'node_modules', '__pycache__', '.speky', 'venv', '.venv', 'dist', 'build'}
        files = []
        
        for item in self.project_root.rglob("*"):
            if item.is_file():
                # Skip ignored directories
                if any(ignored in item.parts for ignored in ignore_patterns):
                    continue
                rel_path = item.relative_to(self.project_root)
                files.append(str(rel_path))
        
        if not files:
            Console.warning("No source files found in project")
            return True
        
        Console.log(f"Found {len(files)} files")
        
        # Analyze codebase structure
        file_list = "\n".join(files[:100])  # Limit for token efficiency
        if len(files) > 100:
            file_list += f"\n... and {len(files) - 100} more files"
        
        Console.section("Analyzing Structure")
        
        # Load tech_decisions.md if it exists to provide authoritative context
        tech_decisions = ""
        tech_decisions_file = self.context.context_dir / "tech_decisions.md"
        if tech_decisions_file.exists():
            try:
                tech_decisions = tech_decisions_file.read_text()
            except Exception:
                pass
        
        codebase_analysis = self.ai.query(Prompts.analyze_codebase(file_list, tech_decisions))
        
        if codebase_analysis:
            (self.context.context_dir / "codebase.md").write_text(codebase_analysis)
            
            # Update context
            data = self.context.data
            # Store summary in JSON (smart truncate at line boundary to avoid mid-word cutoff)
            summary = self._smart_truncate(codebase_analysis, 2000)
            data["codebase"]["structure"] = summary
            data["codebase"]["last_synced"] = datetime.now().isoformat()
            self.context.save(data)
            
            # Update IDE context
            self.ide.update_context_file(self.context.get_product_context())
            
            Console.success("Codebase context updated")
            Console.files_created([f"{SPEKY_DIR}/{CONTEXT_DIR}/codebase.md"])
        
        return True

    # -------------------------------------------------------------------------
    # Command: review
    # -------------------------------------------------------------------------
    def cmd_review(self, spec_id: str = None) -> bool:
        """Check for spec-code drift"""
        if not self._require_init():
            return False
        
        Console.header("🔍 Drift Review")
        
        if spec_id:
            # Review specific spec
            spec_dir = self._find_spec_dir(spec_id)
            if not spec_dir:
                Console.error(f"Spec not found: {spec_id}")
                return False
            specs_to_review = [spec_dir]
        else:
            # Review all specs
            specs_to_review = list(self.context.specs_dir.glob("*/"))
        
        if not specs_to_review:
            Console.log("No specs to review")
            return True
        
        Console.log(f"Reviewing {len(specs_to_review)} spec(s)...")
        Console.warning("Note: Full drift detection requires MCP integration (coming soon)")
        
        # For now, just show status
        for spec_dir in specs_to_review:
            status_file = spec_dir / "status.json"
            if status_file.exists():
                status = json.loads(status_file.read_text())
                print(f"\n📋 {spec_dir.name}")
                print(f"   Status: {status.get('status', 'unknown')}")
                print(f"   Has plan: {'✓' if (spec_dir / 'plan.md').exists() else '✗'}")
        
        return True

    # -------------------------------------------------------------------------
    # Command: backlog
    # -------------------------------------------------------------------------
    def cmd_backlog(self) -> bool:
        """Review and manage deferred backlog items"""
        if not self._require_init():
            return False
        
        Console.header("📦 Backlog Review")
        
        # Check both JSON (from drift resolution) and MD (from validation)
        backlog_json = self.context.speky_dir / "backlog.json"
        backlog_md = self.context.speky_dir / "backlog.md"
        
        items = []
        
        # Load JSON backlog (from drift resolution)
        if backlog_json.exists():
            json_items = json.loads(backlog_json.read_text())
            for item in json_items:
                if item.get("status") == "pending":
                    items.append({
                        "title": item.get("name", "Unnamed"),
                        "description": item.get("description", ""),
                        "priority": "MEDIUM",
                        "priority_emoji": "🟡",
                        "source": "drift_resolution",
                        "type": item.get("type", "CODE_BEHIND"),
                        "created_at": item.get("created_at", ""),
                        "format": "json"
                    })
        
        # Load MD backlog (from validation)
        if backlog_md.exists():
            content = backlog_md.read_text()
            md_items = self._parse_backlog_items(content)
            for item in md_items:
                item["format"] = "md"
                items.append(item)
        
        if not items:
            Console.log("No backlog items! 🎉")
            Console.log("Deferred items from spec validation and drift resolution will appear here.")
            return True
        
        Console.log(f"Found {len(items)} item(s)")
        print()
        
        # Review items one by one
        items_to_remove = []
        
        for i, item in enumerate(items, 1):
            print(f"   ─────────────────────────────────────")
            print(f"   Item {i}/{len(items)}")
            print(f"   {item['priority_emoji']} [{item['priority']}] {item['title']}")
            print(f"   Source: {item.get('source', 'unknown')}")
            if item.get('notes'):
                print(f"   Notes: {item['notes']}")
            print()
            
            options = [
                "Create spec now",
                "Promote to story",
                "Keep in backlog",
                "Delete (no longer relevant)"
            ]
            choice = Console.choose("Action?", options)
            
            if choice == 0:  # Create spec
                spec_name = Console.prompt("Spec name", default=item['title'][:50])
                if self.cmd_spec(spec_name, from_backlog=True):
                    items_to_remove.append(item)
            elif choice == 1:  # Promote to story
                self._promote_backlog_item_to_story(item)
                items_to_remove.append(item)
            elif choice == 3:  # Delete
                items_to_remove.append(item)
                Console.log("Marked for removal ✓")
            
            print()
        
        # Remove processed items from backlog
        if items_to_remove:
            self._remove_backlog_items(items_to_remove)
            Console.success(f"Removed {len(items_to_remove)} item(s) from backlog")
        
        # Show summary
        remaining = self._get_backlog_count()
        if remaining["total"] > 0:
            Console.log(f"\n📦 Remaining in backlog: {remaining['total']} item(s)")
        else:
            Console.success("\n🎉 Backlog is now empty!")
        
        return True
    
    def _parse_backlog_items(self, content: str) -> List[dict]:
        """Parse backlog items from markdown content"""
        items = []
        lines = content.split("\n")
        current_item = None
        
        for line in lines:
            if line.startswith("## "):
                # Start of new item
                if current_item:
                    items.append(current_item)
                
                # Parse header: ## 🔴 [HIGH] Title...
                header = line[3:].strip()
                priority_emoji = header[0] if header else "🟡"
                
                if "[HIGH]" in header:
                    priority = "HIGH"
                elif "[MEDIUM]" in header:
                    priority = "MEDIUM"
                elif "[LOW]" in header:
                    priority = "LOW"
                else:
                    priority = "MEDIUM"
                
                # Extract title (after priority tag)
                title = header
                for tag in ["🔴", "🟡", "🟢", "[HIGH]", "[MEDIUM]", "[LOW]"]:
                    title = title.replace(tag, "").strip()
                
                current_item = {
                    "priority_emoji": priority_emoji,
                    "priority": priority,
                    "title": title,
                    "raw_header": line
                }
            
            elif current_item and line.startswith("- **"):
                # Parse metadata
                if "Source" in line:
                    current_item["source"] = line.split(":")[-1].strip()
                elif "Notes" in line:
                    current_item["notes"] = line.split(":", 1)[-1].strip()
                elif "Full description" in line:
                    current_item["description"] = line.split(":", 1)[-1].strip()
        
        if current_item:
            items.append(current_item)
        
        return items
    
    def _promote_backlog_item_to_story(self, item: dict) -> None:
        """Promote a backlog item to a story"""
        Console.section("Promote to Story")
        
        title = item.get("title", "")[:50]
        Console.log(f"Title: {title}")
        custom_title = Console.prompt("Edit title (Enter to accept)")
        if custom_title.strip():
            title = custom_title
        
        type_options = [
            "enhancement - Feature improvement",
            "tech_debt - Code quality improvement",
            "spike - Needs research/investigation"
        ]
        type_choice = Console.choose("Story type?", type_options)
        story_type = ["enhancement", "tech_debt", "spike"][type_choice]
        
        self.cmd_story(title, story_type, from_backlog=True, backlog_source={
            "item": item.get("description", item.get("title", "")),
            "type": "backlog",
            "notes": item.get("notes", ""),
            "source_spec": item.get("source", "")
        })
    
    def _remove_backlog_items(self, items_to_remove: List[dict]) -> None:
        """Remove items from backlog file (supports both JSON and MD formats)"""
        # Handle JSON backlog items
        json_items_to_remove = [item for item in items_to_remove if item.get("format") == "json"]
        if json_items_to_remove:
            backlog_json = self.context.speky_dir / "backlog.json"
            if backlog_json.exists():
                backlog = json.loads(backlog_json.read_text())
                # Mark as completed instead of removing
                for item in json_items_to_remove:
                    for backlog_item in backlog:
                        if (backlog_item.get("name") == item.get("title") and 
                            backlog_item.get("status") == "pending"):
                            backlog_item["status"] = "completed"
                            break
                backlog_json.write_text(json.dumps(backlog, indent=2))
        
        # Handle MD backlog items
        md_items_to_remove = [item for item in items_to_remove if item.get("format") == "md"]
        if md_items_to_remove:
            backlog_file = self.context.speky_dir / "backlog.md"
            
            if not backlog_file.exists():
                return
            
            content = backlog_file.read_text()
            
            # Remove each item's section
            for item in md_items_to_remove:
                raw_header = item.get("raw_header", "")
                if raw_header:
                    # Find and remove the section (from header to next --- or end)
                    sections = content.split("---")
                    new_sections = []
                    for section in sections:
                        if raw_header not in section:
                            new_sections.append(section)
                    content = "---".join(new_sections)
            
            # Clean up extra whitespace and separators
            content = content.replace("---\n\n---", "---")
            content = content.replace("---\n---", "---")
            
            backlog_file.write_text(content)

    # -------------------------------------------------------------------------
    # Command: validate-spec
    # -------------------------------------------------------------------------
    def cmd_validate_spec(self, spec_ref: str, quick: bool = False) -> bool:
        """Validate a spec - check quality, find gaps, suggest improvements"""
        if not self._require_init():
            return False
        
        Console.header("📋 Validate Specification")
        
        # Resolve spec reference - could be ID or file path
        spec_file = self._resolve_spec_file(spec_ref)
        if not spec_file:
            return False
        
        spec_content = spec_file.read_text()
        spec_name = spec_file.parent.name
        spec_id = spec_name.split("-")[0] if "-" in spec_name else spec_name
        
        Console.log(f"Validating: {spec_name}")
        
        # Load existing validation session if available, otherwise create new
        # This preserves user decisions and context across validation runs
        session = self._load_validation_session(spec_file)
        if session:
            Console.log("📂 Resuming previous validation session")
            # Refresh project context (may have changed since last run)
            session.project_context = self._gather_validation_context(spec_id)
        else:
            # Initialize new validation session with project context
            session = ValidationSession()
            session.project_context = self._gather_validation_context(spec_id)
            
            # Find related specs automatically (only on first run)
            related_specs = self._find_related_specs(spec_content, spec_id)
            session.related_specs = related_specs
            
            if session.related_specs:
                Console.log(f"Found {len(session.related_specs)} potentially related spec(s)")
        
        # Run validation with context
        validation_result = self._validate_spec_content(spec_content, spec_name, session)
        validation_result["session"] = session
        
        # Display results - interactive or quick
        if quick:
            self._display_validation_quick(validation_result)
        else:
            validation_result = self._display_validation_results(validation_result, spec_file, session)
        
        return validation_result.get("is_valid", False)
    
    # -------------------------------------------------------------------------
    # Command: validate-story
    # -------------------------------------------------------------------------
    def cmd_validate_story(self, story_ref: str, quick: bool = False) -> bool:
        """Validate a story - check completeness for complex stories"""
        if not self._require_init():
            return False
        
        Console.header("📝 Validate Story")
        
        # Resolve story reference - could be ID or file path
        story_file = self._resolve_story_file(story_ref)
        if not story_file:
            return False
        
        story_content = story_file.read_text()
        story_name = story_file.parent.name
        story_id = story_name.split("-")[0] if "-" in story_name else story_name
        
        Console.log(f"Validating: {story_name}")
        
        # Get project context
        product_context = self.context.get_product_context()
        tech_stack = json.dumps(self.context.data.get("tech_stack", {}), indent=2)
        
        # Get related specs content if story references them
        related_specs_content = ""
        status_file = story_file.parent / "status.json"
        if status_file.exists():
            try:
                status = json.loads(status_file.read_text())
                related_spec_ids = status.get("related_specs", [])
                for spec_id in related_spec_ids[:2]:  # Limit to 2 specs
                    spec_content = self._get_spec_content_brief(spec_id)
                    if spec_content:
                        related_specs_content += f"\n--- Spec {spec_id} ---\n{spec_content}\n"
            except:
                pass
        
        # Run AI validation
        Console.section("AI Analysis")
        validation_response = self.ai.query(Prompts.validate_story(
            story_content,
            project_context=product_context,
            related_specs=related_specs_content,
            tech_stack=tech_stack
        ))
        
        if not validation_response:
            Console.error("Failed to get AI validation")
            return False
        
        # Parse and display results
        validation_result = self._parse_story_validation(validation_response)
        
        if quick:
            self._display_story_validation_quick(validation_result)
        else:
            self._display_story_validation_interactive(validation_result, story_file)
        
        return validation_result.get("score", 0) >= 7
    
    def _resolve_story_file(self, story_ref: str) -> Optional[Path]:
        """Resolve story reference to story.md file path"""
        # Check if it's a file path
        if story_ref.endswith(".md"):
            path = Path(story_ref)
            if path.exists():
                return path
            Console.error(f"File not found: {story_ref}")
            return None
        
        # Try to find by story ID
        story_dir = self._find_story_dir(story_ref)
        if story_dir:
            story_file = story_dir / "story.md"
            if story_file.exists():
                return story_file
            Console.error(f"story.md not found in {story_dir}")
            return None
        
        # Try pattern matching
        story_dir = self._find_story_dir_by_pattern(story_ref)
        if story_dir:
            story_file = story_dir / "story.md"
            if story_file.exists():
                return story_file
        
        Console.error(f"Story not found: {story_ref}")
        Console.log("Provide a story ID (e.g., F001) or file path")
        return None
    
    def _find_story_dir_by_pattern(self, story_id: str) -> Optional[Path]:
        """Find story directory by ID pattern (handles IDE-created stories)"""
        # First try exact match
        story_dir = self._find_story_dir(story_id)
        if story_dir:
            return story_dir
        
        # Try pattern matching for directories starting with story_id
        for dir_path in self.context.stories_dir.glob(f"{story_id}-*"):
            if dir_path.is_dir():
                return dir_path
        
        # Try case-insensitive match
        for dir_path in self.context.stories_dir.glob("*/"):
            dir_name = str(dir_path.name)
            if dir_name.lower().startswith(story_id.lower()):
                return dir_path
        
        return None
    
    def _parse_story_validation(self, response: str) -> dict:
        """Parse AI validation response for story"""
        result = {
            "gaps": [],
            "suggestions": [],
            "scope_assessment": "",
            "score": 5,
            "summary": "",
            "raw": response
        }
        
        # Parse gaps
        gaps_match = re.search(r'## Gaps/Issues\s*\n(.*?)(?=\n##|\Z)', response, re.DOTALL)
        if gaps_match:
            gaps_text = gaps_match.group(1)
            for line in gaps_text.split('\n'):
                line = line.strip()
                if line.startswith('-') or line.startswith('*'):
                    gap = line.lstrip('-*').strip()
                    if gap and len(gap) > 5:
                        result["gaps"].append(gap)
        
        # Parse suggestions
        sugg_match = re.search(r'## Suggestions\s*\n(.*?)(?=\n##|\Z)', response, re.DOTALL)
        if sugg_match:
            sugg_text = sugg_match.group(1)
            for line in sugg_text.split('\n'):
                line = line.strip()
                if line.startswith('-') or line.startswith('*'):
                    sugg = line.lstrip('-*').strip()
                    if sugg and len(sugg) > 5:
                        result["suggestions"].append(sugg)
        
        # Parse scope assessment
        scope_match = re.search(r'## Scope Assessment\s*\n(.*?)(?=\n##|\Z)', response, re.DOTALL)
        if scope_match:
            result["scope_assessment"] = scope_match.group(1).strip()
        
        # Parse score
        score_match = re.search(r'## Quality Score\s*\n.*?(\d+)', response, re.DOTALL)
        if score_match:
            result["score"] = int(score_match.group(1))
        
        # Parse summary
        summary_match = re.search(r'## Summary\s*\n(.*?)(?=\n##|\Z)', response, re.DOTALL)
        if summary_match:
            result["summary"] = summary_match.group(1).strip()
        
        return result
    
    def _display_story_validation_quick(self, result: dict):
        """Display story validation results in quick mode"""
        score = result.get("score", 5)
        
        # Score display
        if score >= 8:
            Console.success(f"Quality Score: {score}/10")
        elif score >= 6:
            Console.warning(f"Quality Score: {score}/10")
        else:
            Console.error(f"Quality Score: {score}/10")
        
        # Summary
        if result.get("summary"):
            print(f"\n{result['summary']}")
        
        # Gaps
        gaps = result.get("gaps", [])
        if gaps:
            Console.section("Gaps/Issues", f"{len(gaps)} found")
            for gap in gaps[:5]:
                print(f"  • {gap}")
        
        # Scope assessment
        if result.get("scope_assessment"):
            Console.section("Scope Assessment")
            print(f"  {result['scope_assessment'][:200]}")
    
    def _display_story_validation_interactive(self, result: dict, story_file: Path):
        """Display story validation results with interactive options"""
        self._display_story_validation_quick(result)
        
        # Show suggestions
        suggestions = result.get("suggestions", [])
        if suggestions:
            Console.section("Suggestions", f"{len(suggestions)} available")
            for i, sugg in enumerate(suggestions[:5], 1):
                print(f"  {i}. {sugg}")
        
        story_id = story_file.parent.name.split("-")[0]
        score = result.get("score", 5)
        scope_assessment = result.get("scope_assessment", "").lower()
        needs_split = "split" in scope_assessment
        
        # Interactive loop
        while True:
            print("\n" + "="*60)
            print("📋 What would you like to do?")
            print("")
            print("  [v] View full analysis")
            print("  [e] Edit story.md (apply fixes manually)")
            
            if needs_split:
                print("  [s] Split story (AI will create sub-stories)")
            
            if suggestions:
                print("  [f] Apply AI suggestions to story.md")
            
            print("")
            if score >= 7:
                print("  [a] ✅ Adopt story (ready for implementation)")
            else:
                print("  [a] ⚠️  Adopt story anyway (has issues)")
            
            print("  [r] Re-validate (after making changes)")
            print("  [q] Quit")
            
            choice = Console.prompt("\nChoice (v/a/r/q)", default="q").strip().lower()
            
            if choice == 'v':
                print("\n" + "="*60)
                print(result.get("raw", "No analysis available"))
                print("\n" + "="*60)
                Console.pause()
                
            elif choice == 'e':
                import subprocess
                editor = os.environ.get('EDITOR', 'nano')
                subprocess.run([editor, str(story_file)])
                Console.success("Story edited. Re-validate to check improvements.")
                
            elif choice == 's' and needs_split:
                self._split_story_interactive(story_file, result)
                return  # Exit after split
                
            elif choice == 'f' and suggestions:
                self._apply_story_suggestions(story_file, result)
                Console.success("Suggestions applied. Re-validate to verify.")
                
            elif choice == 'a':
                if score < 7:
                    if not Console.confirm("Story has issues. Adopt anyway?", default=False):
                        continue
                # Run adopt
                Console.log(f"\nAdopting story {story_id}...")
                success = self._adopt_story(story_id, skip_validation=True)
                if success:
                    print("\n" + "="*60)
                    print("📋 Next steps:")
                    print(f"   1. Generate plan (optional): speky plan {story_id}")
                    print(f"   2. Implement: speky implement {story_id}")
                    print(f"   3. Complete: speky complete {story_id}")
                return
                
            elif choice == 'r':
                Console.log("Re-validating story...")
                # Re-read and re-validate
                story_content = story_file.read_text()
                product_context = self.context.get_product_context()
                tech_stack = json.dumps(self.context.data.get("tech_stack", {}), indent=2)
                
                validation_response = self.ai.query(Prompts.validate_story(
                    story_content,
                    project_context=product_context,
                    related_specs="",
                    tech_stack=tech_stack
                ))
                
                if validation_response:
                    result = self._parse_story_validation(validation_response)
                    score = result.get("score", 5)
                    scope_assessment = result.get("scope_assessment", "").lower()
                    needs_split = "split" in scope_assessment
                    suggestions = result.get("suggestions", [])
                    
                    # Show updated results
                    print("\n")
                    self._display_story_validation_quick(result)
                    
                    if suggestions:
                        Console.section("Suggestions", f"{len(suggestions)} available")
                        for i, sugg in enumerate(suggestions[:5], 1):
                            print(f"  {i}. {sugg}")
                else:
                    Console.error("Failed to re-validate")
                    
            elif choice == 'q':
                print("\n📋 To continue later:")
                print(f"   • Re-validate: speky validate-story {story_id}")
                print(f"   • Adopt: speky adopt {story_id}")
                print(f"   • Edit: {story_file}")
                return
            else:
                Console.warning("Invalid choice. Try again.")
    
    def _split_story_interactive(self, story_file: Path, validation_result: dict):
        """Split a story into multiple smaller stories based on AI recommendation"""
        story_content = story_file.read_text()
        story_dir = story_file.parent
        story_id = story_dir.name.split("-")[0]
        
        Console.section("Split Story", "AI will suggest how to break this down")
        
        # Get AI to suggest split
        split_prompt = f"""This story needs to be split into smaller, focused stories.

ORIGINAL STORY:
{story_content}

SCOPE ASSESSMENT:
{validation_result.get('scope_assessment', '')}

Create 2-4 smaller stories that together cover the original scope.
Each story should be:
- Independently implementable
- Testable on its own
- 30 min to 2 hours of work

For each sub-story, provide:
1. Title
2. Brief description (2-3 sentences)
3. Key acceptance criteria (2-4 items)

Format as:
## Story 1: [Title]
**Description**: ...
**Acceptance Criteria**:
- [ ] ...

## Story 2: [Title]
...
"""
        
        split_response = self.ai.query(split_prompt)
        
        if not split_response:
            Console.error("Failed to generate split suggestions")
            return
        
        print("\n" + split_response)
        
        print("\n" + "="*60)
        if Console.confirm("Create these sub-stories?", default=True):
            # Parse and create sub-stories
            sub_stories = self._parse_split_stories(split_response, story_id)
            
            if sub_stories:
                for i, sub in enumerate(sub_stories, 1):
                    new_id = f"{story_id[0]}{int(story_id[1:]) + i:03d}"
                    new_slug = sub['title'].lower().replace(' ', '-')[:30]
                    new_dir = self.context.stories_dir / f"{new_id}-{new_slug}"
                    new_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Create story.md
                    story_md = f"""# {sub['title']}

## Description
{sub['description']}

## Acceptance Criteria
{chr(10).join('- [ ] ' + c for c in sub['criteria'])}

## Context
- **Parent Story**: {story_id}
- **Split From**: {story_dir.name}

## Notes
This story was split from {story_id} for better focus and testability.
"""
                    (new_dir / "story.md").write_text(story_md)
                    
                    # Create status.json
                    status = {
                        "id": new_id,
                        "title": sub['title'],
                        "type": "feature",
                        "status": ItemStatus.DRAFT.value,
                        "created": datetime.now().isoformat(),
                        "parent_story": story_id,
                    }
                    (new_dir / "status.json").write_text(json.dumps(status, indent=2))
                    
                    Console.success(f"Created: {new_id} - {sub['title']}")
                
                # Update original story status
                status_file = story_dir / "status.json"
                if status_file.exists():
                    status = json.loads(status_file.read_text())
                    status["status"] = "split"
                    status["split_into"] = [f"{story_id[0]}{int(story_id[1:]) + i:03d}" for i in range(1, len(sub_stories) + 1)]
                    status_file.write_text(json.dumps(status, indent=2))
                
                print("\n📋 Next steps:")
                print(f"   • Original story {story_id} marked as 'split'")
                print(f"   • Implement sub-stories in order")
                print(f"   • Run: speky status to see all stories")
        else:
            Console.log("Split cancelled. You can manually edit the story.")
    
    def _parse_split_stories(self, response: str, parent_id: str) -> List[dict]:
        """Parse AI split response into story definitions"""
        stories = []
        current = None
        
        for line in response.split('\n'):
            line = line.strip()
            
            if line.startswith('## Story') and ':' in line:
                if current:
                    stories.append(current)
                title = line.split(':', 1)[1].strip()
                current = {'title': title, 'description': '', 'criteria': []}
                
            elif current:
                if line.startswith('**Description**:'):
                    current['description'] = line.replace('**Description**:', '').strip()
                elif line.startswith('- [ ]') or line.startswith('- [x]'):
                    criterion = line.lstrip('- [ ]').lstrip('- [x]').strip()
                    if criterion:
                        current['criteria'].append(criterion)
                elif current['description'] == '' and line and not line.startswith('**'):
                    current['description'] = line
        
        if current:
            stories.append(current)
        
        return stories
    
    def _apply_story_suggestions(self, story_file: Path, validation_result: dict):
        """Apply AI suggestions to improve the story"""
        story_content = story_file.read_text()
        suggestions = validation_result.get("suggestions", [])
        gaps = validation_result.get("gaps", [])
        
        Console.section("Apply Suggestions", "AI will update story.md")
        
        # Show what will be added
        print("\nWill address:")
        for gap in gaps[:3]:
            print(f"  ❌ {gap[:60]}...")
        for sugg in suggestions[:3]:
            print(f"  💡 {sugg[:60]}...")
        
        if not Console.confirm("\nApply these improvements?", default=True):
            return
        
        # Get AI to improve the story
        improve_prompt = f"""Improve this story by addressing the gaps and applying suggestions.

ORIGINAL STORY:
{story_content}

GAPS TO ADDRESS:
{chr(10).join('- ' + g for g in gaps)}

SUGGESTIONS TO APPLY:
{chr(10).join('- ' + s for s in suggestions)}

Return the COMPLETE improved story.md content.
Keep the same structure but add missing details.
Be specific with technical details (durations, thresholds, etc.).
Add error handling and edge cases to acceptance criteria.
"""
        
        improved = self.ai.query(improve_prompt)
        
        if not improved:
            Console.error("Failed to generate improvements")
            return
        
        # Backup original
        backup_file = story_file.parent / "story.md.backup"
        backup_file.write_text(story_content)
        Console.log(f"Backup saved: {backup_file.name}")
        
        # Write improved version
        story_file.write_text(improved)
        Console.success("Story updated with improvements")
    
    def _gather_validation_context(self, current_spec_id: str) -> dict:
        """Gather full project context for validation - enhanced with tech decisions and POC recommendations"""
        context = {
            "product": self.context.data.get("product", {}),
            "tech_stack": self.context.data.get("tech_stack", {}),
            "all_specs": self._get_all_specs_summary(exclude_id=current_spec_id),
            "tech_decisions": self._load_tech_decisions(),
            "poc_recommendations": self._load_poc_recommendations(),
        }
        return context
    
    def _load_tech_decisions(self) -> str:
        """Load tech_decisions.md if it exists - authoritative tech choices"""
        tech_decisions_file = self.context.context_dir / "tech_decisions.md"
        if tech_decisions_file.exists():
            return tech_decisions_file.read_text()
        return ""
    
    def _load_poc_recommendations(self) -> str:
        """Load POC import recommendations if they exist"""
        recommendations = []
        poc_import_dir = self.context.speky_dir / "imports" / "poc_import"
        
        if poc_import_dir.exists():
            for poc_dir in poc_import_dir.iterdir():
                if poc_dir.is_dir():
                    rec_file = poc_dir / "recommendations.md"
                    if rec_file.exists():
                        content = rec_file.read_text()
                        # Extract just the key decisions (first 2000 chars)
                        recommendations.append(f"## From {poc_dir.name}\n{content[:2000]}")
        
        return "\n\n".join(recommendations) if recommendations else ""
    
    def _get_all_specs_summary(self, exclude_id: str = None) -> List[dict]:
        """Get summary of all specs for cross-reference"""
        specs = []
        specs_dir = self.context.specs_dir
        
        if not specs_dir.exists():
            return specs
        
        for spec_dir in sorted(specs_dir.iterdir()):
            if not spec_dir.is_dir():
                continue
            
            spec_id = spec_dir.name.split("-")[0] if "-" in spec_dir.name else spec_dir.name
            
            # Skip the spec being validated
            if exclude_id and spec_id == exclude_id:
                continue
            
            spec_file = spec_dir / "spec.md"
            status_file = spec_dir / "status.json"
            
            if not spec_file.exists():
                continue
            
            # Get basic info
            spec_info = {
                "id": spec_id,
                "name": spec_dir.name,
                "path": str(spec_dir),
            }
            
            # Get status info
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    spec_info["status"] = status.get("status", "draft")
                    spec_info["priority"] = status.get("priority", "P1")
                except:
                    pass
            
            # Get brief content (first 500 chars + key sections)
            content = spec_file.read_text()
            spec_info["brief"] = self._extract_spec_brief(content)
            spec_info["keywords"] = self._extract_spec_keywords(content)
            
            specs.append(spec_info)
        
        return specs
    
    def _extract_spec_brief(self, content: str) -> str:
        """Extract brief summary from spec content"""
        # Get overview section if present
        lines = content.split("\n")
        brief_lines = []
        in_overview = False
        
        for line in lines[:50]:  # First 50 lines
            if "## overview" in line.lower():
                in_overview = True
                continue
            if in_overview:
                if line.startswith("##"):
                    break
                if line.strip():
                    brief_lines.append(line.strip())
                    if len(brief_lines) >= 3:
                        break
        
        if brief_lines:
            return " ".join(brief_lines)[:300]
        
        # Fallback: first non-header paragraph
        for line in lines[1:20]:
            if line.strip() and not line.startswith("#"):
                return line.strip()[:300]
        
        return content[:200]
    
    def _extract_spec_keywords(self, content: str) -> List[str]:
        """Extract key terms from spec for matching"""
        # Common feature-related words to look for
        keywords = []
        content_lower = content.lower()
        
        # Extract from headers
        for line in content.split("\n"):
            if line.startswith("#"):
                words = line.replace("#", "").strip().split()
                keywords.extend([w.lower() for w in words if len(w) > 3])
        
        # Look for key terms
        key_terms = [
            "auth", "authentication", "login", "user", "account",
            "api", "endpoint", "rest", "graphql",
            "database", "storage", "cache", "sync",
            "notification", "push", "email", "sms",
            "payment", "billing", "subscription",
            "search", "filter", "sort",
            "upload", "download", "file", "media",
            "bookmark", "save", "favorite", "spaces",
            "browser", "webview", "navigation",
            "settings", "preferences", "config",
            "profile", "dashboard", "admin",
        ]
        
        for term in key_terms:
            if term in content_lower:
                keywords.append(term)
        
        return list(set(keywords))[:15]
    
    def _find_related_specs(self, spec_content: str, current_spec_id: str) -> List[dict]:
        """Find specs that might be related based on content analysis"""
        all_specs = self._get_all_specs_summary(exclude_id=current_spec_id)
        current_keywords = self._extract_spec_keywords(spec_content)
        
        related = []
        for spec in all_specs:
            spec_keywords = spec.get("keywords", [])
            
            # Find overlapping keywords
            overlap = set(current_keywords) & set(spec_keywords)
            
            if len(overlap) >= 2:  # At least 2 keywords in common
                related.append({
                    "id": spec["id"],
                    "name": spec["name"],
                    "brief": spec.get("brief", ""),
                    "overlap": list(overlap),
                    "relevance": len(overlap)
                })
        
        # Sort by relevance
        related.sort(key=lambda x: x["relevance"], reverse=True)
        return related[:5]  # Top 5 related specs
    
    def _format_tech_stack_for_prompt(self) -> str:
        """Format tech stack for AI prompts"""
        tech_stack = self.context.data.get("tech_stack", {})
        if not tech_stack:
            return "Not specified"
        
        parts = []
        for key, value in tech_stack.items():
            if value:
                parts.append(f"- {key}: {value}")
        
        return "\n".join(parts) if parts else "Not specified"
    
    def _format_related_specs_for_prompt(self, related_specs: List[dict]) -> str:
        """Format related specs for AI prompts"""
        if not related_specs:
            return ""
        
        parts = []
        for spec in related_specs:
            overlap = ", ".join(spec.get("overlap", []))
            parts.append(f"Spec {spec['id']} ({spec['name']}): {spec.get('brief', '')[:200]}")
            parts.append(f"  Overlapping concepts: {overlap}")
        
        return "\n".join(parts)
    
    def _extract_spec_references_from_context(self, user_context: str) -> List[str]:
        """Extract spec IDs mentioned in user context"""
        import re
        
        # Patterns to match spec references
        patterns = [
            r'spec\s*(\d{3})',  # "spec 006"
            r'spec\s*#(\d{3})',  # "spec #006"
            r'(\d{3})-\w+',  # "006-spaces"
            r'spec\s+(\d+)',  # "spec 6"
        ]
        
        found_ids = set()
        for pattern in patterns:
            matches = re.findall(pattern, user_context.lower())
            for match in matches:
                # Normalize to 3 digits
                spec_id = str(match).zfill(3)
                found_ids.add(spec_id)
        
        return list(found_ids)
    
    def _load_spec_content(self, spec_id: str) -> Optional[str]:
        """Load spec content by ID"""
        spec_dir = self._find_spec_dir(spec_id)
        if spec_dir:
            spec_file = spec_dir / "spec.md"
            if spec_file.exists():
                return spec_file.read_text()
        return None
    
    def _resolve_spec_file(self, spec_ref: str) -> Optional[Path]:
        """Resolve spec reference to actual file path"""
        # Check if it's a file path
        path = Path(spec_ref)
        if path.exists() and path.is_file():
            return path
        
        # Check if it's a spec ID
        spec_dir = self._find_spec_dir(spec_ref)
        if spec_dir:
            spec_file = spec_dir / "spec.md"
            if spec_file.exists():
                return spec_file
        
        # Check if it's a directory path
        if path.exists() and path.is_dir():
            spec_file = path / "spec.md"
            if spec_file.exists():
                return spec_file
        
        Console.error(f"Could not find spec: {spec_ref}")
        Console.log("Provide a spec ID (e.g., 001) or file path")
        return None
    
    def _validate_spec_content(self, content: str, spec_name: str, 
                                session: ValidationSession = None) -> dict:
        """Validate spec content and return detailed results - context-aware"""
        results = {
            "is_valid": True,
            "format_checks": [],
            "gaps": [],
            "suggestions": [],
            "cross_spec_concerns": [],
            "score": 10,
        }
        
        # Format checks - required sections
        required_sections = [
            ("## Overview", "Overview section"),
            ("## MVP Scope", "MVP Scope section"),
            ("## User Stories", "User Stories section"),
            ("## Requirements", "Requirements section"),
            ("## Out of Scope", "Out of Scope section"),
        ]
        
        for section, name in required_sections:
            if section.lower() in content.lower():
                results["format_checks"].append({"name": name, "status": "pass"})
            else:
                results["format_checks"].append({"name": name, "status": "fail"})
                results["gaps"].append(f"Missing required section: {name}")
                results["score"] -= 1
                results["is_valid"] = False
        
        # Prepare context for AI analysis
        project_context = ""
        tech_stack = ""
        related_specs = ""
        tech_decisions = ""
        poc_recommendations = ""
        
        if session:
            # Format product context
            product = session.project_context.get("product", {})
            if product:
                project_context = f"""Product: {product.get('name', 'Unknown')}
Description: {product.get('description', '')}
Target Users: {product.get('target_users', '')}"""
            
            # Format tech stack
            tech_stack = self._format_tech_stack_for_prompt()
            
            # Get tech decisions (authoritative)
            tech_decisions = session.project_context.get("tech_decisions", "")
            
            # Get POC recommendations
            poc_recommendations = session.project_context.get("poc_recommendations", "")
            
            # Format related specs
            if session.related_specs:
                related_specs = self._format_related_specs_for_prompt(session.related_specs)
        
        # Check for tech decision violations BEFORE AI analysis
        if tech_decisions:
            tech_violations = self._check_tech_decision_violations(content, tech_decisions)
            if tech_violations:
                results["tech_violations"] = tech_violations
                for violation in tech_violations:
                    results["gaps"].append(f"Tech decision violation: {violation}")
                    results["score"] -= 2  # Tech violations are serious
        
        # Validate spec dependencies exist
        dep_issues = self._validate_spec_dependencies_exist(content, spec_name)
        if dep_issues:
            results["dependency_issues"] = dep_issues
            for issue in dep_issues:
                results["gaps"].append(f"Dependency issue: {issue}")
                results["score"] -= 1
        
        # Detect feature overlaps with existing specs
        current_spec_id = spec_name.split("-")[0] if "-" in spec_name else spec_name
        feature_overlaps = self._detect_feature_overlap(content, current_spec_id)
        if feature_overlaps:
            results["feature_overlaps"] = feature_overlaps
            for overlap in feature_overlaps[:3]:  # Top 3 overlaps
                results["gaps"].append(
                    f"Feature overlap: '{overlap['current_feature'][:50]}...' similar to {overlap['other_spec']}"
                )
                results["score"] -= 1
        
        # Use AI for deeper analysis with context
        analysis = self.ai.query(Prompts.validate_spec(
            content, 
            project_context=project_context,
            related_specs=related_specs,
            tech_stack=tech_stack,
            tech_decisions=tech_decisions,
            poc_recommendations=poc_recommendations
        ))
        
        if analysis:
            # Parse AI analysis
            ai_gaps = self._parse_validation_gaps(analysis)
            ai_suggestions = self._parse_validation_suggestions(analysis)
            cross_spec = self._parse_cross_spec_concerns(analysis)
            
            # NEW: Extract gap→fix mappings for caching (reduces AI calls)
            gap_fix_mappings = self._parse_gap_fix_mappings(analysis)
            
            # Deduplicate AI gaps against format check gaps (avoid showing same issue twice)
            existing_gap_keywords = set()
            for gap in results["gaps"]:
                # Extract key terms from existing gaps for matching
                gap_lower = gap.lower()
                for keyword in ["overview", "mvp scope", "user stories", "requirements", "out of scope"]:
                    if keyword in gap_lower:
                        existing_gap_keywords.add(keyword)
            
            # Only add AI gaps that don't duplicate format check findings
            for ai_gap in ai_gaps:
                ai_gap_lower = ai_gap.lower()
                is_duplicate = False
                for keyword in existing_gap_keywords:
                    if keyword in ai_gap_lower:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    results["gaps"].append(ai_gap)
            
            # Deduplicate suggestions similarly
            existing_suggestions = set(s.lower()[:50] for s in results["suggestions"])
            for suggestion in ai_suggestions:
                if suggestion.lower()[:50] not in existing_suggestions:
                    results["suggestions"].append(suggestion)
                    existing_suggestions.add(suggestion.lower()[:50])
            
            results["cross_spec_concerns"] = cross_spec
            results["ai_analysis"] = analysis
            results["gap_fix_cache"] = gap_fix_mappings  # Cache for later use
            
            # Adjust score based on gaps and cross-spec concerns
            results["score"] = max(0, results["score"] - len(ai_gaps) - len(cross_spec))
        
        return results
    
    def _parse_cross_spec_concerns(self, analysis: str) -> List[str]:
        """Parse cross-spec concerns from AI analysis"""
        concerns = []
        in_cross_spec = False
        
        for line in analysis.split("\n"):
            line = line.strip()
            if "cross-spec" in line.lower() or "overlap" in line.lower() or "conflict" in line.lower():
                in_cross_spec = True
            if in_cross_spec and line.startswith("-"):
                concerns.append(line[1:].strip())
            if line.startswith("##") and "cross" not in line.lower() and "overlap" not in line.lower():
                in_cross_spec = False
        
        return concerns[:5]  # Limit to top 5
    
    def _parse_validation_gaps(self, analysis: str) -> List[str]:
        """Parse gaps from AI analysis - maintains backward compatibility
        
        Now returns list of gap descriptions. The gap→fix mappings are extracted
        separately by _parse_gap_fix_mappings() for caching.
        """
        gaps = []
        in_gaps = False
        for line in analysis.split("\n"):
            line = line.strip()
            if "gap" in line.lower() or "missing" in line.lower() or "issue" in line.lower():
                in_gaps = True
            if in_gaps:
                # Handle both old format (- gap) and new format (- **Gap**: ...)
                if line.startswith("- **Gap**:"):
                    gap_text = line.replace("- **Gap**:", "").strip()
                    gaps.append(gap_text)
                elif line.startswith("-") and "**Fix**:" not in line:
                    gaps.append(line[1:].strip())
            if line.startswith("##") and not any(x in line.lower() for x in ["gap", "issue"]):
                in_gaps = False
        return gaps[:5]  # Limit to top 5
    
    def _parse_gap_fix_mappings(self, analysis: str) -> Dict[str, str]:
        """Parse gap→fix pairs from structured AI response
        
        Returns dict mapping gap text to its fix recommendation.
        This enables caching AI suggestions without additional calls.
        """
        mappings = {}
        in_gaps = False
        current_gap = None
        
        lines = analysis.split("\n")
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Detect gaps section
            if "gap" in line.lower() and "issue" in line.lower():
                in_gaps = True
                continue
            
            # Exit gaps section
            if line.startswith("##") and not any(x in line.lower() for x in ["gap", "issue"]):
                in_gaps = False
                current_gap = None
                continue
            
            if in_gaps:
                # Extract gap
                if line.startswith("- **Gap**:"):
                    current_gap = line.replace("- **Gap**:", "").strip()
                
                # Extract fix for current gap
                elif line.startswith("**Fix**:") and current_gap:
                    fix_text = line.replace("**Fix**:", "").strip()
                    # Check if fix continues on next lines (multi-line fix)
                    j = i + 1
                    while j < len(lines) and not lines[j].strip().startswith(("- **Gap**:", "**Fix**:", "##")):
                        if lines[j].strip():
                            fix_text += " " + lines[j].strip()
                        j += 1
                    mappings[current_gap] = fix_text
                    current_gap = None  # Reset for next gap
        
        return mappings
    
    def _parse_validation_suggestions(self, analysis: str) -> List[str]:
        """Parse suggestions from AI analysis"""
        suggestions = []
        in_suggestions = False
        for line in analysis.split("\n"):
            line = line.strip()
            if "suggestion" in line.lower() or "recommend" in line.lower() or "improve" in line.lower():
                in_suggestions = True
            if in_suggestions and line.startswith("-"):
                suggestions.append(line[1:].strip())
            if line.startswith("##") and "suggestion" not in line.lower():
                in_suggestions = False
        return suggestions[:5]  # Limit to top 5
    
    def _filter_suggestions_by_fixed_items(self, original_suggestions: List[str], 
                                           fixed_items: List[dict]) -> List[str]:
        """Filter out suggestions that are semantically similar to already-fixed items
        
        OPTIMIZATION: This replaces the expensive _regenerate_suggestions_fresh() which
        called AI again. Instead, we filter existing suggestions using semantic matching.
        
        Args:
            original_suggestions: Suggestions from initial validation
            fixed_items: Items user already fixed during this session
            
        Returns:
            Filtered list of suggestions excluding duplicates of fixed items
        """
        if not fixed_items:
            return original_suggestions
        
        # Build list of fixed item descriptions for semantic matching
        fixed_descriptions = []
        for item in fixed_items:
            item_text = item.get("item", "")
            fixed_descriptions.append(item_text.lower())
        
        # Filter out suggestions that are semantically similar to fixed items
        filtered_suggestions = []
        for suggestion in original_suggestions:
            suggestion_lower = suggestion.lower()
            is_duplicate = False
            
            for fixed_desc in fixed_descriptions:
                # Check for semantic similarity using keyword overlap
                similarity = self._calculate_text_similarity(suggestion_lower, fixed_desc)
                if similarity > 0.4:  # 40% keyword overlap = likely duplicate
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                filtered_suggestions.append(suggestion)
        
        return filtered_suggestions
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts based on significant words"""
        # Extract significant words (exclude common words)
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 
                      'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                      'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
                      'as', 'into', 'through', 'during', 'before', 'after', 'above',
                      'below', 'between', 'under', 'again', 'further', 'then', 'once',
                      'and', 'but', 'or', 'nor', 'so', 'yet', 'both', 'either',
                      'neither', 'not', 'only', 'own', 'same', 'than', 'too', 'very',
                      'just', 'also', 'now', 'here', 'there', 'when', 'where', 'why',
                      'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most',
                      'other', 'some', 'such', 'no', 'any', 'this', 'that', 'these',
                      'those', 'add', 'missing', 'section', 'fix', 'consider', 'spec'}
        
        words1 = set(w for w in text1.split() if len(w) > 2 and w not in stop_words)
        words2 = set(w for w in text2.split() if len(w) > 2 and w not in stop_words)
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union) if union else 0.0
    
    def _check_tech_decision_violations(self, spec_content: str, tech_decisions: str) -> List[str]:
        """Check spec for tech decision violations - returns list of violations"""
        import re
        violations = []
        
        # Build deprecated -> correct mappings from tech_decisions.md
        deprecated_mappings = self._parse_tech_decision_mappings(tech_decisions)
        
        spec_lower = spec_content.lower()
        
        for deprecated, correct in deprecated_mappings.items():
            deprecated_lower = deprecated.lower()
            
            # Use word boundary matching to avoid false positives
            # e.g., "provider" shouldn't match "path_provider" or "riverpod"
            pattern = r'\b' + re.escape(deprecated_lower) + r'\b'
            
            # Exclude matches that are part of allowed terms
            allowed_terms = ['riverpod', 'path_provider', 'shared_preferences']
            
            # Find all matches
            matches = re.finditer(pattern, spec_lower)
            has_violation = False
            
            for match in matches:
                # Check if this match is part of an allowed term
                start = max(0, match.start() - 20)
                end = min(len(spec_lower), match.end() + 20)
                context = spec_lower[start:end]
                
                # Skip if it's part of an allowed term
                is_allowed = any(allowed in context for allowed in allowed_terms)
                if not is_allowed:
                    has_violation = True
                    break
            
            if has_violation:
                violations.append(f"Uses '{deprecated}' but project decided on '{correct}'")
        
        return violations
    
    def _parse_tech_decision_mappings(self, tech_decisions: str) -> Dict[str, str]:
        """Parse tech_decisions.md to extract deprecated -> correct mappings"""
        import re
        mappings = {}
        
        # Common patterns in tech_decisions.md:
        # "Use X instead of Y" or "X (not Y)" or "Chose X over Y"
        patterns = [
            r'use\s+([^\s]+)\s+instead\s+of\s+([^\s,\)]+)',  # "use X instead of Y"
            r'([^\s]+)\s+\(not\s+([^\)]+)\)',  # "X (not Y)"
            r'chose\s+([^\s]+)\s+over\s+([^\s,\)]+)',  # "chose X over Y"
            r'([^\s]+)\s+replaces?\s+([^\s,\)]+)',  # "X replaces Y"
            r'migrated?\s+from\s+([^\s]+)\s+to\s+([^\s,\)]+)',  # "migrated from Y to X"
        ]
        
        text_lower = tech_decisions.lower()
        
        for pattern in patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                if len(match) == 2:
                    # For "migrated from Y to X", swap order
                    if 'migrated' in pattern or 'from' in pattern:
                        deprecated, correct = match[0], match[1]
                    else:
                        correct, deprecated = match[0], match[1]
                    
                    # Clean up and add mapping
                    deprecated = deprecated.strip('`"\' ')
                    correct = correct.strip('`"\' ')
                    if deprecated and correct and deprecated != correct:
                        mappings[deprecated] = correct
        
        # Also check for explicit "DEPRECATED:" or "DON'T USE:" sections
        lines = tech_decisions.split('\n')
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if 'deprecated' in line_lower or "don't use" in line_lower or 'do not use' in line_lower:
                # Look for package names in this line or next few lines
                for check_line in lines[i:i+3]:
                    # Find backticked terms
                    backtick_terms = re.findall(r'`([^`]+)`', check_line)
                    for term in backtick_terms:
                        if term not in mappings:
                            # Mark as deprecated without specific replacement
                            mappings[term] = "(see tech_decisions.md for alternative)"
        
        return mappings
    
    def _validate_spec_dependencies_exist(self, spec_content: str, spec_name: str) -> List[str]:
        """Validate that all referenced spec dependencies actually exist"""
        import re
        issues = []
        
        # Find dependency references in spec content
        # Patterns: "spec 001", "spec-001", "depends on 001", "requires 001"
        patterns = [
            r'spec\s*[#]?(\d{3})',
            r'depends?\s+on\s+(\d{3})',
            r'requires?\s+(\d{3})',
            r'after\s+(\d{3})',
            r'blocked\s+by\s+(\d{3})',
        ]
        
        referenced_ids = set()
        for pattern in patterns:
            matches = re.findall(pattern, spec_content.lower())
            referenced_ids.update(matches)
        
        # Check if each referenced spec exists
        for ref_id in referenced_ids:
            spec_exists = False
            for spec_dir in self.context.specs_dir.glob(f"{ref_id}-*"):
                if spec_dir.is_dir():
                    spec_exists = True
                    break
            
            if not spec_exists:
                issues.append(f"References spec {ref_id} which does not exist")
        
        # Also check status.json dependencies if spec directory exists
        current_spec_id = spec_name.split("-")[0] if "-" in spec_name else spec_name
        spec_dir = self._find_spec_dir(current_spec_id)
        
        if spec_dir:
            status_file = spec_dir / "status.json"
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    deps = status.get("dependencies", [])
                    for dep_id in deps:
                        dep_exists = False
                        for d in self.context.specs_dir.glob(f"{dep_id}-*"):
                            if d.is_dir():
                                dep_exists = True
                                break
                        if not dep_exists:
                            issues.append(f"Dependency {dep_id} in status.json does not exist")
                except json.JSONDecodeError:
                    pass
        
        return issues
    
    def _detect_feature_overlap(self, spec_content: str, current_spec_id: str) -> List[dict]:
        """Detect potential feature overlaps with existing specs using semantic matching"""
        overlaps = []
        
        # Extract key features from current spec
        current_features = self._extract_features_from_spec(spec_content)
        
        if not current_features:
            return overlaps
        
        # Check against all other specs
        for spec_dir in sorted(self.context.specs_dir.iterdir()):
            if not spec_dir.is_dir():
                continue
            
            spec_id = spec_dir.name.split("-")[0] if "-" in spec_dir.name else spec_dir.name
            if spec_id == current_spec_id:
                continue
            
            spec_file = spec_dir / "spec.md"
            if not spec_file.exists():
                continue
            
            other_content = spec_file.read_text()
            other_features = self._extract_features_from_spec(other_content)
            
            # Find overlapping features
            for curr_feat in current_features:
                for other_feat in other_features:
                    similarity = self._feature_similarity(curr_feat, other_feat)
                    if similarity > 0.7:  # 70% similarity threshold
                        overlaps.append({
                            "current_feature": curr_feat,
                            "other_spec": spec_dir.name,
                            "other_feature": other_feat,
                            "similarity": similarity
                        })
        
        return overlaps
    
    def _extract_features_from_spec(self, content: str) -> List[str]:
        """Extract feature descriptions from a spec"""
        features = []
        
        # Look for user stories
        in_stories = False
        for line in content.split('\n'):
            line_lower = line.lower().strip()
            
            if 'user stor' in line_lower or '## stories' in line_lower:
                in_stories = True
                continue
            
            if in_stories:
                if line.startswith('##'):
                    in_stories = False
                    continue
                
                # Extract "As a... I want... so that..." patterns
                if 'i want' in line_lower or 'i can' in line_lower:
                    features.append(line.strip())
                elif line.strip().startswith('-') and len(line.strip()) > 10:
                    features.append(line.strip()[1:].strip())
        
        # Also look for requirements section
        in_requirements = False
        for line in content.split('\n'):
            line_lower = line.lower().strip()
            
            if '## requirement' in line_lower or '## functional' in line_lower:
                in_requirements = True
                continue
            
            if in_requirements:
                if line.startswith('##'):
                    in_requirements = False
                    continue
                
                if line.strip().startswith('-') and len(line.strip()) > 10:
                    features.append(line.strip()[1:].strip())
        
        return features[:10]  # Limit to top 10 features
    
    def _feature_similarity(self, feat1: str, feat2: str) -> float:
        """Calculate similarity between two feature descriptions using word overlap"""
        # Simple word-based similarity (Jaccard index)
        words1 = set(w.lower() for w in feat1.split() if len(w) > 3)
        words2 = set(w.lower() for w in feat2.split() if len(w) > 3)
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        # Boost score if key action words match
        action_words = {'save', 'add', 'create', 'delete', 'update', 'view', 'list', 
                       'bookmark', 'favorite', 'sync', 'share', 'export', 'import'}
        action_overlap = (words1 & action_words) & (words2 & action_words)
        
        base_score = len(intersection) / len(union) if union else 0.0
        action_boost = 0.2 if action_overlap else 0.0
        
        return min(1.0, base_score + action_boost)
    
    def _get_user_comments(self, prompt: str = "Add your comments/context") -> str:
        """Get multi-line user comments"""
        Console.log(f"\n💬 {prompt} (Enter to skip, or type and press Enter twice when done):")
        return " ".join(Console.text_block(prompt, line_prompt="   > ", stop_on_blank=True).split("\n")).strip()
    
    def _build_action_item(
        self,
        intent: str,
        item: str,
        ai_suggestion: str = "",
        user_note: str = "",
        category: str = "gap",
        status: str = "pending",
    ) -> dict:
        """Create structured action item metadata"""
        return {
            "id": str(uuid.uuid4()),
            "intent": intent,
            "item": item,
            "category": category,
            "ai_suggestion": ai_suggestion,
            "user_note": user_note,
            "status": status,
            "created": datetime.now().isoformat(),
        }

    def _format_action_item(self, action: dict) -> str:
        """Pretty-print action item for summaries
        
        NOTE: Truncates AI suggestion to 120 chars for DISPLAY only.
        The full suggestion is preserved in the action dict and stored in JSON.
        """
        intent = action.get("intent", "Task")
        item = action.get("item", "")
        status = action.get("status", "pending")
        status_icon = "✅" if status == "done" else "⏳"
        summary = f"{status_icon} {intent}: {item}"
        ai_tip = action.get("ai_suggestion")
        if ai_tip:
            # Truncate for display only - full text is in the action dict
            summary += f"\n         💡 AI: {ai_tip[:120]}{'...' if len(ai_tip) > 120 else ''}"
        note = action.get("user_note")
        if note:
            summary += f"\n         💭 Note: {note}"
        return summary
    
    def _get_ai_suggestion_for_item(self, item: str) -> str:
        """Get AI suggestion for a gap/suggestion item"""
        Console.section("AI Suggestions", "Getting recommendations...")
        ai_suggestion = self.ai.query(Prompts.suggest_fix_for_gap(item))
        
        if ai_suggestion:
            print(f"\n💡 AI Suggestion:\n{ai_suggestion}\n")
        else:
            Console.warning("Could not get AI suggestion")
        
        return ai_suggestion or ""
    
    def _get_ai_suggestion_with_context(self, item: str, user_context: str) -> str:
        """Get AI suggestion for an item with user-provided context"""
        Console.section("AI Suggestions", "Getting recommendations with your context...")
        
        prompt = f"""A feature specification has the following gap/issue:

GAP: {item}

USER'S CONTEXT/CONCERNS:
{user_context}

Provide specific, actionable suggestions to fix this gap, taking into account the user's context.
Include:
1. What needs to be added/changed (addressing user's concerns)
2. Where in the spec it should go
3. Example or template if helpful

Keep it brief but address the user's specific concerns."""

        ai_suggestion = self.ai.query(prompt)
        
        if ai_suggestion:
            print(f"\n💡 AI Suggestion (with your context):\n{ai_suggestion}\n")
        else:
            Console.warning("Could not get AI suggestion")
        
        return ai_suggestion or ""
    
    def _get_ai_suggestion_for_item_with_session(self, item: str, 
                                                  session: ValidationSession = None) -> str:
        """Get AI suggestion with session context (tech stack, related specs)"""
        Console.section("AI Suggestions", "Getting context-aware recommendations...")
        
        # Build context from session
        tech_stack = self._format_tech_stack_for_prompt() if session else "Not specified"
        session_context = session.get_context_for_ai() if session else ""
        related_specs = ""
        
        if session and session.related_specs:
            related_specs = self._format_related_specs_for_prompt(session.related_specs)
        
        prompt = Prompts.suggest_fix_with_full_context(
            gap=item,
            user_context="",  # No user context for simple [y]es
            session_context=session_context,
            tech_stack=tech_stack,
            related_specs=related_specs
        )
        
        ai_suggestion = self.ai.query(prompt)
        
        if ai_suggestion:
            print(f"\n💡 AI Suggestion:\n{ai_suggestion}\n")
        else:
            Console.warning("Could not get AI suggestion")
        
        return ai_suggestion or ""
    
    def _get_ai_suggestion_with_full_context(self, item: str, user_context: str,
                                              session: ValidationSession = None) -> str:
        """Get AI suggestion with user context AND session context"""
        Console.section("AI Suggestions", "Getting recommendations with full context...")
        
        # Build context from session
        tech_stack = self._format_tech_stack_for_prompt() if session else "Not specified"
        session_context = session.get_context_for_ai() if session else ""
        related_specs = ""
        
        if session and session.related_specs:
            related_specs = self._format_related_specs_for_prompt(session.related_specs)
        
        # Check if user mentioned other specs and load them
        if session and user_context:
            mentioned_spec_ids = self._extract_spec_references_from_context(user_context)
            for spec_id in mentioned_spec_ids:
                if spec_id not in session.referenced_specs:
                    spec_content = self._load_spec_content(spec_id)
                    if spec_content:
                        session.add_referenced_spec(spec_id, spec_content)
                        Console.log(f"Loaded referenced spec {spec_id} for context")
            
            # Update related_specs with newly loaded specs
            if session.referenced_specs:
                for spec_id, content in session.referenced_specs.items():
                    related_specs += f"\n\nSpec {spec_id} (user referenced):\n{content[:800]}..."
            
            # Check for terminology mappings in user context
            self._extract_terminology_mappings(user_context, session)
            session_context = session.get_context_for_ai()
        
        prompt = Prompts.suggest_fix_with_full_context(
            gap=item,
            user_context=user_context,
            session_context=session_context,
            tech_stack=tech_stack,
            related_specs=related_specs
        )
        
        ai_suggestion = self.ai.query(prompt)
        
        if ai_suggestion:
            print(f"\n💡 AI Suggestion (with full context):\n{ai_suggestion}\n")
        else:
            Console.warning("Could not get AI suggestion")
        
        return ai_suggestion or ""
    
    def _extract_terminology_mappings(self, user_context: str, session: ValidationSession):
        """Extract terminology mappings from user context (e.g., 'bookmark = spaces')"""
        import re
        
        # Patterns to detect terminology mappings
        patterns = [
            r"(\w+)\s+(?:is|are|=|means?|equals?)\s+(?:the\s+)?(\w+)",  # "bookmark is spaces"
            r"(\w+)\s+(?:is\s+)?(?:same\s+as|equivalent\s+to)\s+(\w+)",  # "bookmark same as spaces"
            r"(\w+)\s*=\s*(\w+)",  # "bookmark = spaces"
        ]
        
        context_lower = user_context.lower()
        
        for pattern in patterns:
            matches = re.findall(pattern, context_lower)
            for match in matches:
                term1, term2 = match
                # Only add if both terms are meaningful (not common words)
                common_words = {"the", "a", "an", "is", "are", "this", "that", "it", "we", "our"}
                if term1 not in common_words and term2 not in common_words:
                    if len(term1) > 2 and len(term2) > 2:
                        session.add_terminology_mapping(term1, term2)
                        Console.log(f"Noted: '{term1}' = '{term2}'")
    
    def _handle_defer_item(self, item: str, spec_file: Path, item_type: str, ai_suggestion: str = "") -> None:
        """Handle deferring a gap or suggestion for later"""
        Console.section("Defer for Later", "How important is this for the product?")
        
        priority_options = [
            "High - Should be next iteration (creates story)",
            "Medium - Future enhancement (adds to backlog)",
            "Low - Nice to have someday (adds to backlog)"
        ]
        priority_choice = Console.choose("Priority level?", priority_options)
        
        # Get user notes/questions
        notes = self._get_user_comments("Add notes, questions, or context for future reference")
        
        # Combine AI suggestion with notes if available
        full_notes = ""
        if ai_suggestion:
            full_notes = f"AI Suggestion: {ai_suggestion[:200]}..."
        if notes:
            full_notes = f"{full_notes}\nUser Notes: {notes}" if full_notes else notes
        
        # Get source spec info
        spec_name = spec_file.parent.name if spec_file else "unknown"
        
        if priority_choice == 0:  # High priority - create story
            self._create_deferred_story(item, item_type, full_notes, spec_name)
        else:
            # Medium or Low - add to backlog
            priority = "medium" if priority_choice == 1 else "low"
            self._add_to_backlog(item, item_type, priority, full_notes, spec_name)
    
    def _create_deferred_story(self, item: str, item_type: str, notes: str, source_spec: str) -> None:
        """Create a story from a high-priority deferred item"""
        Console.section("Create Story", "Setting up story for this item...")
        
        # Generate title suggestion
        title_suggestion = item[:50] + "..." if len(item) > 50 else item
        title_suggestion = title_suggestion.replace("**", "").strip()
        
        Console.log(f"Suggested title: {title_suggestion}")
        custom_title = Console.prompt("Edit title (Enter to accept)")
        title = custom_title if custom_title.strip() else title_suggestion
        
        # Choose story type
        type_options = [
            "enhancement - Feature improvement",
            "tech_debt - Code quality improvement", 
            "spike - Needs research/investigation"
        ]
        type_choice = Console.choose("Story type?", type_options)
        story_type = ["enhancement", "tech_debt", "spike"][type_choice]
        
        # Create the story
        success = self.cmd_story(title, story_type, from_backlog=True, backlog_source={
            "item": item,
            "type": item_type,
            "notes": notes,
            "source_spec": source_spec
        })
        
        if success:
            Console.success(f"Story created from deferred {item_type}")
        else:
            # Fallback to backlog if story creation fails
            Console.warning("Story creation failed, adding to backlog instead")
            self._add_to_backlog(item, item_type, "high", notes, source_spec)
    
    def _add_to_backlog(self, item: str, item_type: str, priority: str, notes: str, source_spec: str) -> None:
        """Add item to the global backlog"""
        backlog_file = self.context.speky_dir / "backlog.md"
        
        # Create or update backlog file
        if backlog_file.exists():
            content = backlog_file.read_text()
        else:
            content = """# SPEKY Backlog

Deferred items from spec validation. Review these when creating new specs.

---

"""
        
        # Add new item
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}[priority]
        
        new_entry = f"""
## {priority_emoji} [{priority.upper()}] {item[:60]}{"..." if len(item) > 60 else ""}

- **Type**: {item_type}
- **Source**: {source_spec}
- **Added**: {timestamp}
- **Full description**: {item}
"""
        if notes:
            new_entry += f"- **Notes**: {notes}\n"
        
        new_entry += "\n---\n"
        
        content += new_entry
        backlog_file.write_text(content)
        
        Console.success(f"Added to backlog ({priority} priority)")
        Console.log(f"   Location: {backlog_file}")
    
    def _get_backlog_count(self) -> dict:
        """Get count of backlog items by priority"""
        counts = {"high": 0, "medium": 0, "low": 0, "total": 0}
        
        # Count JSON backlog items (from drift resolution)
        backlog_json = self.context.speky_dir / "backlog.json"
        if backlog_json.exists():
            json_items = json.loads(backlog_json.read_text())
            pending_items = [item for item in json_items if item.get("status") == "pending"]
            counts["medium"] += len(pending_items)  # All drift items are medium priority
            counts["total"] += len(pending_items)
        
        # Count MD backlog items (from validation)
        backlog_file = self.context.speky_dir / "backlog.md"
        if backlog_file.exists():
            content = backlog_file.read_text()
            high = content.count("[HIGH]")
            medium = content.count("[MEDIUM]")
            low = content.count("[LOW]")
            counts["high"] += high
            counts["medium"] += medium
            counts["low"] += low
            counts["total"] += high + medium + low
        
        return counts
    
    def _check_backlog_before_spec(self) -> bool:
        """Check backlog and offer review before creating new spec"""
        counts = self._get_backlog_count()
        
        if counts["total"] == 0:
            return True  # No backlog, proceed
        
        Console.section("📦 Backlog Check")
        print(f"   You have {counts['total']} deferred item(s):")
        if counts["high"]:
            print(f"      🔴 High priority: {counts['high']}")
        if counts["medium"]:
            print(f"      🟡 Medium priority: {counts['medium']}")
        if counts["low"]:
            print(f"      🟢 Low priority: {counts['low']}")
        print()
        
        options = [
            "Review backlog now",
            "Skip and create spec",
            "Show backlog summary"
        ]
        choice = Console.choose("What would you like to do?", options)
        
        if choice == 0:
            self.cmd_backlog()
            return Console.confirm("\nContinue creating spec?", default=True)
        elif choice == 2:
            self._show_backlog_summary()
            return Console.confirm("\nContinue creating spec?", default=True)
        
        return True
    
    def _show_backlog_summary(self) -> None:
        """Show a summary of backlog items"""
        backlog_file = self.context.speky_dir / "backlog.md"
        
        if not backlog_file.exists():
            Console.log("No backlog items")
            return
        
        content = backlog_file.read_text()
        
        # Parse and show items
        Console.section("Backlog Summary")
        lines = content.split("\n")
        for line in lines:
            if line.startswith("## "):
                print(f"   {line[3:]}")

    def _display_validation_quick(self, results: dict) -> None:
        """Quick non-interactive display of validation results (for scripting)"""
        # Format checks
        Console.section("Format Check", "Required sections")
        for check in results["format_checks"]:
            status = "✅" if check["status"] == "pass" else "❌"
            print(f"   {status} {check['name']}")
        
        # Gaps
        if results["gaps"]:
            Console.section("Gaps Found", "Issues that should be addressed")
            for gap in results["gaps"]:
                print(f"   ⚠️  {gap}")
        else:
            Console.section("Gaps")
            print("   ✅ No significant gaps found")
        
        # Suggestions
        if results["suggestions"]:
            Console.section("Suggestions", "Improvements to consider")
            for suggestion in results["suggestions"]:
                print(f"   💡 {suggestion}")
        
        # Score
        score = results["score"]
        score_emoji = "🟢" if score >= 8 else "🟡" if score >= 5 else "🔴"
        print(f"\n{score_emoji} Score: {score}/10")
        
        if score >= 8:
            Console.success("Spec is ready for adoption")
        elif score >= 5:
            Console.warning("Spec has minor issues - consider fixing before adoption")
        else:
            Console.error("Spec has significant issues - fix before adoption")
    
    def _display_validation_results(self, results: dict, spec_file: Path = None,
                                     session: ValidationSession = None) -> dict:
        """Interactive validation results - walk through issues one by one (context-aware)"""
        action_items: List[dict] = []
        existing_pending_actions: List[dict] = []
        if spec_file:
            existing_pending_actions = self._apply_saved_validation_actions(spec_file)
        
        # Show related specs if found
        if session and session.related_specs:
            Console.section("Related Specs Detected", "Potential overlaps found")
            for spec in session.related_specs[:3]:
                overlap = ", ".join(spec.get("overlap", []))
                print(f"   📋 {spec['name']}: overlaps on [{overlap}]")
            print()
        
        # Step 0a: Tech violations (CRITICAL - show first)
        tech_violations = results.get("tech_violations", [])
        if tech_violations:
            Console.section("🚨 TECH DECISION VIOLATIONS", "Spec uses packages that contradict project decisions")
            for violation in tech_violations:
                print(f"   ❌ {violation}")
            print()
            print("   📋 Reference: .speky/context/tech_decisions.md")
            print()
            if Console.confirm("Add tech violations to fix list?", default=True):
                for violation in tech_violations:
                    action_items.append(
                        self._build_action_item(
                            intent="Fix",
                            item=f"Tech violation: {violation}",
                            category="tech_violation",
                        )
                    )
        
        # Step 0b: Feature overlaps (show before other gaps)
        feature_overlaps = results.get("feature_overlaps", [])
        if feature_overlaps:
            Console.section("⚠️ Feature Overlaps Detected", "Similar features exist in other specs")
            for overlap in feature_overlaps[:5]:
                print(f"   📋 '{overlap['current_feature'][:60]}...'")
                print(f"      Similar to: {overlap['other_spec']}")
                print(f"      Similarity: {overlap['similarity']:.0%}")
                print()
            
            options = [
                "Add to fix list (will review each)",
                "Skip - these are intentionally different",
                "View overlapping specs"
            ]
            choice = Console.choose("How to handle overlaps?", options)
            
            if choice == 0:
                for overlap in feature_overlaps:
                    action_items.append(
                        self._build_action_item(
                            intent="Resolve",
                            item=f"Feature overlap with {overlap['other_spec']}: {overlap['current_feature'][:100]}",
                            category="feature_overlap",
                        )
                    )
            elif choice == 2:
                # Show the overlapping specs
                shown_specs = set()
                for overlap in feature_overlaps:
                    spec_name = overlap['other_spec']
                    if spec_name not in shown_specs:
                        shown_specs.add(spec_name)
                        spec_id = spec_name.split("-")[0]
                        spec_content = self._load_spec_content(spec_id)
                        if spec_content:
                            print(f"\n   === {spec_name} ===")
                            # Show just the user stories section
                            lines = spec_content.split('\n')
                            in_stories = False
                            for line in lines[:100]:
                                if 'user stor' in line.lower():
                                    in_stories = True
                                if in_stories:
                                    print(f"   {line}")
                                    if line.startswith('##') and 'user stor' not in line.lower():
                                        break
                            print()
        
        # Step 0c: Dependency issues
        dep_issues = results.get("dependency_issues", [])
        if dep_issues:
            Console.section("⚠️ Dependency Issues", "Referenced specs have problems")
            for issue in dep_issues:
                print(f"   ⚠️  {issue}")
            print()
        
        # Step 0d: Cross-spec concerns (if any)
        cross_spec_concerns = results.get("cross_spec_concerns", [])
        if cross_spec_concerns:
            Console.section("⚠️ Cross-Spec Concerns", "Potential conflicts with other specs")
            for concern in cross_spec_concerns:
                print(f"   ⚠️  {concern}")
            print()
            if Console.confirm("Add cross-spec concerns to fix list?", default=True):
                for concern in cross_spec_concerns:
                    action_items.append(
                        self._build_action_item(
                            intent="Resolve",
                            item=concern,
                            category="cross_spec",
                        )
                    )
        
        # Step 1: Format checks (quick summary)
        Console.section("Format Check", "Required sections")
        format_issues = []
        for check in results["format_checks"]:
            status = "✅" if check["status"] == "pass" else "❌"
            print(f"   {status} {check['name']}")
            if check["status"] != "pass":
                format_issues.append(check['name'])
        
        if format_issues:
            print(f"\n   ⚠️  Missing: {', '.join(format_issues)}")
            if Console.confirm("Add these to your fix list?", default=True):
                for issue in format_issues:
                    action_items.append(
                        self._build_action_item(
                            intent="Fix",
                            item=f"Add missing section: {issue}",
                            category="format",
                        )
                    )
        
        # Step 2: Walk through gaps one by one
        # Extract gap→fix cache from results (populated during validation)
        gap_fix_cache = results.get("gap_fix_cache", {})
        
        # Load previously resolved items to skip them
        previously_resolved = set()
        if spec_file:
            all_actions = self._load_validation_actions(spec_file)
            for action in all_actions:
                if action.get("status") == "done":
                    # Extract the core issue text for matching
                    item_text = action.get("item", "")
                    previously_resolved.add(item_text.lower().strip())
        
        # Filter out already-resolved gaps
        new_gaps = []
        skipped_gaps = []
        if results["gaps"]:
            for gap in results["gaps"]:
                # Check if this gap matches a previously resolved item
                gap_lower = gap.lower().strip()
                is_resolved = False
                
                for resolved_text in previously_resolved:
                    # Simple substring matching - if gap is mentioned in resolved item or vice versa
                    if (gap_lower in resolved_text or resolved_text in gap_lower) and len(gap_lower) > 20:
                        is_resolved = True
                        skipped_gaps.append(gap)
                        break
                
                if not is_resolved:
                    new_gaps.append(gap)
        
        # Show summary of skipped items
        if skipped_gaps:
            Console.log(f"✓ Skipping {len(skipped_gaps)} previously resolved issue(s)")
        
        if new_gaps:
            Console.section("Gaps Found", "Let's review each issue")
            print(f"   Found {len(new_gaps)} new/unresolved gap(s) to review\n")
            
            # Offer batch operations for efficiency
            if len(new_gaps) >= 3:
                batch_options = [
                    "Process gaps one-by-one (interactive)",
                    "Batch: Add all to fix list",
                    "Batch: Defer all to backlog",
                    "Batch: Auto-fix all with AI suggestions",
                ]
                batch_choice = Console.choose("How to proceed?", batch_options)
                
                if batch_choice == 1:  # Add all to fix list
                    for gap in new_gaps:
                        cached_fix = gap_fix_cache.get(gap, "")
                        action_items.append(
                            self._build_action_item(
                                intent="Fix",
                                item=gap,
                                ai_suggestion=cached_fix,
                                category="gap",
                            )
                        )
                    Console.success(f"Added {len(new_gaps)} gap(s) to fix list")
                    new_gaps = []  # Clear so we don't process individually
                    
                elif batch_choice == 2:  # Defer all to backlog
                    for gap in new_gaps:
                        cached_fix = gap_fix_cache.get(gap, "")
                        self._handle_defer_item(gap, spec_file, "gap", cached_fix)
                    Console.success(f"Deferred {len(new_gaps)} gap(s) to backlog")
                    new_gaps = []  # Clear so we don't process individually
                    
                elif batch_choice == 3:  # Auto-fix all with AI
                    Console.log(f"Attempting to auto-fix {len(new_gaps)} gaps...")
                    batch_fixed = 0
                    batch_failed = []
                    
                    for gap in new_gaps:
                        cached_fix = gap_fix_cache.get(gap, "")
                        if not cached_fix:
                            # Get AI suggestion if not cached
                            cached_fix = self._get_ai_suggestion_for_item_with_session(gap, session)
                        
                        if self._apply_ai_fix_to_spec(spec_file, gap, cached_fix):
                            action_items.append(
                                self._build_action_item(
                                    intent="Fixed",
                                    item=gap,
                                    ai_suggestion=cached_fix,
                                    user_note="Auto-applied (batch)",
                                    category="gap",
                                    status="done",
                                )
                            )
                            batch_fixed += 1
                        else:
                            batch_failed.append(gap)
                    
                    if batch_fixed > 0:
                        Console.success(f"Auto-fixed {batch_fixed}/{len(new_gaps)} gap(s)")
                    if batch_failed:
                        Console.warning(f"{len(batch_failed)} gap(s) failed auto-fix - will process manually")
                        new_gaps = batch_failed  # Only process failed ones individually
                    else:
                        new_gaps = []  # All succeeded, clear the list
                # batch_choice == 0 falls through to process one-by-one
            
            for i, gap in enumerate(new_gaps, 1):
                print(f"   ─────────────────────────────────────")
                print(f"   Gap {i}/{len(new_gaps)}")
                print(f"   ⚠️  {gap}")
                print()
                
                # Step 1: Optionally show AI suggestion
                # NEW: Check cache first to avoid redundant AI calls
                ai_suggestion = ""
                cached_fix = gap_fix_cache.get(gap, "")
                
                if cached_fix:
                    # We have a cached fix from initial validation
                    ai_choice = Console.prompt("   Want AI fix suggestion? [y]es / [n]o / [c]ontext", default="n").strip().lower()
                    
                    if ai_choice in ['y', 'yes']:
                        # Use cached fix (no AI call needed!)
                        ai_suggestion = cached_fix
                        print(f"\n💡 AI Fix Suggestion:\n{ai_suggestion}\n")
                    elif ai_choice in ['c', 'context']:
                        # User wants elaboration with their context - make AI call
                        user_context = self._get_user_comments("Provide your context/concerns for AI")
                        ai_suggestion = self._get_ai_suggestion_with_full_context(gap, user_context, session)
                else:
                    # No cache available (older format or parsing failed) - fallback to AI call
                    ai_choice = Console.prompt("   Want AI suggestions? [y]es / [n]o / [c]ontext", default="n").strip().lower()
                    
                    if ai_choice in ['y', 'yes']:
                        ai_suggestion = self._get_ai_suggestion_for_item_with_session(gap, session)
                    elif ai_choice in ['c', 'context']:
                        user_context = self._get_user_comments("Provide your context/concerns for AI")
                        ai_suggestion = self._get_ai_suggestion_with_full_context(gap, user_context, session)
                
                # Step 2: Choose action
                options = [
                    "Add to fix list",
                    "Skip",
                    "Fix now",
                    "Defer for later"
                ]
                choice = Console.choose("How to handle this?", options)
                
                if choice == 0:  # Add to fix list
                    item = self._build_action_item(
                        intent="Fix",
                        item=gap,
                        ai_suggestion=ai_suggestion,
                        user_note=self._get_user_comments("Add your comments"),
                        category="gap",
                    )
                    action_items.append(item)
                    Console.log("Added to fix list ✓")
                
                elif choice == 2:  # Fix now
                    fix_mode = Console.prompt("   Fix now: [a]uto / [m]anual", default="m").strip().lower()
                    if fix_mode in ["a", "auto"]:
                        if self._apply_ai_fix_to_spec(spec_file, gap, ai_suggestion):
                            item = self._build_action_item(
                                intent="Fixed",
                                item=gap,
                                ai_suggestion=ai_suggestion,
                                user_note="Applied automatically",
                                category="gap",
                                status="done",
                            )
                            action_items.append(item)
                            Console.log("✅ Applied automatically")
                        else:
                            Console.warning("Auto-fix failed, please fix manually")
                            self._run_manual_fix(spec_file)
                            comment = self._get_user_comments("Describe what you fixed")
                            item = self._build_action_item(
                                intent="Fixed",
                                item=gap,
                                ai_suggestion=ai_suggestion,
                                user_note=comment or "Fixed manually",
                                category="gap",
                                status="done",
                            )
                            action_items.append(item)
                    else:
                        self._run_manual_fix(spec_file)
                        comment = self._get_user_comments("Describe what you fixed")
                        item = self._build_action_item(
                            intent="Fixed",
                            item=gap,
                            ai_suggestion=ai_suggestion,
                            user_note=comment or "Fixed manually",
                            category="gap",
                            status="done",
                        )
                        action_items.append(item)
                    Console.log("Continuing validation...")
                
                elif choice == 3:  # Defer for later
                    self._handle_defer_item(gap, spec_file, "gap", ai_suggestion)
                # choice == 1 means skip
                
                print()
        else:
            Console.section("Gaps")
            print("   ✅ No significant gaps found")
        
        # OPTIMIZATION: Filter suggestions to exclude items similar to what was just fixed
        # Replaces expensive AI re-call with semantic filtering
        fixed_items = [a for a in action_items if a.get("status") == "done"]
        if fixed_items:
            Console.log("\n   Filtering suggestions to exclude fixed items...")
            original_suggestions = results.get("suggestions", [])
            filtered_suggestions = self._filter_suggestions_by_fixed_items(
                original_suggestions, 
                fixed_items
            )
            results["suggestions"] = filtered_suggestions
            if len(filtered_suggestions) < len(original_suggestions):
                removed_count = len(original_suggestions) - len(filtered_suggestions)
                Console.log(f"   Removed {removed_count} suggestion(s) similar to fixed items ✓")
        
        # Step 3: Walk through suggestions one by one
        if results["suggestions"]:
            Console.section("Suggestions", "Optional improvements to consider")
            print(f"   Found {len(results['suggestions'])} suggestion(s)\n")
            
            review_suggestions = Console.confirm("Review suggestions one by one?", default=True)
            
            if review_suggestions:
                for i, suggestion in enumerate(results["suggestions"], 1):
                    print(f"   ─────────────────────────────────────")
                    print(f"   Suggestion {i}/{len(results['suggestions'])}")
                    print(f"   💡 {suggestion}")
                    print()
                    
                    # Step 1: Optionally get AI suggestion FIRST
                    ai_suggestion = ""
                    ai_choice = Console.prompt("   Want AI suggestions? [y]es / [n]o / [c]ontext", default="n").strip().lower()
                    
                    if ai_choice in ['y', 'yes']:
                        ai_suggestion = self._get_ai_suggestion_for_item_with_session(suggestion, session)
                    elif ai_choice in ['c', 'context']:
                        user_context = self._get_user_comments("Provide your context/concerns for AI")
                        ai_suggestion = self._get_ai_suggestion_with_full_context(suggestion, user_context, session)
                    
                    # Step 2: Choose action
                    options = [
                        "Add to improvement list",
                        "Skip",
                        "Defer for later"
                    ]
                    choice = Console.choose("Include this?", options)
                    
                    if choice == 0:  # Add to list
                        item = self._build_action_item(
                            intent="Consider",
                            item=suggestion,
                            ai_suggestion=ai_suggestion,
                            user_note=self._get_user_comments("Add your comments"),
                            category="suggestion",
                        )
                        action_items.append(item)
                        Console.log("Added to list ✓")
                    
                    elif choice == 2:  # Defer for later
                        self._handle_defer_item(suggestion, spec_file, "suggestion", ai_suggestion)
                    
                    print()
            else:
                Console.log("Skipping detailed suggestion review")
        
        # Step 4: Summary
        Console.section("Validation Summary")
        
        # Recalculate score based on what was actually fixed during this session
        score = results["score"]
        fixed_count = sum(1 for item in action_items if item.get("status") == "done")
        skipped_count = sum(1 for item in action_items if item.get("status") == "skipped")
        
        # Add back points for fixed items (they were deducted during initial analysis)
        score = min(10, score + fixed_count)
        
        # Update the results with the recalculated score
        results["score"] = score
        
        score_emoji = "🟢" if score >= 8 else "🟡" if score >= 5 else "🔴"
        print(f"   {score_emoji} Quality Score: {score}/10")
        
        if fixed_count > 0:
            print(f"   ✅ Fixed {fixed_count} issue(s) during this session")
        
        if action_items:
            print(f"\n   📋 Action Items ({len(action_items)}):")
            for item in action_items:
                print(f"      • {self._format_action_item(item)}")
            
            # Bug Fix: Save ALL actions (done + pending) for complete history
            # Previously only saved pending, losing track of what was fixed
            done_actions = [a for a in action_items if a.get("status") == "done"]
            pending_actions = [a for a in action_items if a.get("status") != "done"]
            # Combine: existing pending + new done + new pending
            all_actions = existing_pending_actions + done_actions + pending_actions
            combined_pending = existing_pending_actions + pending_actions  # For UI display
            if spec_file:
                # Save ALL actions (done + pending) for complete tracking
                self._save_validation_actions(spec_file, all_actions)
                
                # Offer to apply remaining fixes now
                if combined_pending and Console.confirm("\nApply remaining fixes now?", default=False):
                    combined_pending, applied_now = self._process_validation_actions(
                        spec_file,
                        combined_pending,
                        heading="Apply Pending Fixes",
                        session=session,
                    )
                    if applied_now:
                        Console.success(f"Applied {len(applied_now)} pending fix(es)")
                        # Re-save with updated statuses (include all: done + remaining pending)
                        all_actions_updated = done_actions + applied_now + combined_pending
                        self._save_validation_actions(spec_file, all_actions_updated)
                
                if Console.confirm("\nSave action items to a file?", default=False):
                    self._write_validation_notes(spec_file, action_items, combined_pending)
        else:
            if spec_file:
                self._save_validation_actions(spec_file, existing_pending_actions)
            print("\n   ✅ No action items - spec looks good!")
        
        # Save validation session for continuity across runs
        # Preserves terminology mappings, decisions, and referenced specs
        if spec_file and session:
            self._save_validation_session(spec_file, session)
        
        # Final recommendation
        print()
        if score >= 8:
            Console.success("Spec is ready for adoption")
            Console.log("Next: speky adopt <id>")
        elif score >= 5:
            Console.warning("Spec has minor issues - consider fixing before adoption")
            Console.log("You can still adopt with: speky adopt <id>")
        else:
            Console.error("Spec has significant issues - fix before adoption")
            Console.log("Fix the issues above, then run validate-spec again")
        
        results["action_items"] = action_items
        return results

    # ------------------------------------------------------------------
    # Validation action & session persistence utilities
    # ------------------------------------------------------------------
    def _validation_actions_path(self, spec_file: Path) -> Path:
        return spec_file.parent / "validation_actions.json"
    
    def _validation_session_path(self, spec_file: Path) -> Path:
        """Path to persisted ValidationSession for this spec"""
        return spec_file.parent / "validation_session.json"

    def _load_validation_actions(self, spec_file: Path) -> List[dict]:
        path = self._validation_actions_path(spec_file)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except Exception:
            Console.warning("Failed to read validation actions, resetting file")
            path.unlink(missing_ok=True)
            return []

    def _save_validation_actions(self, spec_file: Path, actions: List[dict]) -> None:
        path = self._validation_actions_path(spec_file)
        if actions:
            path.write_text(json.dumps(actions, indent=2))
        else:
            path.unlink(missing_ok=True)
    
    def _save_validation_session(self, spec_file: Path, session: ValidationSession) -> None:
        """Persist ValidationSession to disk for continuity across runs
        
        Saves user decisions, terminology mappings, and referenced specs so
        the next validation session can continue where this one left off.
        """
        path = self._validation_session_path(spec_file)
        session_data = session.to_dict()
        path.write_text(json.dumps(session_data, indent=2))
    
    def _load_validation_session(self, spec_file: Path) -> Optional[ValidationSession]:
        """Load persisted ValidationSession if it exists
        
        Returns None if no session exists or if loading fails.
        """
        path = self._validation_session_path(spec_file)
        if not path.exists():
            return None
        
        try:
            session_data = json.loads(path.read_text())
            session = ValidationSession.from_dict(session_data)
            return session
        except Exception as e:
            Console.warning(f"Failed to load validation session: {e}")
            return None

    def _apply_saved_validation_actions(self, spec_file: Path) -> List[dict]:
        saved = self._load_validation_actions(spec_file)
        
        # Fallback: if no validation_actions.json but validation_notes.md exists, convert it
        if not saved:
            notes_file = spec_file.parent / "validation_notes.md"
            if notes_file.exists():
                saved = self._convert_validation_notes_to_actions(notes_file)
                if saved:
                    self._save_validation_actions(spec_file, saved)
        
        if not saved:
            return []
        
        # Filter for pending items only - skip already completed ones
        pending_items = [a for a in saved if a.get("status") != "done"]
        completed_items = [a for a in saved if a.get("status") == "done"]
        
        if not pending_items:
            # All items are done - no pending fixes to show
            if completed_items:
                Console.log(f"Previous validation: {len(completed_items)} fix(es) already applied ✓")
            return []
        
        # Load session for context-aware processing
        session = self._load_validation_session(spec_file)
        
        remaining, applied = self._process_validation_actions(
            spec_file,
            pending_items,
            heading="Pending Validation Fixes",
            show_heading=True,
            session=session,
        )
        if applied:
            Console.success(f"Applied {len(applied)} pending fix(es)")
        
        # Save all items (completed + remaining pending)
        all_items = completed_items + remaining + applied
        self._save_validation_actions(spec_file, all_items)
        return remaining

    def _convert_validation_notes_to_actions(self, notes_file: Path) -> List[dict]:
        """Convert legacy validation_notes.md to structured action items"""
        if not notes_file.exists():
            return []
        
        content = notes_file.read_text()
        actions = []
        current_action = None
        
        for line in content.split("\n"):
            # Look for checkbox lines: - [ ] or - [x]
            if line.strip().startswith("- ["):
                # Extract checkbox state and text
                if current_action:
                    actions.append(current_action)
                
                is_done = "[x]" in line
                text = line.split("]", 1)[1].strip() if "]" in line else ""
                
                # Parse intent and item from text (e.g., "Fix: Missing error handling")
                if ":" in text:
                    intent, item = text.split(":", 1)
                    intent = intent.strip()
                    item = item.strip()
                else:
                    intent = "Task"
                    item = text
                
                current_action = {
                    "id": str(uuid.uuid4()),
                    "intent": intent,
                    "item": item,
                    "category": "gap" if "Fix" in intent else "suggestion",
                    "ai_suggestion": "",
                    "user_note": "",
                    "status": "done" if is_done else "pending",
                    "created": datetime.now().isoformat(),
                }
            
            # Look for AI suggestion lines (handle various formats)
            elif current_action and "💡" in line and ("AI suggestion:" in line or "AI:" in line):
                if "AI suggestion:" in line:
                    ai_text = line.split("AI suggestion:", 1)[1].strip()
                elif "AI:" in line:
                    ai_text = line.split("AI:", 1)[1].strip()
                else:
                    ai_text = ""
                current_action["ai_suggestion"] = ai_text
            
            # Look for user note lines (handle various formats)
            elif current_action and "💭" in line and ("Note:" in line or "User note:" in line):
                if "User note:" in line:
                    note_text = line.split("User note:", 1)[1].strip()
                elif "Note:" in line:
                    note_text = line.split("Note:", 1)[1].strip()
                else:
                    note_text = ""
                current_action["user_note"] = note_text
        
        if current_action:
            actions.append(current_action)
        
        return actions

    def _get_pending_validation_status(self, spec_dir: Path) -> dict:
        """Get pending validation action status for a spec directory
        
        Returns dict with:
            - has_pending: bool - whether there are pending validation actions
            - pending_count: int - number of pending actions
            - pending_actions: List[dict] - the pending actions themselves
            - done_count: int - number of completed actions
        """
        spec_file = spec_dir / "spec.md"
        if not spec_file.exists():
            return {"has_pending": False, "pending_count": 0, "pending_actions": [], "done_count": 0}
        
        actions = self._load_validation_actions(spec_file)
        if not actions:
            return {"has_pending": False, "pending_count": 0, "pending_actions": [], "done_count": 0}
        
        pending = [a for a in actions if a.get("status") != "done"]
        done = [a for a in actions if a.get("status") == "done"]
        
        return {
            "has_pending": len(pending) > 0,
            "pending_count": len(pending),
            "pending_actions": pending,
            "done_count": len(done)
        }
    
    def _warn_pending_validation_actions(self, spec_dir: Path, command_name: str) -> bool:
        """Check for pending validation actions and warn user
        
        Returns True if user wants to proceed, False to abort
        """
        status = self._get_pending_validation_status(spec_dir)
        
        if not status["has_pending"]:
            return True  # No pending actions, proceed
        
        spec_id = spec_dir.name.split("-")[0] if "-" in spec_dir.name else spec_dir.name
        
        Console.warning(f"⚠️  {status['pending_count']} validation fix(es) pending for this spec")
        
        # Show first 3 pending items
        for action in status["pending_actions"][:3]:
            intent = action.get("intent", "Fix")
            item = action.get("item", "")[:60]
            print(f"   • [{intent}] {item}...")
        
        if status["pending_count"] > 3:
            print(f"   ... and {status['pending_count'] - 3} more")
        
        print()
        options = [
            f"Proceed with {command_name} anyway",
            "Run validate-spec first to review/fix issues",
            "Cancel"
        ]
        choice = Console.choose("How to proceed?", options)
        
        if choice == 0:  # Proceed anyway
            return True
        elif choice == 1:  # Run validate-spec
            Console.log(f"Run: speky validate-spec {spec_id}")
            return False
        else:  # Cancel
            return False

    def _process_validation_actions(
        self,
        spec_file: Path,
        actions: List[dict],
        heading: str,
        show_heading: bool = False,
        session: ValidationSession = None,
    ) -> (List[dict], List[dict]):
        """Process pending validation actions with optional session context
        
        If session is provided, AI suggestions will be context-aware using
        terminology mappings and previous decisions.
        """
        if not actions:
            return [], []
        remaining = []
        applied = []
        if show_heading:
            Console.section(heading)
        for idx, action in enumerate(actions, 1):
            print(f"   Item {idx}/{len(actions)}")
            print(f"      {self._format_action_item(action)}\n")
            choice = Console.prompt("      Apply now? [a]uto / [m]anual / [s]kip", default="s").strip().lower()
            if choice in ["a", "auto"]:
                ai_suggestion = action.get("ai_suggestion", "")
                
                # If no AI suggestion exists, offer to get one
                # NOTE: Full suggestions are stored, not truncated, so simple empty check is sufficient
                if not ai_suggestion:
                    Console.log("   No AI suggestion available for this item.")
                    if Console.confirm("   Get AI suggestion now?", default=True):
                        # Use session-aware AI suggestion if available
                        if session:
                            ai_suggestion = self._get_ai_suggestion_for_item_with_session(
                                action.get("item", ""), session
                            )
                        else:
                            ai_suggestion = self._get_ai_suggestion_for_item(action.get("item", ""))
                        action["ai_suggestion"] = ai_suggestion
                
                if self._apply_ai_fix_to_spec(spec_file, action.get("item", ""), ai_suggestion):
                    action["status"] = "done"
                    action["user_note"] = (action.get("user_note") or "") + " (auto-applied)"
                    applied.append(action)
                    Console.success("   ✅ Applied to spec!")
                else:
                    Console.warning("   Auto-apply failed, leaving pending")
                    remaining.append(action)
            elif choice in ["m", "manual"]:
                self._run_manual_fix(spec_file)
                note = self._get_user_comments("Describe what you updated")
                
                # Offer to re-check if fix resolved the issue
                if Console.confirm("   Re-check if this issue is resolved?", default=True):
                    spec_content = spec_file.read_text()
                    check_prompt = f"""Check if this issue has been resolved in the spec:

Issue: {action.get('item', '')}

Spec content (first 3000 chars):
{spec_content[:3000]}

Respond with just:
- "RESOLVED" if the issue is fixed
- "NOT_RESOLVED: [brief reason]" if still present
"""
                    check_result = self.ai.query(check_prompt)
                    if check_result and "RESOLVED" in check_result and "NOT_RESOLVED" not in check_result:
                        Console.success("   ✅ AI confirms: Issue resolved!")
                        action["status"] = "done"
                        action["user_note"] = (note or "Fixed manually") + " (verified)"
                        applied.append(action)
                    else:
                        reason = check_result.replace("NOT_RESOLVED:", "").strip() if check_result else "Unknown"
                        Console.warning(f"   ⚠️  AI check: Still needs work - {reason}")
                        if Console.confirm("   Mark as done anyway?", default=False):
                            action["status"] = "done"
                            action["user_note"] = (note or "Fixed manually") + " (unverified)"
                            applied.append(action)
                        else:
                            Console.log("   Keeping as pending for next review")
                            action["user_note"] = (note or "") + f" (attempted, needs more work: {reason})"
                            remaining.append(action)
                else:
                    action["status"] = "done"
                    action["user_note"] = note or "Fixed manually"
                    applied.append(action)
            else:
                Console.log("   Skipped for now")
                remaining.append(action)
        return remaining, applied

    def _write_validation_notes(self, spec_file: Path, latest_actions: List[dict], pending_actions: List[dict]):
        notes_file = spec_file.parent / "validation_notes.md"
        lines = ["# Validation Notes", "", f"Generated: {datetime.now().isoformat()}", "", "## Action Items", ""]
        def _line_for(action: dict) -> str:
            checkbox = "x" if action.get("status") == "done" else " "
            return f"- [{checkbox}] {action.get('intent', 'Task')}: {action.get('item', '')}"

        for action in latest_actions:
            lines.append(_line_for(action))
            ai_tip = action.get("ai_suggestion")
            if ai_tip:
                lines.append(f"  - 💡 AI: {ai_tip}")
            note = action.get("user_note")
            if note:
                lines.append(f"  - 💭 Note: {note}")
            lines.append("")

        if pending_actions:
            lines.append("## Pending from previous sessions")
            lines.append("")
            for action in pending_actions:
                lines.append(_line_for(action))
            lines.append("")

        notes_file.write_text("\n".join(lines))
        Console.success(f"Saved to {notes_file}")

    def _apply_ai_fix_to_spec(self, spec_file: Path, item_description: str, ai_suggestion: str) -> bool:
        if not spec_file or not spec_file.exists():
            Console.error("Spec file not found for auto-fix")
            return False
        if not ai_suggestion:
            Console.warning("AI suggestion required for auto-fix")
            return False

        spec_content = spec_file.read_text()
        original_line_count = len(spec_content.splitlines())
        
        # Warn if spec is getting very large
        if original_line_count > 1500:
            Console.warning(f"⚠️  Large spec file ({original_line_count} lines)")
            Console.log("Consider manual editing for very large specs to avoid truncation risks.")
            if not Console.confirm("Continue with auto-fix anyway?", default=False):
                return False
        
        # Use higher token limit for spec edits to prevent truncation
        max_tokens_for_edit = self.config.get("max_tokens_spec_edit", 32768)
        
        updated_content = self.ai.query(
            Prompts.apply_validation_fix(
                spec_content=spec_content,
                spec_name=spec_file.parent.name,
                issue_description=item_description,
                ai_suggestion=ai_suggestion,
            ),
            max_tokens=max_tokens_for_edit
        )

        if not updated_content:
            Console.warning("AI did not return updated content")
            return False
        
        # Validate that content wasn't severely truncated
        updated_line_count = len(updated_content.splitlines())
        if updated_line_count < original_line_count * 0.7:  # Lost more than 30% of content
            Console.error(f"⚠️  AI response appears truncated ({updated_line_count} lines vs original {original_line_count})")
            Console.warning("This may indicate token limit issues. Skipping this auto-fix.")
            Console.log("Consider fixing this item manually or in smaller increments.")
            return False

        diff = difflib.unified_diff(
            spec_content.splitlines(),
            updated_content.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm=""
        )
        diff_lines = list(diff)
        preview = "\n".join(diff_lines[:50])  # Show more diff context
        if preview:
            Console.section("Proposed Changes")
            print(preview)
            if len(diff_lines) > 50:
                print(f"\n   (diff truncated, {len(diff_lines)} total lines)")
            # Show line count change
            line_diff = updated_line_count - original_line_count
            if line_diff > 0:
                print(f"   📈 Lines: {original_line_count} → {updated_line_count} (+{line_diff})")
            elif line_diff < 0:
                print(f"   📉 Lines: {original_line_count} → {updated_line_count} ({line_diff})")

        if not Console.confirm("Apply this AI-generated change?", default=True):
            return False

        spec_file.write_text(updated_content)
        return True

    def _run_manual_fix(self, spec_file: Path):
        Console.log(f"\n📝 Spec file: {spec_file}")
        Console.log("Make your changes, save the file, then press Enter to continue...\n")
        Console.pause("")


    # -------------------------------------------------------------------------
    # Command: adopt
    # -------------------------------------------------------------------------
    def cmd_adopt(self, item_id: str, item_type: str = None, skip_validation: bool = False) -> bool:
        """Adopt an IDE-created spec or story into SPEKY tracking"""
        if not self._require_init():
            return False
        
        # Auto-detect item type from ID prefix if not specified
        if not item_type:
            # Story IDs start with letter prefix (F001, B001, T001, E001, S001)
            if item_id and len(item_id) >= 1 and item_id[0].isalpha() and len(item_id) >= 4:
                item_type = "story"
            else:
                item_type = "spec"
        
        if item_type == "story":
            return self._adopt_story(item_id, skip_validation)
        else:
            return self._adopt_spec(item_id, skip_validation)
    
    def _adopt_spec(self, spec_id: str, skip_validation: bool = False) -> bool:
        """Adopt an IDE-created spec into SPEKY tracking"""
        Console.header(f"📥 Adopt Spec: {spec_id}")
        
        # Find spec directory
        spec_dir = self._find_spec_dir_by_pattern(spec_id)
        if not spec_dir:
            Console.error(f"Spec directory not found matching: {spec_id}")
            Console.log("Expected location: .speky/specs/{id}-{name}/spec.md")
            Console.log("Make sure the spec was created by IDE in the correct location")
            return False
        
        spec_file = spec_dir / "spec.md"
        if not spec_file.exists():
            Console.error(f"spec.md not found in {spec_dir}")
            return False
        
        Console.log(f"Found: {spec_dir.name}")
        
        # Basic validation (format check)
        if not skip_validation:
            Console.section("Quick Validation")
            spec_content = spec_file.read_text()
            
            # Check for minimum required sections
            required = ["## Overview", "## MVP Scope", "## Requirements"]
            missing = [s for s in required if s.lower() not in spec_content.lower()]
            
            if missing:
                Console.warning(f"Missing sections: {', '.join(missing)}")
                if not Console.confirm("Adopt anyway?", default=False):
                    Console.log("Run 'speky validate-spec' for detailed analysis")
                    return False
            else:
                Console.success("Basic format check passed")
            
            # Check for pending validation actions
            if not self._warn_pending_validation_actions(spec_dir, "adopt"):
                return False
        
        # Check if already adopted
        data = self.context.data
        existing = [s for s in data.get("specs", []) if s["id"] == spec_id]
        if existing:
            Console.warning(f"Spec {spec_id} is already in SPEKY tracking")
            if not Console.confirm("Update tracking info?"):
                return False
            # Remove old entry
            data["specs"] = [s for s in data["specs"] if s["id"] != spec_id]
        
        # Create/update status.json if missing
        status_file = spec_dir / "status.json"
        if not status_file.exists():
            # Extract name from directory
            dir_name = spec_dir.name
            name_part = dir_name.split("-", 1)[1] if "-" in dir_name else dir_name
            feature_name = name_part.replace("-", " ").title()
            
            status = {
                "id": spec_id,
                "name": feature_name,
                "status": ItemStatus.DRAFT.value,
                "created": datetime.now().isoformat(),
                "adopted_from_ide": True,
            }
            status_file.write_text(json.dumps(status, indent=2))
            Console.log("Created status.json")
        else:
            # Update existing status
            status = json.loads(status_file.read_text())
            status["adopted_from_ide"] = True
            status_file.write_text(json.dumps(status, indent=2))
        
        # Add to context tracking
        status = json.loads(status_file.read_text())
        data["specs"].append({
            "id": spec_id,
            "name": status.get("name", spec_dir.name),
            "dir": spec_dir.name
        })
        self.context.save(data)
        
        Console.success(f"Spec adopted: {spec_dir.name}")
        
        print(f"\n📋 Next steps:")
        print(f"   • Review spec: {spec_dir}/spec.md")
        print(f"   • Validate (optional): speky validate-spec {spec_id}")
        print(f"   • Generate plan: speky plan {spec_id}")
        
        return True
    
    def _adopt_story(self, story_id: str, skip_validation: bool = False) -> bool:
        """Adopt an IDE-created story into SPEKY tracking"""
        Console.header(f"📥 Adopt Story: {story_id}")
        
        # Find story directory
        story_dir = self._find_story_dir_by_pattern(story_id)
        if not story_dir:
            Console.error(f"Story directory not found matching: {story_id}")
            Console.log("Expected location: .speky/stories/{id}-{name}/story.md")
            Console.log("Make sure the story was created in the correct location")
            Console.log("\nExpected folder naming convention:")
            Console.log("  F001-feature-name/  (Feature)")
            Console.log("  B001-bug-name/      (Bug)")
            Console.log("  T001-tech-debt/     (Tech Debt)")
            Console.log("  E001-enhancement/   (Enhancement)")
            Console.log("  S001-spike-name/    (Spike)")
            return False
        
        story_file = story_dir / "story.md"
        if not story_file.exists():
            Console.error(f"story.md not found in {story_dir}")
            Console.log("Create a story.md file with at least:")
            Console.log("  # Story Title")
            Console.log("  ## Description")
            Console.log("  ## Acceptance Criteria")
            return False
        
        Console.log(f"Found: {story_dir.name}")
        
        # Basic validation (structure check - no AI)
        if not skip_validation:
            Console.section("Structure Validation")
            validation_passed = True
            
            # Check folder naming convention
            dir_name = str(story_dir.name)
            valid_prefixes = ["F", "B", "T", "E", "S"]
            if not any(dir_name.startswith(p) for p in valid_prefixes):
                Console.warning(f"Folder name should start with F/B/T/E/S prefix: {dir_name}")
                validation_passed = False
            
            # Check story.md basic structure
            story_content = story_file.read_text()
            
            # Check for minimum required sections
            required_sections = ["description", "acceptance criteria"]
            content_lower = story_content.lower()
            missing = []
            for section in required_sections:
                # Check for section header or inline mention
                if section not in content_lower and f"## {section}" not in content_lower:
                    missing.append(section.title())
            
            if missing:
                Console.warning(f"Missing sections in story.md: {', '.join(missing)}")
                validation_passed = False
            
            # Check for status.json (required for adoption)
            status_file = story_dir / "status.json"
            if not status_file.exists():
                Console.log("status.json not found - will be created")
            
            if not validation_passed:
                if not Console.confirm("Adopt anyway?", default=False):
                    Console.log("Run 'speky validate-story' for detailed AI analysis")
                    return False
            else:
                Console.success("Basic structure check passed")
        
        # Check if already adopted
        data = self.context.data
        existing = [s for s in data.get("stories", []) if s["id"] == story_id]
        if existing:
            Console.warning(f"Story {story_id} is already in SPEKY tracking")
            if not Console.confirm("Update tracking info?"):
                return False
            # Remove old entry
            data["stories"] = [s for s in data["stories"] if s["id"] != story_id]
        
        # Create/update status.json
        status_file = story_dir / "status.json"
        dir_name = str(story_dir.name)
        
        # Determine story type from prefix
        prefix_to_type = {
            "F": "feature",
            "B": "bug",
            "T": "tech_debt",
            "E": "enhancement",
            "S": "spike"
        }
        story_type = prefix_to_type.get(dir_name[0].upper(), "feature")
        
        # Extract title from directory name
        name_part = dir_name.split("-", 1)[1] if "-" in dir_name else dir_name
        story_title = name_part.replace("-", " ").title()
        
        # Parse dependencies from story.md if mentioned
        story_content = story_file.read_text()
        dependencies = self._extract_story_dependencies(story_content)
        
        # Parse related specs from story.md if mentioned
        related_specs = self._extract_related_specs_from_story(story_content)
        
        if not status_file.exists():
            status = {
                "id": story_id,
                "title": story_title,
                "type": story_type,
                "status": ItemStatus.DRAFT.value,
                "created": datetime.now().isoformat(),
                "adopted_from_ide": True,
                "related_specs": related_specs,
                "dependencies": dependencies,
            }
            status_file.write_text(json.dumps(status, indent=2))
            Console.log("Created status.json")
        else:
            # Update existing status
            status = json.loads(status_file.read_text())
            status["adopted_from_ide"] = True
            if dependencies and not status.get("dependencies"):
                status["dependencies"] = dependencies
            if related_specs and not status.get("related_specs"):
                status["related_specs"] = related_specs
            status_file.write_text(json.dumps(status, indent=2))
            Console.log("Updated status.json")
        
        # Add to context tracking
        status = json.loads(status_file.read_text())
        data["stories"].append({
            "id": story_id,
            "title": status.get("title", story_title),
            "type": status.get("type", story_type),
            "dir": str(story_dir.name)
        })
        self.context.save(data)
        
        Console.success(f"Story adopted: {story_dir.name}")
        
        # Show extracted info
        if related_specs:
            print(f"\n🔗 Linked to spec(s): {', '.join(related_specs)}")
        if dependencies:
            print(f"📦 Dependencies: {', '.join(dependencies)}")
        
        print(f"\n📋 Next steps:")
        print(f"   • Review story: {story_dir}/story.md")
        print(f"   • Validate (optional): speky validate-story {story_id}")
        print(f"   • Generate plan (optional): speky plan {story_id}")
        print(f"   • Implement: speky implement {story_id}")
        
        return True
    
    def _extract_story_dependencies(self, story_content: str) -> List[str]:
        """Extract dependencies mentioned in story content"""
        dependencies = []
        
        # Look for dependency patterns
        patterns = [
            r'depends on[:\s]+([A-Z]\d{3})',
            r'dependency[:\s]+([A-Z]\d{3})',
            r'requires[:\s]+([A-Z]\d{3})',
            r'after[:\s]+([A-Z]\d{3})',
            r'blocked by[:\s]+([A-Z]\d{3})',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, story_content, re.IGNORECASE)
            dependencies.extend(matches)
        
        # Also check for spec dependencies (numeric IDs)
        spec_patterns = [
            r'depends on spec[:\s]+(\d{3})',
            r'requires spec[:\s]+(\d{3})',
        ]
        
        for pattern in spec_patterns:
            matches = re.findall(pattern, story_content, re.IGNORECASE)
            dependencies.extend(matches)
        
        return list(set(dependencies))
    
    def _extract_related_specs_from_story(self, story_content: str) -> List[str]:
        """Extract related spec IDs mentioned in story content"""
        specs = []
        
        # Look for spec reference patterns
        patterns = [
            r'spec[:\s]+(\d{3})',
            r'specification[:\s]+(\d{3})',
            r'related spec[:\s]+(\d{3})',
            r'see spec[:\s]+(\d{3})',
            r'from spec[:\s]+(\d{3})',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, story_content, re.IGNORECASE)
            specs.extend(matches)
        
        return list(set(specs))
    
    def _find_spec_dir_by_pattern(self, spec_id: str) -> Optional[Path]:
        """Find spec directory by ID pattern (handles IDE-created specs)"""
        # First try exact match
        spec_dir = self._find_spec_dir(spec_id)
        if spec_dir:
            return spec_dir
        
        # Try pattern matching for directories starting with spec_id
        for dir_path in self.context.specs_dir.glob(f"{spec_id}-*"):
            if dir_path.is_dir():
                return dir_path
        
        # Try just the number
        if spec_id.isdigit():
            padded = f"{int(spec_id):03d}"
            for dir_path in self.context.specs_dir.glob(f"{padded}-*"):
                if dir_path.is_dir():
                    return dir_path
        
        return None

    # -------------------------------------------------------------------------
    # IDE Rules Auto-Refresh
    # -------------------------------------------------------------------------
    def _maybe_refresh_ide_rules(self) -> None:
        """Smart refresh of IDE rules for all enabled IDEs - only if the managed block changed"""
        try:
            enabled_ides = self._get_enabled_ides()
            product_context = self.context.get_product_context()

            for ide_name in enabled_ides:
                ide_config = IDEIntegration.IDE_CONFIGS.get(ide_name)
                if not ide_config:
                    continue
                if ide_config["type"] == "folder":
                    # Folder-based rules are SPEKY-only files; rewrite them every time
                    self.ide.update_context_file(product_context, target_ide=ide_name)
                    continue

                rules_file = self.project_root / ide_config["path"]
                if rules_file.exists():
                    current = IDEIntegration.extract_managed_block(rules_file.read_text())
                    wanted = self.ide.build_rules_content(ide_name, product_context).strip("\n")
                    if current == wanted:
                        continue
                self.ide.update_context_file(product_context, target_ide=ide_name)

        except Exception as e:
            # Don't interrupt commands for rule refresh issues, but say what happened
            Console.warning(f"Could not refresh IDE rules: {e}")
    
    def _get_enabled_ides(self) -> List[str]:
        """Get list of enabled IDEs with backward compatibility

        Priority: context.json (project-specific) > config (global) > fallback
        """
        # First check context.json for enabled_ides (project-specific takes precedence)
        if self.context.is_initialized():
            context_ides = self.context.data.get("enabled_ides")
            if context_ides:
                return [context_ides] if isinstance(context_ides, str) else context_ides

        # Check global config for enabled_ides
        enabled_ides = self.config.get("enabled_ides")
        if enabled_ides:
            return [enabled_ides] if isinstance(enabled_ides, str) else enabled_ides

        # Fallback to single IDE setting (backward compatibility)
        single_ide = self.config.get("ide", "windsurf")
        return [single_ide]
    
    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------
    def _smart_truncate(self, text: str, max_chars: int) -> str:
        """Truncate text at line boundary to avoid mid-word cutoff
        
        Args:
            text: Text to truncate
            max_chars: Maximum characters to keep
            
        Returns:
            Truncated text ending at a complete line
        """
        if len(text) <= max_chars:
            return text
        
        # Find the last newline before max_chars
        truncated = text[:max_chars]
        last_newline = truncated.rfind('\n')
        
        if last_newline > 0:
            return truncated[:last_newline]
        
        # No newline found, fall back to word boundary
        last_space = truncated.rfind(' ')
        if last_space > 0:
            return truncated[:last_space] + "..."
        
        return truncated + "..."
    
    def _require_init(self) -> bool:
        """Check if SPEKY is initialized"""
        if not self.context.is_initialized():
            Console.error("SPEKY not initialized. Run: speky init \"Your product idea\"")
            return False
        return True
    
    def _parse_questions(self, response: str) -> List[str]:
        """Parse numbered questions from AI response"""
        questions = []
        for line in response.split('\n'):
            line = line.strip()
            # Match lines starting with numbers like "1.", "1)", "1:"
            if re.match(r'^\d+[\.\)\:]', line):
                question = re.sub(r'^\d+[\.\)\:]\s*', '', line)
                if question:
                    questions.append(question)
        return questions if questions else [response]  # Fallback to whole response
    
    def _format_product_md(self, profile: dict) -> str:
        """Format product profile as markdown"""
        return f"""# {profile.get('name', 'Product')}

## Description
{profile.get('description', 'No description')}

## Target Users
{profile.get('target_users', 'Not specified')}

## Problem
{profile.get('problem', 'Not specified')}

## Platform
{profile.get('platform', 'Not specified')}

## Scale
{profile.get('scale', 'mvp')}

## Domain
{profile.get('domain', 'general')}

## MVP Scope
{profile.get('mvp_scope', 'Not specified')}

## Features
{self._format_features(profile.get('features', []))}

## Constraints
{profile.get('constraints', 'None specified')}
"""

    def _format_features(self, features: list) -> str:
        """Format features list as markdown bullet points"""
        if not features:
            return "No features defined yet. Run `speky spec \"Feature name\"` to add features."
        return "\n".join([f"- {feature}" for feature in features])

    def _generate_tech_decisions_file(self, tech_stack: dict, research_tech_stack: dict = None) -> None:
        """Generate tech_decisions.md from tech stack choices - authoritative tech reference"""
        tech_decisions_file = self.context.context_dir / "tech_decisions.md"
        
        # Build content
        content = f"""# Tech Decisions

> **AUTHORITATIVE**: This file defines the official technology choices for this project.
> All specs, plans, and implementations MUST use these technologies.
> Do NOT suggest alternatives without updating this file first.

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

"""
        
        # Map tech stack categories to more descriptive sections
        category_labels = {
            "frontend": ("Frontend Framework", "UI framework and platform"),
            "backend": ("Backend/Runtime", "Server-side technology"),
            "database": ("Database/Storage", "Data persistence layer"),
            "deployment": ("Deployment", "Hosting and deployment target"),
        }
        
        for key, value in tech_stack.items():
            if value and value.lower() not in ["not decided", "none yet", "not specified", ""]:
                label, description = category_labels.get(key, (key.title(), ""))
                
                # Check if this came from research
                from_research = ""
                if research_tech_stack and research_tech_stack.get(key) == value:
                    from_research = " *(from research)*"
                
                content += f"""## {label}

**Decision**: `{value}`{from_research}
**Description**: {description}
**Rationale**: Selected during project initialization

---

"""
        
        # Add Important Architecture Decisions section (always included in IDE context)
        content += """## Important Architecture Decisions

> **CRITICAL**: This section is ALWAYS included in IDE context during implementation.
> All specs, stories, and code changes MUST conform to these architectural patterns.
> Update this section when making significant architectural changes.

### Patterns & Conventions

*Document your core architectural patterns here. Examples:*

- **State Management**: [Describe how state flows through the app]
- **Data Layer**: [Describe data access patterns, repositories, etc.]
- **Error Handling**: [Describe error handling strategy]
- **Module Structure**: [Describe how code is organized]

### Design Decisions

*Document key design decisions that affect implementation. Examples:*

- **Component Architecture**: [How components are structured]
- **API Contracts**: [How services communicate]
- **Security Patterns**: [Authentication, authorization approach]

### Anti-Patterns to Avoid

*Document patterns that should NOT be used:*

- ❌ [Anti-pattern 1]: [Why to avoid and what to do instead]
- ❌ [Anti-pattern 2]: [Why to avoid and what to do instead]

---

"""
        
        # Add section for future decisions
        content += """## Adding New Decisions

When making technology decisions during development:

1. Add a new section to this file with:
   - **Decision**: The chosen technology
   - **Alternatives Considered**: What else was evaluated
   - **Rationale**: Why this choice was made
   - **Date**: When the decision was made

2. If replacing a technology:
   - Keep the old section but mark it as `DEPRECATED`
   - Add: `**Replaced By**: [new technology]`
   - Add: `**Migration Notes**: [any migration guidance]`

Example:
```markdown
## WebView Package

**Decision**: `flutter_inappwebview` (not webview_flutter)
**Alternatives Considered**: webview_flutter, flutter_webview_plugin
**Rationale**: Better JavaScript interop, more features, active maintenance
**Date**: 2024-01-15
```

---

## Deprecated Technologies

*List any deprecated technologies here with their replacements*

<!-- Example:
### SQLite (DEPRECATED)
**Replaced By**: Drift
**Migration Notes**: Use Drift's type-safe queries instead of raw SQL
-->
"""
        
        tech_decisions_file.write_text(content)
        Console.success(f"Created tech_decisions.md")

    def _update_tech_decisions_from_poc(self, recommendations: dict) -> None:
        """Update tech_decisions.md with POC import recommendations"""
        tech_decisions_file = self.context.context_dir / "tech_decisions.md"
        
        if not tech_decisions_file.exists():
            # Create new file if doesn't exist
            self._generate_tech_decisions_file({})
        
        # Read existing content
        content = tech_decisions_file.read_text()
        
        # Add POC recommendations section
        poc_section = f"""
## POC Import Decisions

*Added from POC import on {datetime.now().strftime('%Y-%m-%d %H:%M')}*

"""
        
        for category, decision in recommendations.items():
            if decision and isinstance(decision, dict):
                chosen = decision.get("chosen", "")
                rejected = decision.get("rejected", "")
                rationale = decision.get("rationale", "From POC analysis")
                
                if chosen:
                    poc_section += f"""### {category}

**Decision**: `{chosen}`"""
                    if rejected:
                        poc_section += f" (not {rejected})"
                    poc_section += f"""
**Rationale**: {rationale}

"""
        
        # Insert before "Adding New Decisions" section if it exists
        if "## Adding New Decisions" in content:
            content = content.replace(
                "## Adding New Decisions",
                poc_section + "\n---\n\n## Adding New Decisions"
            )
        else:
            content += "\n" + poc_section
        
        tech_decisions_file.write_text(content)
        Console.success("Updated tech_decisions.md with POC recommendations")

    def _slugify(self, text: str) -> str:
        """Convert text to slug"""
        slug = text.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = slug.strip('-')
        return slug[:50]  # Limit length
    
    def _is_foundation_spec(self, spec_name: str, spec_content: str = "") -> bool:
        """Detect if a spec should be marked as foundation based on name/content patterns.
        
        Foundation specs are architectural building blocks that other specs depend ON,
        but should not have dependencies themselves. Examples:
        - Infrastructure, environment, deployment setup
        - Core browser/webview module
        - Base authentication framework
        - Database setup and core models
        """
        name_lower = spec_name.lower()
        content_lower = spec_content.lower() if spec_content else ""
        
        # Name patterns that indicate foundation specs
        foundation_name_patterns = [
            'infrastructure', 'infra', 'setup', 'environment', 'env-',
            'core-', 'base-', 'foundation', 'bootstrap',
            'database', 'db-setup', 'schema',
            'deployment', 'docker', 'ci-cd', 'cicd',
            'config', 'configuration',
        ]
        
        # Content patterns that indicate foundation specs (in addition to name)
        foundation_content_patterns = [
            'docker-compose', 'dockerfile', 
            'environment variables', 'env setup',
            'project structure', 'directory structure',
            'initial setup', 'development environment',
        ]
        
        # Check name patterns
        for pattern in foundation_name_patterns:
            if pattern in name_lower:
                return True
        
        # Check content patterns (only if content provided)
        if content_lower:
            for pattern in foundation_content_patterns:
                if pattern in content_lower:
                    return True
        
        return False
    
    @staticmethod
    def _next_item_number(base_dir: Path, prefix: str = "") -> int:
        """Next free number for items named `<prefix><NNN>-slug` in base_dir.

        Uses the highest existing number + 1, so deleting or deprecating an item
        never makes a new item reuse an ID that already exists.
        """
        pattern = re.compile(rf"^{re.escape(prefix)}(\d+)(?:-|$)", re.IGNORECASE)
        highest = 0
        if base_dir.exists():
            for entry in base_dir.iterdir():
                match = pattern.match(entry.name) if entry.is_dir() else None
                if match:
                    highest = max(highest, int(match.group(1)))
        return highest + 1

    @staticmethod
    def _find_item_dir(base_dir: Path, ref: str) -> Optional[Path]:
        """Find an item directory by exact ID (`001`, `1`, `F001`, `f1`) or, failing that,
        by a name that matches exactly one item's slug. Never matches a substring of an ID,
        so `01` cannot resolve to `010-...`."""
        if not ref or not base_dir.exists():
            return None
        ref = ref.strip()
        dirs = sorted(d for d in base_dir.iterdir() if d.is_dir())

        def id_of(name: str) -> str:
            return name.split("-", 1)[0].lower()

        wanted = {ref.lower()}
        id_match = re.match(r"^([A-Za-z]?)(\d+)$", ref)
        if id_match:
            wanted.add(f"{id_match.group(1)}{int(id_match.group(2)):03d}".lower())
        for d in dirs:
            if d.name.lower() == ref.lower() or id_of(d.name) in wanted:
                return d

        # Name lookup: the slug part must contain the ref's slug, and only one item may match
        ref_slug = re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-")
        if not ref_slug or id_match:
            return None
        matches = [d for d in dirs if "-" in d.name and ref_slug in d.name.split("-", 1)[1].lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            Console.warning(f"'{ref}' matches several items: {', '.join(d.name for d in matches)}. "
                            "Use the ID instead.")
        return None

    def _find_spec_dir(self, spec_id: str) -> Optional[Path]:
        """Find spec directory by ID or unique name"""
        return self._find_item_dir(self.context.specs_dir, spec_id)

    def _find_story_dir(self, story_id: str) -> Optional[Path]:
        """Find story directory by ID or unique name"""
        return self._find_item_dir(self.context.stories_dir, story_id)

    def _find_epic_dir(self, epic_id: str) -> Optional[Path]:
        """Find epic directory by ID or unique name"""
        return self._find_item_dir(self.context.epics_dir, epic_id)

    def _load_epic(self, epic_id: str) -> Optional[dict]:
        """Load epic manifest.yaml"""
        epic_dir = self._find_epic_dir(epic_id)
        if not epic_dir:
            return None
        
        manifest_file = epic_dir / "manifest.yaml"
        if not manifest_file.exists():
            return None
        
        try:
            import yaml
            with open(manifest_file) as f:
                epic = yaml.safe_load(f)
                epic['_dir'] = epic_dir  # Store directory reference
                return epic
        except Exception as e:
            Console.warning(f"Failed to load epic {epic_id}: {e}")
            return None

    def _save_epic(self, epic_id: str, epic_data: dict) -> bool:
        """Save epic manifest.yaml"""
        epic_dir = self._find_epic_dir(epic_id)
        if not epic_dir:
            return False
        
        manifest_file = epic_dir / "manifest.yaml"
        
        # Remove internal fields before saving
        save_data = {k: v for k, v in epic_data.items() if not k.startswith('_')}
        
        try:
            import yaml
            with open(manifest_file, 'w') as f:
                yaml.dump(save_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            return True
        except Exception as e:
            Console.error(f"Failed to save epic {epic_id}: {e}")
            return False

    def _get_epic_status(self, epic_id: str) -> dict:
        """Compute epic status from stories (dynamic, not stored)"""
        epic = self._load_epic(epic_id)
        if not epic:
            return {"total": 0, "completed": 0, "in_progress": 0, "pending": 0}
        
        story_ids = epic.get("stories", [])
        stories = []
        
        for sid in story_ids:
            story_dir = self._find_story_dir(sid)
            if story_dir:
                status_file = story_dir / "status.json"
                if status_file.exists():
                    try:
                        stories.append(json.loads(status_file.read_text()))
                    except:
                        pass
        
        completed = sum(1 for s in stories if s.get("status") in ["completed", "done"])
        in_progress = sum(1 for s in stories if s.get("status") == "in_progress")
        
        return {
            "total": len(story_ids),
            "completed": completed,
            "in_progress": in_progress,
            "pending": len(story_ids) - completed - in_progress
        }

    def _get_story_epic(self, story_id: str) -> Optional[dict]:
        """Find which epic a story belongs to"""
        story_dir = self._find_story_dir(story_id)
        if not story_dir:
            return None
        
        status_file = story_dir / "status.json"
        if status_file.exists():
            try:
                status = json.loads(status_file.read_text())
                epic_id = status.get("related_epic")
                if epic_id:
                    return self._load_epic(epic_id)
            except:
                pass
        return None

    def _get_all_epics(self) -> List[dict]:
        """Get all epics with their status"""
        epics = []
        for epic_dir in sorted(self.context.epics_dir.glob("E*/")):
            manifest_file = epic_dir / "manifest.yaml"
            if manifest_file.exists():
                epic = self._load_epic(epic_dir.name.split('-')[0])
                if epic:
                    epic['status'] = self._get_epic_status(epic['id'])
                    epics.append(epic)
        return epics

    # -------------------------------------------------------------------------
    # Command: import (External Knowledge Import)
    # -------------------------------------------------------------------------
    def cmd_import(self, phase: str = None, no_review: bool = False) -> bool:
        """Import external knowledge from .speky/imports/<phase>/source/ with interactive review"""
        if not self._require_init():
            return False
        
        Console.header("📚 Import External Knowledge")
        
        # Step 1: Get phase name
        if not phase:
            # Show existing import folders
            imports_dir = self.context.speky_dir / "imports"
            existing_phases = []
            if imports_dir.exists():
                for d in imports_dir.iterdir():
                    if d.is_dir() and (d / "source").exists():
                        source_dir = d / "source"
                        doc_count = len(list(source_dir.glob("*")))
                        if doc_count > 0:
                            existing_phases.append((d.name, doc_count))
            
            if existing_phases:
                print("\n📂 Existing import folders with documents:")
                for name, count in existing_phases:
                    print(f"   • {name} ({count} document(s))")
                print()
            
            phase = Console.prompt("Phase name (e.g., 'mvp', 'v2-features')", default="mvp")
        
        # Step 2: Define source location (predefined path)
        import_dir = self.context.speky_dir / "imports" / phase
        source_dir = import_dir / "source"
        temp_state_file = import_dir / ".import_state.json"
        
        # Create folder structure if it doesn't exist
        if not source_dir.exists():
            source_dir.mkdir(parents=True, exist_ok=True)
            Console.log(f"Created import folder: .speky/imports/{phase}/source/")
            Console.log("")
            Console.log("📋 Next steps:")
            Console.log(f"   1. Place your documents in: .speky/imports/{phase}/source/")
            Console.log(f"      (Supported: .md, .txt, .pdf, .docx)")
            Console.log(f"   2. Run: speky import --phase {phase}")
            return True
        
        # Step 3: Check for existing import state (from previous failed import)
        if temp_state_file.exists():
            Console.warning("Found incomplete import from previous run")
            if Console.confirm("Resume from where you left off?", default=True):
                # Load saved state
                state = json.loads(temp_state_file.read_text())
                documents = state.get("documents", [])
                analysis = state.get("analysis", "")
                proposed_specs = state.get("proposed_specs", [])
                Console.success(f"Resumed with {len(proposed_specs)} proposed spec(s)")
            else:
                # Discard and start fresh
                temp_state_file.unlink()
                Console.log("Starting fresh import")
                documents = None
                analysis = None
                proposed_specs = None
        else:
            documents = None
            analysis = None
            proposed_specs = None
        
        # Step 4: Scan source folder for documents (if not resumed)
        if documents is None:
            Console.section("Scanning Documents", f"Location: .speky/imports/{phase}/source/")
            documents = self._scan_import_folder(source_dir)
            
            if not documents:
                Console.warning(f"No documents found in .speky/imports/{phase}/source/")
                Console.log("")
                Console.log("📋 To import external knowledge:")
                Console.log(f"   1. Place your documents in: .speky/imports/{phase}/source/")
                Console.log(f"      (Supported: .md, .txt, .pdf, .docx)")
                Console.log(f"   2. Run: speky import --phase {phase}")
                return False
            
            Console.success(f"Found {len(documents)} document(s)")
            for doc in documents:
                print(f"   • {doc['name']} ({doc['size']}) - {doc.get('type', 'general')}")
            
            # Step 5: AI analysis
            Console.section("Analyzing Content")
            analysis = self._analyze_documents(documents, self.context.get_product_context())
            
            if not analysis:
                Console.error("Failed to analyze documents")
                return False
            
            # Step 6: Propose specs
            proposed_specs = self._propose_specs_from_analysis(analysis)
            
            if not proposed_specs:
                Console.error("Could not generate spec proposals")
                return False
            
            Console.success(f"Proposed {len(proposed_specs)} spec(s)")
            
            # Save state before interactive review
            state = {
                "documents": documents,
                "analysis": analysis,
                "proposed_specs": proposed_specs
            }
            temp_state_file.write_text(json.dumps(state, indent=2))
        
        # Step 7: Interactive review (unless --no-review)
        if not no_review:
            Console.section("Interactive Review", "Review and modify proposed specs before importing")
            proposed_specs = self._interactive_spec_review(proposed_specs)
            
            if not proposed_specs:
                Console.log("Import cancelled")
                return False
        
        # Step 7: Finalize import
        Console.section("Creating Import")
        
        # Create specs
        created_specs = []
        for spec_proposal in proposed_specs:
            spec_id = self._create_spec_from_import(spec_proposal, phase)
            if spec_id:
                created_specs.append(spec_id)
        
        # Create manifest
        manifest = {
            "id": phase,
            "name": phase.replace("-", " ").title(),
            "imported_at": datetime.now().isoformat(),
            "source_folder": str(source_dir),
            "documents": [{"name": d['name'], "type": d.get('type', 'unknown')} for d in documents],
            "derived_specs": created_specs,
            "status": "active",
            "analysis_version": "1.0"
        }
        
        (import_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        
        # Save analysis and roadmap
        (import_dir / "analysis.md").write_text(analysis)
        roadmap = self._generate_roadmap(created_specs, proposed_specs)
        (import_dir / "roadmap.md").write_text(roadmap)
        
        # Clean up temp state file after successful import
        if temp_state_file.exists():
            temp_state_file.unlink()
        
        Console.success(f"Import complete: {phase}")
        Console.files_created([
            f".speky/imports/{phase}/manifest.json",
            f".speky/imports/{phase}/analysis.md",
            f".speky/imports/{phase}/roadmap.md",
            f".speky/imports/{phase}/source/ ({len(documents)} files)"
        ])
        
        # Offer phase suggestions if we created multiple specs
        if len(created_specs) >= 2:
            # Build spec list for phase suggestion
            import_specs = []
            for spec_id_item in created_specs:
                spec_dir = self.context.specs_dir / f"{spec_id_item}-*"
                matching_dirs = list(self.context.specs_dir.glob(f"{spec_id_item}-*"))
                if matching_dirs:
                    status_file = matching_dirs[0] / "status.json"
                    if status_file.exists():
                        try:
                            status = json.loads(status_file.read_text())
                            import_specs.append({
                                "id": spec_id_item,
                                "name": status.get("name", "Unknown"),
                                "scope": next((s.get("scope", "") for s in proposed_specs if s.get("name") == status.get("name")), "")
                            })
                        except:
                            pass
            
            if import_specs:
                self._offer_phase_suggestions(import_specs, source="external import")
        
        print(f"\n📋 Next steps:")
        print(f"   1. Review roadmap: .speky/imports/{phase}/roadmap.md")
        print(f"   2. Validate specs (optional): speky validate-spec 001")
        print(f"   3. Generate plan: speky plan 001")
        print(f"   4. Implement: speky implement 001")
        if len(created_specs) >= 2:
            print(f"   5. Or if phases created: speky phases start phase-1")
        print(f"\n💡 Note: Imported specs are already tracked in SPEKY (no adoption needed)")
        
        return True
    
    def cmd_reconcile(self, phase: str, spec_id: str = None, dry_run: bool = False) -> bool:
        """Reconcile code with imported docs and specs"""
        if not self._require_init():
            return False
        
        Console.header(f"🔄 Reconciliation: {phase}")
        
        # Find import
        import_dir = self.context.speky_dir / "imports" / phase
        if not import_dir.exists():
            Console.error(f"Import not found: {phase}")
            return False
        
        # Load manifest
        manifest_file = import_dir / "manifest.json"
        if not manifest_file.exists():
            Console.error("Manifest not found")
            return False
        
        manifest = json.loads(manifest_file.read_text())
        spec_ids = manifest.get("derived_specs", [])
        
        if spec_id:
            spec_ids = [spec_id]
        
        # Detect mismatches
        Console.section("Detecting Mismatches")
        all_mismatches = []
        
        for sid in spec_ids:
            spec_dir = self._find_spec_dir(sid)
            if not spec_dir:
                continue
            
            spec_file = spec_dir / "spec.md"
            if not spec_file.exists():
                continue
            
            mismatches = self._detect_mismatches(spec_file, import_dir)
            all_mismatches.extend(mismatches)
        
        if not all_mismatches:
            Console.success("No mismatches detected - everything is in sync!")
            return True
        
        Console.warning(f"Found {len(all_mismatches)} mismatch(es)")
        
        if dry_run:
            Console.section("Mismatches (Dry Run)")
            for i, mismatch in enumerate(all_mismatches, 1):
                print(f"\n{i}. {mismatch.get('type', 'Unknown')}")
                print(f"   Description: {mismatch.get('description', '')}")
            return True
        
        # Interactive resolution
        Console.section("Interactive Resolution")
        resolutions = []
        
        for i, mismatch in enumerate(all_mismatches, 1):
            print(f"\n{'='*60}")
            print(f"Mismatch {i}/{len(all_mismatches)}: {mismatch.get('type', 'Unknown')}")
            print(f"{'='*60}")
            
            print(f"\n📄 Import: {mismatch.get('import_content', '')[:100]}...")
            print(f"💻 Code: {mismatch.get('code_content', '')[:100]}...")
            
            resolution = self._interactive_mismatch_resolution(mismatch)
            if resolution:
                resolutions.append(resolution)
        
        # Apply resolutions
        if resolutions and not dry_run:
            Console.section("Applying Resolutions")
            for resolution in resolutions:
                self._apply_resolution(resolution, import_dir)
            Console.success(f"Applied {len(resolutions)} resolution(s)")
        
        return True
    
    def cmd_import_status(self) -> bool:
        """Show status of all imports"""
        if not self._require_init():
            return False
        
        Console.header("📚 Import Status")
        
        imports_dir = self.context.speky_dir / "imports"
        if not imports_dir.exists():
            Console.log("No imports found")
            return True
        
        imports = list(imports_dir.glob("*/"))
        if not imports:
            Console.log("No imports found")
            return True
        
        for import_dir in sorted(imports):
            manifest_file = import_dir / "manifest.json"
            if not manifest_file.exists():
                continue
            
            manifest = json.loads(manifest_file.read_text())
            specs = manifest.get("derived_specs", [])
            
            print(f"\n📦 {manifest.get('name', import_dir.name)}")
            print(f"   ID: {manifest.get('id')}")
            print(f"   Status: {manifest.get('status', 'unknown')}")
            print(f"   Imported: {manifest.get('imported_at', 'unknown')}")
            print(f"   Specs: {len(specs)} ({', '.join(specs)})")
        
        return True
    
    # -------------------------------------------------------------------------
    # Command: poc-import (POC Code Import)
    # -------------------------------------------------------------------------
    def cmd_poc_import(self, path: str = None, spec_id: str = None, resume: bool = False) -> bool:
        """Import features from existing POC codebase with AI-assisted analysis"""
        if not self._require_init():
            return False
        
        Console.header("📦 POC Code Import")
        
        # Create POC import directory
        poc_import_dir = self.context.speky_dir / "imports" / "poc_import"
        poc_import_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate session ID
        session_id = f"poc-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        session_dir = poc_import_dir / session_id
        
        # Check for resume
        if resume:
            # Find most recent session
            existing_sessions = sorted(poc_import_dir.glob("poc-*/"), reverse=True)
            for sess in existing_sessions:
                state_file = sess / "state.json"
                if state_file.exists():
                    state = json.loads(state_file.read_text())
                    if state.get("phase") != "completed":
                        session_dir = sess
                        session_id = sess.name
                        Console.success(f"Resuming session: {session_id}")
                        return self._poc_resume_session(session_dir)
            Console.warning("No incomplete sessions found to resume")
        
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # =====================================================================
        # STEP 1: Gather POC Paths
        # =====================================================================
        Console.section("📁 POC Project Path(s)")
        
        poc_paths = []
        
        if path:
            # Path provided via argument
            poc_path = Path(path).resolve()
            if poc_path.exists():
                poc_paths.append(str(poc_path))
            else:
                Console.error(f"Path not found: {path}")
                return False
        else:
            # Ask for path
            print("Enter the path to your POC project:")
            print("(This can be an absolute path or relative to current directory)")
            
            while True:
                path_input = Console.prompt("POC path")
                if not path_input:
                    break
                
                poc_path = Path(path_input).resolve()
                if poc_path.exists():
                    poc_paths.append(str(poc_path))
                    Console.success(f"Added: {poc_path}")
                else:
                    Console.warning(f"Path not found: {path_input}")
                
                if not Console.confirm("Add another POC?", default=False):
                    break
        
        if not poc_paths:
            Console.error("No POC paths provided")
            return False
        
        # Save initial state
        state = {
            "session_id": session_id,
            "phase": "paths_collected",
            "poc_paths": poc_paths,
            "spec_id": spec_id,
            "started_at": datetime.now().isoformat()
        }
        self._poc_save_state(session_dir, state)
        
        # =====================================================================
        # STEP 2: Generate Research Task for IDE
        # =====================================================================
        Console.section("📋 Creating Research Task")
        
        project_tech = self.context.data.get("tech_stack", {})
        task_content = Prompts.poc_research_task(poc_paths, project_tech)
        
        task_file = session_dir / "task.md"
        task_file.write_text(task_content)
        
        print(f"\n📄 Task file created: {task_file}")
        print("\n💡 You can edit task.md to customize the analysis scope\n")
        
        print("=" * 60)
        print("📋 INSTRUCTIONS FOR YOUR IDE")
        print("=" * 60)
        print(f"""
Copy this to your IDE/AI coding agent:

"Please read and follow the instructions in:
{task_file}

Analyze the POC project(s) and write the results to:
{session_dir / 'results.json'}
"
""")
        print("=" * 60)
        
        # Update state
        state["phase"] = "research_pending"
        state["task_file"] = str(task_file)
        self._poc_save_state(session_dir, state)
        
        # Wait for user
        Console.prompt("\nPress Enter when IDE has completed the research...", default="")
        
        # =====================================================================
        # STEP 3: Validate and Read Results
        # =====================================================================
        results_file = session_dir / "results.json"
        
        if not results_file.exists():
            Console.warning("results.json not found")
            print(f"\nExpected location: {results_file}")
            print("\nPlease ensure your IDE wrote the results, then run:")
            print(f"   speky poc-import --resume")
            return False
        
        try:
            results = json.loads(results_file.read_text())
        except json.JSONDecodeError as e:
            Console.error(f"Invalid JSON in results.json: {e}")
            print("\nPlease fix the JSON and run: speky poc-import --resume")
            return False
        
        Console.success("Research results loaded")
        
        # Display summary
        all_features = []
        for poc in results.get("pocs", []):
            print(f"\n📦 POC: {poc.get('name', 'Unknown')}")
            print(f"   Path: {poc.get('path', 'Unknown')}")
            
            tech = poc.get("tech_stack", {})
            print(f"   Tech: {tech.get('framework', 'Unknown')} / {tech.get('database', 'Unknown')}")
            
            features = poc.get("features", [])
            print(f"   Features: {len(features)}")
            for f in features:
                print(f"      • {f.get('name', 'Unknown')} [{f.get('complexity', '?')}] - {f.get('description', '')[:50]}")
                all_features.append(f)
        
        # Update state
        state["phase"] = "research_complete"
        state["results"] = results
        self._poc_save_state(session_dir, state)
        
        # Allow user to edit results
        edit_choice = Console.prompt("\n[Enter] continue, [e] edit results.json first", default="")
        if edit_choice.lower() == 'e':
            print(f"Edit: {results_file}")
            Console.prompt("Press Enter when done...", default="")
            results = json.loads(results_file.read_text())
            all_features = []
            for poc in results.get("pocs", []):
                all_features.extend(poc.get("features", []))
        
        # =====================================================================
        # STEP 4: Feature Selection (Natural Language)
        # =====================================================================
        Console.section("🎯 Feature Selection")
        
        print("\nWhich features do you want to include?")
        print("Options:")
        print("  • Enter numbers: 1,2,4")
        print("  • Describe: 'auth and api but not admin'")
        print("  • 'all' to include everything")
        print("  • 'none' to cancel")
        
        # List features with numbers
        print("\n📋 Available Features:")
        for i, f in enumerate(all_features, 1):
            print(f"   {i}. {f.get('name', 'Unknown')} - {f.get('description', '')[:60]}")
        
        selection_input = Console.prompt("\nYour selection")
        
        if selection_input.lower() == 'none':
            Console.log("Import cancelled")
            return False
        
        # Parse selection
        selected_features = self._poc_parse_feature_selection(selection_input, all_features)
        
        if not selected_features:
            Console.error("No features selected")
            return False
        
        # Confirm selection
        print("\n✅ Selected features:")
        for f in selected_features:
            print(f"   • {f.get('name')}")
        
        if not Console.confirm("Proceed with these features?", default=True):
            return False
        
        # Update state
        state["phase"] = "selection_complete"
        state["selected_features"] = selected_features
        self._poc_save_state(session_dir, state)
        
        # =====================================================================
        # STEP 5: AI Auto-Resolution (Transparent)
        # =====================================================================
        Console.section("🤖 AI Analysis & Recommendations")
        
        # Get POC tech stack from first POC
        poc_tech = results.get("pocs", [{}])[0].get("tech_stack", {})
        
        # AI resolution
        resolution_prompt = Prompts.poc_auto_resolve(selected_features, poc_tech, project_tech)
        resolution_response = self.ai.query(resolution_prompt)
        
        # Try to parse JSON from response
        resolutions = self.ai._extract_json(resolution_response)
        
        if not resolutions:
            # Fallback - create basic resolutions
            Console.warning("Could not parse AI recommendations, using defaults")
            resolutions = {
                "tech_conflicts": [],
                "feature_handling": [
                    {"feature_id": f.get("id", f.get("name")), "feature_name": f.get("name"), "action": "SPEC_ONLY", "reason": "Default", "notes": ""}
                    for f in selected_features
                ],
                "new_dependencies": [],
                "summary": "Using default spec-only approach"
            }
        
        # Save recommendations for user to review/edit
        recommendations_file = session_dir / "recommendations.md"
        recommendations_md = f"""# AI Recommendations for POC Import

## Summary
{resolutions.get('summary', 'No summary')}

## Tech Stack Conflicts
"""
        for conflict in resolutions.get("tech_conflicts", []):
            recommendations_md += f"""
### {conflict.get('component', 'Unknown')}
- **POC**: {conflict.get('poc', 'Unknown')}
- **Project**: {conflict.get('project', 'Unknown')}
- **Severity**: {conflict.get('severity', 'Unknown')}
- **Recommendation**: {conflict.get('recommendation', 'None')}
"""
        
        recommendations_md += "\n## Feature Handling\n"
        for fh in resolutions.get("feature_handling", []):
            recommendations_md += f"""
### {fh.get('feature_name', 'Unknown')}
- **Action**: {fh.get('action', 'SPEC_ONLY')}
- **Reason**: {fh.get('reason', 'None')}
- **Notes**: {fh.get('notes', 'None')}
"""
        
        recommendations_md += "\n## New Dependencies\n"
        for dep in resolutions.get("new_dependencies", []):
            recommendations_md += f"- **{dep.get('name', 'Unknown')}**: {dep.get('purpose', 'Unknown')}\n"
        
        recommendations_file.write_text(recommendations_md)
        
        # Display recommendations
        print("\n" + "=" * 60)
        print("🤖 AI RECOMMENDATIONS")
        print("=" * 60)
        print(f"\n{resolutions.get('summary', 'Analysis complete')}\n")
        
        if resolutions.get("tech_conflicts"):
            print("⚠️  Tech Conflicts:")
            for c in resolutions["tech_conflicts"]:
                print(f"   • {c.get('component')}: {c.get('poc')} → {c.get('project')} [{c.get('severity')}]")
        
        print("\n📋 Feature Handling:")
        for fh in resolutions.get("feature_handling", []):
            action_icon = "📋" if fh.get("action") == "SPEC_ONLY" else "📁"
            print(f"   {action_icon} {fh.get('feature_name')}: {fh.get('action')}")
            if fh.get("notes"):
                print(f"      Note: {fh.get('notes')}")
        
        print(f"\n📄 Full recommendations: {recommendations_file}")
        print("💡 Edit this file to override any AI decisions\n")
        
        override_choice = Console.prompt("[Enter] accept, [e] edit recommendations first", default="")
        if override_choice.lower() == 'e':
            print(f"Edit: {recommendations_file}")
            Console.prompt("Press Enter when done...", default="")
            # Note: Would need to re-parse markdown to JSON - for now trust user edited correctly
        
        # Update state
        state["phase"] = "resolution_complete"
        state["resolutions"] = resolutions
        self._poc_save_state(session_dir, state)
        
        # =====================================================================
        # STEP 6: Generate Extraction Task
        # =====================================================================
        Console.section("📋 Creating Extraction Task")
        
        extraction_content = Prompts.poc_extraction_task(selected_features, resolutions)
        extraction_file = session_dir / "extraction_task.md"
        extraction_file.write_text(extraction_content)
        
        # Create specs directory
        specs_dir = session_dir / "specs"
        specs_dir.mkdir(exist_ok=True)
        
        print(f"\n📄 Extraction task created: {extraction_file}")
        print(f"📁 Specs will be created in: {specs_dir}")
        
        print("\n" + "=" * 60)
        print("📋 INSTRUCTIONS FOR YOUR IDE")
        print("=" * 60)
        print(f"""
Copy this to your IDE/AI coding agent:

"Please read and follow the instructions in:
{extraction_file}

Create specs in: {specs_dir}
Write completion report to: {session_dir / 'extraction_report.json'}
"
""")
        print("=" * 60)
        
        # Update state
        state["phase"] = "extraction_pending"
        state["extraction_file"] = str(extraction_file)
        self._poc_save_state(session_dir, state)
        
        Console.prompt("\nPress Enter when IDE has completed extraction...", default="")
        
        # =====================================================================
        # STEP 7-9: Validate and Adopt Specs (delegated to helper method)
        # =====================================================================
        return self._poc_validate_and_adopt_specs(
            session_dir, specs_dir, selected_features,
            poc_paths, session_id, results, resolutions, state
        )
    
    def _poc_validate_and_adopt_specs(
        self, session_dir: Path, specs_dir: Path, selected_features: List[dict],
        poc_paths: List[str], session_id: str, results: dict, resolutions: dict, state: dict
    ) -> bool:
        """Validate and adopt generated specs (Step 7-9 of POC import)"""
        
        # =====================================================================
        # STEP 7: Validate and Adopt Specs
        # =====================================================================
        Console.section("📋 Validating Generated Specs")
        
        # Find generated specs
        generated_specs = list(specs_dir.glob("*/spec.md")) + list(specs_dir.glob("*.md"))
        
        if not generated_specs:
            Console.warning("No specs found in specs folder")
            print(f"\nExpected location: {specs_dir}")
            print("\nPlease ensure your IDE created specs, then run:")
            print("   speky poc-import --resume")
            return False
        
        Console.success(f"Found {len(generated_specs)} spec(s)")
        
        for spec_file in generated_specs:
            spec_name = spec_file.parent.name if spec_file.name == "spec.md" else spec_file.stem
            print(f"   • {spec_name}")
        
        print(f"\n💡 Review/edit specs in: {specs_dir}")
        print("   You can modify any spec before adoption\n")
        
        if not Console.confirm("Adopt these specs into SPEKY?", default=True):
            Console.log("Specs saved but not adopted. Run 'speky poc-import --resume' to continue later.")
            return False
        
        # =====================================================================
        # STEP 8: Adopt Specs (with Conflict Detection)
        # =====================================================================
        Console.section("📥 Adopting Specs")
        
        adopted_specs = []
        skipped_specs = []
        merged_specs = []
        next_id = self._next_item_number(self.context.specs_dir)
        
        # Build feature ID to spec ID mapping for dependencies
        feature_to_spec = {}
        
        for spec_file in generated_specs:
            # Determine spec name
            if spec_file.name == "spec.md":
                spec_name = spec_file.parent.name
                spec_content = spec_file.read_text()
            else:
                spec_name = spec_file.stem
                spec_content = spec_file.read_text()
            
            # Find matching feature from selected_features
            matching_feature = None
            for f in selected_features:
                if self._slugify(f.get('name', '')) == self._slugify(spec_name) or f.get('id', '') == spec_name:
                    matching_feature = f
                    break
            
            if not matching_feature:
                matching_feature = {"name": spec_name}
            
            # =====================================================================
            # CONFLICT DETECTION
            # =====================================================================
            conflict = self._detect_spec_conflict(spec_name)
            
            if conflict:
                # Resolve conflict interactively
                resolution = self._resolve_spec_conflict(
                    matching_feature,
                    spec_content,
                    conflict
                )
                
                if resolution["action"] == "skip":
                    # Keep existing, skip POC feature
                    Console.log(f"Skipped: {spec_name} (keeping existing {conflict.get('spec_id')})")
                    skipped_specs.append({
                        "name": spec_name,
                        "reason": resolution.get("reason"),
                        "existing_spec": conflict.get("spec_id")
                    })
                    
                    # Add note to existing spec about POC alternative
                    existing_spec_dir = conflict.get("spec_dir")
                    if existing_spec_dir:
                        notes_file = existing_spec_dir / "notes.md"
                        note_content = f"""## POC Alternative Considered ({datetime.now().isoformat()})

- POC Feature: {spec_name}
- Decision: Kept existing spec
- Reason: {resolution.get('reason', 'User preference')}
"""
                        if notes_file.exists():
                            note_content = notes_file.read_text() + "\n" + note_content
                        notes_file.write_text(note_content)
                    
                    continue
                
                elif resolution["action"] == "replace":
                    # Deprecate existing, create new from POC
                    self._deprecate_spec(
                        conflict.get("spec_id"),
                        resolution.get("reason", "Replaced by POC implementation")
                    )
                    # Continue with normal creation below
                
                elif resolution["action"] == "merge":
                    # AI-assisted merge into existing spec
                    merged_id = self._merge_specs(
                        matching_feature,
                        spec_content,
                        conflict,
                        resolution.get("merge_recommendation", "")
                    )
                    if merged_id:
                        merged_specs.append(merged_id)
                        # Map feature to merged spec for dependency tracking
                        feature_id = matching_feature.get('id', matching_feature.get('name', ''))
                        feature_to_spec[feature_id] = merged_id
                    continue
                
                elif resolution["action"] == "keep_both":
                    # Create new spec and add cross-references
                    # Will be handled below, but we'll add cross-reference after creation
                    pass
            
            # =====================================================================
            # CREATE NEW SPEC
            # =====================================================================
            spec_id = f"{next_id:03d}"
            slug = self._slugify(spec_name)
            target_dir = self.context.specs_dir / f"{spec_id}-{slug}"
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy spec
            (target_dir / "spec.md").write_text(spec_content)
            
            # Determine priority from feature complexity or action
            priority = "P1"  # Default
            complexity = matching_feature.get('complexity', 'M')
            if complexity == 'S':
                priority = "P2"
            elif complexity == 'L':
                priority = "P0"
            
            # Store mapping for dependency resolution
            feature_id = matching_feature.get('id', matching_feature.get('name', ''))
            feature_to_spec[feature_id] = spec_id
            
            # Auto-detect if this should be a foundation spec
            is_foundation = self._is_foundation_spec(spec_name, spec_content)
            
            # Create status with POC source info, priority, and placeholder for dependencies
            status = {
                "id": spec_id,
                "name": spec_name,
                "status": "draft",
                "created": datetime.now().isoformat(),
                "source": "poc_import",
                "poc_session": session_id,
                "poc_paths": poc_paths,
                "priority": priority,
                "dependencies": [],  # Will be populated below (but not for foundations)
                "foundation": is_foundation
            }
            (target_dir / "status.json").write_text(json.dumps(status, indent=2))
            
            # Add cross-references if this was a "keep_both" resolution
            if conflict and resolution.get("action") == "keep_both":
                self._add_spec_cross_reference(
                    conflict.get("spec_id"),
                    spec_id,
                    spec_name
                )
                self._add_spec_cross_reference(
                    spec_id,
                    conflict.get("spec_id"),
                    conflict.get("spec_name")
                )
                Console.success(f"Created spec: {spec_id}-{slug} [Alternative to {conflict.get('spec_id')}]")
            else:
                foundation_marker = " 🏗️ FOUNDATION" if is_foundation else ""
                Console.success(f"Created spec: {spec_id}-{slug} [Priority: {priority}]{foundation_marker}")
            
            adopted_specs.append(spec_id)
            next_id += 1
        
        # Summary of conflict resolutions
        if skipped_specs or merged_specs:
            print("\n📊 Conflict Resolution Summary:")
            if skipped_specs:
                print(f"   Skipped: {len(skipped_specs)} (kept existing specs)")
                for s in skipped_specs:
                    print(f"      • {s['name']} → kept {s['existing_spec']}")
            if merged_specs:
                print(f"   Merged: {len(merged_specs)} (combined with existing)")
                for m in merged_specs:
                    print(f"      • Merged into {m}")
        
        # =====================================================================
        # Map POC Feature Dependencies to Spec Dependencies
        # =====================================================================
        feature_dependencies = results.get("feature_dependencies", [])
        
        if feature_dependencies:
            Console.section("🔗 Mapping Feature Dependencies")
            
            for dep in feature_dependencies:
                from_feature = dep.get("from")
                to_feature = dep.get("to")
                reason = dep.get("reason", "")
                
                # Map to spec IDs
                from_spec = feature_to_spec.get(from_feature)
                to_spec = feature_to_spec.get(to_feature)
                
                if from_spec and to_spec:
                    # Find the actual directory (slug might differ)
                    for spec_dir in self.context.specs_dir.glob(f"{from_spec}-*"):
                        status_file = spec_dir / "status.json"
                        if status_file.exists():
                            status_data = json.loads(status_file.read_text())
                            if status_data.get("id") == from_spec:
                                # Skip if from_spec is a foundation (foundations have no deps)
                                if status_data.get("foundation", False):
                                    print(f"   ⚠️  Skipping: {from_spec} is FOUNDATION (no deps allowed)")
                                    break
                                # Add dependency
                                if to_spec not in status_data.get("dependencies", []):
                                    status_data["dependencies"].append(to_spec)
                                    status_file.write_text(json.dumps(status_data, indent=2))
                                    print(f"   • {from_spec} depends on {to_spec} ({reason})")
                                break
        
        # =====================================================================
        # STEP 9: Finalize
        # =====================================================================
        
        # Create manifest
        manifest = {
            "session_id": session_id,
            "completed_at": datetime.now().isoformat(),
            "poc_paths": poc_paths,
            "features_selected": [f.get("name") for f in selected_features],
            "specs_created": adopted_specs,
            "resolutions": resolutions
        }
        (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        
        # Update state
        state["phase"] = "completed"
        state["adopted_specs"] = adopted_specs
        self._poc_save_state(session_dir, state)
        
        # Offer phase suggestions if we created multiple specs
        if len(adopted_specs) >= 2:
            poc_specs = []
            for spec_id in adopted_specs:
                matching_dirs = list(self.context.specs_dir.glob(f"{spec_id}-*"))
                if matching_dirs:
                    status_file = matching_dirs[0] / "status.json"
                    if status_file.exists():
                        try:
                            status = json.loads(status_file.read_text())
                            poc_specs.append({
                                "id": spec_id,
                                "name": status.get("name", "Unknown"),
                                "scope": ""
                            })
                        except:
                            pass
            
            if poc_specs:
                self._offer_phase_suggestions(poc_specs, source="POC import")
        
        # Summary
        print("\n" + "=" * 60)
        print("✅ POC IMPORT COMPLETE")
        print("=" * 60)
        print(f"""
POC Source: {', '.join(poc_paths)}
Session: {session_id}

Created Specs:""")
        for spec_id in adopted_specs:
            print(f"   • {spec_id}")
        
        phases_exist = len(self._get_all_phases()) > 0
        phase_step = ""
        if phases_exist:
            phase_step = f"\n   6. Or start phase: speky phases start phase-1"
        
        print(f"""
📋 Next Steps:
   1. Review specs in {SPEKY_DIR}/specs/
   2. Run: speky sequence (to see implementation order)
   3. Run: speky infer-deps (to infer dependencies)
   4. Run: speky plan {adopted_specs[0] if adopted_specs else '001'}
   5. Run: speky implement {adopted_specs[0] if adopted_specs else '001'}{phase_step}
""")
        
        return True
    
    def _poc_save_state(self, session_dir: Path, state: dict):
        """Save POC import session state"""
        state_file = session_dir / "state.json"
        state_file.write_text(json.dumps(state, indent=2))
    
    def _poc_resume_session(self, session_dir: Path) -> bool:
        """Resume an incomplete POC import session"""
        state_file = session_dir / "state.json"
        state = json.loads(state_file.read_text())
        
        phase = state.get("phase", "")
        Console.log(f"Resuming from phase: {phase}")
        
        # Resume based on phase
        if phase == "research_pending":
            Console.log("Waiting for research results...")
            Console.prompt("Press Enter when IDE has completed research...", default="")
            # Continue with rest of flow
            # For simplicity, restart the flow with saved paths
            return self.cmd_poc_import(path=state.get("poc_paths", [None])[0])
        
        elif phase == "extraction_pending":
            Console.log("Waiting for extraction...")
            Console.prompt("Press Enter when IDE has completed extraction...", default="")
            
            # Continue from Step 7: Validation and Adoption
            session_id = state.get("session_id")
            specs_dir = session_dir / "specs"
            selected_features = state.get("selected_features", [])
            poc_paths = state.get("poc_paths", [])
            results = state.get("results", {})
            resolutions = state.get("resolutions", {})
            
            # Jump to Step 7
            return self._poc_validate_and_adopt_specs(
                session_dir, specs_dir, selected_features, 
                poc_paths, session_id, results, resolutions, state
            )
        
        else:
            Console.warning(f"Cannot resume from phase: {phase}")
            return False
    
    def _poc_parse_feature_selection(self, selection: str, all_features: List[dict]) -> List[dict]:
        """Parse natural language or number-based feature selection"""
        selection = selection.strip().lower()
        
        # Handle 'all'
        if selection == 'all':
            return all_features
        
        # Handle comma-separated numbers
        if all(c.isdigit() or c in ', ' for c in selection):
            numbers = [int(n.strip()) for n in selection.split(',') if n.strip().isdigit()]
            selected = []
            for n in numbers:
                if 1 <= n <= len(all_features):
                    selected.append(all_features[n - 1])
            return selected
        
        # Natural language parsing - simple keyword matching
        selected = []
        selection_lower = selection.lower()
        
        # Check for exclusions
        exclude_keywords = []
        if ' but not ' in selection_lower:
            parts = selection_lower.split(' but not ')
            selection_lower = parts[0]
            exclude_keywords = [k.strip() for k in parts[1].split(' and ')]
        elif ' except ' in selection_lower:
            parts = selection_lower.split(' except ')
            selection_lower = parts[0]
            exclude_keywords = [k.strip() for k in parts[1].split(' and ')]
        
        # Parse inclusions
        include_keywords = [k.strip() for k in selection_lower.replace(' and ', ',').split(',')]
        
        for f in all_features:
            feature_name = f.get('name', '').lower()
            feature_id = f.get('id', '').lower()
            
            # Check if should include
            should_include = any(kw in feature_name or kw in feature_id for kw in include_keywords if kw)
            
            # Check if should exclude
            should_exclude = any(kw in feature_name or kw in feature_id for kw in exclude_keywords if kw)
            
            if should_include and not should_exclude:
                selected.append(f)
        
        return selected
    
    # -------------------------------------------------------------------------
    # Spec Conflict Detection & Resolution
    # -------------------------------------------------------------------------
    
    def _detect_spec_conflict(self, feature_name: str) -> Optional[dict]:
        """Detect if a feature conflicts with existing specs"""
        existing_specs = list(self.context.specs_dir.glob("*/"))
        
        for spec_dir in existing_specs:
            status_file = spec_dir / "status.json"
            if not status_file.exists():
                continue
            
            try:
                status = json.loads(status_file.read_text())
                spec_name = status.get("name", "")
                
                # Skip deprecated specs
                if status.get("status") == "deprecated":
                    continue
                
                # Check for name similarity
                if self._is_name_similar(feature_name, spec_name):
                    # Load spec content for comparison
                    spec_file = spec_dir / "spec.md"
                    spec_content = spec_file.read_text() if spec_file.exists() else ""
                    
                    return {
                        "spec_id": status.get("id"),
                        "spec_name": spec_name,
                        "spec_dir": spec_dir,
                        "source": status.get("source", "unknown"),
                        "priority": status.get("priority", "P1"),
                        "spec_content": spec_content[:1500],  # First 1500 chars for comparison
                        "status": status
                    }
            except Exception:
                continue
        
        return None
    
    def _is_name_similar(self, name1: str, name2: str) -> bool:
        """Check if two feature names are similar enough to be conflicts"""
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()
        
        # Exact match
        if n1 == n2:
            return True
        
        # One contains the other
        if n1 in n2 or n2 in n1:
            return True
        
        # Word overlap check
        # Remove common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'for', 'to', 'of', 'in', 'with'}
        words1 = set(n1.replace('-', ' ').replace('_', ' ').split()) - stop_words
        words2 = set(n2.replace('-', ' ').replace('_', ' ').split()) - stop_words
        
        if len(words1) == 0 or len(words2) == 0:
            return False
        
        # If 50%+ of words match, consider similar
        overlap = len(words1 & words2)
        similarity = overlap / min(len(words1), len(words2))
        
        return similarity >= 0.5
    
    def _resolve_spec_conflict(self, poc_feature: dict, poc_spec_content: str, 
                               conflict: dict) -> dict:
        """Interactive conflict resolution with AI recommendation"""
        print(f"\n{'='*60}")
        print("⚠️  SPEC CONFLICT DETECTED")
        print(f"{'='*60}")
        
        poc_name = poc_feature.get('name', 'Unknown')
        existing_name = conflict.get('spec_name')
        existing_id = conflict.get('spec_id')
        existing_source = conflict.get('source', 'unknown')
        
        print(f"\n📦 POC Feature: \"{poc_name}\"")
        print(f"📄 Existing Spec: {existing_id}-{self._slugify(existing_name)} (from {existing_source})")
        
        # Show brief comparison
        print(f"\n--- Existing Spec Approach ---")
        existing_summary = conflict.get('spec_content', '')[:500]
        print(existing_summary + "..." if len(existing_summary) >= 500 else existing_summary)
        
        print(f"\n--- POC Implementation ---")
        poc_summary = poc_spec_content[:500] if poc_spec_content else poc_feature.get('description', 'No description')[:500]
        print(poc_summary + "..." if len(poc_summary) >= 500 else poc_summary)
        
        # Get AI recommendation
        print("\n🤖 Getting AI recommendation...")
        recommendation = self._get_conflict_recommendation(
            poc_feature, poc_spec_content, conflict
        )
        
        print(f"\n🤖 AI Recommendation: {recommendation.get('action', 'UNKNOWN')}")
        print(f"   Reason: {recommendation.get('reason', 'No reason provided')}")
        
        # Present options
        print("\nHow would you like to resolve this conflict?")
        options = [
            f"Keep existing spec (skip POC feature)",
            f"Replace with POC (deprecate {existing_id})",
            "Merge both approaches (AI-assisted)",
            "Keep both as alternatives",
            "Show detailed comparison"
        ]
        
        # Mark recommended option
        rec_action = recommendation.get('action', '')
        for i, opt in enumerate(options):
            marker = " [RECOMMENDED]" if (
                (rec_action == "KEEP_EXISTING" and i == 0) or
                (rec_action == "USE_POC" and i == 1) or
                (rec_action == "MERGE" and i == 2)
            ) else ""
            print(f"   {i+1}. {opt}{marker}")
        
        choice = Console.prompt("Your choice (1-5)", default="1")
        
        try:
            choice_num = int(choice)
        except ValueError:
            choice_num = 1
        
        if choice_num == 5:
            # Show detailed comparison
            self._show_detailed_comparison(poc_feature, poc_spec_content, conflict)
            # Re-prompt
            return self._resolve_spec_conflict(poc_feature, poc_spec_content, conflict)
        
        if choice_num == 1:
            # Keep existing, skip POC
            reason = Console.prompt("Reason for keeping existing (optional)", default="")
            return {
                "action": "skip",
                "reason": reason or "User chose to keep existing spec",
                "existing_spec_id": existing_id
            }
        
        elif choice_num == 2:
            # Replace with POC
            return {
                "action": "replace",
                "deprecate_spec_id": existing_id,
                "reason": "Replaced by POC implementation"
            }
        
        elif choice_num == 3:
            # Merge
            return {
                "action": "merge",
                "existing_spec_id": existing_id,
                "existing_spec_dir": conflict.get('spec_dir'),
                "merge_recommendation": recommendation.get('merge_suggestion', '')
            }
        
        elif choice_num == 4:
            # Keep both
            return {
                "action": "keep_both",
                "existing_spec_id": existing_id,
                "cross_reference": True
            }
        
        # Default: skip
        return {"action": "skip", "reason": "No valid choice"}
    
    def _get_conflict_recommendation(self, poc_feature: dict, poc_spec_content: str,
                                     conflict: dict) -> dict:
        """Get AI recommendation for conflict resolution"""
        product_context = self.context.get_product_context()[:1000]
        
        prompt = f"""Analyze these two approaches for the same feature and recommend which to use:

EXISTING SPEC (from {conflict.get('source', 'unknown')}):
Name: {conflict.get('spec_name')}
Content:
{conflict.get('spec_content', 'No content')[:1000]}

POC IMPLEMENTATION:
Name: {poc_feature.get('name')}
Description: {poc_feature.get('description', 'No description')}
Tech: {poc_feature.get('tech', {})}
Content:
{poc_spec_content[:1000] if poc_spec_content else 'No spec content yet'}

PRODUCT CONTEXT:
{product_context}

Analyze and respond in JSON:
{{
    "action": "KEEP_EXISTING" | "USE_POC" | "MERGE",
    "reason": "2-3 sentence explanation",
    "merge_suggestion": "If MERGE, brief description of how to combine"
}}

Consider:
- Technical merit and production-readiness
- Alignment with product goals
- Complexity and maintainability
- Which approach is more complete"""

        response = self.ai.query(prompt)
        result = self.ai._extract_json(response)
        
        if not result:
            return {
                "action": "MERGE",
                "reason": "Could not determine best approach, recommend manual review",
                "merge_suggestion": "Review both approaches and combine best elements"
            }
        
        return result
    
    def _show_detailed_comparison(self, poc_feature: dict, poc_spec_content: str,
                                  conflict: dict):
        """Show detailed side-by-side comparison"""
        print(f"\n{'='*60}")
        print("DETAILED COMPARISON")
        print(f"{'='*60}")
        
        print(f"\n{'='*30} EXISTING SPEC {'='*30}")
        print(f"ID: {conflict.get('spec_id')}")
        print(f"Name: {conflict.get('spec_name')}")
        print(f"Source: {conflict.get('source')}")
        print(f"Priority: {conflict.get('priority')}")
        print(f"\nContent:\n{conflict.get('spec_content', 'No content')}")
        
        print(f"\n{'='*30} POC FEATURE {'='*30}")
        print(f"Name: {poc_feature.get('name')}")
        print(f"Description: {poc_feature.get('description', 'No description')}")
        print(f"Complexity: {poc_feature.get('complexity', 'Unknown')}")
        print(f"Tech: {poc_feature.get('tech', {})}")
        if poc_spec_content:
            print(f"\nSpec Content:\n{poc_spec_content[:2000]}")
        
        print(f"\n{'='*60}\n")
        Console.prompt("Press Enter to continue...", default="")
    
    def _deprecate_spec(self, spec_id: str, reason: str, replaced_by: str = None):
        """Deprecate an existing spec"""
        for spec_dir in self.context.specs_dir.glob(f"{spec_id}-*"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                status = json.loads(status_file.read_text())
                status["status"] = "deprecated"
                status["deprecated_at"] = datetime.now().isoformat()
                status["deprecated_reason"] = reason
                if replaced_by:
                    status["replaced_by"] = replaced_by
                status_file.write_text(json.dumps(status, indent=2))
                
                # Also add note to spec.md
                spec_file = spec_dir / "spec.md"
                if spec_file.exists():
                    content = spec_file.read_text()
                    deprecation_notice = f"""
> ⚠️ **DEPRECATED**: {reason}
> Replaced by: {replaced_by if replaced_by else 'N/A'}
> Deprecated at: {datetime.now().isoformat()}

"""
                    spec_file.write_text(deprecation_notice + content)
                
                Console.warning(f"Deprecated spec: {spec_id}")
                return True
        
        return False
    
    def _merge_specs(self, poc_feature: dict, poc_spec_content: str, 
                     conflict: dict, merge_suggestion: str) -> str:
        """AI-assisted merge of two spec approaches"""
        existing_spec_dir = conflict.get('spec_dir')
        existing_spec_file = existing_spec_dir / "spec.md"
        existing_content = existing_spec_file.read_text() if existing_spec_file.exists() else ""
        
        product_context = self.context.get_product_context()[:500]
        tech_stack = self.context.data.get("tech_stack", {})
        
        prompt = f"""Merge these two approaches into a single comprehensive spec:

EXISTING SPEC:
{existing_content[:2000]}

POC IMPLEMENTATION:
Feature: {poc_feature.get('name')}
Description: {poc_feature.get('description', '')}
{poc_spec_content[:2000] if poc_spec_content else ''}

MERGE GUIDANCE:
{merge_suggestion}

PRODUCT CONTEXT:
{product_context}

TECH STACK:
{json.dumps(tech_stack, indent=2)}

Create a merged spec that:
1. Combines the best of both approaches
2. Clearly documents what came from each source
3. Resolves any conflicts with clear reasoning
4. Follows this format:

# [Feature Name]

## Overview
[Combined description]

## Approach
[Merged approach with sources noted]

## MVP Scope
[Combined scope]

## User Stories
[Merged stories]

## Technical Approach
[Best technical approach from both]

## Merge Notes
- From existing spec: [what was kept]
- From POC: [what was incorporated]
- Conflicts resolved: [how]
"""

        merged_content = self.ai.query(prompt)
        
        if not merged_content:
            Console.warning("AI merge failed, keeping existing spec")
            return None
        
        # Update existing spec with merged content
        existing_spec_file.write_text(merged_content)
        
        # Update status
        status_file = existing_spec_dir / "status.json"
        if status_file.exists():
            status = json.loads(status_file.read_text())
            status["merged_at"] = datetime.now().isoformat()
            status["merged_with_poc"] = poc_feature.get('name')
            status["source"] = f"{status.get('source', 'unknown')}+poc_import"
            status_file.write_text(json.dumps(status, indent=2))
        
        Console.success(f"Merged POC into existing spec: {conflict.get('spec_id')}")
        return conflict.get('spec_id')
    
    def _add_spec_cross_reference(self, spec_id: str, related_spec_id: str, 
                                  related_name: str):
        """Add cross-reference between two related specs"""
        for spec_dir in self.context.specs_dir.glob(f"{spec_id}-*"):
            spec_file = spec_dir / "spec.md"
            if spec_file.exists():
                content = spec_file.read_text()
                
                # Add cross-reference section if not exists
                if "## Related Specs" not in content:
                    content += f"""

## Related Specs

- See [{related_spec_id}](./{related_spec_id}-{self._slugify(related_name)}/spec.md) for alternative approach
"""
                else:
                    # Append to existing section
                    content = content.replace(
                        "## Related Specs\n",
                        f"## Related Specs\n\n- See [{related_spec_id}](./{related_spec_id}-{self._slugify(related_name)}/spec.md) for alternative approach\n"
                    )
                
                spec_file.write_text(content)
    
    # -------------------------------------------------------------------------
    # Dependency Inference & Validation
    # -------------------------------------------------------------------------
    
    def _infer_dependencies(self, spec_name: str, spec_content: str) -> List[str]:
        """AI-assisted dependency inference based on spec content and existing specs"""
        # Get all existing specs
        existing_specs = []
        foundation_specs = []  # Specs marked as foundation
        current_spec_id = None
        
        for spec_dir in self.context.specs_dir.glob("*/"):
            status_file = spec_dir / "status.json"
            spec_file = spec_dir / "spec.md"
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    if status.get("status") == "deprecated":
                        continue
                    
                    # Check if this is the current spec
                    if status.get("name") == spec_name:
                        current_spec_id = status.get("id")
                        # If marked as foundation, return empty (no deps)
                        if status.get("foundation", False):
                            return []
                    
                    spec_summary = ""
                    if spec_file.exists():
                        spec_summary = spec_file.read_text()[:500]
                    
                    spec_info = {
                        "id": status.get("id"),
                        "name": status.get("name"),
                        "summary": spec_summary,
                        "foundation": status.get("foundation", False),
                        "current_deps": status.get("dependencies", [])
                    }
                    existing_specs.append(spec_info)
                    
                    if status.get("foundation", False):
                        foundation_specs.append(status.get("id"))
                except Exception:
                    continue
        
        if not existing_specs:
            return []
        
        # Build spec list for AI with foundation markers
        specs_list = "\n".join([
            f"- {s['id']}: {s['name']} {'[FOUNDATION]' if s['foundation'] else ''} - {s['summary'][:100]}..."
            for s in existing_specs
        ])
        
        # Build existing dependencies context to avoid cycles
        existing_deps_context = ""
        for s in existing_specs:
            if s['current_deps']:
                existing_deps_context += f"\n- {s['id']} already depends on: {', '.join(s['current_deps'])}"
        
        prompt = f"""Analyze this spec and determine which existing specs it MUST depend on.

SPEC TO ANALYZE:
Name: {spec_name}
Spec ID: {current_spec_id or 'unknown'}
Content:
{spec_content[:2000]}

EXISTING SPECS:
{specs_list}

EXISTING DEPENDENCIES (to avoid cycles):{existing_deps_context}

CRITICAL RULES:
1. FOUNDATION specs (marked [FOUNDATION]) should NOT be depended upon by infrastructure/setup specs
2. NEVER create circular dependencies - if spec A already depends on B, then B cannot depend on A
3. Infrastructure/setup specs should have NO dependencies or only depend on other foundation specs
4. A dependency means "MUST be implemented FIRST" - not just "is related to"
5. Consider the DIRECTION of dependency:
   - Browser Module is a foundation - others depend ON it
   - Navigation, Tab Management BUILD ON Browser - they depend on Browser
   - Browser should NOT depend on Navigation (even if it "uses" navigation controls)

FOUNDATION SPEC PATTERNS (should have NO dependencies):
- Infrastructure, setup, environment specs
- Core browser/webview module
- Base authentication framework
- Database setup

DEPENDENT SPEC PATTERNS (should have dependencies):
- Features that use the browser (Reader Mode, Downloads, etc.)
- Features that require auth (Gmail, Dashboard, etc.)
- UI components that need navigation (Sidebar items)

Respond in JSON format:
{{
    "dependencies": ["001", "003"],
    "reasoning": {{
        "001": "Brief reason why this is a TRUE prerequisite",
        "003": "Brief reason"
    }}
}}

If no dependencies (foundation spec), return: {{"dependencies": [], "reasoning": {{}}}}"""

        response = self.ai.query(prompt)
        result = self.ai._extract_json(response)
        
        if not result:
            return []
        
        dependencies = result.get("dependencies", [])
        reasoning = result.get("reasoning", {})
        
        # Validate that dependencies exist
        valid_ids = {s["id"] for s in existing_specs}
        valid_deps = [d for d in dependencies if d in valid_ids]
        
        # CRITICAL: Filter out dependencies that would create cycles
        # If spec X already depends on current spec, we cannot depend on X
        if current_spec_id:
            specs_depending_on_us = set()
            for s in existing_specs:
                if current_spec_id in s.get('current_deps', []):
                    specs_depending_on_us.add(s['id'])
            
            # Remove any that would create a cycle
            filtered_deps = []
            for dep_id in valid_deps:
                if dep_id in specs_depending_on_us:
                    print(f"   ⚠️  Skipping {dep_id} (would create cycle - it already depends on us)")
                else:
                    filtered_deps.append(dep_id)
            valid_deps = filtered_deps
        
        if valid_deps and reasoning:
            Console.log("🔗 Inferred dependencies:")
            for dep_id in valid_deps:
                reason = reasoning.get(dep_id, "Related functionality")
                print(f"   • {dep_id}: {reason}")
        
        return valid_deps
    
    def _validate_dependencies(self, spec_id: str) -> dict:
        """Check if a spec's dependencies are met (completed)"""
        # Find spec
        spec_dir = None
        for d in self.context.specs_dir.glob(f"{spec_id}-*"):
            spec_dir = d
            break
        
        if not spec_dir:
            return {"valid": False, "error": "Spec not found"}
        
        status_file = spec_dir / "status.json"
        if not status_file.exists():
            return {"valid": True, "dependencies": [], "unmet": []}
        
        status = json.loads(status_file.read_text())
        dependencies = status.get("dependencies", [])
        
        if not dependencies:
            return {"valid": True, "dependencies": [], "unmet": []}
        
        # Check each dependency
        unmet = []
        met = []
        
        for dep_id in dependencies:
            dep_status = self._get_spec_status(dep_id)
            if dep_status and dep_status.get("status") == "completed":
                met.append(dep_id)
            else:
                unmet.append({
                    "id": dep_id,
                    "status": dep_status.get("status", "unknown") if dep_status else "not_found"
                })
        
        return {
            "valid": len(unmet) == 0,
            "dependencies": dependencies,
            "met": met,
            "unmet": unmet
        }
    
    def _get_spec_status(self, spec_id: str) -> Optional[dict]:
        """Get status of a spec by ID"""
        for spec_dir in self.context.specs_dir.glob(f"{spec_id}-*"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                return json.loads(status_file.read_text())
        return None
    
    def _show_dependency_warning(self, spec_id: str, validation: dict):
        """Show warning about unmet dependencies"""
        if validation.get("valid", True):
            return
        
        unmet = validation.get("unmet", [])
        if not unmet:
            return
        
        print(f"\n⚠️  DEPENDENCY WARNING for spec {spec_id}")
        print(f"   The following dependencies are not yet completed:\n")
        
        for dep in unmet:
            dep_id = dep.get("id")
            dep_status = dep.get("status", "unknown")
            print(f"   • {dep_id} (status: {dep_status})")
        
        print(f"\n   Consider implementing these first, or proceed if you're sure.")
        print(f"   Run 'speky sequence' to see recommended order.\n")
    
    def cmd_infer_deps(self, spec_id: str = None) -> bool:
        """Infer and update dependencies for specs"""
        if not self._require_init():
            return False
        
        Console.header("🔗 Dependency Inference")
        
        specs_to_process = []
        
        if spec_id:
            # Single spec
            for spec_dir in self.context.specs_dir.glob(f"{spec_id}-*"):
                specs_to_process.append(spec_dir)
                break
            
            if not specs_to_process:
                Console.error(f"Spec {spec_id} not found")
                return False
        else:
            # All specs
            for spec_dir in self.context.specs_dir.glob("*/"):
                status_file = spec_dir / "status.json"
                if status_file.exists():
                    status = json.loads(status_file.read_text())
                    if status.get("status") != "deprecated":
                        specs_to_process.append(spec_dir)
        
        if not specs_to_process:
            Console.warning("No specs found")
            return False
        
        print(f"\nAnalyzing {len(specs_to_process)} spec(s) for dependencies...\n")
        
        updated_count = 0
        
        for spec_dir in specs_to_process:
            status_file = spec_dir / "status.json"
            spec_file = spec_dir / "spec.md"
            
            if not status_file.exists() or not spec_file.exists():
                continue
            
            status = json.loads(status_file.read_text())
            spec_content = spec_file.read_text()
            spec_name = status.get("name", spec_dir.name)
            current_spec_id = status.get("id")
            
            print(f"📋 Analyzing: {current_spec_id}-{self._slugify(spec_name)}")
            
            # Infer dependencies
            inferred = self._infer_dependencies(spec_name, spec_content)
            
            # Filter out self-reference
            inferred = [d for d in inferred if d != current_spec_id]
            
            current_deps = status.get("dependencies", [])
            
            if inferred:
                # Merge with existing (don't remove manually added ones)
                new_deps = list(set(current_deps + inferred))
                
                if new_deps != current_deps:
                    status["dependencies"] = new_deps
                    status["dependencies_inferred_at"] = datetime.now().isoformat()
                    status_file.write_text(json.dumps(status, indent=2))
                    
                    added = set(new_deps) - set(current_deps)
                    if added:
                        Console.success(f"   Added dependencies: {', '.join(added)}")
                        updated_count += 1
                else:
                    print(f"   No new dependencies found")
            else:
                print(f"   No dependencies detected")
        
        print(f"\n✅ Updated {updated_count} spec(s) with new dependencies")
        print(f"\n💡 Run 'speky sequence' to see updated implementation order")
        
        return True
    
    def cmd_mark_foundation(self, spec_id: str) -> bool:
        """Mark a spec as a foundation spec (clears dependencies, prevents future inference)"""
        if not self._require_init():
            return False
        
        # Find spec
        spec_dir = None
        for d in self.context.specs_dir.glob(f"{spec_id}-*"):
            spec_dir = d
            break
        
        if not spec_dir:
            Console.error(f"Spec {spec_id} not found")
            return False
        
        status_file = spec_dir / "status.json"
        if not status_file.exists():
            Console.error(f"Spec {spec_id} has no status.json")
            return False
        
        status = json.loads(status_file.read_text())
        spec_name = status.get("name", spec_id)
        
        # Mark as foundation
        status["foundation"] = True
        status["dependencies"] = []  # Clear all dependencies
        status["foundation_marked_at"] = datetime.now().isoformat()
        
        status_file.write_text(json.dumps(status, indent=2))
        
        Console.success(f"Marked {spec_id}-{self._slugify(spec_name)} as FOUNDATION spec")
        print(f"   • Dependencies cleared")
        print(f"   • Future infer-deps will skip this spec")
        print(f"   • This spec will appear in 'Foundation Specs' section of sequence")
        
        return True
    
    def cmd_reset_deps(self, spec_id: str = None, all_specs: bool = False) -> bool:
        """Reset dependencies for a spec or all specs"""
        if not self._require_init():
            return False
        
        if not spec_id and not all_specs:
            Console.error("Specify a spec ID or use --all flag")
            return False
        
        specs_to_reset = []
        
        if all_specs:
            if not Console.confirm("Reset dependencies for ALL specs? This cannot be undone.", default=False):
                return False
            for spec_dir in self.context.specs_dir.glob("*/"):
                status_file = spec_dir / "status.json"
                if status_file.exists():
                    specs_to_reset.append(spec_dir)
        else:
            for d in self.context.specs_dir.glob(f"{spec_id}-*"):
                specs_to_reset.append(d)
                break
            
            if not specs_to_reset:
                Console.error(f"Spec {spec_id} not found")
                return False
        
        reset_count = 0
        for spec_dir in specs_to_reset:
            status_file = spec_dir / "status.json"
            if not status_file.exists():
                continue
            
            status = json.loads(status_file.read_text())
            
            if status.get("dependencies"):
                old_deps = status.get("dependencies", [])
                status["dependencies"] = []
                if "dependencies_inferred_at" in status:
                    del status["dependencies_inferred_at"]
                status_file.write_text(json.dumps(status, indent=2))
                
                spec_name = status.get("name", spec_dir.name)
                Console.log(f"Reset: {status.get('id')}-{self._slugify(spec_name)} (was: {', '.join(old_deps)})")
                reset_count += 1
        
        Console.success(f"Reset dependencies for {reset_count} spec(s)")
        print(f"\n💡 Run 'speky infer-deps' to re-infer dependencies with improved algorithm")
        print(f"   Or 'speky mark-foundation <id>' to mark specs that should have NO dependencies")
        
        return True
    
    def cmd_fix_circular_deps(self) -> bool:
        """Interactive fix for circular dependencies"""
        if not self._require_init():
            return False
        
        Console.header("🔄 Circular Dependency Resolution")
        
        # Load all specs
        specs = []
        for spec_dir in self.context.specs_dir.glob("*/"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    if status.get("status") != "deprecated":
                        specs.append({
                            "id": status.get("id"),
                            "name": status.get("name"),
                            "dependencies": status.get("dependencies", []),
                            "dir": spec_dir
                        })
                except Exception:
                    continue
        
        # Detect circular dependencies
        circular_deps = self._detect_circular_dependencies(specs)
        
        if not circular_deps:
            Console.success("No circular dependencies detected!")
            return True
        
        print(f"\n⚠️  Found {len(circular_deps)} circular dependency cycle(s):\n")
        
        for i, cycle in enumerate(circular_deps, 1):
            print(f"   {i}. {' → '.join(cycle)}")
        
        print(f"\n📋 Recommended fixes:\n")
        
        # Analyze each cycle and suggest fixes
        suggested_foundations = set()
        suggested_removals = []
        
        for cycle in circular_deps:
            # Find the spec that should be the "foundation" (typically the first in ID order)
            foundation_candidate = min(cycle[:-1], key=lambda x: int(x) if x.isdigit() else 999)
            suggested_foundations.add(foundation_candidate)
            
            # Find which dependency to remove
            for j, spec_id in enumerate(cycle[:-1]):
                next_id = cycle[j + 1]
                if spec_id == foundation_candidate:
                    # This is the foundation - it should NOT depend on anything in the cycle
                    suggested_removals.append((spec_id, next_id))
        
        print("   🏗️  Mark as FOUNDATION (should have no dependencies):")
        for spec_id in suggested_foundations:
            spec = next((s for s in specs if s['id'] == spec_id), None)
            if spec:
                print(f"      • {spec_id}: {spec.get('name', 'Unknown')}")
        
        print(f"\n   🔗 Dependencies to REMOVE:")
        for from_id, to_id in suggested_removals:
            print(f"      • {from_id} → {to_id}")
        
        print(f"\n❓ Options:")
        print(f"   1. Auto-fix (mark foundations + remove deps)")
        print(f"   2. Manual review (opens each spec for editing)")
        print(f"   3. Cancel")
        
        choice = Console.prompt("Choose option", default="1")
        
        if choice == "1":
            # Auto-fix
            for spec_id in suggested_foundations:
                self.cmd_mark_foundation(spec_id)
            Console.success("Auto-fix complete! Run 'speky sequence' to verify.")
            return True
        elif choice == "2":
            print(f"\n📝 Manual review:")
            print(f"   Edit status.json in each spec directory to fix dependencies:")
            for spec in specs:
                if spec['id'] in suggested_foundations or any(spec['id'] == r[0] for r in suggested_removals):
                    print(f"   • {spec['dir'] / 'status.json'}")
            return True
        else:
            Console.log("Cancelled")
            return False
    
    def cmd_renumber(self, dry_run: bool = False) -> bool:
        """Renumber specs to match implementation order (only unimplemented specs).
        
        This command renumbers specs based on their implementation order (foundation first,
        then by priority and dependencies). Only specs with status 'draft' or 'pending' 
        are renumbered. Completed and in-progress specs keep their original IDs.
        
        Args:
            dry_run: If True, show what would be changed without making changes
        """
        if not self._require_init():
            return False
        
        Console.header("🔢 Renumber Specs")
        
        # Load all specs
        specs = []
        for spec_dir in self.context.specs_dir.glob("*/"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    if status.get("status") != "deprecated":
                        specs.append({
                            "id": status.get("id"),
                            "name": status.get("name"),
                            "status": status.get("status", "draft"),
                            "priority": status.get("priority", "P1"),
                            "dependencies": status.get("dependencies", []),
                            "foundation": status.get("foundation", False),
                            "dir": spec_dir,
                            "status_data": status
                        })
                except Exception as e:
                    Console.warning(f"Skipping {spec_dir.name}: {e}")
                    continue
        
        if not specs:
            Console.warning("No specs found")
            return False
        
        # Separate implemented from unimplemented
        implemented = [s for s in specs if s["status"] in ["completed", "in_progress"]]
        unimplemented = [s for s in specs if s["status"] in ["draft", "pending"]]
        
        if not unimplemented:
            Console.success("All specs are already implemented or in progress. Nothing to renumber.")
            return True
        
        print(f"\n📊 Status:")
        print(f"   Implemented/In-Progress: {len(implemented)} (will keep original IDs)")
        print(f"   Unimplemented: {len(unimplemented)} (will be renumbered)")
        
        # Sort implemented by current ID to preserve their positions
        implemented.sort(key=lambda x: int(x["id"]) if x["id"].isdigit() else 999)
        
        # Sort unimplemented by implementation order (foundation, priority, dependencies)
        # Use topological sort
        ordered_unimplemented = self._topological_sort_specs(unimplemented)
        
        # Separate foundation from non-foundation
        foundation_specs = [s for s in ordered_unimplemented if s.get("foundation", False)]
        non_foundation_specs = [s for s in ordered_unimplemented if not s.get("foundation", False)]
        
        # Sort non-foundation by priority
        p0 = [s for s in non_foundation_specs if s.get("priority") == "P0"]
        p1 = [s for s in non_foundation_specs if s.get("priority") == "P1"]
        p2 = [s for s in non_foundation_specs if s.get("priority") == "P2"]
        p3 = [s for s in non_foundation_specs if s.get("priority") == "P3"]
        
        # Build new order: foundations first, then P0, P1, P2, P3
        new_order = foundation_specs + p0 + p1 + p2 + p3
        
        # Assign new IDs
        # Start from 001, skip IDs used by implemented specs
        used_ids = {s["id"] for s in implemented}
        next_id = 1
        id_mapping = {}  # old_id -> new_id
        
        for spec in new_order:
            # Find next available ID
            while f"{next_id:03d}" in used_ids:
                next_id += 1
            
            new_id = f"{next_id:03d}"
            old_id = spec["id"]
            
            if old_id != new_id:
                id_mapping[old_id] = new_id
                spec["new_id"] = new_id
            else:
                spec["new_id"] = old_id  # No change needed
            
            used_ids.add(new_id)
            next_id += 1
        
        # Check if any changes needed
        if not id_mapping:
            Console.success("Specs are already in correct order. No renumbering needed.")
            return True
        
        # Show preview
        print(f"\n📋 Renumbering Plan:")
        print(f"\n   Changes:")
        for spec in new_order:
            if spec["id"] != spec["new_id"]:
                foundation_marker = " 🏗️" if spec.get("foundation") else ""
                print(f"   {spec['id']} → {spec['new_id']}: {spec['name']}{foundation_marker}")
        
        # Show dependency updates
        deps_to_update = []
        for spec in specs:
            old_deps = spec.get("dependencies", [])
            new_deps = [id_mapping.get(d, d) for d in old_deps]
            if old_deps != new_deps:
                deps_to_update.append({
                    "spec": spec,
                    "old_deps": old_deps,
                    "new_deps": new_deps
                })
        
        if deps_to_update:
            print(f"\n   Dependency Updates:")
            for item in deps_to_update:
                spec = item["spec"]
                print(f"   [{spec['id']}] {spec['name']}:")
                print(f"      Old: {', '.join(item['old_deps'])}")
                print(f"      New: {', '.join(item['new_deps'])}")
        
        # Warnings
        print(f"\n⚠️  Important:")
        print(f"   • This will rename spec directories (e.g., 015-auth → 003-auth)")
        print(f"   • All dependency references will be auto-updated")
        print(f"   • Hardcoded references in spec.md content will NOT be updated")
        print(f"   • Git will see this as file renames (use 'git mv' or 'git add -A')")
        
        if dry_run:
            Console.log("\n[DRY RUN] No changes made. Run without --dry-run to apply.")
            return True
        
        # Confirm
        if not Console.confirm("\nProceed with renumbering?", default=False):
            Console.log("Cancelled")
            return False
        
        # Execute renumbering
        print(f"\n🔄 Renumbering specs...")
        
        # Step 1: Rename directories to temporary names (to avoid conflicts)
        temp_mapping = {}
        for spec in new_order:
            if spec["id"] != spec["new_id"]:
                old_dir = spec["dir"]
                temp_name = f"TEMP_{spec['new_id']}_{self._slugify(spec['name'])}"
                temp_dir = self.context.specs_dir / temp_name
                
                try:
                    old_dir.rename(temp_dir)
                    temp_mapping[spec["id"]] = {
                        "temp_dir": temp_dir,
                        "new_id": spec["new_id"],
                        "name": spec["name"],
                        "status_data": spec["status_data"]
                    }
                except Exception as e:
                    Console.error(f"Failed to rename {old_dir.name}: {e}")
                    # Rollback
                    for old_id, info in temp_mapping.items():
                        info["temp_dir"].rename(self.context.specs_dir / f"{old_id}-{self._slugify(info['name'])}")
                    return False
        
        # Step 2: Rename from temp to final names and update status.json
        for old_id, info in temp_mapping.items():
            temp_dir = info["temp_dir"]
            new_id = info["new_id"]
            name = info["name"]
            status_data = info["status_data"]
            
            final_name = f"{new_id}-{self._slugify(name)}"
            final_dir = self.context.specs_dir / final_name
            
            try:
                # Update status.json with new ID
                status_data["id"] = new_id
                status_data["renumbered_at"] = datetime.now().isoformat()
                status_data["previous_id"] = old_id
                
                # Write updated status
                status_file = temp_dir / "status.json"
                status_file.write_text(json.dumps(status_data, indent=2))
                
                # Rename to final name
                temp_dir.rename(final_dir)
                
                print(f"   ✓ Renamed: {old_id} → {new_id}")
            except Exception as e:
                Console.error(f"Failed to finalize {temp_dir.name}: {e}")
                return False
        
        # Step 3: Update all dependencies in all specs
        print(f"\n🔗 Updating dependencies...")
        for spec_dir in self.context.specs_dir.glob("*/"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    old_deps = status.get("dependencies", [])
                    new_deps = [id_mapping.get(d, d) for d in old_deps]
                    
                    if old_deps != new_deps:
                        status["dependencies"] = new_deps
                        status_file.write_text(json.dumps(status, indent=2))
                        print(f"   ✓ Updated deps in [{status.get('id')}] {status.get('name')}")
                except Exception as e:
                    Console.warning(f"Failed to update deps in {spec_dir.name}: {e}")
        
        # Success
        Console.success(f"\n✅ Renumbered {len(id_mapping)} spec(s)")
        
        print(f"\n📋 Next Steps:")
        print(f"   1. Review changes: speky sequence")
        print(f"   2. Check for hardcoded ID references in spec.md files")
        print(f"   3. Commit changes: git add -A && git commit -m 'Renumber specs to match implementation order'")
        
        return True
    
    # -------------------------------------------------------------------------
    # Import Helper Methods
    # -------------------------------------------------------------------------
    
    def _scan_import_folder(self, folder: Path) -> List[dict]:
        """Scan folder for importable documents"""
        documents = []
        
        # Handle single file
        if folder.is_file():
            documents.append({
                "name": folder.name,
                "path": str(folder),
                "size": f"{folder.stat().st_size / 1024:.1f}KB",
                "type": self._detect_document_type_from_content(folder.read_text())
            })
            return documents
        
        # Scan folder
        for ext in [".md", ".txt", ".pdf", ".docx"]:
            for file_path in folder.rglob(f"*{ext}"):
                if file_path.is_file() and not file_path.name.startswith("."):
                    try:
                        content = file_path.read_text() if ext in [".md", ".txt"] else f"[{ext} file]"
                        documents.append({
                            "name": file_path.name,
                            "path": str(file_path),
                            "size": f"{file_path.stat().st_size / 1024:.1f}KB",
                            "type": self._detect_document_type_from_content(content)
                        })
                    except:
                        pass
        
        return documents
    
    def _detect_document_type_from_content(self, content: str) -> str:
        """Detect document type from content"""
        content_lower = content.lower()
        
        if any(term in content_lower for term in ["user story", "acceptance criteria", "epic", "feature"]):
            return "product"
        elif any(term in content_lower for term in ["architecture", "api", "database", "schema", "technical"]):
            return "technical"
        elif any(term in content_lower for term in ["integration", "external", "third-party", "webhook"]):
            return "integration"
        elif any(term in content_lower for term in ["security", "compliance", "pci", "gdpr", "requirement"]):
            return "security"
        elif any(term in content_lower for term in ["step", "task", "instruction", "implementation", "handoff"]):
            return "implementation"
        else:
            return "general"
    
    def _analyze_documents(self, documents: List[dict], product_context: str) -> str:
        """AI analysis of document content"""
        doc_content = ""
        for doc in documents:
            try:
                content = Path(doc['path']).read_text()
                doc_content += f"\n\n--- {doc['name']} (Type: {doc.get('type', 'unknown')}) ---\n{content[:2000]}"
            except:
                pass
        
        prompt = Prompts.analyze_external_documents(doc_content, product_context)
        analysis = self.ai.query(prompt)
        return analysis or "Analysis failed"
    
    def _propose_specs_from_analysis(self, analysis: str) -> List[dict]:
        """Generate spec proposals from analysis"""
        tech_stack = self.context.data.get("tech_stack", {})
        prompt = Prompts.propose_specs_from_analysis(analysis, tech_stack)
        response = self.ai.query(prompt)
        
        if not response:
            return []
        
        # Parse spec proposals from response
        specs = []
        current_spec = {}
        
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("SPEC:"):
                if current_spec:
                    specs.append(current_spec)
                current_spec = {"name": line.replace("SPEC:", "").strip()}
            elif line.startswith("SCOPE:"):
                current_spec["scope"] = line.replace("SCOPE:", "").strip()
            elif line.startswith("ESTIMATE:"):
                current_spec["estimate"] = line.replace("ESTIMATE:", "").strip()
            elif line.startswith("SOURCE:"):
                current_spec["source"] = line.replace("SOURCE:", "").strip()
        
        if current_spec:
            specs.append(current_spec)
        
        return specs
    
    def _interactive_spec_review(self, proposed_specs: List[dict]) -> List[dict]:
        """Interactive review of proposed specs before import"""
        reviewed_specs = []
        i = 1
        
        while i <= len(proposed_specs):
            spec = proposed_specs[i - 1]
            
            print(f"\n{'='*60}")
            print(f"Proposed Spec {i}/{len(proposed_specs)}: {spec.get('name', 'Unnamed')}")
            print(f"{'='*60}")
            
            print(f"\n📝 Scope: {spec.get('scope', 'Not specified')}")
            print(f"⏱️  Estimate: {spec.get('estimate', 'Unknown')}")
            if spec.get('source'):
                print(f"📄 Source: {spec.get('source')}")
            
            choice = Console.prompt(
                "Action: [a]ccept [m]odify [s]plit [r]emove [q]uestion [n]ext [p]revious",
                default="a"
            ).lower()
            
            if choice == "a":
                reviewed_specs.append(spec)
                i += 1
            elif choice == "m":
                spec = self._modify_proposed_spec(spec)
                proposed_specs[i - 1] = spec
                reviewed_specs.append(spec)
                i += 1
            elif choice == "s":
                split_specs = self._split_spec(spec)
                reviewed_specs.extend(split_specs)
                i += 1
            elif choice == "r":
                Console.log("Spec removed")
                i += 1
            elif choice == "q":
                question = Console.prompt("Your question")
                answer = self._handle_spec_question(spec, question)
                print(f"\n🤖 {answer}\n")
            elif choice == "n":
                # Skip without adding to reviewed_specs
                i += 1
            elif choice == "p":
                i = max(1, i - 1)
        
        return reviewed_specs
    
    def _modify_proposed_spec(self, spec: dict) -> dict:
        """Allow user to modify a proposed spec"""
        print(f"\nModifying: {spec.get('name')}")
        print("   1. Change name")
        print("   2. Reduce scope")
        print("   3. Expand scope")
        print("   4. Change estimate")
        print("   5. Add notes")
        
        choice = Console.prompt("What to modify", default="1")
        
        if choice == "1":
            spec["name"] = Console.prompt("New name", default=spec.get("name", ""))
        elif choice == "2":
            spec["scope"] = Console.prompt("Reduced scope", default=spec.get("scope", ""))
        elif choice == "3":
            spec["scope"] = Console.prompt("Expanded scope", default=spec.get("scope", ""))
        elif choice == "4":
            spec["estimate"] = Console.prompt("New estimate", default=spec.get("estimate", ""))
        elif choice == "5":
            spec["notes"] = Console.prompt("Add notes")
        
        return spec
    
    def _split_spec(self, spec: dict) -> List[dict]:
        """Split a spec into multiple smaller specs with AI suggestions"""
        print(f"\nSplitting: {spec.get('name')}")
        
        # Get number of splits with error handling
        while True:
            try:
                count_input = Console.prompt("How many specs to split into", default="2")
                count = int(count_input)
                if count < 2:
                    Console.warning("Must split into at least 2 specs")
                    continue
                break
            except ValueError:
                Console.warning(f"Invalid input: '{count_input}'. Please enter a number.")
        
        # Get AI suggestions for split
        Console.section("Getting AI Suggestions", "Generating split recommendations")
        suggestions = self._get_split_suggestions(spec, count)
        
        split_specs = []
        for i in range(count):
            print(f"\n📌 Spec {i+1}/{count}")
            
            # Show AI suggestion if available
            if i < len(suggestions):
                suggestion = suggestions[i]
                print(f"   AI Suggestion:")
                print(f"   • Name: {suggestion.get('name', 'N/A')}")
                print(f"   • Scope: {suggestion.get('scope', 'N/A')}")
                print(f"   • Estimate: {suggestion.get('estimate', 'N/A')}")
                print()
                
                # Ask if user wants to use suggestion
                if Console.confirm("Use this suggestion?", default=True):
                    split_specs.append({
                        "name": suggestion.get('name'),
                        "scope": suggestion.get('scope'),
                        "estimate": suggestion.get('estimate'),
                        "source": spec.get("source")
                    })
                    continue
            
            # Manual entry
            name = Console.prompt(f"Name for spec {i+1}")
            scope = Console.prompt(f"Scope for spec {i+1}")
            estimate = Console.prompt(f"Estimate for spec {i+1}")
            split_specs.append({
                "name": name,
                "scope": scope,
                "estimate": estimate,
                "source": spec.get("source")
            })
        
        return split_specs
    
    def _get_split_suggestions(self, spec: dict, count: int) -> List[dict]:
        """Get AI suggestions for splitting a spec"""
        prompt = f"""A user wants to split this spec into {count} smaller, independent specs.

ORIGINAL SPEC:
Name: {spec.get('name')}
Scope: {spec.get('scope')}
Estimate: {spec.get('estimate')}

Provide {count} split specs that:
1. Are independent and can be implemented separately
2. Each focus on a specific aspect of the original
3. Are realistic in scope and effort

Format each as:
SPEC <number>:
Name: <name>
Scope: <2-3 sentence scope>
Estimate: <hours or time estimate>
---

Be concise and practical."""
        
        response = self.ai.query(prompt)
        if not response:
            return []
        
        # Parse response into structured suggestions
        suggestions = []
        specs = response.split("---")
        
        for spec_text in specs:
            if "Name:" in spec_text and "Scope:" in spec_text:
                try:
                    name_line = [l for l in spec_text.split("\n") if "Name:" in l][0]
                    scope_line = [l for l in spec_text.split("\n") if "Scope:" in l][0]
                    estimate_line = [l for l in spec_text.split("\n") if "Estimate:" in l][0]
                    
                    suggestions.append({
                        "name": name_line.split("Name:", 1)[1].strip(),
                        "scope": scope_line.split("Scope:", 1)[1].strip(),
                        "estimate": estimate_line.split("Estimate:", 1)[1].strip()
                    })
                except (IndexError, ValueError):
                    continue
        
        return suggestions
    
    def _handle_spec_question(self, spec: dict, question: str) -> str:
        """AI answers user question about proposed spec"""
        prompt = f"""A user is reviewing a proposed spec and has a question.

SPEC: {spec.get('name')}
SCOPE: {spec.get('scope')}
ESTIMATE: {spec.get('estimate')}

USER QUESTION: {question}

Provide a helpful, concise answer (2-3 sentences max)."""
        
        return self.ai.query(prompt) or "Unable to answer question"
    
    def _create_spec_from_import(self, spec_proposal: dict, phase: str) -> Optional[str]:
        """Create a spec from import proposal"""
        # Get next spec ID
        next_id = self._next_item_number(self.context.specs_dir)
        spec_id = f"{next_id:03d}"
        
        # Create spec directory
        slug = self._slugify(spec_proposal.get("name", "spec"))
        spec_dir = self.context.specs_dir / f"{spec_id}-{slug}"
        spec_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate spec content
        spec_content = f"""# {spec_proposal.get('name', 'Unnamed')}

## Overview
{spec_proposal.get('scope', 'No description')}

## MVP Scope
- {spec_proposal.get('scope', 'Not specified')}

## User Stories
- As a user, I want to [action], so that [benefit]
  - Acceptance: [criteria]

## Requirements

### Functional Requirements
- Essential behaviors only

### Non-Functional Requirements
- Only if critical

## Out of Scope
- To be determined during planning

## Open Questions
- Specific decisions needed before implementation

## Technical Approach
- Key libraries/services
- Main architectural decisions

## Import Source
- Phase: {phase}
- Source: {spec_proposal.get('source', 'Unknown')}
"""
        
        (spec_dir / "spec.md").write_text(spec_content)
        
        # Create status with priority and dependencies
        status = {
            "id": spec_id,
            "name": spec_proposal.get("name", "Unnamed"),
            "status": ItemStatus.DRAFT.value,
            "created": datetime.now().isoformat(),
            "source": "external_import",
            "import_source": {
                "phase": phase,
                "document": spec_proposal.get("source", "Unknown")
            },
            "priority": spec_proposal.get("priority", "P1"),
            "dependencies": spec_proposal.get("dependencies", [])
        }
        (spec_dir / "status.json").write_text(json.dumps(status, indent=2))
        
        # Update context
        data = self.context.data
        data["specs"].append({"id": spec_id, "name": spec_proposal.get("name"), "dir": str(spec_dir.name)})
        self.context.save(data)
        
        return spec_id
    
    def _detect_mismatches(self, spec_file: Path, import_dir: Path) -> List[dict]:
        """Detect mismatches between spec and code"""
        spec_content = spec_file.read_text()
        product_context = self.context.get_product_context()
        relevant_code = self._get_relevant_code_for_spec(spec_content)
        
        prompt = f"""Compare this spec with the actual implementation and identify mismatches.

SPECIFICATION:
{spec_content[:2000]}

ACTUAL CODE:
{relevant_code[:2000] if relevant_code else "No code found"}

PRODUCT CONTEXT:
{product_context[:500]}

For each mismatch, respond in this format:
MISMATCH_TYPE: <type>
DESCRIPTION: <what differs>
IMPORT_CONTENT: <what import says>
CODE_CONTENT: <what code does>
---

If no mismatches, respond with: NO_MISMATCHES"""
        
        response = self.ai.query(prompt)
        
        if not response or "NO_MISMATCHES" in response:
            return []
        
        # Parse mismatches
        mismatches = []
        current = {}
        
        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("MISMATCH_TYPE:"):
                if current:
                    mismatches.append(current)
                current = {"type": line.replace("MISMATCH_TYPE:", "").strip()}
            elif line.startswith("DESCRIPTION:"):
                current["description"] = line.replace("DESCRIPTION:", "").strip()
            elif line.startswith("IMPORT_CONTENT:"):
                current["import_content"] = line.replace("IMPORT_CONTENT:", "").strip()
            elif line.startswith("CODE_CONTENT:"):
                current["code_content"] = line.replace("CODE_CONTENT:", "").strip()
        
        if current:
            mismatches.append(current)
        
        return mismatches
    
    def _interactive_mismatch_resolution(self, mismatch: dict) -> Optional[dict]:
        """Interactively resolve a mismatch"""
        print(f"\n📋 Description: {mismatch.get('description', '')}")
        
        choice = Console.prompt(
            "Action: [u]pdate code [u]pdate spec [q]uestion [s]kip [c]ancel",
            default="q"
        ).lower()
        
        if choice == "u":
            action = Console.prompt("Update [c]ode or [s]pec", default="c").lower()
            return {
                "type": mismatch.get("type"),
                "action": f"update_{action}",
                "description": mismatch.get("description")
            }
        elif choice == "q":
            question = Console.prompt("Your question")
            answer = self._ask_clarifying_questions(mismatch, question)
            print(f"\n🤖 {answer}\n")
            return self._interactive_mismatch_resolution(mismatch)
        elif choice == "s":
            return None
        elif choice == "c":
            return None
        
        return None
    
    def _ask_clarifying_questions(self, mismatch: dict, user_question: str) -> str:
        """AI asks clarifying questions for mismatch resolution"""
        prompt = f"""A user is resolving a mismatch between imported docs and code.

MISMATCH: {mismatch.get('type')}
DESCRIPTION: {mismatch.get('description')}
IMPORT SAYS: {mismatch.get('import_content')}
CODE DOES: {mismatch.get('code_content')}

USER QUESTION: {user_question}

Provide analysis and recommendations (2-3 sentences max)."""
        
        return self.ai.query(prompt) or "Unable to analyze"
    
    def _apply_resolution(self, resolution: dict, import_dir: Path = None):
        """Apply resolution to docs/specs - handles priority-based spec creation"""
        action = resolution.get("action", "")
        priority = resolution.get("priority", "P3")
        
        if action == "p0_blocker":
            # P0 BLOCKER - Create spec immediately with full context
            spec_name = resolution.get("spec_name", "Unnamed")
            Console.section(f"🚨 Creating P0 Spec: {spec_name}")
            
            # Generate spec content with full context
            spec_content = self._generate_priority_spec(resolution, "P0")
            
            # Create the spec
            created = self._create_priority_spec(spec_name, spec_content, resolution)
            if created:
                Console.success(f"✅ P0 Spec created: {created}")
                Console.warning("⚠️  Implement this IMMEDIATELY after current feature!")
            
        elif action == "p1_high":
            # P1 HIGH - Create spec with context, queue for next
            spec_name = resolution.get("spec_name", "Unnamed")
            Console.section(f"⚡ Creating P1 Spec: {spec_name}")
            
            spec_content = self._generate_priority_spec(resolution, "P1")
            created = self._create_priority_spec(spec_name, spec_content, resolution)
            if created:
                Console.success(f"✅ P1 Spec created: {created}")
                Console.log("📋 Queued as next priority after current work")
            
        elif action == "p2_medium":
            # P2 MEDIUM - Add to backlog with details
            backlog_file = self.context.speky_dir / "backlog.json"
            backlog = []
            if backlog_file.exists():
                backlog = json.loads(backlog_file.read_text())
            
            backlog.append({
                "name": resolution.get("spec_name", "Unnamed"),
                "description": resolution.get("description", ""),
                "suggestion": resolution.get("suggestion", ""),
                "type": resolution.get("type", "CODE_BEHIND"),
                "priority": "P2",
                "source_spec": resolution.get("source_spec", ""),
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            })
            
            backlog_file.write_text(json.dumps(backlog, indent=2))
            Console.log(f"📋 P2 added to backlog: {resolution.get('spec_name')}")
            
        elif action == "p3_low":
            # P3 LOW - Quick note in backlog
            backlog_file = self.context.speky_dir / "backlog.json"
            backlog = []
            if backlog_file.exists():
                backlog = json.loads(backlog_file.read_text())
            
            backlog.append({
                "name": resolution.get("description", "Unnamed")[:50],
                "description": resolution.get("note", resolution.get("description", "")),
                "type": "note",
                "priority": "P3",
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            })
            
            backlog_file.write_text(json.dumps(backlog, indent=2))
            Console.log(f"📝 P3 noted in backlog")
            
        # Legacy support for old action names
        elif action == "detailed_spec":
            backlog_file = self.context.speky_dir / "backlog.json"
            backlog = []
            if backlog_file.exists():
                backlog = json.loads(backlog_file.read_text())
            
            backlog.append({
                "name": resolution.get("future_spec_name", "Unnamed"),
                "description": resolution.get("description", ""),
                "type": resolution.get("type", "CODE_BEHIND"),
                "priority": "P2",
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            })
            
            backlog_file.write_text(json.dumps(backlog, indent=2))
            Console.log(f"Added to backlog: {resolution.get('future_spec_name')}")
            
        elif action == "short_spec":
            backlog_file = self.context.speky_dir / "backlog.json"
            backlog = []
            if backlog_file.exists():
                backlog = json.loads(backlog_file.read_text())
            
            backlog.append({
                "name": resolution.get("description", "Unnamed")[:50],
                "description": resolution.get("note", resolution.get("description", "")),
                "type": "short_note",
                "priority": "P3",
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            })
            
            backlog_file.write_text(json.dumps(backlog, indent=2))
            Console.log(f"Added short note to backlog")
            
        elif "update_spec" in action:
            Console.log(f"Would update spec: {resolution.get('description')}")
        elif "update_code" in action:
            Console.log(f"Would update code: {resolution.get('description')}")
    
    def _generate_priority_spec(self, resolution: dict, priority: str) -> str:
        """Generate spec content for P0/P1 priority items with full context"""
        
        spec_name = resolution.get("spec_name", "Unnamed")
        description = resolution.get("description", "")
        suggestion = resolution.get("suggestion", "")
        source_spec = resolution.get("source_spec", "")
        depends_on = resolution.get("depends_on", "")
        
        # Use AI to generate a proper spec
        prompt = f"""Generate a focused, implementable spec for this priority item.

ITEM NAME: {spec_name}
PRIORITY: {priority} {"(BLOCKER - must fix immediately)" if priority == "P0" else "(HIGH - next in queue)"}
DRIFT DESCRIPTION: {description}
SUGGESTED FIX: {suggestion}
SOURCE SPEC: {source_spec}
DEPENDS ON: Spec {depends_on}

{"BLOCKER REASON: " + resolution.get("why_blocker", "") if priority == "P0" else ""}
{"ACCEPTANCE CRITERIA: " + resolution.get("acceptance", "") if priority == "P1" else ""}

Generate a spec in this format:

# {spec_name}

## Overview
[1-2 sentence description of what needs to be done]

## Priority
{priority} - [reason]

## Context
- Source: {source_spec}
- Depends on: Spec {depends_on} (complete this first)
- Drift type: {resolution.get("type", "CODE_BEHIND")}

## Problem
[What's missing or broken - from the drift description]

## Solution
[How to fix it - from the suggestion]

## Acceptance Criteria
- [ ] [Specific, testable criteria]
- [ ] [Another criteria]

## Technical Approach
[Brief technical guidance based on the suggestion]

## Out of Scope
- Anything not directly related to this fix

Keep it focused and actionable. This should be implementable in 1-4 hours."""

        return self.ai.query(prompt) or f"""# {spec_name}

## Overview
{description}

## Priority
{priority}

## Context
- Source: {source_spec}
- Depends on: Spec {depends_on}

## Problem
{description}

## Solution
{suggestion}

## Acceptance Criteria
- [ ] Implementation matches requirements
- [ ] Tests pass

## Out of Scope
- Unrelated changes
"""
    
    def _create_priority_spec(self, name: str, content: str, resolution: dict) -> str:
        """Create a spec file for P0/P1 priority items"""
        
        # Get next spec ID
        existing_specs = list(self.context.specs_dir.glob("*/"))
        next_id = 1
        for spec_dir in existing_specs:
            try:
                spec_id = int(spec_dir.name.split("-")[0])
                next_id = max(next_id, spec_id + 1)
            except (ValueError, IndexError):
                pass
        
        spec_id = f"{next_id:03d}"
        
        # Create spec directory
        safe_name = name.lower().replace(" ", "-")[:30]
        spec_dir = self.context.specs_dir / f"{spec_id}-{safe_name}"
        spec_dir.mkdir(parents=True, exist_ok=True)
        
        # Write spec file
        spec_file = spec_dir / "spec.md"
        spec_file.write_text(content)
        
        # Write status file
        status = {
            "id": spec_id,
            "name": name,
            "status": "draft",
            "priority": resolution.get("priority", "P1"),
            "created": datetime.now().isoformat(),
            "source": "drift_resolution",
            "depends_on": resolution.get("depends_on", ""),
            "source_spec": resolution.get("source_spec", "")
        }
        status_file = spec_dir / "status.json"
        status_file.write_text(json.dumps(status, indent=2))
        
        return f"{spec_id}-{safe_name}"
    
    def _generate_roadmap(self, spec_ids: List[str], proposals: List[dict]) -> str:
        """Generate implementation roadmap"""
        roadmap = "# Implementation Roadmap\n\n"
        
        for i, (spec_id, proposal) in enumerate(zip(spec_ids, proposals), 1):
            roadmap += f"## {i}. {proposal.get('name', 'Unnamed')} ({spec_id})\n\n"
            roadmap += f"**Scope**: {proposal.get('scope', 'Not specified')}\n\n"
            roadmap += f"**Estimate**: {proposal.get('estimate', 'Unknown')}\n\n"
            if proposal.get('notes'):
                roadmap += f"**Notes**: {proposal.get('notes')}\n\n"
            roadmap += "---\n\n"
        
        return roadmap

    # -------------------------------------------------------------------------
    # Command: sequence
    # -------------------------------------------------------------------------
    def cmd_sequence(self, export: bool = False) -> bool:
        """Show unified implementation roadmap with dependency analysis"""
        if not self._require_init():
            return False
        
        Console.header("📋 Spec Sequence & Dependency Analysis")
        
        # Load all specs
        specs = []
        foundation_count = 0
        for spec_dir in self.context.specs_dir.glob("*/"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                    # Skip deprecated specs
                    if status.get("status") == "deprecated":
                        continue
                    is_foundation = status.get("foundation", False)
                    if is_foundation:
                        foundation_count += 1
                    specs.append({
                        "id": status.get("id"),
                        "name": status.get("name"),
                        "priority": status.get("priority", "P1"),
                        "dependencies": status.get("dependencies", []),
                        "source": status.get("source", "unknown"),
                        "status": status.get("status", "draft"),
                        "dir": spec_dir.name,
                        "foundation": is_foundation
                    })
                except Exception:
                    continue
        
        if not specs:
            Console.warning("No specs found. Create specs first with 'speky spec' or 'speky poc-import'")
            return False
        
        # Sort by ID
        specs.sort(key=lambda x: x.get("id", "999"))
        
        # Build dependency graph
        spec_by_id = {s["id"]: s for s in specs}
        
        # Detect circular dependencies
        circular_deps = self._detect_circular_dependencies(specs)
        
        # Calculate implementation order (topological sort)
        ordered_specs = self._topological_sort_specs(specs)
        
        # Group by priority
        p0_specs = [s for s in ordered_specs if s.get("priority") == "P0"]
        p1_specs = [s for s in ordered_specs if s.get("priority") == "P1"]
        p2_specs = [s for s in ordered_specs if s.get("priority") == "P2"]
        p3_specs = [s for s in ordered_specs if s.get("priority") == "P3"]
        
        # Display
        print(f"\n📊 Total Specs: {len(specs)}")
        print(f"   🏗️  Foundation: {foundation_count}")
        print(f"   P0 (Blocker): {len(p0_specs)}")
        print(f"   P1 (High): {len(p1_specs)}")
        print(f"   P2 (Medium): {len(p2_specs)}")
        print(f"   P3 (Low): {len(p3_specs)}")
        
        # Show phase information if phases exist
        phases = self._get_all_phases()
        current_phase_blocked_info = None
        
        if phases:
            roadmap = self._load_roadmap()
            current_phase = roadmap.get("current_phase") if roadmap else None
            
            Console.section("📅 Phases")
            for phase in phases:
                phase_id = phase.get("id", phase.get("_dir"))
                phase_name = phase.get("name", "Unnamed")
                phase_status = phase.get("status", "not_started")
                phase_specs = [s.get("id") if isinstance(s, dict) else s for s in phase.get("specs", [])]
                
                # Progress
                progress = self._calculate_phase_progress(phase)
                pct = progress["specs_percent"]
                
                # Status icon
                status_icons = {"not_started": "⬜", "in_progress": "🔄", "complete": "✅"}
                icon = status_icons.get(phase_status, "⬜")
                
                is_current = phase_id == current_phase
                marker = " ◀ CURRENT" if is_current else ""
                
                print(f"   {icon} {phase_id}: {phase_name} ({pct}%){marker}")
                print(f"      Specs: {', '.join(phase_specs[:5])}{' ...' if len(phase_specs) > 5 else ''}")
                
                # Check if current phase is blocked
                if is_current and phase_status == "in_progress":
                    blocked_specs = self._check_phase_blocking(phase, specs)
                    if blocked_specs:
                        current_phase_blocked_info = {
                            "phase_id": phase_id,
                            "phase_name": phase_name,
                            "blocked_specs": blocked_specs
                        }
            
            print(f"\n   💡 View phases: speky phases list")
            print(f"   💡 Start next: speky phases start <phase-id>")
            
            # Show phase blocking warning if detected
            if current_phase_blocked_info:
                print(f"\n⚠️  PHASE CONFIGURATION ISSUE DETECTED")
                print(f"   Phase: {current_phase_blocked_info['phase_name']}")
                print(f"   Problem: Some specs in this phase have dependencies OUTSIDE the phase")
                print(f"\n   Blocked specs:")
                for spec_info in current_phase_blocked_info["blocked_specs"][:3]:
                    print(f"   ⛔ {spec_info['id']}: {spec_info['name']}")
                    if spec_info["deps_outside_phase"]:
                        outside_deps = ", ".join(spec_info["deps_outside_phase"])
                        print(f"      Dependencies outside phase: {outside_deps}")
                    if spec_info["unmet_deps"]:
                        unmet = ", ".join(spec_info["unmet_deps"])
                        print(f"      Unmet dependencies: {unmet}")
                
                if len(current_phase_blocked_info["blocked_specs"]) > 3:
                    print(f"   ... and {len(current_phase_blocked_info['blocked_specs']) - 3} more")
                
                print(f"\n   💡 FIX OPTIONS:")
                print(f"   1. Implement dependencies first (follow sequence order below)")
                print(f"   2. Add missing dependencies to phase manifest")
                print(f"   3. Remove blocked specs from phase")
                print(f"   4. Run: speky phases validate {current_phase_blocked_info['phase_id']}")
        elif len(specs) >= 5:
            print(f"\n   💡 You have {len(specs)} specs. Consider: speky phases suggest")
        
        # Show circular dependencies warning with actionable fix
        if circular_deps:
            print(f"\n⚠️  CIRCULAR DEPENDENCIES DETECTED:")
            for cycle in circular_deps[:5]:  # Show first 5
                print(f"   🔄 {' → '.join(cycle)}")
            if len(circular_deps) > 5:
                print(f"   ... and {len(circular_deps) - 5} more cycles")
            print(f"\n   🔧 TO FIX: Run 'speky fix-circular-deps' for interactive resolution")
            print(f"   📝 OR manually mark foundation specs: 'speky mark-foundation <id>'")
        
        # Show implementation order
        Console.section("📋 Recommended Implementation Order")
        
        order_num = 1
        
        # Separate foundation specs from priority groups
        foundation_list = [s for s in ordered_specs if s.get("foundation", False)]
        non_foundation = [s for s in ordered_specs if not s.get("foundation", False)]
        
        # Re-group non-foundation by priority
        p0_non_foundation = [s for s in non_foundation if s.get("priority") == "P0"]
        p1_non_foundation = [s for s in non_foundation if s.get("priority") == "P1"]
        p2_non_foundation = [s for s in non_foundation if s.get("priority") == "P2"]
        p3_non_foundation = [s for s in non_foundation if s.get("priority") == "P3"]
        
        # Helper to format spec line with clear Step vs ID distinction
        def format_spec_line(spec, step_num, show_deps=True):
            status_icon = "✅" if spec.get("status") == "completed" else "⬜"
            deps = spec.get("dependencies", [])
            dep_str = f" → needs: {', '.join(deps)}" if (deps and show_deps) else ""
            # Format: "Step N. [status] ID: name (source) → needs: X, Y"
            return f"   Step {step_num:2d}. {status_icon} [{spec['id']}] {self._slugify(spec['name'])}{dep_str}"
        
        # FOUNDATION specs first (these should be implemented before anything else)
        if foundation_list:
            print("\n🏗️  FOUNDATION (Implement FIRST - no dependencies):")
            for spec in foundation_list:
                print(format_spec_line(spec, order_num, show_deps=False))
                order_num += 1
        
        # P0 next (but only non-foundation)
        if p0_non_foundation:
            print("\n🚨 P0 - BLOCKERS (Implement immediately after foundations):")
            for spec in p0_non_foundation:
                print(format_spec_line(spec, order_num))
                order_num += 1
        
        # P1 next
        if p1_non_foundation:
            print("\n⚡ P1 - HIGH PRIORITY (Core features):")
            for spec in p1_non_foundation:
                print(format_spec_line(spec, order_num))
                order_num += 1
        
        # P2
        if p2_non_foundation:
            print("\n📋 P2 - MEDIUM PRIORITY (Important but not critical):")
            for spec in p2_non_foundation:
                print(format_spec_line(spec, order_num))
                order_num += 1
        
        # P3
        if p3_non_foundation:
            print("\n📝 P3 - LOW PRIORITY (Nice-to-have):")
            for spec in p3_non_foundation:
                print(format_spec_line(spec, order_num))
                order_num += 1
        
        # Note about Step vs ID
        print(f"\n   📌 Note: 'Step N' = implementation order, '[ID]' = spec identifier")
        
        # Show dependency tree
        Console.section("🌳 Dependency Tree")
        
        # Find root specs (no dependencies)
        # Foundation specs are those marked explicitly OR have no dependencies
        foundation_specs = [s for s in specs if s.get("foundation", False)]
        root_specs = [s for s in specs if not s.get("dependencies") and not s.get("foundation")]
        dependent_specs = [s for s in specs if s.get("dependencies") and not s.get("foundation")]
        
        if foundation_specs:
            print("\n🏗️  FOUNDATION Specs (marked, no deps allowed):")
            for spec in foundation_specs:
                status_icon = "✅" if spec.get("status") == "completed" else "⬜"
                print(f"   {status_icon} {spec['id']}-{self._slugify(spec['name'])} [START HERE]")
        
        if root_specs:
            print("\n📌 Root Specs (no dependencies yet):")
            for spec in root_specs:
                print(f"   • {spec['id']}-{self._slugify(spec['name'])}")
        
        if dependent_specs:
            print("\n🔗 Dependent Specs:")
            for spec in dependent_specs:
                deps = spec.get("dependencies", [])
                print(f"   • {spec['id']}-{self._slugify(spec['name'])} → depends on: {', '.join(deps)}")
        
        # Show specs by source
        Console.section("📦 Specs by Source")
        
        sources = {}
        for spec in specs:
            source = spec.get("source", "unknown")
            if source not in sources:
                sources[source] = []
            sources[source].append(spec)
        
        for source, source_specs in sources.items():
            print(f"\n{source}:")
            for spec in source_specs:
                print(f"   • {spec['id']}-{self._slugify(spec['name'])} [{spec['priority']}]")
        
        # Export option
        if export:
            roadmap_file = self.context.speky_dir / "roadmap.md"
            roadmap_content = self._generate_sequence_roadmap(ordered_specs, circular_deps)
            roadmap_file.write_text(roadmap_content)
            Console.success(f"Roadmap exported to: {roadmap_file}")
        
        # Next steps
        print(f"\n📋 Next Steps:")
        
        # Prioritize: 1) incomplete foundations, 2) incomplete specs with met deps
        next_spec = None
        
        # First check incomplete foundations (they have no deps, so always ready)
        for spec in foundation_list:
            if spec.get("status") != "completed":
                next_spec = spec
                break
        
        # If all foundations done, find next non-foundation with met deps
        if not next_spec:
            for spec in non_foundation:
                if spec.get("status") != "completed":
                    deps = spec.get("dependencies", [])
                    deps_met = all(
                        spec_by_id.get(d, {}).get("status") == "completed"
                        for d in deps
                    )
                    if deps_met:
                        next_spec = spec
                        break
        
        if next_spec:
            is_foundation = next_spec.get("foundation", False)
            marker = " (FOUNDATION - start here!)" if is_foundation else ""
            print(f"   1. Run: speky plan {next_spec['id']}{marker}")
            print(f"   2. Run: speky implement {next_spec['id']}")
        else:
            if circular_deps:
                print("   ⚠️  Circular dependencies blocking progress!")
                print("   Run: speky fix-circular-deps")
            else:
                print("   All specs are either completed or have unmet dependencies!")
        
        print(f"\n💡 Tips:")
        print(f"   • Mark foundation specs: speky mark-foundation <id>")
        print(f"   • Reset dependencies: speky reset-deps <id>")
        print(f"   • Fix circular deps: speky fix-circular-deps")
        print(f"   • Export roadmap: speky sequence --export")
        
        return True
    
    def _detect_circular_dependencies(self, specs: List[dict]) -> List[List[str]]:
        """Detect circular dependencies in specs"""
        spec_by_id = {s["id"]: s for s in specs}
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(spec_id: str, path: List[str]) -> bool:
            if spec_id in rec_stack:
                # Found cycle
                cycle_start = path.index(spec_id)
                cycle = path[cycle_start:] + [spec_id]
                cycles.append(cycle)
                return True
            
            if spec_id in visited:
                return False
            
            visited.add(spec_id)
            rec_stack.add(spec_id)
            
            spec = spec_by_id.get(spec_id, {})
            for dep in spec.get("dependencies", []):
                if dep in spec_by_id:
                    dfs(dep, path + [spec_id])
            
            rec_stack.remove(spec_id)
            return False
        
        for spec in specs:
            if spec["id"] not in visited:
                dfs(spec["id"], [])
        
        return cycles
    
    def _topological_sort_specs(self, specs: List[dict]) -> List[dict]:
        """Sort specs by dependencies (topological sort) then by priority"""
        spec_by_id = {s["id"]: s for s in specs}
        in_degree = {s["id"]: 0 for s in specs}
        
        # Calculate in-degrees
        for spec in specs:
            for dep in spec.get("dependencies", []):
                if dep in in_degree:
                    in_degree[spec["id"]] += 1
        
        # Priority order: P0 > P1 > P2 > P3
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        
        # Start with specs that have no dependencies
        queue = [s for s in specs if in_degree[s["id"]] == 0]
        queue.sort(key=lambda x: (priority_order.get(x.get("priority", "P1"), 1), x.get("id", "999")))
        
        result = []
        
        while queue:
            # Get highest priority spec with no unmet dependencies
            spec = queue.pop(0)
            result.append(spec)
            
            # Reduce in-degree for dependents
            for other in specs:
                if spec["id"] in other.get("dependencies", []):
                    in_degree[other["id"]] -= 1
                    if in_degree[other["id"]] == 0:
                        queue.append(other)
                        queue.sort(key=lambda x: (priority_order.get(x.get("priority", "P1"), 1), x.get("id", "999")))
        
        # Add any remaining specs (circular dependencies)
        remaining = [s for s in specs if s not in result]
        remaining.sort(key=lambda x: (priority_order.get(x.get("priority", "P1"), 1), x.get("id", "999")))
        result.extend(remaining)
        
        return result
    
    def _generate_sequence_roadmap(self, ordered_specs: List[dict], circular_deps: List[List[str]]) -> str:
        """Generate roadmap markdown file"""
        roadmap = f"""# Implementation Roadmap

Generated: {datetime.now().isoformat()}

## Overview

Total Specs: {len(ordered_specs)}
- P0 (Blocker): {len([s for s in ordered_specs if s.get('priority') == 'P0'])}
- P1 (High): {len([s for s in ordered_specs if s.get('priority') == 'P1'])}
- P2 (Medium): {len([s for s in ordered_specs if s.get('priority') == 'P2'])}
- P3 (Low): {len([s for s in ordered_specs if s.get('priority') == 'P3'])}

"""
        
        if circular_deps:
            roadmap += "## ⚠️ Circular Dependencies\n\n"
            for cycle in circular_deps:
                roadmap += f"- {' → '.join(cycle)}\n"
            roadmap += "\n"
        
        roadmap += "## Implementation Order\n\n"
        
        for i, spec in enumerate(ordered_specs, 1):
            deps = spec.get("dependencies", [])
            dep_str = f" (depends on: {', '.join(deps)})" if deps else ""
            status = "✅" if spec.get("status") == "completed" else "⬜"
            
            roadmap += f"{i}. {status} **{spec['id']}-{self._slugify(spec['name'])}** [{spec['priority']}]{dep_str}\n"
            roadmap += f"   - Source: {spec.get('source', 'unknown')}\n"
            roadmap += f"   - Status: {spec.get('status', 'draft')}\n\n"
        
        roadmap += """## How to Use

1. Work through specs in order (dependencies are respected)
2. For each spec:
   - `speky plan <id>` - Generate implementation plan
   - `speky implement <id>` - Hand off to IDE
   - `speky complete <id>` - Mark as complete

3. To change priority: Edit `status.json` in spec directory
4. To add dependencies: Add spec IDs to `dependencies` array in `status.json`
"""
        
        return roadmap

    # -------------------------------------------------------------------------
    # Command: decisions
    # -------------------------------------------------------------------------
    def cmd_decisions(self, add: bool = False, edit: bool = False, generate: bool = False) -> bool:
        """View and manage tech decisions"""
        if not self._require_init():
            return False
        
        Console.header("🔧 Tech Decisions")
        
        tech_decisions_file = self.context.context_dir / "tech_decisions.md"
        
        # Generate from context.json if requested or file doesn't exist
        if generate or not tech_decisions_file.exists():
            if not tech_decisions_file.exists():
                Console.log("No tech_decisions.md found. Generating from context...")
            else:
                Console.log("Regenerating tech_decisions.md from context...")
            
            tech_stack = self.context.data.get("tech_stack", {})
            self._generate_tech_decisions_file(tech_stack)
            
            if not add and not edit:
                # Show the generated file
                content = tech_decisions_file.read_text()
                print(f"\n{content[:2000]}")
                if len(content) > 2000:
                    print(f"\n... (truncated, see full file at {tech_decisions_file})")
                return True
        
        # Edit mode - open in editor
        if edit:
            import subprocess
            editor = os.environ.get("EDITOR", "nano")
            Console.log(f"Opening {tech_decisions_file} in {editor}...")
            try:
                subprocess.run([editor, str(tech_decisions_file)])
                Console.success("Tech decisions updated")
                return True
            except Exception as e:
                Console.error(f"Could not open editor: {e}")
                Console.log(f"Manually edit: {tech_decisions_file}")
                return False
        
        # Add mode - interactive addition
        if add:
            Console.section("Add New Tech Decision")
            
            category = Console.prompt("Category (e.g., 'WebView Package', 'State Management')")
            if not category:
                Console.warning("Cancelled")
                return False
            
            decision = Console.prompt("Decision (the chosen technology)")
            if not decision:
                Console.warning("Cancelled")
                return False
            
            alternatives = Console.prompt("Alternatives considered (comma-separated, or skip)", default="")
            rationale = Console.prompt("Rationale (why this choice)")
            
            # Read existing content
            content = tech_decisions_file.read_text() if tech_decisions_file.exists() else ""
            
            # Build new section
            new_section = f"""
## {category}

**Decision**: `{decision}`"""
            if alternatives:
                new_section += f"\n**Alternatives Considered**: {alternatives}"
            if rationale:
                new_section += f"\n**Rationale**: {rationale}"
            new_section += f"\n**Date**: {datetime.now().strftime('%Y-%m-%d')}\n\n---\n"
            
            # Insert before "Adding New Decisions" section
            if "## Adding New Decisions" in content:
                content = content.replace(
                    "## Adding New Decisions",
                    new_section + "\n## Adding New Decisions"
                )
            else:
                content += new_section
            
            tech_decisions_file.write_text(content)
            Console.success(f"Added tech decision: {category} = {decision}")
            return True
        
        # Default: show current decisions
        if tech_decisions_file.exists():
            content = tech_decisions_file.read_text()
            
            Console.section("Current Tech Decisions")
            
            # Parse and display nicely
            lines = content.split('\n')
            current_category = None
            
            for line in lines:
                if line.startswith('## ') and 'Adding New' not in line and 'Deprecated' not in line:
                    current_category = line[3:].strip()
                elif line.startswith('**Decision**:') and current_category:
                    decision = line.replace('**Decision**:', '').strip()
                    print(f"   📌 {current_category}: {decision}")
                    current_category = None
            
            print(f"\n   📄 Full file: {tech_decisions_file}")
            print(f"\n   Commands:")
            print(f"      speky decisions --add     Add a new decision")
            print(f"      speky decisions --edit    Edit the file")
            print(f"      speky decisions --generate  Regenerate from context")
        else:
            Console.warning("No tech decisions file found")
            Console.log("Run 'speky decisions --generate' to create one")
        
        return True

    # -------------------------------------------------------------------------
    # Command: host (Host mode — the calling agent answers SPEKY's prompts)
    # -------------------------------------------------------------------------
    def cmd_host(self, action: str = "status", request_id: str = None, file: str = None) -> bool:
        """Inspect and answer prompts that a SPEKY run in host mode is waiting on."""
        if action == "guide":
            print(HOST_AGENT_GUIDE)
            return True

        pending = pending_host_requests(self.project_root)
        if action == "status":
            if not pending:
                print("No host requests waiting.")
                print("Start a command in host mode with --host (or SPEKY_MODEL=host); see `speky host guide`.")
                return True
            for f in pending:
                print(f"⏸️  {f.name[:3]}  waiting  {f}")
            return True

        if request_id:
            rid = f"{int(request_id):03d}" if request_id.isdigit() else request_id
            prompt_file = self.project_root / SPEKY_DIR / "host" / f"{rid}.prompt.md"
        elif pending:
            prompt_file, rid = pending[0], pending[0].name[:3]
        else:
            Console.error("No host requests waiting.")
            return False
        if not prompt_file.exists():
            Console.error(f"No host request {rid} waiting ({prompt_file}).")
            return False

        if action == "show":
            print(prompt_file.read_text())
            return True

        # answer
        text = Path(file).read_text() if file else sys.stdin.read()
        if not text.strip():
            Console.error("Empty answer — pass --file or pipe the answer on stdin.")
            return False
        try:
            write_host_answer(self.project_root, rid, text)
        except LLMError as e:
            Console.error(str(e))
            return False
        Console.success(f"Answered host request {rid}; the waiting SPEKY run will continue.")
        return True

    # -------------------------------------------------------------------------
    # Command: config (SPEKY Configuration)
    # -------------------------------------------------------------------------
    def cmd_config(self, ides: str = None, action: str = None, value: str = None,
                   list_ides: bool = False, model: str = None, providers: bool = False) -> bool:
        """View and manage SPEKY configuration, especially IDE settings

        Usage:
            speky config                           Show current config
            speky config --list-ides               List all supported IDEs
            speky config --ides                    Show enabled IDEs
            speky config --ides add antigravity    Add Antigravity IDE
            speky config --ides remove cursor      Remove Cursor IDE
            speky config --ides set windsurf,antigravity  Set specific IDEs
            speky config --model                   Show current model + available env models
            speky config --model GEMINI_MODEL      Switch to model defined by env var key
            speky config --model openrouter/moonshotai/kimi-k2   Set model (provider/model)
            speky config --providers               List AI providers and key status
        """
        Console.header("⚙️ SPEKY Configuration")

        # Handle model configuration
        if model is not None:
            return self._config_model(model)
        if providers:
            return self._config_providers()

        # List all supported IDEs
        if list_ides:
            Console.section("Supported IDEs")
            for ide_name, ide_config in IDEIntegration.IDE_CONFIGS.items():
                ide_type = ide_config["type"]
                ide_path = ide_config["path"]
                if ide_type == "folder":
                    main_file = ide_config.get("main_file", "rules.md")
                    print(f"   • {ide_name}: {ide_path}/{main_file} (folder-based)")
                else:
                    print(f"   • {ide_name}: {ide_path}")
            return True

        # Handle IDE configuration
        if ides is not None:
            return self._config_ides(ides, action, value)

        # Default: show current configuration
        self._show_current_config()
        return True

    def _config_model(self, model_arg: str) -> bool:
        """Show or set the active model (a provider/model ref, saved to ~/.speky/models.yaml)."""
        router = self.ai.router
        if not model_arg:
            print(f"   🤖 Current model: {router.model_ref or 'not set'}")
            if router.fallbacks:
                print(f"   ↪️  Fallbacks: {', '.join(router.fallbacks)}")
            print(f"   📄 Config: {GLOBAL_CONFIG}")
            if not Console.confirm("Change model?", default=False):
                print("\n   Usage: speky config --model openrouter/moonshotai/kimi-k2")
                print("          speky config --providers     # list providers and key status")
                return True
            return self._pick_model()

        # Legacy: an env var key (e.g. GEMINI_MODEL) resolves to its value
        import re
        if re.match(r'^[A-Z][A-Z0-9_]+$', model_arg):
            resolved = os.environ.get(model_arg)
            if not resolved:
                Console.error(f"Env var '{model_arg}' not found. Add it to your .env file.")
                return False
            Console.log(f"Resolved {model_arg} → {resolved}")
            model_arg = resolved

        try:
            provider, model = router.resolve(model_arg)
        except LLMError as e:
            Console.error(str(e))
            return False
        return self._save_model(f"{provider}/{model}")

    def _pick_model(self) -> bool:
        """Interactive provider → model picker."""
        router = self.ai.router
        names = sorted(router.providers, key=lambda n: (not router.is_available(n), n))
        labels = [f"{n:<14} {'✅' if router.is_available(n) else '  '} {router.status(n)}" for n in names]
        provider = names[Console.choose("Select a provider:", labels)]
        if not router.is_available(provider):
            Console.warning(f"{provider} is not ready yet ({router.status(provider)}) — saving anyway.")
            models = list(router.providers[provider].get("models") or [])
        else:
            Console.log(f"Fetching models from {provider}...")
            models = router.list_models(provider)
        if models:
            shown = models[:40]
            for i, m in enumerate(shown, 1):
                print(f"  {i:>3}. {m}")
            if len(models) > len(shown):
                print(f"       … {len(models) - len(shown)} more — type the exact name")
            answer = Console.prompt("Model number or name")
            model = shown[int(answer) - 1] if answer.isdigit() and 1 <= int(answer) <= len(shown) else answer
        else:
            model = Console.prompt("Model name")
        if not model:
            Console.error("No model chosen.")
            return False
        return self._save_model(f"{provider}/{model}")

    def _save_model(self, model_ref: str) -> bool:
        save_model(model_ref)
        Console.success(f"Model set to: {model_ref}  (saved in {GLOBAL_CONFIG})")
        if os.environ.get("SPEKY_MODEL"):
            Console.warning(f"SPEKY_MODEL={os.environ['SPEKY_MODEL']} is set and overrides this.")
        if (self.project_root / SPEKY_DIR / "models.yaml").exists():
            Console.warning(f"{SPEKY_DIR}/models.yaml in this project may override it.")
        return True

    def _config_providers(self) -> bool:
        """List known providers and whether each is ready to use."""
        router = self.ai.router
        Console.section("AI Providers")
        for name in sorted(router.providers):
            p = router.providers[name]
            mark = "✅" if router.is_available(name) else "❌"
            where = p.get("base_url") or ("claude CLI" if p["type"] == "claude-code" else p["type"])
            print(f"   {mark} {name:<14} {router.status(name):<28} {where}")
        print(f"\n   Add or override providers in {GLOBAL_CONFIG} (see MODELS.md).")
        return True

    def _config_ides(self, ides: str, action: str = None, value: str = None) -> bool:
        """Handle IDE configuration commands"""
        
        # Get current enabled IDEs
        current_ides = self._get_enabled_ides()
        
        # Show current IDEs if just --ides with no action
        if ides == "show" and not action:
            Console.section("Enabled IDEs")
            for ide in current_ides:
                ide_config = IDEIntegration.IDE_CONFIGS.get(ide, {})
                ide_path = ide_config.get("path", "unknown")
                print(f"   ✅ {ide}: {ide_path}")
            
            print(f"\n   Commands:")
            print(f"      speky config --ides add <ide>        Add an IDE")
            print(f"      speky config --ides remove <ide>     Remove an IDE")
            print(f"      speky config --ides set <ide1,ide2>  Set specific IDEs")
            print(f"      speky config --list-ides             List all supported IDEs")
            return True
        
        # Handle add/remove/set actions
        if action == "add":
            if not value:
                Console.error("Please specify an IDE to add")
                Console.log("Example: speky config --ides add antigravity")
                return False
            
            ide_to_add = value.lower().strip()
            
            # Validate IDE name
            if ide_to_add not in IDEIntegration.IDE_CONFIGS:
                Console.error(f"Unknown IDE: {ide_to_add}")
                Console.log(f"Supported IDEs: {', '.join(IDEIntegration.IDE_CONFIGS.keys())}")
                return False
            
            if ide_to_add in current_ides:
                Console.warning(f"{ide_to_add} is already enabled")
                return True
            
            # Add the IDE
            new_ides = current_ides + [ide_to_add]
            self._save_enabled_ides(new_ides)
            Console.success(f"Added {ide_to_add} to enabled IDEs")
            
            # Generate rules for the new IDE
            Console.log(f"Generating rules for {ide_to_add}...")
            self.ide.update_context_file(self.context.get_product_context(), target_ide=ide_to_add)
            
            return True
        
        elif action == "remove":
            if not value:
                Console.error("Please specify an IDE to remove")
                Console.log("Example: speky config --ides remove cursor")
                return False
            
            ide_to_remove = value.lower().strip()
            
            if ide_to_remove not in current_ides:
                Console.warning(f"{ide_to_remove} is not currently enabled")
                return True
            
            if len(current_ides) == 1:
                Console.error("Cannot remove the last IDE. At least one IDE must be enabled.")
                return False
            
            # Remove the IDE
            new_ides = [ide for ide in current_ides if ide != ide_to_remove]
            self._save_enabled_ides(new_ides)
            Console.success(f"Removed {ide_to_remove} from enabled IDEs")
            Console.log(f"Note: The rules file for {ide_to_remove} was not deleted. Remove manually if desired.")
            
            return True
        
        elif action == "set":
            if not value:
                Console.error("Please specify IDEs to set")
                Console.log("Example: speky config --ides set windsurf,antigravity")
                return False
            
            # Parse comma-separated list
            ides_to_set = [ide.lower().strip() for ide in value.split(",")]
            
            # Validate all IDE names
            invalid_ides = [ide for ide in ides_to_set if ide not in IDEIntegration.IDE_CONFIGS]
            if invalid_ides:
                Console.error(f"Unknown IDE(s): {', '.join(invalid_ides)}")
                Console.log(f"Supported IDEs: {', '.join(IDEIntegration.IDE_CONFIGS.keys())}")
                return False
            
            if not ides_to_set:
                Console.error("At least one IDE must be specified")
                return False
            
            # Set the IDEs
            self._save_enabled_ides(ides_to_set)
            Console.success(f"Set enabled IDEs to: {', '.join(ides_to_set)}")
            
            # Generate rules for all new IDEs
            new_ides = [ide for ide in ides_to_set if ide not in current_ides]
            if new_ides:
                Console.log(f"Generating rules for new IDEs: {', '.join(new_ides)}")
                product_context = self.context.get_product_context()
                for ide in new_ides:
                    self.ide.update_context_file(product_context, target_ide=ide)
            
            return True
        
        else:
            # Unknown action or just --ides without action
            Console.error(f"Unknown action: {action or ides}")
            Console.log("Usage: speky config --ides <add|remove|set> <value>")
            return False
    
    def _save_enabled_ides(self, ides: List[str]) -> None:
        """Save enabled IDEs to context.json"""
        # Load data once, modify, then save (data property reloads each access)
        data = self.context.data
        data["enabled_ides"] = ides
        self.context.save(data)
        
        # Also update the IDE integration instance
        self.ide.enabled_ides = ides
    
    def _show_current_config(self) -> None:
        """Display current SPEKY configuration"""
        Console.section("Current Configuration")
        
        # Show enabled IDEs
        enabled_ides = self._get_enabled_ides()
        print(f"   📱 Enabled IDEs: {', '.join(enabled_ides)}")
        
        # Show model
        print(f"   🤖 AI Model: {self.ai.model_ref or 'not set'}")
        
        # Show MCP status
        mcp_enabled = self.config.get("mcp_enabled", False)
        print(f"   🔌 MCP: {'Enabled' if mcp_enabled else 'Disabled'}")
        
        # Show project info if initialized
        if self.context.is_initialized():
            product = self.context.data.get("product", {})
            print(f"\n   📦 Project: {product.get('name', 'Unknown')}")
            
            # Count specs and stories
            specs_count = len(list(self.context.specs_dir.glob("*"))) if self.context.specs_dir.exists() else 0
            stories_count = len(list(self.context.stories_dir.glob("*"))) if self.context.stories_dir.exists() else 0
            print(f"   📋 Specs: {specs_count}")
            print(f"   📝 Stories: {stories_count}")
        
        print(f"\n   Commands:")
        print(f"      speky config --ides                  Manage IDE settings")
        print(f"      speky config --list-ides             List all supported IDEs")

    # -------------------------------------------------------------------------
    # Command: design (Design System Management)
    # -------------------------------------------------------------------------
    def cmd_design(self, action: str, design_type: str = None, path: str = None, 
                   tech: str = None, spec_id: str = None, analyze: bool = False) -> bool:
        """Manage design system - init, import, status, analyze, link"""
        if not self._require_init():
            return False
        
        if action == "init":
            return self._design_init(tech=tech, from_path=path)
        elif action == "import":
            return self._design_import(path=path, design_type=design_type, 
                                       spec_id=spec_id, analyze=analyze)
        elif action == "status":
            return self._design_status()
        elif action == "analyze":
            return self._design_analyze(path=path)
        elif action == "link":
            return self._design_link(path=path, spec_id=spec_id)
        elif action == "resolve":
            return self._design_resolve()
        elif action == "validate":
            return self._design_validate()
        elif action == "sync":
            return self._design_sync(apply_changes=analyze)  # reuse 'analyze' flag as 'apply'
        else:
            Console.error(f"Unknown design action: {action}")
            Console.log("Available actions: init, import, status, analyze, link, resolve, validate, sync")
            return False
    
    def _design_init(self, tech: str = None, from_path: str = None) -> bool:
        """Initialize design system for project"""
        Console.header("🎨 Design System: Initialize")
        
        design_dir = self.context.speky_dir / DESIGN_DIR
        config_file = design_dir / "config.yaml"
        
        # Check if already initialized
        if config_file.exists():
            if not Console.confirm("Design system already initialized. Reinitialize?", default=False):
                return False
        
        # Step 1: Get technology
        if not tech:
            tech_stack = self.context.data.get("tech_stack", {})
            frontend = tech_stack.get("frontend", "")
            
            # Try to detect from tech stack
            if "flutter" in frontend.lower():
                suggested_tech = "flutter"
            elif "react" in frontend.lower():
                suggested_tech = "react"
            elif "vue" in frontend.lower():
                suggested_tech = "vue"
            else:
                suggested_tech = ""
            
            print("\n📱 What UI technology is this project using?")
            print("   1. Flutter")
            print("   2. React")
            print("   3. Vue")
            print("   4. Svelte")
            print("   5. Other (specify)")
            
            if suggested_tech:
                Console.log(f"   (Detected from tech stack: {suggested_tech})")
            
            choice = Console.prompt("Select technology [1-5]", default="1" if suggested_tech == "flutter" else "")
            
            tech_map = {"1": "flutter", "2": "react", "3": "vue", "4": "svelte"}
            if choice in tech_map:
                tech = tech_map[choice]
            elif choice == "5":
                tech = Console.prompt("Enter technology name")
            else:
                tech = choice.lower() if choice else "flutter"
        
        Console.log(f"Technology: {tech}")
        
        # Step 2: Determine source mode
        print("\n📄 How will you provide the design system?")
        print("   1. I have a design system document (markdown)")
        print("   2. I have Hi-Fi design images only")
        print("   3. I have both document and images")
        print("   4. Start fresh (create template)")
        
        source_choice = Console.prompt("Select source [1-4]", default="4")
        
        source_mode_map = {
            "1": DesignSourceMode.DOCUMENT.value,
            "2": DesignSourceMode.IMAGES.value,
            "3": DesignSourceMode.HYBRID.value,
            "4": DesignSourceMode.DOCUMENT.value  # Template is a document
        }
        source_mode = source_mode_map.get(source_choice, DesignSourceMode.DOCUMENT.value)
        
        # Step 3: Create folder structure
        Console.section("Creating Design System Structure")
        
        folders = [
            design_dir / "system" / "source",
            design_dir / "hifi" / "source",
            design_dir / "lofi" / "source",
            design_dir / "icons" / "source",
        ]
        
        for folder in folders:
            folder.mkdir(parents=True, exist_ok=True)
        
        Console.success("Created .speky/design/ structure")
        
        # Step 4: Handle source based on choice
        design_system_content = None
        
        if source_choice == "1" or source_choice == "3":
            # Import from document
            if from_path:
                doc_path = Path(from_path)
            else:
                print(f"\n📁 Place your design system document in:")
                print(f"   {design_dir / 'system' / 'source'}")
                print(f"   Supported: .md, .txt")
                Console.prompt("\nPress Enter when ready...", default="")
                
                # Scan for documents
                source_dir = design_dir / "system" / "source"
                docs = list(source_dir.glob("*.md")) + list(source_dir.glob("*.txt"))
                
                if docs:
                    doc_path = docs[0]
                    Console.success(f"Found: {doc_path.name}")
                else:
                    Console.warning("No document found. Creating template instead.")
                    source_choice = "4"
                    doc_path = None
            
            if doc_path and doc_path.exists():
                # Copy to design folder if not already there
                dest_path = design_dir / "system" / "source" / doc_path.name
                if doc_path != dest_path:
                    import shutil
                    shutil.copy2(doc_path, dest_path)
                    Console.success(f"Copied: {doc_path.name}")
                
                # Read and analyze
                design_system_content = dest_path.read_text()
                
                # AI analysis
                Console.section("Analyzing Design System Document")
                analysis = self.ai.query(Prompts.analyze_design_document(design_system_content, tech))
                
                if analysis:
                    # Save analysis
                    analysis_file = design_dir / "system" / "analysis.md"
                    analysis_file.write_text(analysis)
                    Console.success(f"Analysis saved: {analysis_file.name}")
                    
                    # Show preview
                    print("\n--- Analysis Preview ---")
                    print(analysis[:1500] + "..." if len(analysis) > 1500 else analysis)
                    print("--- End Preview ---\n")
        
        if source_choice == "2" or source_choice == "3":
            # Prompt for images
            print(f"\n📁 Place your Hi-Fi design images in:")
            print(f"   {design_dir / 'hifi' / 'source'}")
            print(f"   Supported: .png, .jpg, .jpeg, .webp, .svg")
            
            if source_choice == "2":
                Console.prompt("\nPress Enter when ready...", default="")
                
                # Scan for images
                hifi_dir = design_dir / "hifi" / "source"
                images = []
                for ext in DESIGN_IMAGE_EXTENSIONS:
                    images.extend(hifi_dir.glob(f"*{ext}"))
                
                if images:
                    Console.success(f"Found {len(images)} image(s)")
                    for img in images[:5]:
                        print(f"   • {img.name}")
                    if len(images) > 5:
                        print(f"   ... and {len(images) - 5} more")
                    
                    # Ask if they want to analyze now
                    if Console.confirm("Analyze images now? (uses Vision AI)", default=True):
                        return self._design_analyze()
                else:
                    Console.warning("No images found yet. Run 'speky design import' later.")
        
        if source_choice == "4" or design_system_content is None:
            # Create template
            Console.section("Creating Design System Template")
            
            template = Prompts.get_design_system_template(tech)
            template = template.replace("[Project Name]", self.context.data.get("product", {}).get("name", "Project"))
            template = template.replace("[date]", datetime.now().strftime("%Y-%m-%d"))
            
            template_file = design_dir / "system" / "source" / "design-system.md"
            template_file.write_text(template)
            Console.success(f"Created template: {template_file.name}")
            
            design_system_content = template
        
        # Step 5: Generate design_system.md summary in context
        Console.section("Generating Context Summary")
        
        summary = self.ai.query(Prompts.summarize_design_system(design_system_content, tech))
        
        if summary:
            context_design_file = self.context.context_dir / "design_system.md"
            context_design_file.write_text(summary)
            Console.success(f"Created: .speky/context/design_system.md")
        
        # Step 6: Create config
        config = {
            "version": "1.0",
            "technology": tech,
            "source_mode": source_mode,
            "vision_analysis": True,
            "context_mode": "descriptions",  # paths, descriptions, embedded
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        
        # Write as YAML-like format (simple key: value)
        config_content = "# Design System Configuration\n\n"
        for key, value in config.items():
            config_content += f"{key}: {value}\n"
        
        config_file.write_text(config_content)
        
        # Step 7: Create manifest
        manifest = {
            "id": "design-system",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "technology": tech,
            "source_mode": source_mode,
            "system_doc": None,
            "hifi_images": [],
            "lofi_images": [],
            "icons": [],
            "conflicts": [],
            "components": [],
        }
        
        # Check for system doc
        system_docs = list((design_dir / "system" / "source").glob("*.md"))
        if system_docs:
            manifest["system_doc"] = str(system_docs[0].relative_to(self.context.speky_dir))
        
        # Scan for images
        for img_type in ["hifi", "lofi", "icons"]:
            img_dir = design_dir / img_type / "source"
            if img_dir.exists():
                images = []
                for ext in DESIGN_IMAGE_EXTENSIONS:
                    for img in img_dir.glob(f"*{ext}"):
                        images.append({
                            "id": img.stem,
                            "filename": img.name,
                            "path": str(img.relative_to(self.context.speky_dir)),
                            "analyzed": False,
                            "related_specs": [],
                        })
                manifest[f"{img_type}_images" if img_type != "icons" else "icons"] = images
        
        manifest_file = design_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2))
        
        # Step 8: Update IDE rules
        self.ide.update_context_file(self.context.get_product_context())
        
        Console.success("Design system initialized!")
        print(f"\n📁 Structure created:")
        print(f"   .speky/design/")
        print(f"   ├── config.yaml")
        print(f"   ├── manifest.json")
        print(f"   ├── system/source/     ← Design system documents")
        print(f"   ├── hifi/source/       ← Hi-Fi designs (pixel-perfect)")
        print(f"   ├── lofi/source/       ← Lo-Fi wireframes (guidance)")
        print(f"   └── icons/source/      ← Icon assets")
        print(f"\n   .speky/context/design_system.md  ← Summary for AI context")
        
        print(f"\n📋 Next steps:")
        print(f"   1. Add design files to appropriate folders")
        print(f"   2. Run: speky design import ./path/to/designs --type hifi")
        print(f"   3. Run: speky design analyze")
        print(f"   4. Run: speky design status")
        
        return True
    
    def _design_import(self, path: str = None, design_type: str = None, 
                       spec_id: str = None, analyze: bool = False) -> bool:
        """Import design files (images, docs, icons)"""
        Console.header("🎨 Design System: Import")
        
        design_dir = self.context.speky_dir / DESIGN_DIR
        
        # Check if design system is initialized
        if not (design_dir / "manifest.json").exists():
            Console.error("Design system not initialized. Run: speky design init")
            return False
        
        # Get path
        if not path:
            path = Console.prompt("Path to design file(s) or folder")
            if not path:
                Console.warning("Cancelled")
                return False
        
        source_path = Path(path)
        if not source_path.exists():
            Console.error(f"Path not found: {path}")
            return False
        
        # Get design type
        if not design_type:
            print("\n📁 What type of design is this?")
            print("   1. hifi  - High-fidelity designs (pixel-perfect required)")
            print("   2. lofi  - Low-fidelity wireframes (guidance only)")
            print("   3. icons - Icon assets")
            print("   4. system - Design system document")
            
            choice = Console.prompt("Select type [1-4]", default="1")
            type_map = {"1": "hifi", "2": "lofi", "3": "icons", "4": "system"}
            design_type = type_map.get(choice, "hifi")
        
        # Determine destination
        if design_type == "system":
            dest_dir = design_dir / "system" / "source"
        else:
            dest_dir = design_dir / design_type / "source"
        
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Import files
        import shutil
        imported_files = []
        
        if source_path.is_file():
            # Single file
            dest = dest_dir / source_path.name
            shutil.copy2(source_path, dest)
            imported_files.append(dest)
            Console.success(f"Imported: {source_path.name}")
        else:
            # Directory - import all supported files
            if design_type == "system":
                extensions = DESIGN_DOC_EXTENSIONS
            else:
                extensions = DESIGN_IMAGE_EXTENSIONS
            
            for ext in extensions:
                for file in source_path.glob(f"*{ext}"):
                    if file.is_file():
                        dest = dest_dir / file.name
                        shutil.copy2(file, dest)
                        imported_files.append(dest)
            
            Console.success(f"Imported {len(imported_files)} file(s)")
        
        if not imported_files:
            Console.warning("No supported files found to import")
            return False
        
        # Update manifest
        manifest_file = design_dir / "manifest.json"
        manifest = json.loads(manifest_file.read_text())
        
        for file in imported_files:
            file_entry = {
                "id": file.stem,
                "filename": file.name,
                "path": str(file.relative_to(self.context.speky_dir)),
                "analyzed": False,
                "related_specs": [spec_id] if spec_id else [],
                "imported_at": datetime.now().isoformat(),
            }
            
            if design_type == "system":
                manifest["system_doc"] = str(file.relative_to(self.context.speky_dir))
            elif design_type == "hifi":
                # Check if already exists
                existing = [i for i in manifest.get("hifi_images", []) if i["filename"] == file.name]
                if existing:
                    existing[0].update(file_entry)
                else:
                    manifest.setdefault("hifi_images", []).append(file_entry)
            elif design_type == "lofi":
                existing = [i for i in manifest.get("lofi_images", []) if i["filename"] == file.name]
                if existing:
                    existing[0].update(file_entry)
                else:
                    manifest.setdefault("lofi_images", []).append(file_entry)
            elif design_type == "icons":
                existing = [i for i in manifest.get("icons", []) if i["filename"] == file.name]
                if existing:
                    existing[0].update(file_entry)
                else:
                    manifest.setdefault("icons", []).append(file_entry)
        
        manifest["updated_at"] = datetime.now().isoformat()
        manifest_file.write_text(json.dumps(manifest, indent=2))
        
        # Show imported files
        for file in imported_files[:10]:
            print(f"   ✅ {file.name}")
        if len(imported_files) > 10:
            print(f"   ... and {len(imported_files) - 10} more")
        
        # Analyze if requested
        if analyze and design_type in ["hifi", "lofi"]:
            Console.log("\nRunning Vision AI analysis...")
            return self._design_analyze()
        
        print(f"\n📋 Next steps:")
        if design_type in ["hifi", "lofi"]:
            print(f"   Run: speky design analyze")
        if spec_id:
            print(f"   Linked to spec: {spec_id}")
        else:
            print(f"   Run: speky design link <filename> --spec <id>")
        
        return True
    
    def _design_status(self) -> bool:
        """Show design system status"""
        Console.header("🎨 Design System: Status")
        
        design_dir = self.context.speky_dir / DESIGN_DIR
        manifest_file = design_dir / "manifest.json"
        
        if not manifest_file.exists():
            Console.warning("Design system not initialized")
            Console.log("Run: speky design init")
            return True
        
        manifest = json.loads(manifest_file.read_text())
        
        # Configuration
        config_file = design_dir / "config.yaml"
        config = {}
        if config_file.exists():
            for line in config_file.read_text().split("\n"):
                if ":" in line and not line.startswith("#"):
                    key, value = line.split(":", 1)
                    config[key.strip()] = value.strip()
        
        Console.section("Configuration")
        print(f"   Technology: {config.get('technology', 'unknown')}")
        print(f"   Source Mode: {config.get('source_mode', 'unknown')}")
        print(f"   Vision Analysis: {config.get('vision_analysis', 'true')}")
        print(f"   Context Mode: {config.get('context_mode', 'descriptions')}")
        
        # Files
        Console.section("Files")
        
        system_doc = manifest.get("system_doc")
        if system_doc:
            print(f"   📄 System Doc: ✅ {Path(system_doc).name}")
        else:
            print(f"   📄 System Doc: ❌ Not found")
        
        hifi = manifest.get("hifi_images", [])
        analyzed_hifi = len([i for i in hifi if i.get("analyzed")])
        print(f"   🖼️  Hi-Fi Images: {len(hifi)} files ({analyzed_hifi} analyzed)")
        
        lofi = manifest.get("lofi_images", [])
        analyzed_lofi = len([i for i in lofi if i.get("analyzed")])
        print(f"   📝 Lo-Fi Images: {len(lofi)} files ({analyzed_lofi} analyzed)")
        
        icons = manifest.get("icons", [])
        print(f"   🎯 Icons: {len(icons)} files")
        
        # Conflicts
        conflicts = manifest.get("conflicts", [])
        unresolved = [c for c in conflicts if not c.get("resolution")]
        if unresolved:
            Console.section(f"⚠️  Conflicts ({len(unresolved)} unresolved)")
            for conflict in unresolved[:5]:
                print(f"   • [{conflict.get('type', 'unknown').upper()}] {conflict.get('context', 'Unknown')}")
                print(f"     {conflict.get('existing_value', '?')} vs {conflict.get('new_value', '?')}")
            if len(unresolved) > 5:
                print(f"   ... and {len(unresolved) - 5} more")
            print(f"\n   Run: speky design resolve")
        else:
            print(f"\n   ✅ No unresolved conflicts")
        
        # Spec coverage
        Console.section("Spec Coverage")
        
        specs_dir = self.context.speky_dir / SPECS_DIR
        if specs_dir.exists():
            specs_with_designs = set()
            for img in hifi + lofi:
                specs_with_designs.update(img.get("related_specs", []))
            
            all_specs = list(specs_dir.glob("*/spec.md"))
            covered = len(specs_with_designs)
            total = len(all_specs)
            
            print(f"   {covered}/{total} specs have linked designs")
            
            if covered < total:
                print(f"\n   Specs without designs:")
                for spec_dir in all_specs[:5]:
                    spec_id = spec_dir.parent.name.split("-")[0]
                    if spec_id not in specs_with_designs:
                        print(f"   • {spec_dir.parent.name}")
        
        # Context file
        context_file = self.context.context_dir / "design_system.md"
        if context_file.exists():
            print(f"\n   📋 Context: .speky/context/design_system.md ✅")
        else:
            print(f"\n   📋 Context: .speky/context/design_system.md ❌")
            print(f"      Run: speky design init --from <doc>")
        
        return True
    
    def _design_analyze(self, path: str = None) -> bool:
        """Analyze designs using Vision AI"""
        Console.header("🎨 Design System: Analyze")
        
        design_dir = self.context.speky_dir / DESIGN_DIR
        manifest_file = design_dir / "manifest.json"
        
        if not manifest_file.exists():
            Console.error("Design system not initialized. Run: speky design init")
            return False
        
        manifest = json.loads(manifest_file.read_text())
        
        # Get config
        config_file = design_dir / "config.yaml"
        technology = "flutter"  # default
        if config_file.exists():
            for line in config_file.read_text().split("\n"):
                if line.startswith("technology:"):
                    technology = line.split(":", 1)[1].strip()
                    break
        
        # Find images to analyze
        images_to_analyze = []
        
        if path:
            # Specific file
            target = Path(path)
            if target.exists():
                images_to_analyze.append({
                    "path": str(target),
                    "filename": target.name,
                    "type": "hifi"
                })
            else:
                # Try to find in design folders
                for img_type in ["hifi", "lofi"]:
                    img_path = design_dir / img_type / "source" / path
                    if img_path.exists():
                        images_to_analyze.append({
                            "path": str(img_path),
                            "filename": img_path.name,
                            "type": img_type
                        })
                        break
        else:
            # All unanalyzed images
            for img_type in ["hifi", "lofi"]:
                for img in manifest.get(f"{img_type}_images", []):
                    if not img.get("analyzed"):
                        img_path = self.context.speky_dir / img["path"]
                        if img_path.exists():
                            images_to_analyze.append({
                                "path": str(img_path),
                                "filename": img["filename"],
                                "type": img_type,
                                "id": img["id"]
                            })
        
        if not images_to_analyze:
            Console.success("All images already analyzed!")
            return True
        
        Console.log(f"Found {len(images_to_analyze)} image(s) to analyze")
        
        # Analyze each image
        for i, img_info in enumerate(images_to_analyze, 1):
            Console.section(f"Analyzing ({i}/{len(images_to_analyze)})", img_info["filename"])
            
            try:
                analysis = self._analyze_image_with_vision(
                    Path(img_info["path"]), 
                    technology
                )
                
                if analysis:
                    # Save analysis alongside image
                    img_path = Path(img_info["path"])
                    analysis_path = img_path.parent / f"{img_path.stem}.analysis.md"
                    analysis_path.write_text(analysis["analysis"])
                    
                    Console.success(f"Analysis saved: {analysis_path.name}")
                    
                    # Update manifest
                    img_type = img_info["type"]
                    for img in manifest.get(f"{img_type}_images", []):
                        if img["filename"] == img_info["filename"]:
                            img["analyzed"] = True
                            img["analyzed_at"] = analysis["analyzed_at"]
                            img["analysis_path"] = str(analysis_path.relative_to(self.context.speky_dir))
                            break
                    
                    # Show preview
                    print("\n--- Analysis Preview ---")
                    print(analysis["analysis"][:1000] + "..." if len(analysis["analysis"]) > 1000 else analysis["analysis"])
                    print("--- End Preview ---\n")
                else:
                    Console.warning(f"Analysis failed for {img_info['filename']}")
                    
            except Exception as e:
                Console.error(f"Error analyzing {img_info['filename']}: {str(e)}")
        
        # Save updated manifest
        manifest["updated_at"] = datetime.now().isoformat()
        manifest_file.write_text(json.dumps(manifest, indent=2))
        
        Console.success("Analysis complete!")
        print(f"\n📋 Next steps:")
        print(f"   Run: speky design status")
        print(f"   Run: speky design resolve  (if conflicts detected)")
        
        return True
    
    def _analyze_image_with_vision(self, image_path: Path, technology: str) -> Optional[dict]:
        """Analyze image using Claude Vision API"""
        import base64

        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")
        
        # Determine media type
        suffix = image_path.suffix.lower()
        media_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        media_type = media_types.get(suffix, "image/png")
        
        # SVG is text-based, handle differently
        if suffix == ".svg":
            Console.warning("SVG files are analyzed as text, not images")
            svg_content = image_path.read_text()
            prompt = f"""Analyze this SVG icon/image for a {technology} application.

SVG CONTENT:
{svg_content[:5000]}

Extract:
1. Icon purpose/meaning
2. Colors used
3. Dimensions
4. Recommended usage
"""
            response = self.ai.query(prompt)
            return {
                "analysis": response or "Analysis failed",
                "analyzed_at": datetime.now().isoformat(),
            }
        
        # Build vision prompt
        prompt = f"""Analyze this UI design image for a {technology} application.

Extract the following design tokens with EXACT values:

## 1. COLORS
Extract all visible colors as hex values:
- Background colors (main, sidebar, cards, etc.)
- Text colors (primary, secondary, muted)
- Accent/brand colors
- Border colors
- Shadow colors (if visible)

## 2. TYPOGRAPHY
For each text style visible:
- Approximate font size (in pixels)
- Font weight (regular, medium, semibold, bold)
- Letter spacing if notable
- Text case (normal, uppercase, lowercase)

## 3. SPACING
Measure key spacing values:
- Padding values (small, medium, large patterns)
- Margins between elements
- Gap between items in lists/grids

## 4. DIMENSIONS
Key layout measurements:
- Sidebar width (if visible)
- Card widths
- Icon sizes
- Border radius values

## 5. COMPONENTS
Identify UI components visible:
- Component name
- Key visual properties
- Interactive states if visible (hover, active)

## 6. HIERARCHY
Describe the visual hierarchy:
- Primary actions
- Secondary elements
- Navigation structure

## 7. IMPLEMENTATION NOTES
Specific notes for implementing this in {technology}:
- Widget/component suggestions
- State management considerations
- Animation opportunities

Output as structured markdown with exact values.
Be specific with pixel values and hex codes."""

        try:
            client, model = self.ai.router.anthropic_client()
            if not client:
                Console.warning("Image analysis needs an anthropic/* model. Skipping.")
                return None
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ],
                    }
                ],
            )

            return {
                "analysis": response.content[0].text,
                "analyzed_at": datetime.now().isoformat(),
            }
            
        except Exception as e:
            Console.error(f"Vision API error: {str(e)}")
            return None
    
    def _design_link(self, path: str = None, spec_id: str = None) -> bool:
        """Link designs to specs"""
        Console.header("🎨 Design System: Link")
        
        design_dir = self.context.speky_dir / DESIGN_DIR
        manifest_file = design_dir / "manifest.json"
        
        if not manifest_file.exists():
            Console.error("Design system not initialized. Run: speky design init")
            return False
        
        manifest = json.loads(manifest_file.read_text())
        
        # Get design file
        if not path:
            # Show available designs
            all_designs = []
            for img_type in ["hifi", "lofi"]:
                for img in manifest.get(f"{img_type}_images", []):
                    all_designs.append((img["filename"], img_type, img.get("related_specs", [])))
            
            if not all_designs:
                Console.warning("No designs found. Run: speky design import")
                return False
            
            print("\n📁 Available designs:")
            for i, (name, dtype, specs) in enumerate(all_designs, 1):
                specs_str = f" → {', '.join(specs)}" if specs else ""
                print(f"   {i}. [{dtype}] {name}{specs_str}")
            
            choice = Console.prompt("Select design number")
            try:
                idx = int(choice) - 1
                path = all_designs[idx][0]
            except (ValueError, IndexError):
                Console.warning("Invalid selection")
                return False
        
        # Get spec ID
        if not spec_id:
            # Show available specs
            specs_dir = self.context.speky_dir / SPECS_DIR
            specs = list(specs_dir.glob("*/spec.md"))
            
            if not specs:
                Console.warning("No specs found")
                return False
            
            print("\n📋 Available specs:")
            for spec in specs[:10]:
                print(f"   • {spec.parent.name}")
            
            spec_id = Console.prompt("Spec ID (e.g., 007)")
        
        # Update manifest
        linked = False
        for img_type in ["hifi", "lofi"]:
            for img in manifest.get(f"{img_type}_images", []):
                if img["filename"] == path or path in img.get("path", ""):
                    if spec_id not in img.get("related_specs", []):
                        img.setdefault("related_specs", []).append(spec_id)
                        linked = True
                        Console.success(f"Linked {img['filename']} → spec {spec_id}")
        
        if linked:
            manifest["updated_at"] = datetime.now().isoformat()
            manifest_file.write_text(json.dumps(manifest, indent=2))
        else:
            Console.warning(f"Design not found: {path}")
            return False
        
        return True
    
    def _design_resolve(self) -> bool:
        """Resolve design conflicts with AI recommendations"""
        Console.header("🎨 Design System: Resolve Conflicts")
        
        design_dir = self.context.speky_dir / DESIGN_DIR
        manifest_file = design_dir / "manifest.json"
        
        if not manifest_file.exists():
            Console.error("Design system not initialized. Run: speky design init")
            return False
        
        manifest = json.loads(manifest_file.read_text())
        
        # Get unresolved conflicts
        conflicts = [c for c in manifest.get("conflicts", []) if not c.get("resolution")]
        
        if not conflicts:
            Console.success("No unresolved conflicts!")
            return True
        
        Console.log(f"Found {len(conflicts)} unresolved conflict(s)")
        
        # Load design system for context
        design_system_content = ""
        context_file = self.context.context_dir / "design_system.md"
        if context_file.exists():
            design_system_content = context_file.read_text()
        
        # Get technology
        config_file = design_dir / "config.yaml"
        technology = "flutter"
        if config_file.exists():
            for line in config_file.read_text().split("\n"):
                if line.startswith("technology:"):
                    technology = line.split(":", 1)[1].strip()
                    break
        
        # Resolve each conflict
        for i, conflict in enumerate(conflicts, 1):
            Console.section(f"Conflict {i}/{len(conflicts)}", conflict.get("context", "Unknown"))
            
            print(f"\n   Type: {conflict.get('type', 'unknown').upper()}")
            print(f"   Location: {conflict.get('location', 'unknown')}")
            print(f"\n   ┌─────────────────────────┐    ┌─────────────────────────┐")
            print(f"   │ DESIGN SYSTEM           │ vs │ HI-FI IMAGE             │")
            print(f"   │ {conflict.get('existing_value', '?'):<23} │    │ {conflict.get('new_value', '?'):<23} │")
            print(f"   └─────────────────────────┘    └─────────────────────────┘")
            
            # Get AI recommendation
            Console.log("\n   🤖 Getting AI recommendation...")
            
            recommendation = self._get_conflict_recommendation(conflict, design_system_content, technology)
            
            if recommendation:
                print(f"\n   🤖 AI RECOMMENDATION: {recommendation.get('recommendation', 'Unknown')}")
                print(f"      Confidence: {recommendation.get('confidence', 'Unknown')}")
                print(f"\n   📝 Reasoning:")
                reasoning = recommendation.get('reasoning', 'No reasoning provided')
                for line in reasoning.split('\n')[:5]:
                    print(f"      {line}")
                
                if recommendation.get('accessibility_note'):
                    print(f"\n   ♿ Accessibility: {recommendation.get('accessibility_note')}")
                
                if recommendation.get('suggestion'):
                    print(f"\n   💡 Suggestion: {recommendation.get('suggestion')}")
            
            # User decision
            print(f"\n   Options:")
            print(f"   1) ✅ Accept AI recommendation")
            print(f"   2) Use Design System value ({conflict.get('existing_value', '?')})")
            print(f"   3) Use Hi-Fi value ({conflict.get('new_value', '?')})")
            print(f"   4) Enter different value")
            print(f"   5) Skip for now")
            
            choice = Console.prompt("Select option [1-5]", default="1")
            
            if choice == "1" and recommendation:
                rec = recommendation.get('recommendation', '').lower()
                if 'hifi' in rec or 'hi-fi' in rec or 'image' in rec:
                    conflict["resolution"] = "use_hifi"
                    conflict["resolved_value"] = conflict.get("new_value")
                elif 'system' in rec or 'existing' in rec:
                    conflict["resolution"] = "use_system"
                    conflict["resolved_value"] = conflict.get("existing_value")
                else:
                    conflict["resolution"] = "ai_recommended"
                    conflict["resolved_value"] = recommendation.get('suggestion', conflict.get("new_value"))
            elif choice == "2":
                conflict["resolution"] = "use_system"
                conflict["resolved_value"] = conflict.get("existing_value")
            elif choice == "3":
                conflict["resolution"] = "use_hifi"
                conflict["resolved_value"] = conflict.get("new_value")
            elif choice == "4":
                custom_value = Console.prompt("Enter value")
                conflict["resolution"] = "custom"
                conflict["resolved_value"] = custom_value
            else:
                continue  # Skip
            
            conflict["resolved_at"] = datetime.now().isoformat()
            conflict["ai_recommendation"] = recommendation
            
            Console.success(f"Resolved: {conflict.get('resolution')} → {conflict.get('resolved_value')}")
        
        # Save updated manifest
        manifest["updated_at"] = datetime.now().isoformat()
        manifest_file.write_text(json.dumps(manifest, indent=2))
        
        # Update design_system.md if needed
        resolved_count = len([c for c in manifest.get("conflicts", []) if c.get("resolution")])
        Console.success(f"Resolved {resolved_count} conflict(s)")
        
        if Console.confirm("Update design_system.md with resolved values?", default=True):
            self._update_design_system_from_resolutions(manifest)
        
        return True
    
    def _get_conflict_recommendation(self, conflict: dict, design_system: str, technology: str) -> Optional[dict]:
        """Get AI recommendation for a design conflict"""
        prompt = f"""You are a senior UI/UX designer analyzing a design conflict.

## PROJECT TECHNOLOGY
{technology}

## THE CONFLICT
Type: {conflict.get('type', 'unknown')}
Element: {conflict.get('context', 'Unknown element')}
Location: {conflict.get('location', 'Unknown location')}

Design System Value: {conflict.get('existing_value', 'Not specified')}
Hi-Fi Image Value: {conflict.get('new_value', 'Not specified')}

## CURRENT DESIGN SYSTEM
{design_system[:5000] if design_system else 'No design system loaded'}

## ANALYSIS TASK
1. Analyze which value is more appropriate
2. Consider:
   - Visual consistency with the design system
   - Accessibility (contrast ratios for colors)
   - Modern design best practices
   - The specific context of this element
3. Provide a clear recommendation with reasoning
4. Rate your confidence (high/medium/low)

## OUTPUT FORMAT (exactly as shown)
RECOMMENDATION: [use_design_system | use_hifi | use_custom]
CONFIDENCE: [high | medium | low]
REASONING: [detailed explanation in 2-3 sentences]
ACCESSIBILITY_NOTE: [if relevant, e.g., contrast ratio concerns]
SUGGESTION: [if neither is ideal, suggest a better value]
"""
        
        response = self.ai.query(prompt)
        if not response:
            return None
        
        # Parse response
        result = {}
        for line in response.split('\n'):
            if line.startswith('RECOMMENDATION:'):
                result['recommendation'] = line.split(':', 1)[1].strip()
            elif line.startswith('CONFIDENCE:'):
                result['confidence'] = line.split(':', 1)[1].strip()
            elif line.startswith('REASONING:'):
                result['reasoning'] = line.split(':', 1)[1].strip()
            elif line.startswith('ACCESSIBILITY_NOTE:'):
                result['accessibility_note'] = line.split(':', 1)[1].strip()
            elif line.startswith('SUGGESTION:'):
                result['suggestion'] = line.split(':', 1)[1].strip()
        
        return result if result else None
    
    def _update_design_system_from_resolutions(self, manifest: dict) -> None:
        """Update design_system.md with resolved conflict values"""
        context_file = self.context.context_dir / "design_system.md"
        if not context_file.exists():
            Console.warning("No design_system.md to update")
            return
        
        content = context_file.read_text()
        updated = False
        
        for conflict in manifest.get("conflicts", []):
            if conflict.get("resolution") and conflict.get("resolved_value"):
                old_value = conflict.get("existing_value", "")
                new_value = conflict.get("resolved_value", "")
                
                if old_value and new_value and old_value != new_value:
                    if old_value in content:
                        content = content.replace(old_value, new_value)
                        updated = True
                        Console.log(f"   Updated: {old_value} → {new_value}")
        
        if updated:
            context_file.write_text(content)
            Console.success("Updated design_system.md")
        else:
            Console.log("No updates needed in design_system.md")
    
    def _design_validate(self) -> bool:
        """Validate design system against Hi-Fi images and detect conflicts"""
        Console.header("🎨 Design System: Validate")
        
        design_dir = self.context.speky_dir / DESIGN_DIR
        manifest_file = design_dir / "manifest.json"
        
        if not manifest_file.exists():
            Console.error("Design system not initialized. Run: speky design init")
            return False
        
        manifest = json.loads(manifest_file.read_text())
        
        # Load design system
        design_system_content = ""
        context_file = self.context.context_dir / "design_system.md"
        if context_file.exists():
            design_system_content = context_file.read_text()
        else:
            Console.warning("No design_system.md found. Run: speky design init")
            return False
        
        # Get technology
        config_file = design_dir / "config.yaml"
        technology = "flutter"
        if config_file.exists():
            for line in config_file.read_text().split("\n"):
                if line.startswith("technology:"):
                    technology = line.split(":", 1)[1].strip()
                    break
        
        # Collect all analyzed images
        analyzed_images = []
        for img_type in ["hifi", "lofi"]:
            for img in manifest.get(f"{img_type}_images", []):
                if img.get("analyzed") and img.get("analysis_path"):
                    analysis_path = self.context.speky_dir / img["analysis_path"]
                    if analysis_path.exists():
                        analyzed_images.append({
                            "filename": img["filename"],
                            "type": img_type,
                            "analysis": analysis_path.read_text()
                        })
        
        if not analyzed_images:
            Console.warning("No analyzed images found. Run: speky design analyze")
            return True
        
        Console.log(f"Validating {len(analyzed_images)} analyzed image(s) against design system...")
        
        # AI validation
        all_analyses = "\n\n---\n\n".join([
            f"## {img['filename']} ({img['type']})\n{img['analysis'][:3000]}"
            for img in analyzed_images[:5]  # Limit to 5 for token efficiency
        ])
        
        prompt = f"""Compare these Hi-Fi design analyses against the design system and identify conflicts.

## DESIGN SYSTEM
{design_system_content[:8000]}

## IMAGE ANALYSES
{all_analyses}

## TASK
Identify any conflicts between the design system and the analyzed images:

For each conflict found, output in this EXACT format:
---
CONFLICT_TYPE: [color | typography | spacing | radius | shadow | layout]
LOCATION: [image filename and element]
CONTEXT: [what element this is, e.g., "Primary button background"]
DESIGN_SYSTEM_VALUE: [value from design system]
IMAGE_VALUE: [value from image analysis]
SEVERITY: [high | medium | low]
---

If no conflicts found, output: NO_CONFLICTS_FOUND

Be specific with values (hex codes, pixel values).
Only report actual conflicts, not missing information."""

        Console.section("Running Validation")
        response = self.ai.query(prompt, max_tokens=4096)
        
        if not response:
            Console.error("Validation failed")
            return False
        
        # Parse conflicts
        new_conflicts = []
        
        if "NO_CONFLICTS_FOUND" in response:
            Console.success("✅ No conflicts found! Design system matches Hi-Fi images.")
        else:
            # Parse conflict blocks
            conflict_blocks = response.split("---")
            for block in conflict_blocks:
                if "CONFLICT_TYPE:" in block:
                    conflict = {"id": f"conflict-{len(new_conflicts)+1}"}
                    for line in block.split('\n'):
                        if line.startswith('CONFLICT_TYPE:'):
                            conflict['type'] = line.split(':', 1)[1].strip().lower()
                        elif line.startswith('LOCATION:'):
                            conflict['location'] = line.split(':', 1)[1].strip()
                        elif line.startswith('CONTEXT:'):
                            conflict['context'] = line.split(':', 1)[1].strip()
                        elif line.startswith('DESIGN_SYSTEM_VALUE:'):
                            conflict['existing_value'] = line.split(':', 1)[1].strip()
                        elif line.startswith('IMAGE_VALUE:'):
                            conflict['new_value'] = line.split(':', 1)[1].strip()
                        elif line.startswith('SEVERITY:'):
                            conflict['severity'] = line.split(':', 1)[1].strip().lower()
                    
                    if conflict.get('type') and conflict.get('existing_value'):
                        conflict['detected_at'] = datetime.now().isoformat()
                        new_conflicts.append(conflict)
            
            if new_conflicts:
                Console.warning(f"Found {len(new_conflicts)} conflict(s)")
                
                for conflict in new_conflicts:
                    severity_icon = "🔴" if conflict.get('severity') == 'high' else "🟡" if conflict.get('severity') == 'medium' else "🟢"
                    print(f"\n   {severity_icon} [{conflict.get('type', '?').upper()}] {conflict.get('context', 'Unknown')}")
                    print(f"      Location: {conflict.get('location', '?')}")
                    print(f"      Design System: {conflict.get('existing_value', '?')}")
                    print(f"      Hi-Fi Image: {conflict.get('new_value', '?')}")
                
                # Add to manifest
                existing_conflicts = manifest.get("conflicts", [])
                
                # Avoid duplicates
                existing_keys = set(
                    f"{c.get('type')}:{c.get('existing_value')}:{c.get('new_value')}"
                    for c in existing_conflicts
                )
                
                for conflict in new_conflicts:
                    key = f"{conflict.get('type')}:{conflict.get('existing_value')}:{conflict.get('new_value')}"
                    if key not in existing_keys:
                        existing_conflicts.append(conflict)
                
                manifest["conflicts"] = existing_conflicts
                manifest["updated_at"] = datetime.now().isoformat()
                manifest_file.write_text(json.dumps(manifest, indent=2))
                
                print(f"\n   Run: speky design resolve")
        
        return True

    def _design_sync(self, apply_changes: bool = False) -> bool:
        """Sync design system document with implementation code"""
        Console.header("🎨 Design System: Sync")
        
        design_dir = self.context.speky_dir / DESIGN_DIR
        manifest_file = design_dir / "manifest.json"
        
        if not manifest_file.exists():
            Console.error("Design system not initialized. Run: speky design init")
            return False
        
        manifest = json.loads(manifest_file.read_text())
        
        # Get technology
        config_file = design_dir / "config.yaml"
        technology = "flutter"
        if config_file.exists():
            for line in config_file.read_text().split("\n"):
                if line.startswith("technology:"):
                    technology = line.split(":", 1)[1].strip()
                    break
        
        # Check for sync_results.json
        sync_results_file = design_dir / "sync_results.json"
        
        if apply_changes and sync_results_file.exists():
            # Apply mode - process existing results
            return self._design_sync_apply(sync_results_file, technology)
        
        if sync_results_file.exists() and not apply_changes:
            # Results exist, ask what to do
            Console.log("Found existing sync_results.json")
            print("\n   Options:")
            print("   1) Review and apply existing results")
            print("   2) Generate new analysis task for IDE")
            print("   3) Cancel")
            
            choice = Console.prompt("Select option [1-3]", default="1")
            
            if choice == "1":
                return self._design_sync_apply(sync_results_file, technology)
            elif choice == "3":
                Console.log("Cancelled")
                return True
            # choice == "2" falls through to generate new task
        
        # Generate sync task for IDE
        Console.section("Generating Sync Analysis Task")
        
        # Find design system document
        design_system_path = None
        design_system_content = ""
        
        system_doc = manifest.get("system_doc")
        if system_doc:
            doc_path = self.context.speky_dir / system_doc
            if doc_path.exists():
                design_system_path = str(doc_path.relative_to(self.project_root))
                design_system_content = doc_path.read_text()
        
        if not design_system_content:
            # Try context summary
            context_file = self.context.context_dir / "design_system.md"
            if context_file.exists():
                design_system_path = str(context_file.relative_to(self.project_root))
                design_system_content = context_file.read_text()
        
        if not design_system_content:
            Console.error("No design system document found. Run: speky design init")
            return False
        
        # Detect implementation files based on technology
        implementation_paths = self._detect_design_implementation_files(technology)
        
        if not implementation_paths:
            Console.warning("No implementation files detected. Please specify paths manually.")
            paths_input = Console.prompt("Enter implementation file paths (comma-separated)")
            if paths_input:
                implementation_paths = [p.strip() for p in paths_input.split(",")]
            else:
                return False
        
        Console.log(f"Found {len(implementation_paths)} implementation file(s)")
        for p in implementation_paths[:5]:
            print(f"   • {p}")
        if len(implementation_paths) > 5:
            print(f"   ... and {len(implementation_paths) - 5} more")
        
        # Generate task file
        task_content = Prompts.design_sync_task(
            technology=technology,
            design_system_path=design_system_path,
            implementation_paths=implementation_paths,
            design_system_content=design_system_content
        )
        
        task_file = design_dir / "sync_task.md"
        task_file.write_text(task_content)
        
        Console.success(f"Created: {task_file.relative_to(self.project_root)}")
        
        print(f"\n📋 Next Steps:")
        print(f"   1. Open your IDE and read: .speky/design/sync_task.md")
        print(f"   2. IDE will analyze implementation files")
        print(f"   3. IDE writes results to: .speky/design/sync_results.json")
        print(f"   4. Run: speky design sync --analyze  (to apply changes)")
        
        # Wait for IDE to complete
        if Console.confirm("\nWait for IDE to complete analysis?", default=True):
            Console.log("Waiting for sync_results.json...")
            Console.log("(Press Ctrl+C to cancel, or complete the task in your IDE)")
            
            import time
            max_wait = 600  # 10 minutes
            waited = 0
            
            while waited < max_wait:
                if sync_results_file.exists():
                    # Check if file was recently modified
                    mtime = sync_results_file.stat().st_mtime
                    if mtime > time.time() - 5:  # Modified in last 5 seconds
                        Console.success("sync_results.json detected!")
                        return self._design_sync_apply(sync_results_file, technology)
                
                time.sleep(2)
                waited += 2
                
                if waited % 30 == 0:
                    Console.log(f"   Still waiting... ({waited}s)")
            
            Console.warning("Timeout waiting for results. Run 'speky design sync' again when ready.")
        
        return True
    
    def _detect_design_implementation_files(self, technology: str) -> list:
        """Detect design system implementation files based on technology"""
        paths = []
        
        if technology == "flutter":
            # Common Flutter theme file locations
            patterns = [
                "lib/core/theme/*.dart",
                "lib/theme/*.dart",
                "lib/config/theme/*.dart",
                "lib/shared/theme/*.dart",
                "lib/ui/theme/*.dart",
                "lib/styles/*.dart",
            ]
            for pattern in patterns:
                for f in self.project_root.glob(pattern):
                    if f.is_file():
                        paths.append(str(f.relative_to(self.project_root)))
        
        elif technology in ["react", "vue", "svelte"]:
            # Common web framework theme locations
            patterns = [
                "src/theme/*.ts",
                "src/theme/*.tsx",
                "src/theme/*.js",
                "src/styles/*.ts",
                "src/styles/*.css",
                "src/styles/*.scss",
                "src/config/theme*.ts",
                "tailwind.config.js",
                "tailwind.config.ts",
            ]
            for pattern in patterns:
                for f in self.project_root.glob(pattern):
                    if f.is_file():
                        paths.append(str(f.relative_to(self.project_root)))
        
        return paths
    
    def _design_sync_apply(self, results_file: Path, technology: str) -> bool:
        """Apply sync results - interactive review and update design system"""
        Console.section("Processing Sync Results")
        
        try:
            results = json.loads(results_file.read_text())
        except json.JSONDecodeError as e:
            Console.error(f"Invalid sync_results.json: {e}")
            return False
        
        additions = results.get("additions", [])
        missing = results.get("missing", [])
        conflicts = results.get("conflicts", [])
        summary = results.get("summary", {})
        
        # Display summary
        Console.section("Sync Summary")
        print(f"   📊 Files Analyzed: {summary.get('files_analyzed', 'unknown')}")
        print(f"   ➕ Additions (code → doc): {len(additions)}")
        print(f"   ❌ Missing (doc → code): {len(missing)}")
        print(f"   ⚠️  Conflicts: {len(conflicts)}")
        
        if not additions and not conflicts:
            Console.success("Design system is in sync with implementation!")
            if missing:
                Console.warning(f"Note: {len(missing)} token(s) in design system are not yet implemented")
                if Console.confirm("Show missing implementations?", default=False):
                    for item in missing[:10]:
                        print(f"   • [{item.get('category', '?')}] {item.get('name', '?')}: {item.get('value', '?')}")
            return True
        
        # Show additions
        if additions:
            Console.section(f"Additions ({len(additions)} tokens to add to design system)")
            
            by_category = {}
            for item in additions:
                cat = item.get("category", "other")
                by_category.setdefault(cat, []).append(item)
            
            for cat, items in by_category.items():
                print(f"\n   📁 {cat.upper()} ({len(items)} items)")
                for item in items[:5]:
                    print(f"      • {item.get('name', '?')}: {item.get('value', '?')}")
                    if item.get('file'):
                        print(f"        └─ {item.get('file')}:{item.get('line', '?')}")
                if len(items) > 5:
                    print(f"      ... and {len(items) - 5} more")
        
        # Show conflicts
        if conflicts:
            Console.section(f"Conflicts ({len(conflicts)} value mismatches)")
            
            for conflict in conflicts[:10]:
                severity_icon = "🔴" if conflict.get('severity') == 'high' else "🟡" if conflict.get('severity') == 'medium' else "🟢"
                print(f"\n   {severity_icon} [{conflict.get('category', '?')}] {conflict.get('name', '?')}")
                print(f"      Doc:  {conflict.get('doc_value', '?')}")
                print(f"      Code: {conflict.get('code_value', '?')}")
                if conflict.get('file'):
                    print(f"      File: {conflict.get('file')}:{conflict.get('line', '?')}")
        
        # Options
        print(f"\n📋 Options:")
        print(f"   1) Update design system with ALL additions and conflicts (use code values)")
        print(f"   2) Review each change interactively")
        print(f"   3) Export changes to markdown for manual review")
        print(f"   4) Cancel")
        
        choice = Console.prompt("Select option [1-4]", default="1")
        
        if choice == "4":
            Console.log("Cancelled")
            return True
        
        if choice == "3":
            return self._design_sync_export(additions, conflicts, missing)
        
        if choice == "2":
            # Interactive review
            approved_additions = []
            approved_conflicts = []
            
            if additions:
                Console.section("Review Additions")
                for i, item in enumerate(additions, 1):
                    print(f"\n   [{i}/{len(additions)}] {item.get('category', '?')}.{item.get('name', '?')}")
                    print(f"   Value: {item.get('value', '?')}")
                    if item.get('code_snippet'):
                        print(f"   Code: {item.get('code_snippet', '')[:80]}")
                    
                    if Console.confirm("Add to design system?", default=True):
                        approved_additions.append(item)
            
            if conflicts:
                Console.section("Review Conflicts")
                for i, conflict in enumerate(conflicts, 1):
                    print(f"\n   [{i}/{len(conflicts)}] {conflict.get('category', '?')}.{conflict.get('name', '?')}")
                    print(f"   Doc value:  {conflict.get('doc_value', '?')}")
                    print(f"   Code value: {conflict.get('code_value', '?')}")
                    
                    print("   Options: [C]ode value, [D]oc value, [S]kip")
                    choice = Console.prompt("Select", default="C").upper()
                    
                    if choice == "C":
                        approved_conflicts.append(conflict)
                    elif choice == "D":
                        pass  # Keep doc value, don't add to approved
            
            additions = approved_additions
            conflicts = approved_conflicts
        
        if not additions and not conflicts:
            Console.log("No changes to apply")
            return True
        
        # Load design system document
        design_dir = self.context.speky_dir / DESIGN_DIR
        manifest = json.loads((design_dir / "manifest.json").read_text())
        
        design_system_path = None
        design_system_content = ""
        
        system_doc = manifest.get("system_doc")
        if system_doc:
            doc_path = self.context.speky_dir / system_doc
            if doc_path.exists():
                design_system_path = doc_path
                design_system_content = doc_path.read_text()
        
        if not design_system_content:
            Console.error("Could not load design system document")
            return False
        
        # Use AI to update design system
        Console.section("Updating Design System")
        Console.log("Generating updated design system document...")
        
        updated_content = self.ai.query(
            Prompts.design_sync_apply(
                additions=additions,
                missing=missing,
                conflicts=conflicts,
                design_system_content=design_system_content,
                technology=technology
            ),
            max_tokens=16000,
            use_streaming=True
        )
        
        if not updated_content:
            Console.error("Failed to generate updated design system")
            return False
        
        # Show diff summary
        original_lines = len(design_system_content.split('\n'))
        updated_lines = len(updated_content.split('\n'))
        
        Console.log(f"   Original: {original_lines} lines")
        Console.log(f"   Updated:  {updated_lines} lines")
        Console.log(f"   Change:   {updated_lines - original_lines:+d} lines")
        
        # Confirm and save
        if Console.confirm("Save updated design system?", default=True):
            # Backup original
            backup_path = design_system_path.with_suffix('.md.backup')
            backup_path.write_text(design_system_content)
            Console.log(f"   Backup saved: {backup_path.name}")
            
            # Save updated
            design_system_path.write_text(updated_content)
            Console.success(f"Updated: {design_system_path.relative_to(self.project_root)}")
            
            # Update context summary
            if Console.confirm("Regenerate context summary?", default=True):
                summary = self.ai.query(Prompts.summarize_design_system(updated_content, technology))
                if summary:
                    context_file = self.context.context_dir / "design_system.md"
                    context_file.write_text(summary)
                    Console.success("Updated: .speky/context/design_system.md")
            
            # Archive sync results
            archive_path = design_dir / f"sync_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            results_file.rename(archive_path)
            Console.log(f"   Archived results: {archive_path.name}")
        
        return True
    
    def _design_sync_export(self, additions: list, conflicts: list, missing: list) -> bool:
        """Export sync changes to markdown for manual review"""
        design_dir = self.context.speky_dir / DESIGN_DIR
        
        content = f"""# Design System Sync Report

Generated: {datetime.now().isoformat()}

## Summary

- **Additions** (code → doc): {len(additions)}
- **Conflicts** (value mismatches): {len(conflicts)}
- **Missing** (doc → code): {len(missing)}

---

## Additions (Tokens to Add to Design System)

"""
        
        if additions:
            by_category = {}
            for item in additions:
                cat = item.get("category", "other")
                by_category.setdefault(cat, []).append(item)
            
            for cat, items in sorted(by_category.items()):
                content += f"### {cat.title()}\n\n"
                for item in items:
                    content += f"- **{item.get('name', '?')}**: `{item.get('value', '?')}`\n"
                    if item.get('file'):
                        content += f"  - File: `{item.get('file')}:{item.get('line', '?')}`\n"
                    if item.get('code_snippet'):
                        content += f"  - Code: `{item.get('code_snippet', '')[:60]}`\n"
                content += "\n"
        else:
            content += "*No additions needed*\n\n"
        
        content += "---\n\n## Conflicts (Value Mismatches)\n\n"
        
        if conflicts:
            for conflict in conflicts:
                severity = conflict.get('severity', 'medium')
                icon = "🔴" if severity == 'high' else "🟡" if severity == 'medium' else "🟢"
                content += f"### {icon} {conflict.get('category', '?')}.{conflict.get('name', '?')}\n\n"
                content += f"| Source | Value |\n|--------|-------|\n"
                content += f"| Design System | `{conflict.get('doc_value', '?')}` |\n"
                content += f"| Implementation | `{conflict.get('code_value', '?')}` |\n\n"
                if conflict.get('file'):
                    content += f"File: `{conflict.get('file')}:{conflict.get('line', '?')}`\n\n"
        else:
            content += "*No conflicts found*\n\n"
        
        content += "---\n\n## Missing (Not Yet Implemented)\n\n"
        
        if missing:
            for item in missing:
                content += f"- **{item.get('name', '?')}**: `{item.get('value', '?')}`\n"
                if item.get('doc_section'):
                    content += f"  - Section: {item.get('doc_section')}\n"
        else:
            content += "*All design system tokens are implemented*\n\n"
        
        export_file = design_dir / "sync_report.md"
        export_file.write_text(content)
        
        Console.success(f"Exported: {export_file.relative_to(self.project_root)}")
        print(f"\n   Review the report and manually update the design system as needed.")
        
        return True

    # -------------------------------------------------------------------------
    # Command: cleanup
    # -------------------------------------------------------------------------
    def cmd_cleanup(self, dry_run: bool = False) -> bool:
        """Clean up temporary and clutter files from project root and .speky directory"""
        if not self._require_init():
            return False
        
        Console.header("🧹 Cleanup: Remove Clutter Files")
        
        # Patterns for files that should NOT be in root or .speky/ directly
        clutter_patterns = [
            "*_SPEC.md",
            "IMPLEMENTATION_COMPLETE.md",
            "implementation_notes.md",
            "analysis_*.md",
            "temp_*.md",
            "*.tmp.md",
            "BILLING_SETUP.md",
            "*_SETUP.md",
        ]
        
        # Find clutter files in project root
        clutter_files = []
        for pattern in clutter_patterns:
            for f in self.project_root.glob(pattern):
                if f.is_file() and f.name != "README.md":
                    clutter_files.append(f)
        
        # Also check .speky/ directory directly (not subdirs like specs/, context/)
        # Valid subdirs: specs/, stories/, context/, temp/, project_ops/
        # Only files directly in .speky/ are checked for clutter
        for f in self.context.speky_dir.iterdir():
            if f.is_file():
                # Any .md file directly in .speky/ is clutter (except config files)
                if f.suffix == ".md":
                    clutter_files.append(f)
                # Also check for clutter patterns
                for pattern in clutter_patterns:
                    if f.match(pattern):
                        if f not in clutter_files:
                            clutter_files.append(f)
        
        # Also check for .speky/temp directory
        temp_dir = self.context.speky_dir / "temp"
        temp_files = []
        if temp_dir.exists():
            temp_files = list(temp_dir.rglob("*"))
        
        if not clutter_files and not temp_files:
            Console.success("No clutter files found - project is clean!")
            return True
        
        # Show what will be cleaned
        if clutter_files:
            Console.section("Clutter Files Found")
            for f in clutter_files:
                # Show relative path from project root
                try:
                    rel_path = f.relative_to(self.project_root)
                    print(f"  ❌ {rel_path}")
                except ValueError:
                    print(f"  ❌ {f.name}")
        
        if temp_files:
            Console.section("Temporary Files (.speky/temp/)")
            for f in temp_files:
                if f.is_file():
                    print(f"  ❌ {f.relative_to(self.project_root)}")
        
        if dry_run:
            Console.log("Dry run - no files deleted")
            return True
        
        # Confirm deletion
        total = len(clutter_files) + len([f for f in temp_files if f.is_file()])
        if not Console.confirm(f"Delete {total} file(s)?", default=False):
            Console.log("Cleanup cancelled")
            return False
        
        # Delete files
        deleted = 0
        for f in clutter_files:
            try:
                f.unlink()
                deleted += 1
            except Exception as e:
                Console.warning(f"Could not delete {f.name}: {e}")
        
        # Clean temp directory
        if temp_dir.exists():
            import shutil
            try:
                shutil.rmtree(temp_dir)
                deleted += len([f for f in temp_files if f.is_file()])
            except Exception as e:
                Console.warning(f"Could not clean temp directory: {e}")
        
        Console.success(f"Cleaned up {deleted} file(s)")
        return True

    # =========================================================================
    # PHASE MANAGEMENT - Multi-Spec Coordination Layer
    # =========================================================================
    
    def _load_phase(self, phase_id: str) -> Optional[dict]:
        """Load a phase manifest by ID"""
        phase_dir = self.context.phases_dir / phase_id
        manifest_file = phase_dir / "manifest.yaml"
        
        if not manifest_file.exists():
            return None
        
        try:
            content = manifest_file.read_text()
            # Simple YAML parser for our structured format
            return self._parse_yaml(content)
        except Exception as e:
            Console.warning(f"Could not load phase {phase_id}: {e}")
            return None
    
    def _save_phase(self, phase_id: str, data: dict) -> bool:
        """Save a phase manifest"""
        phase_dir = self.context.phases_dir / phase_id
        phase_dir.mkdir(parents=True, exist_ok=True)
        
        manifest_file = phase_dir / "manifest.yaml"
        
        try:
            content = self._to_yaml(data)
            manifest_file.write_text(content)
            return True
        except Exception as e:
            Console.error(f"Could not save phase {phase_id}: {e}")
            return False
    
    def _add_spec_to_phase(self, spec_id: str, phase_id: str) -> bool:
        """Add a spec to a phase"""
        phase = self._load_phase(phase_id)
        if not phase:
            Console.error(f"Phase not found: {phase_id}")
            return False
        
        # Get current specs in phase
        specs = phase.get("specs", [])
        
        # Check if already in phase
        existing_ids = [s.get("id") if isinstance(s, dict) else s for s in specs]
        if spec_id in existing_ids:
            Console.warning(f"Spec {spec_id} already in phase {phase_id}")
            return True
        
        # Add spec
        specs.append({"id": spec_id})
        phase["specs"] = specs
        
        # Save
        if self._save_phase(phase_id, phase):
            Console.success(f"Added spec {spec_id} to phase {phase_id}")
            return True
        return False
    
    def _get_spec_phase(self, spec_id: str) -> Optional[dict]:
        """Find which phase a spec belongs to"""
        phases = self._get_all_phases()
        
        for phase in phases:
            specs = phase.get("specs", [])
            for spec in specs:
                sid = spec.get("id") if isinstance(spec, dict) else spec
                if sid == spec_id:
                    return phase
        
        return None
    
    def _get_all_phases(self) -> List[dict]:
        """Get all phases with their data"""
        phases = []
        
        if not self.context.phases_dir.exists():
            return phases
        
        for phase_dir in sorted(self.context.phases_dir.iterdir()):
            if not phase_dir.is_dir():
                continue
            
            manifest_file = phase_dir / "manifest.yaml"
            if manifest_file.exists():
                try:
                    data = self._parse_yaml(manifest_file.read_text())
                    data["_dir"] = phase_dir.name
                    phases.append(data)
                except Exception:
                    continue
        
        return phases
    
    def _load_roadmap(self) -> Optional[dict]:
        """Load the master phase roadmap"""
        roadmap_file = self.context.phases_dir / "roadmap.yaml"
        
        if not roadmap_file.exists():
            return None
        
        try:
            return self._parse_yaml(roadmap_file.read_text())
        except Exception:
            return None
    
    def _save_roadmap(self, data: dict) -> bool:
        """Save the master phase roadmap"""
        roadmap_file = self.context.phases_dir / "roadmap.yaml"
        
        try:
            content = self._to_yaml(data)
            roadmap_file.write_text(content)
            return True
        except Exception as e:
            Console.error(f"Could not save roadmap: {e}")
            return False
    
    def _parse_yaml(self, content: str) -> dict:
        """Simple YAML parser for our structured format"""
        import re
        
        result = {}
        current_key = None
        current_list = None
        current_dict = None
        indent_stack = [0]
        key_stack = [result]
        
        lines = content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Skip comments and empty lines
            if not stripped or stripped.startswith('#'):
                i += 1
                continue
            
            # Calculate indent
            indent = len(line) - len(line.lstrip())
            
            # Handle list items
            if stripped.startswith('- '):
                item_content = stripped[2:].strip()
                
                # Check if it's a dict item (has colon)
                if ':' in item_content and not item_content.startswith('"'):
                    # Dict in list
                    if current_list is not None:
                        item_dict = {}
                        # Parse key: value
                        key, _, value = item_content.partition(':')
                        key = key.strip().strip('"').strip("'")
                        value = value.strip().strip('"').strip("'")
                        if value:
                            item_dict[key] = self._parse_yaml_value(value)
                        
                        # Look for continuation lines at deeper indent
                        j = i + 1
                        while j < len(lines):
                            next_line = lines[j]
                            next_stripped = next_line.strip()
                            next_indent = len(next_line) - len(next_line.lstrip())
                            
                            if not next_stripped or next_stripped.startswith('#'):
                                j += 1
                                continue
                            
                            if next_indent <= indent:
                                break
                            
                            if ':' in next_stripped:
                                k, _, v = next_stripped.partition(':')
                                k = k.strip().strip('"').strip("'")
                                v = v.strip().strip('"').strip("'")
                                if v:
                                    item_dict[k] = self._parse_yaml_value(v)
                                elif not next_stripped.startswith('- '):
                                    # Nested list or dict coming
                                    item_dict[k] = []
                            elif next_stripped.startswith('- '):
                                # Add to last key's list
                                for dict_key in reversed(list(item_dict.keys())):
                                    if isinstance(item_dict[dict_key], list):
                                        item_val = next_stripped[2:].strip().strip('"').strip("'")
                                        item_dict[dict_key].append(self._parse_yaml_value(item_val))
                                        break
                            j += 1
                        
                        current_list.append(item_dict)
                        i = j
                        continue
                else:
                    # Simple list item
                    if current_list is not None:
                        current_list.append(self._parse_yaml_value(item_content))
            
            # Handle key: value
            elif ':' in stripped:
                key, _, value = stripped.partition(':')
                key = key.strip().strip('"').strip("'")
                value = value.strip()
                
                # Pop back to correct level
                while len(indent_stack) > 1 and indent <= indent_stack[-1]:
                    indent_stack.pop()
                    key_stack.pop()
                
                target = key_stack[-1]
                
                if value:
                    # Simple value
                    if isinstance(target, dict):
                        target[key] = self._parse_yaml_value(value)
                    current_list = None
                else:
                    # Start of nested structure
                    # Look ahead to see if it's a list or dict
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j]
                        next_stripped = next_line.strip()
                        if next_stripped and not next_stripped.startswith('#'):
                            if next_stripped.startswith('- '):
                                # It's a list
                                new_list = []
                                if isinstance(target, dict):
                                    target[key] = new_list
                                current_list = new_list
                            else:
                                # It's a dict
                                new_dict = {}
                                if isinstance(target, dict):
                                    target[key] = new_dict
                                indent_stack.append(indent)
                                key_stack.append(new_dict)
                                current_list = None
                            break
                        j += 1
            
            i += 1
        
        return result
    
    def _parse_yaml_value(self, value: str):
        """Parse a YAML value string"""
        # Strip inline comments (but not inside quotes)
        if not value.startswith('"') and not value.startswith("'"):
            # Find # that's not inside brackets
            bracket_depth = 0
            for i, c in enumerate(value):
                if c == '[':
                    bracket_depth += 1
                elif c == ']':
                    bracket_depth -= 1
                elif c == '#' and bracket_depth == 0:
                    value = value[:i]
                    break
        
        value = value.strip().strip('"').strip("'")
        
        # Empty value
        if not value:
            return ""
        
        # Boolean
        if value.lower() in ('true', 'yes'):
            return True
        if value.lower() in ('false', 'no'):
            return False
        
        # Number
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass
        
        # Empty list notation []
        if value == '[]':
            return []
        
        # List notation [a, b, c]
        if value.startswith('[') and value.endswith(']'):
            items = value[1:-1].split(',')
            return [item.strip().strip('"').strip("'") for item in items if item.strip()]
        
        return value
    
    def _to_yaml(self, data: dict, indent: int = 0) -> str:
        """Convert dict to YAML string"""
        lines = []
        prefix = "  " * indent
        
        for key, value in data.items():
            if key.startswith('_'):  # Skip internal keys
                continue
            
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(self._to_yaml(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        # First item on same line as dash
                        first = True
                        for k, v in item.items():
                            if first:
                                if isinstance(v, list):
                                    lines.append(f"{prefix}  - {k}:")
                                    for sub_item in v:
                                        lines.append(f"{prefix}      - \"{sub_item}\"")
                                else:
                                    lines.append(f"{prefix}  - {k}: \"{v}\"")
                                first = False
                            else:
                                if isinstance(v, list):
                                    lines.append(f"{prefix}    {k}:")
                                    for sub_item in v:
                                        lines.append(f"{prefix}      - \"{sub_item}\"")
                                else:
                                    lines.append(f"{prefix}    {k}: \"{v}\"")
                    else:
                        lines.append(f"{prefix}  - \"{item}\"")
            elif isinstance(value, bool):
                lines.append(f"{prefix}{key}: {str(value).lower()}")
            elif isinstance(value, (int, float)):
                lines.append(f"{prefix}{key}: {value}")
            else:
                lines.append(f"{prefix}{key}: \"{value}\"")
        
        return '\n'.join(lines)
    
    def _get_phase_specs(self, phase: dict) -> List[dict]:
        """Get all specs included in a phase with their status"""
        specs = []
        phase_specs = phase.get("specs", [])
        
        for spec_entry in phase_specs:
            spec_id = spec_entry.get("id") if isinstance(spec_entry, dict) else spec_entry
            
            # Find the spec
            for spec_dir in self.context.specs_dir.glob(f"{spec_id}*"):
                if spec_dir.is_dir():
                    status_file = spec_dir / "status.json"
                    spec_file = spec_dir / "spec.md"
                    
                    spec_data = {
                        "id": spec_id,
                        "dir": spec_dir.name,
                        "path": spec_dir,
                    }
                    
                    if status_file.exists():
                        try:
                            status = json.loads(status_file.read_text())
                            spec_data.update(status)
                        except Exception:
                            pass
                    
                    if spec_file.exists():
                        spec_data["spec_content"] = spec_file.read_text()
                    
                    # Add phase-specific scope if provided
                    if isinstance(spec_entry, dict):
                        spec_data["phase_scope"] = spec_entry.get("scope", "full")
                        spec_data["phase_features"] = spec_entry.get("features", [])
                        spec_data["phase_excludes"] = spec_entry.get("excludes", [])
                    
                    specs.append(spec_data)
                    break
        
        return specs
    
    def _validate_phase_prerequisites(self, phase: dict) -> tuple:
        """Check if phase prerequisites are met. Returns (met, unmet_list)"""
        prerequisites = phase.get("prerequisites", [])
        unmet = []
        
        for prereq in prerequisites:
            # Handle both string and dict format
            if isinstance(prereq, dict):
                prereq_desc = prereq.get("description", "")
                prereq_validation = prereq.get("validation", "")
            else:
                prereq_desc = str(prereq)
                prereq_validation = ""
            
            prereq_lower = prereq_desc.lower()
            
            if "project initialized" in prereq_lower or "flutter" in prereq_lower:
                # Check for common project files
                if not any([
                    (self.project_root / "pubspec.yaml").exists(),
                    (self.project_root / "package.json").exists(),
                    (self.project_root / "requirements.txt").exists(),
                    (self.project_root / "Cargo.toml").exists(),
                    (self.project_root / "go.mod").exists(),
                ]):
                    unmet.append(prereq_desc)
            elif "database" in prereq_lower or "drift" in prereq_lower:
                # Check for database setup indicators
                if prereq_validation:
                    # Try to validate if validation path is provided
                    validation_path = prereq_validation.split(" ")[0]  # e.g., "lib/database/database.dart exists"
                    if validation_path.endswith(".dart") or validation_path.endswith(".ts") or validation_path.endswith(".py"):
                        if not (self.project_root / validation_path).exists():
                            unmet.append(prereq_desc)
                # pass  # Let it pass for now - hard to validate
            else:
                # Generic prereq - just note it
                pass
        
        return len(unmet) == 0, unmet
    
    def _calculate_phase_progress(self, phase: dict) -> dict:
        """Calculate progress for a phase"""
        specs = self._get_phase_specs(phase)
        deliverables = phase.get("deliverables", [])
        
        completed_specs = sum(1 for s in specs if s.get("status") == "completed")
        total_specs = len(specs)
        
        # Load phase status for deliverable tracking
        phase_id = phase.get("id", phase.get("_dir", "unknown"))
        phase_dir = self.context.phases_dir / phase_id
        status_file = phase_dir / "status.json"
        
        verified_deliverables = []
        if status_file.exists():
            try:
                status_data = json.loads(status_file.read_text())
                verified_deliverables = status_data.get("verified_deliverables", [])
            except Exception:
                pass
        
        return {
            "specs_completed": completed_specs,
            "specs_total": total_specs,
            "specs_percent": int((completed_specs / total_specs * 100)) if total_specs > 0 else 0,
            "deliverables_verified": len(verified_deliverables),
            "deliverables_total": len(deliverables),
            "deliverables_percent": int((len(verified_deliverables) / len(deliverables) * 100)) if deliverables else 100,
        }
    
    # -------------------------------------------------------------------------
    # Command: phases (list, show, status, start, complete, guide, suggest)
    # -------------------------------------------------------------------------
    def cmd_phases(self, action: str, phase_id: str = None, for_ai: bool = False) -> bool:
        """Manage project phases"""
        if not self._require_init():
            return False
        
        if action == "list":
            return self._cmd_phases_list()
        elif action == "show":
            return self._cmd_phases_show(phase_id)
        elif action == "status":
            return self._cmd_phases_status()
        elif action == "start":
            return self._cmd_phases_start(phase_id)
        elif action == "complete":
            return self._cmd_phases_complete(phase_id)
        elif action == "guide":
            return self._cmd_phases_guide(phase_id, for_ai=for_ai)
        elif action == "create":
            return self._cmd_phases_create(phase_id)
        elif action == "suggest":
            return self._cmd_phases_suggest()
        else:
            Console.error(f"Unknown action: {action}")
            return False
    
    def _cmd_phases_list(self) -> bool:
        """List all phases"""
        Console.header("📅 Project Phases")
        
        phases = self._get_all_phases()
        roadmap = self._load_roadmap()
        
        if not phases and not roadmap:
            Console.warning("No phases defined yet")
            print("\n   To create phases:")
            print("   1. Run: speky phases create phase-1")
            print("   2. Edit: .speky/phases/phase-1/manifest.yaml")
            print("\n   Or import a roadmap from your PRD:")
            print("   1. Place roadmap in .speky/phases/roadmap.yaml")
            return True
        
        # Show roadmap summary if exists
        if roadmap:
            Console.section("📋 Roadmap Overview")
            print(f"   Project: {roadmap.get('project', 'Unknown')}")
            print(f"   Total Phases: {roadmap.get('total_phases', len(phases))}")
            print(f"   Estimated Duration: {roadmap.get('estimated_duration', 'TBD')}")
            current = roadmap.get('current_phase', 'Not started')
            print(f"   Current Phase: {current}")
        
        # List phases
        Console.section("📅 Phases")
        
        # Load all specs for blocking detection
        all_specs = []
        for spec_dir in self.context.specs_dir.glob("*/"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                try:
                    spec_status = json.loads(status_file.read_text())
                    if spec_status.get("status") != "deprecated":
                        all_specs.append(spec_status)
                except Exception:
                    continue
        
        for phase in phases:
            phase_id = phase.get("id", phase.get("_dir", "unknown"))
            name = phase.get("name", "Unnamed")
            status = phase.get("status", "not_started")
            duration = phase.get("duration", "TBD")
            
            # Status icon
            status_icons = {
                "not_started": "⬜",
                "in_progress": "🔄",
                "testing": "🧪",
                "complete": "✅",
                "blocked": "🚫",
            }
            icon = status_icons.get(status, "⬜")
            
            # Progress
            progress = self._calculate_phase_progress(phase)
            
            print(f"\n   {icon} {phase_id}: {name}")
            print(f"      Duration: {duration}")
            print(f"      Specs: {progress['specs_completed']}/{progress['specs_total']} ({progress['specs_percent']}%)")
            print(f"      Deliverables: {progress['deliverables_verified']}/{progress['deliverables_total']}")
            
            # Check for blocking if phase is in progress
            if status == "in_progress":
                blocked_specs = self._check_phase_blocking(phase, all_specs)
                if blocked_specs:
                    print(f"      ⚠️  {len(blocked_specs)} spec(s) blocked by external dependencies")
                    print(f"      Run: speky phases show {phase_id} for details")
        
        print(f"\n   Commands:")
        print(f"      speky phases show <phase-id>     View phase details")
        print(f"      speky phases status              Show current progress")
        print(f"      speky phases start <phase-id>    Start a phase")
        print(f"      speky phases guide <phase-id>    Generate AI implementation guide")
        print(f"      speky phases suggest             AI suggests phases from specs")
        
        return True
    
    def _cmd_phases_suggest(self) -> bool:
        """AI suggests phases based on existing specs"""
        Console.header("🤖 AI Phase Suggestions")
        
        # Load all specs
        specs = []
        for spec_dir in sorted(self.context.specs_dir.glob("*/")):
            status_file = spec_dir / "status.json"
            spec_file = spec_dir / "spec.md"
            
            if not status_file.exists():
                continue
            
            try:
                status = json.loads(status_file.read_text())
                if status.get("status") == "deprecated":
                    continue
                
                # Get spec content summary
                spec_content = ""
                if spec_file.exists():
                    content = spec_file.read_text()
                    # Extract first 500 chars of content
                    spec_content = content[:500]
                
                specs.append({
                    "id": status.get("id", spec_dir.name[:3]),
                    "name": status.get("name", spec_dir.name),
                    "priority": status.get("priority", "P1"),
                    "dependencies": status.get("dependencies", []),
                    "status": status.get("status", "draft"),
                    "summary": spec_content[:200] if spec_content else "No content"
                })
            except Exception:
                continue
        
        if len(specs) < 2:
            Console.warning("Need at least 2 specs for phase suggestions")
            print("\n   Create more specs first:")
            print("   speky spec 'Feature name'")
            return False
        
        # Check if phases already exist
        existing_phases = self._get_all_phases()
        if existing_phases:
            Console.warning(f"Found {len(existing_phases)} existing phase(s)")
            if not Console.confirm("Generate new suggestions anyway?", default=False):
                return False
        
        Console.log(f"Analyzing {len(specs)} specs...")
        
        # Build specs summary for AI
        specs_summary = ""
        for spec in specs:
            deps = f" [depends on: {', '.join(spec['dependencies'])}]" if spec['dependencies'] else ""
            specs_summary += f"- {spec['id']}: {spec['name']} ({spec['priority']}){deps}\n"
            specs_summary += f"  Status: {spec['status']}\n"
            specs_summary += f"  Summary: {spec['summary'][:100]}...\n\n"
        
        # Get product context
        product_context = ""
        product_file = self.context.context_dir / "product.md"
        if product_file.exists():
            product_context = product_file.read_text()[:1500]
        
        # Get tech stack
        tech_stack = self.context.data.get("tech_stack", {})
        
        # Query AI
        prompt = Prompts.suggest_phases_from_specs(specs_summary, product_context, tech_stack)
        
        Console.log("Querying AI for phase suggestions...")
        result = self.ai.query_json(prompt)
        
        if not result or "phases" not in result:
            Console.error("Could not get valid suggestions from AI")
            return False
        
        suggested_phases = result["phases"]
        recommendation = result.get("recommendation", "")
        
        # Display suggestions
        Console.section("📋 Suggested Phases")
        
        if recommendation:
            print(f"\n   💡 {recommendation}\n")
        
        for i, phase in enumerate(suggested_phases, 1):
            print(f"\n   {i}. {phase.get('name', 'Unnamed')} ({phase.get('id', f'phase-{i}')})")
            print(f"      Goal: {phase.get('goal', 'No goal specified')}")
            print(f"      Duration: {phase.get('duration_estimate', 'TBD')}")
            print(f"      Specs: {', '.join(phase.get('specs', []))}")
            if phase.get('deliverables'):
                print(f"      Deliverables:")
                for d in phase.get('deliverables', [])[:3]:
                    print(f"         • {d}")
            if phase.get('rationale'):
                print(f"      Rationale: {phase.get('rationale')[:100]}...")
        
        # Interactive acceptance
        print(f"\n   Options:")
        print(f"   1. Accept all phases")
        print(f"   2. Accept with modifications")
        print(f"   3. Regenerate suggestions")
        print(f"   4. Cancel")
        
        choice = Console.prompt("Choice", default="1")
        
        if choice == "4":
            Console.log("Cancelled")
            return True
        
        if choice == "3":
            return self._cmd_phases_suggest()  # Recursive call
        
        if choice == "2":
            # Allow modifications
            Console.section("📝 Modify Phases")
            print("   Enter modifications (or press Enter to keep):")
            
            for phase in suggested_phases:
                print(f"\n   Phase: {phase.get('name')}")
                
                new_name = Console.prompt(f"   Name [{phase.get('name')}]", default="")
                if new_name:
                    phase['name'] = new_name
                
                new_specs = Console.prompt(f"   Specs [{', '.join(phase.get('specs', []))}] (comma-separated)", default="")
                if new_specs:
                    phase['specs'] = [s.strip() for s in new_specs.split(",")]
        
        # Create phases
        Console.section("📁 Creating Phases")
        
        self.context.phases_dir.mkdir(exist_ok=True)
        
        for phase in suggested_phases:
            phase_id = phase.get('id', f"phase-{suggested_phases.index(phase) + 1}")
            
            # Create lightweight sketch format
            phase_data = {
                "id": phase_id,
                "name": phase.get('name', 'Unnamed'),
                "description": phase.get('goal', ''),
                "duration": phase.get('duration_estimate', 'TBD'),
                "status": "not_started",
                "specs": [{"id": sid} for sid in phase.get('specs', [])],
                "deliverables": [{"name": d} for d in phase.get('deliverables', [])],
                "acceptance_criteria": [phase.get('success_criteria', 'All deliverables verified')],
                "depends_on": [],
                "unlocks": [],
            }
            
            # Set dependencies based on phase order
            phase_index = suggested_phases.index(phase)
            if phase_index > 0:
                prev_phase = suggested_phases[phase_index - 1]
                phase_data["depends_on"] = [prev_phase.get('id', f"phase-{phase_index}")]
            if phase_index < len(suggested_phases) - 1:
                next_phase = suggested_phases[phase_index + 1]
                phase_data["unlocks"] = [next_phase.get('id', f"phase-{phase_index + 2}")]
            
            self._save_phase(phase_id, phase_data)
            Console.success(f"Created: {phase_id}")
        
        # Create roadmap
        roadmap_data = {
            "project": self.context.data.get("product", {}).get("name", "Unknown"),
            "total_phases": len(suggested_phases),
            "current_phase": None,
            "estimated_duration": f"{sum(int(p.get('duration_estimate', '2').split()[0]) for p in suggested_phases if p.get('duration_estimate', '').split() and p.get('duration_estimate', '').split()[0].isdigit())} weeks",
        }
        self._save_roadmap(roadmap_data)
        
        Console.success(f"Created {len(suggested_phases)} phases!")
        
        print(f"\n   Next steps:")
        print(f"   1. Review phases: speky phases list")
        print(f"   2. Edit if needed: .speky/phases/<phase-id>/manifest.yaml")
        print(f"   3. Start first phase: speky phases start {suggested_phases[0].get('id', 'phase-1')}")
        
        return True
    
    def _suggest_phases_from_specs_for_import(self, specs: List[dict], analysis: str = "") -> Optional[List[dict]]:
        """Suggest phases during import workflow (non-interactive, returns suggestions)"""
        if len(specs) < 2:
            return None
        
        # Build specs summary
        specs_summary = ""
        for spec in specs:
            specs_summary += f"- {spec.get('name', 'Unknown')}: {spec.get('scope', 'No scope')[:100]}\n"
        
        # Get product context
        product_context = ""
        product_file = self.context.context_dir / "product.md"
        if product_file.exists():
            product_context = product_file.read_text()[:1000]
        
        prompt = Prompts.suggest_phases_from_import(
            analysis or specs_summary,
            product_context,
            len(specs)
        )
        
        result = self.ai.query_json(prompt)
        
        if result and "phases" in result:
            return result["phases"]
        return None
    
    def _offer_phase_suggestions(self, specs: List[dict], source: str = "import") -> bool:
        """Offer to create phases from suggested groupings"""
        Console.section("📅 Phase Suggestions")
        
        print(f"\n   You've created {len(specs)} specs from {source}.")
        print("   Would you like AI to suggest logical implementation phases?")
        print("\n   Phases help by:")
        print("   • Grouping related specs")
        print("   • Defining clear milestones")
        print("   • Generating AI implementation guides")
        
        if not Console.confirm("Suggest phases?", default=True):
            return False
        
        # Get suggestions
        suggestions = self._suggest_phases_from_specs_for_import(specs)
        
        if not suggestions:
            Console.warning("Could not generate phase suggestions")
            return False
        
        # Display and accept
        print(f"\n   🤖 Suggested {len(suggestions)} phases:")
        
        for i, phase in enumerate(suggestions, 1):
            print(f"\n   {i}. {phase.get('name', 'Unnamed')}")
            print(f"      Goal: {phase.get('goal', 'No goal')}")
            print(f"      Specs: {phase.get('spec_criteria', 'Various specs')}")
        
        if Console.confirm("Accept these phases?", default=True):
            # Create phases
            self.context.phases_dir.mkdir(exist_ok=True)
            
            for phase in suggestions:
                phase_id = phase.get('id', f"phase-{suggestions.index(phase) + 1}")
                phase_data = {
                    "id": phase_id,
                    "name": phase.get('name', 'Unnamed'),
                    "description": phase.get('goal', ''),
                    "duration": phase.get('duration_estimate', 'TBD'),
                    "status": "not_started",
                    "spec_criteria": phase.get('spec_criteria', ''),
                    "specs": [],  # Will be populated by user or AI later
                    "deliverables": [{"name": d} for d in phase.get('deliverables', [])],
                    "acceptance_criteria": [phase.get('success_criteria', 'All deliverables verified')],
                }
                self._save_phase(phase_id, phase_data)
            
            Console.success(f"Created {len(suggestions)} phases")
            print(f"   Edit phases: .speky/phases/<phase-id>/manifest.yaml")
            print(f"   Add specs to phases as needed")
            return True
        
        return False
    
    def _cmd_phases_show(self, phase_id: str) -> bool:
        """Show phase details"""
        if not phase_id:
            Console.error("Please specify a phase ID")
            return False
        
        phase = self._load_phase(phase_id)
        if not phase:
            Console.error(f"Phase not found: {phase_id}")
            return False
        
        Console.header(f"📅 Phase: {phase.get('name', phase_id)}")
        
        # Basic info
        print(f"\n   ID: {phase.get('id', phase_id)}")
        print(f"   Status: {phase.get('status', 'not_started')}")
        print(f"   Duration: {phase.get('duration', 'TBD')}")
        print(f"   Description: {phase.get('description', 'No description')}")
        
        # Dependencies
        depends_on = phase.get("depends_on", [])
        if depends_on:
            dep_strs = []
            for dep in depends_on:
                if isinstance(dep, dict):
                    dep_strs.append(dep.get("phase_id", str(dep)))
                else:
                    dep_strs.append(str(dep))
            if dep_strs:
                print(f"\n   Depends On: {', '.join(dep_strs)}")
        
        unlocks = phase.get("unlocks", [])
        if unlocks:
            unlock_strs = []
            for unlock in unlocks:
                if isinstance(unlock, dict):
                    unlock_strs.append(unlock.get("phase_id", str(unlock)))
                else:
                    unlock_strs.append(str(unlock))
            if unlock_strs:
                print(f"   Unlocks: {', '.join(unlock_strs)}")
        
        # Prerequisites
        prerequisites = phase.get("prerequisites", [])
        if prerequisites:
            Console.section("📋 Prerequisites")
            prereqs_met, unmet = self._validate_phase_prerequisites(phase)
            for prereq in prerequisites:
                # Handle both simple strings and complex dicts
                if isinstance(prereq, dict):
                    prereq_desc = prereq.get("description", str(prereq))
                else:
                    prereq_desc = str(prereq)
                icon = "✅" if prereq_desc not in unmet else "⬜"
                print(f"   {icon} {prereq_desc}")
        
        # Specs in phase
        Console.section("📄 Specs")
        specs = self._get_phase_specs(phase)
        
        # Load all specs for dependency checking
        all_specs = []
        for spec_dir in self.context.specs_dir.glob("*/"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                try:
                    spec_status = json.loads(status_file.read_text())
                    if spec_status.get("status") != "deprecated":
                        all_specs.append(spec_status)
                except Exception:
                    continue
        
        # Check for blocking
        blocked_specs = self._check_phase_blocking(phase, all_specs)
        blocked_ids = {b["id"] for b in blocked_specs}
        
        for spec in specs:
            status_icon = "✅" if spec.get("status") == "completed" else "⬜"
            is_blocked = spec.get("id") in blocked_ids
            
            if is_blocked:
                status_icon = "⛔"
            
            scope = spec.get("phase_scope", "full")
            scope_label = f" ({scope})" if scope != "full" else ""
            print(f"   {status_icon} {spec['id']}: {spec.get('name', 'Unknown')}{scope_label}")
            
            # Show blocking info
            if is_blocked:
                blocked_info = next((b for b in blocked_specs if b["id"] == spec.get("id")), None)
                if blocked_info:
                    if blocked_info["deps_outside_phase"]:
                        outside_deps = ", ".join(blocked_info["deps_outside_phase"])
                        print(f"      ⚠️  BLOCKED: Dependencies outside phase: {outside_deps}")
                    else:
                        unmet = ", ".join(blocked_info["unmet_deps"])
                        print(f"      ⚠️  BLOCKED: Unmet dependencies: {unmet}")
            
            features = spec.get("phase_features", [])
            if features:
                for feature in features[:3]:
                    print(f"      • {feature}")
                if len(features) > 3:
                    print(f"      • ... and {len(features) - 3} more")
            
            excludes = spec.get("phase_excludes", [])
            if excludes:
                print(f"      ⛔ Excludes: {', '.join(excludes[:3])}")
        
        # Show blocking summary if any
        if blocked_specs:
            Console.section("⚠️  Configuration Issues")
            print(f"   {len(blocked_specs)} spec(s) have dependencies OUTSIDE this phase:")
            for blocked in blocked_specs:
                outside = ", ".join(blocked["deps_outside_phase"])
                print(f"   • {blocked['id']}: needs {outside}")
            
            print(f"\n   💡 FIX OPTIONS:")
            print(f"   1. Implement dependencies first: speky plan <dep-id>")
            print(f"   2. Add dependencies to this phase manifest")
            print(f"   3. Move blocked specs to a later phase")
        
        # Deliverables
        deliverables = phase.get("deliverables", [])
        if deliverables:
            Console.section("🎯 Deliverables")
            
            # Load verified status
            phase_dir = self.context.phases_dir / phase_id
            status_file = phase_dir / "status.json"
            verified = []
            if status_file.exists():
                try:
                    verified = json.loads(status_file.read_text()).get("verified_deliverables", [])
                except Exception:
                    pass
            
            for d in deliverables:
                d_id = d.get("id", "")
                d_name = d.get("name", "Unknown")
                d_test = d.get("test", "")
                icon = "✅" if d_id in verified else "⬜"
                print(f"   {icon} {d_id}: {d_name}")
                if d_test:
                    print(f"      Test: {d_test}")
        
        # Acceptance Criteria
        acceptance = phase.get("acceptance_criteria", [])
        if acceptance:
            Console.section("✓ Acceptance Criteria")
            for criterion in acceptance:
                print(f"   • {criterion}")
        
        # User Review Points
        review_points = phase.get("user_review_points", [])
        if review_points:
            Console.section("👤 User Review Points")
            for rp in review_points:
                after = rp.get("after", "")
                questions = rp.get("questions", [])
                print(f"   After {after}:")
                for q in questions:
                    print(f"      • {q}")
        
        print(f"\n   Commands:")
        print(f"      speky phases start {phase_id}    Start this phase")
        print(f"      speky phases guide {phase_id}    Generate AI guide")
        
        return True
    
    def _cmd_phases_status(self) -> bool:
        """Show overall phase progress"""
        Console.header("📊 Phase Status")
        
        phases = self._get_all_phases()
        roadmap = self._load_roadmap()
        
        if not phases:
            Console.warning("No phases defined")
            return True
        
        current_phase = roadmap.get("current_phase") if roadmap else None
        
        # Summary stats
        total = len(phases)
        completed = sum(1 for p in phases if p.get("status") == "complete")
        in_progress = sum(1 for p in phases if p.get("status") == "in_progress")
        
        print(f"\n   Total Phases: {total}")
        print(f"   Completed: {completed}")
        print(f"   In Progress: {in_progress}")
        print(f"   Not Started: {total - completed - in_progress}")
        
        if current_phase:
            print(f"\n   🎯 Current: {current_phase}")
        
        # Show each phase progress
        Console.section("📈 Progress by Phase")
        
        for phase in phases:
            phase_id = phase.get("id", phase.get("_dir"))
            name = phase.get("name", "Unnamed")
            status = phase.get("status", "not_started")
            progress = self._calculate_phase_progress(phase)
            
            # Progress bar
            pct = progress["specs_percent"]
            bar_filled = int(pct / 10)
            bar = "█" * bar_filled + "░" * (10 - bar_filled)
            
            is_current = phase_id == current_phase
            marker = " ◀ CURRENT" if is_current else ""
            
            print(f"\n   {phase_id}: {name}{marker}")
            print(f"   [{bar}] {pct}%")
            print(f"   Specs: {progress['specs_completed']}/{progress['specs_total']} | Deliverables: {progress['deliverables_verified']}/{progress['deliverables_total']}")
        
        # Next actions
        Console.section("📋 Next Actions")
        
        # Load all specs for blocking detection
        all_specs = []
        for spec_dir in self.context.specs_dir.glob("*/"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                try:
                    spec_status = json.loads(status_file.read_text())
                    if spec_status.get("status") != "deprecated":
                        all_specs.append(spec_status)
                except Exception:
                    continue
        
        # Find current or next phase
        for phase in phases:
            if phase.get("status") == "in_progress":
                phase_id = phase.get("id", phase.get("_dir"))
                specs = self._get_phase_specs(phase)
                incomplete = [s for s in specs if s.get("status") != "completed"]
                
                # Check for blocking
                blocked_specs = self._check_phase_blocking(phase, all_specs)
                
                if blocked_specs:
                    print(f"   ⚠️  Phase {phase_id} has blocked specs:")
                    for blocked in blocked_specs[:2]:
                        outside = ", ".join(blocked["deps_outside_phase"])
                        print(f"   • {blocked['id']} needs: {outside}")
                    if len(blocked_specs) > 2:
                        print(f"   • ... and {len(blocked_specs) - 2} more")
                    
                    # Suggest implementing dependencies
                    first_dep = blocked_specs[0]["deps_outside_phase"][0] if blocked_specs[0]["deps_outside_phase"] else None
                    if first_dep:
                        print(f"\n   Recommended: Implement dependency first")
                        print(f"   1. speky plan {first_dep}")
                        print(f"   2. speky implement {first_dep}")
                        print(f"\n   Or view details: speky phases show {phase_id}")
                elif incomplete:
                    next_spec = incomplete[0]
                    print(f"   Continue {phase_id}:")
                    print(f"   1. speky plan {next_spec['id']}")
                    print(f"   2. speky implement {next_spec['id']}")
                else:
                    print(f"   Complete {phase_id}:")
                    print(f"   speky phases complete {phase_id}")
                break
        else:
            # No phase in progress, find next to start
            for phase in phases:
                if phase.get("status") == "not_started":
                    phase_id = phase.get("id", phase.get("_dir"))
                    print(f"   Start next phase:")
                    print(f"   speky phases start {phase_id}")
                    break
            else:
                print("   All phases complete! 🎉")
        
        return True
    
    def _cmd_phases_start(self, phase_id: str) -> bool:
        """Start a phase"""
        if not phase_id:
            Console.error("Please specify a phase ID")
            return False
        
        phase = self._load_phase(phase_id)
        if not phase:
            Console.error(f"Phase not found: {phase_id}")
            return False
        
        Console.header(f"🚀 Starting Phase: {phase.get('name', phase_id)}")
        
        # Check dependencies
        depends_on = phase.get("depends_on", [])
        if depends_on:
            Console.section("Checking Dependencies")
            unmet_deps = []
            
            for dep_id in depends_on:
                dep_phase = self._load_phase(dep_id)
                if not dep_phase:
                    unmet_deps.append(f"{dep_id} (not found)")
                elif dep_phase.get("status") != "complete":
                    unmet_deps.append(f"{dep_id} (status: {dep_phase.get('status', 'not_started')})")
                else:
                    print(f"   ✅ {dep_id} complete")
            
            if unmet_deps:
                Console.warning("Unmet dependencies:")
                for dep in unmet_deps:
                    print(f"   ⬜ {dep}")
                
                if not Console.confirm("Start anyway?", default=False):
                    return False
        
        # Check prerequisites
        prereqs_met, unmet = self._validate_phase_prerequisites(phase)
        if not prereqs_met:
            Console.warning("Some prerequisites may not be met:")
            for prereq in unmet:
                print(f"   ⬜ {prereq}")
            
            if not Console.confirm("Start anyway?", default=True):
                return False
        
        # Check for specs with external dependencies
        Console.section("Validating Phase Configuration")
        all_specs = []
        for spec_dir in self.context.specs_dir.glob("*/"):
            status_file = spec_dir / "status.json"
            if status_file.exists():
                try:
                    spec_status = json.loads(status_file.read_text())
                    if spec_status.get("status") != "deprecated":
                        all_specs.append(spec_status)
                except Exception:
                    continue
        
        blocked_specs = self._check_phase_blocking(phase, all_specs)
        if blocked_specs:
            Console.warning(f"⚠️  Configuration Issue Detected:")
            print(f"   {len(blocked_specs)} spec(s) in this phase have dependencies OUTSIDE the phase:")
            for blocked in blocked_specs[:3]:
                outside = ", ".join(blocked["deps_outside_phase"])
                print(f"   • {blocked['id']}: needs {outside}")
            if len(blocked_specs) > 3:
                print(f"   • ... and {len(blocked_specs) - 3} more")
            
            print(f"\n   These specs cannot be implemented until their dependencies are complete.")
            print(f"   You may want to:")
            print(f"   1. Add missing dependencies to this phase")
            print(f"   2. Implement dependencies first before starting this phase")
            print(f"   3. Remove blocked specs from this phase")
            
            if not Console.confirm("Start phase anyway?", default=False):
                return False
        else:
            print(f"   ✅ All specs in phase have dependencies met or within phase")
        
        # Update phase status
        phase["status"] = "in_progress"
        self._save_phase(phase_id, phase)
        
        # Update roadmap current phase
        roadmap = self._load_roadmap() or {}
        roadmap["current_phase"] = phase_id
        self._save_roadmap(roadmap)
        
        # Create status.json for tracking
        phase_dir = self.context.phases_dir / phase_id
        status_file = phase_dir / "status.json"
        status_data = {
            "started_at": datetime.now().isoformat(),
            "verified_deliverables": [],
            "notes": [],
        }
        status_file.write_text(json.dumps(status_data, indent=2))
        
        Console.success(f"Phase {phase_id} started!")
        
        # Show what to do next
        specs = self._get_phase_specs(phase)
        if specs:
            first_spec = specs[0]
            print(f"\n   📋 First spec to implement: {first_spec['id']}")
            print(f"\n   Next steps:")
            print(f"   1. speky phases guide {phase_id} --for-ai    Generate AI context")
            print(f"   2. speky plan {first_spec['id']}             Plan first spec")
            print(f"   3. speky implement {first_spec['id']}        Start implementation")
        
        return True
    
    def _cmd_phases_complete(self, phase_id: str) -> bool:
        """Complete a phase"""
        if not phase_id:
            Console.error("Please specify a phase ID")
            return False
        
        phase = self._load_phase(phase_id)
        if not phase:
            Console.error(f"Phase not found: {phase_id}")
            return False
        
        Console.header(f"✅ Completing Phase: {phase.get('name', phase_id)}")
        
        # Check all specs completed
        specs = self._get_phase_specs(phase)
        incomplete_specs = [s for s in specs if s.get("status") != "completed"]
        
        if incomplete_specs:
            Console.warning("Not all specs are completed:")
            for spec in incomplete_specs:
                print(f"   ⬜ {spec['id']}: {spec.get('name', 'Unknown')}")
            
            if not Console.confirm("Mark phase complete anyway?", default=False):
                return False
        
        # Verify deliverables
        deliverables = phase.get("deliverables", [])
        if deliverables:
            Console.section("Verify Deliverables")
            
            phase_dir = self.context.phases_dir / phase_id
            status_file = phase_dir / "status.json"
            status_data = {}
            if status_file.exists():
                try:
                    status_data = json.loads(status_file.read_text())
                except Exception:
                    pass
            
            verified = status_data.get("verified_deliverables", [])
            
            for d in deliverables:
                d_id = d.get("id", "")
                d_name = d.get("name", "Unknown")
                d_test = d.get("test", "")
                
                if d_id in verified:
                    print(f"   ✅ {d_id}: {d_name}")
                else:
                    print(f"\n   ⬜ {d_id}: {d_name}")
                    if d_test:
                        print(f"      Test: {d_test}")
                    
                    if Console.confirm("Mark as verified?", default=True):
                        verified.append(d_id)
            
            # Save verified deliverables
            status_data["verified_deliverables"] = verified
            status_file.write_text(json.dumps(status_data, indent=2))
        
        # Check acceptance criteria
        acceptance = phase.get("acceptance_criteria", [])
        if acceptance:
            Console.section("Acceptance Criteria")
            print("   Please confirm each criterion:")
            
            all_met = True
            for criterion in acceptance:
                if not Console.confirm(f"   {criterion}", default=True):
                    all_met = False
            
            if not all_met:
                Console.warning("Not all acceptance criteria met")
                if not Console.confirm("Mark phase complete anyway?", default=False):
                    return False
        
        # Update phase status
        phase["status"] = "complete"
        self._save_phase(phase_id, phase)
        
        # Update roadmap
        roadmap = self._load_roadmap() or {}
        unlocks = phase.get("unlocks", [])
        if unlocks:
            roadmap["current_phase"] = unlocks[0]
        roadmap[f"{phase_id}_completed_at"] = datetime.now().isoformat()
        self._save_roadmap(roadmap)
        
        Console.success(f"Phase {phase_id} completed! 🎉")
        
        if unlocks:
            print(f"\n   Next phase unlocked: {unlocks[0]}")
            print(f"   Run: speky phases start {unlocks[0]}")
        
        return True
    
    def _cmd_phases_guide(self, phase_id: str, for_ai: bool = False) -> bool:
        """Generate implementation guide for a phase"""
        if not phase_id:
            Console.error("Please specify a phase ID")
            return False
        
        phase = self._load_phase(phase_id)
        if not phase:
            Console.error(f"Phase not found: {phase_id}")
            return False
        
        Console.header(f"📖 Implementation Guide: {phase.get('name', phase_id)}")
        
        # Generate guide content
        guide = self._generate_phase_guide(phase, for_ai=for_ai)
        
        # Save to file
        phase_dir = self.context.phases_dir / phase_id
        guide_file = phase_dir / "implementation.md"
        guide_file.write_text(guide)
        
        print(f"\n{guide[:3000]}")
        if len(guide) > 3000:
            print(f"\n... (truncated)")
        
        Console.success(f"Guide saved to: {guide_file}")
        
        if for_ai:
            print(f"\n   💡 Copy this guide to your AI agent's context")
        
        return True
    
    def _cmd_phases_create(self, phase_id: str) -> bool:
        """Create a new phase with template"""
        if not phase_id:
            # Interactive phase ID prompt
            phase_id = Console.prompt("Phase ID (e.g., phase-1, mvp)")
            if not phase_id:
                Console.warning("Cancelled")
                return False
        
        phase_dir = self.context.phases_dir / phase_id
        
        if phase_dir.exists():
            Console.warning(f"Phase {phase_id} already exists")
            return False
        
        Console.header(f"📝 Create Phase: {phase_id}")
        
        # Gather info
        name = Console.prompt("Phase name", default=f"Phase {phase_id}")
        description = Console.prompt("Description", default="")
        duration = Console.prompt("Duration (e.g., '4 weeks')", default="TBD")
        
        # Get specs to include
        print("\n   Available specs:")
        specs = []
        for spec_dir in sorted(self.context.specs_dir.iterdir()):
            if spec_dir.is_dir():
                status_file = spec_dir / "status.json"
                if status_file.exists():
                    try:
                        status = json.loads(status_file.read_text())
                        spec_id = status.get("id", spec_dir.name[:3])
                        spec_name = status.get("name", spec_dir.name)
                        print(f"      {spec_id}: {spec_name}")
                        specs.append({"id": spec_id, "name": spec_name})
                    except Exception:
                        pass
        
        spec_ids_input = Console.prompt("\n   Specs to include (comma-separated IDs)", default="")
        spec_ids = [s.strip() for s in spec_ids_input.split(",") if s.strip()] if spec_ids_input else []
        
        # Create manifest
        phase_data = {
            "id": phase_id,
            "name": name,
            "description": description,
            "duration": duration,
            "status": "not_started",
            "specs": [
                {
                    "id": sid, 
                    "scope": "full",  # "full", "partial", or "mvp"
                    "features": [],   # List of features to implement
                    "excludes": [],   # List of features to skip
                    "implementation_priority": i + 1
                } for i, sid in enumerate(spec_ids)
            ],
            "prerequisites": [
                {"description": "Example prerequisite", "validation": "How to verify"}
            ],
            "deliverables": [
                {
                    "id": "D1", 
                    "name": "Example deliverable", 
                    "description": "What this deliverable provides",
                    "test_steps": ["Step 1", "Step 2", "Verify result"],
                    "pass_criteria": "What success looks like"
                }
            ],
            "acceptance_criteria": [
                "All deliverables verified",
                "No critical bugs",
            ],
            "user_review_points": [
                {"after": "D1", "type": "ux_review", "questions": ["Is the UX intuitive?"]}
            ],
            "implementation_files": {
                "create": [],  # Files to create
                "modify": []   # Files to modify with changes description
            },
            "tech_requirements": {
                "packages": [],   # Required packages with version and reason
                "forbidden": []   # Packages NOT to use with reason
            },
            "depends_on": [],
            "unlocks": [],
        }
        
        phase_dir.mkdir(parents=True, exist_ok=True)
        self._save_phase(phase_id, phase_data)
        
        Console.success(f"Phase created: {phase_dir}")
        print(f"\n   Edit manifest: {phase_dir / 'manifest.yaml'}")
        print(f"   Add specs with scope/features/excludes")
        print(f"   Define deliverables and acceptance criteria")
        
        return True
    
    def _generate_phase_guide(self, phase: dict, for_ai: bool = False) -> str:
        """Generate implementation guide for a phase"""
        phase_id = phase.get("id", "unknown")
        phase_name = phase.get("name", "Unknown Phase")
        
        # Load tech decisions
        tech_decisions = ""
        tech_file = self.context.context_dir / "tech_decisions.md"
        if tech_file.exists():
            tech_decisions = tech_file.read_text()
        
        # Get specs
        specs = self._get_phase_specs(phase)
        
        # Build guide
        lines = []
        
        lines.append(f"# {phase_name} - Implementation Guide")
        lines.append("")
        
        if for_ai:
            lines.append("## AI Agent Instructions")
            lines.append("")
            lines.append(f"You are implementing **{phase_name}** ({phase_id}). This phase includes:")
            lines.append("")
        
        # Specs summary
        for spec in specs:
            scope = spec.get("phase_scope", "full")
            features = spec.get("phase_features", [])
            feature_str = ", ".join(features[:3]) if features else "all features"
            lines.append(f"- **Spec {spec['id']}** ({scope}): {feature_str}")
        
        lines.append("")
        
        # Critical context / tech decisions
        if tech_decisions:
            lines.append("### Critical Context")
            lines.append("")
            
            # Extract key decisions
            for line in tech_decisions.split('\n'):
                if line.startswith('**Decision**:'):
                    lines.append(f"- {line}")
        
        lines.append("")
        
        # Package decisions (from tech stack)
        tech_stack = self.context.data.get("tech_stack", {})
        if tech_stack:
            lines.append("### Package Decisions (AUTHORITATIVE)")
            lines.append("")
            for category, value in tech_stack.items():
                if value:
                    lines.append(f"- **{category.title()}**: `{value}`")
            lines.append("")
        
        # What NOT to do (from excludes)
        all_excludes = []
        for spec in specs:
            excludes = spec.get("phase_excludes", [])
            all_excludes.extend(excludes)
        
        if all_excludes:
            lines.append("### What NOT To Do")
            lines.append("")
            for exclude in all_excludes:
                lines.append(f"- ❌ {exclude}")
            lines.append("")
        
        # Tech requirements from phase manifest
        tech_requirements = phase.get("tech_requirements", {})
        if tech_requirements:
            packages = tech_requirements.get("packages", [])
            forbidden = tech_requirements.get("forbidden", [])
            
            if packages:
                lines.append("### Required Packages")
                lines.append("")
                for pkg in packages:
                    name = pkg.get("name", "")
                    version = pkg.get("version", "")
                    reason = pkg.get("reason", "")
                    lines.append(f"- `{name}` {version} - {reason}")
                lines.append("")
            
            if forbidden:
                lines.append("### Forbidden Packages (DO NOT USE)")
                lines.append("")
                for pkg in forbidden:
                    name = pkg.get("name", "")
                    reason = pkg.get("reason", "")
                    lines.append(f"- ❌ `{name}` - {reason}")
                lines.append("")
        
        # Implementation files
        impl_files = phase.get("implementation_files", {})
        if impl_files:
            create_files = impl_files.get("create", [])
            modify_files = impl_files.get("modify", [])
            
            if create_files:
                lines.append("### Files to Create")
                lines.append("")
                for f in create_files:
                    lines.append(f"- `{f}`")
                lines.append("")
            
            if modify_files:
                lines.append("### Files to Modify")
                lines.append("")
                for f in modify_files:
                    if isinstance(f, dict):
                        path = f.get("path", "")
                        changes = f.get("changes", "")
                        lines.append(f"- `{path}` - {changes}")
                    else:
                        lines.append(f"- `{f}`")
                lines.append("")
        
        # Deliverables
        deliverables = phase.get("deliverables", [])
        if deliverables:
            lines.append("### Deliverables (test each)")
            lines.append("")
            for d in deliverables:
                d_id = d.get('id', '')
                d_name = d.get('name', '')
                d_desc = d.get('description', '')
                lines.append(f"- [ ] **{d_id}**: {d_name}")
                if d_desc:
                    lines.append(f"  - {d_desc}")
                
                # Support both "test" and "test_steps"
                if d.get("test"):
                    lines.append(f"  - Test: {d.get('test')}")
                elif d.get("test_steps"):
                    lines.append(f"  - Steps: {', '.join(d.get('test_steps', []))}")
                
                if d.get("pass_criteria"):
                    lines.append(f"  - Pass: {d.get('pass_criteria')}")
            lines.append("")
        
        # Implementation order (specs)
        if specs:
            lines.append("### Implementation Order")
            lines.append("")
            for i, spec in enumerate(specs, 1):
                lines.append(f"{i}. **{spec['id']}**: {spec.get('name', 'Unknown')}")
                features = spec.get("phase_features", [])
                for feature in features:
                    lines.append(f"   - {feature}")
            lines.append("")
        
        # Stop conditions
        if for_ai:
            lines.append("### Stop Conditions")
            lines.append("")
            lines.append("Stop and ask user when:")
            lines.append("- Unclear requirements")
            lines.append("- Tech decision conflict")
            lines.append("- Cross-spec integration unclear")
            lines.append("- Feature scope question")
            lines.append("")
        
        # Success criteria
        acceptance = phase.get("acceptance_criteria", [])
        if acceptance:
            lines.append("### Success Criteria")
            lines.append("")
            lines.append("Phase is complete when:")
            for criterion in acceptance:
                lines.append(f"- {criterion}")
            lines.append("")
        
        return "\n".join(lines)
    
    # -------------------------------------------------------------------------
    # Command: context (AI context generation)
    # -------------------------------------------------------------------------
    def cmd_context(self, phase_id: str = None, format: str = "prompt") -> bool:
        """Generate AI context for phase implementation"""
        if not self._require_init():
            return False
        
        Console.header("🤖 AI Context Generation")
        
        if not phase_id:
            # Find current phase
            roadmap = self._load_roadmap()
            if roadmap:
                phase_id = roadmap.get("current_phase")
        
        if not phase_id:
            Console.error("No phase specified and no current phase set")
            print("   Run: speky context --phase <phase-id>")
            return False
        
        phase = self._load_phase(phase_id)
        if not phase:
            Console.error(f"Phase not found: {phase_id}")
            return False
        
        # Generate context
        context = self._generate_ai_context(phase)
        
        print(context)
        
        # Also save to file
        phase_dir = self.context.phases_dir / phase_id
        context_file = phase_dir / "ai_context.md"
        context_file.write_text(context)
        
        Console.success(f"Context saved to: {context_file}")
        print("\n   Copy and paste this context to your AI agent")
        
        return True
    
    def _generate_ai_context(self, phase: dict) -> str:
        """Generate comprehensive AI context for a phase"""
        phase_id = phase.get("id", "unknown")
        phase_name = phase.get("name", "Unknown")
        
        lines = []
        
        lines.append(f"# {phase_name} Implementation Context")
        lines.append("")
        lines.append("## Your Mission")
        lines.append(f"Implement {phase_name} of the {self.context.data.get('product', {}).get('name', 'project')}.")
        lines.append("")
        
        # Specs to implement
        specs = self._get_phase_specs(phase)
        lines.append("## Specs to Implement (in order)")
        for i, spec in enumerate(specs, 1):
            scope = spec.get("phase_scope", "full")
            features = spec.get("phase_features", [])
            feature_str = ", ".join(features) if features else "all features"
            lines.append(f"{i}. **Spec {spec['id']}** ({scope}): {feature_str}")
        lines.append("")
        
        # Critical rules
        lines.append("## Critical Rules")
        lines.append("")
        
        # DOs from tech stack
        lines.append("### DO")
        tech_stack = self.context.data.get("tech_stack", {})
        for category, value in tech_stack.items():
            if value:
                lines.append(f"✅ Use {value} for {category}")
        lines.append("✅ Test after each major feature")
        lines.append("")
        
        # DON'Ts from excludes
        lines.append("### DON'T")
        for spec in specs:
            excludes = spec.get("phase_excludes", [])
            for exclude in excludes:
                lines.append(f"❌ {exclude}")
        lines.append("")
        
        # Deliverables
        deliverables = phase.get("deliverables", [])
        if deliverables:
            lines.append("## Deliverables (test each)")
            for d in deliverables:
                lines.append(f"- [ ] {d.get('name', '')} ({d.get('id', '')})")
            lines.append("")
        
        # Stop conditions
        lines.append("## Stop Conditions")
        lines.append("Stop and ask user when:")
        lines.append("- Unclear requirements")
        lines.append("- Tech decision conflict")
        lines.append("- Cross-spec integration unclear")
        lines.append("- Feature scope question")
        lines.append("")
        
        # Success criteria
        acceptance = phase.get("acceptance_criteria", [])
        if acceptance:
            lines.append("## Success Criteria")
            lines.append("Phase is complete when:")
            for criterion in acceptance:
                lines.append(f"- {criterion}")
        
        return "\n".join(lines)


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

# =============================================================================
# GLOBAL OPTIONS — accepted anywhere on the command line, before or after the command
# =============================================================================

_GLOBAL_FLAGS = {"-y": "yes", "--yes": "yes", "--non-interactive": "non_interactive",
                 "--no-input": "non_interactive", "--host": "host"}
_GLOBAL_VALUE_OPTIONS = {"--answer": "answer", "--answers": "answers", "--llm": "llm"}


def _extract_global_options(argv: List[str]):
    """Pull global options out of argv so they work after the subcommand too.
    Returns (remaining argv, options dict)."""
    opts = {"yes": False, "non_interactive": False, "host": False,
            "answer": [], "answers": None, "llm": None}
    rest, i = [], 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            rest.extend(argv[i:])
            break
        name, eq, inline = arg.partition("=")
        if arg in _GLOBAL_FLAGS:
            opts[_GLOBAL_FLAGS[arg]] = True
        elif name in _GLOBAL_VALUE_OPTIONS:
            if eq:
                value = inline
            elif i + 1 < len(argv):
                i += 1
                value = argv[i]
            else:
                print(f"❌ {name} needs a value")
                sys.exit(2)
            key = _GLOBAL_VALUE_OPTIONS[name]
            if key == "answer":
                opts["answer"].append(value)
            else:
                opts[key] = value
        else:
            rest.append(arg)
        i += 1
    return rest, opts


def _load_answers_file(path: str) -> List[tuple]:
    """--answers file: a JSON/YAML mapping {question: answer}, or a list of
    one-key mappings when the same question needs several answers in order."""
    try:
        text = Path(path).read_text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            import yaml
            data = yaml.safe_load(text)
        items = data.items() if isinstance(data, dict) else [kv for d in (data or []) for kv in d.items()]
        return [(str(k), "" if v is None else str(v)) for k, v in items]
    except Exception as e:
        print(f"❌ Could not read --answers file {path}: {str(e).splitlines()[0]}")
        print("   Expected {question: answer} pairs, or a list of one-pair mappings (see AUTOMATION.md).")
        sys.exit(2)


def _apply_global_options(opts: dict):
    answers = []
    if opts["answers"]:
        answers.extend(_load_answers_file(opts["answers"]))
    for item in opts["answer"]:
        key, sep, value = item.partition("=")
        if not sep:
            print(f'❌ --answer expects "question=answer", got: {item}')
            sys.exit(2)
        answers.append((key.strip(), value.strip()))
    # No terminal (scripts, CI, AI agents' shell tools) → never block on input()
    no_tty = not sys.stdin.isatty() and os.environ.get("SPEKY_INTERACTIVE") != "1"
    Console.configure(non_interactive=opts["non_interactive"] or no_tty,
                      assume_yes=opts["yes"], answers=answers)
    if opts["host"]:
        os.environ["SPEKY_MODEL"] = "host"
    elif opts["llm"]:
        os.environ["SPEKY_MODEL"] = opts["llm"]
    if not sys.stdout.isatty():
        # Callers read our output while we run (e.g. host mode waiting for an answer)
        sys.stdout.reconfigure(line_buffering=True)


def _global_options_parser() -> argparse.ArgumentParser:
    """Global options, shown in every command's --help (parsing is done by _extract_global_options)."""
    parent = argparse.ArgumentParser(add_help=False)
    g = parent.add_argument_group("global options (work before or after the command)")
    g.add_argument("-y", "--yes", action="store_true",
                   help="Answer yes to every confirmation; other questions take their default")
    g.add_argument("--non-interactive", "--no-input", action="store_true",
                   help="Never wait for keyboard input: use --answer values, else defaults "
                        "(automatic when stdin is not a terminal; SPEKY_INTERACTIVE=1 disables that)")
    g.add_argument("--answer", metavar='"QUESTION=VALUE"', action="append",
                   help="Pre-answer any question whose text contains QUESTION (case-insensitive). "
                        "Repeatable. For choices VALUE is the option number or part of its text")
    g.add_argument("--answers", metavar="FILE",
                   help="JSON/YAML file of {question: answer} pairs (same matching as --answer)")
    g.add_argument("--llm", metavar="PROVIDER/MODEL",
                   help="Model for this run only, e.g. openrouter/moonshotai/kimi-k2 (same as SPEKY_MODEL)")
    g.add_argument("--host", action="store_true",
                   help="Host mode: no LLM call — the agent running SPEKY answers each prompt "
                        "(see `speky host guide`)")
    return parent


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        prog="speky",
        description="SPEKY v2: AI-Assisted Scalable Engineering Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Choosing the AI model (any provider):
  config --providers             List providers (OpenRouter, Nebius, OpenCode Go, Claude
                                 subscription, Ollama, ...) and whether their keys are set
  config --model                 Show the current model and pick a new one interactively
  config --model PROVIDER/MODEL  Set it, e.g. openrouter/moonshotai/kimi-k2, claude-code/opus
  --llm PROVIDER/MODEL           Use a model for one run only (or env SPEKY_MODEL)
  Config file: ~/.speky/models.yaml (model, fallbacks, custom providers) — see MODELS.md

Running from scripts and AI agents (Claude Code, Cursor, CI):
  -y, --yes                      Answer yes to confirmations; other questions use defaults
  --answer "QUESTION=VALUE"      Pre-answer a question (matched by text, repeatable)
  --answers FILE                 Many answers from a JSON/YAML file
  --non-interactive              Never prompt (automatic when stdin is not a terminal)
  Each unattended answer is printed as "↳ question → answer". If a question has no
  usable default, SPEKY exits with code 4 and prints the exact --answer to add.

Host mode (the calling agent is SPEKY's model — no API key needed):
  --host  (or SPEKY_MODEL=host)  SPEKY writes each prompt to .speky/host/NNN.prompt.md
                                 and waits; the agent answers and SPEKY continues
  host guide                     Instructions to give your agent (paste into CLAUDE.md)
  host status                    Show prompts waiting for an answer
  host show [ID]                 Print a waiting prompt
  host answer ID --file F        Deliver an answer (or pipe it on stdin)

Exit codes: 0 ok · 1 failed · 2 bad usage · 4 needs an --answer · 130 interrupted

Core Commands:
  init "idea"                    Initialize SPEKY with your product idea
  init --from-project            Existing repo: fill the product profile and tech stack from
                                 its README/docs/manifests instead of asking (also refreshes)
  spec "feature"                 Create feature spec (with optional research input)
  plan <spec-id>                 Generate implementation plan for a spec
  plan <spec-id> --check         Include pre-planning codebase analysis (opt-in)
  story --type TYPE "title"      Create a story (feature/bug/enhancement/tech_debt/spike)
  story "title" --epic E001      Create story and add to epic
  story "title" --spec 006       Create story linked to spec
  implement <id>                 Hand off to IDE for implementation (with full context chain)
  complete <id>                  Mark spec or story complete (drift detection for specs)
  commit <spec-id>               Commit a completed feature with comprehensive message
  status                         Show project status

Epic Management (Story Grouping):
  epic "Epic Name" --spec 006    Create epic linked to a spec
  epic "Name" --stories F001,F002  Create epic with existing stories
  epic E001                      Show epic details and progress
  epic E001 --add F003           Add story to epic
  epic E001 --remove F003        Remove story from epic
  epics                          List all epics with status

Context & Maintenance:
  sync                           Sync codebase context
  review [spec-id]               Check for spec-code drift
  cleanup [--dry-run]            Clean up clutter files from project root

Configuration:
  config                         Show current SPEKY configuration
  config --list-ides             List all supported IDEs
  config --ides                  Show enabled IDEs
  config --ides add <ide>        Add an IDE (e.g., antigravity)
  config --ides remove <ide>     Remove an IDE
  config --ides set <ide1,ide2>  Set specific IDEs (comma-separated)
  config --model [REF]           Show/pick/set the AI model (see "Choosing the AI model")
  config --providers             List AI providers and key status

External Knowledge Import:
  import [--phase NAME]          Import docs from .speky/imports/<phase>/source/
  import --phase mvp --no-review Import without interactive review
  import-status                  Show status of all imports
  reconcile <phase>              Reconcile code with imported docs and specs
  reconcile <phase> --dry-run    Preview reconciliation without applying

POC Code Import:
  poc-import                     Import features from existing POC codebase
  poc-import --path /path/to/poc Provide POC path directly
  poc-import --resume            Resume incomplete import session
  poc-import --spec 003          Link POC to existing spec

Import Workflow:
  1. Create folder: .speky/imports/<phase>/source/
  2. Place your docs there (PRD, tech spec, etc.)
  3. Run: speky import --phase <phase>

POC Import Workflow:
  1. Run: speky poc-import
  2. Tell IDE to analyze POC (follow task.md)
  3. Select features (numbers or natural language)
  4. Review AI recommendations
  5. Tell IDE to create specs (follow extraction_task.md)
  6. Specs auto-adopted into SPEKY

Spec Sequencing & Dependencies:
  sequence                       Show unified roadmap with dependency analysis
  sequence --export              Export roadmap to .speky/roadmap.md
  infer-deps                     AI-infer dependencies for all specs
  infer-deps <spec-id>           AI-infer dependencies for specific spec

Phase Management (Multi-Spec Coordination):
  phases suggest                 AI suggests phases from existing specs (RECOMMENDED)
  phases list                    List all phases
  phases show <phase-id>         Show phase details
  phases status                  Show overall phase progress
  phases start <phase-id>        Start a phase (validates prerequisites)
  phases complete <phase-id>     Complete a phase (validates deliverables)
  phases guide <phase-id>        Generate AI implementation guide
  phases guide <phase-id> --for-ai  Generate AI-optimized guide
  phases create [phase-id]       Create a new phase manually
  context                        Generate AI context for current phase
  context --phase <phase-id>     Generate AI context for specific phase

Phase Workflows:
  # Option A: AI-Suggested Phases (RECOMMENDED)
  1. Create specs: speky spec "Feature" (repeat for all features)
  2. Suggest phases: speky phases suggest
  3. Start phase: speky phases start phase-1
  4. Implement: speky phases guide phase-1 --for-ai → implement specs
  5. Complete: speky phases complete phase-1

  # Option B: Manual Phase Creation
  1. Create phase: speky phases create phase-1
  2. Edit: .speky/phases/phase-1/manifest.yaml
  3. Continue from step 3 above

Spec Validation & Adoption (IDE Workflow):
  validate-spec <ref>            Validate spec quality, find gaps, get suggestions
  validate-spec <ref> --quick    Quick validation (non-interactive)
  adopt <spec-id>                Adopt IDE-created spec into SPEKY tracking

Backlog Management (Anti-Rot):
  backlog                        Review and manage deferred validation items
                                 (High priority → stories, Medium/Low → backlog)

Spec Features:
  • Research-aware: Include existing docs/research when creating specs
  • Interactive validation: Walk through gaps/suggestions one-by-one
  • Context-aware AI: Provide your concerns for better suggestions
  • Defer for later: Route items by priority (story vs backlog)
  • Anti-rot check: Review backlog before creating new specs

Validation Flow:
  1. Want AI suggestions? [y]es / [n]o / [c]ontext
  2. Choose action: Add to fix list / Skip / Fix now / Defer for later
  3. Add comments (optional for all actionable options)
  4. If defer: Choose priority (High/Medium/Low)

Drift Types:
  SPEC_BEHIND              Implementation has features not in spec (update spec)
  CODE_BEHIND              Spec has features not yet implemented (next iteration)
  SCOPE_CREEP              Implemented out-of-scope items (document or remove)
  TECH_DEVIATION           Different tech approach than specified (update spec)
  DOC_STALE                Documentation doesn't match code (update docs)

Examples:
  speky config --model opencode-go/glm-5.2  # switch model for all projects
  speky spec "Login" -y --answer "Add to phase=phase-1"   # no prompts
  speky spec "Login" --host                # let the calling agent write the spec
  speky init "A mobile app for converting cooking videos to step-by-step recipes"
  speky import --phase mvp                   # Creates folder, guides you to add docs
  speky import --phase mvp                   # Import docs from .speky/imports/mvp/source/
  speky import --phase mvp --no-review       # Import without interactive review
  speky import-status                        # Show all imports
  speky spec "Video transcription"
  speky validate-spec 001
  speky adopt 001
  speky plan 001
  speky implement 001
  speky complete 001             # Drift detection + sync + mark complete
  speky reconcile mvp            # Reconcile code with imported docs
  speky commit 001               # Commit with comprehensive message
  speky backlog                  # Review deferred items
  speky status
        """
    )
    
    global_options = _global_options_parser()
    global_group = parser.add_argument_group("global options (work before or after the command)")
    for action in global_options._actions:
        global_group._add_action(action)  # list global options in `speky --help`
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    _add_parser = subparsers.add_parser

    def add_parser_with_global_options(name, **kwargs):
        kwargs["parents"] = list(kwargs.get("parents", [])) + [global_options]
        kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
        return _add_parser(name, **kwargs)
    subparsers.add_parser = add_parser_with_global_options
    
    # init
    init_parser = subparsers.add_parser(
        "init", help="Initialize SPEKY (new idea, or read an existing project with --from-project)",
        epilog="""Examples:
  speky init "A grocery list app for families"   # new product: answer a few questions
  speky init --from-project                      # existing repo: answers come from its README,
                                                 # docs, CLAUDE.md/AGENTS.md and manifests
  speky init --from-project --host               # ...with the calling agent as the model
  speky init --from-project                      # in an initialized project: refresh profile
                                                 # and tech stack, keep specs/stories/phases

Unattended runs (no terminal, --yes, agents) in a project that already has docs or
manifests use --from-project automatically.""")
    init_parser.add_argument("idea", nargs="?",
                             help="Your product idea (optional with --from-project: read from the README)")
    init_parser.add_argument("--from-project", action="store_true",
                             help="Answer init's questions from this project's own docs, manifests and "
                                  "structure instead of asking (you can still accept/override each answer)")
    
    # spec
    spec_parser = subparsers.add_parser("spec", help="Create feature specification")
    spec_parser.add_argument("feature", help="Feature name")
    
    # plan
    plan_parser = subparsers.add_parser("plan", help="Generate implementation plan")
    plan_parser.add_argument("spec_id", help="Spec ID (e.g., 001)")
    plan_parser.add_argument("--check", "-c", action="store_true", help="Run pre-planning codebase analysis (opt-in, can be unreliable)")
    
    # epic
    epic_parser = subparsers.add_parser("epic", help="Create or manage epics")
    epic_parser.add_argument("name_or_id", nargs="?", help="Epic name (for creation) or Epic ID (for show/modify)")
    epic_parser.add_argument("--spec", "-s", help="Related spec ID (for creation)")
    epic_parser.add_argument("--stories", help="Comma-separated story IDs to include (for creation)")
    epic_parser.add_argument("--add", "-a", help="Add story to epic")
    epic_parser.add_argument("--remove", "-r", help="Remove story from epic")
    
    # epics (list all)
    subparsers.add_parser("epics", help="List all epics with status")
    
    # story
    story_parser = subparsers.add_parser("story", help="Create a story")
    story_parser.add_argument("title", help="Story title")
    story_parser.add_argument("--type", "-t", default="feature", 
                             choices=["feature", "bug", "enhancement", "tech_debt", "spike"],
                             help="Story type")
    story_parser.add_argument("--epic", "-e", help="Epic ID to add story to")
    story_parser.add_argument("--spec", "-s", help="Related spec ID (single)")
    story_parser.add_argument("--specs", help="Related spec IDs (comma-separated)")
    story_parser.add_argument("--files", "-f", help="Affected files (comma-separated)")
    story_parser.add_argument("--no-spec", action="store_true", help="Explicitly standalone (no spec linking)")
    
    # implement
    impl_parser = subparsers.add_parser("implement", help="Hand off to IDE")
    impl_parser.add_argument("item_id", help="Spec or story ID")
    impl_parser.add_argument("--tdd", action="store_true", help="Start TDD workflow (generate tests first)")
    
    # complete
    complete_parser = subparsers.add_parser("complete", help="Mark feature as complete with drift detection")
    complete_parser.add_argument("spec_id", help="Spec ID (e.g., 001)")
    complete_parser.add_argument("--test", action="store_true", help="Run tests before marking complete")
    complete_parser.add_argument("--test-type", choices=["unit", "integration", "e2e", "all"], default="all",
                                help="Type of tests to run (requires --test)")
    
    # commit
    commit_parser = subparsers.add_parser("commit", help="Commit a completed feature")
    commit_parser.add_argument("spec_id", help="Spec ID (e.g., 001)")
    commit_parser.add_argument("--edit", "-e", action="store_true", help="Edit commit message before committing")
    
    # status
    subparsers.add_parser("status", help="Show project status")
    
    # sync
    subparsers.add_parser("sync", help="Sync codebase context")
    
    # review
    review_parser = subparsers.add_parser("review", help="Check for drift")
    review_parser.add_argument("spec_id", nargs="?", help="Specific spec to review")
    
    # cleanup
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up clutter files")
    cleanup_parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be deleted without deleting")
    
    # backlog
    subparsers.add_parser("backlog", help="Review and manage deferred backlog items")
    
    # validate-spec
    validate_parser = subparsers.add_parser("validate-spec", help="Validate a spec for quality and completeness")
    validate_parser.add_argument("spec_ref", help="Spec ID (e.g., 001) or file path")
    validate_parser.add_argument("--quick", "-q", action="store_true", help="Quick mode - show summary without interactive review")
    
    # validate-story
    validate_story_parser = subparsers.add_parser("validate-story", help="Validate a story for completeness (AI-powered)")
    validate_story_parser.add_argument("story_ref", help="Story ID (e.g., F001) or file path")
    validate_story_parser.add_argument("--quick", "-q", action="store_true", help="Quick mode - show summary without interactive review")
    
    # adopt (supports both specs and stories)
    adopt_parser = subparsers.add_parser("adopt", help="Adopt an IDE-created spec or story into SPEKY tracking")
    adopt_parser.add_argument("item_id", help="Spec ID (e.g., 001) or Story ID (e.g., F001)")
    adopt_parser.add_argument("--type", "-t", dest="item_type", choices=["spec", "story"], help="Item type (auto-detected from ID if not specified)")
    adopt_parser.add_argument("--skip-validation", "-s", action="store_true", help="Skip basic validation")
    
    # import
    import_parser = subparsers.add_parser("import", help="Import external knowledge from .speky/imports/<phase>/source/")
    import_parser.add_argument("--phase", "-p", help="Phase name (e.g., mvp, v2-features)")
    import_parser.add_argument("--no-review", action="store_true", help="Skip interactive review")
    
    # import-status
    subparsers.add_parser("import-status", help="Show status of all imports")
    
    # reconcile
    reconcile_parser = subparsers.add_parser("reconcile", help="Reconcile code with imported docs and specs")
    reconcile_parser.add_argument("phase", help="Import phase to reconcile")
    reconcile_parser.add_argument("--spec", help="Specific spec ID to reconcile")
    reconcile_parser.add_argument("--dry-run", "-n", action="store_true", help="Preview changes without applying")
    
    # poc-import
    poc_parser = subparsers.add_parser("poc-import", help="Import features from existing POC codebase")
    poc_parser.add_argument("--path", "-p", help="Path to POC project")
    poc_parser.add_argument("--spec", "-s", help="Link POC to existing spec ID")
    poc_parser.add_argument("--resume", "-r", action="store_true", help="Resume incomplete import session")
    
    # sequence
    sequence_parser = subparsers.add_parser("sequence", help="Show unified implementation roadmap with dependency analysis")
    sequence_parser.add_argument("--export", "-e", action="store_true", help="Export roadmap to .speky/roadmap.md")
    
    # infer-deps
    infer_parser = subparsers.add_parser("infer-deps", help="AI-assisted dependency inference for specs")
    infer_parser.add_argument("spec_id", nargs="?", help="Specific spec ID (or all if omitted)")
    
    # mark-foundation
    foundation_parser = subparsers.add_parser("mark-foundation", help="Mark spec as foundation (clears deps)")
    foundation_parser.add_argument("spec_id", help="Spec ID to mark as foundation")
    
    # reset-deps
    reset_parser = subparsers.add_parser("reset-deps", help="Reset dependencies for spec(s)")
    reset_parser.add_argument("spec_id", nargs="?", help="Spec ID to reset (or use --all)")
    reset_parser.add_argument("--all", "-a", action="store_true", dest="all_specs", help="Reset all specs")
    
    # fix-circular-deps
    fix_circular_parser = subparsers.add_parser("fix-circular-deps", help="Interactive fix for circular dependencies")
    
    # renumber
    renumber_parser = subparsers.add_parser("renumber", help="Renumber specs to match implementation order")
    renumber_parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    
    # decisions
    decisions_parser = subparsers.add_parser("decisions", help="View and manage tech decisions")
    decisions_parser.add_argument("--add", "-a", action="store_true", help="Add a new tech decision interactively")
    decisions_parser.add_argument("--edit", "-e", action="store_true", help="Open tech_decisions.md for editing")
    decisions_parser.add_argument("--generate", "-g", action="store_true", help="Regenerate from context.json")
    
    # config (SPEKY Configuration)
    config_parser = subparsers.add_parser("config", help="View and manage SPEKY configuration")
    config_parser.add_argument("--ides", nargs="*", default=None,
                               help="Manage enabled IDEs: no args=show, add <ide>, remove <ide>, set <ide1,ide2,...>")
    config_parser.add_argument("--list-ides", action="store_true", help="List all supported IDEs")
    config_parser.add_argument("--model", nargs="?", const="", default=None,
                               metavar="PROVIDER/MODEL",
                               help="No value: show current model and pick one interactively. With a value: "
                                    "set it, e.g. openrouter/moonshotai/kimi-k2, claude-code/sonnet, host "
                                    "(saved to ~/.speky/models.yaml). An env var name like GEMINI_MODEL is resolved.")
    config_parser.add_argument("--providers", action="store_true", help="List AI providers and whether their keys are set")
    
    # design (Design System Management)
    design_parser = subparsers.add_parser("design", help="Manage design system (init, import, status, analyze, link, resolve, validate)")
    design_parser.add_argument("action", choices=["init", "import", "status", "analyze", "link", "resolve", "validate"],
                               help="Action: init, import, status, analyze, link, resolve, validate")
    design_parser.add_argument("path", nargs="?", help="Path to design file(s) or folder")
    design_parser.add_argument("--type", "-t", dest="design_type", choices=["hifi", "lofi", "icons", "system"],
                               help="Design type (hifi, lofi, icons, system)")
    design_parser.add_argument("--tech", help="UI technology (flutter, react, vue, etc.)")
    design_parser.add_argument("--spec", "-s", dest="spec_id", help="Link to spec ID")
    design_parser.add_argument("--analyze", "-a", action="store_true", help="Analyze after import")
    
    # phases (Multi-Spec Coordination Layer)
    phases_parser = subparsers.add_parser("phases", help="Manage project phases for multi-spec coordination")
    phases_parser.add_argument("action", choices=["list", "show", "status", "start", "complete", "guide", "create", "suggest"],
                               help="Action: list, show, status, start, complete, guide, create, suggest")
    phases_parser.add_argument("phase_id", nargs="?", help="Phase ID (required for show, start, complete, guide)")
    phases_parser.add_argument("--for-ai", action="store_true", help="Generate AI-optimized output (for guide action)")
    
    # context (AI context generation for phases)
    context_parser = subparsers.add_parser("context", help="Generate AI context for phase implementation")
    context_parser.add_argument("--phase", "-p", help="Phase ID (uses current phase if not specified)")
    context_parser.add_argument("--format", "-f", default="prompt", choices=["prompt", "markdown"],
                                help="Output format (default: prompt)")
    
    # test (Testing Integration - loaded from speky_testing.py)
    test_parser = subparsers.add_parser("test", help="Testing commands (init, gen, run, coverage, status, e2e, link, gaps, recommend, setup)")
    test_parser.add_argument("action", choices=["init", "gen", "run", "coverage", "status", "e2e", "link", "gaps", "recommend", "setup", "refresh-context", "refresh-guide", "tdd-red", "tdd-green", "tdd-status", "complete", "triage"],
                            help="Testing action to perform")
    test_parser.add_argument("target", nargs="?", help="Target spec ID, test file, or other argument")
    test_parser.add_argument("--type", dest="test_type", choices=["unit", "widget", "integration", "e2e", "all"],
                            default="all", help="Type of tests to run/generate")
    test_parser.add_argument("--spec", dest="spec_id", help="Filter by spec ID")
    test_parser.add_argument("--affected", action="store_true", help="Run only tests affected by recent changes")
    test_parser.add_argument("--failed", action="store_true", help="Re-run previously failed tests")
    test_parser.add_argument("--coverage", action="store_true", help="Run with coverage reporting")
    test_parser.add_argument("--platform", choices=["web", "mobile", "all"], default="all",
                            help="Platform for E2E tests")
    test_parser.add_argument("--headed", action="store_true", help="Run E2E tests with visible browser")
    test_parser.add_argument("--refresh", action="store_true", help="Refresh cached data (for setup command)")
    test_parser.add_argument("--e2e", action="store_true", help="Scaffold E2E infrastructure (for init command)")
    
    # host (Host mode: the calling agent answers SPEKY's prompts)
    host_parser = subparsers.add_parser(
        "host", help="Host mode: answer SPEKY's prompts from the agent that runs it",
        description="In host mode (--host or SPEKY_MODEL=host) SPEKY makes no LLM calls. Each "
                    "prompt is written to .speky/host/NNN.prompt.md and SPEKY waits until the "
                    "answer is delivered, then continues.",
        epilog="""Examples:
  speky spec "Login" --host &        # run in the background; it waits on each prompt
  speky host status                  # which prompt is waiting
  speky host show                    # read it
  speky host answer 001 --file answer.md
  speky host guide >> CLAUDE.md      # teach your agent the loop""")
    host_parser.add_argument("action", nargs="?", default="status",
                             choices=["status", "show", "answer", "guide"],
                             help="status (default) | show [ID] | answer ID | guide")
    host_parser.add_argument("request_id", nargs="?", help="Request ID, e.g. 001 (default: oldest waiting)")
    host_parser.add_argument("--file", "-f", help="Answer file for `answer` (default: read stdin)")

    argv, global_opts = _extract_global_options(sys.argv[1:])
    _apply_global_options(global_opts)
    args = parser.parse_args(argv)
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize SPEKY
    speky = SPEKY()
    
    # Execute command
    try:
        if args.command == "init":
            success = speky.cmd_init(args.idea, from_project=args.from_project)
        elif args.command == "spec":
            success = speky.cmd_spec(args.feature)
        elif args.command == "plan":
            success = speky.cmd_plan(args.spec_id, run_check=args.check)
        elif args.command == "epic":
            # Determine if name_or_id is a name (for creation) or ID (for show/modify)
            name_or_id = args.name_or_id
            if name_or_id and name_or_id.startswith("E") and name_or_id[1:4].isdigit():
                # It's an epic ID (E001, E002, etc.)
                success = speky.cmd_epic(
                    name=None, 
                    epic_id=name_or_id, 
                    spec=args.spec,
                    stories=args.stories,
                    add=args.add, 
                    remove=args.remove
                )
            elif name_or_id:
                # It's a name for creation
                success = speky.cmd_epic(
                    name=name_or_id, 
                    epic_id=None,
                    spec=args.spec,
                    stories=args.stories,
                    add=args.add, 
                    remove=args.remove
                )
            else:
                # No name or ID provided
                Console.error("Please provide an epic name or ID")
                success = False
        elif args.command == "epics":
            success = speky.cmd_epics()
        elif args.command == "story":
            success = speky.cmd_story(
                args.title, 
                args.type,
                epic=args.epic,
                spec=args.spec,
                specs=args.specs,
                files=args.files,
                no_spec=args.no_spec
            )
        elif args.command == "implement":
            success = speky.cmd_implement(args.item_id, tdd=getattr(args, 'tdd', False))
        elif args.command == "complete":
            success = speky.cmd_complete(args.spec_id, run_tests=args.test, test_type=args.test_type)
        elif args.command == "commit":
            success = speky.cmd_commit(args.spec_id, edit=args.edit)
        elif args.command == "status":
            success = speky.cmd_status()
        elif args.command == "sync":
            success = speky.cmd_sync()
        elif args.command == "review":
            success = speky.cmd_review(args.spec_id)
        elif args.command == "cleanup":
            success = speky.cmd_cleanup(dry_run=args.dry_run)
        elif args.command == "backlog":
            success = speky.cmd_backlog()
        elif args.command == "validate-spec":
            success = speky.cmd_validate_spec(args.spec_ref, quick=args.quick)
        elif args.command == "validate-story":
            success = speky.cmd_validate_story(args.story_ref, quick=args.quick)
        elif args.command == "adopt":
            success = speky.cmd_adopt(args.item_id, item_type=args.item_type, skip_validation=args.skip_validation)
        elif args.command == "import":
            success = speky.cmd_import(phase=args.phase, no_review=args.no_review)
        elif args.command == "import-status":
            success = speky.cmd_import_status()
        elif args.command == "reconcile":
            success = speky.cmd_reconcile(args.phase, spec_id=args.spec, dry_run=args.dry_run)
        elif args.command == "poc-import":
            success = speky.cmd_poc_import(path=args.path, spec_id=args.spec, resume=args.resume)
        elif args.command == "sequence":
            success = speky.cmd_sequence(export=args.export)
        elif args.command == "infer-deps":
            success = speky.cmd_infer_deps(spec_id=args.spec_id)
        elif args.command == "mark-foundation":
            success = speky.cmd_mark_foundation(spec_id=args.spec_id)
        elif args.command == "reset-deps":
            success = speky.cmd_reset_deps(spec_id=args.spec_id, all_specs=args.all_specs)
        elif args.command == "fix-circular-deps":
            success = speky.cmd_fix_circular_deps()
        elif args.command == "renumber":
            success = speky.cmd_renumber(dry_run=args.dry_run)
        elif args.command == "decisions":
            success = speky.cmd_decisions(add=args.add, edit=args.edit, generate=args.generate)
        elif args.command == "config":
            # Parse --ides arguments: [], ["add", "antigravity"], ["set", "windsurf,antigravity"], etc.
            ides_args = args.ides if args.ides is not None else None
            if ides_args is not None:
                if len(ides_args) == 0:
                    # Just --ides with no args = show
                    ides_mode = "show"
                    ides_action = None
                    ides_value = None
                elif len(ides_args) == 1:
                    # Could be action without value (error) or single IDE for set
                    if ides_args[0] in ["add", "remove", "set"]:
                        ides_mode = ides_args[0]
                        ides_action = ides_args[0]
                        ides_value = None
                    else:
                        ides_mode = "show"
                        ides_action = None
                        ides_value = None
                else:
                    # --ides add antigravity OR --ides set windsurf,antigravity
                    ides_mode = ides_args[0]
                    ides_action = ides_args[0] if ides_args[0] in ["add", "remove", "set"] else None
                    ides_value = ides_args[1] if len(ides_args) > 1 else None
            else:
                ides_mode = None
                ides_action = None
                ides_value = None
            
            success = speky.cmd_config(
                ides=ides_mode,
                action=ides_action,
                value=ides_value,
                list_ides=args.list_ides,
                model=args.model,
                providers=args.providers
            )
        elif args.command == "design":
            success = speky.cmd_design(
                action=args.action,
                design_type=args.design_type,
                path=args.path,
                tech=args.tech,
                spec_id=args.spec_id,
                analyze=args.analyze
            )
        elif args.command == "phases":
            success = speky.cmd_phases(args.action, phase_id=args.phase_id, for_ai=args.for_ai)
        elif args.command == "host":
            success = speky.cmd_host(args.action, request_id=args.request_id, file=args.file)
        elif args.command == "context":
            success = speky.cmd_context(phase_id=args.phase, format=args.format)
        elif args.command == "test":
            # Testing Integration (delegated to speky_testing.py)
            if speky.testing:
                success = speky.testing.cmd_test(args)
            else:
                Console.error("Testing module not available. Ensure speky_testing.py is in the same directory.")
                success = False
        else:
            parser.print_help()
            success = False
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n⛔ Interrupted")
        sys.exit(130)
    except Exception as e:
        Console.error(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
