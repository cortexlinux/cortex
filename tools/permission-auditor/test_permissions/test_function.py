#!/usr/bin/env python3
import sys
sys.path.insert(0, '../src')

import auditor

# Test the function directly
print("Direct function test:")
result1 = auditor.check_file_permissions("dangerous_file.txt")
print(f"dangerous_file.txt: {result1}")

result2 = auditor.check_file_permissions("world_writable.txt")
print(f"world_writable.txt: {result2}")

result3 = auditor.check_file_permissions("dangerous_dir")
print(f"dangerous_dir: {result3}")
