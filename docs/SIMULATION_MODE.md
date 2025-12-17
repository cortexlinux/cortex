# Installation Simulation Mode Guide

This guide covers the installation simulation feature for Cortex (Issue #103).

## Overview

The `--simulate` flag enables preview mode for installations, showing what would be installed without making any changes. This helps users:
- Preview what would be installed with **real package sizes from LLM**
- Check **actual disk space** availability on your system
- Verify system compatibility before installation
- See package information quickly

### Key Features

**Real System Checks:**
- ✅ Actual disk space detection (via `shutil.disk_usage()`)
- ✅ Real OS detection (platform module / `/etc/os-release`)
- ✅ Current package installation status
- ✅ Basic system information (kernel, architecture)

**LLM-Powered Package Information:**
- 🤖 **Real package sizes** queried from OpenAI/Claude
- 📦 Accurate download sizes and version information
- 🔄 Auto-fallback: OpenAI → Anthropic
- 📊 Estimates shown when no API key (marked with ~)

## Usage

### Basic Simulation

```bash
cortex install docker --simulate
```

### Example Output (With API Key)

```text
🔍 Simulation mode: No changes will be made

System Information:
  OS: Windows 10.0.26200
  Kernel: 11
  Architecture: AMD64

Would install:
  - containerd 1.4.3-1 (80 MB)

Total download: 80 MB
Disk space required: 240 MB
Disk space available: 117 GB ✓

Potential issues: None detected
```

### Example Output (Without API Key)

```text
🔍 Simulation mode: No changes will be made

System Information:
  OS: Ubuntu 22.04
  Kernel: 5.15.0
  Architecture: x86_64

Would install:
  - docker-ce latest (~85 MB estimate)
  - containerd.io latest (~45 MB estimate)

Total download: ~130 MB (estimate)
Disk space required: ~390 MB (estimate)
Disk space available: 50 GB ✓

Note: Install API key for accurate package sizes
Potential issues: None detected
```

### Simulating Different Software

```bash
# Simulate Docker installation
cortex install docker --simulate

# Simulate Python installation
cortex install python --simulate

# Simulate nginx installation
cortex install nginx --simulate
```

## What Gets Checked

### System Information
- Operating system (platform, version, distribution)
- Kernel version
- CPU architecture (amd64, arm64, x86_64)

### Disk Space
- Available disk space on current directory
- Required space for installation (from LLM or estimates)

### Package Status
- Docker installation check
- containerd installation check
- Generic software package detection

### Package Information (via LLM)
- Real package sizes queried from OpenAI/Claude
- Package versions available
- Dependencies and download sizes
- Falls back to estimates if no API key

## Report Information

### Errors
Critical issues detected during simulation:
```text
❌ Errors:
  - Insufficient disk space: 200 MB available, 500 MB required
  - Unable to detect OS information
```

### Warnings
Issues to be aware of (non-blocking):
```text
⚠️ Warnings:
  - API key not found, using estimates for package sizes
  - Package version could not be determined
```

## Combining with Other Flags

The `--simulate` flag takes precedence:

```bash
# This will only simulate, not execute
cortex install docker --simulate --execute

# This will only simulate
cortex install docker --simulate --dry-run
```

## Exit Codes

- `0`: Simulation completed, no blocking issues
- `1`: Simulation found blocking issues

## Differences from --dry-run

| Feature | --simulate | --dry-run |
|---------|-----------|-----------|
| System checks | Yes | No |
| API key required | Optional (better with) | Yes |
| Shows packages to install | Yes | No |
| Shows commands to run | No | Yes |
| Disk space analysis | Yes | No |
| LLM for package info | Yes | No |
| Package size accuracy | Real (with API key) | N/A |

## Files Created

- `cortex/preflight_checker.py` - Core preflight checking logic
- `test/test_preflight_checker.py` - Unit tests

## LLM Integration

### API Key Setup

The simulation mode works best with an API key to query real package information:

```bash
# Set OpenAI API key
export OPENAI_API_KEY="sk-..."

# Or Anthropic API key (auto-fallback)
export ANTHROPIC_API_KEY="sk-ant-..."
```

Without an API key, the simulation uses estimated package sizes (marked with ~).

### How It Works

1. Detects your OS and system information
2. Queries LLM (OpenAI/Claude) for real package sizes
3. Auto-falls back to Anthropic if OpenAI fails
4. Uses estimates if no API key is available
5. Shows disk space requirements with ✓ or ✗

## API Reference

### PreflightChecker Class

```python
from cortex.preflight_checker import PreflightChecker, format_report

# Create checker with API key (optional)
checker = PreflightChecker(api_key="sk-...", provider="openai")

# Run all checks for a package
report = checker.run_all_checks("docker")

# Format and display report
output = format_report(report, "docker")
print(output)
```

### PreflightReport Fields

- `os_info`: Operating system details (dict)
- `kernel_info`: Kernel version and architecture (dict)
- `disk_usage`: List of DiskInfo objects
- `package_status`: List of PackageInfo objects
- `packages_to_install`: List of packages to be installed
- `total_download_mb`: Total download size (int)
- `total_disk_required_mb`: Total disk space needed (int)
- `errors`: List of error messages
- `warnings`: List of warning messages

### Helper Functions

```python
# Export report to JSON
from cortex.preflight_checker import export_report
export_report(report, "report.json")

# Check specific software
pkg_info = checker.check_software("nginx")
print(f"{pkg_info.name}: installed={pkg_info.installed}, version={pkg_info.version}")
```
