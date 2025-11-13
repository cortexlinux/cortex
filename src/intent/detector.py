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
        intents = []

        # 1. Rule-based keyword detection
        for pkg, keywords in self.COMMON_PACKAGES.items():
            if any(k in text for k in keywords):
                intents.append(Intent(action="install", target=pkg))

        # 2. Look for verify steps
        if "verify" in text or "check" in text:
            intents.append(Intent(action="verify", target="installation"))

        # 3. GPU setup requests
        # Avoid duplicate GPU intents
        if "gpu" in text and not any(i.target == "gpu" for i in intents):
            intents.append(Intent(action="configure", target="gpu"))


        # 4. If nothing detected → return empty list (LLM will help later)
        return intents

