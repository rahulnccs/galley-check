"""Plain-text and JSON reports. (HTML and commented .docx come later.)"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from ..model.document import SEVERITY_ORDER, Document, Issue

HEADINGS = {"error": "ERRORS", "warning": "WARNINGS", "info": "NOTES"}


def _where(doc: Document, issue: Issue) -> str:
    if issue.para_index is None:
        return ""
    p = doc.paragraph(issue.para_index)
    snippet = issue.anchor or p.text[:50]
    return f'\n      at paragraph {issue.para_index + 1} ({p.section}): "{snippet}"'


def render_text(doc: Document, issues: list[Issue]) -> str:
    lines = [f"Manuscript check: {Path(doc.path).name}"]
    sources = Counter(c.source for c in doc.citations)
    cite_info = ", ".join(f"{s.capitalize()} {n}" for s, n in sorted(sources.items()))
    lines.append(f"Read {sum(1 for p in doc.paragraphs if p.text)} paragraphs; "
                 f"{len(doc.citations)} reference-manager citations"
                 + (f" ({cite_info})" if cite_info else ""))
    lines.append("")

    if not issues:
        lines.append("No problems found.")
        return "\n".join(lines)

    issues = sorted(issues, key=lambda i: (SEVERITY_ORDER[i.severity],
                                           i.para_index if i.para_index is not None else -1))
    for sev in ("error", "warning", "info"):
        group = [i for i in issues if i.severity == sev]
        if not group:
            continue
        lines.append(f"{HEADINGS[sev]} ({len(group)})")
        for i in group:
            lines.append(f"  [{i.check}] {i.message}{_where(doc, i)}")
            if i.suggestion:
                lines.append(f"      -> {i.suggestion}")
        lines.append("")
    counts = Counter(i.severity for i in issues)
    lines.append(f"Summary: {counts['error']} errors, {counts['warning']} warnings, "
                 f"{counts['info']} notes")
    return "\n".join(lines)


def render_json(doc: Document, issues: list[Issue]) -> str:
    return json.dumps({"file": doc.path, "issues": [asdict(i) for i in issues]}, indent=2)
