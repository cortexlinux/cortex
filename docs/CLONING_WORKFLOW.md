# System Cloning and Templating Workflow

Cortex allows you to capture your entire system state as a reusable template, which can then be used to restore your system or clone it to another machine. This feature replicates your specific environment, server configurations, or project-specific baseline setups with a single command.

## Core Concepts

- **Templates**: A snapshot encompassing:
  - **Packages**: `apt`, `pip`, and global `npm` packages.
  - **Configurations**: User preferences and safe system environment variables.
  - **Services**: `systemd` unit states (running/stopped/enabled).
- **VERSIONING**: Automatic version tracking (`v1`, `v2`, etc.) ensures you can rollback to previous "Golden States."
- **Differential Updates**: Cortex calculates the exact difference between your current system and the template, restoring only what is necessary.

## Step-by-Step Workflow

### 1. Capture Your System (📸)
Snapshot your current working environment. You can use any name and description that helps you remember what this system state is for.

```bash
cortex template create <template-name> --description "<optional-description>"
```

**Output Example:**
```text
📸 Capturing system state...
   - 1250 packages
   - 5 configurations
   - 80 services
✓  Template saved: <template-name>-v1
```

> [!TIP]
> **Performance Optimization**: If you only care about services and want a fast capture, use:
> `cortex template create <name> --sources service`

### 2. Inspecting Templates
Review what is inside a template before deploying it.

```bash
# List all templates and their versions
cortex template list

# See exactly what's inside a specific version
cortex template show <template-name>-v1
```

### 3. Clone / Restore (🚀)
Replicate the configuration. On the same machine, this acts as "Self-Healing." On a new machine, it acts as a full "Clone."

```bash
# Dry-run first to see the differential plan
cortex template deploy <template-name>-v1 --dry-run

# Perform the actual deployment
cortex template deploy <template-name>-v1 --to <target-label>
```

**Output:**
```text
🚀 Deploying template...
   ✓  Packages installed
   ✓  Configurations applied
   ✓  Services started
✓  System cloned successfully
```

### 4. Sharing Templates
Move your configuration to a new system or share it with a team member.

1.  **On Machine A**: `cortex template export <template-name>-v1 my_clone.zip`
2.  **On Machine B**: `cortex template import my_clone.zip`
3.  **Deploy on Machine B**: `cortex template deploy <template-name>-v1`

---

## Command Reference

| Command | Description |
|---------|-------------|
| `create <name>` | Capture current system state as a new version |
| `list` | List all templates and their available versions |
| `show <name>` | Display counts and description of a template |
| `deploy <name>` | Restore or clone a template to the current system |
| `export <name> <file>` | Pack a template version into a portable .zip |
| `import <file>` | Load a template version from a .zip file |
| `delete <name>` | Permanently remove a template version |

## Best Practices

### The "Self-Healing" Workflow
Regularly create a `baseline` template. If your system starts acting up or a service stops responding, simply run `cortex template deploy baseline` to restore the exact running state without a full reboot or manual debugging.

### Team Onboarding
1. Create a template with all necessary tools for your specific project.
2. Export and share the ZIP with your team.
3. New members simply `import` and `deploy` to have a matching environment in minutes.

## Troubleshooting

- **Sudo Permissions**: Deploying packages or starting services requires `sudo` access.
- **Service Warnings**: If a service fails to restore, check `journalctl -u <service-name>` for system-level errors.
- **Version Mismatches**: Use `cortex template list` to verify you are using the correct version suffix (`-v1`).
