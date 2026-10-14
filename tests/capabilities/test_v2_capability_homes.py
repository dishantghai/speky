"""Guard: no v2 capability is lost.

Every v2 command (`cmd_*` on the v2 SPEKY class, plus `test`) has a row here naming its home in the new
SPEKY (docs/v3/PLAN.md §11). A row marked "built" must point at v3 commands that exist. A v2 command may
only be deleted from speky.py once its row is "built" (or "dropped" with the owner's agreement).
"""
import speky
from speky_core.cli import COMMANDS

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


def v2_commands():
    names = {m[4:] for m in dir(speky.SPEKY) if m.startswith("cmd_")}
    return names | {"test"}


def test_every_v2_command_has_a_home():
    missing = sorted(v2_commands() - set(HOMES))
    assert not missing, f"v2 commands with no planned home: {missing}"


def test_built_rows_point_at_existing_commands():
    broken = {k: [c for c in v if c not in COMMANDS] for k, (status, v) in HOMES.items() if status == "built"}
    assert not {k: v for k, v in broken.items() if v}


def test_v2_commands_are_only_removed_once_their_home_is_built():
    removed = set(HOMES) - v2_commands()
    not_ready = sorted(k for k in removed if HOMES[k][0] == "pending")
    assert not not_ready, f"v2 commands removed before their new home was built: {not_ready}"


def test_progress_report():
    """Not a check; prints how far the move is (pytest -s)."""
    built = [k for k, (s, _) in HOMES.items() if s == "built"]
    print(f"\nv2 → new SPEKY: {len(built)}/{len(HOMES)} built, "
          f"{len([1 for s, _ in HOMES.values() if s == 'dropped'])} dropped by agreement")
