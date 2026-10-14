"""Guard: no v2 capability is lost.

Every v2 command has a row here naming its home in SPEKY today (docs/v3/PLAN.md §11). A "built" row
must point at commands that exist; "dropped" rows were agreed with the owner. The v2 implementation
was deleted once every row was built or dropped; V2_COMMANDS is the frozen list of what it had.
"""
from speky_core.cli import COMMANDS

# every `speky <command>` of SPEKY v2 (0.5.x): its cmd_* methods plus `test`
V2_COMMANDS = {
    "init", "spec", "story", "adopt", "validate_spec", "validate_story", "plan", "implement", "complete",
    "commit", "status", "sync", "review", "cleanup", "backlog", "import", "import_status", "reconcile",
    "poc_import", "sequence", "infer_deps", "mark_foundation", "reset_deps", "fix_circular_deps",
    "renumber", "decisions", "config", "design", "phases", "context", "epic", "epics", "host", "test",
}

# v2 command -> (status, v3 commands that replace it)
HOMES = {
    "init":              ("built",   ["init"]),
    "spec":              ("built",   ["new", "spec"]),
    "story":             ("built",   ["new", "story"]),
    "adopt":             ("built",   ["check"]),
    "validate_spec":     ("built",   ["check", "finding"]),
    "validate_story":    ("built",   ["check", "finding"]),
    "plan":              ("built",   ["plan", "context"]),
    "implement":         ("built",   ["start", "context"]),
    "complete":          ("built",   ["verify", "archive"]),
    "commit":            ("built",   ["commit"]),
    "status":            ("built",   ["status", "state"]),
    "sync":              ("dropped", ["remember", "knowledge"]),   # owner agreed 2026-10-14
    "review":            ("built",   ["review"]),
    "cleanup":           ("built",   ["cleanup"]),
    "backlog":           ("built",   ["task", "backlog"]),
    "import":            ("built",   ["import"]),
    "import_status":     ("built",   ["import"]),
    "reconcile":         ("built",   ["import"]),
    "poc_import":        ("built",   ["import"]),
    "sequence":          ("built",   ["order"]),
    "infer_deps":        ("built",   ["deps"]),
    "mark_foundation":   ("built",   ["deps"]),
    "reset_deps":        ("built",   ["deps"]),
    "fix_circular_deps": ("built",   ["deps"]),
    "renumber":          ("dropped", ["order"]),                    # owner agreed 2026-10-14
    "decisions":         ("built",   ["decide", "adr", "knowledge"]),
    "config":            ("built",   ["config", "setup"]),
    "design":            ("built",   ["design"]),
    "phases":            ("built",   ["phases"]),
    "context":           ("built",   ["context"]),
    "epic":              ("built",   ["epic"]),
    "epics":             ("built",   ["epic"]),
    "host":              ("dropped", []),                           # owner agreed 2026-10-14
    "test":              ("built",   ["test"]),
}


def test_every_v2_command_has_a_home():
    missing = sorted(V2_COMMANDS - set(HOMES))
    assert not missing, f"v2 commands with no planned home: {missing}"


def test_built_rows_point_at_existing_commands():
    broken = {k: [c for c in v if c not in COMMANDS] for k, (status, v) in HOMES.items() if status == "built"}
    assert not {k: v for k, v in broken.items() if v}


def test_no_v2_capability_is_pending():
    pending = sorted(k for k, (status, _) in HOMES.items() if status not in ("built", "dropped"))
    assert not pending, f"v2 commands without a home: {pending}"


def test_progress_report():
    """Not a check; prints how far the move is (pytest -s)."""
    built = [k for k, (s, _) in HOMES.items() if s == "built"]
    print(f"\nv2 → new SPEKY: {len(built)}/{len(HOMES)} built, "
          f"{len([1 for s, _ in HOMES.values() if s == 'dropped'])} dropped by agreement")


def test_help_lists_every_command():
    import re
    from speky_core.cli import HELP
    unlisted = sorted(c for c in COMMANDS if not re.search(r"(?<![\w-])" + re.escape(c) + r"(?![\w-])", HELP))
    assert not unlisted, f"commands missing from `speky --help`: {unlisted}"
