# Cortex Import - Package Requirements Importer

Import dependencies from various package manager requirement files.

## Quick Start

```bash
# Import from a single file
cortex import requirements.txt
cortex import package.json

# Import from all detected files
cortex import --all

# Preview what would be installed
cortex import --dry-run requirements.txt

# Include dev dependencies
cortex import --dev package.json
```

## Supported File Formats

| File | Package Manager | Language |
|------|-----------------|----------|
| `requirements.txt` | pip | Python |
| `package.json` | npm | Node.js |
| `Gemfile` | bundler | Ruby |
| `Cargo.toml` | cargo | Rust |
| `go.mod` | go | Go |

## Commands

### Import Single File

```bash
cortex import <file>

# Examples:
cortex import requirements.txt
cortex import package.json
cortex import Gemfile
cortex import Cargo.toml
cortex import go.mod
```

### Import All Detected Files

```bash
cortex import --all

# From a specific directory
cortex import --all --dir /path/to/project
```

### Detect Files Only

```bash
cortex import --detect

# Output:
# Detected requirements files:
#   - requirements.txt
#   - package.json
```

### Dry Run (Preview)

```bash
cortex import --dry-run requirements.txt

# Output:
# Parsing requirements.txt (pip)...
# Dependencies (3):
#   - flask (2.0.1)
#   - requests (2.28.0)
#   - django
# Installing...
# Success: [DRY RUN] Would install 3 packages via pip
```

### Include Dev Dependencies

```bash
cortex import --dev package.json
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--all` | `-a` | Import from all detected files |
| `--detect` | `-d` | Detect files without importing |
| `--dry-run` | `-n` | Preview without installing |
| `--dev` | | Include dev dependencies |
| `--verbose` | `-v` | Show detailed output |
| `--dir` | | Directory to search (default: `.`) |

## File Format Examples

### requirements.txt (Python)

```txt
flask==2.0.1
requests>=2.28.0
django~=4.0
celery[redis]
# Comments are ignored
```

Supported specifiers:
- Exact: `package==1.0.0`
- Range: `package>=1.0,<2.0`
- Compatible: `package~=1.0`
- Extras: `package[extra1,extra2]`
- Environment markers: `package; python_version >= "3.8"`

### package.json (Node.js)

```json
{
  "dependencies": {
    "express": "^4.18.0",
    "lodash": "~4.17.21"
  },
  "devDependencies": {
    "jest": "^29.0.0",
    "eslint": "^8.0.0"
  }
}
```

### Gemfile (Ruby)

```ruby
source 'https://rubygems.org'

gem 'rails', '7.0.0'
gem 'pg', '>= 0.18', '< 2.0'

group :development do
  gem 'rubocop'
end

group :test do
  gem 'rspec', '3.12.0'
end
```

### Cargo.toml (Rust)

```toml
[package]
name = "myproject"
version = "0.1.0"

[dependencies]
serde = "1.0"
tokio = { version = "1.28", features = ["full"] }

[dev-dependencies]
criterion = "0.5"
```

### go.mod (Go)

```go
module example.com/myproject

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1
    github.com/spf13/cobra v1.7.0
)
```

Indirect dependencies (marked with `// indirect`) are skipped.

## Python API

```python
from cortex.requirements_importer import (
    RequirementsImporter,
    RequirementsParser,
    PackageJsonParser,
)

# Create importer
importer = RequirementsImporter(dry_run=True, verbose=True)

# Detect files in current directory
files = importer.detect_files('.')
print(f"Found: {files}")

# Parse a single file
result = importer.parse_file('requirements.txt')
print(f"Dependencies: {len(result.dependencies)}")
print(f"Package manager: {result.package_manager.value}")

# Install
success, message = importer.install(result, include_dev=True)
print(f"Install: {message}")

# Get summary
print(importer.summary())
```

## Exit Codes

| Code | Description |
|------|-------------|
| 0 | Success |
| 1 | Error (file not found, parse error, install failed) |

## Requirements

- Python 3.8+
- Package managers must be installed for installation:
  - pip (Python) - usually included with Python
  - npm (Node.js) - install Node.js
  - bundler (Ruby) - `gem install bundler`
  - cargo (Rust) - install Rust via rustup
  - go (Go) - install Go

## Files

- `cortex/requirements_importer.py` - Core implementation
- `cortex/import_cli.py` - CLI commands
- `tests/test_requirements_importer.py` - Unit tests (50+ tests)
- `README_IMPORT.md` - This documentation

## Related Issue

- [#126 Package Import from Requirements Files](https://github.com/cortexlinux/cortex/issues/126)
