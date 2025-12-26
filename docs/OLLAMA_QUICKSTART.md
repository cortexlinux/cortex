# Ollama Quick Start Guide

Get started with Cortex Linux's local LLM support in 5 minutes!

## 🚀 Installation (2 minutes)

```bash
# 1. Clone and enter directory
git clone https://github.com/cortexlinux/cortex.git
cd cortex

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Cortex (auto-installs Ollama)
pip install -e .
```

**That's it!** Ollama will be automatically installed and configured.

## ✅ Verify Installation (30 seconds)

```bash
# Check Cortex
cortex --version

# Check Ollama
ollama list

# Should show at least one model (e.g., phi3:mini)
```

## 🎯 First Command (1 minute)

```bash
# Try it without any API keys!
cortex install nginx --dry-run
```

**Expected output:**
```
🧭 Routing: system_operation → ollama (optimal for this task)
✅ Using local model: phi3:mini
📦 Analyzing request...
✅ Package identified: nginx
📋 Installation plan:
  - sudo apt update
  - sudo apt install -y nginx
  
💰 Cost: $0.00 (100% local)
```

## 🎉 You're Done!

No API keys needed. Everything runs locally. Zero cost. Complete privacy.

## 🔧 Optional: Better Models

The default `phi3:mini` (1.9GB) is lightweight. For better quality:

```bash
# Balanced performance (4.7GB, recommended)
ollama pull llama3:8b

# Code-optimized (9GB, best for Cortex)
ollama pull codellama:13b

# Best quality (10GB+, if you have the resources)
ollama pull deepseek-coder-v2:16b
```

Cortex will automatically use the best available model.

## ☁️ Optional: Cloud Fallback

Want cloud providers as backup? Just set API keys:

```bash
# Add to .env file
echo 'ANTHROPIC_API_KEY=your-key' > .env
echo 'OPENAI_API_KEY=your-key' >> .env

# Cortex will use Ollama first, cloud as fallback
```

## 📖 Learn More

- **Full Guide:** [docs/OLLAMA_INTEGRATION.md](OLLAMA_INTEGRATION.md)
- **Examples:** [examples/ollama_demo.py](../examples/ollama_demo.py)
- **Discord:** https://discord.gg/uCqHvxjU83

## 🆘 Troubleshooting

### Ollama Not Starting?
```bash
# Start manually
ollama serve &

# Or re-run setup
cortex-setup-ollama
```

### No Models Available?
```bash
# Pull default model
ollama pull phi3:mini
```

### Want to Skip Auto-Install?
```bash
# Set before pip install
export CORTEX_SKIP_OLLAMA_SETUP=1
pip install -e .
```

## 💡 Tips

- 🚀 Use `--dry-run` to preview without executing
- 🔄 Cortex auto-selects the best available model
- 💰 Check cost with `cortex history` (should show $0.00)
- 🔒 100% privacy - no data leaves your machine
- 📴 Works completely offline after setup

## 🎓 Next Steps

1. Try different package installations
2. Explore `cortex history` and `cortex rollback`
3. Download better models for improved quality
4. Read the full documentation
5. Join our Discord community

---

**Welcome to privacy-first package management!** 🎉
