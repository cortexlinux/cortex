import os
import subprocess

def check_cis_compliance():
    """Performs a basic CIS-style compliance scan for Linux."""
    checks = [
        ("Checking if /etc/shadow is root-only...", "ls -l /etc/shadow", "-rw-------"),
        ("Checking if /etc/passwd is root-writable only...", "ls -l /etc/passwd", "-rw-r--r--"),
        ("Checking if SSH root login is disabled...", "grep '^PermitRootLogin no' /etc/ssh/sshd_config", "PermitRootLogin no"),
    ]
    
    results = []
    for desc, cmd, expected in checks:
        print(desc)
        try:
            output = subprocess.check_output(cmd, shell=True).decode()
            if expected in output:
                results.append(f"PASS: {desc}")
            else:
                results.append(f"FAIL: {desc} (Output: {output.strip()})")
        except:
            results.append(f"ERROR: Could not execute {cmd}")
            
    return results

if __name__ == "__main__":
    for r in check_cis_compliance():
        print(r)
