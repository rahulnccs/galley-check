"""Fellowship matching: which fellowships a researcher can apply for, and why.

Everything here runs on the user's computer. The fellowship list ships with
Galley; the researcher's details never leave their machine.
"""
from .match import ELIGIBLE, NOT_ELIGIBLE, POSSIBLE, Match, match, match_all
from .model import Fellowship, Researcher, Stay, load_fellowships

__all__ = ["ELIGIBLE", "NOT_ELIGIBLE", "POSSIBLE", "Fellowship", "Match",
           "Researcher", "Stay", "load_fellowships", "match", "match_all"]
