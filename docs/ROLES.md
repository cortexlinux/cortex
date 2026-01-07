# System Role Management

Manage system personalities and receive tailored package recommendations based on your workstation's specific purpose.

## Overview

Cortex uses "System Roles" to understand the context of your Linux environment. Whether you are building a high-performance Machine Learning workstation or a secure Web Server, Cortex identifies existing software stacks and suggests relevant tools to complete your setup.

The `cortex role` command group handles the detection, declaration, and intelligent learning of these system personalities.

## Usage

### Basic Commands
```bash
# Auto-detect your current system role based on installed binaries
cortex role detect

# Manually set your system role (e.g., to ML Workstation)
cortex role set ml-workstation

# View valid role identifiers
cortex role set --help
```

## Features

### 1. Intelligent Role Detection

Cortex recursively scans your system `PATH` for signature binaries to determine your active roles.

- **Web Server:** Detected via `nginx`, `apache2`, or `httpd`.
- **Database Server:** Detected via `psql`, `mysql`, `mongod`, or `redis-server`.
- **ML Workstation:** Detected via `nvidia-smi`, `nvcc`, or `jupyter`, `conda`.

### 2. Role-Based Recommendations

Once a role is set, Cortex provides curated package "bundles" designed for that specific environment.

**Example Recommendations:**
- **Web Server:** Certbot, Fail2Ban, Nginx Amplify.
- **ML Workstation:** CUDA Toolkit, PyTorch, TensorFlow, Jupyter Lab.
- **Database Server:** pgAdmin, Redis Insight, Backup Tools.

### 3. Learning from Patterns

Cortex keeps your system intelligence up-to-date by learning from your installation habits.

- **Context Awareness:** When you successfully run `cortex install <package>`, Cortex checks if a system role is active.
- **Local Intelligence:** Successful installs are appended to `learned_roles.json` and will appear in future recommendations for that role.

### 4. Custom Role Support

Define your own system personalities by creating a `custom_roles.json` file in your `~/.cortex/` directory.

```json
{
  "Frontend-Dev": {
    "slug": "frontend",
    "binaries": ["node", "npm"],
    "recommendations": ["VS Code", "Postman", "Figma"]
  }
}
```

## Examples

### Detecting Active Personalities
```bash
$ cortex role detect

Detected roles:
   - Web Server (nginx installed)
   - ML Workstation (nvidia-smi detected)
```

### Declaring a Role
```bash
$ cortex role set ml-workstation

✓ Role set to: ml-workstation

💡 Recommended packages for ml-workstation:
   - CUDA Toolkit
   - PyTorch
   - Jupyter Lab
   - NVIDIA Drivers
```

## Technical Implementation

### Thread-Safe Persistence

The tool utilizes `fcntl` for advisory record locking to ensure your configuration remains consistent. (See `role_manager.py:_locked_read_modify_write` for full implementation details).

```python
# Simplified illustration of the locking logic
with open(lock_file, "r+") as lock_fd:
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
        # Atomic read-modify-write cycle
        updated_content = modifier(existing_content, key, value)
        temp_file.replace(target)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
```

## Related Commands

- `cortex stack <name>` - Install pre-built software stacks.
- `cortex doctor` - Run health checks to verify role-specific drivers (like CUDA).
- `cortex env` - Manage the environment variables that power your roles.