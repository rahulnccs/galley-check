"""Command-line interface:  galley paper.docx [--json]"""
from __future__ import annotations

import argparse
import sys

from .checks.registry import OFFLINE_CHECKS
from .engine import load, run_checks
from .checks.offline.submission import PROFILE_DIR, Profile
from .report.docx_comments import annotate, default_output_path
from .report.text_report import render_json, render_text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="galley",
                                 description="Offline sanity checks for manuscript drafts.")
    ap.add_argument("file", help="manuscript (.docx)")
    ap.add_argument("--json", action="store_true", help="output JSON instead of text")
    ap.add_argument("--only", nargs="+", choices=sorted(OFFLINE_CHECKS),
                    help="run only these checks")
    ap.add_argument("--profile", metavar="NAME_OR_FILE",
                    help="journal profile with word and item limits (a JSON file, "
                         f"or a name from {PROFILE_DIR})")
    ap.add_argument("--comments", nargs="?", const="", metavar="OUT.docx",
                    help="also save a copy of the manuscript with Word comments "
                         "at each problem (the original is never changed)")
    ap.add_argument("--comment-level", choices=["error", "warning", "info"],
                    default="info",
                    help="lowest severity to comment on (default: info, meaning all)")
    args = ap.parse_args(argv)

    try:
        doc = load(args.file)
    except Exception as e:  # unreadable or unsupported file
        print(f"Could not read {args.file}: {e}", file=sys.stderr)
        return 2
    profile = None
    if args.profile:
        try:
            profile = Profile.load(args.profile)
        except (OSError, ValueError) as e:
            print(f"Could not read the profile {args.profile}: {e}", file=sys.stderr)
            return 2
    issues = run_checks(doc, args.only, profile=profile)
    print(render_json(doc, issues) if args.json else render_text(doc, issues))

    if args.comments is not None:
        levels = {"error": ("error",), "warning": ("error", "warning"),
                  "info": ("error", "warning", "info")}[args.comment_level]
        out = args.comments or default_output_path(args.file)
        try:
            written = annotate(doc, issues, out, severities=levels)
            print(f"\nCommented copy saved to {written}")
        except Exception as e:
            print(f"\nCouldn't write the commented copy: {e}", file=sys.stderr)
    return 1 if any(i.severity == "error" for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
