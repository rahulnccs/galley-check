"""All checks the engine runs. New checks are added here.

Checks take a Document and return a list of Issue. A check that needs
configuration (like the journal profile) takes it as a second argument; the
engine passes it when one is available.
"""
from .offline.abbreviations import check_abbreviations
from .offline.consistency import check_consistency
from .offline.figures import check_figures
from .offline.references import check_references
from .offline.species import check_species
from .offline.statements import check_statements
from .offline.submission import check_submission

OFFLINE_CHECKS = {
    "figures": check_figures,
    "references": check_references,
    "abbreviations": check_abbreviations,
    "species": check_species,
    "consistency": check_consistency,
    "statements": check_statements,
    "submission": check_submission,
}

# Checks that accept a journal profile as their second argument.
PROFILE_AWARE = {"submission", "references", "statements"}
