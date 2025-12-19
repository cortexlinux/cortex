#!/usr/bin/env python3
"""Direct test of the interactive UI to see if it works."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from cortex.interactive_suggestions import SuggestionDatabase, InteractiveSuggestionUI
    from cortex.hardware_detection import HardwareDetector
    
    print("Testing interactive UI...")
    print("=" * 60)
    
    # Load database
    db = SuggestionDatabase()
    print(f"✅ Database loaded: {len(db.suggestions)} suggestions")
    
    # Hardware detection
    detector = HardwareDetector(use_cache=True)
    hw = detector.detect_quick()
    print(f"✅ Hardware detected: {hw}")
    
    # Search
    results = db.search("docker", hw, limit=10)
    print(f"✅ Found {len(results)} results for 'docker'")
    
    if results:
        print("\nTop 3 results:")
        for i, r in enumerate(results[:3], 1):
            print(f"  {i}. {r.get('display_name')}")
        
        print("\n" + "=" * 60)
        print("Launching interactive UI...")
        print("(Use ↑↓ to navigate, Enter to select, Esc to cancel)")
        print("=" * 60 + "\n")
        
        # Show UI
        ui = InteractiveSuggestionUI(db, hw)
        suggestion = ui.show(initial_query="docker")
        
        if suggestion:
            print(f"\n✅ Selected: {suggestion.get('display_name')}")
        else:
            print("\n❌ No suggestion selected (cancelled)")
    else:
        print("❌ No results found!")
        
except Exception as e:
    import traceback
    print(f"❌ Error: {e}")
    print("\nTraceback:")
    traceback.print_exc()

