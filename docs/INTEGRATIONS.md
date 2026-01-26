# CX Terminal/Linux AI Integrations & Partners

## Current Integrations

| Provider | Status | Type | Notes |
|----------|--------|------|-------|
| Ollama | Active | Local LLM | Primary local inference engine |
| Claude API | Active | Cloud Fallback | Anthropic API for complex reasoning |

---

## Priority Integration Matrix

### Tier 1: Critical (Launch Blockers)
High value, low complexity - integrate before v1.0

| Partner | Type | Complexity | Value | API Compatibility |
|---------|------|------------|-------|-------------------|
| **Jan.ai** | Local LLM Runtime | Low | High | OpenAI-compatible (localhost:1337) |
| **LocalAI** | Self-hosted LLM | Low | High | OpenAI-compatible drop-in |
| **Shell GPT** | CLI AI Tool | Low | Medium | OpenAI/Ollama compatible |

### Tier 2: High Priority (v1.1)
Strategic partnerships for ecosystem growth

| Partner | Type | Complexity | Value | Notes |
|---------|------|------------|-------|-------|
| **Sentient GRID** | Decentralized AI | Medium | High | 110+ partners, token rewards, agent marketplace |
| **OpenMind AGI (OM1)** | Robot OS | Medium | Medium | Plug-and-play OpenAI/Gemini/DeepSeek |
| **LF AI & Data** | Foundation | Medium | High | Linux Foundation credibility, enterprise adoption |

### Tier 3: Enterprise (v1.2+)
Major cloud providers for enterprise deployments

| Partner | Type | Complexity | Value | Notes |
|---------|------|------------|-------|-------|
| **OpenAI** | Cloud API | Low | High | GPT-4/5, Responses API with shell tool |
| **Google (Vertex AI)** | Cloud API | Medium | High | Gemini models, enterprise MLOps |
| **Amazon (Bedrock)** | Cloud API | Medium | High | Multi-model access, AWS ecosystem |
| **Microsoft (Azure AI)** | Cloud API | Medium | High | Enterprise, GitHub Copilot synergy |

### Tier 4: ML Infrastructure (Future)
Deep integration for power users

| Partner | Type | Complexity | Value | Notes |
|---------|------|------------|-------|-------|
| **PyTorch** | ML Framework | High | Medium | Training/fine-tuning support |
| **TensorFlow** | ML Framework | High | Medium | Model serving, TF Lite for edge |
| **Ubuntu MLOps** | Platform | Medium | Medium | Canonical's ML stack |

---

## Integration Details

### Jan.ai
**Status**: Ready for integration
**API Endpoint**: `http://127.0.0.1:1337` (OpenAI-compatible)
**Key Features**:
- 100% offline operation
- Downloads models from HuggingFace (Llama, Mistral, Gemma, Qwen)
- MCP (Model Context Protocol) support
- Cross-platform (Mac, Windows, Linux)
- GPU support: NVIDIA (CUDA), AMD (Vulkan), Intel Arc

**Integration Path**:
```rust
// Add to cx_daemon/client.rs
pub enum LLMBackend {
    Ollama,
    Jan,
    LocalAI,
    Claude,
}
```

**Sources**: [Jan.ai Docs](https://www.jan.ai/docs), [Jan GitHub](https://github.com/janhq/jan)

---

### LocalAI
**Status**: Ready for integration
**API Endpoint**: `http://localhost:8080` (OpenAI-compatible)
**Key Features**:
- MIT Licensed, fully open source
- No GPU required - runs on consumer hardware
- Supports LLMs, image generation, audio models
- Docker-first deployment
- Part of LocalAGI ecosystem (agent orchestration)

**Integration Path**:
```bash
# Docker deployment
docker run -p 8080:8080 --name local-ai -ti localai/localai:latest
```

**Sources**: [LocalAI Website](https://localai.io/), [LocalAI GitHub](https://github.com/mudler/LocalAI)

---

### Sentient GRID
**Status**: Evaluate for v1.1
**Key Features**:
- Decentralized AGI network with 110+ partners
- 40+ AI agents, 50+ data sources, 10+ models
- Token-based rewards for developers
- Real-time agent collaboration across Web2/Web3
- Backed by Founders Fund, Pantera Capital ($85M raised)

**Integration Opportunity**:
- Register CX Terminal as a GRID agent
- Enable token rewards for CX Linux users
- Cross-chain interoperability (Base, Polygon, Arbitrum)

**Sources**: [CoinDesk Article](https://www.coindesk.com/business/2025/08/13/openai-rival-sentient-unveils-open-source-agi-network-the-grid), [SiliconANGLE](https://siliconangle.com/2025/08/15/sentient-launches-grid-connect-monetize-open-ai-agents/)

---

### Shell GPT
**Status**: Complementary tool
**Key Features**:
- CLI tool for OpenAI/Ollama interaction
- Shell integration with hotkeys (Ctrl+L)
- REPL mode for interactive chat
- Offline mode with Ollama

**Integration Opportunity**:
- Bundle as optional CX Terminal plugin
- Share configuration with cx-daemon
- Provide `sgpt` alias in CX shell

**Sources**: [Shell GPT GitHub](https://github.com/TheR1D/shell_gpt), [PyPI](https://pypi.org/project/shell-gpt/)

---

### OpenMind AGI (OM1)
**Status**: Watch for robotics use cases
**Key Features**:
- Open-source robot OS (hardware-agnostic)
- Plug-and-play: OpenAI, Gemini, DeepSeek, xAI
- Voice + Vision capabilities
- FABRIC decentralized coordination layer

**Integration Opportunity**:
- CX Linux as preferred OS for OM1 deployments
- Shared AI backend configuration
- Edge computing for robotics workloads

**Sources**: [Robot Report](https://www.therobotreport.com/openmind-launches-om1-open-source-robot-agnostic-operating-system/)

---

## Implementation Roadmap

### Phase 1: Multi-Backend Support (v1.0)
```
Week 1-2:
- [ ] Abstract LLM backend in cx-daemon
- [ ] Add Jan.ai backend (OpenAI-compatible)
- [ ] Add LocalAI backend
- [ ] Configuration: ~/.cx/backends.yaml

Week 3-4:
- [ ] Auto-detection of available backends
- [ ] Fallback chain: Ollama -> Jan -> LocalAI -> Claude
- [ ] Backend health monitoring
```

### Phase 2: Cloud Providers (v1.1)
```
- [ ] OpenAI GPT-4/5 integration
- [ ] Google Gemini via Vertex AI
- [ ] Amazon Bedrock multi-model
- [ ] Azure OpenAI Service
```

### Phase 3: Ecosystem (v1.2)
```
- [ ] Sentient GRID agent registration
- [ ] LF AI & Data Foundation membership
- [ ] Shell GPT bundling
- [ ] MCP server for CX Terminal
```

---

## Configuration Schema

```yaml
# ~/.cx/ai-config.yaml
backends:
  primary: ollama
  fallback:
    - jan
    - localai
    - claude

  ollama:
    endpoint: http://localhost:11434
    model: llama3.2

  jan:
    endpoint: http://127.0.0.1:1337
    model: mistral-7b

  localai:
    endpoint: http://localhost:8080
    model: gpt-3.5-turbo

  claude:
    api_key_env: CX_ANTHROPIC_KEY
    model: claude-sonnet-4-20250514

  openai:
    api_key_env: OPENAI_API_KEY
    model: gpt-4o
```

---

## Partner Outreach Status

| Partner | Contact Status | Next Step |
|---------|---------------|-----------|
| Jan.ai | Not contacted | Email founders@jan.ai |
| LocalAI | Not contacted | GitHub issue/discussion |
| Sentient | Not contacted | Apply for GRID partnership |
| LF AI & Data | Not contacted | Membership inquiry |
| OpenAI | Not contacted | Enterprise API access |
| Google | Not contacted | Cloud partner program |
| Amazon | Not contacted | AWS partner network |
| Microsoft | Not contacted | Azure AI partnership |

---

## Success Metrics

1. **Integration Coverage**: Support 5+ LLM backends by v1.0
2. **User Adoption**: 10% of users configure alternative backend
3. **Latency**: <100ms backend switching
4. **Reliability**: 99.9% uptime with fallback chain
5. **Partnerships**: 3+ official partner announcements by launch
