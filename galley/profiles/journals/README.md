# Journal list

One JSON file per journal (and article type). Galley ships these files, and
**Check for Updates** on the Manuscript screen refreshes them from this
folder on GitHub, so a correction here reaches every user.

The easiest way to maintain the list is the spreadsheet:

    python scripts/journals_sheet.py export journals.xlsx   # the list, for Excel
    python scripts/journals_sheet.py import journals.xlsx   # back into this folder

Checking a journal means reading its author guidelines, correcting the row,
and setting `verified` to that day's date. Until then (`"verified": null`)
Galley tells users the requirements haven't been confirmed: limits are marked
"not yet confirmed" and a missing section is a warning rather than an error.

## Fields

| Key | Meaning |
| --- | --- |
| `id` | File name, lower case with hyphens, e.g. `nature-communications`. Never change it once published. |
| `name`, `publisher`, `article_type` | Shown in the journal list as "Name · Article type". Use one file per article type if they differ much. |
| `guidelines_url` | The journal's own author guidelines. Required. |
| `verified` | The date you last read those guidelines (YYYY-MM-DD), or `null`. |
| `limits` | Any of `title_words`, `title_chars`, `abstract_words`, `main_text_words` (introduction to discussion), `total_words` (abstract, main text and methods), `keywords` (most allowed), `references`, `figures`, `tables`, `display_items` (figures and tables together). Leave out what the journal doesn't limit. |
| `abstract_headings` | For a structured abstract, its headings in order, e.g. `["Background", "Results", "Conclusions"]`. |
| `required_sections` | Sections or statements that must be present, e.g. `"Data availability"`. Matched against headings and run-in headings, ignoring "and", "of" and "the". |
| `reference_style` | `numbered` or `author_year`. |
| `max_authors_listed` | Authors listed in a reference before "et al.". |
| `require_doi` | `true` if every reference needs a DOI. |
| `notes` | Shown to users: anything they should know that the fields can't say. |
