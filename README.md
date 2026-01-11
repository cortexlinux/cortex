<p align="center">
  <img src="images/logo.png" alt="Cortex Linux" width="200" />
</p>

<h1 align="center">Cortex Linux</h1>

<p align="center">
  <strong>Cortex is an AI layer for Linux Debian/Ubuntu</strong><br>
 Instead of memorizing commands, googling errors, and copy-pasting from Stack Overflow — describe what you need.
</p>

<p align="center">
  <a href="https://github.com/cortexlinux/cortex/actions/workflows/ci.yml">
    <img src="https://github.com/cortexlinux/cortex/actions/workflows/ci.yml/badge.svg" alt="CI Status" />
  </a>
  <a href="https://github.com/cortexlinux/cortex/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License" />
  </a>
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+" />
  </a>
  <a href="https://github.com/cortexlinux/cortex/releases">
    <img src="https://img.shields.io/badge/version-0.1.0--alpha-orange.svg" alt="Version" />
  </a>
  <a href="https://discord.gg/uCqHvxjU83">
    <img src="https://img.shields.io/discord/1234567890?color=7289da&label=Discord&logo=discord&logoColor=white" alt="Discord" />
  </a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#features">Features</a> •
  <a href="#usage">Usage</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#contributing">Contributing</a> •
  <a href="#community">Community</a>
</p>

---

## What is Cortex?

<strong>Cortex is an AI layer for Linux Debian/Ubuntu</strong><br>
Instead of memorizing commands, googling errors, and copy-pasting from Stack Overflow — describe what you need.
```bash
# Instead of googling "what's the package name for PDF editing on Ubuntu?"
cortex install "something to edit PDFs"

# Instead of remembering exact package names
cortex install "a lightweight code editor with syntax highlighting"

# Natural language just works
cortex install "tools for video compression"
```

<p align="center">
  <img src="images/cortex_demo.gif" alt="Cortex Demo" width="700" />
</p>

---

## Features

| Feature | Description |
|---------|-------------|
| **Natural Language** | Describe what you need in plain English |
| **Dry-Run Default** | Preview all commands before execution |
| **Sandboxed Execution** | Commands run in Firejail isolation |
| **Full Rollback** | Undo any installation with `cortex rollback` |
| **AI System Roles** | Dynamic context sensing with PII redaction and operational history learning. |
| **Docker Permission Fixer** | Fix root-owned bind mount issues automatically |
| **Audit Trail** | Complete history in `~/.cortex/history.db` |
| **Hardware-Aware** | Optimizes for NVIDIA (CUDA), AMD (ROCm), and Intel GPU architectures. |
| **Multi-LLM Support** | Works with Claude, GPT-4, or local Ollama models |

---

## Quick Start

### Prerequisites

- **OS:** Ubuntu 22.04+ / Debian 12+
- **Python:** 3.10 or higher
- **API Key:** [Anthropic](https://console.anthropic.com) or [OpenAI](https://platform.openai.com) *(optional - use Ollama for free local inference)*

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/cortexlinux/cortex.git
cd cortex

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Cortex
pip install -e .

# 4. Configure AI Provider (choose one):

## Option A: Ollama (FREE - Local LLM, no API key needed)
python scripts/setup_ollama.py

## Option B: Claude (Cloud API - Best quality)
echo 'ANTHROPIC_API_KEY=your-key-here' > .env

## Option C: OpenAI (Cloud API - Alternative)
echo 'OPENAI_API_KEY=your-key-here' > .env

# 5. Verify installation
cortex --version
```

> **💡 Zero-Config:** If you already have API keys from Claude CLI (`~/.config/anthropic/`) or OpenAI CLI (`~/.config/openai/`), Cortex will auto-detect them! Environment variables work immediately without prompting. See [Zero Config API Keys](docs/ZERO_CONFIG_API_KEYS.md).

### First Run

```bash
# Preview what would be installed (safe, no changes made)
cortex install nginx --dry-run

# Actually install
cortex install nginx --execute
```

---

## Usage

### Basic Commands

```bash
# Install with natural language
cortex install "web server for static sites" --dry-run
cortex install "image editing software like photoshop" --execute

# View installation history
cortex history

# Rollback an installation
cortex rollback <installation-id>
```

### Command Reference

| Command | Description |
|---------|-------------|
| `cortex install <query>` | Install packages matching natural language query |
| `cortex install <query> --dry-run` | Preview installation plan (default) |
| `cortex install <query> --execute` | Execute the installation |
| `cortex role detect` | AI analysis of system context to identify system role |
| `cortex role set <slug>` | Manually declare a role to receive AI-tailored recommendations |
| `cortex docker permissions` | Fix file ownership for Docker bind mounts |
| `cortex sandbox <cmd>` | Test packages in Docker sandbox |
| `cortex history` | View all past installations |
| `cortex rollback <id>` | Undo a specific installation |
| `cortex --version` | Show version information |
| `cortex --help` | Display help message |

### Configuration

Cortex stores configuration in `~/.cortex/`:

```
~/.cortex/
├── config.yaml      # User preferences
├── history.db       # Installation history (SQLite)
└── audit.log        # Detailed audit trail
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Input                              │
│                    "install video editor"                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Interface                            │
│                         (cli.py)                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      LLM Router                                 │
│              Claude / GPT-4 / Ollama                            │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Anthropic  │  │   OpenAI    │  │   Ollama    │              │
│  │   Claude    │  │    GPT-4    │  │   Local     │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Coordinator                                 │
│            (Plan Generation & Validation)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│    AI Role      │ │    Package      │ │    Sandbox      │
│    Sensing      │ │    Manager      │ │    Executor     │
│(Redaction Layer)│ │  (apt/yum/dnf)  │ │   (Firejail)    │
└─────────────────┘ └─────────────────┘ └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Installation History                          │
│                 (SQLite + Audit Logging)                        │
└─────────────────────────────────────────────────────────────────┘
```

### Project Structure

```
cortex/
├── cortex/                 # Main package
│   ├── cli.py              # Command-line interface
│   ├── coordinator.py      # Installation orchestration
│   ├── role_manager.py     # Role management logic
│   ├── llm_router.py       # Multi-LLM routing
│   ├── packages.py         # Package manager wrapper
│   ├── hardware_detection.py
│   ├── installation_history.py
│   └── utils/              # Utility modules
├── tests/                  # Test suite
├── docs/                   # Documentation
├── examples/               # Example scripts
└── scripts/                # Utility scripts
```

---

## Safety & Security

Cortex is designed with security as a priority:

| Protection | Implementation |
|------------|----------------|
| **Dry-run by default** | No execution without `--execute` flag |
| **Sandboxed execution** | All commands run in Firejail containers |
| **Command validation** | Dangerous patterns blocked before execution |
| **Audit logging** | Every action recorded with timestamps |
| **Rollback capability** | Full undo support for all installations |
| **No root by default** | Sudo only when explicitly required |

### Security Policy

Found a vulnerability? Please report it responsibly:
- Email: security@cortexlinux.com
- See [SECURITY.md](SECURITY.md) for our disclosure policy

---

## Troubleshooting

<details>
<summary><strong>"No API key found"</strong></summary>

Cortex auto-detects API keys from multiple locations. If none are found:

```bash
# Option 1: Set environment variables (used immediately, no save needed)
export ANTHROPIC_API_KEY=sk-ant-your-key
cortex install nginx --dry-run

# Option 2: Save directly to Cortex config
echo 'ANTHROPIC_API_KEY=sk-ant-your-key' > ~/.cortex/.env

# Option 3: Use Ollama (free, local, no key needed)
export CORTEX_PROVIDER=ollama
python scripts/setup_ollama.py

# Option 4: If you have Claude CLI installed, Cortex will find it automatically
# Just run: cortex install nginx --dry-run
```

See [Zero Config API Keys](docs/ZERO_CONFIG_API_KEYS.md) for details.
</details>

<details>
<summary><strong>"command not found: cortex"</strong></summary>

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall
pip install -e .
```
</details>

<details>
<summary><strong>"Python version too old"</strong></summary>

```bash
# Check version
python3 --version

# Install Python 3.11 on Ubuntu/Debian
sudo apt update
sudo apt install python3.11 python3.11-venv

# Create venv with specific version
python3.11 -m venv venv
```
</details>

<details>
<summary><strong>pip install fails</strong></summary>

```bash
# Update pip
pip install --upgrade pip

# Install build dependencies
sudo apt install python3-dev build-essential

# Retry installation
pip install -e .
```
</details>

---

## Project Status

> **Alpha Release** - Cortex is under active development. APIs may change.

### Completed
- [x] Natural language to package resolution
- [x] Claude and OpenAI integration
- [x] Installation history and rollback
- [x] User preferences (YAML-backed)
- [x] Hardware detection (GPU/CPU/Memory)
- [x] Firejail sandboxing
- [x] Dry-run preview mode
- [x] Docker bind-mount permission fixer
- [x] AI-driven System Role sensing layer

### In Progress
- [ ] Conflict resolution UI
- [ ] Multi-step orchestration
- [ ] Ollama local model support
- [ ] MCP server integration
- [ ] Snap/Flatpak support

### Planned
- [ ] Fedora/RHEL support
- [ ] Arch Linux support
- [ ] Web UI dashboard
- [ ] VS Code extension

See [ROADMAP.md](docs/ROADMAP.md) for the full development roadmap.

---

## Contributing

We welcome contributions of all kinds!

### Ways to Contribute

- **Code**: Python, Linux kernel optimizations
- **Documentation**: Guides, tutorials, API docs
- **Testing**: Bug reports, test coverage
- **Design**: UI/UX improvements

### Bounty Program

We offer bounties for merged PRs:

| Tier | Reward | Examples |
|------|--------|----------|
| Small | $25 | Bug fixes, typos, minor features |
| Medium | $50-100 | New features, significant improvements |
| Large | $150-200 | Major features, security fixes |

See issues labeled [`bounty`](https://github.com/cortexlinux/cortex/labels/bounty) for available tasks.

### Getting Started

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/cortex.git
cd cortex

# Setup development environment
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/ -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## Community

- **Discord**: [discord.gg/uCqHvxjU83](https://discord.gg/uCqHvxjU83)
- **Discussions**: [GitHub Discussions](https://github.com/cortexlinux/cortex/discussions)
- **Email**: mike@cortexlinux.com
- **Twitter**: [@cortexlinux](https://twitter.com/cortexlinux)

### Support

- **Bug Reports**: [GitHub Issues](https://github.com/cortexlinux/cortex/issues)
- **Feature Requests**: [GitHub Discussions](https://github.com/cortexlinux/cortex/discussions/categories/ideas)
- **Security Issues**: security@cortexlinux.com

---

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

---

<p align="center">
  <sub>Built with love by the Cortex team and contributors worldwide.</sub>
</p>
