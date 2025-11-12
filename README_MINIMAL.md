# System Requirements Checker

Validates system requirements before package installation.

## Usage

```bash
python src/requirements_checker.py oracle-23-ai
python src/requirements_checker.py oracle-23-ai --force
python src/requirements_checker.py oracle-23-ai --json
```

## Features

- Disk space validation
- RAM checking
- OS compatibility
- Architecture validation
- Package detection
- GPU detection

## Requirements

Optional: `pip install psutil` for better system detection.







