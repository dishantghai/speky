"""Every `speky …` example in the skills and docs must parse with today's CLI."""
import contextlib
import io
import re
import shlex
from pathlib import Path

from speky_core.cli import _parser, _strip_noop_flags

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted((ROOT / "speky_core" / "skills").glob("*/SKILL.md")) + [
    ROOT / p for p in ("README.md", "MODELS.md", "docs/v3/CONTRACTS.md", "docs/v3/MIGRATION.md")]


def examples():
    for path in DOCS:
        text = path.read_text()
        found = re.findall(r"`(speky [^`\n]+)`", text) + \
            re.findall(r"^(speky [^\n#]+?)\s*(?:#.*)?$", text, re.MULTILINE)
        for snippet in found:
            if any(t in snippet for t in ("…", "...", "|", "[")):
                continue  # synopsis, not an example
            snippet = re.sub(r"<(id|item|ref)>", "001", snippet)
            snippet = re.sub(r"<[^>]+>", "x", snippet)
            try:
                yield path.relative_to(ROOT), shlex.split(snippet)[1:]
            except ValueError:
                continue


def test_doc_examples_parse():
    failures = []
    for where, argv in examples():
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                _parser().parse_args(_strip_noop_flags(argv))
        except SystemExit as e:
            message = err.getvalue()
            # a bare mention ("use `speky check`") lacks arguments; a wrong flag or name is a real error
            if e.code and ("unrecognized arguments" in message or "invalid choice" in message):
                failures.append(f"{where}: speky {' '.join(argv)} → {err.getvalue().strip().splitlines()[-1]}")
    assert not failures, "\n".join(failures)
