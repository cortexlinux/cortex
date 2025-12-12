# Troubleshooting Guide

Common errors and solutions for Cortex Linux.

## Table of Contents

- [API Key Issues](#api-key-issues)
- [Installation Errors](#installation-errors)
- [Network & Connectivity](#network--connectivity)
- [Permission Problems](#permission-problems)
- [LLM Provider Issues](#llm-provider-issues)
- [Package Manager Conflicts](#package-manager-conflicts)
- [Performance Issues](#performance-issues)
- [Rollback & Recovery](#rollback--recovery)

---

## API Key Issues

### Error: "No API key found"

**Symptom:**
```
Error: No API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.
```

**Solutions:**

1. **Set the environment variable:**
```bash
# For Claude (recommended)
export ANTHROPIC_API_KEY='sk-ant-api03-your-key-here'

# For OpenAI
export OPENAI_API_KEY='sk-your-key-here'
```

2.  **Add to shell config for persistence:**
```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-api03-your-key"' >> ~/.bashrc
source ~/.bashrc
```

3.  **Use the setup wizard:**
```bash
cortex wizard
```

4.  **For offline mode (no API key needed):**
```bash
export CORTEX_PROVIDER=ollama
cortex install docker
```

### Error: "API rate limit exceeded"

**Symptom:**
```
Error: Rate limit exceeded. Please wait before trying again.
```

**Solutions:**
1.  **Wait and retry:**
```bash
sleep 60 && cortex install docker
```

2.  **Use a different provider temporarily:**
```bash
export CORTEX_PROVIDER=ollama
```

-----

## Installation Errors

### Error: "Package not found"

**Symptom:**
```
E: Unable to locate package xyz
```

**Solutions:**

1.  **Update package lists:**
```bash
sudo apt update
```

2.  **Use natural language for better matching:**
```bash
cortex install "text editor like vim" # Instead of exact package name
```

### Error: "Dependency problems"

**Solutions:**

1.  **Fix broken packages:**
```bash
sudo apt --fix-broken install
```

2.  **Update and upgrade:**
```bash
sudo apt update && sudo apt upgrade
```

### Error: "dpkg lock"

**Symptom:**
```
E: Could not get lock /var/lib/dpkg/lock-frontend
```

**Solutions:**

1.  **Check what's using it:**
```bash
sudo lsof /var/lib/dpkg/lock-frontend
```

2.  **Kill stuck apt process (use with caution):**
```bash
sudo killall apt apt-get
```
-----

## Network & Connectivity

### Error: "Could not resolve host"

**Symptom:**
```
Could not resolve 'archive.ubuntu.com'
```

**Solutions:**

1.  **Check internet connection:**
```bash
ping -c 3 8.8.8.8
```

2.  **Try different DNS (Safe Method):**
```bash
echo "nameserver 8.8.8.8" | sudo tee -a /etc/resolv.conf
```

### Error: "SSL certificate problem"

**Solutions:**

1.  **Update CA certificates:**
```bash
sudo apt install ca-certificates
sudo update-ca-certificates
```

2.  **Check system time (SSL requires correct time):**
```bash
timedatectl status
sudo timedatectl set-ntp true
```
-----

## Permission Problems

### Error: "Permission denied"

**Solutions:**

1.  **Run with sudo for system packages:**
```bash
sudo cortex install docker --execute
```

2.  **Check file ownership:**
```bash
ls -la ~/.cortex/
```

-----

## LLM Provider Issues

### Error: "Ollama not running"

**Symptom:**
```
Error: Could not connect to Ollama at localhost:11434
```

**Solutions:**

1.  **Start Ollama:**
```bash
ollama serve &
```

2.  **Install Ollama if missing:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Error: "Context length exceeded"

**Symptom:**
```
Error: This model's maximum context length is 4096 tokens
```

**Solutions:**

1.  **Simplify your request:**
    Instead of asking for a "complete development environment," try installing tools individually (e.g., "python development tools").

2.  **Change Provider:**
    Switch to a provider that supports larger context windows (e.g., Anthropic) using the wizard:
```bash
cortex wizard
```
-----

## Package Manager Conflicts

### Error: "Snap vs apt conflict"

**Symptom:**
```
error: cannot install "firefox": classic confinement requires snaps
```

**Solutions:**

1.  **Use snap with classic:**
```bash
sudo snap install firefox --classic
```
-----

## Performance Issues

### Slow AI responses

**Solutions:**

1.  **Use local LLM:**
```bash
export CORTEX_PROVIDER=ollama
```

2.  **Check network latency:**
```bash
ping api.anthropic.com
```
-----

## Rollback & Recovery

### How to undo an installation
```bash
# View installation history
cortex history

# Rollback last installation
cortex rollback

# Rollback specific installation
cortex rollback <installation-id>
```

### System recovery

If Cortex causes system issues:

1.  **Boot into recovery mode**
2.  **Use dpkg to fix:**
```bash
sudo dpkg --configure -a
sudo apt --fix-broken install
```