# CX Terminal Development Guide

CX Terminal is an AI-native terminal emulator built on a fork of WezTerm, designed for the CX Linux ecosystem.

## License

CX Terminal is licensed under the **Business Source License 1.1** (BSL 1.1).

- Source available for inspection and contribution
- Commercial use requires a license from AI Venture Holdings LLC
- Converts to Apache License 2.0 after **6 years** from each version release

All new files must include the BSL 1.1 header:

```rust
// Copyright (c) 2026 AI Venture Holdings LLC
// Licensed under the Business Source License 1.1
// You may not use this file except in compliance with the License.
```

---

## Build Requirements

### Ubuntu/Debian

```bash
sudo apt-get update
sudo apt-get install -y \
  cmake \
  libfontconfig1-dev \
  libfreetype6-dev \
  libx11-dev \
  libx11-xcb-dev \
  libxcb1-dev \
  libxcb-render0-dev \
  libxcb-shape0-dev \
  libxcb-xfixes0-dev \
  libxcb-keysyms1-dev \
  libxcb-icccm4-dev \
  libxcb-image0-dev \
  libxcb-util-dev \
  libxkbcommon-dev \
  libxkbcommon-x11-dev \
  libwayland-dev \
  libssl-dev \
  libegl1-mesa-dev \
  libasound2-dev
```

### macOS

macOS builds require the app bundle structure at `assets/macos/CX Terminal.app/`.

---

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

# Run clippy
cargo clippy --workspace -- -D warnings
```

---

## Code Style

### Rust Standards

- **Edition**: Rust 2021
- **Formatting**: `rustfmt` with default settings
- **Linting**: `clippy` with `-D warnings` (treat warnings as errors)
- **Comments**: Mark CX additions with `// CX Terminal:` prefix

```rust
// CX Terminal: AI panel integration
pub struct AiPanel {
    provider: Box<dyn AiProvider>,
    // ...
}
```

### Logging

Use the `log` crate consistently:

```rust
use log::{info, debug, warn, error, trace};

info!("Starting CX Terminal v{}", env!("CARGO_PKG_VERSION"));
debug!("Config loaded from {:?}", config_path);
warn!("Fallback to local AI - no API key");
error!("Failed to connect to daemon: {}", e);
trace!("Frame rendered in {}ms", duration);
```

### Error Handling

```rust
// Preferred: Use anyhow for application errors
use anyhow::{Context, Result};

fn load_config() -> Result<Config> {
    let path = config_path().context("Failed to determine config path")?;
    let content = fs::read_to_string(&path)
        .with_context(|| format!("Failed to read config from {:?}", path))?;
    Ok(toml::from_str(&content)?)
}
```

### Commit Messages

Follow Conventional Commits:

```
feat: Add voice input support
fix: Resolve memory leak in AI panel
docs: Update documentation
refactor: Extract subscription validation
style: Apply rustfmt to all files
chore: Update dependencies
test: Add integration tests for daemon IPC
perf: Optimize command block rendering
```

---

## Project Structure

| Path | Purpose |
|------|---------|
| `wezterm-gui/src/ai/` | AI panel, providers, streaming |
| `wezterm-gui/src/agents/` | Agent system (file, system, code) |
| `wezterm-gui/src/blocks/` | Command blocks system |
| `wezterm-gui/src/voice/` | Voice input with cpal |
| `wezterm-gui/src/subscription/` | Licensing integration |
| `shell-integration/` | Bash/Zsh/Fish integration |
| `config/src/` | Configuration, Lua bindings |
| `examples/` | Example configs (cx.lua) |

## Configuration

- User config: `~/.cx.lua` or `~/.config/cx/cx.lua`
- Data directory: `~/.config/cx-terminal/`

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude API access |
| `OLLAMA_HOST` | Local LLM endpoint |
| `CX_TERMINAL` | Set by terminal for shell detection |
| `TERM_PROGRAM` | Set to "CXTerminal" |

---

## CI Requirements

All PRs must pass these checks before merge:

| Check | Command | Purpose |
|-------|---------|---------|
| Cargo Check | `cargo check --workspace` | Compilation verification |
| Rustfmt | `cargo fmt --all -- --check` | Code formatting |
| Test Suite | `cargo test --workspace` | Unit/integration tests |
| Documentation Tests | `cargo test --doc --workspace` | Doc example verification |

---

## Production Verification

```bash
# Full release build
cargo build --release

# Run test suite
cargo test

# Run clippy
cargo clippy --workspace -- -D warnings

# Verify branding
grep -r "wezterm/wezterm" . --include="*.toml" | grep -v target
```

**Binary location:** `./target/release/cx-terminal-gui`

---

## Links

- **GitHub**: github.com/cxlinux-ai/cx
- **Website**: cxlinux.ai
- **Documentation**: docs.cxlinux.ai

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Ensure all CI checks pass
4. Submit a pull request

All contributions are subject to the BSL 1.1 license terms.
