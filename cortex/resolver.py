"""
Semantic Version Conflict Resolver Module.
Handles dependency version conflicts using AI-driven intelligent analysis.
"""

import json
import logging
import re
from typing import Any

import semantic_version as sv

from cortex.ask import AskHandler

logger = logging.getLogger(__name__)


class DependencyResolver:
    """
    AI-powered semantic version conflict resolver.
    Analyzes dependency trees and suggests upgrade/downgrade paths.

    Supported Semver Examples:
        - Caret: "^1.0.0" (Updates within major version)
        - Tilde: "~1.9.0" (Updates within minor version)
        - Ranges: ">=1.0.0 <2.0.0"
        - Exact: "1.1.0"
    """

    def __init__(self, api_key: str | None = None, provider: str = "ollama"):
        """
        Initialize the resolver with the AskHandler for reasoning.
        """
        self.handler = AskHandler(
            api_key=api_key or "ollama",
            provider=provider,
        )

    async def resolve(self, conflict_data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Resolve semantic version conflicts using deterministic analysis and AI.
        """
        required_keys = ["package_a", "package_b", "dependency"]
        for key in required_keys:
            if key not in conflict_data:
                raise KeyError(f"Missing required key: {key}")

        # 1. Deterministic resolution first (Reliable & Fast)
        strategies = self._deterministic_resolution(conflict_data)
        if strategies and strategies[0].get("risk") == "Low":
            return strategies

        # 2. AI Reasoning fallback
        prompt = self._build_prompt(conflict_data)
        try:
            # We use the handler to get the AI suggestion
            response = self.handler.ask(prompt)
            ai_strategies = self._parse_ai_response(response)

            # If AI returns valid data, combine or return it
            return ai_strategies if ai_strategies else strategies
        except Exception as e:
            logger.error(f"AI Resolution failed: {e}")
            # Ensure we never return an empty list or a raw error string
            return strategies or [
                {
                    "id": 1,
                    "type": "Manual",
                    "action": f"Check {conflict_data['dependency']} compatibility manually.",
                    "risk": "High",
                }
            ]

    def _deterministic_resolution(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Perform semantic-version constraint analysis safely."""
        try:
            dependency = data["dependency"]
            a_req = sv.SimpleSpec(data["package_a"]["requires"])
            b_req = sv.SimpleSpec(data["package_b"]["requires"])

            intersection = a_req & b_req
            if intersection:
                return [
                    {
                        "id": 1,
                        "type": "Recommended",
                        "action": f"Use {dependency} {intersection}",
                        "risk": "Low",
                        "explanation": "Version constraints are compatible",
                    }
                ]

            if not a_req.specs:
                return []

            a_spec = a_req.specs[0]
            a_major = getattr(getattr(a_spec, "version", object()), "major", 0)

            return [
                {
                    "id": 1,
                    "type": "Recommended",
                    "action": f"Upgrade {data['package_b']['name']} to support {dependency} ^{a_major}.0.0",
                    "risk": "Medium",
                }
            ]
        except Exception as e:
            logger.debug(f"Deterministic resolution skipped: {e}")
            return []

    def _build_prompt(self, data: dict[str, Any]) -> str:
        """Constructs a prompt for direct JSON response with parseable actions."""
        return (
            f"Act as a semantic version conflict resolver. "
            f"Analyze this conflict for the dependency: {data['dependency']}. "
            f"Package '{data['package_a']['name']}' requires {data['package_a']['requires']}. "
            f"Package '{data['package_b']['name']}' requires {data['package_b']['requires']}. "
            "Return ONLY a JSON array of 2 objects with keys: 'id', 'type', 'action', 'risk'. "
            "IMPORTANT: The 'action' field MUST follow the exact format: 'Use <package_name> <version>' "
            "(e.g., 'Use django 4.2.0') so it can be parsed by the system. "
            f"Do not mention packages other than {data['package_a']['name']}, {data['package_b']['name']}, and {data['dependency']}."
        )

    def _parse_ai_response(self, response: str) -> list[dict[str, Any]]:
        """Parses the LLM output safely using Regex to find JSON arrays."""
        try:
            # Search for anything between [ and ] including newlines
            match = re.search(r"\[.*\]", response, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return []
        except (json.JSONDecodeError, AttributeError):
            return []
