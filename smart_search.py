#!/usr/bin/env python3
"""
Smart Package Search with Fuzzy Matching for Cortex Linux

Intelligent search that understands typos, synonyms, and natural language queries.
Provides ranked search results with suggestions.
"""

import json
import difflib
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum


class PackageCategory(Enum):
    """Package categories for filtering."""
    WEB_SERVER = "web server"
    DATABASE = "database"
    DEVELOPMENT = "development"
    LANGUAGE = "language"
    CONTAINER = "container"
    EDITOR = "editor"
    SECURITY = "security"
    NETWORK = "network"
    MONITORING = "monitoring"
    COMPRESSION = "compression"
    VERSION_CONTROL = "version control"
    MEDIA = "media"
    SYSTEM = "system"
    CLOUD = "cloud"


@dataclass
class PackageInfo:
    """Package information with metadata."""
    name: str
    display_name: str
    description: str
    category: PackageCategory
    keywords: List[str]
    synonyms: List[str]


@dataclass
class SearchResult:
    """Search result with ranking score."""
    package: PackageInfo
    score: float
    match_type: str  # "exact", "fuzzy", "synonym", "keyword"
    matched_term: str


@dataclass
class SearchHistoryEntry:
    """Search history entry."""
    timestamp: str
    query: str
    results_count: int
    top_result: Optional[str]


class PackageDatabase:
    """In-memory package database with comprehensive package information."""

    def __init__(self):
        """Initialize package database."""
        self.packages = self._build_package_database()

    def _build_package_database(self) -> Dict[str, PackageInfo]:
        """Build comprehensive package database."""
        packages = [
            # Web Servers
            PackageInfo(
                name="nginx",
                display_name="Nginx",
                description="High-performance HTTP server and reverse proxy",
                category=PackageCategory.WEB_SERVER,
                keywords=["web", "server", "http", "https", "proxy", "reverse proxy"],
                synonyms=["web server", "http server", "proxy server"]
            ),
            PackageInfo(
                name="apache2",
                display_name="Apache HTTP Server",
                description="Popular open-source HTTP server",
                category=PackageCategory.WEB_SERVER,
                keywords=["web", "server", "http", "https", "apache", "httpd"],
                synonyms=["apache", "httpd", "web server", "http server"]
            ),
            PackageInfo(
                name="caddy",
                display_name="Caddy",
                description="Fast, multi-platform web server with automatic HTTPS",
                category=PackageCategory.WEB_SERVER,
                keywords=["web", "server", "http", "https", "automatic", "tls"],
                synonyms=["web server", "http server"]
            ),
            PackageInfo(
                name="lighttpd",
                display_name="Lighttpd",
                description="Lightweight web server optimized for speed",
                category=PackageCategory.WEB_SERVER,
                keywords=["web", "server", "http", "lightweight", "fast"],
                synonyms=["web server", "http server", "light server"]
            ),

            # Databases
            PackageInfo(
                name="postgresql",
                display_name="PostgreSQL",
                description="Advanced open-source relational database",
                category=PackageCategory.DATABASE,
                keywords=["database", "sql", "relational", "postgres", "rdbms"],
                synonyms=["postgres", "pgsql", "psql", "postgress"]  # including typo
            ),
            PackageInfo(
                name="postgis",
                display_name="PostGIS",
                description="PostgreSQL extension for geographic objects",
                category=PackageCategory.DATABASE,
                keywords=["database", "postgres", "extension", "geographic", "gis", "spatial"],
                synonyms=["postgres extension", "geo database"]
            ),
            PackageInfo(
                name="mysql-server",
                display_name="MySQL",
                description="Popular open-source relational database",
                category=PackageCategory.DATABASE,
                keywords=["database", "sql", "relational", "mysql", "rdbms"],
                synonyms=["mysql", "my sql", "mariadb"]
            ),
            PackageInfo(
                name="mongodb",
                display_name="MongoDB",
                description="Popular NoSQL document database",
                category=PackageCategory.DATABASE,
                keywords=["database", "nosql", "document", "mongo", "json"],
                synonyms=["mongo", "document database", "nosql"]
            ),
            PackageInfo(
                name="redis-server",
                display_name="Redis",
                description="In-memory data structure store and cache",
                category=PackageCategory.DATABASE,
                keywords=["database", "cache", "key-value", "in-memory", "redis"],
                synonyms=["redis", "cache", "key value store"]
            ),
            PackageInfo(
                name="sqlite3",
                display_name="SQLite",
                description="Lightweight embedded relational database",
                category=PackageCategory.DATABASE,
                keywords=["database", "sql", "embedded", "lightweight", "sqlite"],
                synonyms=["sqlite", "lite database"]
            ),

            # Programming Languages
            PackageInfo(
                name="python3",
                display_name="Python 3",
                description="Popular high-level programming language",
                category=PackageCategory.LANGUAGE,
                keywords=["python", "programming", "language", "scripting", "interpreter"],
                synonyms=["python", "py", "python3"]
            ),
            PackageInfo(
                name="nodejs",
                display_name="Node.js",
                description="JavaScript runtime built on Chrome's V8 engine",
                category=PackageCategory.LANGUAGE,
                keywords=["javascript", "js", "node", "runtime", "v8"],
                synonyms=["node", "nodejs", "javascript", "js runtime"]
            ),
            PackageInfo(
                name="golang",
                display_name="Go",
                description="Statically typed compiled programming language",
                category=PackageCategory.LANGUAGE,
                keywords=["go", "golang", "programming", "language", "compiled"],
                synonyms=["go", "golang", "go lang"]
            ),
            PackageInfo(
                name="ruby",
                display_name="Ruby",
                description="Dynamic, interpreted programming language",
                category=PackageCategory.LANGUAGE,
                keywords=["ruby", "programming", "language", "scripting", "interpreter"],
                synonyms=["ruby", "ruby lang"]
            ),

            # Containers
            PackageInfo(
                name="docker.io",
                display_name="Docker",
                description="Platform for developing, shipping, and running applications in containers",
                category=PackageCategory.CONTAINER,
                keywords=["container", "docker", "virtualization", "deployment"],
                synonyms=["docker", "containers", "containerization"]
            ),
            PackageInfo(
                name="kubectl",
                display_name="kubectl",
                description="Kubernetes command-line tool",
                category=PackageCategory.CONTAINER,
                keywords=["kubernetes", "k8s", "container", "orchestration", "kubectl"],
                synonyms=["kubernetes", "k8s", "kube"]
            ),

            # Editors
            PackageInfo(
                name="vim",
                display_name="Vim",
                description="Highly configurable text editor",
                category=PackageCategory.EDITOR,
                keywords=["editor", "text", "vim", "vi", "terminal"],
                synonyms=["vi", "vim", "text editor"]
            ),
            PackageInfo(
                name="emacs",
                display_name="Emacs",
                description="Extensible, customizable text editor",
                category=PackageCategory.EDITOR,
                keywords=["editor", "text", "emacs", "gnu", "terminal"],
                synonyms=["emacs", "text editor", "gnu emacs"]
            ),
            PackageInfo(
                name="nano",
                display_name="GNU nano",
                description="Simple terminal-based text editor",
                category=PackageCategory.EDITOR,
                keywords=["editor", "text", "nano", "simple", "terminal"],
                synonyms=["nano", "text editor"]
            ),

            # Version Control
            PackageInfo(
                name="git",
                display_name="Git",
                description="Distributed version control system",
                category=PackageCategory.VERSION_CONTROL,
                keywords=["git", "version", "control", "vcs", "source"],
                synonyms=["git", "version control", "source control"]
            ),
            PackageInfo(
                name="subversion",
                display_name="Apache Subversion",
                description="Centralized version control system",
                category=PackageCategory.VERSION_CONTROL,
                keywords=["svn", "subversion", "version", "control", "vcs"],
                synonyms=["svn", "subversion", "version control"]
            ),

            # Development Tools
            PackageInfo(
                name="build-essential",
                display_name="Build Essential",
                description="Essential tools for building software",
                category=PackageCategory.DEVELOPMENT,
                keywords=["build", "compile", "gcc", "make", "development"],
                synonyms=["build tools", "compiler", "development tools"]
            ),
            PackageInfo(
                name="cmake",
                display_name="CMake",
                description="Cross-platform build system generator",
                category=PackageCategory.DEVELOPMENT,
                keywords=["build", "cmake", "make", "cross-platform"],
                synonyms=["cmake", "build tool"]
            ),

            # Network Tools
            PackageInfo(
                name="curl",
                display_name="curl",
                description="Command-line tool for transferring data with URLs",
                category=PackageCategory.NETWORK,
                keywords=["network", "http", "curl", "download", "transfer"],
                synonyms=["curl", "http client", "download tool"]
            ),
            PackageInfo(
                name="wget",
                display_name="wget",
                description="Network downloader",
                category=PackageCategory.NETWORK,
                keywords=["network", "http", "wget", "download", "transfer"],
                synonyms=["wget", "downloader", "http client"]
            ),
            PackageInfo(
                name="net-tools",
                display_name="Net Tools",
                description="Network configuration and debugging tools",
                category=PackageCategory.NETWORK,
                keywords=["network", "tools", "ifconfig", "netstat", "route"],
                synonyms=["network tools", "networking"]
            ),
            PackageInfo(
                name="tcpdump",
                display_name="tcpdump",
                description="Network packet analyzer",
                category=PackageCategory.NETWORK,
                keywords=["network", "packet", "capture", "analyzer", "tcpdump"],
                synonyms=["packet capture", "packet sniffer", "network analyzer"]
            ),

            # Monitoring
            PackageInfo(
                name="htop",
                display_name="htop",
                description="Interactive process viewer",
                category=PackageCategory.MONITORING,
                keywords=["monitoring", "process", "cpu", "memory", "htop"],
                synonyms=["process monitor", "system monitor", "top"]
            ),
            PackageInfo(
                name="iotop",
                display_name="iotop",
                description="I/O monitoring tool",
                category=PackageCategory.MONITORING,
                keywords=["monitoring", "io", "disk", "iotop"],
                synonyms=["io monitor", "disk monitor"]
            ),

            # Security
            PackageInfo(
                name="ufw",
                display_name="Uncomplicated Firewall",
                description="Easy-to-use firewall management tool",
                category=PackageCategory.SECURITY,
                keywords=["security", "firewall", "ufw", "iptables"],
                synonyms=["firewall", "iptables", "security"]
            ),
            PackageInfo(
                name="fail2ban",
                display_name="Fail2Ban",
                description="Intrusion prevention software",
                category=PackageCategory.SECURITY,
                keywords=["security", "fail2ban", "intrusion", "prevention", "ban"],
                synonyms=["intrusion prevention", "security tool"]
            ),

            # Compression
            PackageInfo(
                name="zip",
                display_name="Zip",
                description="Archiver for .zip files",
                category=PackageCategory.COMPRESSION,
                keywords=["compression", "zip", "archive"],
                synonyms=["zip", "compress", "archive"]
            ),
            PackageInfo(
                name="unzip",
                display_name="Unzip",
                description="De-archiver for .zip files",
                category=PackageCategory.COMPRESSION,
                keywords=["compression", "unzip", "extract", "archive"],
                synonyms=["unzip", "extract", "decompress"]
            ),
            PackageInfo(
                name="gzip",
                display_name="gzip",
                description="GNU compression utility",
                category=PackageCategory.COMPRESSION,
                keywords=["compression", "gzip", "gnu"],
                synonyms=["gzip", "compress", "gnu zip"]
            ),
        ]

        return {pkg.name: pkg for pkg in packages}

    def get_all_packages(self) -> List[PackageInfo]:
        """Get all packages."""
        return list(self.packages.values())

    def get_package(self, name: str) -> Optional[PackageInfo]:
        """Get package by name."""
        return self.packages.get(name)

    def get_by_category(self, category: PackageCategory) -> List[PackageInfo]:
        """Get packages by category."""
        return [pkg for pkg in self.packages.values() if pkg.category == category]


class SmartPackageSearch:
    """
    Smart package search with fuzzy matching, synonym detection, and ranking.

    Features:
    - Fuzzy string matching for typo tolerance
    - Synonym detection for natural language
    - Search result ranking by relevance
    - Category filtering
    - Search history tracking
    - "Did you mean?" suggestions
    """

    def __init__(self, history_file: Optional[Path] = None):
        """
        Initialize smart search.

        Args:
            history_file: Path to search history file (default: ~/.config/cortex/search_history.json)
        """
        self.db = PackageDatabase()

        if history_file is None:
            config_dir = Path.home() / ".config" / "cortex"
            config_dir.mkdir(parents=True, exist_ok=True)
            history_file = config_dir / "search_history.json"

        self.history_file = history_file
        self.history = self._load_history()

        # Fuzzy matching threshold (0.0 to 1.0)
        self.fuzzy_threshold = 0.6

        # Minimum score for search results
        self.min_score = 0.3

    def _load_history(self) -> List[SearchHistoryEntry]:
        """Load search history from file."""
        if not self.history_file.exists():
            return []

        try:
            with open(self.history_file, 'r') as f:
                data = json.load(f)
                return [SearchHistoryEntry(**entry) for entry in data]
        except (json.JSONDecodeError, KeyError):
            return []

    def _save_history(self):
        """Save search history to file."""
        try:
            with open(self.history_file, 'w') as f:
                data = [asdict(entry) for entry in self.history]
                json.dump(data, f, indent=2)
        except IOError:
            pass  # Silently fail if can't write history

    def _add_to_history(self, query: str, results: List[SearchResult]):
        """Add search to history."""
        entry = SearchHistoryEntry(
            timestamp=datetime.now().isoformat(),
            query=query,
            results_count=len(results),
            top_result=results[0].package.name if results else None
        )
        self.history.append(entry)

        # Keep only last 100 searches
        if len(self.history) > 100:
            self.history = self.history[-100:]

        self._save_history()

    def _normalize_query(self, query: str) -> str:
        """Normalize search query."""
        return query.lower().strip()

    def _fuzzy_match(self, query: str, text: str) -> float:
        """
        Calculate fuzzy match score using sequence matcher.

        Args:
            query: Search query
            text: Text to match against

        Returns:
            Match score (0.0 to 1.0)
        """
        return difflib.SequenceMatcher(None, query, text).ratio()

    def _check_exact_match(self, query: str, package: PackageInfo) -> Optional[float]:
        """Check for exact matches in name, display name, or keywords."""
        query_lower = query.lower()

        # Exact name match (highest score)
        if query_lower == package.name.lower():
            return 1.0

        # Exact display name match
        if query_lower == package.display_name.lower():
            return 0.95

        # Exact keyword match
        for keyword in package.keywords:
            if query_lower == keyword.lower():
                return 0.9

        return None

    def _check_synonym_match(self, query: str, package: PackageInfo) -> Optional[Tuple[float, str]]:
        """Check for synonym matches."""
        query_lower = query.lower()

        for synonym in package.synonyms:
            if query_lower == synonym.lower():
                return (0.85, synonym)

            # Fuzzy synonym match
            score = self._fuzzy_match(query_lower, synonym.lower())
            if score >= self.fuzzy_threshold:
                return (score * 0.8, synonym)  # Slightly lower than exact

        return None

    def _check_fuzzy_match(self, query: str, package: PackageInfo) -> Optional[Tuple[float, str]]:
        """Check for fuzzy matches in name and keywords."""
        query_lower = query.lower()
        best_score = 0.0
        best_match = ""

        # Fuzzy match against name
        score = self._fuzzy_match(query_lower, package.name.lower())
        if score > best_score:
            best_score = score
            best_match = package.name

        # Fuzzy match against display name
        score = self._fuzzy_match(query_lower, package.display_name.lower())
        if score > best_score:
            best_score = score
            best_match = package.display_name

        # Fuzzy match against keywords
        for keyword in package.keywords:
            score = self._fuzzy_match(query_lower, keyword.lower())
            if score > best_score:
                best_score = score
                best_match = keyword

        if best_score >= self.fuzzy_threshold:
            return (best_score * 0.7, best_match)  # Lower weight for fuzzy

        return None

    def _check_keyword_match(self, query: str, package: PackageInfo) -> Optional[Tuple[float, str]]:
        """Check for partial keyword matches."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for keyword in package.keywords:
            keyword_lower = keyword.lower()
            keyword_words = set(keyword_lower.split())

            # Check word overlap
            overlap = query_words & keyword_words
            if overlap:
                score = len(overlap) / max(len(query_words), len(keyword_words))
                if score >= 0.5:
                    return (score * 0.6, keyword)  # Lower weight for partial match

            # Check if query is substring of keyword
            if query_lower in keyword_lower:
                return (0.5, keyword)

        return None

    def _rank_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """Sort results by score (descending)."""
        return sorted(results, key=lambda r: r.score, reverse=True)

    def _find_suggestions(self, query: str, packages: List[PackageInfo], limit: int = 3) -> List[str]:
        """Find "did you mean" suggestions for likely typos."""
        suggestions = []
        query_lower = query.lower()

        for package in packages:
            # Check name similarity
            score = self._fuzzy_match(query_lower, package.name.lower())
            if 0.5 <= score < self.fuzzy_threshold:
                suggestions.append((package.name, score))

            # Check synonym similarity
            for synonym in package.synonyms:
                score = self._fuzzy_match(query_lower, synonym.lower())
                if 0.5 <= score < self.fuzzy_threshold:
                    suggestions.append((synonym, score))

        # Sort by score and return top suggestions
        suggestions.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in suggestions[:limit]]

    def search(
        self,
        query: str,
        category: Optional[PackageCategory] = None,
        limit: int = 10
    ) -> Tuple[List[SearchResult], List[str]]:
        """
        Search for packages with fuzzy matching and ranking.

        Args:
            query: Search query (can include typos)
            category: Optional category filter
            limit: Maximum number of results

        Returns:
            Tuple of (search results, suggestions)
        """
        if not query or not query.strip():
            return ([], [])

        query = self._normalize_query(query)
        results = []

        # Get packages to search
        if category:
            packages = self.db.get_by_category(category)
        else:
            packages = self.db.get_all_packages()

        # Search each package
        for package in packages:
            match_type = None
            score = None
            matched_term = None

            # Check exact match first
            exact_score = self._check_exact_match(query, package)
            if exact_score:
                match_type = "exact"
                score = exact_score
                matched_term = package.name

            # Check synonym match
            if not score:
                synonym_match = self._check_synonym_match(query, package)
                if synonym_match:
                    match_type = "synonym"
                    score, matched_term = synonym_match

            # Check fuzzy match
            if not score:
                fuzzy_match = self._check_fuzzy_match(query, package)
                if fuzzy_match:
                    match_type = "fuzzy"
                    score, matched_term = fuzzy_match

            # Check keyword match
            if not score:
                keyword_match = self._check_keyword_match(query, package)
                if keyword_match:
                    match_type = "keyword"
                    score, matched_term = keyword_match

            # Add to results if score meets threshold
            if score and score >= self.min_score:
                results.append(SearchResult(
                    package=package,
                    score=score,
                    match_type=match_type,
                    matched_term=matched_term
                ))

        # Rank results
        results = self._rank_results(results)

        # Limit results
        results = results[:limit]

        # Find suggestions if few results
        suggestions = []
        if len(results) < 3:
            suggestions = self._find_suggestions(query, packages)

        # Add to search history
        self._add_to_history(query, results)

        return (results, suggestions)

    def get_history(self, limit: int = 20) -> List[SearchHistoryEntry]:
        """Get recent search history."""
        return list(reversed(self.history[-limit:]))

    def clear_history(self):
        """Clear search history."""
        self.history = []
        self._save_history()


def format_search_results(results: List[SearchResult], suggestions: List[str]) -> str:
    """
    Format search results for display.

    Args:
        results: Search results
        suggestions: Search suggestions

    Returns:
        Formatted string for display
    """
    output = []

    if suggestions:
        output.append("Did you mean: " + ", ".join(suggestions) + "?\n")

    if not results:
        output.append("No packages found.")
        return "\n".join(output)

    output.append("Results:")
    for i, result in enumerate(results, 1):
        pkg = result.package
        # Format: "  1. nginx (web server) - HTTP server and reverse proxy"
        line = f"  {i}. {pkg.name} ({pkg.category.value}) - {pkg.description}"
        output.append(line)

    return "\n".join(output)
