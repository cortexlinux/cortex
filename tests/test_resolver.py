import unittest
from cortex.resolver import DependencyResolver


class TestDependencyResolver(unittest.TestCase):
    """Unit tests for DependencyResolver conflict resolution logic."""

    def setUp(self) -> None:
        """Initialize a DependencyResolver instance for each test."""
        self.resolver: DependencyResolver = DependencyResolver()

    def test_basic_conflict_resolution(self) -> None:
        """Test basic conflict resolution returns expected strategies."""
        conflict = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "^2.0.0"},
            "package_b": {"name": "pkg-b", "requires": "~1.9.0"}
        }
        strategies = self.resolver.resolve(conflict)
        self.assertEqual(len(strategies), 2)
        self.assertEqual(strategies[0]['type'], "Recommended")

    def test_risk_calculation_low(self) -> None:
        """Test that risk is Low when no major version breaking changes exist."""
        conflict = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "^2.0.0"},
            "package_b": {"name": "pkg-b", "requires": "2.5.0"}
        }
        strategies = self.resolver.resolve(conflict)
        self.assertEqual(
            strategies[0]['risk'], 
            "Low (no breaking changes detected)"
        )

    def test_complex_constraint_formats(self) -> None:
        """Test various semver constraint syntaxes for parser stability."""
        test_cases = [
            {"req_a": "==2.0.0", "req_b": "2.1.0"},
            {"req_a": ">=1.0.0", "req_b": "1.5.0"},
            {"req_a": "~1.2.3", "req_b": "1.2.0"},
        ]
        for case in test_cases:
            conflict = {
                "dependency": "lib-y",
                "package_a": {"name": "pkg-a", "requires": case["req_a"]},
                "package_b": {"name": "pkg-b", "requires": case["req_b"]}
            }
            strategies = self.resolver.resolve(conflict)
            self.assertNotEqual(strategies[0]['type'], "Error")

    def test_strategy_field_integrity(self) -> None:
        """Verify all required fields exist in the resolution strategies."""
        conflict = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "^2.0.0"},
            "package_b": {"name": "pkg-b", "requires": "~1.9.0"}
        }
        strategies = self.resolver.resolve(conflict)
        for strategy in strategies:
            for field in ['id', 'type', 'action', 'risk']:
                self.assertIn(field, strategy)

    def test_missing_keys_raises_error(self) -> None:
        """Test that KeyError is raised when top-level keys are missing."""
        bad_data = {"package_a": {}}
        with self.assertRaises(KeyError):
            self.resolver.resolve(bad_data)

    def test_invalid_semver_handles_gracefully(self) -> None:
        """Test that invalid semver strings trigger the Error strategy."""
        conflict = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "not-a-version"},
            "package_b": {"name": "pkg-b", "requires": "1.0.0"}
        }
        strategies = self.resolver.resolve(conflict)
        self.assertEqual(strategies[0]['type'], "Error")