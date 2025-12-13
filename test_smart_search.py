#!/usr/bin/env python3
"""
Unit tests for Smart Package Search with Fuzzy Matching
"""

import unittest
import tempfile
import json
from pathlib import Path
from datetime import datetime

from smart_search import (
    SmartPackageSearch,
    PackageDatabase,
    PackageCategory,
    PackageInfo,
    SearchResult,
    SearchHistoryEntry,
    format_search_results
)


class TestPackageDatabase(unittest.TestCase):
    """Test cases for PackageDatabase."""

    def setUp(self):
        """Set up test fixtures."""
        self.db = PackageDatabase()

    def test_database_initialized(self):
        """Test that database is properly initialized."""
        self.assertIsNotNone(self.db.packages)
        self.assertGreater(len(self.db.packages), 0)

    def test_get_package(self):
        """Test getting package by name."""
        nginx = self.db.get_package("nginx")
        self.assertIsNotNone(nginx)
        self.assertEqual(nginx.name, "nginx")
        self.assertEqual(nginx.category, PackageCategory.WEB_SERVER)

    def test_get_nonexistent_package(self):
        """Test getting nonexistent package."""
        pkg = self.db.get_package("nonexistent")
        self.assertIsNone(pkg)

    def test_get_all_packages(self):
        """Test getting all packages."""
        packages = self.db.get_all_packages()
        self.assertIsInstance(packages, list)
        self.assertGreater(len(packages), 20)  # Should have many packages

    def test_get_by_category(self):
        """Test getting packages by category."""
        web_servers = self.db.get_by_category(PackageCategory.WEB_SERVER)
        self.assertIsInstance(web_servers, list)
        self.assertGreater(len(web_servers), 0)

        # All should be web servers
        for pkg in web_servers:
            self.assertEqual(pkg.category, PackageCategory.WEB_SERVER)

    def test_packages_have_metadata(self):
        """Test that packages have required metadata."""
        for pkg in self.db.get_all_packages():
            self.assertIsInstance(pkg, PackageInfo)
            self.assertTrue(pkg.name)
            self.assertTrue(pkg.display_name)
            self.assertTrue(pkg.description)
            self.assertIsInstance(pkg.category, PackageCategory)
            self.assertIsInstance(pkg.keywords, list)
            self.assertIsInstance(pkg.synonyms, list)


class TestSmartPackageSearch(unittest.TestCase):
    """Test cases for SmartPackageSearch."""

    def setUp(self):
        """Set up test fixtures."""
        # Use temporary file for history
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history_file = Path(self.temp_dir.name) / "test_history.json"
        self.search = SmartPackageSearch(history_file=self.history_file)

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_initialization(self):
        """Test search initialization."""
        self.assertIsNotNone(self.search.db)
        self.assertIsNotNone(self.search.history)
        self.assertEqual(self.search.history_file, self.history_file)

    def test_exact_match(self):
        """Test exact package name match."""
        results, suggestions = self.search.search("nginx")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].package.name, "nginx")
        self.assertEqual(results[0].match_type, "exact")
        self.assertGreater(results[0].score, 0.9)

    def test_typo_fuzzy_match(self):
        """Test fuzzy matching with typo."""
        # "postgress" is a common typo for "postgresql"
        results, suggestions = self.search.search("postgress")

        # Should either find postgresql or suggest it
        found_postgresql = any(r.package.name == "postgresql" for r in results)
        suggested_postgresql = "postgresql" in suggestions

        self.assertTrue(
            found_postgresql or suggested_postgresql,
            "Should find or suggest postgresql for 'postgress'"
        )

    def test_synonym_match(self):
        """Test synonym detection."""
        # "postgres" is a synonym for "postgresql"
        results, suggestions = self.search.search("postgres")
        self.assertGreater(len(results), 0)

        # postgresql should be in results
        names = [r.package.name for r in results]
        self.assertIn("postgresql", names)

    def test_natural_language_query(self):
        """Test natural language query understanding."""
        results, suggestions = self.search.search("web server")
        self.assertGreater(len(results), 0)

        # Should find web servers
        categories = [r.package.category for r in results]
        self.assertTrue(
            any(cat == PackageCategory.WEB_SERVER for cat in categories),
            "Should find web server packages"
        )

    def test_empty_query(self):
        """Test empty query handling."""
        results, suggestions = self.search.search("")
        self.assertEqual(len(results), 0)
        self.assertEqual(len(suggestions), 0)

    def test_whitespace_query(self):
        """Test whitespace-only query."""
        results, suggestions = self.search.search("   ")
        self.assertEqual(len(results), 0)

    def test_nonexistent_package(self):
        """Test query with no matches."""
        results, suggestions = self.search.search("xyzabc123nonexistent")
        # Should either have no results or very low-scored results
        if results:
            self.assertLess(results[0].score, 0.7)

    def test_category_filtering(self):
        """Test filtering by category."""
        results, _ = self.search.search(
            "server",
            category=PackageCategory.WEB_SERVER
        )

        # All results should be web servers
        for result in results:
            self.assertEqual(result.package.category, PackageCategory.WEB_SERVER)

    def test_result_limit(self):
        """Test result limit."""
        results, _ = self.search.search("server", limit=3)
        self.assertLessEqual(len(results), 3)

    def test_result_ranking(self):
        """Test that results are ranked by relevance."""
        results, _ = self.search.search("postgres")

        # Results should be sorted by score (descending)
        if len(results) > 1:
            for i in range(len(results) - 1):
                self.assertGreaterEqual(results[i].score, results[i + 1].score)

    def test_multiple_keyword_match(self):
        """Test matching multiple keywords."""
        results, _ = self.search.search("web")
        self.assertGreater(len(results), 0)

        # Should find packages with "web" keyword
        for result in results[:5]:  # Check top 5
            keywords_lower = [k.lower() for k in result.package.keywords]
            self.assertTrue(
                any("web" in k for k in keywords_lower),
                f"Expected 'web' in keywords for {result.package.name}"
            )

    def test_case_insensitive_search(self):
        """Test that search is case insensitive."""
        results1, _ = self.search.search("NGINX")
        results2, _ = self.search.search("nginx")
        results3, _ = self.search.search("NginX")

        # All should return same top result
        self.assertEqual(results1[0].package.name, results2[0].package.name)
        self.assertEqual(results2[0].package.name, results3[0].package.name)

    def test_search_history_tracking(self):
        """Test that searches are added to history."""
        initial_count = len(self.search.history)

        self.search.search("nginx")
        self.search.search("postgresql")

        self.assertEqual(len(self.search.history), initial_count + 2)

    def test_history_persistence(self):
        """Test that history is saved and loaded."""
        # Perform searches
        self.search.search("nginx")
        self.search.search("docker")

        # Create new search instance with same history file
        new_search = SmartPackageSearch(history_file=self.history_file)

        # Should have loaded history
        self.assertEqual(len(new_search.history), len(self.search.history))

    def test_get_history(self):
        """Test getting search history."""
        self.search.search("nginx")
        self.search.search("postgresql")

        history = self.search.get_history()
        self.assertGreater(len(history), 0)
        self.assertIsInstance(history[0], SearchHistoryEntry)

    def test_history_limit(self):
        """Test history retrieval limit."""
        # Add multiple searches
        for i in range(10):
            self.search.search(f"test{i}")

        history = self.search.get_history(limit=5)
        self.assertEqual(len(history), 5)

    def test_clear_history(self):
        """Test clearing search history."""
        self.search.search("nginx")
        self.search.clear_history()

        self.assertEqual(len(self.search.history), 0)

        # Should persist
        new_search = SmartPackageSearch(history_file=self.history_file)
        self.assertEqual(len(new_search.history), 0)

    def test_history_max_entries(self):
        """Test that history is limited to 100 entries."""
        # Add 150 searches
        for i in range(150):
            self.search.search(f"test{i}")

        # Should keep only last 100
        self.assertEqual(len(self.search.history), 100)

    def test_suggestions_for_typos(self):
        """Test that suggestions are provided for typos."""
        # "ngnix" is a typo for "nginx"
        results, suggestions = self.search.search("ngnix")

        # Should suggest nginx
        self.assertTrue(
            len(suggestions) > 0 or any(r.package.name == "nginx" for r in results),
            "Should suggest or find nginx for 'ngnix'"
        )

    def test_fuzzy_match_threshold(self):
        """Test fuzzy match threshold."""
        # Very different query should not match
        results, _ = self.search.search("abcdefgh")
        if results:
            # Any results should have low scores
            self.assertLess(results[0].score, 0.8)

    def test_normalize_query(self):
        """Test query normalization."""
        normalized = self.search._normalize_query("  NGINX  ")
        self.assertEqual(normalized, "nginx")

    def test_fuzzy_match_score(self):
        """Test fuzzy matching score calculation."""
        score = self.search._fuzzy_match("nginx", "nginx")
        self.assertEqual(score, 1.0)

        score = self.search._fuzzy_match("nginx", "ngnix")
        self.assertGreater(score, 0.5)
        self.assertLess(score, 1.0)

    def test_check_exact_match(self):
        """Test exact match checking."""
        db = PackageDatabase()
        nginx = db.get_package("nginx")

        # Exact name match
        score = self.search._check_exact_match("nginx", nginx)
        self.assertEqual(score, 1.0)

        # Non-match
        score = self.search._check_exact_match("apache", nginx)
        self.assertIsNone(score)

    def test_check_synonym_match(self):
        """Test synonym matching."""
        db = PackageDatabase()
        postgresql = db.get_package("postgresql")

        # "postgres" is a synonym
        result = self.search._check_synonym_match("postgres", postgresql)
        self.assertIsNotNone(result)
        score, matched = result
        self.assertGreater(score, 0.7)

    def test_multiple_categories(self):
        """Test that database has multiple categories."""
        categories = set()
        for pkg in self.search.db.get_all_packages():
            categories.add(pkg.category)

        self.assertGreaterEqual(len(categories), 5)

    def test_database_comprehensiveness(self):
        """Test that database has comprehensive package coverage."""
        # Should have common packages
        common_packages = ["nginx", "postgresql", "docker.io", "git", "python3"]
        for pkg_name in common_packages:
            pkg = self.search.db.get_package(pkg_name)
            self.assertIsNotNone(pkg, f"Missing common package: {pkg_name}")

    def test_keyword_coverage(self):
        """Test that packages have good keyword coverage."""
        for pkg in self.search.db.get_all_packages():
            # Each package should have at least 3 keywords
            self.assertGreaterEqual(
                len(pkg.keywords),
                3,
                f"{pkg.name} should have at least 3 keywords"
            )

    def test_synonym_coverage(self):
        """Test that packages have synonym coverage."""
        packages_with_synonyms = [
            pkg for pkg in self.search.db.get_all_packages()
            if pkg.synonyms
        ]
        # Most packages should have synonyms
        self.assertGreater(len(packages_with_synonyms), 15)


class TestSearchResults(unittest.TestCase):
    """Test cases for search result formatting."""

    def test_format_search_results(self):
        """Test formatting search results."""
        db = PackageDatabase()
        nginx = db.get_package("nginx")

        results = [
            SearchResult(
                package=nginx,
                score=1.0,
                match_type="exact",
                matched_term="nginx"
            )
        ]

        output = format_search_results(results, [])
        self.assertIn("nginx", output)
        self.assertIn("Results:", output)

    def test_format_with_suggestions(self):
        """Test formatting with suggestions."""
        output = format_search_results([], ["nginx", "apache2"])
        self.assertIn("Did you mean:", output)
        self.assertIn("nginx", output)

    def test_format_no_results(self):
        """Test formatting with no results."""
        output = format_search_results([], [])
        self.assertIn("No packages found", output)

    def test_format_multiple_results(self):
        """Test formatting multiple results."""
        db = PackageDatabase()
        nginx = db.get_package("nginx")
        apache = db.get_package("apache2")

        results = [
            SearchResult(package=nginx, score=1.0, match_type="exact", matched_term="nginx"),
            SearchResult(package=apache, score=0.8, match_type="fuzzy", matched_term="apache"),
        ]

        output = format_search_results(results, [])
        self.assertIn("1. nginx", output)
        self.assertIn("2. apache2", output)


class TestDataStructures(unittest.TestCase):
    """Test data structure definitions."""

    def test_package_info_creation(self):
        """Test PackageInfo creation."""
        pkg = PackageInfo(
            name="test",
            display_name="Test Package",
            description="A test package",
            category=PackageCategory.DEVELOPMENT,
            keywords=["test", "development"],
            synonyms=["test-pkg"]
        )

        self.assertEqual(pkg.name, "test")
        self.assertEqual(pkg.category, PackageCategory.DEVELOPMENT)

    def test_search_result_creation(self):
        """Test SearchResult creation."""
        db = PackageDatabase()
        nginx = db.get_package("nginx")

        result = SearchResult(
            package=nginx,
            score=0.95,
            match_type="fuzzy",
            matched_term="ngnix"
        )

        self.assertEqual(result.package.name, "nginx")
        self.assertEqual(result.score, 0.95)
        self.assertEqual(result.match_type, "fuzzy")

    def test_history_entry_creation(self):
        """Test SearchHistoryEntry creation."""
        entry = SearchHistoryEntry(
            timestamp=datetime.now().isoformat(),
            query="nginx",
            results_count=5,
            top_result="nginx"
        )

        self.assertEqual(entry.query, "nginx")
        self.assertEqual(entry.results_count, 5)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history_file = Path(self.temp_dir.name) / "test_history.json"
        self.search = SmartPackageSearch(history_file=self.history_file)

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_special_characters_in_query(self):
        """Test query with special characters."""
        # Should not crash
        results, _ = self.search.search("web-server!@#$")
        self.assertIsInstance(results, list)

    def test_very_long_query(self):
        """Test very long query."""
        long_query = "a" * 1000
        results, _ = self.search.search(long_query)
        self.assertIsInstance(results, list)

    def test_numeric_query(self):
        """Test numeric query."""
        results, _ = self.search.search("12345")
        self.assertIsInstance(results, list)

    def test_unicode_query(self):
        """Test unicode characters in query."""
        results, _ = self.search.search("nginx™")
        self.assertIsInstance(results, list)

    def test_corrupted_history_file(self):
        """Test handling corrupted history file."""
        # Write corrupted JSON
        with open(self.history_file, 'w') as f:
            f.write("not valid json{}")

        # Should handle gracefully
        search = SmartPackageSearch(history_file=self.history_file)
        self.assertEqual(len(search.history), 0)

    def test_missing_history_directory(self):
        """Test creating history in non-existent directory."""
        history_path = Path(self.temp_dir.name) / "subdir" / "history.json"
        # Parent directory doesn't exist, but SmartPackageSearch should handle it
        search = SmartPackageSearch(history_file=history_path)
        search.search("nginx")
        # Should not crash


class TestCLIIntegration(unittest.TestCase):
    """Test CLI integration scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history_file = Path(self.temp_dir.name) / "test_history.json"
        self.search = SmartPackageSearch(history_file=self.history_file)

    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_typical_user_workflow(self):
        """Test typical user search workflow."""
        # User searches for web server
        results, _ = self.search.search("web server")
        self.assertGreater(len(results), 0)

        # User searches with typo
        results, suggestions = self.search.search("postgress")
        self.assertTrue(len(results) > 0 or len(suggestions) > 0)

        # User checks history
        history = self.search.get_history()
        self.assertEqual(len(history), 2)

    def test_search_examples_from_issue(self):
        """Test examples from the GitHub issue."""
        # Example 1: cortex search "web server"
        results, _ = self.search.search("web server")
        self.assertGreater(len(results), 0)

        names = [r.package.name for r in results]
        # Should find nginx, apache2, or other web servers
        has_web_server = any(n in ["nginx", "apache2", "caddy", "lighttpd"] for n in names)
        self.assertTrue(has_web_server)

        # Example 2: cortex search "postgress" (typo)
        results, suggestions = self.search.search("postgress")
        # Should find postgresql or suggest it
        found_or_suggested = (
            any(r.package.name == "postgresql" for r in results) or
            "postgresql" in suggestions
        )
        self.assertTrue(found_or_suggested)


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
