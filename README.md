# Cortex Linux

An AI-powered package manager for Debian/Ubuntu that understands natural language.
```bash
$ cortex install nginx --dry-run

🧠 Understanding request...
📦 Planning installation...

Packages to install:
  - nginx (1.24.0)
  - nginx-common
  - libnginx-mod-http-geoip

Commands that will be executed:
  sudo apt update
  sudo apt install -y nginx

Run with --execute to install, or edit the plan above.
```

## What It Does

Cortex wraps `apt` with AI to:
- Parse natural language requests ("install something for web serving")
- Detect hardware and optimize installations for your GPU/CPU
- Resolve dependency conflicts interactively
- Track installation history with rollback support
- Run in dry-run mode by default (no surprises)

## Installation
```bash
# Clone the repo
git clone https://github.com/cortexlinux/cortex.git
cd cortex

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install
pip install -e .

# Set your API key
echo 'ANTHROPIC_API_KEY=your-key-here' > .env

# Test it
cortex install nginx --dry-run
```

## Usage
```bash
# Preview what will happen (safe, no changes)
cortex install nginx --dry-run

# Actually install
cortex install nginx --execute

# Natural language works
cortex install "something to edit PDFs" --dry-run

# View installation history
cortex history

# Rollback an installation
cortex rollback <id>

# Check preferences
cortex check-pref
```

## Safety

Cortex is designed to be safe by default:

| Feature | Description |
|---------|-------------|
| **Dry-run default** | Shows planned commands without executing |
| **Firejail sandbox** | Commands run in isolated environment |
| **Rollback support** | Undo any installation with `cortex rollback` |
| **Audit logging** | All actions logged to `~/.cortex/history.db` |
| **No root by default** | Only uses sudo when explicitly needed |

## Project Status

### Completed
- ✅ CLI with dry-run and execute modes
- ✅ Claude and OpenAI integration
- ✅ Installation history and rollback
- ✅ User preferences (YAML-backed)
- ✅ Hardware detection
- ✅ Firejail sandboxing
- ✅ Kernel optimization features

### In Progress
- 🔄 Conflict resolution UI (PR #192)
- 🔄 Multi-step orchestration
- 🔄 Ollama local model support

### Planned
- ⏳ Configuration file generation
- ⏳ Error diagnosis and auto-fix
- ⏳ Multi-distro support (Fedora, Arch)

## Tech Stack

| Component | Technology |
|-----------|------------|
| Base OS | Ubuntu 22.04+ / Debian 12+ |
| Language | Python 3.10+ |
| LLM | Claude API, OpenAI API (Ollama planned) |
| Security | Firejail, AppArmor |
| Package Backend | apt/dpkg |

## Kernel Features

Cortex includes optional kernel-level optimizations for LLM workloads:
```bash
cd cortex/kernel_features
sudo ./install.sh

# Detect your GPU/NPU
cortex-detect-hardware

# Apply system optimizations
sudo sysctl -p /etc/sysctl.d/99-cortex-llm.conf
```

See `cortex/kernel_features/README.md` for details.

## Contributing

We need:
- Python developers (package manager features)
- Linux kernel developers (kernel optimizations)
- Technical writers (documentation)
- Beta testers (bug reports)

Bounties available for merged PRs. See issues labeled `bounty`.

## Community

- Discord: [discord.gg/uCqHvxjU83](https://discord.gg/uCqHvxjU83)
- Email: mike@cortexlinux.com

## License

Apache 2.0
