# CX LINUX CLAUDE INSTRUCTIONS

## CTO Authority - Execute, Don't Ask
Execute decisively. Ship code. Dominate the $50B Linux sysadmin market.

### Core Mission
CX Linux is the AI-native OS layer that eliminates the need to memorize commands, google errors, or copy-paste from Stack Overflow. Users describe what they need - the AI executes it safely and intelligently.

## PRIORITY 1: BSL 1.1 LICENSE PROTECTION

**ALL CX LINUX CODE IS BSL 1.1 LICENSED**

- **Business Source License 1.1** protects competitive advantage for 4 years
- No commercial use without license from AI Venture Holdings LLC
- Source available for inspection and contribution, not commercial copying
- After 4 years converts to Apache 2.0
- **NEVER suggest Apache/MIT for core features**
- All new files MUST include BSL 1.1 header

```python
"""
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
"""
```

---

## CX Linux Terminal Family

This CLAUDE.md defines standards for **all 4 CX terminals**:

| Terminal | Repository | Purpose |
|----------|------------|---------|
| **CX Terminal** | `cxlinux-ai/cx` | Primary GUI terminal |
| **CX TTY** | `cxlinux-ai/cx-tty` | Virtual console terminal |
| **CX Remote** | `cxlinux-ai/cx-remote` | SSH/remote session terminal |
| **CX Embedded** | `cxlinux-ai/cx-embedded` | Lightweight embedded terminal |

All terminals MUST follow the code style, pricing constants, and branch protection rules defined here.

---

## Pricing Constants

**All 4 terminals MUST use these exact pricing values:**

```rust
// Subscription tier pricing - DO NOT MODIFY without business approval
pub const TIER_CORE_PRICE: u32 = 0;        // Free
pub const TIER_PRO_PRICE: u32 = 1900;      // $19.00 per system (one-time)
pub const TIER_TEAM_PRICE: u32 = 9900;     // $99.00 per month
pub const TIER_ENTERPRISE_PRICE: u32 = 19900; // $199.00 per month
```

### Subscription Tiers

| Tier | Price | Billing | Features |
|------|-------|---------|----------|
| **Core** | Free | - | Local AI only, basic terminal |
| **Pro** | $19/system | One-time | Cloud AI, all providers |
| **Team** | $99/month | Monthly | Team features, shared configs, analytics |
| **Enterprise** | $199/month | Monthly | Full suite, SSO, audit logs, SLA |

### Stripe Product IDs

```bash
# Environment variables for Stripe integration
STRIPE_PRICE_CORE=price_free
STRIPE_PRICE_PRO=price_1ABC...      # $19 one-time
STRIPE_PRICE_TEAM=price_1DEF...     # $99/month recurring
STRIPE_PRICE_ENTERPRISE=price_1GHI... # $199/month recurring
```

---

## PRIORITY 2: ZERO DOCUMENTATION OS LAYER

**The OS layer must understand intent without documentation.**

- Self-documenting command architecture
- Natural language interfaces that need no explanation
- Intent-driven execution: `cx "install nginx"` not `apt install nginx`
- Progressive capability discovery through usage
- Code comments explain WHY, never WHAT
- **No user manuals - the AI IS the manual**

### Implementation Standards:
```python
# ✅ Zero-doc pattern
def natural_install(intent: str) -> ExecutionResult:
    """Understands user intent and executes safely."""

# ❌ Traditional pattern requiring documentation
def install_package(pkg_name: str, flags: List[str]) -> None:
```

## PRIORITY 3: FOUNDING 1,000 ECOSYSTEM

**Early adopter lock-in with network effects and referral mechanics.**

- First 1,000 users get permanent advantages
- 10% of Pro tier revenue to referring users (lifetime)
- Founding member badges and exclusive agent capabilities
- Referral tracking in telemetry and user onboarding
- Network effects compound through shared agent configurations
- **Every feature must strengthen community lock-in**

### Implementation Requirements:
```python
# Founding member tracking in user profiles
@dataclass
class UserProfile:
    founding_member: bool = False
    referral_code: str = Field(factory=generate_referral_code)
    referred_by: Optional[str] = None
    tier: Literal["founding", "pro", "enterprise"] = "founding"
```

---

## Branch Protection Rules

### Ruleset Configuration (ID: 9679118)

All repositories in `@cxlinux-ai` organization use this ruleset:

```json
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          { "context": "Cargo Check" },
          { "context": "Rustfmt" },
          { "context": "Test Suite" },
          { "context": "Documentation Tests" }
        ]
      }
    }
  ],
  "bypass_actors": [
    {
      "actor_id": 5,
      "actor_type": "RepositoryRole",
      "bypass_mode": "always"
    }
  ]
}
```

### Required CI Checks

All PRs must pass these checks before merge:

| Check | Command | Purpose |
|-------|---------|---------|
| Cargo Check | `cargo check --workspace` | Compilation verification |
| Rustfmt | `cargo fmt --all -- --check` | Code formatting |
| Test Suite | `cargo test --workspace` | Unit/integration tests |
| Documentation Tests | `cargo test --doc --workspace` | Doc example verification |

---

## PRIORITY 4: ENTERPRISE RUST/PYTHON ARCHITECTURE

**Production-grade code only. No prototype patterns.**

### Required Standards:
- **Python 3.11+**: asyncio, Pydantic v2, FastAPI, proper typing
- **Rust**: Tokio, Serde, clap, anyhow error handling
- **Security**: Input validation, sandboxed execution, audit trails
- **Testing**: 95%+ coverage, integration tests, property testing
- **Monitoring**: Structured logging, metrics, distributed tracing

### Forbidden Patterns:
```python
# ❌ Prototype patterns - NEVER do this
result = os.system(user_input)
data = json.loads(response.text)  # No error handling
subprocess.run(cmd, shell=True)  # Shell injection risk
```

```python
# ✅ Enterprise patterns - ALWAYS do this
from cx.security import CommandValidator
from cx.types import SafeCommand

async def execute_validated_command(intent: str) -> ExecutionResult:
    safe_cmd = await CommandValidator.parse_intent(intent)
    return await safe_cmd.execute_sandboxed()
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
docs: Update CLAUDE.md with pricing
refactor: Extract subscription validation
style: Apply rustfmt to all files
chore: Update dependencies
test: Add integration tests for daemon IPC
perf: Optimize command block rendering
```

---

## CI Dependencies

### Ubuntu/Debian Build Requirements

All CI workflows must install these packages:

```yaml
- name: Install dependencies
  run: |
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

### macOS Build Requirements

macOS builds require the app bundle structure:

```
assets/macos/CX Terminal.app/
└── Contents/
    └── Info.plist
```

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

---

## CX Linux Development Context

### Current Architecture
- **CLI**: Python 3.11+ with Typer and Rich UI
- **Agents**: Specialized AI agents for package management, system config, security
- **LLM Integration**: Multi-provider routing (OpenAI, Anthropic, local models)
- **Security**: Command validation, sandboxed execution, audit logging
- **Target**: Ubuntu 24.04 LTS primary, Debian/Fedora support

### Market Position
- **TAM**: $50B Linux system administration market
- **Users**: DevOps engineers, system administrators, developers
- **Competitive Moat**: AI-native approach vs traditional documentation/tutorials
- **Revenue Model**: Open source base + Pro tier + Enterprise licenses

### Feature Status
✅ Natural language package installation
✅ System diagnostics and troubleshooting
✅ Multi-LLM provider routing
✅ Command validation and sandboxing
🔄 Founding 1,000 referral system (in progress)
🔄 BSL 1.1 license migration (in progress)
🔄 Enterprise agent marketplace (planned)

---

## Production Deployment

**Pre-deployment verification:**
```bash
# Full release build
cargo build --release

# Run test suite
cargo test

# Run clippy
cargo clippy --workspace -- -D warnings

# Verify branding (should return no results)
grep -r "wezterm/wezterm" . --include="*.toml" | grep -v target
grep -r "cortexlinux" . --include="*.rs" --include="*.md" | grep -v target
```

**Binary location:** `./target/release/cx-terminal-gui`

**Required runtime:**
- `~/.cx/` directory (auto-created)
- CX daemon running for full AI features
- API keys in environment or config for cloud AI

---

## Important Notes

- Never use "cortex" or "cortexlinux" - use "cx" and "cxlinux-ai"
- GitHub: github.com/cxlinux-ai/cx
- Website: cxlinux.ai
- License server: license.cxlinux.ai

---

## Organization Repositories

All 20 repositories in `@cxlinux-ai` follow these standards:

| Repository | Description |
|------------|-------------|
| cx | Primary CX Terminal |
| cx-tty | Virtual console terminal |
| cx-remote | SSH/remote terminal |
| cx-embedded | Embedded terminal |
| cx-daemon | System daemon |
| cx-cli | Command-line interface |
| cx-llm | Local LLM inference |
| cx-network | Network management |
| cx-distro | ISO builder |
| cx-docs | Documentation |
| cx-apt-repo | Package repository |
| cx-website | Marketing site |
| cx-installer | Installation wizard |
| cx-themes | Theme packages |
| cx-plugins | Plugin system |
| cx-analytics | Usage analytics |
| cx-auth | Authentication service |
| cx-api | REST API |
| cx-sdk | Developer SDK |
| cx-examples | Example configurations |

---

## Response Patterns

**Execute immediately:**
```
✅ "Added BSL 1.1 headers to new modules"
✅ "Implemented referral tracking in user onboarding"
✅ "Natural language intent parser handles 'install web server'"
```

**Never ask permission for:**
- Adding BSL 1.1 license headers
- Implementing referral mechanics
- Creating enterprise-grade security layers
- Adding type safety and async patterns
- Performance optimizations
- Zero-documentation UX improvements

**Only pause for:**
- License file modifications (affects all contributors)
- External API key integrations
- Database schema changes
- Breaking changes to public CLI interface

**Architecture Decisions:**
- Python for rapid iteration, Rust for performance-critical components
- Multi-agent architecture with specialized capabilities
- Sandboxed execution with comprehensive audit trails
- Natural language intent parsing with fallback to traditional commands
