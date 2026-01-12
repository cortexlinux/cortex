"""
Lesson Loader Tool - Deterministic tool for loading cached lesson content.

This tool does NOT use LLM calls - it retrieves pre-generated lessons from cache.
"""

from pathlib import Path
from typing import Any

from langchain.tools import BaseTool
from pydantic import Field

from cortex.tutor.config import get_config
from cortex.tutor.contracts.lesson_context import LessonContext
from cortex.tutor.memory.sqlite_store import SQLiteStore


class LessonLoaderTool(BaseTool):
    """
    Deterministic tool for loading cached lesson content.

    This tool retrieves lessons from SQLite cache without LLM calls.
    It is fast, free, and should be checked before generating new lessons.
    """

    name: str = "lesson_loader"
    description: str = (
        "Load cached lesson content for a package. "
        "Use this before generating new lessons to save cost. "
        "Returns None if no valid cache exists."
    )

    store: SQLiteStore | None = Field(default=None, exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, db_path: Path | None = None) -> None:
        """
        Initialize the lesson loader tool.

        Args:
            db_path: Path to SQLite database. Uses config default if not provided.
        """
        super().__init__()
        if db_path is None:
            config = get_config()
            db_path = config.get_db_path()
        self.store = SQLiteStore(db_path)

    def _run(
        self,
        package_name: str,
        force_fresh: bool = False,
    ) -> dict[str, Any]:
        """
        Load cached lesson content.

        Args:
            package_name: Name of the package to load lesson for.
            force_fresh: If True, skip cache and return cache miss.

        Returns:
            Dict with cached lesson or cache miss indicator.
        """
        if force_fresh:
            return {
                "success": True,
                "cache_hit": False,
                "lesson": None,
                "reason": "Force fresh requested",
            }

        try:
            cached = self.store.get_cached_lesson(package_name)

            if cached:
                return {
                    "success": True,
                    "cache_hit": True,
                    "lesson": cached,
                    "cost_saved_gbp": 0.02,  # Estimated LLM cost saved
                }

            return {
                "success": True,
                "cache_hit": False,
                "lesson": None,
                "reason": "No valid cache found",
            }

        except Exception as e:
            return {
                "success": False,
                "cache_hit": False,
                "lesson": None,
                "error": str(e),
            }

    async def _arun(
        self,
        package_name: str,
        force_fresh: bool = False,
    ) -> dict[str, Any]:
        """Async version - delegates to sync implementation."""
        return self._run(package_name, force_fresh)

    def cache_lesson(
        self,
        package_name: str,
        lesson: dict[str, Any],
        ttl_hours: int = 24,
    ) -> bool:
        """
        Cache a lesson for future retrieval.

        Args:
            package_name: Name of the package.
            lesson: Lesson content to cache.
            ttl_hours: Time-to-live in hours.

        Returns:
            True if cached successfully.
        """
        try:
            self.store.cache_lesson(package_name, lesson, ttl_hours)
            return True
        except Exception:
            return False

    def clear_cache(self, package_name: str | None = None) -> int:
        """
        Clear cached lessons.

        Args:
            package_name: Specific package to mark as expired (makes it
                unretrievable via get_cached_lesson). If None, removes
                only already-expired entries from the database.

        Returns:
            int: For specific package - 1 if marked as expired, 0 on error.
                 For None - number of expired entries actually deleted.

        Note:
            When package_name is provided, this marks the entry as expired
            by calling cache_lesson with ttl_hours=0, rather than deleting it.
            The entry persists until clear_expired_cache() runs.
        """
        if package_name:
            # Mark specific package as expired by caching empty with 0 TTL
            try:
                self.store.cache_lesson(package_name, {}, ttl_hours=0)
                return 1
            except Exception:
                return 0
        else:
            return self.store.clear_expired_cache()


# Pre-built lesson templates for common packages
# These can be used as fallbacks when LLM is unavailable

FALLBACK_LESSONS = {
    "docker": {
        "package_name": "docker",
        "summary": "Docker is a containerization platform for packaging and running applications.",
        "explanation": (
            "Docker enables you to package applications with their dependencies into "
            "standardized units called containers. Containers are lightweight, portable, "
            "and isolated from the host system, making deployment consistent across environments."
        ),
        "use_cases": [
            "Development environment consistency",
            "Microservices deployment",
            "CI/CD pipelines",
            "Application isolation",
        ],
        "best_practices": [
            "Use official base images when possible",
            "Keep images small with multi-stage builds",
            "Never store secrets in images",
            "Use .dockerignore to exclude unnecessary files",
        ],
        "installation_command": "apt install docker.io",
        "confidence": 0.7,  # Lower confidence for fallback
    },
    "git": {
        "package_name": "git",
        "summary": "Git is a distributed version control system for tracking code changes.",
        "explanation": (
            "Git tracks changes to files over time, allowing you to recall specific versions "
            "later. It supports collaboration through branching, merging, and remote repositories."
        ),
        "use_cases": [
            "Source code version control",
            "Team collaboration",
            "Code review workflows",
            "Release management",
        ],
        "best_practices": [
            "Write clear, descriptive commit messages",
            "Use feature branches for new work",
            "Pull before push to avoid conflicts",
            "Review changes before committing",
        ],
        "installation_command": "apt install git",
        "confidence": 0.7,
    },
    "nginx": {
        "package_name": "nginx",
        "summary": "Nginx is a high-performance web server and reverse proxy.",
        "explanation": (
            "Nginx (pronounced 'engine-x') is known for its high performance, stability, "
            "and low resource consumption. It can serve static content, act as a reverse proxy, "
            "and handle load balancing."
        ),
        "use_cases": [
            "Static file serving",
            "Reverse proxy for applications",
            "Load balancing",
            "SSL/TLS termination",
        ],
        "best_practices": [
            "Use separate config files for each site",
            "Enable gzip compression",
            "Configure proper caching headers",
            "Set up SSL with strong ciphers",
        ],
        "installation_command": "apt install nginx",
        "confidence": 0.7,
    },
}


def get_fallback_lesson(package_name: str) -> dict[str, Any] | None:
    """
    Get a fallback lesson template for common packages.

    Args:
        package_name: Name of the package.

    Returns:
        Fallback lesson dict or None.
    """
    return FALLBACK_LESSONS.get(package_name.lower())


def load_lesson_with_fallback(
    package_name: str,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """
    Load lesson from cache with fallback to templates.

    Args:
        package_name: Name of the package.
        db_path: Optional database path.

    Returns:
        Lesson content dict.
    """
    loader = LessonLoaderTool(db_path)
    result = loader._run(package_name)

    if result.get("cache_hit") and result.get("lesson"):
        return {
            "source": "cache",
            "lesson": result["lesson"],
            "cost_saved_gbp": result.get("cost_saved_gbp", 0),
        }

    fallback = get_fallback_lesson(package_name)
    if fallback:
        return {
            "source": "fallback_template",
            "lesson": fallback,
            "cost_saved_gbp": 0.02,
        }

    return {
        "source": "none",
        "lesson": None,
        "needs_generation": True,
    }
