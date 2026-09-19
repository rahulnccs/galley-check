# Galley

Offline checks for academic manuscript drafts — figures, tables, citations and
references. Your paper never leaves your computer.

A galley proof is the draft an author checks before publication. Galley does the
mechanical part of that check for you.

[![Tests](https://github.com/rahulnccs/galley-check/actions/workflows/tests.yml/badge.svg)](https://github.com/rahulnccs/galley-check/actions/workflows/tests.yml)
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

Choose **Journal → Enter journal requirements…** and fill in what the journal
asks for: abstract, main text and total word limits, title length, maximum
references and display items, required sections, the citation style, how many
authors an entry lists before "et al.", and whether every reference needs a DOI.
Anything left blank isn't checked.

The profile is saved under your user folder and appears in the dropdown next
time, so you fill it in once per journal. Galley remembers the last journal you
used, and profiles you made can be edited or removed from the same row. They are
small JSON files, so one can also be shared with a labmate. Profiles are small JSON files, so you
can also share one with your lab, or pass it on the command line with
`--profile myjournal.json`.

Every profile records the date its rules were checked and a link to the
journal's own guidelines, and Galley reports both. A profile with no date, or
one older than a year, produces a warning rather than quietly implying its
numbers are current.

Galley ships a template rather than real journals, because a stale limit is
worse than none, and there is no way for the app to know when a journal changed
its rules. Profiles for journals you submit to are welcome as pull requests.

**Comparing two versions**

Choose **Document → Compare with an earlier version…**, or run
`galley revised.docx --compare-with old.docx`. Galley works out which sentences
are new or edited and saves a copy of the revised file with those sentences
highlighted — useful when sending a revision back to reviewers. Comparison is at
sentence level, so reordering a paragraph doesn't light up the whole page, and
the original file is never modified. Changes to numbers alone — a p-value or an
n — are treated as unchanged text.

**Species names**

- Italicized in some places and not others
- Genus abbreviated before it has been spelled out in full
- "sp." and "spp." used inconsistently
- Genus written in lower case

A phrase is only treated as a species when the manuscript gives evidence it is
one — italics somewhere, an abbreviated form, or a "sp." usage — so ordinary
prose like "Alpha diversity" is never mistaken for a binomial.

**Citations and references**

- Every citation points at a reference that exists
- Every reference in the list is cited somewhere in the text
- Numbered references are first cited in ascending order
- No gaps or repeats in the reference numbering
- Duplicate entries in the reference list
- Entries missing a year, an author list, a journal, or a DOI
- Malformed DOIs, and missing ones when the rest of the list has them

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

Ready-to-run apps are on the [releases page](https://github.com/rahulnccs/galley-check/releases):
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

**Desktop app:** run `galley-app`, or double-click `Galley.pyw`.
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

## Feedback

Galley is early, and the most useful thing you can send is a case where it's
**wrong**: something it flagged that was fine, or a real problem it stayed quiet
about. Two ways to reach me:

- [Tell me how you're using Galley](https://docs.google.com/forms/d/e/1FAIpQLSf-IEokqhT8mjond7SFDCp90sDzUDCupJPK8p26aVls46QYjg/viewform) — a short form.
  Leave your email if you'd like to hear when new checks land.
- [Open an issue](https://github.com/rahulnccs/galley-check/issues) for bugs.

To be notified of new versions, click **Watch** at the top of this page, choose
**Custom**, and tick **Releases**. GitHub emails you when a release is published;
nothing is collected by Galley itself.

## Citing Galley

If Galley saved you time on a manuscript, please cite it. Citations are how a
free tool like this earns a place on a CV, and they help other people find it.

> Bodkhe, R. (2026). *Galley: offline manuscript checks for figures, tables,
> citations and references* (Version 1.0.0) [Computer software]. Zenodo.
> https://doi.org/10.5281/zenodo.22733230

DOI: [10.5281/zenodo.22733230](https://doi.org/10.5281/zenodo.22733230)

A BibTeX entry and other formats are available from the
[Zenodo record](https://doi.org/10.5281/zenodo.22733230), and GitHub's
**Cite this repository** button (top right of this page) generates a citation
in several styles.

In a methods section, something like this is enough:

> Figure callouts, citations, references and abbreviations were checked with
> Galley v1.0.0 (Bodkhe, 2026).

## License

MIT — see [LICENSE](LICENSE).
