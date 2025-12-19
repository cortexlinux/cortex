#!/usr/bin/env python3
"""
Test script for interactive suggestions system.

Usage:
    python examples/test_suggestions.py docker
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cortex.interactive_suggestions import SuggestionDatabase, get_suggestion
from cortex.hardware_detection import HardwareDetector


def test_suggestions():
    """Test the suggestion system."""
    query = sys.argv[1] if len(sys.argv) > 1 else "docker"

    print(f"Testing suggestions for query: '{query}'\n")

    # Load database
    db = SuggestionDatabase()
    print(f"Loaded {len(db.suggestions)} suggestions from database\n")

    # Quick hardware detection
    detector = HardwareDetector(use_cache=True)
    hardware_info = detector.detect_quick()
    print(f"Hardware info: {hardware_info}\n")

    # Search
    results = db.search(query, hardware_info, limit=5)
    print(f"Found {len(results)} results:\n")

    for idx, suggestion in enumerate(results, 1):
        print(f"{idx}. {suggestion.get('display_name', 'Unknown')}")
        print(f"   {suggestion.get('description', '')}")
        print(f"   Keywords: {', '.join(suggestion.get('keywords', []))}")
        print()

    # Test interactive (if prompt_toolkit available)
    if len(sys.argv) > 2 and sys.argv[2] == "--interactive":
        print("Testing interactive UI...")
        suggestion = get_suggestion(query, hardware_info, interactive=True)
        if suggestion:
            print(f"\nSelected: {suggestion.get('display_name')}")
        else:
            print("\nNo suggestion selected")


if __name__ == "__main__":
    test_suggestions()

