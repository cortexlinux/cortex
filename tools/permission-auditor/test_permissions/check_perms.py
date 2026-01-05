#!/usr/bin/env python3
import os
import stat

print("=== DIAGNOSTIC ===")

files = ["dangerous_file.txt", "world_writable.txt", "dangerous_dir"]

for f in files:
    if os.path.exists(f):
        st = os.stat(f)
        mode = st.st_mode
        perm = stat.S_IMODE(mode)
        
        print(f"\nFile: {f}")
        print(f"  Permissions (decimal): {perm}")
        print(f"  Permissions (octal): {oct(perm)}")
        print(f"  Last 3 digits: {oct(perm)[-3:]}")
        print(f"  Is 0o777? {perm == 0o777}")
        print(f"  World writable? {bool(perm & 0o002)}")
        print(f"  Owner UID: {st.st_uid}")
    else:
        print(f"\nFile {f} does not exist!")
