#!/usr/bin/env python3
"""Test version display."""

import subprocess
import sys

def test_version_flag():
    """Test --version flag."""
    print("Testing --version flag...")
    result = subprocess.run(
        [sys.executable, 'src/auditor.py', '--version'],
        capture_output=True,
        text=True
    )
    
    output = result.stdout.strip()
    
    if '1.0.0' in output:
        print(f"✅ Version flag works: {output}")
        return True
    else:
        print(f"❌ Version flag failed. Output: {output}")
        return False

def test_help_version():
    """Test version in --help output."""
    print("\nTesting --help output for version...")
    result = subprocess.run(
        [sys.executable, 'src/auditor.py', '--help'],
        capture_output=True,
        text=True
    )
    
    output = result.stdout + result.stderr
    
    # Version should be in description or somewhere
    if '1.0.0' in output or 'v1.0.0' in output:
        print("✅ Version found in help output")
        # Show relevant lines
        for line in output.split('\n'):
            if '1.0.0' in line or 'version' in line.lower():
                print(f"   {line}")
        return True
    else:
        print("❌ Version NOT found in help output")
        return False

def test_banner_version():
    """Test version in banner."""
    print("\nTesting banner for version...")
    result = subprocess.run(
        [sys.executable, 'src/auditor.py', '.'],
        capture_output=True,
        text=True
    )
    
    output = result.stdout
    
    if 'v1.0.0' in output or '1.0.0' in output:
        print("✅ Version found in banner/output")
        # Find and show the line with version
        for line in output.split('\n'):
            if '1.0.0' in line:
                print(f"   {line}")
                break
        return True
    else:
        print("❌ Version NOT found in banner/output")
        return False

if __name__ == "__main__":
    print("Testing version display in Permission Auditor...")
    
    tests = [
        test_version_flag,
        test_help_version,
        test_banner_version
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nResults: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("✅ All version tests PASSED")
        sys.exit(0)
    else:
        print("❌ Some version tests FAILED")
        sys.exit(1)
