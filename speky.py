#!/usr/bin/env python3
"""SPEKY: spec-driven development for AI coding agents.

SPEKY keeps the state, rules and evidence of a project in `.speky/`; the coding agent you already use
(Claude Code, Codex, Cursor, Copilot, ...) does the reasoning by following SPEKY's skills and the
`speky` CLI. Without an agent, `speky run` is SPEKY's own. Everything lives in `speky_core`.
Run `speky --help`.
"""
import sys


def main():
    from speky_core.cli import main as cli_main
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        argv = ["--help"]
    try:
        sys.exit(cli_main(argv))
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
