"""All checks the engine runs. New checks are added here."""
from .offline.figures import check_figures
from .offline.references import check_references

OFFLINE_CHECKS = {
    "figures": check_figures,
    "references": check_references,
}
