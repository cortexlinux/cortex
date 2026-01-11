# Uninstall Impact Analysis - Developer Guide

## Implementation Overview

The Uninstall Impact Analysis feature is implemented across three main components:

1. **[cortex/uninstall_impact.py](../cortex/uninstall_impact.py)** - Core analysis engine
2. **[cortex/cli.py](../cortex/cli.py)** - CLI integration for `cortex remove` command
3. **[tests/test_uninstall_impact.py](../tests/test_uninstall_impact.py)** - Comprehensive test suite

## Architecture Diagram

```
┌─────────────────────────────────────┐
│   CLI: cortex remove <package>      │
│   (cli.py - remove method)          │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  UninstallImpactAnalyzer            │
│  (uninstall_impact.py)              │
├─────────────────────────────────────┤
│                                     │
│  1. analyze_uninstall_impact()      │
│     ├─ is_package_installed()       │
│     ├─ get_directly_dependent()     │
│     │  └─ get_reverse_deps()        │
│     ├─ get_indirectly_dependent()   │
│     ├─ get_affected_services()      │
│     ├─ find_orphaned_packages()     │
│     ├─ _determine_severity()        │
│     └─ _generate_recommendations()  │
│                                     │
│  2. System Commands (subprocess)    │
│     ├─ dpkg -l (list packages)      │
│     ├─ apt-cache rdepends (deps)    │
│     ├─ systemctl (service status)   │
│     └─ dpkg-query (version)         │
│                                     │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  UninstallImpactAnalysis            │
│  (DataClass with results)           │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  Display Results & Recommendations  │
│  or Execute Removal Commands        │
└─────────────────────────────────────┘
```

## Key Design Decisions

### 1. Caching Strategy

**Problem**: Repeated calls to system commands are slow.

**Solution**:
```python
self._reverse_deps_cache: dict[str, list[str]] = {}
self._installed_packages: set[str] = set()
```

- Cache reverse dependencies to avoid repeated `apt-cache rdepends` calls
- Cache installed packages set, refreshed once at initialization
- Thread-safe caching with locks for concurrent access

**Trade-off**: Cache freshness vs. performance (acceptable for typical use)

### 2. Severity Classification

**Problem**: Need to determine risk without over-flagging safe removals.

**Solution**: Multi-factor severity assessment:

```python
def _determine_severity(self, package_name, critical_deps, 
                       critical_services, total_deps):
    # Highest priority: System packages
    if package_name in CRITICAL_PACKAGES:
        return "critical"
    
    # Critical dependencies or services
    if critical_deps or critical_services:
        return "high"
    
    # Many dependents
    if total_deps > 5:
        return "high"
    
    # Several dependents  
    if total_deps >= 3:
        return "medium"
    
    return "low"
```

### 3. Separate Dependency Types

**Problem**: Different types of dependencies have different risks.

**Solution**: Categorize dependencies:

```python
critical_deps = [d for d in directly_depends if d.critical]
optional_deps = [d for d in directly_depends if not d.critical]
```

Allows for more nuanced recommendations.

### 4. Two-Phase Analysis

**Phase 1 - Collection**:
- Get reverse dependencies
- Get service status
- Find orphaned packages

**Phase 2 - Analysis**:
- Calculate severity
- Generate recommendations
- Determine safety

This allows reusing the same analysis for different purposes.

## Code Flow Examples

### Example: Analyzing nginx Removal

```python
analyzer = UninstallImpactAnalyzer()
analysis = analyzer.analyze_uninstall_impact("nginx")
```

**Step-by-step execution**:

1. **Check if installed**
   ```bash
   dpkg-query -W -f='${Version}' nginx
   # Returns: 1.18.0
   ```

2. **Get reverse dependencies**
   ```bash
   apt-cache rdepends nginx
   # Output:
   # nginx
   # Reverse Depends:
   #   certbot
   #   haproxy
   ```

3. **Get service status**
   ```bash
   systemctl is-active nginx
   # Returns: active
   ```

4. **Calculate severity**
   - `nginx` not in CRITICAL_PACKAGES
   - No critical dependencies found
   - 2 total dependencies
   - → Result: "low"

5. **Generate recommendations**
   - No critical issues
   - Safe to remove
   - → Recommendation: "✅ Safe to remove nginx"

### Example: Analyzing Python3 Removal

```python
analyzer = UninstallImpactAnalyzer()
analysis = analyzer.analyze_uninstall_impact("python3")
```

**Expected results**:

```python
analysis.severity == "high"  # Many dependents
analysis.safe_to_remove == False  # Requires --cascading
analysis.recommendations == [
    "⚠️  Use caution when removing python3 - it affects critical services",
    "Remove dependent packages first using cascading removal"
]
```

## Testing Strategy

### Unit Testing Approach

1. **Isolation**: Mock system calls with `@patch`
2. **Coverage**: Each method has dedicated test class
3. **Integration**: Full workflow tests with mocked system

### Example Test

```python
@patch.object(UninstallImpactAnalyzer, "_run_command")
def test_get_directly_dependent_packages(self, mock_run):
    # Arrange
    mock_run.return_value = (True, "nginx\nReverse Depends:\n  certbot\n", "")
    
    # Act
    deps = analyzer.get_directly_dependent_packages("openssl")
    
    # Assert
    self.assertEqual(len(deps), 1)
    self.assertEqual(deps[0].name, "certbot")
```

### Test Coverage Areas

- ✅ Data class instantiation (ImpactedPackage, ServiceImpact, etc.)
- ✅ System command execution and error handling
- ✅ Package detection and versioning
- ✅ Reverse dependency parsing
- ✅ Dependency caching and thread-safety
- ✅ Service impact detection
- ✅ Orphan package detection
- ✅ Severity calculation with various scenarios
- ✅ Recommendation generation
- ✅ Full impact analysis workflow
- ✅ JSON export functionality
- ✅ Concurrent access handling

**Coverage: 92.11%** (exceeds 80% requirement)

## Adding New Features

### Example: GPU Service Detection

To add GPU service detection:

```python
# Step 1: Add to SERVICE_PACKAGE_MAP in __init__
SERVICE_PACKAGE_MAP = {
    ...existing...
    "gpu-runtime": ["cuda", "nvidia-driver"],
    "tensorrt": ["tensorrt"],
}

# Step 2: Add to test
def test_get_affected_services_gpu(self, mock_run):
    mock_run.return_value = (True, "active\n", "")
    services = analyzer.get_affected_services("cuda")
    self.assertEqual(services[0].service_name, "gpu-runtime")

# Step 3: Run tests
pytest tests/test_uninstall_impact.py -v
```

### Example: Custom Criticality Rules

To add custom rules:

```python
def _is_critical_dependency(self, package_name: str) -> bool:
    """Override or extend criticality checks"""
    # Base check
    if package_name in self.CRITICAL_PACKAGES:
        return True
    
    # Custom rules
    if self._is_database_package(package_name):
        return True
    
    if self._is_webserver_package(package_name):
        return True
    
    return False
```

## Performance Optimization

### Current Bottlenecks

1. **apt-cache rdepends** - Slowest operation (~100-500ms per package)
2. **systemctl is-active** - ~50-100ms per service
3. **dpkg-query** - ~10-20ms per package

### Optimization Strategies

1. **Batch Operations**
   ```python
   # Current: One dpkg-query per package
   # Future: Single query for all packages
   dpkg-query --show '*'  # Get all versions at once
   ```

2. **Parallel Resolution**
   ```python
   import concurrent.futures
   
   with concurrent.futures.ThreadPoolExecutor() as executor:
       futures = {
           executor.submit(self.get_reverse_dependencies, pkg): pkg
           for pkg in package_list
       }
   ```

3. **Direct libapt-pkg Binding**
   ```python
   # Replace subprocess calls with python-apt
   import apt
   cache = apt.Cache()
   pkg = cache['nginx']
   ```

## Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

analyzer = UninstallImpactAnalyzer()
analysis = analyzer.analyze_uninstall_impact("nginx")
```

### Debug Output

```
INFO:cortex.uninstall_impact:Refreshing installed packages cache...
INFO:cortex.uninstall_impact:Found 2847 installed packages
INFO:cortex.uninstall_impact:Analyzing uninstall impact for nginx...
INFO:cortex.uninstall_impact:Using cached reverse dependencies for nginx
```

### Common Issues and Solutions

**Issue**: No reverse dependencies found

```python
# Debug: Check what apt-cache returns
analyzer._run_command(["apt-cache", "rdepends", "nginx"])

# Solution: Verify package exists
apt-cache search nginx  # Check if package is in repos
```

**Issue**: systemctl not found

```python
# Graceful fallback: Service detection is optional
# The analyzer continues with partial results
```

## Integration with Cortex Ecosystem

### Installation History Integration

The `cortex remove` command can optionally record removals in installation history:

```python
history = InstallationHistory()
history.record_removal(
    packages=["nginx"],
    commands=commands,
    analysis=analysis
)
```

### Future Integrations

1. **Undo/Rollback**: Use history to reinstall removed packages
2. **Configuration Backup**: Back up package configs before removal
3. **Audit Trail**: Track all removals with timestamps
4. **Predictive Removal**: Use ML to suggest safe removals

## Security Considerations

### Privilege Escalation

All removal commands use `sudo`:
```bash
sudo apt-get remove -y nginx
```

This is intentional - package management requires elevated privileges.

### Sandboxing

Consider wrapping removal in Firejail:
```bash
firejail sudo apt-get remove -y nginx
```

### Input Validation

Always validate package names:
```python
import re

if not re.match(r'^[a-zA-Z0-9._+-]+$', package_name):
    raise ValueError(f"Invalid package name: {package_name}")
```

## Release Checklist

- [ ] All 36 unit tests pass
- [ ] Coverage >= 80%
- [ ] CLI integration works end-to-end
- [ ] Documentation updated
- [ ] Examples tested manually
- [ ] Performance acceptable (< 1s for typical packages)
- [ ] Error messages clear and actionable
- [ ] No regressions in existing commands

## References

### Files

- [uninstall_impact.py](../cortex/uninstall_impact.py) - 506 lines
- [cli.py](../cortex/cli.py) - Remove method added
- [test_uninstall_impact.py](../tests/test_uninstall_impact.py) - 530 lines, 36 tests
- [UNINSTALL_IMPACT_ANALYSIS.md](./UNINSTALL_IMPACT_ANALYSIS.md) - User guide

### Dependencies

- `apt-cache` - System package
- `dpkg` - System package
- `systemctl` - System package
- Python 3.10+ with dataclasses, subprocess, threading

### External Documentation

- [APT Documentation](https://wiki.debian.org/AptCLI)
- [Debian Package Relationships](https://www.debian.org/doc/debian-policy/ch-relationships.html)
- [systemd Service Files](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
