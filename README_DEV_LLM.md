# Cortex /dev/llm Virtual Device

A FUSE-based virtual filesystem providing file-like interface to LLM operations. Enables shell scripts and any Unix program to use LLMs through standard file operations.

## Quick Start

```bash
# Install dependencies
pip install fusepy anthropic

# Set API key (optional - uses mock client without)
export ANTHROPIC_API_KEY=your-key-here

# Mount the device
python -m cortex.kernel_features.llm_device mount /mnt/llm

# Use it!
echo "What is 2+2?" > /mnt/llm/claude/prompt
cat /mnt/llm/claude/response
```

## Features

- **File-based LLM Interface**: Use echo/cat for prompts and responses
- **Multiple Models**: claude, sonnet, haiku, opus endpoints
- **Session Management**: Create sessions via mkdir for conversation history
- **Configuration**: Modify temperature, max_tokens via JSON files
- **Metrics**: Track usage statistics
- **Mock Mode**: Test without API key

## Directory Structure

```
/mnt/llm/
├── claude/              # Claude Sonnet endpoint
│   ├── prompt           # Write prompts here
│   ├── response         # Read responses here
│   ├── config           # JSON configuration
│   └── metrics          # Usage statistics
├── sonnet/              # Alias for Claude Sonnet
├── haiku/               # Claude Haiku (faster)
├── opus/                # Claude Opus (most capable)
├── sessions/            # Named conversation sessions
│   ├── default/         # Default session
│   │   ├── prompt
│   │   ├── response
│   │   ├── config
│   │   ├── history      # Full conversation history
│   │   └── clear        # Write to clear history
│   └── <session-name>/  # Custom sessions
└── status               # System status JSON
```

## Usage Examples

### Basic Prompt/Response

```bash
# Simple query
echo "Explain quantum computing in one sentence" > /mnt/llm/claude/prompt
cat /mnt/llm/claude/response
```

### Use with Unix Pipes

```bash
# Code review
git diff | (echo "Review this code:" && cat) > /mnt/llm/claude/prompt
cat /mnt/llm/claude/response

# Summarize a file
cat README.md | (echo "Summarize:" && cat) > /mnt/llm/claude/prompt
cat /mnt/llm/claude/response
```

### Session Management

```bash
# Create a project session
mkdir /mnt/llm/sessions/my-project

# Have a conversation
echo "I'm building a web app" > /mnt/llm/sessions/my-project/prompt
cat /mnt/llm/sessions/my-project/response

echo "What database should I use?" > /mnt/llm/sessions/my-project/prompt
cat /mnt/llm/sessions/my-project/response

# View full history
cat /mnt/llm/sessions/my-project/history

# Clear history
echo "" > /mnt/llm/sessions/my-project/clear

# Delete session
rmdir /mnt/llm/sessions/my-project
```

### Configuration

```bash
# View current config
cat /mnt/llm/sessions/default/config

# Update config
echo '{"temperature": 0.3, "max_tokens": 1000}' > /mnt/llm/sessions/default/config

# Set system prompt
echo '{"system_prompt": "You are a helpful coding assistant"}' > /mnt/llm/sessions/default/config
```

### Check Status

```bash
cat /mnt/llm/status
# Output:
# {
#   "status": "running",
#   "uptime_seconds": 3600,
#   "total_requests": 42,
#   "total_tokens": 15000,
#   "requests_per_minute": 0.7
# }
```

## CLI Commands

```bash
# Mount the filesystem
cortex-llm-device mount /mnt/llm

# Mount in foreground (for debugging)
cortex-llm-device mount /mnt/llm -f

# Force mock mode (no API calls)
cortex-llm-device mount /mnt/llm --mock

# Unmount
cortex-llm-device umount /mnt/llm

# Check dependencies
cortex-llm-device status
```

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| model | string | claude-3-5-sonnet-20241022 | Model to use |
| temperature | float | 0.7 | Response randomness (0-1) |
| max_tokens | int | 4096 | Maximum response length |
| system_prompt | string | "" | System instruction |

## Requirements

- Python 3.8+
- fusepy (`pip install fusepy`)
- FUSE support (Linux kernel)
- anthropic (`pip install anthropic`) - optional for real API

## Mock Mode

When no `ANTHROPIC_API_KEY` is set or `--mock` flag is used, the device runs in mock mode. This is useful for:

- Testing without API costs
- Development and debugging
- CI/CD pipelines

Mock responses include the original prompt and are clearly marked.

## Testing

```bash
pytest tests/test_llm_device.py -v
```

## Troubleshooting

### "fusepy not installed"
```bash
pip install fusepy
```

### "Permission denied" on mount
```bash
# May need to allow user mounts
sudo chmod 666 /dev/fuse
```

### Filesystem won't unmount
```bash
fusermount -uz /mnt/llm  # Force unmount
```

## Files

- `cortex/kernel_features/llm_device.py` - Main implementation (~730 lines)
- `tests/test_llm_device.py` - Unit tests (~350 lines, 49 tests)
- `README_DEV_LLM.md` - This documentation

## Related Issues

- [#223 /dev/llm Virtual Device - FUSE-Based LLM Interface](https://github.com/cortexlinux/cortex/issues/223)
