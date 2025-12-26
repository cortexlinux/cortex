import unittest
from cortex.resolver import DependencyResolver

class TestDependencyResolver(unittest.TestCase):
    def setUp(self):
        """
        Create a fresh DependencyResolver instance and assign it to self.resolver for use by each test.
        """
        self.resolver = DependencyResolver()

    def test_basic_conflict_resolution(self):
        """
        Verifies that the resolver returns a recommended update strategy for a simple dependency conflict.
        
        Constructs a conflict between two packages depending on the same library, resolves it, and asserts that two strategies are returned, the first strategy is of type "Recommended", and its action suggests updating pkg-b.
        """
        conflict = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "^2.0.0"},
            "package_b": {"name": "pkg-b", "requires": "~1.9.0"}
        }
        strategies = self.resolver.resolve(conflict)
        
        self.assertEqual(len(strategies), 2)
        self.assertEqual(strategies[0]['type'], "Recommended")
        self.assertIn("Update pkg-b", strategies[0]['action'])

    def test_complex_constraint_formats(self):
        """
        Verify the resolver handles a variety of semantic-version constraint formats.
        
        Constructs conflict scenarios using different semver syntaxes and asserts that the DependencyResolver
        returns a non-empty list of resolution strategies for each case.
        """
        test_cases = [
            {"req_a": "==2.0.0", "req_b": "^2.1.0"},
            {"req_a": ">=1.0.0,<2.0.0", "req_b": "1.5.0"},
            {"req_a": "~1.2.3", "req_b": ">=1.2.0"},
        ]
        for case in test_cases:
            conflict = {
                "dependency": "lib-y",
                "package_a": {"name": "pkg-a", "requires": case["req_a"]},
                "package_b": {"name": "pkg-b", "requires": case["req_b"]}
            }
            strategies = self.resolver.resolve(conflict)
            self.assertIsInstance(strategies, list)
            self.assertGreater(len(strategies), 0)

    def test_strategy_field_integrity(self):
        """Verify all required fields (id, type, action, risk) exist in output."""
        conflict = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "^2.0.0"},
            "package_b": {"name": "pkg-b", "requires": "~1.9.0"}
        }
        strategies = self.resolver.resolve(conflict)
        for strategy in strategies:
            self.assertIn('id', strategy)
            self.assertIn('type', strategy)
            self.assertIn('action', strategy)
            self.assertIn('risk', strategy)

    def test_missing_keys_raises_error(self):
        bad_data = {"package_a": {}}
        with self.assertRaises(KeyError):
            self.resolver.resolve(bad_data)

    def test_invalid_semver_handles_gracefully(self):
        """
        Verify the resolver reports an error and recommends manual resolution when a package specifies an invalid semantic version.
        
        Asserts that the first resolution strategy has type "Error" and that its action message includes "Manual resolution required".
        """
        conflict = {
            "dependency": "lib-x",
            "package_a": {"name": "pkg-a", "requires": "invalid-version"},
            "package_b": {"name": "pkg-b", "requires": "1.0.0"}
        }
        strategies = self.resolver.resolve(conflict)
        self.assertEqual(strategies[0]['type'], "Error")
        self.assertIn("Manual resolution required", strategies[0]['action'])

if __name__ == "__main__":
    unittest.main()