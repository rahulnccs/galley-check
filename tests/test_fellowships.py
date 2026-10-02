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
    entries = load_fellowships(include_templates=True, include_custom=False)
    assert len(entries) >= 3
    assert all(f.url.startswith("https://") for f in entries)


def test_templates_are_kept_out_of_real_results():
    assert all(not f.template for f in load_fellowships(include_custom=False))


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
        load_fellowships(tmp_path, include_custom=False)


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
    entries = {f.id: f for f in load_fellowships(DATA_DIR, include_templates=True,
                                                 include_custom=False)}
    indian_postdoc = Researcher(phd_date=date(2024, 8, 1), nationalities=["IN"],
                                residence="IN", clinical=False,
                                fields=["microbiology"], target_hosts=["IN", "DE"],
                                stays=[Stay("IN", date(2015, 1, 1))])
    results = {m.fellowship.id: m.status
               for m in match_all(list(entries.values()), indian_postdoc, TODAY)}
    assert results["example-national-fellowship"] == POSSIBLE   # other_rules
    assert results["example-clinical-rolling"] == NOT_ELIGIBLE  # clinical, GB
    assert results["example-international-postdoc"] == ELIGIBLE


# --- the user's own entries --------------------------------------------------

from galley.fellowships import (delete_custom_fellowship,  # noqa: E402
                                save_custom_fellowship)


def test_custom_entry_needs_only_a_name(tmp_path):
    f = save_custom_fellowship({"name": "Institute Internal Fellowship"}, tmp_path)
    assert f.id == "custom-institute-internal-fellowship"
    assert f.custom and (tmp_path / f"{f.id}.json").exists()


def test_custom_entry_without_a_name_is_refused(tmp_path):
    with pytest.raises(ValueError, match="give the entry a name"):
        save_custom_fellowship({"name": "  "}, tmp_path)
    assert not list(tmp_path.iterdir())


def test_custom_entry_is_validated_before_saving(tmp_path):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        save_custom_fellowship({"name": "X", "deadlines": [
            {"kind": "final", "date": "next March"}]}, tmp_path)
    assert not list(tmp_path.iterdir())


def test_custom_entries_load_with_the_database(tmp_path):
    save_custom_fellowship({"name": "Society Travel Grant",
                            "deadlines": [{"kind": "final", "date": "2026-11-30"}]},
                           tmp_path)
    entries = load_fellowships(custom_folder=tmp_path, include_templates=True)
    custom = [f for f in entries if f.custom]
    assert [f.name for f in custom] == ["Society Travel Grant"]
    assert len(entries) == len(load_fellowships(custom_folder=tmp_path / "none",
                                                include_templates=True)) + 1


def test_same_name_twice_gets_its_own_id(tmp_path):
    a = save_custom_fellowship({"name": "Seed Grant"}, tmp_path)
    b = save_custom_fellowship({"name": "Seed Grant"}, tmp_path)
    assert a.id != b.id and b.id == "custom-seed-grant-2"


def test_saving_with_an_id_updates_the_entry(tmp_path):
    f = save_custom_fellowship({"name": "Seed Grant"}, tmp_path)
    save_custom_fellowship({"id": f.id, "name": "Seed Grant (renewal)"}, tmp_path)
    names = [x.name for x in load_fellowships(tmp_path / "none", custom_folder=tmp_path)]
    assert names == ["Seed Grant (renewal)"]


def test_custom_ids_cannot_take_over_database_entries(tmp_path):
    with pytest.raises(ValueError, match='start with "custom-"'):
        save_custom_fellowship({"id": "example-clinical-rolling", "name": "X"},
                               tmp_path)


def test_delete_custom_entry(tmp_path):
    f = save_custom_fellowship({"name": "Seed Grant"}, tmp_path)
    assert delete_custom_fellowship(f.id, tmp_path)
    assert not delete_custom_fellowship(f.id, tmp_path)
    assert not delete_custom_fellowship("example-clinical-rolling", tmp_path)


def test_hand_edited_broken_custom_file_is_skipped(tmp_path):
    (tmp_path / "custom-broken.json").write_text("{ not json")
    save_custom_fellowship({"name": "Fine"}, tmp_path)
    names = [f.name for f in load_fellowships(tmp_path / "none", custom_folder=tmp_path)]
    assert names == ["Fine"]


def test_custom_entry_is_matched_like_any_other(tmp_path):
    f = save_custom_fellowship({"name": "Institute Fellowship",
                                "career_stage": {"max_years_since_phd": 2},
                                "deadlines": [{"kind": "final", "date": DEADLINE}]},
                               tmp_path)
    m = match(f, Researcher(phd_date=date(2020, 1, 1)), TODAY)
    assert m.status == NOT_ELIGIBLE
    assert "You added this entry yourself" in texts(m)
    assert "last checked" not in texts(m)       # no staleness nag on your own
