# Fellowship database

One JSON file per fellowship. Galley ships these files and, later, will
refresh them from this folder on GitHub, so a fix here reaches every user.

The three `example-*.json` files are invented and marked `"template": true`,
which keeps them out of real results. Copy one to start a new entry.

Scope: life-science funding only, of three kinds (`category`): postdoc
fellowships, PhD fellowships and travel grants.

## Fields

| Key | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique, lower case with hyphens, e.g. `embo-postdoctoral`. Never change it once published: users' shortlists refer to it. |
| `name`, `funder`, `url` | yes | `url` is the funder's official call page. |
| `verified` | yes | The date you last read the official page (YYYY-MM-DD), or `null` if nobody has yet. An unverified entry is never shown as "eligible", only "worth checking"; one older than 12 months is flagged. |
| `fields` | no | Life-science fields, or `["any"]` (the default). See the list below. |
| `track` | no | `any` (default), `clinical` or `non_clinical`. |
| `career_stage` | no | `min_years_since_phd`, `max_years_since_phd`, `phd_required` (default true when `career_stage` is given; leave the whole section out if career stage doesn't matter), `career_breaks_extend` (true if parental leave, illness etc. extend the window). |
| `nationalities` | no | Countries whose nationals may apply. Leave out for any. |
| `excluded_nationalities` | no | Countries whose nationals may not. |
| `residence` | no | Countries the applicant must live in. |
| `host_countries` | no | Where the fellowship must be held. Leave out for anywhere. |
| `excluded_host_countries` | no | Where it may not be held. |
| `mobility` | no | `{"max_months_in_host": 12, "window_years": 3}`: no more than 12 months living in the host country in the 3 years before the deadline. |
| `deadlines` | no | A list, each with `kind`, `date`, and optionally `time`, `timezone` (e.g. `Europe/Berlin`), `estimated` (true if guessed from previous years) and `label`. Kinds: `final`, `internal`, `pre_proposal`, `call_opens`. |
| `rolling` | no | true if applications are accepted at any time. |
| `annual` | no | true (default) if the call runs every year. |
| `requirements` | no | What the application needs; see below. |
| `category` | no | `postdoc` (default), `phd` or `travel`. |
| `career_levels` | no | Who may apply: any of `masters_student`, `phd_student`, `postdoc`, `faculty`. PhD fellowships default to Master's and PhD students; leave it out otherwise if the career-stage rules already say enough. |
| `purpose` | no | Travel grants: `conference`, `lab_visit`, `course`, `fieldwork` or `other`. |
| `membership`, `membership_min_months` | no | A society membership the applicant must hold, e.g. `"the British Society for Immunology"`, and for how long. Shown to users to check. |
| `other_rules` | no | Eligibility rules the fields above can't express, in plain words, e.g. `"Must move to a new research field"`. Shown to the user as a list to confirm; they don't change the verdict, which comes from the rules Galley can check. |
| `source` | no | Where the entry came from, for the maintainer. Not shown to users. |
| `amount`, `duration_months`, `notes` | no | Shown to users as written. `notes` is for information, not rules. |

## Requirements

```json
"requirements": {
  "documents": [
    {"name": "Research proposal", "max_pages": 5, "max_words": 3000,
     "min_font_size": 11, "min_margin_cm": 2, "file_format": "pdf",
     "sections": ["Background", "Aims"],
     "template_url": "https://...", "notes": "References don't count"}
  ],
  "cv_format": "narrative",
  "cv_notes": "Two pages, funder's template",
  "host_letter": true,
  "submission": "portal",
  "submission_url": "https://..."
}
```

Everything is optional. `cv_format` is `standard`, `narrative` or
`funder_template`; `submission` is `portal`, `email` or `institution`;
`file_format` is `pdf` or `docx`. When a user attaches their documents, Galley
checks each against `max_pages`, `max_words`, `sections`, `min_font_size`,
`min_margin_cm` and `file_format`, and builds each applicant's preparation plan from the host letter
and documents listed here.

Countries are two-letter ISO codes: `IN`, `DE`, `GB`, `US`.

Fields: `molecular_cell_biology`, `neuroscience`, `immunology_infection`,
`genetics_genomics`, `ecology_evolution`, `plant_science`, `microbiology`,
`structural_biology`, `bioinformatics`, `biomedical_clinical`.

## Users' own entries

Users can add fellowships that aren't here (an institute's internal scheme, a
society grant) with `save_custom_fellowship`. Those are saved in their Galley
settings folder, never in this one, so a refresh of the database leaves them
alone. They use the same keys as above, but only `name` is required, and their
ids always start with `custom-`.

## When a rule doesn't fit

Put it in `other_rules` in plain words. The matcher only decides what it can
check reliably; a rule in `other_rules` is listed on the fellowship under
"Also confirm", so it is never silently treated as met. If the rule is one
most applicants fail, say so plainly so it stands out.

## From the spreadsheet

Fill in `templates/fellowship-database-template.xlsx` (one row per
fellowship, one row per required document) and run

    python scripts/import_fellowships.py filled-template.xlsx

It writes one file here per row, named after the id, replacing any file
with the same id. It checks every row first and writes nothing until all
of them are valid, listing each problem with its row number. Rows whose id
starts with `example-` are skipped.

`pytest tests/test_fellowships.py` checks every file here loads.
