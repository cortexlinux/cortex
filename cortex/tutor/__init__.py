"""
Intelligent Tutor - AI-Powered Installation Tutor for Cortex Linux.

An interactive AI tutor that teaches users about packages and best practices.
"""

from cortex.tutor import agent
from cortex.tutor.branding import console, tutor_print
from cortex.tutor.config import Config

__all__ = ["Config", "agent", "console", "tutor_print"]
