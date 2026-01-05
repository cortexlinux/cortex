#!/usr/bin/env python3
"""Test fix command generation and application."""

import os
import tempfile
import stat
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

from auditor import apply_single_fix, suggest_safe_permissions

def get_current_user():
    """Get current username safely."""
    try:
        # Try multiple methods to get username
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name
    except (ImportError, KeyError):
        try:
            return os.getlogin()
        except (FileNotFoundError, OSError):
            return "testuser"

def test_single_fix_dry_run():
    """Test that fix commands are generated correctly."""
    
    # Create a test file with 777 permissions
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sh') as f:
        f.write("#!/bin/bash\necho 'test'")
        temp_path = f.name
    
    try:
        os.chmod(temp_path, 0o777)
        
        # Get current user safely
        current_user = get_current_user()
        
        # Create a mock finding
        finding = {
            'path': temp_path,
            'permissions': '777',
            'permissions_octal': '777',
            'issue': 'FULL_777',
            'severity': 'CRITICAL',
            'is_directory': False,
            'owner': current_user,
            'group': current_user,
            'uid': os.getuid(),
            'gid': os.getgid()
        }
        
        # Test dry run
        result = apply_single_fix(finding, dry_run=True, backup=False)
        
        assert result['status'] == 'DRY_RUN', f"Expected DRY_RUN, got {result['status']}"
        assert 'chmod' in result['command'], "Command should contain chmod"
        # Check that it recommends safe permissions (750 or 755 for executable)
        assert any(perm in result['command'] for perm in ['750', '755', '644']), \
            f"Should recommend safe permissions, got: {result['command']}"
        
        print("✅ test_single_fix_dry_run: PASSED")
        return True
        
    except AssertionError as e:
        print(f"❌ test_single_fix_dry_run: FAILED - {e}")
        return False
    except Exception as e:
        print(f"❌ test_single_fix_dry_run: ERROR - {e}")
        return False
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def test_safe_permission_suggestion():
    """Test that appropriate permissions are suggested."""
    
    test_cases = [
        {
            'path': '/home/user/script.sh',
            'permissions': '777',
            'is_directory': False,
            'expected': '750'  # Executable script
        },
        {
            'path': '/etc/myapp/config.conf',
            'permissions': '666',
            'is_directory': False,
            'expected': '640'  # Config file
        },
        {
            'path': '/var/log/app.log',
            'permissions': '777',
            'is_directory': False,
            'expected': '640'  # Log file
        },
        {
            'path': '/home/user/docs/readme.txt',
            'permissions': '777',
            'is_directory': False,
            'expected': '644'  # Regular file
        },
        {
            'path': '/var/www/html',
            'permissions': '777',
            'is_directory': True,
            'expected': '755'  # Web directory
        },
        {
            'path': '/home/user/private',
            'permissions': '777',
            'is_directory': True,
            'expected': '750'  # Home directory
        }
    ]
    
    all_passed = True
    current_user = get_current_user()
    
    for i, test_case in enumerate(test_cases):
        finding = {
            'path': test_case['path'],
            'permissions': test_case['permissions'],
            'issue': 'FULL_777',
            'severity': 'CRITICAL',
            'is_directory': test_case['is_directory'],
            'owner': current_user,
            'group': current_user,
            'uid': os.getuid() if 'home' in test_case['path'] else 0,
            'gid': os.getgid() if 'home' in test_case['path'] else 0
        }
        
        suggestion = suggest_safe_permissions(finding)
        recommended = suggestion['recommended']
        
        if recommended == test_case['expected']:
            print(f"✅ test_case_{i}: {test_case['path']} -> {recommended} (PASSED)")
        else:
            print(f"❌ test_case_{i}: {test_case['path']} -> {recommended} (expected {test_case['expected']})")
            all_passed = False
    
    return all_passed

def test_world_writable_fix():
    """Test fix for world-writable files."""
    
    # Create a test file with 666 permissions (world-writable)
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test content")
        temp_path = f.name
    
    try:
        os.chmod(temp_path, 0o666)
        
        current_user = get_current_user()
        
        finding = {
            'path': temp_path,
            'permissions': '666',
            'permissions_octal': '666',
            'issue': 'WORLD_WRITABLE',
            'severity': 'HIGH',
            'is_directory': False,
            'owner': current_user,
            'group': current_user,
            'uid': os.getuid(),
            'gid': os.getgid()
        }
        
        suggestion = suggest_safe_permissions(finding)
        
        # Should suggest 644 for regular file
        assert suggestion['recommended'] in ['644', '640'], \
            f"Should suggest 644 or 640 for regular file, got {suggestion['recommended']}"
        
        print("✅ test_world_writable_fix: PASSED")
        return True
        
    except AssertionError as e:
        print(f"❌ test_world_writable_fix: FAILED - {e}")
        return False
    except Exception as e:
        print(f"❌ test_world_writable_fix: ERROR - {e}")
        return False
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def test_special_files():
    """Test permission suggestions for special system files."""
    
    test_cases = [
        ('/etc/shadow', '600', 'Password hashes - root only'),
        ('/etc/sudoers', '440', 'Sudo configuration - root only'),
        ('/etc/passwd', '644', 'User database - readable by all'),
    ]
    
    all_passed = True
    
    for path, expected_perm, expected_reason in test_cases:
        finding = {
            'path': path,
            'permissions': '777',
            'issue': 'FULL_777',
            'severity': 'CRITICAL',
            'is_directory': False,
            'owner': 'root',
            'group': 'root',
            'uid': 0,
            'gid': 0
        }
        
        suggestion = suggest_safe_permissions(finding)
        
        if suggestion['recommended'] == expected_perm:
            print(f"✅ {path}: {suggestion['recommended']} (PASSED)")
        else:
            print(f"❌ {path}: {suggestion['recommended']} (expected {expected_perm})")
            all_passed = False
        
        # Check reason contains expected text
        if expected_reason.lower() in suggestion['reason'].lower():
            print(f"   Reason: {suggestion['reason'][:50]}...")
        else:
            print(f"❌ Reason mismatch for {path}")
            all_passed = False
    
    return all_passed

if __name__ == "__main__":
    print("Testing fix command functionality...\n")
    
    tests = [
        test_single_fix_dry_run,
        test_safe_permission_suggestion,
        test_world_writable_fix,
        test_special_files
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nResults: {passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)
