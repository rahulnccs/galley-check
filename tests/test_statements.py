"""Ethics and declaration statements."""
from galley.checks.offline.statements import check_statements
from galley.checks.offline.submission import Profile
from galley.model.document import Document, Paragraph

DECLARATIONS = [
    ("back_matter", "Data availability. Sequencing data are deposited in GEO (GSE1)."),
    ("back_matter", "Competing interests. The authors declare no competing interests."),
    ("acknowledgments", "This work was funded by the Wellcome Trust (grant 1234)."),
    ("back_matter", "Author contributions. A.B. designed the study; C.D. wrote it."),
]


def make_doc(rows):
    paras = [Paragraph(index=i, text=text, style="Normal", section=section)
             for i, (section, text) in enumerate(rows)]
    return Document(path="t.docx", paragraphs=paras)


def messages(rows, profile=None):
    return [(i.severity, i.message)
            for i in check_statements(make_doc(rows), profile)]


def test_complete_manuscript_is_silent():
    assert messages([("results", "Growth was faster at 30 °C.")] + DECLARATIONS) == []


def test_missing_statements_reported_together():
    msgs = messages([("results", "Growth was faster at 30 °C.")])
    assert msgs == [("info",
                     "No data availability, competing interests, funding or "
                     "author contributions statements were found. Most "
                     "journals ask for these.")]


def test_one_missing_statement():
    msgs = messages([("results", "Growth was faster.")] + DECLARATIONS[1:])
    assert msgs == [("info", "No data availability statement was found. "
                             "Most journals ask for one.")]


def test_profile_required_sections_are_not_repeated():
    profile = Profile(name="J", required_sections=["Data availability"])
    msgs = messages([("results", "Growth was faster.")] + DECLARATIONS[1:], profile)
    assert msgs == []


def test_human_study_without_ethics_or_consent():
    msgs = messages([
        ("methods", "We recruited 40 patients from two clinics."),
        ("results", "Patients in the treated arm recovered sooner."),
    ] + DECLARATIONS)
    loud = [m for s, m in msgs if s == "warning"]
    assert len(loud) == 2
    assert "no ethics approval statement" in loud[0]
    assert "informed consent" in loud[1]


def test_human_study_with_ethics_and_consent_is_silent():
    assert messages([
        ("methods", "We recruited 40 patients. The study was approved by the "
                    "Oxford Research Ethics Committee (ref 12/345) and all "
                    "participants gave written informed consent."),
        ("results", "Patients in the treated arm recovered sooner."),
    ] + DECLARATIONS) == []


def test_patients_mentioned_only_in_introduction():
    # Background about a disease is not a study of people.
    assert messages([
        ("introduction", "Many patients relapse, and patients with sepsis die."),
        ("results", "The enzyme was active at pH 7."),
    ] + DECLARATIONS) == []


def test_animal_study_without_ethics():
    msgs = messages([
        ("methods", "Mice were housed in groups of four."),
        ("results", "Treated mice gained less weight."),
    ] + DECLARATIONS)
    assert any(s == "warning" and "no animal ethics approval" in m for s, m in msgs)


def test_animal_study_with_iacuc_is_silent():
    assert messages([
        ("methods", "Mice were housed in groups of four. Procedures were "
                    "approved by the IACUC of the university (protocol 22-1)."),
        ("results", "Treated mice gained less weight."),
    ] + DECLARATIONS) == []


def test_antibodies_are_not_animal_work():
    assert messages([
        ("methods", "We used a mouse anti-GFP antibody and a rabbit polyclonal "
                    "antibody raised in rabbits against actin."),
        ("results", "GFP and actin co-localized."),
    ] + DECLARATIONS) == []


def test_custom_code_without_availability():
    msgs = messages([("methods", "Images were analysed with custom Python scripts.")]
                    + DECLARATIONS)
    assert any("custom Python scripts" in m and "where the code" in m for _, m in msgs)


def test_custom_code_with_github_link_is_silent():
    assert messages([("methods", "Images were analysed with custom scripts, "
                                 "available at github.com/lab/tool.")]
                    + DECLARATIONS) == []
