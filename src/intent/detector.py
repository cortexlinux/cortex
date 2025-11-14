# detector.py

from dataclasses import dataclass
from typing import List, Optional
import re

@dataclass
class Intent:
    action: str
    target: str
    details: Optional[dict] = None

class IntentDetector:
    """
    Extracts high-level installation intents from natural language requests.
    """

    COMMON_PACKAGES = {
        "cuda": ["cuda", "nvidia toolkit"],
        "pytorch": ["pytorch", "torch"],
        "tensorflow": ["tensorflow", "tf"],
        "jupyter": ["jupyter", "jupyterlab", "notebook"],
        "cudnn": ["cudnn"],
        "gpu": ["gpu", "graphics card", "rtx", "nvidia"]
    }

    def detect(self, text: str) -> List[Intent]:
        text = text.lower()
