"""Command-line interface:  galley paper.docx [--json]"""
from __future__ import annotations

import argparse
import sys

from .checks.registry import OFFLINE_CHECKS
from .engine import load, run_checks
from .report.text_report import render_json, render_text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="galley",
                                 description="Offline sanity checks for manuscript drafts.")
    ap.add_argument("file", help="manuscript (.docx)")
    ap.add_argument("--json", action="store_true", help="output JSON instead of text")
    ap.add_argument("--only", nargs="+", choices=sorted(OFFLINE_CHECKS),
                    help="run only these checks")
    args = ap.parse_args(argv)

    try:
        doc = load(args.file)
    except Exception as e:  # unreadable or unsupported file
        print(f"Could not read {args.file}: {e}", file=sys.stderr)
        return 2
    issues = run_checks(doc, args.only)
    print(render_json(doc, issues) if args.json else render_text(doc, issues))
    return 1 if any(i.severity == "error" for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
