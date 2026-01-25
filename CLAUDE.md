# CX Terminal - Development Guide

## Mission Statement

**CX Terminal is the terminal emulator for the AI-Native Agentic OS.**

CX Linux reimagines the operating system for an era where AI agents are first-class citizens. CX Terminal serves as the primary interface between users and AI agents, providing:

- **Command Blocks**: AI-generated commands with context, explanations, and one-click execution
- **Voice-First Input**: Natural language command entry via local speech recognition
- **Learning System**: Privacy-preserving adaptation to user workflows
- **Agent Integration**: Native support for file, system, and code agents
- **Daemon Communication**: Real-time IPC with the CX system daemon

## Project Overview
CX Terminal is an AI-native terminal emulator for CX Linux, forked from WezTerm.

## Build Commands
```bash
# Quick check (fast, no binary)
cargo check

# Debug build
cargo build

# Release build (optimized)
cargo build --release

# Run debug binary
cargo run --bin cx-terminal-gui

# Run release binary
./target/release/cx-terminal-gui
```

## Test Commands
```bash
# Run all tests
cargo test

# Run specific package tests
cargo test -p cx-terminal-gui
cargo test -p config

# Run with output
cargo test -- --nocapture
```

## Code Style
- Rust 2018 edition
- Follow existing WezTerm patterns
- Mark CX additions with `// CX Terminal:` comments
- Use `log::info!`, `log::debug!`, `log::error!` for logging

## Key Directories
| Path | Purpose |
|------|---------|
| `wezterm-gui/src/ai/` | AI panel, providers, streaming |
| `wezterm-gui/src/agents/` | Agent system (file, system, code) |
| `wezterm-gui/src/blocks/` | Command blocks system |
| `wezterm-gui/src/voice/` | Voice input with cpal |
| `wezterm-gui/src/learning/` | ML training, user model |
| `wezterm-gui/src/workflows/` | Workflow automation |
| `wezterm-gui/src/subscription/` | Licensing, Stripe integration |
| `wezterm-gui/src/cx_daemon/` | CX daemon IPC client |
| `shell-integration/` | Bash/Zsh/Fish integration |
| `config/src/` | Configuration, Lua bindings |
| `examples/` | Example configs (cx.lua) |

## Config Paths
- User config: `~/.cx.lua` or `~/.config/cx/cx.lua`
- Data dir: `~/.config/cx-terminal/`
- Daemon socket: `~/.cx/daemon.sock`

## Environment Variables
| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude API access |
| `OLLAMA_HOST` | Local LLM endpoint |
| `CX_TERMINAL` | Set by terminal for shell detection |
| `TERM_PROGRAM` | Set to "CXTerminal" |

## Subscription Tiers
- Core: Free (local AI only)
- Pro: $19/system (cloud AI)
- Team: $49/mo (team features)
- Enterprise: $199/mo (full suite)

## Commit Style
```
feat: Add new feature
fix: Bug fix
docs: Documentation
refactor: Code refactoring
style: Formatting
chore: Maintenance
```

## Security Constraints

**Critical security measures implemented:**

1. **Webhook Verification**: Stripe webhooks use HMAC-SHA256 signature verification
2. **Learning Data Privacy**: User learning data stored with `0o700` permissions (owner-only)
3. **IPC Socket Security**: No `/tmp` fallback - sockets only in secure user directories
4. **Privacy Filters**: All privacy filters (IP, email, username anonymization) enabled by default

**Security audit checklist:**
```bash
# Verify learning data permissions
ls -la ~/.config/cx-terminal/

# Verify socket permissions
ls -la ~/.cx/daemon.sock

# Check no secrets in environment
env | grep -i "key\|secret\|token" | head -5
```

## Production Deployment

**Pre-deployment verification:**
```bash
# Full release build
cargo build --release

# Run test suite
cargo test

# Verify branding (should return no results)
grep -r "wezterm/wezterm" . --include="*.toml" | grep -v target
grep -r "cortexlinux" . --include="*.rs" --include="*.md" | grep -v target
```

**Binary location:** `./target/release/cx-terminal-gui`

**Required runtime:**
- `~/.cx/` directory (auto-created)
- CX daemon running for full AI features
- API keys in environment or config for cloud AI

## Attribution

CX Terminal is built on the excellent [WezTerm](https://wezfurlong.org/wezterm/) by Wez Furlong, licensed under MIT.

## Important Notes
- Never use "cortex" or "cortexlinux" - use "cx" and "cxlinux-ai"
- GitHub: github.com/cxlinux-ai/cx
- Website: cxlinux.ai
- License server: license.cxlinux.ai
