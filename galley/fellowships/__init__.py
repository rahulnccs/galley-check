"""Fellowship matching: which fellowships a researcher can apply for, and why.

Everything here runs on the user's computer. The fellowship list ships with
Galley; the researcher's details never leave their machine.
"""
from .match import ELIGIBLE, NOT_ELIGIBLE, POSSIBLE, Match, match, match_all
from .application_check import (ApplicationReport, Finding, check_application,
                                check_document, pdf_supported)
from .requirements import Requirements
from .timeline import Step, plan
from .tracker import (STATUSES, Application, Reminder, load_applications,
                      reminders, save_applications, start_application)
from .model import (Fellowship, Researcher, Stay, delete_custom_fellowship,
                    load_fellowships, save_custom_fellowship)

__all__ = ["STATUSES", "Application", "Reminder", "Requirements", "Step",
           "ApplicationReport", "Finding", "check_application",
           "check_document", "pdf_supported", "load_applications", "plan", "reminders",
           "save_applications", "start_application",
           "ELIGIBLE", "NOT_ELIGIBLE", "POSSIBLE", "Fellowship", "Match",
           "Researcher", "Stay", "delete_custom_fellowship", "load_fellowships",
           "match", "match_all", "save_custom_fellowship"]
