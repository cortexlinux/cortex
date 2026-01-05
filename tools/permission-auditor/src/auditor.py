#!/usr/bin/env python3
"""
Linux Permission Auditor
Solution for Pain Point #9: Prevent chmod -R 777 security holes

Core features:
1. Scan for 777 and world-writable permissions
2. Explain security risks in plain English
3. Suggest safe permissions based on file type
4. Generate fix commands (safe, not automatic)
5. Docker container support with UID mapping analysis
6. Single command safe fixes with --apply option
"""

import os
import sys
import stat
import pwd
import grp
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# ============================================================================
# CONFIGURATION AND CONSTANTS
# ============================================================================

VERSION = "1.0.0"
AUTHOR = "Security Team"
import json
from pathlib import Path

def load_config(config_path=None):
    """Load configuration from JSON file."""
    default_config = {
        "settings": {
            "default_scan_path": ".",
            "recursive_scan": True,
            "max_depth": 8,
            "exclude_patterns": EXCLUDE_PATHS,
            "safe_permissions": {
                "directories": "755",
                "regular_files": "644",
                "executable_files": "750",
                "sensitive_files": "600"
            }
        }
    }
    
    if config_path and Path(config_path).exists():
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                # Merge with default config
                if 'permission_auditor' in user_config:
                    return user_config['permission_auditor']
        except Exception as e:
            print(f"{Colors.YELLOW}[!] Config error: {e}, using defaults{Colors.END}")
    
    return default_config
    
# ANSI color codes for terminal output
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'

# System paths to exclude from scanning
EXCLUDE_PATHS = [
    '/proc', '/sys', '/dev', '/run',
    '/tmp/.X11-unix', '/tmp/.ICE-unix'
]

# Special files with recommended permissions
SPECIAL_FILES = {
    '/etc/shadow': ('600', 'Password hashes - root only'),
    '/etc/gshadow': ('600', 'Group passwords - root only'),
    '/etc/sudoers': ('440', 'Sudo configuration - root only'),
    '/etc/passwd': ('644', 'User database - readable by all'),
}

# ============================================================================
# SINGLE COMMAND FIX FUNCTIONS (NEW)
# ============================================================================

def apply_single_fix(finding, dry_run=True, backup=True):
    """
    Apply a single fix safely with dry-run mode.
    Returns command and status.
    
    Args:
        finding: Dictionary with file/finding details
        dry_run: If True, only show command, don't execute
        backup: If True, create backup before changing permissions
    
    Returns:
        Dictionary with results
    """
    # Generate fix recommendation
    fix = suggest_safe_permissions(finding)
    path = finding['path']
    
    # Validate path exists
    if not os.path.exists(path):
        return {
            'status': 'ERROR',
            'command': fix['command'],
            'message': f'Path does not exist: {path}',
            'safe_to_apply': False
        }
    
    # Check if it's a system critical file
    if path in ['/etc/shadow', '/etc/gshadow', '/etc/sudoers', '/etc/passwd']:
        return {
            'status': 'WARNING',
            'command': fix['command'],
            'message': f'System critical file: {path}. Manual intervention recommended.',
            'safe_to_apply': False
        }
    
    # Check current permissions match what we expect
    try:
        current_perms = oct(os.stat(path).st_mode & 0o777)[-3:]
        if current_perms != finding.get('permissions_octal', finding.get('permissions', '000')):
            return {
                'status': 'WARNING',
                'command': fix['command'],
                'message': f'Permissions changed since scan: {current_perms} != {finding.get("permissions", "unknown")}',
                'safe_to_apply': False
            }
    except OSError:
        return {
            'status': 'ERROR',
            'command': fix['command'],
            'message': f'Cannot access file: {path}',
            'safe_to_apply': False
        }
    
    # Build the actual command
    actual_command = fix['command']
    needs_sudo = 'sudo' in actual_command
    
    # Check permissions for execution
    if needs_sudo and os.geteuid() != 0:
        if dry_run:
            return {
                'status': 'DRY_RUN_NEEDS_SUDO',
                'command': actual_command,
                'message': f'Would need sudo to execute. Command: {actual_command}',
                'safe_to_apply': True,
                'needs_sudo': True
            }
        else:
            return {
                'status': 'NEEDS_SUDO',
                'command': actual_command,
                'message': 'Need sudo privileges to execute. Run with sudo or as root.',
                'safe_to_apply': True,
                'needs_sudo': True
            }
    
    # If we're root and command has sudo, remove it
    if needs_sudo and os.geteuid() == 0:
        actual_command = actual_command.replace('sudo ', '')
    
    # For dry run, just return the command
    if dry_run:
        return {
            'status': 'DRY_RUN',
            'command': actual_command,
            'message': f'This would execute: {actual_command}',
            'safe_to_apply': True,
            'backup_created': False if dry_run else backup
        }
    
    # ===== ACTUAL EXECUTION =====
    backup_path = None
    
    try:
        # Create backup if requested
        if backup and os.path.isfile(path):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{path}.perm-backup-{timestamp}"
            try:
                import shutil
                shutil.copy2(path, backup_path)
                # Set safe permissions on backup
                os.chmod(backup_path, 0o600)
                backup_created = True
            except Exception as e:
                backup_created = False
                backup_error = str(e)
        else:
            backup_created = False
        
        # Execute the permission change
        result = subprocess.run(
            actual_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Verify the change was successful
        if result.returncode == 0:
            new_perms = oct(os.stat(path).st_mode & 0o777)[-3:]
            
            return {
                'status': 'APPLIED',
                'command': actual_command,
                'exit_code': result.returncode,
                'output': result.stdout,
                'error': result.stderr,
                'old_permissions': finding.get('permissions', 'unknown'),
                'new_permissions': new_perms,
                'backup_created': backup_created,
                'backup_path': backup_path if backup_created else None,
                'verified': new_perms == fix['recommended'],
                'message': f'Successfully changed permissions from {finding.get("permissions", "unknown")} to {new_perms}'
            }
        else:
            # Command failed
            error_msg = result.stderr.strip() or "Unknown error"
            
            # Attempt to restore from backup if we created one
            if backup_created and backup_path and os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, path)
                    restore_msg = f" Restored from backup: {backup_path}"
                except Exception as restore_error:
                    restore_msg = f" Failed to restore from backup: {restore_error}"
            else:
                restore_msg = ""
            
            return {
                'status': 'FAILED',
                'command': actual_command,
                'exit_code': result.returncode,
                'output': result.stdout,
                'error': error_msg,
                'backup_created': backup_created,
                'restore_attempted': backup_created,
                'message': f'Failed to apply fix: {error_msg}{restore_msg}'
            }
            
    except subprocess.TimeoutExpired:
        return {
            'status': 'TIMEOUT',
            'command': actual_command,
            'message': 'Command timed out after 30 seconds',
            'backup_created': backup_created if 'backup_created' in locals() else False
        }
    except Exception as e:
        return {
            'status': 'ERROR',
            'command': actual_command,
            'message': f'Error applying fix: {str(e)}',
            'backup_created': backup_created if 'backup_created' in locals() else False
        }

def apply_bulk_fixes(findings, dry_run=True, backup=True, interactive=False):
    """
    Apply multiple fixes safely.
    
    Args:
        findings: List of finding dictionaries
        dry_run: If True, only show what would be done
        backup: If True, create backups before changing
        interactive: If True, ask for confirmation for each fix
    
    Returns:
        Dictionary with summary results
    """
    if not findings:
        return {
            'total': 0,
            'applied': 0,
            'failed': 0,
            'skipped': 0,
            'results': []
        }
    
    results = []
    applied = 0
    failed = 0
    skipped = 0
    
    print(f"{Colors.BLUE}[*] Applying {len(findings)} fixes...{Colors.END}")
    
    for i, finding in enumerate(findings, 1):
        path = finding['path']
        severity = finding['severity']
        
        if interactive:
            print(f"\n{i}. {path} ({severity} - {finding['permissions']})")
            fix = suggest_safe_permissions(finding)
            print(f"   Fix: {fix['command']}")
            print(f"   Reason: {fix['reason']}")
            
            if not dry_run:
                response = input(f"   Apply this fix? (y/N/skip): ").strip().lower()
                if response not in ['y', 'yes']:
                    print(f"   {Colors.YELLOW}Skipped{Colors.END}")
                    results.append({
                        'status': 'SKIPPED',
                        'path': path,
                        'message': 'User skipped during interactive mode'
                    })
                    skipped += 1
                    continue
        
        # Apply the fix
        result = apply_single_fix(finding, dry_run=dry_run, backup=backup)
        result['path'] = path
        result['severity'] = severity
        results.append(result)
        
        # Update counters
        if result['status'] == 'APPLIED':
            applied += 1
            if not dry_run:
                print(f"{Colors.GREEN}✅ {i}/{len(findings)} Applied: {path}{Colors.END}")
        elif result['status'] in ['FAILED', 'ERROR', 'TIMEOUT']:
            failed += 1
            if not dry_run:
                print(f"{Colors.RED}❌ {i}/{len(findings)} Failed: {path}{Colors.END}")
                if result.get('message'):
                    print(f"   Reason: {result['message']}")
        elif result['status'] == 'DRY_RUN':
            print(f"{Colors.CYAN}📋 {i}/{len(findings)} Would apply: {path}{Colors.END}")
            print(f"   Command: {result['command']}")
    
    return {
        'total': len(findings),
        'applied': applied,
        'failed': failed,
        'skipped': skipped,
        'dry_run': dry_run,
        'results': results
    }
def apply_selected_fixes(findings, indices, dry_run=True):
    """
    Apply multiple fixes based on selection.
    """
    results = []
    for idx in indices:
        if 0 <= idx < len(findings):
            result = apply_single_fix(findings[idx], dry_run)
            result['finding_index'] = idx
            result['path'] = findings[idx]['path']
            results.append(result)
    
    return results
def interactive_fix_mode(findings):
    """
    Interactive mode to apply fixes one by one.
    """
    print(f"{Colors.CYAN}\n🛠️  INTERACTIVE FIX MODE{Colors.END}")
    print(f"{Colors.YELLOW}You can apply fixes individually.{Colors.END}\n")
    
    for i, finding in enumerate(findings, 1):
        print(f"{i}. {finding['path']} ({finding['permissions']})")
    
    print("\nEnter numbers to fix (comma-separated), 'a' for all, or 'q' to quit:")
    
    while True:
        try:
            choice = input("> ").strip()
            if choice.lower() == "q":
                return []
            elif choice.lower() == "a":
                return list(range(len(findings)))
            else:
                indices = [int(x.strip()) - 1 for x in choice.split(",") if x.strip().isdigit()]
                valid_indices = [i for i in indices if 0 <= i < len(findings)]
                if valid_indices:
                    return valid_indices
                else:
                    print("Invalid selection. Try again.")
        except ValueError:
            print("Please enter numbers separated by commas.")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return []

# ============================================================================
# CORE PERMISSION CHECKING FUNCTIONS
# ============================================================================

def check_file_permissions(filepath: str):
    """
    Check a file or directory for dangerous permissions.
    Returns dictionary with issue details or None if safe.
    """
    try:
        # Get file statistics
        st = os.stat(filepath)
        mode = st.st_mode
        permissions = stat.S_IMODE(mode)
        
        # Get owner and group information
        uid = st.st_uid
        gid = st.st_gid
        
        try:
            owner = pwd.getpwuid(uid).pw_name
        except KeyError:
            owner = f"uid:{uid}"
            
        try:
            group = grp.getgrgid(gid).gr_name
        except KeyError:
            group = f"gid:{gid}"
        
        # Check 1: Full 777 permissions (rwxrwxrwx)
        if permissions == 0o777:
            return {
                'path': filepath,
                'permissions': '777',
                'permissions_octal': oct(permissions)[-3:],
                'issue': 'FULL_777',
                'severity': 'CRITICAL',
                'is_directory': stat.S_ISDIR(mode),
                'owner': owner,
                'group': group,
                'uid': uid,
                'gid': gid,
                'size': st.st_size,
            }
        
        # Check 2: World-writable (others can write)
        if permissions & 0o002:
            return {
                'path': filepath,
                'permissions': oct(permissions)[-3:],
                'permissions_octal': oct(permissions)[-3:],
                'issue': 'WORLD_WRITABLE',
                'severity': 'HIGH',
                'is_directory': stat.S_ISDIR(mode),
                'owner': owner,
                'group': group,
                'uid': uid,
                'gid': gid,
                'size': st.st_size,
            }
        
        # Check 3: World-readable sensitive files
        if permissions & 0o004:  # others can read
            # Check if this is a sensitive system file
            sensitive_files = ['/etc/shadow', '/etc/gshadow', '/etc/sudoers']
            if filepath in sensitive_files:
                return {
                    'path': filepath,
                    'permissions': oct(permissions)[-3:],
                    'permissions_octal': oct(permissions)[-3:],
                    'issue': 'SENSITIVE_WORLD_READABLE',
                    'severity': 'MEDIUM',
                    'is_directory': False,
                    'owner': owner,
                    'group': group,
                    'uid': uid,
                    'gid': gid,
                    'size': st.st_size,
                }
    
    except (PermissionError, FileNotFoundError, OSError):
        # Cannot access the file, skip it
        return None
    
    return None

def should_skip_path(path: str) -> bool:
    """Check if path should be excluded from scanning."""
    abs_path = os.path.abspath(path)
    
    for excluded in EXCLUDE_PATHS:
        if abs_path.startswith(excluded):
            return True
    
    return False

def scan_directory(root_path: str, recursive: bool = True, max_depth: int = 8):
    """
    Scan a directory for permission issues.
    Returns list of findings.
    """
    findings = []
    
    # === FIX: First check the root path itself ===
    if os.path.exists(root_path):
        root_finding = check_file_permissions(root_path)
        if root_finding:
            findings.append(root_finding)
    # === END FIX ===
    
    def _scan(current_path: str, depth: int = 0):
        if depth > max_depth:
            return
        
        # Skip excluded paths
        if should_skip_path(current_path):
            return
        
        # If directory and recursive scanning enabled
        if recursive and os.path.isdir(current_path):
            try:
                # Scan directory contents
                for entry in os.listdir(current_path):
                    # Skip special entries
                    if entry in ['.', '..']:
                        continue
                    
                    full_path = os.path.join(current_path, entry)
                    
                    # === FIX: Check each file/directory ===
                    finding = check_file_permissions(full_path)
                    if finding:
                        findings.append(finding)
                    # === END FIX ===
                    
                    # Recurse if it's a directory
                    if os.path.isdir(full_path):
                        _scan(full_path, depth + 1)
                        
            except (PermissionError, OSError):
                # No permission to read directory
                pass
    
    # Start recursive scanning if needed
    if recursive:
        _scan(root_path)
    return findings

# ============================================================================
# EXPLANATION AND RECOMMENDATION FUNCTIONS
# ============================================================================

def explain_issue(finding: dict) -> str:
    """
    Generate human-readable explanation of the permission issue.
    """
    issue_type = finding['issue']
    path = finding['path']
    perms = finding['permissions']
    owner = finding['owner']
    group = finding['group']
    is_dir = finding['is_directory']
    
    if issue_type == 'FULL_777':
        return f"""{Colors.RED}{Colors.BOLD}🚨 CRITICAL SECURITY RISK:{Colors.END}
   Path: {path}
   Permissions: {perms} (rwxrwxrwx)
   Type: {'Directory' if is_dir else 'File'}
   Owner: {owner}, Group: {group}

   {Colors.YELLOW}WHY THIS IS DANGEROUS:{Colors.END}
   • ANY user on the system can read, modify, or delete this
   • Common cause: Using 'chmod -R 777' as a quick fix
   • Can lead to data theft, malware injection, or system compromise
   • Violates the principle of least privilege"""
    
    elif issue_type == 'WORLD_WRITABLE':
        return f"""{Colors.YELLOW}{Colors.BOLD}⚠️  HIGH SECURITY RISK:{Colors.END}
   Path: {path}
   Permissions: {perms}
   Type: {'Directory' if is_dir else 'File'}
   Owner: {owner}, Group: {group}

   {Colors.YELLOW}WHY THIS IS DANGEROUS:{Colors.END}
   • Any user can modify this file, even if they cannot read it
   • Can be used to inject malicious code or corrupt data
   • Often exploited in privilege escalation attacks
   • Allows unauthorized data modification"""
    
    else:  # SENSITIVE_WORLD_READABLE
        return f"""{Colors.MAGENTA}{Colors.BOLD}🔒 MEDIUM SECURITY RISK:{Colors.END}
   Path: {path}
   Permissions: {perms}
   This is a sensitive system file!

   {Colors.YELLOW}WHY THIS IS DANGEROUS:{Colors.END}
   • Password hashes or sensitive configurations are readable by all users
   • Can lead to password cracking attacks
   • Violates system security policies
   • Information disclosure risk"""

def suggest_safe_permissions(finding: dict) -> dict:
    """
    Suggest safe permissions based on file type and location.
    Returns dictionary with recommendation details.
    """
    path = finding['path']
    is_dir = finding['is_directory']
    
    # Check for special files first
    for special_path, (recommended, reason) in SPECIAL_FILES.items():
        if path == special_path:
            return {
                'recommended': recommended,
                'reason': reason,
                'command': f"sudo chmod {recommended} '{path}'",
                'risk_reduction': 'CRITICAL/HIGH → LOW',
                'needs_sudo': True
            }
    
    # Get owner and group for chown command if needed
    owner = finding.get('owner', '')
    group = finding.get('group', '')
    
    # General recommendations with ownership consideration
    if is_dir:
        if path.startswith('/home/') or '/home/' in path:
            # Home directories
            recommended = '750'
            reason = 'Home directory: owner full access, group can list, others no access'
            chown_cmd = f"sudo chown {owner}:{group} '{path}' && sudo chmod {recommended} '{path}'" if owner and group else f"sudo chmod {recommended} '{path}'"
        else:
            # System directories
            recommended = '755'
            reason = 'Directory: owner can read/write/execute, group/others can read/execute'
            chown_cmd = f"sudo chmod {recommended} '{path}'"
    else:
        # Check file type and content
        is_executable = False
        is_config = False
        is_log = False
        
        # Check by file extension and path patterns
        filename = os.path.basename(path).lower()
        dir_path = os.path.dirname(path).lower()
        
        # Common binary directories
        binary_dirs = ['/bin', '/sbin', '/usr/bin', '/usr/sbin', '/usr/local/bin', '/usr/local/sbin']
        
        # Check if file is in a binary directory
        if any(dir_path.startswith(binary_dir) for binary_dir in binary_dirs):
            is_executable = True
        
        # Check by file extension
        ext = Path(path).suffix.lower()
        if not is_executable:
            if ext in ['.sh', '.py', '.pl', '.rb', '.exe', '.bin', '.run', '']:
                is_executable = True
            elif ext in ['.conf', '.cfg', '.ini', '.yml', '.yaml', '.json', '.xml', '.properties']:
                is_config = True
            elif ext in ['.log', '.txt', '.out', '.err']:
                is_log = True
        
        # Check by filename patterns
        if not any([is_executable, is_config, is_log]):
            if any(pattern in filename for pattern in ['script', 'run', 'start', 'stop', 'install', 'update']):
                is_executable = True
            elif any(pattern in filename for pattern in ['config', 'conf', 'settings', '.conf', '.cfg']):
                is_config = True
            elif any(pattern in filename for pattern in ['log', 'debug', 'error', 'trace']):
                is_log = True
        
        # If file exists, check actual content
        if os.path.exists(path) and not is_executable:
            try:
                # Check if file is executable
                if os.access(path, os.X_OK):
                    is_executable = True
                else:
                    # Check for shebang
                    with open(path, 'rb') as f:
                        first_bytes = f.read(2)
                        if first_bytes == b'#!':
                            is_executable = True
            except:
                pass
        
        # Determine recommendation
        if is_executable:
            recommended = '750'
            reason = 'Executable script/binary: owner can read/write/execute, group can read/execute, others have no access'
        elif is_config:
            recommended = '640'
            reason = 'Configuration file: owner can read/write, group can read, others have no access'
        elif is_log:
            recommended = '640'
            reason = 'Log file: owner can read/write, group can read (for log rotation), others have no access'
        else:
            recommended = '644'
            reason = 'Regular file: owner can read/write, group/others can read only'
        
        chown_cmd = f"sudo chmod {recommended} '{path}'"
    
    # Determine if sudo is needed (check current user vs file owner)
    needs_sudo = False
    try:
        current_uid = os.geteuid()
        file_uid = finding.get('uid', 0)
        if current_uid != 0 and current_uid != file_uid:
            needs_sudo = True
    except:
        needs_sudo = True
    
    # Build command with or without sudo
    if needs_sudo:
        command = f"sudo chmod {recommended} '{path}'"
    else:
        command = f"chmod {recommended} '{path}'"
    
    # Determine risk reduction
    if finding['issue'] == 'FULL_777':
        risk_reduction = 'CRITICAL → LOW'
    elif finding['issue'] == 'WORLD_WRITABLE':
        risk_reduction = 'HIGH → LOW'
    else:
        risk_reduction = 'MEDIUM → LOW'
    
    return {
        'recommended': recommended,
        'reason': reason,
        'command': command,
        'risk_reduction': risk_reduction,
        'needs_sudo': needs_sudo,
        'chown_command': chown_cmd if 'chown_cmd' in locals() else None
    }

# ============================================================================
# DOCKER/CONTAINER SUPPORT
# ============================================================================

def check_docker_available() -> bool:
    """Check if Docker is installed and running."""
    try:
        result = subprocess.run(['docker', '--version'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def scan_docker_containers():
    """Scan running Docker containers for permission issues."""
    if not check_docker_available():
        return []
    
    findings = []
    
    try:
        # Get list of running containers
        cmd = ['docker', 'ps', '--format', '{{.Names}}']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            return []
        
        containers = [name for name in result.stdout.strip().split('\n') if name]
        
        # Limit to 3 containers for performance
        for container in containers[:3]:
            # Find files with 777 permissions in container
            find_cmd = f"docker exec {container} find / -type f -perm 0777 2>/dev/null | head -10"
            
            try:
                result = subprocess.run(
                    find_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.stdout:
                    for file_path in result.stdout.strip().split('\n'):
                        if file_path:
                            findings.append({
                                'path': file_path,
                                'permissions': '777',
                                'issue': 'FULL_777',
                                'severity': 'CRITICAL',
                                'is_directory': False,
                                'owner': 'unknown',
                                'group': 'unknown',
                                'container': container,
                                'note': 'Inside Docker container'
                            })
                            
            except subprocess.TimeoutExpired:
                # Container scan timed out
                pass
    
    except Exception as e:
        # Docker scan failed
        pass
    
    return findings

def analyze_container_uid_mapping(container_name, host_uid):
    """
    Complete UID/GID mapping analysis between host and container.
    Returns recommendations for secure Docker user mapping.
    """
    recommendations = []
    
    try:
        # Get user information in container
        cmd = f"docker exec {container_name} getent passwd {host_uid} 2>/dev/null || echo 'not found'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if "not found" in result.stdout:
            recommendations.append({
                'issue': 'UID_NOT_IN_CONTAINER',
                'severity': 'HIGH',
                'message': f'UID {host_uid} does not exist inside container {container_name}',
                'fix': f'Add user in Dockerfile: RUN useradd -u {host_uid} -g {host_uid} appuser'
            })
        
        # Check subuid/subgid mapping
        if os.path.exists('/etc/subuid'):
            with open('/etc/subuid', 'r') as f:
                for line in f:
                    if str(host_uid) in line:
                        recommendations.append({
                            'issue': 'USER_NAMESPACE_MAPPED',
                            'severity': 'INFO',
                            'message': f'UID {host_uid} has user namespace mapping',
                            'fix': 'Docker uses user namespace for isolation'
                        })
                        break
        
        # Check container user
        cmd = f"docker inspect {container_name} --format='{{{{.Config.User}}}}'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        container_user = result.stdout.strip()
        
        if container_user and container_user != str(host_uid):
            recommendations.append({
                'issue': 'CONTAINER_USER_MISMATCH',
                'severity': 'MEDIUM',
                'message': f'Container runs as {container_user}, but files belong to UID {host_uid}',
                'fix': f'Run container: docker run --user {host_uid}:{host_uid} ...'
            })
    
    except Exception as e:
        recommendations.append({
            'issue': 'MAPPING_ANALYSIS_ERROR',
            'severity': 'WARNING',
            'message': f'UID mapping analysis error: {str(e)}',
            'fix': 'Check user mapping manually'
        })
    
    return recommendations

def analyze_uid_mapping(finding: dict) -> str:
    """
    Analyze UID/GID mapping for Docker containers.
    Provides recommendations for proper user mapping.
    """
    uid = finding.get('uid', 0)
    gid = finding.get('gid', 0)
    
    analysis = []
    analysis.append(f"{Colors.BLUE}🔧 UID/GID MAPPING ANALYSIS:{Colors.END}")
    analysis.append(f"  File owner UID: {uid}, GID: {gid}")
    
    # Check if UID exists on host
    try:
        user_info = pwd.getpwuid(uid)
        analysis.append(f"  On host system: User '{user_info.pw_name}' (UID:{uid})")
    except KeyError:
        analysis.append(f"  {Colors.YELLOW}Warning: UID {uid} not found in /etc/passwd{Colors.END}")
        analysis.append(f"  This can cause permission issues with mounted volumes")
    
    # Security warning for root
    if uid == 0:
        analysis.append(f"  {Colors.RED}Security Warning: Running as root (UID 0){Colors.END}")
        analysis.append(f"  This violates security best practices")
    
    # Docker recommendations
    analysis.append(f"\n  {Colors.GREEN}DOCKER BEST PRACTICES:{Colors.END}")
    analysis.append(f"  # Run container with specific user:")
    analysis.append(f"  docker run --user {uid}:{gid} \\")
    analysis.append(f"      -v /host/path:/container/path:z \\")
    analysis.append(f"      your-image")
    
    if uid >= 1000:  # Regular user UID
        analysis.append(f"\n  # In Dockerfile:")
        analysis.append(f"  RUN groupadd -g {gid} appgroup && \\")
        analysis.append(f"      useradd -u {uid} -g {gid} -m appuser")
        analysis.append(f"  USER appuser")
    
    return "\n".join(analysis)

# ============================================================================
# REPORT GENERATION
# ============================================================================

def generate_text_report(findings: list, docker_findings: list = None) -> str:
    """Generate human-readable text report."""
    report = []
    
    # Header
    report.append(f"{Colors.CYAN}{'='*80}{Colors.END}")
    report.append(f"{Colors.BOLD}🔐 LINUX PERMISSION AUDIT REPORT{Colors.END}")
    report.append(f"{Colors.CYAN}{'='*80}{Colors.END}")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Tool: Permission Auditor v{VERSION}")
    report.append(f"")
    
    # Statistics
    total_issues = len(findings) + (len(docker_findings) if docker_findings else 0)
    
    report.append(f"{Colors.BOLD}📊 SCAN SUMMARY:{Colors.END}")
    report.append(f"  Total issues found: {total_issues}")
    
    if total_issues == 0:
        report.append(f"\n{Colors.GREEN}✅ No security issues found!{Colors.END}")
        report.append(f"Your system follows security best practices.")
        report.append(f"{Colors.CYAN}{'='*80}{Colors.END}")
        return "\n".join(report)
    
    # Count by severity
    severity_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0}
    
    for finding in findings:
        severity_counts[finding['severity']] += 1
    
    if docker_findings:
        for finding in docker_findings:
            severity_counts[finding['severity']] += 1
    
    for severity, color in [('CRITICAL', Colors.RED), ('HIGH', Colors.YELLOW), ('MEDIUM', Colors.MAGENTA)]:
        if severity_counts[severity] > 0:
            report.append(f"  {color}{severity}: {severity_counts[severity]}{Colors.END}")
    
    report.append(f"")
    
    # Detailed findings
    report.append(f"{Colors.BOLD}🔍 DETAILED FINDINGS:{Colors.END}")
    report.append(f"")
    
    issue_num = 1
    
    # File system findings
    for finding in findings:
        report.append(f"{issue_num}. {explain_issue(finding)}\n")
        
        fix = suggest_safe_permissions(finding)
        report.append(f"   {Colors.GREEN}✅ RECOMMENDED FIX:{Colors.END}")
        report.append(f"   Command: {fix['command']}")
        report.append(f"   Reason: {fix['reason']}")
        report.append(f"   Risk reduction: {fix['risk_reduction']}\n")
        
        # UID analysis for Docker context
        if finding.get('uid', 0) != 0:
            report.append(f"{analyze_uid_mapping(finding)}\n")
        
        report.append(f"{Colors.CYAN}{'-'*60}{Colors.END}\n")
        issue_num += 1
    
    # Docker findings
    if docker_findings:
        report.append(f"{Colors.BOLD}🐳 DOCKER CONTAINER FINDINGS:{Colors.END}\n")
        
        for finding in docker_findings:
            report.append(f"{issue_num}. {explain_issue(finding)}")
            report.append(f"   Container: {finding.get('container', 'unknown')}\n")
            
            fix = suggest_safe_permissions(finding)
            report.append(f"   {Colors.GREEN}✅ RECOMMENDED FIX:{Colors.END}")
            fix_cmd = f"docker exec {finding.get('container')} chmod {fix['recommended']} {finding['path']}"
            report.append(f"   Command: {fix_cmd}")
            report.append(f"   Note: Apply inside container or rebuild Docker image\n")
            
            report.append(f"{Colors.CYAN}{'-'*60}{Colors.END}\n")
            issue_num += 1
    
    # Security best practices
    report.append(f"{Colors.BOLD}📝 SECURITY BEST PRACTICES:{Colors.END}")
    report.append(f"  1. {Colors.RED}NEVER{Colors.END} use 'chmod -R 777' as a quick fix")
    report.append(f"  2. Directories should use 755 permissions (drwxr-xr-x)")
    report.append(f"  3. Regular files should use 644 permissions (-rw-r--r--)")
    report.append(f"  4. Scripts should use 750 permissions (-rwxr-x---)")
    report.append(f"  5. Sensitive files should use 600 permissions (-rw-------)")
    report.append(f"  6. In Docker, always use non-root users when possible")
    report.append(f"  7. Regularly audit permissions with this tool")
    
    # Disclaimer
    report.append(f"\n{Colors.YELLOW}⚠️  IMPORTANT DISCLAIMER:{Colors.END}")
    report.append(f"  This tool only identifies potential security issues.")
    report.append(f"  Always review and test fixes in a safe environment")
    report.append(f"  before applying to production systems.")
    
    report.append(f"{Colors.CYAN}{'='*80}{Colors.END}")
    
    return "\n".join(report)

def generate_json_report(findings: list, docker_findings: list = None) -> str:
    """Generate JSON report for programmatic use."""
    report = {
        'metadata': {
            'tool': 'Linux Permission Auditor',
            'version': VERSION,
            'timestamp': datetime.now().isoformat(),
            'purpose': 'Identify dangerous file permissions'
        },
        'summary': {
            'total_issues': len(findings) + (len(docker_findings) if docker_findings else 0),
            'filesystem_issues': len(findings),
            'docker_issues': len(docker_findings) if docker_findings else 0,
        },
        'findings': findings,
        'docker_findings': docker_findings if docker_findings else [],
        'recommendations': [
            "Never use 'chmod -R 777' as a quick fix",
            "Use principle of least privilege for permissions",
            "Regularly audit file permissions",
            "Use non-root users in Docker containers"
        ]
    }
    
    return json.dumps(report, indent=2, ensure_ascii=False)

# ============================================================================
# MAIN FUNCTION WITH --apply SUPPORT
# ============================================================================

def print_banner():
    """Print application banner."""
    banner = f"""
{Colors.CYAN}{Colors.BOLD}
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║      🔒 LINUX PERMISSION AUDITOR v{VERSION}             ║
║      Solution for Pain Point #9: chmod -R 777           ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
{Colors.END}
    """
    print(banner)

def main():
    """Main function - parse arguments and run audit."""
    parser = argparse.ArgumentParser(
        description=f'Linux Permission Auditor v{VERSION} - Find and fix dangerous permissions',
        epilog='''Examples:
  python auditor.py /var/www                    # Basic scan
  python auditor.py /home -r --fix              # Recursive with fixes
  python auditor.py /path --apply               # Apply fixes (careful!)
  python auditor.py --docker --interactive      # Interactive Docker mode
  python auditor.py /etc --json                 # JSON output''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Добавим информацию о версии в аргументы
    parser.add_argument('--version', action='version', version=f'%(prog)s {VERSION}')
    
    parser.add_argument('path', nargs='?', default='.',
                       help='Path to scan (default: current directory)')
    parser.add_argument('-r', '--recursive', action='store_true',
                       help='Scan recursively')
    parser.add_argument('-d', '--docker', action='store_true',
                       help='Scan Docker containers')
    parser.add_argument('-f', '--fix', action='store_true',
                       help='Show fix commands (does not apply automatically)')
    parser.add_argument('-a', '--apply', action='store_true',
                       help='Apply fixes (use with caution!)')
    parser.add_argument('-i', '--interactive', action='store_true',
                       help='Interactive fix selection mode')
    parser.add_argument('-j', '--json', action='store_true',
                       help='Output in JSON format')
    parser.add_argument('-o', '--output',
                       help='Save report to file')
    
    args = parser.parse_args()
       
    # Print banner
    print_banner()
    
    # Validate path
    if not os.path.exists(args.path):
        print(f"{Colors.RED}[!] Error: Path '{args.path}' does not exist{Colors.END}")
        sys.exit(1)
    
    print(f"{Colors.BLUE}[*] Starting permission audit...{Colors.END}")
    print(f"    Target: {args.path}")
    print(f"    Recursive: {args.recursive}")
    print(f"    Docker scan: {args.docker}")
    print(f"    Apply fixes: {args.apply}")
    print(f"    Interactive: {args.interactive}")
    print(f"")
    
    # Scan filesystem
    findings = scan_directory(args.path, args.recursive)
    
    # Scan Docker containers if requested
    docker_findings = []
    if args.docker:
        docker_findings = scan_docker_containers()
    
    # Handle --apply option
    if args.apply:
        if not findings and not docker_findings:
            print(f"{Colors.GREEN}[+] No issues found, nothing to apply.{Colors.END}")
            sys.exit(0)
        
        print(f"{Colors.YELLOW}{'!'*80}{Colors.END}")
        print(f"{Colors.RED}{Colors.BOLD}⚠️  WARNING: PERMISSION MODIFICATION MODE{Colors.END}")
        print(f"{Colors.YELLOW}This will change file permissions on your system.{Colors.END}")
        print(f"{Colors.YELLOW}{'!'*80}{Colors.END}")
        
        all_findings = findings + docker_findings
        
        # Show summary
        print(f"\n{Colors.BLUE}[*] Found {len(all_findings)} issues to fix:{Colors.END}")
        for i, finding in enumerate(all_findings, 1):
            print(f"  {i}. {finding['path']} ({finding['severity']} - {finding['permissions']})")
        
        # Get user confirmation
        if not args.interactive:
            print(f"\n{Colors.YELLOW}You are about to modify {len(all_findings)} files.{Colors.END}")
            print(f"{Colors.YELLOW}Backups will be created for regular files.{Colors.END}")
            confirm = input(f"\nType 'APPLY' to continue, or anything else to cancel: ").strip()
            if confirm != 'APPLY':
                print(f"{Colors.YELLOW}[!] Application cancelled.{Colors.END}")
                sys.exit(0)
        
        # Apply fixes
        if args.interactive:
            # Interactive mode - fix one by one
            print(f"\n{Colors.CYAN}[*] Interactive fix mode{Colors.END}")
            print(f"{Colors.YELLOW}You will be asked for each file individually.{Colors.END}")
            
            results = apply_bulk_fixes(
                all_findings, 
                dry_run=False, 
                backup=True, 
                interactive=True
            )
        else:
            # Batch mode - apply all
            print(f"\n{Colors.BLUE}[*] Applying all fixes in batch mode...{Colors.END}")
            results = apply_bulk_fixes(
                all_findings, 
                dry_run=False, 
                backup=True, 
                interactive=False
            )
        
        # Show results
        print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}📊 FIX APPLICATION RESULTS:{Colors.END}")
        print(f"{Colors.CYAN}{'='*60}{Colors.END}")
        
        print(f"Total files: {results['total']}")
        print(f"Successfully applied: {Colors.GREEN}{results['applied']}{Colors.END}")
        print(f"Failed: {Colors.RED}{results['failed']}{Colors.END}")
        print(f"Skipped: {Colors.YELLOW}{results['skipped']}{Colors.END}")
        
        # Show backup information
        backups = [r for r in results['results'] if r.get('backup_created')]
        if backups:
            print(f"\n{Colors.GREEN}✅ Backups created for {len(backups)} files:{Colors.END}")
            for backup in backups[:5]:  # Show first 5 backups
                print(f"  • {backup['path']} -> {backup.get('backup_path', 'unknown')}")
            if len(backups) > 5:
                print(f"  ... and {len(backups) - 5} more")
        
        # Show failed fixes
        failures = [r for r in results['results'] if r['status'] in ['FAILED', 'ERROR']]
        if failures:
            print(f"\n{Colors.RED}❌ Failed fixes:{Colors.END}")
            for fail in failures:
                print(f"  • {fail['path']}: {fail.get('message', 'Unknown error')}")
        
        # Exit with appropriate code
        if results['failed'] > 0:
            print(f"\n{Colors.YELLOW}[!] Some fixes failed. Check output above.{Colors.END}")
            sys.exit(1)
        else:
            print(f"\n{Colors.GREEN}[+] All fixes applied successfully!{Colors.END}")
            sys.exit(0)
    
    # Generate report
    if args.json:
        report = generate_json_report(findings, docker_findings)
    else:
        report = generate_text_report(findings, docker_findings)
    
    # Output report
    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"{Colors.GREEN}[+] Report saved to: {args.output}{Colors.END}")
        except Exception as e:
            print(f"{Colors.RED}[!] Error saving report: {e}{Colors.END}")
            print(report)
    else:
        print(report)
    
    # Interactive mode without --apply
    if args.interactive and not args.apply and (findings or docker_findings):
        print(f"\n{Colors.CYAN}[*] Entering interactive mode...{Colors.END}")
        all_findings = findings + docker_findings
        indices = interactive_fix_mode(all_findings)
        
        if indices:
            print(f"\n{Colors.BLUE}[*] Preview of {len(indices)} fixes (dry run):{Colors.END}")
            # Fix: add missing function import or implementation
            from auditor import apply_selected_fixes
            results = apply_selected_fixes(all_findings, indices, dry_run=True)
            
            for result in results:
                print(f"\n{result['path']}:")
                print(f"  Command: {result['command']}")
                print(f"  Status: {result['status']}")
                if result.get('message'):
                    print(f"  Note: {result['message']}")
            
            print(f"\n{Colors.YELLOW}[!] To apply these fixes, run with --apply flag{Colors.END}")
            print(f"    Example: python auditor.py {args.path} --apply --interactive")
    
    # Security warning for fix mode
    if args.fix and (findings or docker_findings):
        print(f"\n{Colors.YELLOW}{'!'*80}{Colors.END}")
        print(f"{Colors.RED}{Colors.BOLD}⚠️  SECURITY WARNING:{Colors.END}")
        print(f"{Colors.YELLOW}This tool shows fix commands for educational purposes.")
        print(f"Always review and understand commands before executing.")
        print(f"Test in a development environment before production.")
        print(f"Never execute commands without understanding their impact.{Colors.END}")
        print(f"{Colors.YELLOW}{'!'*80}{Colors.END}")
    
    # Exit with appropriate code
    total_issues = len(findings) + len(docker_findings)
    if total_issues > 0:
        sys.exit(1)  # Exit with error if issues found
    else:
        sys.exit(0)  # Exit successfully if no issues

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}[!] Audit interrupted by user{Colors.END}")
        sys.exit(130)
    except Exception as e:
        print(f"{Colors.RED}[!] Unexpected error: {e}{Colors.END}")
        sys.exit(1)
