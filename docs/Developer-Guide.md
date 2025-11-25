# Developer Guide

## Development Setup
```bash
# Clone repository
git clone https://github.com/cortexlinux/cortex.git
cd cortex

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dev dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# Run with coverage
pytest --cov=cortex tests/
```

## Project Structure
```
cortex/
├── cortex/                      # Core Python modules
│   ├── __init__.py
│   ├── cli.py                   # Command-line interface
│   ├── packages.py              # Package manager wrapper
│   ├── coordinator.py           # Installation coordination
│   ├── dependency_resolver.py   # Dependency resolution
│   ├── installation_history.py  # Installation tracking
│   ├── installation_verifier.py # Installation verification
│   ├── error_parser.py          # Error parsing & recovery
│   ├── llm_router.py            # Multi-LLM routing
│   ├── logging_system.py        # Logging & diagnostics
│   ├── context_memory.py        # AI memory system
│   └── user_preferences.py      # User preferences management
├── LLM/                         # LLM integration layer
│   ├── __init__.py
│   ├── interpreter.py           # Command interpreter
│   └── requirements.txt
├── test/                        # Test suite
│   ├── run_all_tests.py         # Test runner
│   └── test_*.py                # Unit tests
├── docs/                        # Documentation
│   ├── Developer-Guide.md
│   ├── User-Guide.md
│   ├── Bounties.md
│   ├── Getting-Started.md
│   └── *.md                     # Additional docs
├── scripts/                     # Shell scripts
│   ├── cortex-master.sh         # Main automation
│   ├── setup_and_upload.sh      # Setup utilities
│   └── *.sh                     # Other scripts
├── data/                        # Data files
│   ├── contributors.json
│   ├── bounties_owed.csv
│   ├── bounties_pending.json
│   └── *.json, *.csv            # Other data files
├── src/                         # Additional utilities
│   ├── progress_tracker.py
│   ├── sandbox_executor.py
│   └── hwprofiler.py
├── examples/                    # Example scripts
│   ├── progress_demo.py
│   └── standalone_demo.py
└── .github/
    └── workflows/               # CI/CD
```

## Architecture

### Core Flow
```
User Input (Natural Language)
    ↓
LLM Integration Layer (Claude API)
    ↓
Package Manager Wrapper (apt/yum/dnf)
    ↓
Dependency Resolver
    ↓
Sandbox Executor (Firejail)
    ↓
Installation Verifier
    ↓
Context Memory (learns patterns)
```

### Key Components

**CLI Interface (`cortex/cli.py`)**
- Command-line interface
- User interaction handling
- Configuration management

**LLM Router (`cortex/llm_router.py`)**
- Multi-LLM support (Claude, Kimi K2)
- Intelligent task routing
- Cost tracking & fallback

**Package Manager (`cortex/packages.py`)**
- Translates intent to commands
- Supports apt, yum, dnf
- 32+ software categories

**Dependency Resolver (`cortex/dependency_resolver.py`)**
- Package conflict detection
- Interactive conflict resolution
- Saved preference management

**Installation History (`cortex/installation_history.py`)**
- Installation tracking
- Rollback support
- Export capabilities

**Context Memory (`cortex/context_memory.py`)**
- AI learning patterns
- Suggestion generation
- User preference tracking

**Error Parser (`cortex/error_parser.py`)**
- Parse installation errors
- Suggest fixes
- Error pattern matching

## Contributing

### Claiming Issues

1. Browse [open issues](https://github.com/cortexlinux/cortex/issues)
2. Comment "I'd like to work on this"
3. Get assigned
4. Submit PR

### PR Requirements

- Tests with >80% coverage
- Documentation included
- Follows code style
- Passes CI checks

### Bounty Program

Cash bounties on merge:
- Critical features: $150-200
- Standard features: $75-150
- Testing/integration: $50-75
- 2x bonus at funding (Feb 2025)

Payment: Bitcoin, USDC, or PayPal

See [Bounty Program](Bounties) for details.

## Testing
```bash
# Run all tests (automatic discovery)
python test/run_all_tests.py

# Run specific test file
python -m unittest test.test_packages

# Run with verbose output
python test/run_all_tests.py -v

# Individual test modules
python -m unittest test.test_cli
python -m unittest test.test_conflict_ui
python -m unittest test.test_llm_router
```

## Code Style
```bash
# Format code
black cortex/ LLM/ test/

# Lint
pylint cortex/ LLM/

# Type checking
mypy cortex/ LLM/
```

## Questions?

- Discord: https://discord.gg/uCqHvxjU83
- GitHub Discussions: https://github.com/cortexlinux/cortex/discussions
