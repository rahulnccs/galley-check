# Fellowship database

One JSON file per fellowship. Galley ships these files and, later, will
refresh them from this folder on GitHub, so a fix here reaches every user.

The three `example-*.json` files are invented and marked `"template": true`,
which keeps them out of real results. Copy one to start a new entry.

Scope: life-science fellowships only.

## Fields

| Key | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique, lower case with hyphens, e.g. `embo-postdoctoral`. Never change it once published: users' shortlists refer to it. |
| `name`, `funder`, `url` | yes | `url` is the funder's official call page. |
| `verified` | yes | The date you last read the official page (YYYY-MM-DD). Entries older than 12 months are flagged to users. |
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
| `other_rules` | no | Eligibility rules the fields above can't express, in plain words, e.g. `"Must move to a new research field"`. Each one makes the result "possibly eligible" and is shown to the user to check. |
| `amount`, `duration_months`, `notes` | no | Shown to users as written. `notes` is for information, not rules. |

## Requirements

```json
"requirements": {
  "documents": [
    {"name": "Research proposal", "max_pages": 5, "max_words": 3000,
     "min_font_size": 11, "sections": ["Background", "Aims"],
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
`funder_template`; `submission` is `portal`, `email` or `institution`. Galley
checks a draft .docx against a document's `max_words`, `max_pages` and
`sections`, and builds each applicant's preparation plan from the host letter
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
check reliably; a rule in `other_rules` turns "eligible" into "possibly
eligible" and is shown to the user, so it is never silently treated as met.

`pytest tests/test_fellowships.py` checks every file here loads.
