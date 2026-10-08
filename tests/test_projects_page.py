"""The Projects screen. Needs Qt; skipped where PySide6 isn't installed."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from galley.projects import Analysis, Sample, load_projects, new_project, save_project  # noqa: E402


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    if existing is not None:
        return existing
    try:
        return QApplication([])
    except Exception as e:
        pytest.skip(f"Qt cannot start here: {e}")


def texts(widget):
    return " | ".join(l.text() for l in widget.findChildren(QLabel))


@pytest.fixture
def setup(tmp_path):
    data = tmp_path / "rna" / "M01"
    data.mkdir(parents=True)
    p = new_project("Gut microbiome", tmp_path / "projects")
    s = p.add_sample(Sample("M01", "Caecum"))
    s.set_analysis(Analysis("RNA-seq", "done", str(data), str(tmp_path / "gone")))
    p.add_sample(Sample("M02", "Colon"))
    save_project(p, tmp_path / "projects")
    return tmp_path / "projects", p, data


def page_for(folder):
    from galley.gui.projects_page import ProjectsPage
    return ProjectsPage(folder)


def test_home_lists_projects(app, setup):
    folder, p, _ = setup
    page = page_for(folder)
    shown = texts(page.current)
    assert "Gut microbiome" in shown and "2 samples" in shown


def test_samples_tab_tiles_and_chips(app, setup):
    from galley.gui.app import Tile
    folder, p, _ = setup
    page = page_for(folder)
    page.open_project(p.id)
    tiles = {t.key: t.text().split()[0] for t in page.current.findChildren(Tile)}
    assert tiles["all"] == "2" and tiles["RNA-seq"] == "1"
    assert "M01" in texts(page.current) and "RNA-seq" in texts(page.current)
    page._filter_analysis("RNA-seq")
    assert "M02" not in texts(page.current)


def test_clicking_a_sample_offers_its_folders(app, setup, monkeypatch):
    folder, p, data = setup
    page = page_for(folder)
    page.open_project(p.id)
    items = page.sample_menu_items(page.project.sample("M01"))
    labels = [(t, enabled) for t, _, _, _, enabled in items]
    assert labels[0] == ("RNA-seq · raw data", True)
    assert labels[1] == ("RNA-seq · analysis", False)       # folder is gone
    assert labels[-1][0].startswith("Sample details")
    opened = []
    from galley.gui import projects_page as pp
    monkeypatch.setattr(pp.QDesktopServices, "openUrl", lambda url: opened.append(url))
    items[0][3]()
    assert opened and opened[0].toLocalFile() == str(data)


def test_missing_folder_is_reported_not_opened(app, setup, monkeypatch):
    folder, p, _ = setup
    from galley.gui import projects_page as pp
    warned, opened = [], []
    monkeypatch.setattr(pp.QMessageBox, "warning", lambda *a: warned.append(a[1]))
    monkeypatch.setattr(pp.QDesktopServices, "openUrl", lambda url: opened.append(url))
    assert not pp.open_folder(None, "/no/such/folder")
    assert warned == ["Folder not found"] and not opened


def test_readme_saves(app, setup):
    folder, p, _ = setup
    page = page_for(folder)
    page.open_project(p.id, tab=0)
    page.r_text.setPlainText("Does diet change the gut microbiome?")
    page.r_kinds.setText("RNA-seq, Metabolomics, Lipidomics")
    page.save_readme()
    back = load_projects(folder)[0]
    assert back.readme == "Does diet change the gut microbiome?"
    assert back.analysis_types == ["RNA-seq", "Metabolomics", "Lipidomics"]


def test_sample_page_and_notebook(app, setup):
    folder, p, _ = setup
    page = page_for(folder)
    page.open_project(p.id)
    page.project.add_note("Extracted RNA", samples=["M01"])
    page.open_sample("M01")
    shown = texts(page.current)
    assert "Caecum" in shown and "Extracted RNA" in shown and "NOTEBOOK · 1" in shown
    page._switch_tab(2)
    assert "Extracted RNA" in texts(page.current)


def test_main_window_has_projects(app, setup, tmp_path, monkeypatch):
    from galley.checks.offline import submission
    monkeypatch.setattr(submission, "user_profile_dir", lambda: tmp_path / "profiles")
    from galley.gui.app import MainWindow
    win = MainWindow("Georgia")
    assert [b.text() for b in win.switcher.buttons][2] == "Projects"
    win.switcher.select(2)
    assert win.sections.currentWidget() is win.projects
