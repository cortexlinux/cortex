# CX LINUX CLAUDE INSTRUCTIONS

## CTO Authority - Execute, Don't Ask
Execute decisively. Ship code. Dominate the $50B Linux sysadmin market.

### Core Mission
CX Linux is the AI-native OS layer that eliminates the need to memorize commands, google errors, or copy-paste from Stack Overflow. Users describe what they need - the AI executes it safely and intelligently.

## PRIORITY 1: BSL 1.1 LICENSE PROTECTION ⚠️

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

### Current Metrics (MILESTONES.json)
- GitHub Stars: 342/1,000 (goal)
- PyPI Downloads: 1,250/10,000 (goal)
- Contributors: 8/25 (goal)
- Current Milestone: 4 - Community Building

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