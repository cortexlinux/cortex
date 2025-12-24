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
```text
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

2. **Add to shell config for persistence:**
   ```bash
   echo 'export ANTHROPIC_API_KEY="sk-ant-api03-your-key"' >> ~/.bashrc
   source ~/.bashrc
   ```

3. **Use the setup wizard:**
   ```bash
   cortex wizard
   ```

4. **For offline mode (no API key needed):**
   ```bash
   export CORTEX_PROVIDER=ollama
   cortex install docker
   ```

### Error: "API key doesn't look valid"

**Symptom:**
```
ANTHROPIC_API_KEY doesn't look valid (should start with 'sk-ant-')
```

**Solutions:**

1. **Verify key format:**
   - Anthropic keys start with `sk-ant-`
   - OpenAI keys start with `sk-`

2. **Check for extra whitespace:**
   ```bash
   echo "[$ANTHROPIC_API_KEY]"  # Should show no spaces
   ```

3. **Re-export without quotes issues:**
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-api03-your-actual-key
   ```
```bash
# For Claude (recommended)
export ANTHROPIC_API_KEY='<YOUR_ANTHROPIC_API_KEY>'

# For OpenAI
export OPENAI_API_KEY='<YOUR_OPENAI_API_KEY>'
```

2.  **Add to shell config for persistence:**
```bash
echo 'export ANTHROPIC_API_KEY="<YOUR_ANTHROPIC_API_KEY>"' >> ~/.bashrc
source ~/.bashrc
```

3.  **Use the setup wizard:**
```bash
cortex wizard
```

4. **For Local Provider mode (No API key needed):**
   *Note: Installation of tools like Docker may still require an internet connection.*
```bash
export CORTEX_PROVIDER=ollama
cortex install docker
```

### Error: "API rate limit exceeded"

**Symptom:**
```
```text
Error: Rate limit exceeded. Please wait before trying again.
```

**Solutions:**

1. **Wait and retry:**
   ```bash
   sleep 60 && cortex install docker
   ```

2. **Check your API usage** at the provider's dashboard

3. **Use a different provider temporarily:**
   ```bash
   export CORTEX_PROVIDER=ollama
   ```
1.  **Wait and retry:**
```bash
sleep 60 && cortex install docker
```

2.  **Use a different provider temporarily:**
```bash
export CORTEX_PROVIDER=ollama
```

---

## Installation Errors

### Error: "Package not found"

**Symptom:**
```
```text
E: Unable to locate package xyz
```

**Solutions:**

1. **Update package lists:**
   ```bash
   sudo apt update
   ```

2. **Check package name spelling:**
   ```bash
   apt search package-name
   ```

3. **Add required repository:**
   ```bash
   sudo add-apt-repository ppa:required/ppa
   sudo apt update
   ```

4. **Use natural language for better matching:**
   ```bash
   cortex install "text editor like vim"  # Instead of exact package name
   ```

### Error: "Dependency problems"

**Symptom:**
```
The following packages have unmet dependencies:
  package-x : Depends: lib-y (>= 1.0) but it is not installable
```

**Solutions:**

1. **Fix broken packages:**
   ```bash
   sudo apt --fix-broken install
   ```

2. **Update and upgrade:**
   ```bash
   sudo apt update && sudo apt upgrade
   ```

3. **Use Cortex's dependency resolver:**
   ```bash
   cortex install "package-x with all dependencies"
   ```

4. **Clean apt cache:**
   ```bash
   sudo apt clean
   sudo apt autoclean
   ```
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
```text
E: Could not get lock /var/lib/dpkg/lock-frontend
```

**Solutions:**

1. **Wait for other package managers to finish:**
   ```bash
   # Check what's using it
   sudo lsof /var/lib/dpkg/lock-frontend
   ```

2. **If no process is using it:**
   ```bash
   sudo rm /var/lib/dpkg/lock-frontend
   sudo rm /var/lib/dpkg/lock
   sudo dpkg --configure -a
   ```

3. **Kill stuck apt process (use with caution):**
   ```bash
   sudo killall apt apt-get
   ```

### Error: "Held packages"

**Symptom:**
```
The following packages have been kept back:
  package-name
```

**Solutions:**

1. **Full upgrade:**
   ```bash
   sudo apt full-upgrade
   ```

2. **Install specifically:**
   ```bash
   sudo apt install package-name
   ```

3. **Check hold status:**
   ```bash
   apt-mark showhold
   ```

1.  **Check what's using it:**
```bash
sudo lsof /var/lib/dpkg/lock-frontend
```

2. **If it's genuinely stuck, stop the specific process (use with caution):**
```bash
# Check for apt, apt-get, or unattended-upgrades
ps aux | egrep 'apt|apt-get|unattended' | egrep -v egrep

# Then (only if needed) kill the specific PID (replace <PID>):
sudo kill <PID>

# Recovery: Run these if the package manager breaks after killing the process
sudo dpkg --configure -a
sudo apt --fix-broken install
```
---

## Network & Connectivity

### Error: "Could not resolve host"

**Symptom:**
```
```text
Could not resolve 'archive.ubuntu.com'
```

**Solutions:**

1. **Check internet connection:**
   ```bash
   ping -c 3 8.8.8.8
   ping -c 3 google.com
   ```

2. **Check DNS settings:**
   ```bash
   cat /etc/resolv.conf
   ```

3. **Try different DNS:**
   ```bash
   sudo echo "nameserver 8.8.8.8" >> /etc/resolv.conf
   ```

4. **Use offline mode:**
   ```bash
   export CORTEX_PROVIDER=ollama
   ```

### Error: "Connection timed out"

**Symptom:**
```
Connection timed out [IP: x.x.x.x port]
```

**Solutions:**

1. **Check firewall:**
   ```bash
   sudo ufw status
   ```

2. **Try different mirror:**
   ```bash
   sudo software-properties-gtk  # Change download server
   ```

3. **Check proxy settings:**
   ```bash
   echo $http_proxy
   echo $https_proxy
   ```

### Error: "SSL certificate problem"

**Symptom:**
```
SSL certificate problem: unable to get local issuer certificate
```

**Solutions:**

1. **Update CA certificates:**
   ```bash
   sudo apt install ca-certificates
   sudo update-ca-certificates
   ```

2. **Check system time (SSL requires correct time):**
   ```bash
   date
   sudo ntpdate pool.ntp.org
   ```

1.  **Check internet connection:**
```bash
ping -c 3 8.8.8.8
```

2.  **Try different DNS (Temporary):**
    *Note: `/etc/resolv.conf` is often overwritten. Use `resolvectl` for permanent changes.*
```bash
# Append Google DNS
echo "nameserver 8.8.8.8" | sudo tee -a /etc/resolv.conf

# Rollback (Undo): Edit the file and remove the line
sudo nano /etc/resolv.conf
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
---

## Permission Problems

### Error: "Permission denied"

**Symptom:**
```
E: Could not open lock file - open (13: Permission denied)
```

**Solutions:**

1. **Run with sudo for system packages:**
   ```bash
   sudo cortex install docker --execute
   ```

2. **Check file ownership:**
   ```bash
   ls -la /var/lib/dpkg/lock
   ```

3. **For user-level installs, check permissions:**
   ```bash
   ls -la ~/.cortex/
   ```

### Error: "Operation not permitted"

**Symptom:**
```
chown: operation not permitted
```

**Solutions:**

1. **Check if running as root when needed:**
   ```bash
   whoami
   sudo whoami
   ```

2. **For containers, ensure proper capabilities:**
   ```bash
   docker run --privileged ...
   ```
**Solutions:**

1.  **Run with sudo for system packages:**
```bash
sudo cortex install docker --execute
```

2.  **Check file ownership:**
```bash
ls -la ~/.cortex/
```

---

## LLM Provider Issues

### Error: "Ollama not running"

**Symptom:**
```
Error: Could not connect to Ollama at localhost:11434
```

**Solutions:**

1. **Start Ollama:**
   ```bash
   ollama serve &
   ```

2. **Check if running:**
   ```bash
   curl http://localhost:11434/api/tags
   ```

3. **Install Ollama if missing:**
   ```bash
   curl -fsSL https://ollama.ai/install.sh | sh
   ```

4. **Pull required model:**
   ```bash
   ollama pull llama2
   ```

### Error: "Model not found"

**Symptom:**
```
Error: model 'xyz' not found
```

**Solutions:**

1. **List available models:**
   ```bash
   ollama list
   ```

2. **Pull the model:**
   ```bash
   ollama pull llama2
   ```

3. **Use a different model:**
   ```bash
   export CORTEX_MODEL=llama2
   ```
```text
Error: Could not connect to Ollama at localhost:11434
````

**Solutions:**

1.  **Start System Service (Recommended):**

```bash
sudo systemctl start ollama
```

2.  **Manual Start (Fallback):**
    *Note: Only use this if the system service is unavailable.*

```bash
ollama serve
```

3.  **Install Ollama if missing:**
    *Note: Always review remote scripts before running them.*

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Error: "Context length exceeded"

**Symptom:**
```

```text
Error: This model's maximum context length is 4096 tokens
```

**Solutions:**

1. **Simplify your request:**
   ```bash
   # Instead of
   cortex install "complete development environment with..."

   # Try
   cortex install "python development tools"
   ```

2. **Use a model with larger context:**
   ```bash
   export CORTEX_MODEL=claude-3-opus
   ```

1.  **Simplify your request:**
    Instead of asking for a "complete development environment," try installing tools individually (e.g., "python development tools").

2.  **Change Provider:**
    Switch to a provider that supports larger context windows (e.g., Anthropic) using the wizard:

```bash
cortex wizard
```
---

## Package Manager Conflicts

### Error: "Another process is using apt"

**Symptom:**
```
Waiting for cache lock: Could not get lock /var/lib/dpkg/lock
```

**Solutions:**

1. **Wait for automatic updates to finish:**
   ```bash
   # Check for unattended-upgrades
   ps aux | grep unattended
   ```

2. **Disable automatic updates temporarily:**
   ```bash
   sudo systemctl stop unattended-upgrades
   ```

### Error: "Snap vs apt conflict"

**Symptom:**
```
### Error: "Snap vs apt conflict"

**Symptom:**
```text
error: cannot install "firefox": classic confinement requires snaps
```

**Solutions:**

1. **Use apt version:**
   ```bash
   sudo snap remove firefox
   sudo apt install firefox
   ```

2. **Or use snap with classic:**
   ```bash
   sudo snap install firefox --classic
   ```

1.  **Use snap with classic:**
```bash
sudo snap install firefox --classic
```
---

## Performance Issues

### Slow AI responses

**Solutions:**

1. **Use a faster model:**
   ```bash
   export CORTEX_MODEL=claude-3-haiku  # Faster than opus
   ```

2. **Use local LLM:**
   ```bash
   export CORTEX_PROVIDER=ollama
   ```

3. **Check network latency:**
   ```bash
   ping api.anthropic.com
   ```

### High memory usage

**Solutions:**

1. **For Ollama, use smaller models:**
   ```bash
   ollama pull phi  # Smaller than llama2
   ```

2. **Limit context memory:**
   ```bash
   export CORTEX_MAX_CONTEXT=2000
   ```

1.  **Use local LLM:**
```bash
export CORTEX_PROVIDER=ollama
```

2.  **Check network latency:**
```bash
ping api.anthropic.com
```
---

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

1. **Boot into recovery mode**
2. **Use dpkg to fix:**
   ```bash
   sudo dpkg --configure -a
   sudo apt --fix-broken install
   ```
3. **Restore from snapshot (if enabled):**
   ```bash
   sudo timeshift --restore
   ```

---

## Getting More Help

### Enable verbose mode

```bash
cortex -v install docker
```

### Check logs

```bash
cat ~/.cortex/logs/cortex.log
```

### Report a bug

1. Gather information:
   ```bash
   cortex status > cortex-status.txt
   cat ~/.cortex/logs/cortex.log >> cortex-status.txt
   ```

2. Open an issue: https://github.com/cortexlinux/cortex/issues

### Community support

- Discord: https://discord.gg/uCqHvxjU83
- GitHub Discussions: https://github.com/cortexlinux/cortex/discussions

---

## Error Code Reference

| Code | Meaning | Quick Fix |
|------|---------|-----------|
| `E001` | No API key | `export ANTHROPIC_API_KEY=...` |
| `E002` | Invalid API key | Check key format |
| `E003` | Rate limited | Wait and retry |
| `E010` | Package not found | `sudo apt update` |
| `E011` | Dependency error | `sudo apt --fix-broken install` |
| `E012` | Lock file busy | Wait or remove lock |
| `E020` | Network error | Check connectivity |
| `E021` | DNS error | Check `/etc/resolv.conf` |
| `E030` | Permission denied | Use `sudo` |
| `E040` | LLM error | Check provider config |

---

*Last updated: December 2024*
*Cortex Linux v0.1.0*
1.  **Boot into recovery mode**
2.  **Use dpkg to fix:**
```bash
sudo dpkg --configure -a
sudo apt --fix-broken install
```
