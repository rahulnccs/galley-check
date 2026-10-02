"""Fellowship matching: which fellowships a researcher can apply for, and why.

Everything here runs on the user's computer. The fellowship list ships with
Galley; the researcher's details never leave their machine.
"""
from .match import ELIGIBLE, NOT_ELIGIBLE, POSSIBLE, Match, match, match_all
from .requirements import Requirements, check_draft
from .timeline import Step, plan
from .tracker import (STATUSES, Application, Reminder, load_applications,
                      reminders, save_applications, start_application)
from .model import (Fellowship, Researcher, Stay, delete_custom_fellowship,
                    load_fellowships, save_custom_fellowship)

__all__ = ["STATUSES", "Application", "Reminder", "Requirements", "Step",
           "check_draft", "load_applications", "plan", "reminders",
           "save_applications", "start_application",
           "ELIGIBLE", "NOT_ELIGIBLE", "POSSIBLE", "Fellowship", "Match",
           "Researcher", "Stay", "delete_custom_fellowship", "load_fellowships",
           "match", "match_all", "save_custom_fellowship"]
