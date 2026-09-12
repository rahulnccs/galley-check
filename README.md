# Galley

Offline checks for academic manuscript drafts — figures, tables, citations and
references. Your paper never leaves your computer.

A galley proof is the draft an author checks before publication. Galley does the
mechanical part of that check for you.

[![Tests](https://github.com/USERNAME/galley-check/actions/workflows/tests.yml/badge.svg)](https://github.com/USERNAME/galley-check/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Status:** early development (v0.2). Checks figures, tables, citations, and
references in `.docx` files. PDF support is experimental and not yet reliable.

## What it checks so far

**Figures and tables**

- Every figure/table cited in the text has a legend or caption, and vice versa
- Figures and tables are first cited in numerical order
- Legend numbering has no gaps
- Cited panels (e.g. "Fig. 3D") exist in the legend
- Supplementary and Extended Data figures are handled separately
- Mixed "Fig." / "Figure" usage

**Abbreviations**

- Used before it is defined
- Defined more than once in the same part of the paper
- Spelled out differently in different places
- Defined but never used again
- Used repeatedly but never defined

The abstract, main text and methods are treated separately, since journals
expect an abbreviation to be defined once in each.

**Submission readiness**

- Word counts for the title, abstract, main text and methods
- Reference, figure and table counts
- Anything over a journal's limit, and any required section that's missing

Limits come from a journal profile — a small JSON file you edit. Copy
`galley/profiles/example.json`, change the numbers to match your target journal,
and pass it with `--profile myjournal.json` or the **Use journal limits…** button.
Galley ships no real journal profiles, because limits change often and a stale
limit is worse than none.

**Citations and references**

- Every citation points at a reference that exists
- Every reference in the list is cited somewhere in the text
- Numbered references are first cited in ascending order
- No gaps or repeats in the reference numbering
- Duplicate entries in the reference list
- Entries missing a year, and malformed DOIs

Supported citation styles: numbered (`[12]`, `[3,5-7]`, superscript, Word
auto-numbered lists), author-year (`(Smith et al., 2020)`, `[Smith 2020]`,
`Smith (2020)`), LaTeX-style keys (`[Smi20]`, `[ABC+21]`), and footnote or
endnote citations.

When the citation style isn't recognized, the tool says so and skips the
citation comparison instead of guessing — a wrong guess would produce a page
of false errors, and everything else is still checked.

The parser reads text as it appears with tracked changes accepted, and detects
citations inserted by Zotero, Mendeley, and EndNote.

## Download

Ready-to-run apps are on the [releases page](https://github.com/USERNAME/galley-check/releases):
`Galley-macOS.dmg` for Mac and `Galley-Setup.exe` for Windows.
Nothing else needs installing.

The apps are not code-signed yet, so the first launch shows a warning. On Mac,
right-click the app and choose **Open**, then **Open** again. On Windows, click
**More info** then **Run anyway**. This happens once.

## Install from source

```bash
pip install -e ".[gui]"
```

The package installs as `galley-check` (the name `galley` was already taken on
PyPI) and provides two commands: `galley` for the command line and `galley-app`
for the desktop window.

**Desktop app:** run `galley-check`, or double-click `Galley.pyw`.
Drop a .docx onto the window, choose it with the button, or paste its path.
Click any issue to see the exact sentence with the problem highlighted. After fixing
the file in Word, save it and click **Re-check**.

**Comments in your document.** Click **Save with comments…** and Galley writes a
copy of your manuscript with a Word comment in the margin at each problem, so you
can fix them in Word without cross-referencing a report. Your original file is
never modified.

**Command line:**

```bash
galley paper.docx                       # text report
galley paper.docx --json                # machine-readable
galley paper.docx --comments            # also write paper_commented.docx
galley paper.docx --comments out.docx --comment-level warning
galley paper.docx --profile myjournal.json
```

Exit code is 1 if any errors are found (useful for scripts).

## Development

```bash
python tests/fixtures/make_sample.py   # rebuild the sample manuscript
python tests/fixtures/make_corpus.py   # rebuild the style corpus
pytest
```

`tests/fixtures/make_corpus.py` builds one small fictional manuscript per
citation style, each declaring the problems planted in it. `tests/test_corpus.py`
requires the tool to find exactly those and raise nothing else, which is what
keeps the checks honest on papers the authors have never seen.

## Releasing

Builds run automatically. Pushing a version tag publishes the Mac and Windows
apps to a GitHub release:

```bash
git tag v0.2.0
git push origin v0.2.0
```

## Roadmap

1. ~~docx parser + figure/table checks~~
2. ~~Reference checks~~
3. ~~Abbreviations~~; statistics formatting and placeholders still to come
4. ~~Comments inserted into a copy of the .docx~~
5. ~~Desktop app~~ (done early); one-click installers for Windows and Mac
6. Optional online checks (DOI verification, retractions)
7. Code signing, so the first-launch warning goes away

## License

MIT — see [LICENSE](LICENSE).
