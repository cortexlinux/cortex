"""
Tests for deterministic tools.

Tests for lesson_loader and progress_tracker.
"""

import tempfile
from pathlib import Path

import pytest

from cortex.tutor.tools import (
    FALLBACK_LESSONS,
    LessonLoaderTool,
    ProgressTrackerTool,
    get_fallback_lesson,
)


class TestLessonLoaderTool:
    """Tests for LessonLoaderTool."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test.db"

    def test_cache_miss(self, temp_db):
        """Test cache miss returns appropriate response."""
        loader = LessonLoaderTool(temp_db)
        result = loader._run("unknown_package")

        assert result["success"]
        assert not result["cache_hit"]

    def test_cache_and_retrieve(self, temp_db):
        """Test caching and retrieving a lesson."""
        loader = LessonLoaderTool(temp_db)

        lesson = {"package_name": "docker", "summary": "Test"}
        loader.cache_lesson("docker", lesson)

        result = loader._run("docker")
        assert result["cache_hit"]
        assert result["lesson"]["summary"] == "Test"

    def test_force_fresh(self, temp_db):
        """Test force_fresh skips cache."""
        loader = LessonLoaderTool(temp_db)
        loader.cache_lesson("docker", {"summary": "cached"})

        result = loader._run("docker", force_fresh=True)
        assert not result["cache_hit"]


class TestFallbackLessons:
    """Tests for fallback lessons."""

    def test_docker_fallback(self):
        """Test Docker fallback exists."""
        fallback = get_fallback_lesson("docker")
        assert fallback is not None
        assert fallback["package_name"] == "docker"

    def test_git_fallback(self):
        """Test Git fallback exists."""
        fallback = get_fallback_lesson("git")
        assert fallback is not None

    def test_nginx_fallback(self):
        """Test Nginx fallback exists."""
        fallback = get_fallback_lesson("nginx")
        assert fallback is not None

    def test_unknown_fallback(self):
        """Test unknown package returns None."""
        fallback = get_fallback_lesson("unknown_xyz")
        assert fallback is None

    def test_case_insensitive(self):
        """Test fallback lookup is case insensitive."""
        fallback = get_fallback_lesson("DOCKER")
        assert fallback is not None

    def test_all_fallbacks_have_required_fields(self):
        """Test all fallbacks have basic fields."""
        for package in FALLBACK_LESSONS:
            fallback = get_fallback_lesson(package)
            assert "package_name" in fallback
            assert "summary" in fallback


class TestProgressTrackerTool:
    """Tests for ProgressTrackerTool."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test.db"

    @pytest.fixture
    def tracker(self, temp_db):
        """Create a progress tracker."""
        return ProgressTrackerTool(temp_db)

    def test_update_progress(self, tracker):
        """Test update_progress action."""
        result = tracker._run(
            "update_progress",
            package_name="docker",
            topic="basics",
        )
        assert result["success"]

    def test_get_progress(self, tracker):
        """Test get_progress action."""
        tracker._run("update_progress", package_name="docker", topic="basics")
        result = tracker._run("get_progress", package_name="docker", topic="basics")

        assert result["success"]
        assert result["progress"]["package_name"] == "docker"

    def test_get_all_progress(self, tracker):
        """Test get_all_progress action."""
        tracker._run("update_progress", package_name="docker", topic="basics")
        result = tracker._run("get_all_progress")

        assert result["success"]
        assert len(result["progress"]) >= 1

    def test_mark_completed(self, tracker):
        """Test mark_completed action."""
        result = tracker._run(
            "mark_completed",
            package_name="docker",
            topic="basics",
            score=0.9,
        )
        assert result["success"]

    def test_get_stats(self, tracker):
        """Test get_stats action."""
        tracker._run("mark_completed", package_name="docker", topic="basics", score=0.8)
        result = tracker._run("get_stats", package_name="docker")

        assert result["success"]
        assert "stats" in result

    def test_get_profile(self, tracker):
        """Test get_profile action."""
        result = tracker._run("get_profile")

        assert result["success"]
        assert "learning_style" in result["profile"]

    def test_update_profile(self, tracker):
        """Test update_profile action."""
        result = tracker._run("update_profile", learning_style="visual")
        assert result["success"]

    def test_get_packages(self, tracker):
        """Test get_packages action."""
        tracker._run("update_progress", package_name="docker", topic="basics")
        result = tracker._run("get_packages")

        assert result["success"]
        assert "docker" in result["packages"]

    def test_invalid_action(self, tracker):
        """Test invalid action returns error."""
        result = tracker._run("invalid_action_xyz")

        assert not result["success"]
        assert "error" in result
