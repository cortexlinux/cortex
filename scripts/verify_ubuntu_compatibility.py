import subprocess
import os
import sys
import json
import datetime
import shutil

# File name to store history data
HISTORY_FILE = "security_history.json"

def load_history():
    """Load past execution history"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def save_history(score, status, details):
    """Save execution result to history"""
    history = load_history()
    record = {
        "timestamp": datetime.datetime.now().isoformat(),
        "score": score,
        "status": status,
        "details": details
    }
    history.append(record)
    # Keep only the latest 10 records
    history = history[-10:]
    
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=4)
    
    return history

def show_trend(history):
    """Show historical trend (Trend Tracking)"""
    print("\n=== 📊 Historical Trend Analysis ===")
    if not history:
        print("    No historical data available yet.")
        return

    scores = [h["score"] for h in history]
    avg_score = sum(scores) / len(scores)
    last_score = scores[-1]
    
    print(f"    History Count: {len(history)} runs")
    print(f"    Average Score: {avg_score:.1f}")
    print(f"    Last Run Score: {last_score}")
    
    if len(scores) > 1:
        prev_score = scores[-2]
        diff = last_score - prev_score
        if diff > 0:
            print(f"    Trend: 📈 Improved by {diff} points since previous run")
        elif diff < 0:
            print(f"    Trend: 📉 Dropped by {abs(diff)} points since previous run")
        else:
            print(f"    Trend: ➡️ Stable")

def fix_firewall():
    """Enable Firewall (Automated Fix)"""
    print("\n    [Fixing] Enabling UFW Firewall...")

    # Check if ufw is installed using 'which' or checking path
    # (Since sudo is used, we check if we can find ufw path)
    if not shutil.which("ufw") and not os.path.exists("/usr/sbin/ufw"):
         print("    -> ⚠️ UFW is not installed. Cannot enable.")
         print("       (Try: sudo apt install ufw)")
         return False

    try:
        # Depends on execution environment, sudo might be required
        subprocess.run(["sudo", "ufw", "enable"], check=True)
        print("    -> ✅ Success: Firewall enabled.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"    -> ❌ Failed to enable firewall: {e}")
        return False

def fix_ssh_config(config_path):
    """Disable SSH Root Login (Automated Fix)"""
    print(f"\n    [Fixing] Disabling Root Login in {config_path}...")
    
    # Check if file exists before trying to fix
    if not os.path.exists(config_path):
        print(f"    -> ⚠️ Config file not found: {config_path}")
        return False

    # 1. Create backup
    backup_path = config_path + ".bak." + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    try:
        shutil.copy2(config_path, backup_path)
        print(f"    -> Backup created at: {backup_path}")
    except PermissionError:
        print("    -> ❌ Failed to create backup (Permission denied). Need sudo?")
        return False

    # 2. Rewrite configuration
    try:
        new_lines = []
        with open(config_path, 'r') as f:
            lines = f.readlines()
        
        fixed = False
        for line in lines:
            if line.strip().startswith("PermitRootLogin") and "yes" in line:
                # Comment out and add disabled setting
                new_lines.append(f"# {line.strip()} (Disabled by Auto-Fix)\n")
                new_lines.append("PermitRootLogin no\n")
                fixed = True
            else:
                new_lines.append(line)
        
        if fixed:
            with open(config_path, 'w') as f:
                f.writelines(new_lines)
            print("    -> ✅ Success: sshd_config updated.")
            
            # Attempt to restart SSH service
            print("    -> Restarting sshd service...")
            subprocess.run(["sudo", "systemctl", "restart", "ssh"], check=False)
            return True
        else:
            print("    -> No changes needed.")
            return True

    except PermissionError:
        print("    -> ❌ Failed to write config (Permission denied). Need sudo?")
        return False
    except Exception as e:
        print(f"    -> ❌ Error during fix: {e}")
        return False

def verify_security_logic():
    print("=== Ubuntu Security Logic Verification ===")
    
    # ---------------------------------------------------------
    # 1. Firewall (UFW) Check Logic
    # ---------------------------------------------------------
    print("\n[1] Checking Firewall (UFW)...")
    ufw_active = False
    ufw_needs_fix = False
    try:
        print("    Running: systemctl is-active ufw")
        res = subprocess.run(
            ["systemctl", "is-active", "ufw"], 
            capture_output=True, text=True
        )
        output = res.stdout.strip()
        print(f"    Output: '{output}'")
        
        if res.returncode == 0 and output == "active":
            ufw_active = True
            print("    -> JUDGEMENT: Firewall is ACTIVE (Score: 100)")
        else:
            print("    -> JUDGEMENT: Firewall is INACTIVE (Score: 0)")
            ufw_needs_fix = True
            
    except FileNotFoundError:
        print("    -> ERROR: 'systemctl' command not found.")
    except Exception as e:
        print(f"    -> ERROR: {e}")

    # ---------------------------------------------------------
    # 2. SSH Root Login Check Logic
    # ---------------------------------------------------------
    print("\n[2] Checking SSH Configuration...")
    ssh_config = "/etc/ssh/sshd_config"
    score_penalty = 0
    ssh_needs_fix = False
    
    if os.path.exists(ssh_config):
        print(f"    File found: {ssh_config}")
        try:
            with open(ssh_config, 'r') as f:
                found_risky_setting = False
                for line in f:
                    if line.strip().startswith("PermitRootLogin") and "yes" in line:
                        print(f"    -> FOUND RISKY LINE: {line.strip()}")
                        score_penalty = 50
                        found_risky_setting = True
                        ssh_needs_fix = True
                        break
                
                if not found_risky_setting:
                    print("    -> No 'PermitRootLogin yes' found (Safe)")
                    
        except PermissionError:
            print("    -> ERROR: Permission denied. Try running with 'sudo'.")
    else:
        print(f"    -> WARNING: {ssh_config} does not exist.")

    # ---------------------------------------------------------
    # Final Report & History
    # ---------------------------------------------------------
    print("\n=== Summary ===")
    final_score = 100
    if not ufw_active:
        final_score = 0
    final_score -= score_penalty
    final_score = max(0, final_score)
    
    status = "OK"
    if final_score < 50: status = "CRITICAL"
    elif final_score < 100: status = "WARNING"
    
    print(f"Current Score: {final_score}")
    print(f"Status: {status}")

    # --- Trend Tracking ---
    print("\n... Saving history ...")
    details = []
    if ufw_needs_fix: details.append("Firewall Inactive")
    if ssh_needs_fix: details.append("Root SSH Allowed")
    
    history = save_history(final_score, status, ", ".join(details))
    show_trend(history)

    # ---------------------------------------------------------
    # Automated Fixes (Interactive)
    # ---------------------------------------------------------
    if ufw_needs_fix or ssh_needs_fix:
        print("\n=== 🛠️ Automated Fixes Available ===")
        print("Issues detected that can be automatically fixed.")
        user_input = input("Do you want to apply fixes now? (y/n): ").strip().lower()
        
        if user_input == 'y':
            if ufw_needs_fix:
                fix_firewall()
            if ssh_needs_fix:
                fix_ssh_config(ssh_config)
            
            print("\n✅ Fixes attempt complete. Please re-run script to verify.")
        else:
            print("Skipping fixes.")

if __name__ == "__main__":
    # Warn that sudo might be required for execution
    if os.geteuid() != 0:
        print("NOTE: This script works best with 'sudo' for fixing issues.")
    verify_security_logic()