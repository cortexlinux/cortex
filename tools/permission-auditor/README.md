# 🔐 Linux Permission Auditor

**Solution to prevent `chmod -R 777` security holes**

## 🎯 The Problem

System administrators and developers often "fix" permission issues with the dangerous `chmod -R 777` command, creating massive security vulnerabilities.
This tool helps identify and safely fix such problems.

## ✨ Features

- ✅ **Dangerous permission detection**: Find 777 and world-writable files
- ✅ **Smart recommendations**: Context-aware permission suggestions
- ✅ **Safe single-command fixes**: Generate safe `chmod` commands
- ✅ **Docker container support**: Scan containers and analyze UID mapping
- ✅ **Interactive mode**: Choose which fixes to apply
- ✅ **Multiple output formats**: Human-readable and JSON
- ✅ **Safety first**: Dry-run mode by default, backups on apply

## 📋 Requirements
- Python 3.6 or higher
- Linux/Unix system
- Optional: Docker (for container scanning)

### Understanding the Output

The tool provides three severity levels:

- **🚨 CRITICAL**: Files with 777 permissions (read/write/execute for everyone)
- **⚠️ HIGH**: World-writable files (anyone can modify)
- **🔒 MEDIUM**: Sensitive files readable by everyone

For each issue, you'll get:
- Explanation of the risk
- Recommended safe permissions
- Exact command to fix the issue
- Risk reduction assessment

# ⚡ Quick Start

## Run Without Installation (Fastest Way)

```bash
# Clone and run immediately
git clone https://github.com/altynai9128/permission-auditor2.git
cd permission-auditor2

# Run directly from source
python3 src/auditor.py 
