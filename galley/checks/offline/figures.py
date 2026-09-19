"""Figure and table callout checks.

Finds every in-text mention ("Fig. 2A", "Figures 1-3", "Supplementary Fig. S1b,c",
"Table 2", "Extended Data Fig. 4") and every legend/caption ("Figure 2. ...",
"Table 1: ...") and checks that they agree:

  * every figure/table cited in the text has a legend or caption
  * every legend/caption is cited in the text
  * figures/tables are first cited in numerical order
  * legend numbering has no gaps
  * cited panels exist in the legend (when the legend labels its panels)
  * mixed "Fig." vs "Figure" usage (info only)
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from ...model.document import REFERENCES, Document, Issue

CHECK = "figures"

_PREFIX = (r"(?P<prefix>(?:Supp(?:l(?:ement(?:ary|al)?)?)?\.?"
           r"|Extended\s+Data|Online\s+Resource)\s*)?")
_ITEM = r"S?\d+[A-Za-z]?(?![A-Za-z0-9])"
_SEP = r"\s*(?:[\u2013\u2014-]|,|;|and|&)\s*"
CALLOUT_RE = re.compile(
    r"\b" + _PREFIX
    + r"(?P<kind>Fig(?:ure)?s?\.?|Tables?)\s*"
    + rf"(?P<spec>{_ITEM}(?:{_SEP}(?:{_ITEM}|[A-Za-z](?![A-Za-z0-9])))*)",
    re.I,
)
# A legend starts a paragraph: "Figure 2. Title", "Table 1: Title",
# "Supplementary Figure 3, related to Figure 1. Title", "Figure 4 Title".
LEGEND_RE = re.compile(
    r"^\s*" + _PREFIX
    + r"(?P<kind>Fig(?:ure)?\.?|Table)\s*(?P<num>S?\d+)"
    + r"(?P<related>\s*,\s*(?:related|corresponding|associated|linked)\s+to[^.]{0,80})?"
    # The uppercase tests must stay case-sensitive even though re.I is set,
    # otherwise ordinary sentences like "Fig. 8 extends ..." look like legends.
    + r"\s*(?:[.:;|\u2013\u2014-]|,\s+(?-i:[A-Z])|\s+(?-i:[A-Z][a-z]))",
    re.I,
)
_TOKEN_RE = re.compile(r"S?\d+[A-Za-z]?|[A-Za-z]+|[\u2013\u2014-]|[,;&]", re.I)


@dataclass(frozen=True)
class ItemKey:
    kind: str       # "figure" | "table"
    group: str      # "main" | "supplementary" | "extended"
    number: int

    @property
    def label(self) -> str:
        noun = "Figure" if self.kind == "figure" else "Table"
        if self.group == "supplementary":
            return f"Supplementary {noun} S{self.number}"
        if self.group == "extended":
            return f"Extended Data {noun} {self.number}"
        return f"{noun} {self.number}"


@dataclass
class Callout:
    key: ItemKey
    panels: set[str]
    para_index: int
    position: int
    text: str           # the exact matched text, used to anchor comments
    abbreviated: bool   # "Fig." rather than "Figure"


@dataclass
class Legend:
    key: ItemKey
    para_index: int
    text: str
    anchor: str         # the label as written, e.g. "Figure 4."
    panels: set[str] = field(default_factory=set)


def _group(prefix: str | None, label: str) -> str:
    if prefix and "extended" in prefix.lower():
        return "extended"
    if prefix or label.upper().startswith("S"):
        return "supplementary"
    return "main"


def _letters(a: str, b: str) -> set[str]:
    lo, hi = sorted((a.upper(), b.upper()))
    return {chr(c) for c in range(ord(lo), ord(hi) + 1)}


def parse_spec(spec: str) -> dict[str, set[str]]:
    """'1A-C, 2 and 3b' -> {'1': {A,B,C}, '2': set(), '3': {B}}.

    Keys are figure labels as written ('1', 'S2'); an empty set means the
    whole figure was cited.
    """
    result: dict[str, set[str]] = {}
    current: str | None = None
    last_panel: str | None = None
    lowercase_panels = False
    pending_range = False

    for tok in _TOKEN_RE.findall(spec):
        low = tok.lower()
        if tok in ("-", "\u2013", "\u2014"):
            pending_range = True
            continue
        if tok in (",", ";", "&") or low == "and":
            pending_range = False
            continue

        m = re.fullmatch(r"(S?)(\d+)([A-Za-z]?)", tok, re.I)
        if m:
            s, num, panel = m.group(1).upper(), m.group(2), m.group(3)
            label = f"{s}{num}"
            if pending_range and current is not None and last_panel is None:
                # Figure range like "1-3" or "S1-S3": include everything between.
                start = int(re.sub(r"\D", "", current))
                for n in range(start + 1, int(num)):
                    result.setdefault(f"{s}{n}", set())
            result.setdefault(label, set())
            if panel:
                result[label].add(panel.upper())
                lowercase_panels = panel.islower()
            current, last_panel = label, (panel.upper() or None)
            pending_range = False
            continue

        if len(tok) == 1 and current is not None:
            # A bare panel letter continuing the previous figure: "1A, B" or "1a-c".
            if tok.islower() and not lowercase_panels:
                break  # probably ordinary text, e.g. "Fig. 2 and a ..."
            if pending_range and last_panel:
                result[current] |= _letters(last_panel, tok)
            else:
                result[current].add(tok.upper())
            last_panel = tok.upper()
            pending_range = False
            continue
        break
    return result


_REFERENCE_HINTS = re.compile(
    r"\bet al\b|\bdoi\b|\bpp?\.\s*\d|\b(19|20)\d\d[;:)]|\bvol\b", re.I)


def _looks_like_reference(text: str) -> bool:
    """True for a reference-list entry that happens to start like a legend.

    Legends after the reference list are normal practice, so a paragraph is
    only rejected when it reads like a citation (authors, journal, year, DOI)
    and shows no sign of being a legend.
    """
    head = text[:220]
    legend_signs = "(A)" in head or "(a)" in head or len(text) > 400
    return bool(_REFERENCE_HINTS.search(head)) and not legend_signs


def _legend_panels(text: str) -> set[str]:
    """Panels a legend labels, e.g. '(A) ... (B) ...' -> {A, B}.

    Only a run starting at A counts, so stray markers like '(i)' don't
    produce false panels.
    """
    found: set[str] = set()
    for a, b in re.findall(r"\(([A-Za-z])\s*[\u2013\u2014-]\s*([A-Za-z])\)", text):
        found |= _letters(a, b)
    found |= {x.upper() for x in re.findall(r"\(([A-Za-z])\)", text)}
    # "(B, C)" and "(A, C, E)" label several panels in one bracket.
    for group in re.findall(r"\(([A-Za-z](?:\s*,\s*[A-Za-z])+)\)", text):
        found |= {x.strip().upper() for x in group.split(",") if x.strip()}
    found |= {x for x in re.findall(r"(?:^|[.;:]\s+)([A-Z])[.)]\s", text)}
    panels, c = set(), "A"
    while c in found:
        panels.add(c)
        c = chr(ord(c) + 1)
    return panels


PANEL_START = re.compile(r"^\s*\(?[A-Za-z]\)")


def _legend_continuation(doc: Document, index: int) -> tuple[str, set[int]]:
    """Text of the paragraphs that continue a legend, and their indices.

    A legend is often split across paragraphs — in files converted from PDF,
    every printed line is its own paragraph — leaving panel (B) stranded below
    panel (A). Only lines that open with a panel marker are absorbed, so
    ordinary text following a legend is left alone.
    """
    extra, taken = [], set()
    for position, p in enumerate(doc.paragraphs[index + 1:]):
        if not p.text.strip() or p.is_heading or LEGEND_RE.match(p.text):
            break
        # The first continuation must open with a panel marker, which is what
        # proves this legend is wrapped rather than followed by ordinary text.
        # After that, the rest of the legend runs to the next blank line.
        if position == 0 and not PANEL_START.match(p.text):
            break
        extra.append(p.text)
        taken.add(p.index)
    return " ".join(extra), taken


def find_callouts_and_legends(doc: Document) -> tuple[list[Callout], list[Legend]]:
    callouts: list[Callout] = []
    legends: list[Legend] = []
    consumed: set[int] = set()
    for p in doc.paragraphs:
        if not p.text or p.is_heading or p.in_bibliography_field:
            continue
        if p.index in consumed:
            continue
        lm = LEGEND_RE.match(p.text)
        if lm and not _looks_like_reference(p.text):
            kind = "figure" if lm.group("kind").lower().startswith("fig") else "table"
            num = lm.group("num")
            key = ItemKey(kind, _group(lm.group("prefix"), num), int(re.sub(r"\D", "", num)))
            more, taken = _legend_continuation(doc, p.index)
            consumed |= taken
            full = f"{p.text} {more}".strip()
            legends.append(Legend(key, p.index, full, lm.group(0).strip(),
                                  _legend_panels(full) if kind == "figure" else set()))
            continue  # mentions inside legends aren't text callouts
        if p.section == REFERENCES:
            continue  # reference entries are not text callouts
        for m in CALLOUT_RE.finditer(p.text):
            kind = "figure" if m.group("kind").lower().startswith("fig") else "table"
            for label, panels in parse_spec(m.group("spec")).items():
                key = ItemKey(kind, _group(m.group("prefix"), label),
                              int(re.sub(r"\D", "", label)))
                callouts.append(Callout(
                    key, panels, p.index, m.start(), m.group(0).rstrip(" ,;"),
                    abbreviated=m.group("kind").lower().startswith("fig")
                    and not m.group("kind").lower().startswith("figure")))
    return callouts, legends


def check_figures(doc: Document) -> list[Issue]:
    callouts, legends = find_callouts_and_legends(doc)
    issues: list[Issue] = []

    legend_by_key: dict[ItemKey, Legend] = {}
    for lg in legends:
        if lg.key in legend_by_key:
            issues.append(Issue(CHECK, "warning",
                                f"{lg.key.label} has more than one legend/caption.",
                                lg.para_index, lg.anchor))
        else:
            legend_by_key[lg.key] = lg

    first_callout: dict[ItemKey, Callout] = {}
    for c in sorted(callouts, key=lambda c: (c.para_index, c.position)):
        first_callout.setdefault(c.key, c)

    groups = {(k.kind, k.group) for k in list(first_callout) + list(legend_by_key)}
    for kind, group in sorted(groups):
        in_group = lambda k: k.kind == kind and k.group == group  # noqa: E731
        cited = [k for k in first_callout if in_group(k)]
        legended = sorted((k for k in legend_by_key if in_group(k)), key=lambda k: k.number)
        noun = "legend" if kind == "figure" else "caption"
        sample = ItemKey(kind, group, 0).label.rsplit(" ", 1)[0]  # e.g. "Supplementary Figure"

        # 1. Cited but no legend (only if this group has legends at all).
        if legended:
            for k in cited:
                if k not in legend_by_key:
                    c = first_callout[k]
                    issues.append(Issue(CHECK, "error",
                                        f"{k.label} is cited in the text but has no {noun}.",
                                        c.para_index, c.text,
                                        f"Add a {noun} for {k.label} or correct the callout."))
        elif cited and group == "main":
            # Supplementary and Extended Data items are normally submitted as a
            # separate file, so saying they are missing would be noise.
            issues.append(Issue(CHECK, "info",
                                f"No {sample.lower()} {noun}s found, so {sample.lower()} "
                                f"callouts couldn't be matched to {noun}s "
                                f"(they may be in a separate file)."))

        # 2. Legend exists but never cited.
        for k in legended:
            if k not in first_callout:
                lg = legend_by_key[k]
                issues.append(Issue(CHECK, "error",
                                    f"{k.label} has a {noun} but is never cited in the text.",
                                    lg.para_index, lg.anchor,
                                    f"Cite {k.label} where it is first discussed, or remove it."))

        # 3. Gaps in legend numbering.
        nums = [k.number for k in legended]
        for a, b in zip(nums, nums[1:]):
            if b - a > 1:
                issues.append(Issue(CHECK, "warning",
                                    f"{sample} {noun}s jump from "
                                    f"{ItemKey(kind, group, a).label} to "
                                    f"{ItemKey(kind, group, b).label}.",
                                    legend_by_key[ItemKey(kind, group, b)].para_index))
        if nums and nums[0] != 1:
            issues.append(Issue(CHECK, "warning",
                                f"{sample} {noun}s start at "
                                f"{ItemKey(kind, group, nums[0]).label}, not 1.",
                                legend_by_key[legended[0]].para_index))

        # 4. First-citation order. (Items never cited are already reported above.)
        known = {k.number for k in cited}
        seen: set[int] = set()
        for k in sorted(cited, key=lambda k: (first_callout[k].para_index,
                                              first_callout[k].position)):
            missing = sorted(n for n in known if n < k.number and n not in seen)
            if missing:
                c = first_callout[k]
                earlier = ItemKey(kind, group, missing[0]).label
                issues.append(Issue(CHECK, "warning",
                                    f"{k.label} is first cited before {earlier}.",
                                    c.para_index, c.text,
                                    "Most journals require figures and tables to be "
                                    "first cited in numerical order."))
            seen.add(k.number)

    # 5. Panels cited that the legend doesn't have / legend panels never cited.
    cited_panels: dict[ItemKey, set[str]] = defaultdict(set)
    for c in callouts:
        cited_panels[c.key] |= c.panels
        lg = legend_by_key.get(c.key)
        if lg and lg.panels:
            for panel in sorted(c.panels - lg.panels):
                issues.append(Issue(CHECK, "warning",
                                    f"{c.key.label}{panel} is cited, but the legend only "
                                    f"describes panels {_fmt_panels(lg.panels)}.",
                                    c.para_index, c.text))
    for k, lg in legend_by_key.items():
        if lg.panels and cited_panels.get(k):
            unused = lg.panels - cited_panels[k]
            if unused:
                word = "Panels" if len(unused) > 1 else "Panel"
                verb = "are" if len(unused) > 1 else "is"
                issues.append(Issue(CHECK, "info",
                                    f"{word} {_fmt_panels(unused)} of {k.label} {verb} "
                                    f"described in the legend but never cited individually.",
                                    lg.para_index, lg.anchor))

    # 6. Mixed "Fig." and "Figure" in the text.
    fig_callouts = [c for c in callouts if c.key.kind == "figure"]
    abbrev = sum(c.abbreviated for c in fig_callouts)
    if 0 < abbrev < len(fig_callouts):
        issues.append(Issue(CHECK, "info",
                            f'Figure callouts mix "Fig." ({abbrev}) and "Figure" '
                            f"({len(fig_callouts) - abbrev}). Check your journal's style."))

    return _dedupe(issues)


def _fmt_panels(panels: set[str]) -> str:
    p = sorted(panels)
    return ", ".join(p[:-1]) + f" and {p[-1]}" if len(p) > 1 else p[0]


def _dedupe(issues: list[Issue]) -> list[Issue]:
    seen, out = set(), []
    for i in issues:
        key = (i.severity, i.message, i.para_index)
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out
