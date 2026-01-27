# GitHub Copilot Instructions for CX Linux

## Project Overview
CX Linux is the AI-native OS layer for the $50B Linux system administration market. Instead of memorizing commands and googling errors, users describe their intent and the AI executes it safely and intelligently.

## MANDATORY PRIORITIES

### 1. BSL 1.1 License Protection ⚠️
- ALL code suggestions must include BSL 1.1 license header
- NEVER suggest Apache, MIT, or other permissive licenses
- Business Source License protects competitive advantage for 4 years
- Owned by AI Venture Holdings LLC

```python
"""
Copyright (c) 2026 AI Venture Holdings LLC
Licensed under the Business Source License 1.1
You may not use this file except in compliance with the License.
"""
```

### 2. Zero Documentation OS Layer
- Suggest self-documenting natural language interfaces
- Intent-driven patterns: `cx "install web server"` not `apt install nginx`
- Comments explain WHY, never WHAT or HOW
- Progressive capability discovery through usage
- No user manuals - the AI IS the interface

### 3. Founding 1,000 Network Effects
- Every feature suggestion must strengthen community lock-in
- Include referral tracking in user-facing components
- Suggest founding member exclusive capabilities
- 10% lifetime revenue sharing for referrals

### 4. Enterprise Rust/Python Architecture
- Python 3.11+: asyncio, Pydantic v2, proper typing
- Rust: Tokio, Serde, clap, anyhow error handling
- 95%+ test coverage suggestions
- Sandboxed execution patterns
- Structured logging and metrics

## Code Standards

### ✅ Suggest These Patterns:

```python
# Enterprise async patterns with security
from cx.security import CommandValidator
from cx.types import SafeCommand, ExecutionResult

async def execute_user_intent(intent: str) -> ExecutionResult:
    """Natural language intent execution with safety validation."""
    try:
        safe_cmd = await CommandValidator.parse_intent(intent)
        result = await safe_cmd.execute_sandboxed()
        await audit_logger.log_execution(intent, safe_cmd, result)
        return result
    except SecurityViolation as e:
        raise CommandRejectedError(f"Unsafe command rejected: {e}")
```

```python
# Founding member referral tracking
@dataclass
class UserOnboarding:
    referral_code: str = Field(factory=generate_referral_code)
    referred_by: Optional[str] = None
    founding_member: bool = False

    async def process_referral_signup(self, referrer_code: str) -> ReferralResult:
        """Process new user signup with referral tracking."""
```

```rust
// Rust performance-critical components
use tokio::process::Command;
use serde::{Deserialize, Serialize};
use anyhow::Result;

#[derive(Serialize, Deserialize)]
pub struct SafeCommand {
    intent: String,
    validated_cmd: Vec<String>,
    risk_level: RiskLevel,
}

impl SafeCommand {
    pub async fn execute_sandboxed(&self) -> Result<ExecutionResult> {
        // Enterprise-grade sandboxed execution
    }
}
```

### ❌ Never Suggest These Patterns:

```python
# Prototype patterns - FORBIDDEN
import os
os.system(user_input)  # Shell injection risk

subprocess.run(cmd, shell=True)  # Unsafe execution

data = json.loads(response.text)  # No error handling
```

## CX Linux Context

### Core Architecture:
- Python CLI with Typer and Rich terminal UI
- Multi-agent system for specialized capabilities
- LLM routing across OpenAI, Anthropic, local models
- Command validation and sandboxed execution
- Ubuntu 24.04 LTS primary target

### Key Modules:
- `cx/cli.py`: Main CLI entry point with natural language parsing
- `cx/coordinator.py`: Agent orchestration and execution planning
- `cx/agents/`: Specialized agents (package, system, security, network)
- `cx/security/`: Command validation, sandboxing, audit trails
- `cx/llm/`: Multi-provider LLM routing and prompt management

### User Experience Philosophy:
- Natural language intent parsing: `cx "make my system faster"`
- Progressive capability discovery through suggestions
- Safety-first with dry-run and confirmation for dangerous operations
- Zero-config for common operations, powerful config for advanced users

## Completion Rules

### Always Include:
- BSL 1.1 license headers on new files
- Async patterns for I/O operations
- Type hints with Pydantic models
- Error handling with proper Result types
- Referral tracking in user flows
- Command validation and sandboxing

### Context-Aware Suggestions:
- When handling user commands: Add intent parsing and validation
- When creating CLI commands: Use natural language interfaces
- When writing agents: Include founding member exclusive features
- When handling system operations: Implement safety checks and audit logging
- When processing user input: Always validate and sandbox

### Security-First Patterns:
- Never execute raw shell commands from user input
- Always use parameterized commands, not string concatenation
- Implement proper input validation with allow-lists
- Add comprehensive audit logging for all system operations
- Use principle of least privilege for file/system access

### Network Effect Amplifiers:
- Suggest shared agent configurations between users
- Include community-driven capability extensions
- Add referral mechanics to successful command executions
- Implement founding member exclusive agent capabilities
- Create viral sharing mechanisms for useful command patterns

### Performance Optimization:
- Suggest async/await for I/O bound operations
- Recommend caching for repeated LLM queries
- Use efficient data structures for command history
- Implement lazy loading for heavy modules
- Add telemetry for performance monitoring