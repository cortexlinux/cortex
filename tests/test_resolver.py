"""
Unit tests for the DependencyResolver module.
"""

import pytest

from cortex.resolver import DependencyResolver


class TestDependencyResolver:
    """Test suite for DependencyResolver."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = DependencyResolver()

    def test_basic_conflict_resolution(self):
        """
        Test basic conflict resolution with valid semantic versions.
        Should return two strategies with Recommended updating pkg-b.
        """
        conflict_data = {
            "package_a": "pkg-a",
            "package_b": "pkg-b",
            "dependency": "libfoo",
            "version_a": ">=1.0.0,<2.0.0",
            "version_b": ">=1.5.0,<3.0.0",
        }

        strategies = self.resolver.resolve(conflict_data)

        # Should return two strategies
        assert len(strategies) == 2

        # First strategy should be Recommended "Smart Upgrade"
        assert strategies[0]["strategy"] == "Recommended"
        assert strategies[0]["action"] == "Smart Upgrade"
        assert "pkg-b" in strategies[0]["details"]["description"]
        assert strategies[0]["details"]["target"] == "pkg-b"

        # Second strategy should be Alternative "Conservative Downgrade"
        assert strategies[1]["strategy"] == "Alternative"
        assert strategies[1]["action"] == "Conservative Downgrade"

        # Verify details contain expected information
        for strategy in strategies:
            assert strategy["details"]["package_a"] == "pkg-a"
            assert strategy["details"]["package_b"] == "pkg-b"
            assert strategy["details"]["dependency"] == "libfoo"
            assert "recommendation" in strategy["details"]

    def test_missing_keys_raises_keyerror(self):
        """
        Test that missing required keys raise KeyError.
        """
        # Missing package_b
        conflict_data = {"package_a": "pkg-a", "dependency": "libfoo"}

        with pytest.raises(KeyError) as exc_info:
            self.resolver.resolve(conflict_data)

        assert "package_b" in str(exc_info.value)

        # Missing dependency
        conflict_data = {"package_a": "pkg-a", "package_b": "pkg-b"}

        with pytest.raises(KeyError) as exc_info:
            self.resolver.resolve(conflict_data)

        assert "dependency" in str(exc_info.value)

        # Missing package_a
        conflict_data = {"package_b": "pkg-b", "dependency": "libfoo"}

        with pytest.raises(KeyError) as exc_info:
            self.resolver.resolve(conflict_data)

        assert "package_a" in str(exc_info.value)

    def test_invalid_semver_produces_error_strategy(self):
        """
        Test that invalid semantic version produces an Error strategy
        indicating manual resolution is required.
        """
        conflict_data = {
            "package_a": "pkg-a",
            "package_b": "pkg-b",
            "dependency": "libfoo",
            "version_a": "not-a-valid-version",
            "version_b": ">=1.5.0",
        }

        strategies = self.resolver.resolve(conflict_data)

        # Should return one error strategy
        assert len(strategies) == 1
        assert strategies[0]["strategy"] == "Error"
        assert strategies[0]["action"] == "Manual resolution required"

        # Should contain error details
        details = strategies[0]["details"]
        assert "error" in details
        assert "Invalid semantic version" in details["error"]
        assert details["package_a"] == "pkg-a"
        assert details["package_b"] == "pkg-b"
        assert details["dependency"] == "libfoo"
        assert "recommendation" in details

    def test_resolution_with_default_version(self):
        """
        Test conflict resolution when version constraints are not provided.
        Should default to '*' (any version).
        """
        conflict_data = {
            "package_a": "pkg-a",
            "package_b": "pkg-b",
            "dependency": "libfoo",
            # No version_a or version_b specified
        }

        strategies = self.resolver.resolve(conflict_data)

        # Should still return two strategies
        assert len(strategies) == 2
        assert strategies[0]["strategy"] == "Recommended"
        assert strategies[1]["strategy"] == "Alternative"

    def test_complex_version_constraints(self):
        """
        Test resolution with complex version constraints.
        """
        conflict_data = {
            "package_a": "pkg-a",
            "package_b": "pkg-b",
            "dependency": "libfoo",
            "version_a": ">=2.0.0,<3.0.0",
            "version_b": ">=2.5.0,<=2.8.0",
        }

        strategies = self.resolver.resolve(conflict_data)

        # Should successfully parse and return two strategies
        assert len(strategies) == 2
        assert strategies[0]["strategy"] == "Recommended"
        assert strategies[1]["strategy"] == "Alternative"

        # Verify version constraints are preserved in details
        assert strategies[0]["details"]["version_a"] == ">=2.0.0,<3.0.0"
        assert strategies[0]["details"]["version_b"] == ">=2.5.0,<=2.8.0"

    def test_wildcard_version(self):
        """
        Test resolution with wildcard version constraints.
        """
        conflict_data = {
            "package_a": "pkg-a",
            "package_b": "pkg-b",
            "dependency": "libfoo",
            "version_a": "*",
            "version_b": ">=1.0.0",
        }

        strategies = self.resolver.resolve(conflict_data)

        # Should successfully parse wildcard and return two strategies
        assert len(strategies) == 2
        assert strategies[0]["strategy"] == "Recommended"
        assert strategies[1]["strategy"] == "Alternative"

    def test_major_version_conflict(self):
        """
        Test resolution when there's a major version conflict.
        """
        conflict_data = {
            "package_a": "pkg-a",
            "package_b": "pkg-b",
            "dependency": "libfoo",
            "version_a": ">=1.0.0,<2.0.0",
            "version_b": ">=2.0.0,<3.0.0",
        }

        strategies = self.resolver.resolve(conflict_data)

        # Should still provide strategies even for major version conflicts
        assert len(strategies) == 2
        assert strategies[0]["strategy"] == "Recommended"
        assert strategies[1]["strategy"] == "Alternative"

    def test_recommended_strategy_targets_package_b(self):
        """
        Verify that the Recommended strategy specifically targets pkg-b for update.
        """
        conflict_data = {
            "package_a": "pkg-a",
            "package_b": "pkg-b",
            "dependency": "libfoo",
            "version_a": ">=1.0.0",
            "version_b": ">=2.0.0",
        }

        strategies = self.resolver.resolve(conflict_data)

        recommended = strategies[0]
        assert recommended["strategy"] == "Recommended"
        assert recommended["details"]["target"] == "pkg-b"
        assert "pkg-b" in recommended["details"]["description"].lower()

    def test_alternative_strategy_targets_dependency(self):
        """
        Verify that the Alternative strategy targets the dependency itself.
        """
        conflict_data = {
            "package_a": "pkg-a",
            "package_b": "pkg-b",
            "dependency": "libfoo",
            "version_a": ">=1.0.0",
            "version_b": ">=2.0.0",
        }

        strategies = self.resolver.resolve(conflict_data)

        alternative = strategies[1]
        assert alternative["strategy"] == "Alternative"
        assert alternative["details"]["target"] == "libfoo"
        assert "libfoo" in alternative["details"]["description"].lower()
