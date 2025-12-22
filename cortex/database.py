"""
Cortex Intent-Based Suggestion Database Loader
Loads and manages the suggestions.json database with intent + language matching.
"""

import json
from pathlib import Path
from typing import Any, Optional


class SuggestionDatabase:
    """
    Loads and manages the intent-based suggestion database.

    The database contains:
    - intents: Use-case categories (web-backend, machine-learning, etc.)
    - languages: Programming languages with base packages
    - stacks: Curated bundles of packages for specific use cases
    - packages: Individual apt package references
    - aliases: Shorthand mappings to intents
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or self._find_database()
        self._data: dict[str, Any] = {}
        self._intents: list[dict] = []
        self._languages: list[dict] = []
        self._stacks: list[dict] = []
        self._packages: list[dict] = []
        self._aliases: dict[str, list[str]] = {}
        self._load()
        self._build_indexes()

    def _find_database(self) -> str:
        """Find the suggestions.json database file."""
        search_paths = [
            Path(__file__).parent.parent / "data" / "suggestions.json",
            Path(__file__).parent / "data" / "suggestions.json",
            Path.home() / ".cortex" / "suggestions.json",
            Path("/usr/share/cortex/suggestions.json"),
            Path("/etc/cortex/suggestions.json"),
            # Fallback to old packages.json for backward compatibility
            Path(__file__).parent.parent / "data" / "packages.json",
        ]
        for p in search_paths:
            if p.exists():
                return str(p)
        raise FileNotFoundError("suggestions.json not found in any standard location")

    def _load(self) -> None:
        """Load the database from JSON file."""
        with open(self.db_path) as f:
            self._data = json.load(f)

        self._intents = self._data.get("intents", [])
        self._languages = self._data.get("languages", [])
        self._stacks = self._data.get("stacks", [])
        self._packages = self._data.get("packages", [])
        self._aliases = self._data.get("aliases", {})

    def _build_indexes(self) -> None:
        """Build lookup indexes for fast access."""
        # Intent keyword index
        self._intent_keywords: dict[str, str] = {}  # keyword -> intent_id
        for intent in self._intents:
            for kw in intent.get("keywords", []):
                self._intent_keywords[kw.lower()] = intent["id"]

        # Language keyword index
        self._language_keywords: dict[str, str] = {}  # keyword -> language_id
        for lang in self._languages:
            for kw in lang.get("keywords", []):
                self._language_keywords[kw.lower()] = lang["id"]

        # Stack indexes
        self._stacks_by_id: dict[str, dict] = {s["id"]: s for s in self._stacks}
        self._stacks_by_intent: dict[str, list[dict]] = {}
        self._stacks_by_language: dict[str, list[dict]] = {}

        for stack in self._stacks:
            # Index by intent
            for intent in stack.get("intents", []):
                if intent not in self._stacks_by_intent:
                    self._stacks_by_intent[intent] = []
                self._stacks_by_intent[intent].append(stack)

            # Index by language
            lang = stack.get("language")
            if lang:
                if lang not in self._stacks_by_language:
                    self._stacks_by_language[lang] = []
                self._stacks_by_language[lang].append(stack)

        # Package index
        self._packages_by_id: dict[str, dict] = {p["id"]: p for p in self._packages}

    # === Properties ===

    @property
    def intents(self) -> list[dict]:
        return self._intents

    @property
    def languages(self) -> list[dict]:
        return self._languages

    @property
    def stacks(self) -> list[dict]:
        return self._stacks

    @property
    def packages(self) -> list[dict]:
        return self._packages

    @property
    def aliases(self) -> dict[str, list[str]]:
        return self._aliases

    # === Lookup Methods ===

    def get_intent(self, intent_id: str) -> dict | None:
        """Get an intent by its ID."""
        for intent in self._intents:
            if intent["id"] == intent_id:
                return intent
        return None

    def get_language(self, lang_id: str) -> dict | None:
        """Get a language by its ID."""
        for lang in self._languages:
            if lang["id"] == lang_id:
                return lang
        return None

    def get_stack(self, stack_id: str) -> dict | None:
        """Get a stack by its ID."""
        return self._stacks_by_id.get(stack_id)

    def get_package(self, pkg_id: str) -> dict | None:
        """Get a package by its ID."""
        return self._packages_by_id.get(pkg_id)

    # === Detection Methods ===

    def detect_intent_from_keywords(self, tokens: list[str]) -> str | None:
        """
        Detect intent from query tokens.

        Priority:
        1. Multi-word intent keywords in full query (most specific)
        2. Specific intent keywords (ml, docker, kubernetes) - not ambiguous
        3. Aliases for non-language tokens
        4. Fallback to ambiguous tokens
        """
        query = " ".join(tokens)

        # First pass: check multi-word intent keywords (highest specificity)
        # e.g., "machine learning", "deep learning", "data engineering"
        for intent in self._intents:
            for kw in intent.get("keywords", []):
                # Only check multi-word keywords
                if " " in kw and kw.lower() in query:
                    return intent["id"]

        # Second pass: check multi-word aliases
        for alias, intent_ids in self._aliases.items():
            if " " in alias and alias.lower() in query:
                return intent_ids[0]

        # Third pass: check single-token intent keywords (not ambiguous with languages)
        for token in tokens:
            if token in self._intent_keywords:
                if token not in self._language_keywords:
                    return self._intent_keywords[token]

        # Fourth pass: check single-token aliases (not ambiguous with languages)
        for token in tokens:
            if token in self._aliases:
                if token not in self._language_keywords:
                    return self._aliases[token][0]

        # Fifth pass: check remaining intent keywords (including ambiguous ones)
        for token in tokens:
            if token in self._intent_keywords:
                return self._intent_keywords[token]

        # Sixth pass: fallback to aliases (including language tokens)
        for token in tokens:
            if token in self._aliases:
                return self._aliases[token][0]

        return None

    def detect_language_from_keywords(self, tokens: list[str]) -> str | None:
        """Detect language from query tokens."""
        for token in tokens:
            if token in self._language_keywords:
                return self._language_keywords[token]
        return None

    # === Filtering Methods ===

    def get_stacks_by_intent(self, intent_id: str) -> list[dict]:
        """Get all stacks for a given intent."""
        return self._stacks_by_intent.get(intent_id, [])

    def get_stacks_by_language(self, lang_id: str) -> list[dict]:
        """Get all stacks for a given language."""
        return self._stacks_by_language.get(lang_id, [])

    def get_stacks_by_intent_and_language(self, intent_id: str, lang_id: str) -> list[dict]:
        """Get stacks matching both intent and language."""
        intent_stacks = {s["id"] for s in self.get_stacks_by_intent(intent_id)}
        lang_stacks = {s["id"] for s in self.get_stacks_by_language(lang_id)}
        matching_ids = intent_stacks & lang_stacks
        return [self._stacks_by_id[sid] for sid in matching_ids]

    def filter_gpu_stacks(
        self, stacks: list[dict], has_gpu: bool = True, vendor: str = "nvidia"
    ) -> list[dict]:
        """Filter stacks by GPU requirements."""
        if has_gpu:
            return [s for s in stacks if not s.get("requires_gpu") or s.get("gpu_vendor") == vendor]
        return [s for s in stacks if not s.get("requires_gpu")]

    # === APT Package Methods ===

    def get_apt_packages_for_stack(self, stack_id: str) -> list[str]:
        """Get all apt packages needed for a stack."""
        stack = self.get_stack(stack_id)
        if not stack:
            return []
        return stack.get("apt_packages", [])

    def get_pip_packages_for_stack(self, stack_id: str) -> list[str]:
        """Get all pip packages needed for a stack."""
        stack = self.get_stack(stack_id)
        if not stack:
            return []
        return stack.get("pip_packages", [])

    def get_apt_packages(self, pkg_id: str) -> list[str]:
        """Get the apt package names for a package ID."""
        pkg = self.get_package(pkg_id)
        if pkg:
            return pkg.get("apt", [])
        return []

    # === Backward Compatibility Methods ===

    def get_all_apt_for_stack(self, stack_id: str) -> list[str]:
        """Backward compatible method for getting apt packages."""
        return self.get_apt_packages_for_stack(stack_id)

    @property
    def categories(self) -> list[dict]:
        """Backward compatible property - returns intents as categories."""
        return self._intents


# Backward compatibility alias
PackageDatabase = SuggestionDatabase
