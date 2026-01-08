# Unified Package Manager

A unified abstraction layer for managing packages across Snap and Flatpak on Cortex Linux.

## Features

- ✅ Unified API for Snap and Flatpak
- ✅ Automatic backend detection
- ✅ Smart backend selection based on availability
- ✅ Cross-backend installation support
- ✅ Permission checking
- ✅ Storage usage analysis
- ✅ Transaction safety with subprocess timeouts

## Usage

### CLI Usage

The package manager is integrated into the Cortex CLI under the `pkg` (or `apps`) subcommand.

#### List Backend Status
```bash
cortex pkg list
```
*Output:* checks availability of Snap vs Flatpak.

#### Install a Package
```bash
cortex pkg install vlc
```
*Auto-detects the best backend.*

#### Install with Specific Backend
```bash
# Force Snap
cortex pkg install --backend snap Spotify

# Force Flatpak
cortex pkg install --backend flatpak GIMP
```

#### Flatpak Scope (User vs System)
```bash
# Install to user scope (default)
cortex pkg install vlc --scope user

# Install to system scope
cortex pkg install vlc --scope system
```

#### Remove a Package
```bash
cortex pkg remove vlc
```

#### Check Permissions
```bash
cortex pkg permissions vlc
```
*Analyze requested permissions for the installed package.*

### Programmatic Usage

```python
from cortex.package_manager import UnifiedPackageManager

pm = UnifiedPackageManager()

# Check availability
if pm.flatpak_avail:
    print("Flatpak is ready!")

# Install VLC
pm.install("vlc", scope="user")

# Remove VLC
pm.remove("vlc")

# Check permissions
perms = pm.check_permissions("vlc")
print(perms)
```

## Architecture

### UnifiedPackageManager Class
The core class that abstracts the differences between Snap and Flatpak.

- **Initialization**: Detects `snap` and `flatpak` binaries on startup.
- **Backend Selection**: 
    - If user specifies a backend, uses it.
    - If only one backend is available, uses it.
    - If both are available, prompts the user (interactive) or defaults to Snap (non-interactive).
- **Command Execution**: Uses `subprocess.check_call` with a 300-second timeout to ensure stability.

### Error Handling
- **Timeout**: Operations exceeding 5 minutes are terminated.
- **Input Validation**: Package names are validated to prevent command injection.
- **Missing Backends**: Gracefully warns if a required backend is not installed.

## Testing

Run unit tests:
```bash
pytest tests/test_package_manager.py
```

## Security
- **Input Sanitization**: All inputs are validated against strict regex patterns.
- **Least Privilege**: Flatpak defaults to `--user` scope to avoid root requirements where possible.
