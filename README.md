# Galley

A desktop app for life-science researchers, in four parts:

- **Manuscript checks**: offline checks for manuscript drafts (figures, tables,
  citations, references, abbreviations, species names, consistency and ethics
  statements) before reviewers see them.
- **Fellowships**: which postdoc fellowships, PhD fellowships and travel
  grants you can apply for and why, a preparation plan and reminders for each
  application, and a check of your documents against the funder's format.
- **Projects**: a README, a sample tracker that opens each sample's
  sequencing or other data folders, and a lab notebook, per project.
- **My Lab**: the lab's orders from request to the shelf they end up on, an
  inventory of where things are, and spending by account and vendor.

Your manuscript, documents and profile never leave your computer.

A galley proof is the draft an author checks before publication. Galley does the
mechanical part of that check for you.

[![Tests](https://github.com/rahulnccs/galley-check/actions/workflows/tests.yml/badge.svg)](https://github.com/rahulnccs/galley-check/actions/workflows/tests.yml)

**Status:** v1.5. Manuscript checks work on `.docx` files; PDF support is
experimental and not yet reliable. The Fellowships section is new in v1.5 and
its fellowship list is still being built (see [Fellowships](#fellowships)).

## Manuscript checks

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

Choose the journal next to **Journal:** on the first screen. The list is
searchable by journal or publisher and covers about 50 life-science journals
(the Nature and Cell Press journals, Science, PNAS, eLife, PLOS, Frontiers,
BMC, ASM, EMBO, Oxford journals and more). For each, Galley checks the word
limits (title, abstract, main text, whole manuscript), the title length in
characters, the number of keywords, references, figures and tables, the
headings of a structured abstract, required sections and statements (data
availability, competing interests, STAR Methods...), the citation style,
authors before "et al." and DOIs.

Problems are pointed out in the manuscript itself: for a word limit, the
sentence where the limit is reached is highlighted, so you can see what
would have to go; an over-long title, a keywords line with too many entries,
or the first reference or figure past a limit is marked where it is. Click a
finding to jump to it.

Every journal records the date its requirements were last checked against
the journal's author guidelines, and links to them. The list is being built:
entries not yet checked say so, their limits are marked "not yet confirmed",
and a missing section is a warning rather than an error. **Check for
Updates** in the journal list downloads the latest version.

**Another journal.** Choose **Another Journal…** to enter the requirements of
a journal that isn't listed, from its author guidelines. If a listed journal's
requirements are wrong, choose **Correct…** to save your own copy, which then
takes the listed one's place for you. Your journals are small JSON files in
your user folder, so you can share one with your lab, or pass it on the
command line with `--profile myjournal.json`. To suggest a journal for the
list, fill in
[`templates/journal-database-template.xlsx`](templates/journal-database-template.xlsx)
or open an issue.

**Comparing two versions**

Choose **Document → Compare with an earlier version…**, or run
`galley revised.docx --compare-with old.docx`. Galley works out which sentences
are new or edited and saves a copy of the revised file with those sentences
highlighted — useful when sending a revision back to reviewers. Comparison is at
sentence level, so reordering a paragraph doesn't light up the whole page, and
the original file is never modified. Changes to numbers alone — a p-value or an
n — are treated as unchanged text.

Galley also copes with manuscripts where every printed line is a separate
paragraph — files converted from PDF, and some journal templates. In those,
citations, reference entries and figure legends are split across paragraphs,
and are rejoined before checking.

**Species names**

- Italicized in some places and not others
- Genus abbreviated before it has been spelled out in full
- "sp." and "spp." used inconsistently
- Genus written in lower case

A phrase is only treated as a species when the manuscript gives evidence it is
one — italics somewhere, an abbreviated form, or a "sp." usage — so ordinary
prose like "Alpha diversity" is never mistaken for a binomial.

**Consistency**

Each of these only fires when the manuscript does the same thing two ways —
"37 °C" and "37°C" are both acceptable styles, but not in the same paper.

- A unit written with a space after the number in some places and not others
  ("5 mg" and "5mg")
- The same unit capitalized two ways ("ml" and "mL")
- Two different micro signs (µ and μ look alike but aren't), or "u" used in place
  of one ("uL")
- British and American spelling mixed ("colour" and "color"); names such as
  "Cancer Center" and the reference list are left alone
- A sentence that starts with a numeral ("15 mice were...")

**Ethics and statements**

- Data availability, competing interests, funding and author contributions
  statements, which almost every journal asks for
- Ethics approval and informed consent, when the methods or results describe
  research with people ("patients", "participants")
- Animal ethics approval, when they describe work with animals ("mice", "rats");
  antibodies like "mouse anti-GFP" don't count
- A code availability statement, when the manuscript mentions custom code or
  scripts

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

## Fellowships

Switch to **Fellowships** at the top of the window. It covers three kinds of
life-science funding: postdoc fellowships, PhD fellowships and travel grants.

The tabs run in the order you use them: **Profile**, **Matches**,
**Applications** and **Calendar**.

**Matches.** Fill in your profile (career stage, PhD date, career breaks,
nationality, where you live and would like to go, places you've lived, field)
and Galley sorts the funding into what you're eligible for, what's worth
checking, and what you can't apply for, with the reason for each rule: career
stage, years since PhD, nationality, residence, host country, mobility rules,
clinical track and society membership. Filter the list by Postdoc, PhD or
Travel. When your profile leaves something out, Galley says "worth checking"
rather than guessing. Rules written in words that no profile can answer (an
age limit, "a lead-author paper") are listed under **Also confirm** on each
fellowship, and the list shows how many there are, so they are never
silently assumed. Every entry links to the funder's own page.

**Applications.** Add a fellowship to **My Applications** to get a preparation
plan worked back from its deadline (contact host labs, start drafting, get
feedback, final check), track its stage from preparing to awarded, and keep
notes. Whenever you open Galley, a banner lists steps that are overdue or
coming up, and deadlines that have moved.

**Calendar.** A month calendar with your applications' deadlines and
interviews in blue, and, if you choose *Everything I can apply for*, the
deadlines of fellowships you're eligible for in green. Click a day or move
between months to list what's due. **Add to My Calendar** saves the upcoming
deadlines as an .ics file for Apple Calendar, Google Calendar or Outlook,
each with a reminder a week before.

**Check Application.** Before you submit, attach your Word documents to the
application and choose **Check Application**. Galley checks each one against
the fellowship's format (page and word limits, required sections, smallest
text size and margins) and lists what passes and what to fix. If the funder
wants PDFs, Galley reminds you to export them at the end.

**Your own entries.** Funding Galley doesn't list, like an institute's
internal scheme, can be added by hand.

**The fellowship list.** It is maintained in
[`galley/fellowships/data/`](galley/fellowships/data/README.md), one small
file per scheme, each with the date it was last checked against the funder's
page; entries older than a year are flagged. The list is still being built: Galley
ships 166 life-science entries (88 postdoc fellowships, 12 PhD fellowships and
66 travel grants). 86 of them, including the main Indian schemes (ANRF, DBT,
DST, ICMR, CSIR, UGC, India Alliance), have been checked against the funder's
page. The other 80 come from public lists and haven't been checked yet, so
Galley shows them as "worth checking" rather than "eligible" until they are,
and says so on each one. **Check for Updates**, at the top of Matches,
downloads the latest list from this repository, so new and corrected entries
reach the app without a new release; only the list is downloaded, nothing
about you is sent. To suggest a scheme, fill in
[`templates/fellowship-database-template.xlsx`](templates/fellowship-database-template.xlsx)
or open an issue. Each entry in the app has a **Report Outdated Information**
link for corrections.

Your profile and applications are saved on your computer only.

## Projects

Switch to **Projects** at the top of the window to keep each research project
in one place. Galley never copies or moves your data; it records where it is.

**README.** A few lines about the project: the question, the system, the
design, where things stand, and the analyses it uses (RNA-seq, DNA-seq,
metabolomics, or your own).

**Samples.** A searchable list of the project's samples. Click one to open
its page of coloured boxes, one for each thing worth recording (RNA
extraction, sequencing, QC, results). Each box has a title, notes and a
linked data folder that opens in Finder or Explorer; choose its colour, and
press **+ Add a Box** for more. Everything saves as you type. A folder that
has been moved or deleted is flagged instead of failing silently. The page
also lists the sample's analyses and notebook entries. Import a sample sheet
(CSV with a `sample_id` column and columns such as `RNA-seq data` and
`RNA-seq analysis` holding folder paths) rather than typing samples in, and
export it again.

**Notebook.** Dated lab-notebook entries, searchable, each linked to the
samples it concerns; a sample's page shows the entries that mention it.

Projects are saved on your computer only.

## My Lab

Switch to **My Lab** to track the lab's orders.

**Orders.** A spreadsheet with the usual order-sheet columns (Status, Date
Requested, Date Approved, Approved By, Date Ordered, Account, Item Name,
Requested By, Vendor, Catalog #, Qty, Unit Price, Total Price, Received By,
Date Received, Location, SubLocation, Unit Size, URL, Notes). The header
stays in place while the rows scroll; double-click a column name to rename
it for the whole lab. **+ New Row** adds a row at the top to type into.
Double-click a cell to edit it: Status offers a menu, dates a calendar, and
names suggest what the lab has used before. A new tracker starts with a few
example reagent rows, removed with one click. Each order goes Requested →
Approved → Ordered → Received (or Back-ordered or Cancelled), coloured as on
most lab order sheets: red, indigo, amber, purple, green; the Requested,
Approved and Ordered tiles filter the sheet. Click a row number to move an
order on. **Mark as Received** records who took the delivery and asks where
it was put. **Order Again** repeats an earlier order in one click, and
**Copy Order Details** puts the item, vendor, catalogue number, quantity,
price and link on the clipboard for an email or purchasing form. Typing an
item the lab has ordered before fills in its vendor, catalogue number and
last price. A banner flags requests not ordered after a week and orders not
received after two weeks (both adjustable) and shows just those orders; the
count shows on the My Lab tab.

**Inventory.** Everything received, grouped by where it was put (bench,
freezer, cold room), with a "Where is it?" search.

**Spending.** What was ordered this month, this year and over the last 12
months, by account (grant or cost centre), vendor and month, plus what is on
order and what is waiting to be ordered.

**Bring your sheet.** Import the lab's existing order spreadsheet (Excel or
CSV) as it is. Galley finds the header row and recognises the usual columns
(Status, Date Requested, Item Name, Vendor, Catalog #, Qty, Unit Price, Total
Price, Received By, Location and so on), and skips orders it already has.
Export to CSV at any time.

**Share it with the lab.** On the Lab tab, choose a folder on a shared drive
(OneDrive, Google Drive, Dropbox or a network drive) and have everyone choose
the same one. Each order is its own small file, so people working at the
same time don't overwrite each other; press **Refresh** to see their changes.
Your name and which folder you use stay on your computer.

## Download

Ready-to-run apps are on the [releases page](https://github.com/rahulnccs/galley/releases):
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

**Desktop app:** run `galley-app`, or double-click `Galley.pyw`. The window
shows the manuscript's text beside the findings: clicking a finding scrolls the
text to that spot, where the problem is highlighted in place. The coloured tiles
along the top filter by severity.
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

Builds run on every push. Publishing a release with a version tag (for
example `v1.6.0`) builds the Mac and Windows apps and attaches them to a
release of the same name in the public repository,
[rahulnccs/galley](https://github.com/rahulnccs/galley/releases). Whenever the
fellowship list changes on `main`, the *Publish to the public repository*
workflow copies it there too, together with [`public/README.md`](public/README.md).

Both need a token, set up once:

1. Create the public repository `rahulnccs/galley`, ticking **Add a README
   file** so it isn't empty.
2. On GitHub, open **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**. Give it access to
   **Only select repositories: rahulnccs/galley**, with **Contents: Read and
   write** permission.
3. In this repository, open **Settings → Secrets and variables → Actions → New
   repository secret**, name it `PUBLIC_REPO_TOKEN` and paste the token.

Until the secret exists, the publishing steps are skipped with a note rather
than failing.

## Roadmap

1. ~~docx parser + figure/table checks~~
2. ~~Reference checks~~
3. ~~Abbreviations~~; statistics formatting and placeholders still to come
4. ~~Comments inserted into a copy of the .docx~~
5. ~~Desktop app~~ (done early); one-click installers for Windows and Mac
6. Optional online checks (DOI verification, retractions)
7. Code signing, so the first-launch warning goes away
8. ~~Fellowships for life-science researchers: postdoc and PhD fellowships
   and travel grants, matching, application tracking, reminders and document
   checks~~ (v1.5); real fellowship entries and a monthly data refresh still
   to come

## Feedback

Galley is early, and the most useful thing you can send is a case where it's
**wrong**: something it flagged that was fine, or a real problem it stayed quiet
about. Two ways to reach me:

- [Tell me how you're using Galley](https://docs.google.com/forms/d/e/1FAIpQLSf-IEokqhT8mjond7SFDCp90sDzUDCupJPK8p26aVls46QYjg/viewform) — a short form.
  Leave your email if you'd like to hear when new checks land.
- [Open an issue](https://github.com/rahulnccs/galley/issues) for bugs.

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

## Licence

Galley is free to download and use for personal, academic and research
purposes. From version 1.6 the source code is **all rights reserved**: it may
not be copied, modified, redistributed or used to build a competing product
without written permission. See [LICENSE](LICENSE). Versions up to 1.5 were
released under the MIT License, and copies of them remain under it.

The fellowship list in [`galley/fellowships/data/`](galley/fellowships/data/)
is licensed separately under [CC BY 4.0](galley/fellowships/data/LICENSE), so
it can be reused with credit.

## Repositories

- **This repository (private):** the source code.
- **[rahulnccs/galley](https://github.com/rahulnccs/galley) (public):** the
  downloadable apps on its Releases page, the fellowship list that **Check for
  Updates** reads, and issues. The workflows publish both automatically; see
  [Releasing](#releasing).
