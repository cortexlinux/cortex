"""
Cortex Intent-Based Matching Engine
Matches user queries to stacks using intent + language detection.

Matching Strategy:
1. Parse query into tokens
2. Detect language (python, nodejs, go, etc.)
3. Detect intent (web-backend, machine-learning, etc.)
4. Filter stacks by language + intent
5. Score remaining stacks by keyword relevance
6. Return sorted results

Examples:
- "python web" -> language=python, intent=web-backend -> Python Django, FastAPI, Flask
- "docker" -> intent=containerization -> Docker Standard, Docker Dev, Docker GPU
- "python fastapi" -> language=python, keyword=fastapi -> Python FastAPI Stack
"""

import re
from typing import Optional

from .database import SuggestionDatabase
from .hardware_detection import detect_quick


class IntentMatcher:
    """
    Intent-based matching engine for stack suggestions.

    Scoring Priority:
    1. Exact stack ID match: "docker-standard" -> docker-standard (1000)
    2. Intent + Language match: "python web" -> python web stacks (500 + keyword bonus)
    3. Language-only match: "python" -> all python stacks (300 + keyword bonus)
    4. Intent-only match: "web backend" -> all web-backend stacks (300 + keyword bonus)
    5. Keyword match: "fastapi" -> stacks with fastapi keyword (100 + relevance)
    6. Fuzzy match: "dokcer" -> docker stacks (50 * similarity)
    """

    # Score constants
    SCORE_EXACT_ID = 1000
    SCORE_INTENT_LANGUAGE = 500
    SCORE_LANGUAGE_ONLY = 300
    SCORE_INTENT_ONLY = 300
    SCORE_KEYWORD_EXACT = 100
    SCORE_KEYWORD_PARTIAL = 50
    SCORE_FUZZY = 25

    # Bonuses
    BONUS_COMPLEXITY_LOW = 10
    BONUS_GPU_AVAILABLE = 5

    # Stop words to ignore
    STOP_WORDS = {
        "for",
        "with",
        "and",
        "the",
        "a",
        "an",
        "to",
        "in",
        "on",
        "of",
        "i",
        "want",
        "need",
        "install",
        "setup",
        "set",
        "up",
    }

    def __init__(self, db: SuggestionDatabase):
        self.db = db
        self._build_keyword_index()

    def _build_keyword_index(self) -> None:
        """Build reverse index from keywords to stacks."""
        self._keyword_to_stacks: dict[str, list[str]] = {}

        for stack in self.db.stacks:
            stack_id = stack["id"]

            # Index by keywords
            for kw in stack.get("keywords", []):
                kw_lower = kw.lower()
                if kw_lower not in self._keyword_to_stacks:
                    self._keyword_to_stacks[kw_lower] = []
                self._keyword_to_stacks[kw_lower].append(stack_id)

            # Also index by stack name words
            name_words = stack.get("name", "").lower().split()
            for word in name_words:
                if word not in self.STOP_WORDS and len(word) > 2:
                    if word not in self._keyword_to_stacks:
                        self._keyword_to_stacks[word] = []
                    if stack_id not in self._keyword_to_stacks[word]:
                        self._keyword_to_stacks[word].append(stack_id)

    def _tokenize(self, query: str) -> list[str]:
        """Tokenize and normalize query."""
        # Lowercase and split on whitespace/punctuation
        query = query.lower().strip()
        tokens = re.split(r"[\s\-_/,]+", query)

        # Filter out stop words and empty tokens
        tokens = [t for t in tokens if t and t not in self.STOP_WORDS]

        return tokens

    def _detect_context(self, tokens: list[str], full_query: str) -> tuple[str | None, str | None]:
        """
        Detect language and intent from tokens.

        Returns:
            Tuple of (language_id, intent_id)
        """
        language = self.db.detect_language_from_keywords(tokens)
        intent = self.db.detect_intent_from_keywords(tokens)

        # Also check the full query for multi-word matches
        if not intent:
            for intent_obj in self.db.intents:
                for kw in intent_obj.get("keywords", []):
                    if kw.lower() in full_query.lower():
                        intent = intent_obj["id"]
                        break
                if intent:
                    break

        return language, intent

    def _score_keyword_match(self, query_tokens: list[str], stack: dict) -> float:
        """Score how well query tokens match stack keywords."""
        score = 0.0
        stack_keywords = [kw.lower() for kw in stack.get("keywords", [])]
        stack_name = stack.get("name", "").lower()
        stack_desc = stack.get("description", "").lower()

        for token in query_tokens:
            # Exact keyword match
            if token in stack_keywords:
                score += 50
                continue

            # Keyword contains token
            for kw in stack_keywords:
                if token in kw:
                    score += 30
                    break
                if kw in token:
                    score += 25
                    break

            # Token in name
            if token in stack_name:
                score += 20

            # Token in description
            if token in stack_desc:
                score += 5

        return score

    def _fuzzy_match(self, query: str, target: str) -> float:
        """
        Simple fuzzy matching score.
        Returns value between 0 and 1.
        """
        if not query or not target:
            return 0.0

        query = query.lower()
        target = target.lower()

        if query == target:
            return 1.0

        if query in target or target in query:
            return 0.8

        # Check if query is a prefix
        if target.startswith(query):
            return 0.9

        # Character overlap score
        query_chars = set(query)
        target_chars = set(target)
        overlap = len(query_chars & target_chars)
        total = len(query_chars | target_chars)

        if total == 0:
            return 0.0

        return overlap / total * 0.5

    def match(self, query: str, limit: int = 10) -> list[dict]:
        """
        Match query to stacks using intent-based matching.

        Args:
            query: User's natural language query
            limit: Maximum number of results

        Returns:
            List of matched stacks with scores
        """
        if not query or not query.strip():
            return []

        query = query.strip()
        tokens = self._tokenize(query)

        if not tokens:
            return []

        # Detect hardware
        hw = detect_quick()
        has_gpu = hw.get("has_nvidia", False)

        # Detect language and intent
        language, intent = self._detect_context(tokens, query)

        # Collect candidate stacks with scores
        candidates: dict[str, float] = {}

        # Strategy 1: Exact stack ID match
        query_as_id = query.lower().replace(" ", "-")
        for token in tokens:
            stack = self.db.get_stack(token)
            if stack:
                candidates[token] = self.SCORE_EXACT_ID

        stack = self.db.get_stack(query_as_id)
        if stack:
            candidates[query_as_id] = self.SCORE_EXACT_ID

        # Strategy 2: Intent + Language match (highest priority for natural language)
        if language and intent:
            matching_stacks = self.db.get_stacks_by_intent_and_language(intent, language)
            for stack in matching_stacks:
                sid = stack["id"]
                score = self.SCORE_INTENT_LANGUAGE + self._score_keyword_match(tokens, stack)
                candidates[sid] = max(candidates.get(sid, 0), score)

        # Strategy 3: Language-only match
        elif language:
            matching_stacks = self.db.get_stacks_by_language(language)
            for stack in matching_stacks:
                sid = stack["id"]
                score = self.SCORE_LANGUAGE_ONLY + self._score_keyword_match(tokens, stack)
                candidates[sid] = max(candidates.get(sid, 0), score)

        # Strategy 4: Intent-only match
        elif intent:
            matching_stacks = self.db.get_stacks_by_intent(intent)
            for stack in matching_stacks:
                sid = stack["id"]
                score = self.SCORE_INTENT_ONLY + self._score_keyword_match(tokens, stack)
                candidates[sid] = max(candidates.get(sid, 0), score)

        # Strategy 5: Keyword matching (always run to catch specific terms)
        for token in tokens:
            if token in self._keyword_to_stacks:
                for sid in self._keyword_to_stacks[token]:
                    stack = self.db.get_stack(sid)
                    if stack:
                        score = self.SCORE_KEYWORD_EXACT + self._score_keyword_match(tokens, stack)
                        candidates[sid] = max(candidates.get(sid, 0), score)

            # Partial keyword match
            for kw, stack_ids in self._keyword_to_stacks.items():
                if token in kw or kw in token:
                    for sid in stack_ids:
                        if sid not in candidates:
                            stack = self.db.get_stack(sid)
                            if stack:
                                score = self.SCORE_KEYWORD_PARTIAL + self._score_keyword_match(
                                    tokens, stack
                                )
                                candidates[sid] = max(candidates.get(sid, 0), score)

        # Strategy 6: Fuzzy matching on stack IDs, names, AND keywords (fallback)
        # Always run fuzzy matching to catch typos like "mongodo" -> "mongodb"
        for stack in self.db.stacks:
            sid = stack["id"]
            if sid in candidates:
                continue

            fuzzy_score = 0.0

            for token in tokens:
                # Fuzzy match on ID
                id_fuzzy = self._fuzzy_match(token, sid)
                fuzzy_score = max(fuzzy_score, id_fuzzy)

                # Fuzzy match on name
                name_fuzzy = self._fuzzy_match(token, stack.get("name", ""))
                fuzzy_score = max(fuzzy_score, name_fuzzy)

                # Fuzzy match on keywords (catches typos like "mongodo" matching "mongodb")
                for kw in stack.get("keywords", []):
                    kw_fuzzy = self._fuzzy_match(token, kw)
                    fuzzy_score = max(fuzzy_score, kw_fuzzy)

            if fuzzy_score > 0.4:
                score = self.SCORE_FUZZY * fuzzy_score + self._score_keyword_match(tokens, stack)
                candidates[sid] = max(candidates.get(sid, 0), score)

        # Apply bonuses and filter
        results = []
        for sid, score in candidates.items():
            stack = self.db.get_stack(sid)
            if not stack:
                continue

            # Filter out GPU-required stacks if no GPU
            if stack.get("requires_gpu") and not has_gpu:
                continue

            # Complexity bonus (prefer simpler stacks)
            if stack.get("complexity") == "low":
                score += self.BONUS_COMPLEXITY_LOW

            # GPU bonus if available
            if has_gpu and stack.get("gpu_vendor") == "nvidia":
                score += self.BONUS_GPU_AVAILABLE

            results.append(
                {
                    "type": "stack",
                    "id": sid,
                    "name": stack.get("name", sid),
                    "description": stack.get("description", ""),
                    "score": score,
                    "requires_gpu": stack.get("requires_gpu", False),
                    "complexity": stack.get("complexity", "medium"),
                    "language": stack.get("language"),
                    "intents": stack.get("intents", []),
                    "data": stack,
                }
            )

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)

        return results[:limit]

    def get_install_preview(self, item_type: str, item_id: str) -> dict:
        """Get installation preview for a stack."""
        stack = self.db.get_stack(item_id)
        if not stack:
            return {"error": f"Stack {item_id} not found"}

        apt_packages = stack.get("apt_packages", [])
        pip_packages = stack.get("pip_packages", [])
        npm_packages = stack.get("npm_packages", [])
        post_install = stack.get("post_install", [])

        commands = []
        if apt_packages:
            commands.append(f"sudo apt update && sudo apt install -y {' '.join(apt_packages)}")
        if pip_packages:
            commands.append(f"pip install {' '.join(pip_packages)}")
        if npm_packages:
            commands.append(f"npm install -g {' '.join(npm_packages)}")

        return {
            "name": stack.get("name"),
            "description": stack.get("description"),
            "apt_packages": apt_packages,
            "pip_packages": pip_packages,
            "npm_packages": npm_packages,
            "post_install": post_install,
            "commands": commands,
            "command": " && ".join(commands) if commands else None,
            "llm_context": stack.get("llm_context", ""),
            "complexity": stack.get("complexity", "medium"),
            "use_cases": stack.get("use_cases", []),
            "recommended_with": stack.get("recommended_with", []),
        }


# Backward compatibility alias
FuzzyMatcher = IntentMatcher
