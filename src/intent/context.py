# context.py

from typing import List, Optional
from intent.detector import Intent

class SessionContext:
    """
    Stores context from previous user interactions.
    This is needed for Issue #53:
    'Uses context from previous commands'
    """

    def __init__(self):
        self.detected_gpu: Optional[str] = None
        self.previous_intents: List[Intent] = []
        self.installed_packages: List[str] = []
        self.clarifications: List[str] = []

    # -------------------
    # GPU CONTEXT
    # -------------------

    def set_gpu(self, gpu_name: str):
        self.detected_gpu = gpu_name

    def get_gpu(self) -> Optional[str]:
        return self.detected_gpu

    # -------------------
    # INTENT CONTEXT
    # -------------------

    def add_intents(self, intents: List[Intent]):
        self.previous_intents.extend(intents)

    def get_previous_intents(self) -> List[Intent]:
        return self.previous_intents

    # -------------------
    # INSTALLED PACKAGES
    # -------------------

    def add_installed(self, pkg: str):
        if pkg not in self.installed_packages:
            self.installed_packages.append(pkg)

    def is_installed(self, pkg: str) -> bool:
        return pkg in self.installed_packages

    # -------------------
    # CLARIFICATIONS
    # -------------------

    def add_clarification(self, question: str):
        self.clarifications.append(question)

    def get_clarifications(self) -> List[str]:
        return self.clarifications

    # -------------------
    # RESET CONTEXT
    # -------------------

    def reset(self):
        """Reset context (new session)"""
        self.detected_gpu = None
        self.previous_intents = []
        self.installed_packages = []
        self.clarifications = []
