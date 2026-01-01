"""
Semantic Version Conflict Resolver Module.
Handles dependency version conflicts using AI-driven intelligent analysis.
"""

import json
import logging

import semantic_version as sv

from cortex.ask import AskHandler

logger = logging.getLogger(__name__)


class DependencyResolver:
    """
    AI-powered semantic version conflict resolver.
    """

    def __init__(self, api_key: str | None = None, provider: str = "ollama"):
        """
        Initialize the resolver with the AskHandler for reasoning.

        Args:
            api_key: API key for the provider.
            provider: LLM provider (default: "ollama").
        """
        # Architectural Fix: Using AskHandler instead of CommandInterpreter
        # to ensure semantic reasoning instead of shell commands.
        self.handler = AskHandler(
            api_key=api_key or "ollama",
            provider=provider,
        )

    async def resolve(self, conflict_data: dict) -> list[dict]:
        """
        Resolve semantic version conflicts using deterministic analysis and AI.

        Args:
            conflict_data: Dict with 'package_a', 'package_b', 'dependency'.

        Returns:
            list[dict]: List of strategy dictionaries.

        Raises:
            KeyError: If required keys are missing from conflict_data.
        """
        required_keys = ["package_a", "package_b", "dependency"]
        for key in required_keys:
            if key not in conflict_data:
                raise KeyError(f"Missing required key: {key}")

        # 1. Deterministic resolution first (Reliable & Fast)
        strategies = self._deterministic_resolution(conflict_data)
        if strategies and strategies[0].get("risk") == "Low":
            return strategies

        # 2. AI Reasoning fallback using AskHandler
        prompt = self._build_prompt(conflict_data)
        try:
            # Note: AskHandler.ask is currently treated as synchronous.
            response = self.handler.ask(prompt)
            return self._parse_ai_response(response, conflict_data)
        except Exception as e:
            logger.error(f"AI Resolution failed: {e}")
            return strategies or [
                {
                    "id": 0,
                    "type": "Error",
                    "action": f"Manual resolution required: {e}",
                    "risk": "High",
                }
            ]

    def _deterministic_resolution(self, data: dict) -> list[dict]:
        """
        Perform semantic-version constraint analysis safely.

        Args:
            data: Dict containing conflict information.

        Returns:
            list[dict]: List of deterministic strategies.
        """
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

            # Ensure specs have at least one clause before accessing to avoid IndexError
            if not a_req.specs or not b_req.specs:
                logger.debug("Specs have no clauses, skipping deterministic resolution")
                return []

            # Safe access to handle cases where 'version' or 'major' might be missing
            a_spec = a_req.specs[0]
            a_major = getattr(getattr(a_spec, "version", object()), "major", 0)

            # Formatting Fix: Split long lines to stay under 79 chars (PEP 8)
            return [
                {
                    "id": 1,
                    "type": "Recommended",
                    "action": (
                        f"Upgrade {data['package_b']['name']} to "
                        f"support {dependency} ^{a_major}.0.0"
                    ),
                    "risk": "Medium",
                }
            ]
        except Exception as e:
            logger.debug(f"Deterministic resolution skipped: {e}")
            return []

    def _build_prompt(self, data: dict) -> str:
        """Constructs a prompt for direct JSON response."""
        return (
            f"Act as a DevOps Engineer. Analyze this conflict: "
            f"{data['dependency']}. "
            f"Package A: {data['package_a']['name']} "
            f"({data['package_a']['requires']}). "
            f"Package B: {data['package_b']['name']} "
            f"({data['package_b']['requires']}). "
            "Return ONLY a JSON array of objects with keys: "
            "id, type, action, risk."
        )

    def _parse_ai_response(self, response: str, data: dict) -> list[dict]:
        """Parses the LLM output safely."""
        try:
            start = response.find("[")
            end = response.rfind("]") + 1
            if start != -1 and end != 0:
                return json.loads(response[start:end])
            raise ValueError("No JSON array found")
        except Exception:
            # Fragile JSON parsing with unsafe fallback.
            # Falling back to deterministic resolution if parsing fails.
            return self._deterministic_resolution(data)
