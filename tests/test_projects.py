"""Projects: samples, analyses, notebook, sample sheets and storage."""
from datetime import date

import pytest

from galley.projects import (Analysis, Sample, delete_project,
                             export_sample_sheet, import_sample_sheet,
                             load_projects, new_project, save_project)


@pytest.fixture
def project(tmp_path):
    return new_project("Gut microbiome in mice", tmp_path)


def test_new_project_is_saved_with_a_tidy_id(tmp_path, project):
    assert project.id == "gut-microbiome-in-mice"
    assert (tmp_path / "gut-microbiome-in-mice.json").exists()
    again = new_project("Gut microbiome in mice", tmp_path)
    assert again.id == "gut-microbiome-in-mice-2"


def test_project_needs_a_name(tmp_path):
    with pytest.raises(ValueError, match="name"):
        new_project("  ", tmp_path)


def test_samples_and_analyses(project):
    s = project.add_sample(Sample("M01", "Caecum, day 7"))
    s.set_analysis(Analysis("RNA-seq", "done", "/data/rna/M01", "/analysis/rna/M01"))
    s.set_analysis(Analysis("DNA-seq", "in_progress", "/data/dna/M01"))
    assert project.count("RNA-seq") == 1 and project.count("DNA-seq") == 0
    assert project.count("DNA-seq", None) == 1
    assert s.analysis("rna-seq").folders() == [("raw data", "/data/rna/M01"),
                                               ("analysis", "/analysis/rna/M01")]
    s.set_analysis(Analysis("RNA-seq", "failed"))           # replaces, not duplicates
    assert len(s.analyses) == 2 and s.analysis("RNA-seq").status == "failed"


def test_duplicate_or_blank_sample_ids_refused(project):
    project.add_sample(Sample("M01"))
    with pytest.raises(ValueError, match="already"):
        project.add_sample(Sample("M01"))
    with pytest.raises(ValueError, match="ID"):
        project.add_sample(Sample("  "))


def test_bad_status_refused():
    with pytest.raises(ValueError, match="status"):
        Analysis("RNA-seq", "finished")


def test_notebook_links_samples(project):
    project.add_sample(Sample("M01"))
    project.add_note("Extracted RNA, RIN 8.2", date(2026, 10, 1), ["M01"])
    project.add_note("Ordered reagents", date(2026, 10, 2))
    assert [n.text for n in project.notes_for("M01")] == ["Extracted RNA, RIN 8.2"]
    assert project.unknown_samples(["M01", "M99"]) == ["M99"]
    with pytest.raises(ValueError, match="empty"):
        project.add_note("   ")


def test_save_and_load_round_trip(tmp_path, project):
    s = project.add_sample(Sample("M01", "Caecum"))
    s.set_analysis(Analysis("Metabolomics", "planned", "/data/met"))
    project.add_note("Note", date(2026, 10, 1), ["M01"])
    project.readme = "Does diet change the gut microbiome?"
    save_project(project, tmp_path)
    back = load_projects(tmp_path)[0]
    assert back == project


def test_broken_project_file_is_skipped(tmp_path, project):
    (tmp_path / "broken.json").write_text("{ nope")
    assert [p.id for p in load_projects(tmp_path)] == [project.id]


def test_delete_project(tmp_path, project):
    assert delete_project(project.id, tmp_path)
    assert load_projects(tmp_path) == []


def test_import_sample_sheet(tmp_path, project):
    sheet = tmp_path / "samples.csv"
    sheet.write_text(
        "Sample ID,description,collected,RNA-seq data,RNA-seq analysis,Lipidomics data\n"
        "M01,Caecum,2026-09-01,/data/rna/M01,/res/rna/M01,\n"
        "M02,Colon,,/data/rna/M02,,/data/lip/M02\n"
        ",missing id,,,,\n", encoding="utf-8")
    result = import_sample_sheet(project, sheet)
    assert (result.added, result.updated) == (2, 0)
    assert result.skipped == ["Row 4: no sample ID"]
    assert project.sample("M01").analysis("RNA-seq").results_path == "/res/rna/M01"
    assert project.sample("M02").analysis("Lipidomics").data_path == "/data/lip/M02"
    assert "Lipidomics" in project.analysis_types          # new type learnt


def test_sheet_without_id_column_refused(tmp_path, project):
    sheet = tmp_path / "bad.csv"
    sheet.write_text("name,RNA-seq data\nM01,/x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sample_id"):
        import_sample_sheet(project, sheet)


def test_export_then_import_round_trip(tmp_path, project):
    s = project.add_sample(Sample("M01", "Caecum", "2026-09-01"))
    s.set_analysis(Analysis("RNA-seq", "in_progress", "/data/rna", "/res/rna"))
    out = tmp_path / "out.csv"
    export_sample_sheet(project, out)
    other = new_project("Copy", tmp_path)
    import_sample_sheet(other, out)
    a = other.sample("M01").analysis("RNA-seq")
    assert (a.status, a.data_path, a.results_path) == ("in_progress", "/data/rna", "/res/rna")
    assert other.sample("M01").description == "Caecum"
