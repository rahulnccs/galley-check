"""Consistency checks: things a manuscript should do the same way throughout.

None of these is wrong on its own: journals differ on whether to write "37 °C"
or "37°C", and British and American spelling are both fine. What reviewers and
copy editors notice is a manuscript that does both. So every check here stays
quiet unless the manuscript itself uses two forms, and then points at the
less common one.

  * a unit written with a space after the number in some places and without
    in others ("5 mg" and "5mg")
  * the same unit capitalized two ways ("ml" and "mL")
  * two different micro signs, or "u" standing in for one ("uL")
  * British and American spelling mixed ("colour" and "color")
  * a sentence that starts with a numeral ("15 mice were...")
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from ...model.document import Document, Issue, Paragraph

CHECK = "consistency"

# Units that follow a number. Case matters ("mL" is not "ML"), and units that
# collide with ordinary text ("s", "m", "M", "L") are left out.
UNITS = [
    "kg", "mg", "µg", "μg", "ng", "pg", "g",
    "mL", "ml", "µL", "µl", "μL", "μl", "nL", "nl",
    "mM", "µM", "μM", "nM", "pM",
    "km", "cm", "mm", "µm", "μm", "nm",
    "kDa", "kb", "bp", "rpm", "min", "h", "°C", "Hz", "kHz", "mV",
]
_UNIT_ALT = "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
# The number must stand on its own ("H2O" and "CD4" are not quantities), and
# the unit must end the word ("5 min" but not "5 minutes" or "5 gels").
QUANTITY = re.compile(
    rf"(?<![\w.,−-])(\d+(?:[.,]\d+)?)(\s?)({_UNIT_ALT})(?![\wµμ])")
U_FOR_MICRO = re.compile(r"(?<![\w.])\d+(?:\.\d+)?\s?(u[LlMgm])(?![\w])")
MICRO_SIGNS = {"µ": "µ (micro sign, U+00B5)",
               "μ": "μ (Greek mu, U+03BC)"}


def _unit_key(unit: str) -> str:
    """The unit with litre capitalization and micro-sign differences removed.

    Only the litre varies by case ("ml" and "mL"); elsewhere case is meaning
    ("mm" is a length, "mM" a concentration).
    """
    unit = unit.replace("μ", "µ")
    return unit[:-1] + "l" if unit.endswith("L") else unit


# "Fig. 2g" and "Figure 3h" are panels, not grams and hours.
PANEL_CONTEXT = re.compile(
    r"\b(figs?|figures?|tables?|panels?)\.?\s*"
    r"(?:S?\d+[a-z]?(?:\s*[,\u2013-]\s*|\s+and\s+))*$", re.I)


# British and American spellings. Each entry is (family label, British regex,
# American regex); both are whole words. Kept to words where the two forms
# never mean different things: "program", "meter" and "licence" are left out.
_IZE_STEMS = ["normali", "randomi", "characteri", "organi", "recogni",
              "utili", "minimi", "maximi", "optimi", "standardi", "visuali",
              "stabili", "hybridi", "immuni", "synthesi", "summari",
              "categori", "emphasi", "homogeni", "solubili", "neutrali",
              "mobili", "internali", "coloni", "sterili"]
_IZE_ENDINGS = r"(?:e|ed|es|ing|ation|ations|er|ers)"
_OUR_WORDS = ["colo", "behavio", "tumo", "favo", "labo", "flavo", "odo",
              "neighbo", "harbo", "vigo", "rumo"]
_OUR_ENDINGS = r"(?:|s|ed|ing|al|ally|ful|less|ation|able)"


def _spelling_pairs() -> list[tuple[str, re.Pattern, re.Pattern]]:
    pairs: list[tuple[str, str, str]] = []
    for stem in _IZE_STEMS:
        pairs.append((stem + "ise / " + stem + "ize",
                      rf"{stem}s{_IZE_ENDINGS}", rf"{stem}z{_IZE_ENDINGS}"))
    # "analyses" is also the American plural of "analysis", so only the verb
    # forms that differ are counted.
    pairs.append(("analyse / analyze", r"analys(?:e|ed|ing)", r"analyz(?:e|ed|es|ing)"))
    pairs.append(("catalyse / catalyze", r"catalys(?:e|ed|ing)", r"catalyz(?:e|ed|es|ing)"))
    pairs.append(("hydrolyse / hydrolyze", r"hydrolys(?:e|ed|ing)", r"hydrolyz(?:e|ed|es|ing)"))
    for stem in _OUR_WORDS:
        pairs.append((stem + "ur / " + stem + "r",
                      rf"{stem}ur{_OUR_ENDINGS}", rf"{stem}r{_OUR_ENDINGS}"))
    pairs += [
        ("centre / center", r"centre(?:s|d)?", r"center(?:s|ed)?"),
        ("fibre / fiber", r"fibres?", r"fibers?"),
        ("litre / liter", r"(?:milli|micro|nano)?litres?", r"(?:milli|micro|nano)?liters?"),
        ("labelled / labeled", r"labell(?:ed|ing)", r"label(?:ed|ing)"),
        ("modelled / modeled", r"modell(?:ed|ing)", r"model(?:ed|ing)"),
        ("signalling / signaling", r"signall(?:ed|ing)", r"signal(?:ed|ing)"),
        ("travelled / traveled", r"travell(?:ed|ing)", r"travel(?:ed|ing)"),
        ("cancelled / canceled", r"cancell(?:ed|ing)", r"cancel(?:ed|ing)"),
        ("grey / gray", r"grey", r"gray"),
        ("ageing / aging", r"ageing", r"aging"),
        ("sulphur / sulfur", r"sulph(?:ur|ate|ates|ide|ides|onate|onic)",
         r"sulf(?:ur|ate|ates|ide|ides|onate|onic)"),
        ("aluminium / aluminum", r"aluminium", r"aluminum"),
        ("haemoglobin / hemoglobin", r"haemoglobin", r"hemoglobin"),
        ("haematopoietic / hematopoietic", r"haemato\w+", r"hemato\w+"),
        ("haemorrhage / hemorrhage", r"haemorrhag\w*", r"hemorrhag\w*"),
        ("anaemia / anemia", r"anaemi(?:a|c)", r"anemi(?:a|c)"),
        ("leukaemia / leukemia", r"leukaemi(?:a|as|c)", r"leukemi(?:a|as|c)"),
        ("oedema / edema", r"oedema", r"edema"),
        ("oestrogen / estrogen", r"oestrogens?", r"estrogens?"),
        ("paediatric / pediatric", r"paediatrics?", r"pediatrics?"),
        ("faeces / feces", r"faec(?:es|al)", r"fec(?:es|al)"),
        ("foetal / fetal", r"foet(?:al|us|uses)", r"fet(?:al|us|uses)"),
        ("orthopaedic / orthopedic", r"orthopaedics?", r"orthopedics?"),
        ("diarrhoea / diarrhea", r"diarrhoea", r"diarrhea"),
        ("tumour / tumor", r"tumours?", r"tumors?"),
    ]
    seen, out = set(), []
    for label, brit, amer in pairs:
        if label in seen:
            continue
        seen.add(label)
        out.append((label, re.compile(rf"\b{brit}\b", re.I),
                    re.compile(rf"\b{amer}\b", re.I)))
    return out


SPELLING_PAIRS = _spelling_pairs()

# A sentence that opens with a numeral. The full stop before it must end a
# real word, not an abbreviation ("Fig. 3", "et al. 2020", "e.g. 5").
SENTENCE_START_NUMBER = re.compile(
    r"(?:^|(?<=[.!?])\s+)(?P<num>\d[\d,.]*)\s+(?P<next>[a-z][a-z-]+)")
ABBREVIATIONS = {"al", "fig", "figs", "ref", "refs", "no", "nos", "eq", "eqs",
                 "approx", "vs", "ca", "cf", "etc", "vol", "p", "pp", "ext",
                 "suppl", "supp", "tab", "sec", "ch", "n", "e", "i", "g"}

# Sections where these checks apply. The reference list keeps each cited
# work's own spelling and formatting, so it is left alone.
SKIPPED_SECTIONS = {"references", "front_matter"}


def _body(doc: Document) -> list[Paragraph]:
    paras = [p for p in doc.paragraphs
             if p.text and not doc.is_reference_paragraph(p)
             and p.section not in SKIPPED_SECTIONS]
    # A manuscript with no recognized headings is all "front_matter"; check it
    # anyway rather than silently skipping the whole paper.
    if not paras:
        paras = [p for p in doc.paragraphs
                 if p.text and not doc.is_reference_paragraph(p)]
    return paras


@dataclass
class Hit:
    para: int
    text: str


def _times(n: int) -> str:
    return "once" if n == 1 else f"{n} times"


def _unit_issues(paras: list[Paragraph]) -> list[Issue]:
    spaced: dict[str, list[Hit]] = defaultdict(list)
    tight: dict[str, list[Hit]] = defaultdict(list)
    spellings: dict[str, dict[str, list[Hit]]] = defaultdict(lambda: defaultdict(list))
    for p in paras:
        for m in QUANTITY.finditer(p.text):
            unit = m.group(3)
            if unit in ("g", "h") and PANEL_CONTEXT.search(p.text[:m.start()]):
                continue
            key = _unit_key(unit)
            hit = Hit(p.index, m.group(0))
            (spaced if m.group(2) else tight)[key].append(hit)
            # Compare capitalization only; the micro sign is a separate check.
            spellings[key][unit.replace("μ", "µ")].append(hit)

    issues: list[Issue] = []
    for key in sorted(set(spaced) & set(tight)):
        s, t = spaced[key], tight[key]
        unit = s[0].text.split()[-1]
        if len(s) >= len(t):
            odd, n_odd, n_usual, how = t[0], len(t), len(s), "with a space"
        else:
            odd, n_odd, n_usual, how = s[0], len(s), len(t), "without a space"
        issues.append(Issue(
            CHECK, "warning",
            f'"{unit}" is written {how} after the number {_times(n_usual)}, '
            f'but not {_times(n_odd)}, e.g. "{odd.text}".',
            odd.para, odd.text,
            f"Write every {unit} quantity the same way; check the journal's "
            f"style for which."))

    for key, forms in sorted(spellings.items()):
        if len(forms) < 2:
            continue
        ranked = sorted(forms.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        usual = ranked[0][0]
        for form, hits in ranked[1:]:
            issues.append(Issue(
                CHECK, "warning",
                f'The unit is written "{form}" {_times(len(hits))} but '
                f'"{usual}" {_times(len(forms[usual]))}.',
                hits[0].para, hits[0].text,
                f'Use "{usual}" throughout (SI writes litre as "L": "mL", "µL").'
                if usual.lower().endswith("l") else f'Use "{usual}" throughout.'))
    return issues


def _micro_issues(paras: list[Paragraph]) -> list[Issue]:
    issues: list[Issue] = []
    seen: dict[str, list[Hit]] = defaultdict(list)
    u_hits: list[Hit] = []
    for p in paras:
        for m in QUANTITY.finditer(p.text):
            for sign in MICRO_SIGNS:
                if sign in m.group(3):
                    seen[sign].append(Hit(p.index, m.group(0)))
        u_hits += [Hit(p.index, m.group(0)) for m in U_FOR_MICRO.finditer(p.text)]
    if len(seen) == 2:
        (a, ha), (b, hb) = sorted(seen.items(), key=lambda kv: -len(kv[1]))
        issues.append(Issue(
            CHECK, "info",
            f"Two different micro signs are used: {MICRO_SIGNS[a]} "
            f"{_times(len(ha))} and {MICRO_SIGNS[b]} {_times(len(hb))}. They "
            f"look alike but differ for search, and in some fonts.",
            hb[0].para, hb[0].text,
            "Find and replace one with the other so the manuscript uses one."))
    if u_hits:
        h = u_hits[0]
        issues.append(Issue(
            CHECK, "warning",
            f'"u" is used in place of the micro sign {_times(len(u_hits))}, '
            f'e.g. "{h.text}".',
            h.para, h.text, 'Use "µ": "µL", "µM", "µg".'))
    return issues


def _proper_noun(text: str, at: int) -> bool:
    """A capitalized word mid-sentence is a name ("Cancer Center", "Gray et
    al."), which keeps its own spelling."""
    if not text[at].isupper():
        return False
    before = text[:at].rstrip()
    return bool(before) and before[-1] not in ".!?:"


def _spelling_issues(paras: list[Paragraph]) -> list[Issue]:
    british: dict[str, list[Hit]] = defaultdict(list)
    american: dict[str, list[Hit]] = defaultdict(list)
    for p in paras:
        for label, brit, amer in SPELLING_PAIRS:
            for rx, found in ((brit, british), (amer, american)):
                found[label] += [Hit(p.index, m.group(0)) for m in rx.finditer(p.text)
                                 if not _proper_noun(p.text, m.start())]
    n_brit = sum(len(v) for v in british.values())
    n_amer = sum(len(v) for v in american.values())
    if not n_brit or not n_amer:
        return []
    if n_brit >= n_amer:
        usual, odd_name, odd = "British", "American", american
    else:
        usual, odd_name, odd = "American", "British", british
    issues = []
    for label, hits in odd.items():
        if not hits:
            continue
        brit_form, amer_form = (s.strip() for s in label.split("/"))
        wanted = brit_form if usual == "British" else amer_form
        found = Counter(h.text.lower() for h in hits).most_common(1)[0][0]
        issues.append(Issue(
            CHECK, "warning",
            f'"{found}" is {odd_name} spelling ({_times(len(hits))}), but the '
            f"manuscript mostly uses {usual} spelling.",
            hits[0].para, hits[0].text,
            f'Use the {usual} form ("{wanted}" and related words), or switch '
            f"the whole manuscript to the journal's preferred spelling."))
    return issues


def _sentence_start_issues(paras: list[Paragraph]) -> list[Issue]:
    issues = []
    for p in paras:
        if p.is_heading or p.in_table or p.is_list_item:
            continue
        for m in SENTENCE_START_NUMBER.finditer(p.text):
            start = m.start("num")
            if start == 0:
                # Paragraph openers like "1 Introduction" or "2 mL of buffer"
                # in a protocol list; only flag full sentences.
                if not re.match(r"\d[\d,.]*\s+[a-z]+\s+\w+\s+\w+", p.text):
                    continue
                if p.section == "figure_legends":
                    continue
            else:
                before = p.text[:start].rstrip()
                word = re.search(r"([A-Za-z]+)\.$", before)
                if not word or word.group(1).lower() in ABBREVIATIONS \
                        or len(word.group(1)) < 2 or before.endswith(".."):
                    continue
            # Years read naturally at the start of a sentence in history
            # and policy writing; leave them alone.
            if re.fullmatch(r"(19|20)\d\d", m.group("num")):
                continue
            phrase = f"{m.group('num')} {m.group('next')}"
            issues.append(Issue(
                CHECK, "info",
                f'A sentence starts with a numeral: "{phrase}".',
                p.index, phrase,
                "Spell the number out, or reword so the sentence doesn't "
                "start with it."))
    return issues


def check_consistency(doc: Document) -> list[Issue]:
    paras = _body(doc)
    return (_unit_issues(paras) + _micro_issues(paras)
            + _spelling_issues(paras) + _sentence_start_issues(paras))
