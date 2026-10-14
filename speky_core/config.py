"""`.speky/speky.yaml` — v3 settings (real YAML, unlike v2's config.yaml)."""
from pathlib import Path

import yaml

SPEKY_DIR = ".speky"
CONFIG_NAME = "speky.yaml"

DEFAULTS = {
    "version": 3,
    "agent_profile": "conservative",
    "id_style": "sequential",
    "max_rounds": 2,
    "max_questions": 5,
    "max_clarification_markers": 3,
    "max_spec_lines": 250,
    "verify_command": "",
    "harnesses": [],
}


def speky_dir(root: Path) -> Path:
    return Path(root) / SPEKY_DIR


def find_root(start: Path = None) -> Path:
    """Nearest folder (from start upward) containing `.speky/`; falls back to start."""
    start = Path(start or Path.cwd()).resolve()
    for folder in (start, *start.parents):
        if (folder / SPEKY_DIR).is_dir():
            return folder
    return start


def load(root: Path) -> dict:
    path = speky_dir(root) / CONFIG_NAME
    data = {}
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
    return {**DEFAULTS, **data}


def save(root: Path, config: dict) -> Path:
    path = speky_dir(root) / CONFIG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {key: config.get(key, DEFAULTS.get(key)) for key in DEFAULTS}
    ordered.update({k: v for k, v in config.items() if k not in ordered})
    path.write_text("# SPEKY v3 settings — reference: https://github.com/dishantghai/speky/blob/main/docs/v3/CONTRACTS.md#8-spekyyaml\n"
                    + yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, width=110))
    return path
