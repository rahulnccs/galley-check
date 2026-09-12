# Contributing

Bug reports are especially useful. The most valuable ones are manuscripts where
the tool is wrong: something flagged that is actually fine, or a real problem it
stayed silent about.

## Reporting a false alarm or a miss

Open an issue with the sentence involved (not the whole manuscript, which you may
not be able to share) and what you expected. For example: the legend reads
`Figure 1 | Study design`, and the tool didn't recognize it.

## Adding a check

1. Write the check in `galley/checks/offline/`. It takes a `Document`
   and returns a list of `Issue`.
2. Register it in `galley/checks/registry.py`.
3. Add tests. If the check depends on a citation or legend style, add a fixture to
   `tests/fixtures/make_corpus.py` declaring the errors it contains; the corpus
   tests then require your check to find exactly those and nothing else.

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

## Principles

- A false alarm costs more than a missed problem. When the tool can't tell what
  style a manuscript uses, it should say so and skip the check.
- Checks never modify the author's file. Output goes to a copy.
- Everything works offline. Anything needing the internet is opt-in.
