# /dev/llm Virtual Device

**Bounty:** cortexlinux/cortex#223  
**Author:** Yair Siegel  
**Tests:** 20/20 passing

## Overview

FUSE-based virtual filesystem providing file-like interface to LLM APIs.
Enables shell scripts and any Unix program to use LLMs.

## Features

- **File-Based Interface:** Write prompts, read responses
- **Multiple Clients:** Claude API with mock fallback for testing
- **Session Management:** Stateful conversations with history
- **Configuration:** JSON config for model parameters
- **Metrics:** Track API calls and token usage

## Directory Structure

```
/mnt/llm/
├── claude/              # Claude Sonnet
│   ├── prompt           # Write prompts here
│   ├── response         # Read responses
│   ├── config           # JSON configuration
│   └── metrics          # Usage stats
├── sessions/            # Stateful conversations
│   └── <session-name>/
│       ├── prompt
│       ├── response
│       ├── history
│       └── config
└── status               # System status
```

## Usage

```bash
# Mount the filesystem
python llm_device.py mount /mnt/llm

# Simple query
echo "What is 2+2?" > /mnt/llm/claude/prompt
cat /mnt/llm/claude/response

# Check status
cat /mnt/llm/status

# Use in shell scripts
ask_llm() {
    echo "$1" > /mnt/llm/claude/prompt
    cat /mnt/llm/claude/response
}
ask_llm "Explain Docker in one sentence"

# Stateful sessions
mkdir /mnt/llm/sessions/my-project
echo "What is Python?" > /mnt/llm/sessions/my-project/prompt
cat /mnt/llm/sessions/my-project/response
echo "Tell me more" > /mnt/llm/sessions/my-project/prompt  # Context maintained
cat /mnt/llm/sessions/my-project/history
```

## Testing

```bash
# Quick test without mounting
python llm_device.py test

# Run unit tests
python test_llm_device.py
```

## Requirements

- fusepy (`pip install fusepy`)
- anthropic (`pip install anthropic`) for Claude API
- FUSE kernel module (pre-installed on most Linux systems)
