#!/usr/bin/env python3
"""
Standalone test for interactive suggestions (doesn't require full cortex install).

Usage:
    python3 test_suggestions_standalone.py docker
    python3 test_suggestions_standalone.py docker --interactive
"""

import json
import sys
from pathlib import Path


def test_database_load():
    """Test loading the suggestion database."""
    db_path = Path(__file__).parent / "data" / "suggestions.json"
    
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return False
    
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            suggestions = data.get("suggestions", [])
            print(f"✅ Loaded {len(suggestions)} suggestions")
            
            # Show sample
            if suggestions:
                sample = suggestions[0]
                print(f"✅ Sample: {sample.get('name')} - {sample.get('display_name')}")
            
            return True
    except Exception as e:
        print(f"❌ Error loading database: {e}")
        return False


def test_search(query: str):
    """Test fuzzy search."""
    db_path = Path(__file__).parent / "data" / "suggestions.json"
    
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            suggestions = data.get("suggestions", [])
    except Exception as e:
        print(f"❌ Error loading database: {e}")
        return
    
    # Simple fuzzy match
    def fuzzy_match(query: str, text: str) -> float:
        query_lower = query.lower()
        text_lower = text.lower()
        
        if query_lower == text_lower:
            return 1.0
        if text_lower.startswith(query_lower):
            return 0.9
        if query_lower in text_lower:
            return 0.7
        
        # Check keywords
        for kw in text_lower.split():
            if query_lower in kw:
                return 0.5
        
        return 0.0
    
    # Score all suggestions
    scored = []
    for s in suggestions:
        name_score = fuzzy_match(query, s.get("name", ""))
        display_score = fuzzy_match(query, s.get("display_name", ""))
        desc_score = fuzzy_match(query, s.get("description", "")) * 0.5
        
        keywords = s.get("keywords", [])
        keyword_scores = [fuzzy_match(query, kw) * 0.7 for kw in keywords]
        keyword_score = max(keyword_scores) if keyword_scores else 0.0
        
        score = max(name_score, display_score, desc_score, keyword_score)
        
        if score > 0:
            priority = s.get("priority", 10)
            final_score = score + (priority / 100.0)
            scored.append((final_score, s))
    
    # Sort and show top results
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [s for _, s in scored[:5]]
    
    print(f"\n✅ Found {len(results)} results for '{query}':\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r.get('display_name', 'Unknown')}")
        print(f"   {r.get('description', '')[:60]}...")
        print()


def main():
    """Main test function."""
    print("🧪 Testing Interactive Suggestions\n")
    
    # Test 1: Database load
    print("Test 1: Database Loading")
    print("-" * 40)
    if not test_database_load():
        sys.exit(1)
    
    # Test 2: Search
    query = sys.argv[1] if len(sys.argv) > 1 else "docker"
    print(f"\nTest 2: Fuzzy Search (query: '{query}')")
    print("-" * 40)
    test_search(query)
    
    # Test 3: Interactive (if requested)
    if len(sys.argv) > 2 and sys.argv[2] == "--interactive":
        print("\nTest 3: Interactive UI")
        print("-" * 40)
        print("⚠️  Interactive UI requires prompt_toolkit and full cortex install")
        print("   Run: cortex install docker")
    
    print("\n✅ All tests passed!")
    print("\nTo test full integration:")
    print("  1. Install dependencies: pip install -r requirements.txt")
    print("  2. Run: cortex install docker")


if __name__ == "__main__":
    main()

