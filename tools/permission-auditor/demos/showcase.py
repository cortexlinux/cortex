#!/usr/bin/env python3
"""
Showcase all features of Permission Auditor.
"""

import os
import sys
import tempfile
import subprocess

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

def run_showcase():
    """Run the full showcase."""
    print("🔐 PERMISSION AUDITOR SHOWCASE")
    print("=" * 60)
    
    # Create demo environment
    demo_dir = tempfile.mkdtemp(prefix="perm_audit_demo_")
    print(f"\n📁 Created demo directory: {demo_dir}")
    
    try:
        # Create various test files
        print("\n1️⃣  Creating test files with dangerous permissions...")
        
        # Dangerous script with 777
        dangerous_script = os.path.join(demo_dir, "dangerous-script-777.sh")
        with open(dangerous_script, 'w') as f:
            f.write("#!/bin/bash\necho 'This script has 777 permissions! Very dangerous!'")
        os.chmod(dangerous_script, 0o777)
        print(f"   Created: {dangerous_script} (777 permissions)")
        
        # World-writable config
        world_writable_conf = os.path.join(demo_dir, "config-666.conf")
        with open(world_writable_conf, 'w') as f:
            f.write("database_password=supersecret123\napi_key=ABC123XYZ")
        os.chmod(world_writable_conf, 0o666)
        print(f"   Created: {world_writable_conf} (666 - world-writable)")
        
        # Open directory
        open_dir = os.path.join(demo_dir, "open-directory-777")
        os.mkdir(open_dir)
        os.chmod(open_dir, 0o777)
        print(f"   Created: {open_dir} (directory with 777)")
        
        # Safe file for contrast
        safe_file = os.path.join(demo_dir, "safe-file-644.txt")
        with open(safe_file, 'w') as f:
            f.write("This file has safe 644 permissions")
        os.chmod(safe_file, 0o644)
        print(f"   Created: {safe_file} (644 - safe permissions)")
        
        print("\n2️⃣  Running Permission Auditor scan...")
        print("-" * 40)
        
        # Run the auditor
        cmd = [sys.executable, "src/auditor.py", demo_dir, "-r"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        print("\n3️⃣  Showing fix commands (dry run)...")
        print("-" * 40)
        
        cmd = [sys.executable, "src/auditor.py", demo_dir, "-r", "--fix"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Extract just the fix commands section
        output = result.stdout
        if "RECOMMENDED FIX" in output:
            fixes_section = output[output.find("RECOMMENDED FIX"):]
            fixes_section = fixes_section[:fixes_section.find("SECURITY BEST PRACTICES")]
            print(fixes_section)
        
        print("\n4️⃣  Testing JSON output format...")
        print("-" * 40)
        
        cmd = [sys.executable, "src/auditor.py", demo_dir, "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        try:
            import json
            parsed = json.loads(result.stdout)
            print(f"✅ JSON output is valid")
            print(f"   Found {len(parsed.get('findings', []))} issues")
            print(f"   Tool version: {parsed.get('metadata', {}).get('version', 'unknown')}")
        except:
            print("⚠️  Could not parse JSON output")
        
        print("\n5️⃣  Testing --help output...")
        print("-" * 40)
        
        cmd = [sys.executable, "src/auditor.py", "--help"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        help_lines = result.stdout.split('\n')[:10]  # Show first 10 lines
        print("\n".join(help_lines))
        print("...")
        
        print("\n" + "=" * 60)
        print("🎉 SHOWCASE COMPLETE!")
        print("\nFeatures demonstrated:")
        print("  • 777 permission detection")
        print("  • World-writable file detection")
        print("  • Plain English explanations")
        print("  • Smart permission recommendations")
        print("  • Safe fix commands")
        print("  • Multiple output formats (text, JSON)")
        print("  • Comprehensive CLI interface")
        
        print(f"\nDemo directory: {demo_dir}")
        print("(This will be cleaned up automatically)")
        
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(demo_dir, ignore_errors=True)

if __name__ == "__main__":
    run_showcase()
