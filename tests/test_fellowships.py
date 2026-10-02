"""Fellowship matching: format, eligibility rules, and ordering."""
from datetime import date

import pytest

from galley.fellowships import (ELIGIBLE, NOT_ELIGIBLE, POSSIBLE, Fellowship,
                                Researcher, Stay, load_fellowships, match,
                                match_all)
from galley.fellowships.model import DATA_DIR

TODAY = date(2026, 10, 1)
DEADLINE = "2027-01-15"


def fellowship(**overrides) -> Fellowship:
    data = {"id": "f", "name": "Test Fellowship", "funder": "Test Funder",
            "url": "https://example.org/f", "verified": "2026-09-01",
            "deadlines": [{"kind": "final", "date": DEADLINE}]}
    data.update(overrides)
    return Fellowship.from_dict(data)


def texts(m):
    return " | ".join(r.text for r in m.reasons)


# --- the database itself ---------------------------------------------------

def test_every_shipped_entry_loads():
    entries = load_fellowships(include_templates=True)
    assert len(entries) >= 3
    assert all(f.url.startswith("https://") for f in entries)


def test_templates_are_kept_out_of_real_results():
    assert all(not f.template for f in load_fellowships())


@pytest.mark.parametrize("bad, complaint", [
    ({"fields": ["astrophysics"]}, "unknown field"),
    ({"track": "surgical"}, "track must be"),
    ({"nationalities": ["India"]}, "not two-letter country codes"),
    ({"deadlines": [{"kind": "final", "date": "15/01/2027"}]}, "YYYY-MM-DD"),
    ({"deadlines": [{"kind": "soon", "date": "2027-01-15"}]}, "deadline kind"),
])
def test_bad_entries_are_rejected_clearly(bad, complaint):
    with pytest.raises(ValueError, match=complaint):
        fellowship(**bad)


def test_missing_required_key():
    with pytest.raises(ValueError, match="missing 'url'"):
        Fellowship.from_dict({"id": "x", "name": "X", "funder": "Y"})


def test_duplicate_ids_rejected(tmp_path):
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text(
            '{"id": "same", "name": "N", "funder": "F", "url": "https://x.org"}')
    with pytest.raises(ValueError, match="duplicate fellowship id"):
        load_fellowships(tmp_path)


# --- career stage ----------------------------------------------------------

def test_within_window_is_eligible():
    f = fellowship(career_stage={"max_years_since_phd": 3})
    m = match(f, Researcher(phd_date=date(2025, 6, 1)), TODAY)
    assert m.status == ELIGIBLE
    assert "1.6 years" in texts(m)          # counted to the Jan 2027 deadline


def test_too_senior_is_not_eligible():
    f = fellowship(career_stage={"max_years_since_phd": 3})
    m = match(f, Researcher(phd_date=date(2020, 1, 1)), TODAY)
    assert m.status == NOT_ELIGIBLE
    assert "up to 3 years" in texts(m)


def test_too_junior_is_not_eligible():
    f = fellowship(career_stage={"min_years_since_phd": 2})
    m = match(f, Researcher(phd_date=date(2026, 1, 1)), TODAY)
    assert m.status == NOT_ELIGIBLE


def test_career_break_extends_window_when_funder_allows():
    f = fellowship(career_stage={"max_years_since_phd": 3,
                                 "career_breaks_extend": True})
    r = Researcher(phd_date=date(2023, 6, 1), career_break_months=12)
    m = match(f, r, TODAY)
    assert m.status == ELIGIBLE
    assert "counting your career break" in texts(m)


def test_career_break_is_unsure_when_funder_silent():
    # Over the limit only because of the break: don't rule them out.
    f = fellowship(career_stage={"max_years_since_phd": 3})
    r = Researcher(phd_date=date(2023, 6, 1), career_break_months=12)
    m = match(f, r, TODAY)
    assert m.status == POSSIBLE
    assert "allows for breaks" in texts(m)


def test_missing_phd_date_is_possible_not_excluded():
    f = fellowship(career_stage={"max_years_since_phd": 3})
    assert match(f, Researcher(), TODAY).status == POSSIBLE


def test_phd_expected_is_possible():
    f = fellowship(career_stage={"max_years_since_phd": 3})
    m = match(f, Researcher(phd_expected=date(2026, 12, 1)), TODAY)
    assert m.status == POSSIBLE
    assert "before the PhD is awarded" in texts(m)


def test_no_phd_needed():
    f = fellowship(career_stage={"phd_required": False})
    assert match(f, Researcher(), TODAY).status == ELIGIBLE


# --- nationality, residence, host country ---------------------------------

def test_nationality_allowed_list():
    f = fellowship(nationalities=["IN"])
    assert match(f, Researcher(nationalities=["IN"]), TODAY).status == ELIGIBLE
    assert match(f, Researcher(nationalities=["DE"]), TODAY).status == NOT_ELIGIBLE
    assert match(f, Researcher(), TODAY).status == POSSIBLE


def test_dual_nationality_counts_if_either_is_accepted():
    f = fellowship(nationalities=["IN"])
    assert match(f, Researcher(nationalities=["GB", "IN"]), TODAY).status == ELIGIBLE


def test_excluded_nationality():
    f = fellowship(excluded_nationalities=["US"])
    assert match(f, Researcher(nationalities=["US"]), TODAY).status == NOT_ELIGIBLE
    assert match(f, Researcher(nationalities=["FR"]), TODAY).status == ELIGIBLE


def test_residence():
    f = fellowship(residence=["IN"])
    assert match(f, Researcher(residence="IN"), TODAY).status == ELIGIBLE
    assert match(f, Researcher(residence="US"), TODAY).status == NOT_ELIGIBLE


def test_host_country_against_researchers_choice():
    f = fellowship(host_countries=["DE", "FR"])
    assert match(f, Researcher(target_hosts=["FR"]), TODAY).status == ELIGIBLE
    m = match(f, Researcher(target_hosts=["US"]), TODAY)
    assert m.status == NOT_ELIGIBLE and "must be in DE, FR" in texts(m)


def test_host_restriction_is_only_information_without_a_choice():
    f = fellowship(host_countries=["DE"])
    m = match(f, Researcher(), TODAY)
    assert m.status == ELIGIBLE and "must be in DE" in texts(m)


# --- mobility ---------------------------------------------------------------

MOBILITY = {"max_months_in_host": 12, "window_years": 3}


def test_mobility_met():
    f = fellowship(mobility=MOBILITY)
    r = Researcher(target_hosts=["DE"],
                   stays=[Stay("IN", date(2018, 1, 1)),
                          Stay("DE", date(2019, 1, 1), date(2019, 6, 1))])
    assert match(f, r, TODAY).status == ELIGIBLE


def test_mobility_broken_by_living_in_host():
    f = fellowship(mobility=MOBILITY)
    r = Researcher(target_hosts=["DE"], stays=[Stay("DE", date(2024, 1, 1))])
    m = match(f, r, TODAY)
    assert m.status == NOT_ELIGIBLE and "lived in DE" in texts(m)


def test_mobility_counts_only_the_window():
    # Two years in Germany, but ending well before the 3-year window.
    f = fellowship(mobility=MOBILITY)
    r = Researcher(target_hosts=["DE"],
                   stays=[Stay("DE", date(2019, 1, 1), date(2021, 1, 1)),
                          Stay("IN", date(2021, 1, 1))])
    assert match(f, r, TODAY).status == ELIGIBLE


def test_mobility_unknown_without_history():
    f = fellowship(mobility=MOBILITY)
    assert match(f, Researcher(target_hosts=["DE"]), TODAY).status == POSSIBLE


# --- track, extra rules, dates ----------------------------------------------

def test_clinical_track():
    f = fellowship(track="clinical")
    assert match(f, Researcher(clinical=True), TODAY).status == ELIGIBLE
    assert match(f, Researcher(clinical=False), TODAY).status == NOT_ELIGIBLE
    assert match(f, Researcher(), TODAY).status == POSSIBLE


def test_other_rules_are_never_silently_met():
    f = fellowship(other_rules=["Must move to a new research field"])
    m = match(f, Researcher(), TODAY)
    assert m.status == POSSIBLE
    assert "Must move to a new research field" in texts(m)


def test_past_deadline_predicts_next_call():
    f = fellowship(deadlines=[{"kind": "final", "date": "2026-03-01"}])
    m = match(f, Researcher(), TODAY)
    assert not m.is_open
    assert "expected around Mar 2027" in texts(m)


def test_estimated_deadline_is_labelled():
    f = fellowship(deadlines=[{"kind": "final", "date": DEADLINE, "estimated": True}])
    assert "estimated from previous years" in texts(match(f, Researcher(), TODAY))


def test_stale_entry_is_flagged():
    f = fellowship(verified="2024-01-01")
    assert "last checked Jan 2024" in texts(match(f, Researcher(), TODAY))


def test_ordering():
    soon = fellowship(id="soon", name="Soon",
                      deadlines=[{"kind": "final", "date": "2026-11-01"}])
    later = fellowship(id="later", name="Later")
    closed = fellowship(id="closed", name="Closed",
                        deadlines=[{"kind": "final", "date": "2026-01-01"}])
    blocked = fellowship(id="blocked", name="Blocked", nationalities=["JP"])
    unsure = fellowship(id="unsure", name="Unsure", track="clinical")
    order = [m.fellowship.id for m in match_all(
        [blocked, closed, later, unsure, soon],
        Researcher(nationalities=["IN"]), TODAY)]
    assert order == ["soon", "later", "closed", "unsure", "blocked"]


def test_researchers_own_field_ranks_first():
    general = fellowship(id="general", name="General")
    neuro = fellowship(id="neuro", name="Neuro", fields=["neuroscience"])
    order = [m.fellowship.id for m in match_all(
        [general, neuro], Researcher(fields=["neuroscience"]), TODAY)]
    assert order == ["neuro", "general"]


def test_shipped_examples_match_sensibly():
    entries = {f.id: f for f in load_fellowships(DATA_DIR, include_templates=True)}
    indian_postdoc = Researcher(phd_date=date(2024, 8, 1), nationalities=["IN"],
                                residence="IN", clinical=False,
                                fields=["microbiology"], target_hosts=["IN", "DE"],
                                stays=[Stay("IN", date(2015, 1, 1))])
    results = {m.fellowship.id: m.status
               for m in match_all(list(entries.values()), indian_postdoc, TODAY)}
    assert results["example-national-fellowship"] == POSSIBLE   # other_rules
    assert results["example-clinical-rolling"] == NOT_ELIGIBLE  # clinical, GB
    assert results["example-international-postdoc"] == ELIGIBLE
