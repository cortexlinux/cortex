/**
 * @file llama_backend.cpp
 * @brief llama.cpp backend implementation
 */

#include "cortexd/llm/llama_backend.h"
#include "cortexd/logger.h"
#include <llama.h>
#include <fstream>
#include <chrono>
#include <cstring>
#include <algorithm>
#include <cmath>
#include <random>

namespace cortexd {

LlamaBackend::LlamaBackend() {
    // Initialize llama.cpp backend
    llama_backend_init();
    LOG_DEBUG("LlamaBackend", "llama.cpp backend initialized");
}

LlamaBackend::~LlamaBackend() {
    unload();
    llama_backend_free();
}

bool LlamaBackend::load(const std::string& path, int n_ctx, int n_threads) {
    try {
        std::lock_guard<std::mutex> lock(mutex_);
        
        LOG_INFO("LlamaBackend::load", "ENTRY - path=" + path);
        
        // Unload existing model (use internal version since we already hold the lock)
        if (model_) {
            LOG_INFO("LlamaBackend::load", "Unloading existing model");
            unload_internal();
        }
        
        LOG_INFO("LlamaBackend::load", "Setup model parameters");
        
        // Setup model parameters
        llama_model_params model_params = llama_model_default_params();
        model_params.use_mmap = true;
        
        // Load model
        LOG_INFO("LlamaBackend::load", "Calling llama_model_load_from_file");
        model_ = llama_model_load_from_file(path.c_str(), model_params);
        LOG_INFO("LlamaBackend::load", "llama_model_load_from_file returned, model_=" + std::string(model_ ? "non-null" : "null"));
        
        if (!model_) {
            LOG_ERROR("LlamaBackend::load", "Failed to load model from file");
            return false;
        }
        
        LOG_INFO("LlamaBackend::load", "Model loaded, getting vocabulary");
        
        // Get vocabulary from model (always valid when model loads successfully)
        vocab_ = llama_model_get_vocab(model_);
        
        LOG_INFO("LlamaBackend::load", "Got vocabulary, creating context");
        
        // Setup context parameters
        llama_context_params ctx_params = llama_context_default_params();
        ctx_params.n_ctx = n_ctx;
        ctx_params.n_threads = n_threads;
        ctx_params.n_threads_batch = n_threads;
        
        // Create context
        ctx_ = llama_init_from_model(model_, ctx_params);
        LOG_INFO("LlamaBackend::load", "llama_init_from_model returned, ctx_=" + std::string(ctx_ ? "non-null" : "null"));
        
        if (!ctx_) {
            LOG_ERROR("LlamaBackend::load", "Failed to create context from model");
            llama_model_free(model_);
            model_ = nullptr;
            vocab_ = nullptr;
            return false;
        }
        
        model_path_ = path;
        n_ctx_ = n_ctx;
        n_threads_ = n_threads;
        
        LOG_INFO("LlamaBackend::load", "EXIT - success");
        return true;
    } catch (const std::exception& e) {
        LOG_ERROR("LlamaBackend::load", "Exception caught: " + std::string(e.what()));
        return false;
    } catch (...) {
        LOG_ERROR("LlamaBackend::load", "Unknown exception caught");
        return false;
    }
}

void LlamaBackend::unload() {
    std::lock_guard<std::mutex> lock(mutex_);
    unload_internal();
}

void LlamaBackend::unload_internal() {
    // NOTE: Caller must hold mutex_
    if (ctx_) {
        llama_free(ctx_);
        ctx_ = nullptr;
    }
    
    if (model_) {
        llama_model_free(model_);
        model_ = nullptr;
    }
    
    vocab_ = nullptr;  // vocab is owned by model, don't free separately
    
    model_path_.clear();
    LOG_DEBUG("LlamaBackend", "Model unloaded");
}

// Helper function to add a token to a batch
static void batch_add_token(llama_batch& batch, llama_token token, int pos, bool logits) {
    batch.token[batch.n_tokens] = token;
    batch.pos[batch.n_tokens] = pos;
    batch.n_seq_id[batch.n_tokens] = 1;
    batch.seq_id[batch.n_tokens][0] = 0;
    batch.logits[batch.n_tokens] = logits ? 1 : 0;
    batch.n_tokens++;
}

// Helper function to clear a batch
static void batch_clear(llama_batch& batch) {
    batch.n_tokens = 0;
}

InferenceResult LlamaBackend::generate(const InferenceRequest& request) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    InferenceResult result;
    result.request_id = request.request_id;
    
    if (!model_ || !ctx_ || !vocab_) {
        result.success = false;
        result.error = "Model not loaded";
        return result;
    }
    
    // Validate input
    if (request.prompt.empty()) {
        result.success = false;
        result.error = "Prompt cannot be empty";
        return result;
    }
    
    if (request.prompt.size() > MAX_PROMPT_SIZE) {
        result.success = false;
        result.error = "Prompt exceeds maximum size";
        return result;
    }
    
    try {
        auto start_time = std::chrono::high_resolution_clock::now();
        
        // Tokenize prompt
        std::vector<llama_token> tokens = tokenize(request.prompt, true);
        
        if (tokens.empty()) {
            result.success = false;
            result.error = "Tokenization failed";
            return result;
        }
        
        if (static_cast<int>(tokens.size()) >= n_ctx_) {
            result.success = false;
            result.error = "Prompt too long for context";
            return result;
        }
        
        // Clear KV cache / memory
        llama_memory_clear(llama_get_memory(ctx_), true);
        
        // Create batch for prompt tokens
        llama_batch batch = llama_batch_init(std::max(static_cast<int>(tokens.size()), 32), 0, 1);
        
        for (size_t i = 0; i < tokens.size(); i++) {
            batch_add_token(batch, tokens[i], i, i == tokens.size() - 1);
        }
        
        // Process prompt
        if (llama_decode(ctx_, batch) != 0) {
            llama_batch_free(batch);
            result.success = false;
            result.error = "Failed to process prompt";
            return result;
        }
        
        // Generate tokens
        std::string output;
        int n_cur = tokens.size();
        int max_tokens = std::min(request.max_tokens, n_ctx_ - n_cur);
        
        for (int i = 0; i < max_tokens; i++) {
            // Sample next token
            llama_token new_token = sample_token(request.temperature, request.top_p);
            
            // Check for end of generation
            if (is_eog(new_token)) {
                break;
            }
            
            // Convert token to string
            std::string piece = token_to_piece(new_token);
            output += piece;
            result.tokens_generated++;
            
            // Check for stop sequence
            if (!request.stop_sequence.empty() && 
                output.find(request.stop_sequence) != std::string::npos) {
                // Remove stop sequence from output
                size_t pos = output.find(request.stop_sequence);
                output = output.substr(0, pos);
                break;
            }
            
            // Prepare next batch
            batch_clear(batch);
            batch_add_token(batch, new_token, n_cur, true);
            n_cur++;
            
            // Process token
            if (llama_decode(ctx_, batch) != 0) {
                LOG_WARN("LlamaBackend", "Decode failed at token " + std::to_string(i));
                break;
            }
        }
        
        llama_batch_free(batch);
        
        auto end_time = std::chrono::high_resolution_clock::now();
        result.time_ms = std::chrono::duration<float, std::milli>(end_time - start_time).count();
        result.output = output;
        result.success = true;
        
        LOG_DEBUG("LlamaBackend", "Generated " + std::to_string(result.tokens_generated) +
                  " tokens in " + std::to_string(result.time_ms) + "ms");
        
    } catch (const std::exception& e) {
        result.success = false;
        result.error = std::string("Exception: ") + e.what();
        LOG_ERROR("LlamaBackend", "Generate error: " + std::string(e.what()));
    }
    
    return result;
}

void LlamaBackend::generate_stream(const InferenceRequest& request, TokenCallback callback) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    if (!model_ || !ctx_ || !vocab_) {
        callback("[ERROR: Model not loaded]");
        return;
    }
    
    try {
        // Tokenize prompt
        std::vector<llama_token> tokens = tokenize(request.prompt, true);
        
        if (tokens.empty() || static_cast<int>(tokens.size()) >= n_ctx_) {
            callback("[ERROR: Invalid prompt]");
            return;
        }
        
        // Clear memory
        llama_memory_clear(llama_get_memory(ctx_), true);
        
        // Create batch
        llama_batch batch = llama_batch_init(std::max(static_cast<int>(tokens.size()), 32), 0, 1);
        
        for (size_t i = 0; i < tokens.size(); i++) {
            batch_add_token(batch, tokens[i], i, i == tokens.size() - 1);
        }
        
        if (llama_decode(ctx_, batch) != 0) {
            llama_batch_free(batch);
            callback("[ERROR: Failed to process prompt]");
            return;
        }
        
        // Generate with streaming
        std::string full_output;
        int n_cur = tokens.size();
        int max_tokens = std::min(request.max_tokens, n_ctx_ - n_cur);
        
        for (int i = 0; i < max_tokens; i++) {
            llama_token new_token = sample_token(request.temperature, request.top_p);
            
            if (is_eog(new_token)) {
                break;
            }
            
            std::string piece = token_to_piece(new_token);
            full_output += piece;
            
            // Stream callback
            callback(piece);
            
            // Check stop sequence
            if (!request.stop_sequence.empty() && 
                full_output.find(request.stop_sequence) != std::string::npos) {
                break;
            }
            
            // Prepare next batch
            batch_clear(batch);
            batch_add_token(batch, new_token, n_cur++, true);
            
            if (llama_decode(ctx_, batch) != 0) {
                break;
            }
        }
        
        llama_batch_free(batch);
        
    } catch (const std::exception& e) {
        callback("[ERROR: " + std::string(e.what()) + "]");
    }
}

std::vector<llama_token> LlamaBackend::tokenize(const std::string& text, bool add_bos) {
    if (!vocab_) return {};
    
    std::vector<llama_token> tokens(text.size() + 16);
    int n = llama_tokenize(vocab_, text.c_str(), text.size(),
                          tokens.data(), tokens.size(), add_bos, false);
    
    if (n < 0) {
        tokens.resize(-n);
        n = llama_tokenize(vocab_, text.c_str(), text.size(),
                          tokens.data(), tokens.size(), add_bos, false);
    }
    
    if (n >= 0) {
        tokens.resize(n);
    } else {
        tokens.clear();
    }
    
    return tokens;
}

std::string LlamaBackend::detokenize(const std::vector<llama_token>& tokens) {
    std::string result;
    for (auto token : tokens) {
        result += token_to_piece(token);
    }
    return result;
}

ModelInfo LlamaBackend::get_info() const {
    ModelInfo info;
    
    if (!model_ || !vocab_) {
        return info;
    }
    
    info.path = model_path_;
    
    // Extract name from path
    size_t last_slash = model_path_.find_last_of("/\\");
    if (last_slash != std::string::npos) {
        info.name = model_path_.substr(last_slash + 1);
    } else {
        info.name = model_path_;
    }
    
    info.context_length = n_ctx_;
    info.vocab_size = llama_vocab_n_tokens(vocab_);
    
    // Check if quantized based on filename
    if (info.name.find("Q4") != std::string::npos) {
        info.quantized = true;
        info.quantization_type = "Q4";
    } else if (info.name.find("Q8") != std::string::npos) {
        info.quantized = true;
        info.quantization_type = "Q8";
    } else if (info.name.find("F16") != std::string::npos) {
        info.quantized = false;
        info.quantization_type = "F16";
    }
    
    return info;
}

int LlamaBackend::vocab_size() const {
    if (!vocab_) return 0;
    return llama_vocab_n_tokens(vocab_);
}

size_t LlamaBackend::memory_usage() const {
    if (!ctx_) return 0;
    
    // Estimate based on context size and model parameters
    // This is approximate - llama.cpp doesn't expose exact memory usage
    size_t ctx_memory = n_ctx_ * 768 * 4;  // Rough estimate for context buffers
    
    // Add model memory (very rough estimate based on vocab size)
    if (vocab_) {
        size_t vocab_count = llama_vocab_n_tokens(vocab_);
        ctx_memory += vocab_count * 4096;  // Embedding dimension estimate
    }
    
    return ctx_memory;
}

llama_token LlamaBackend::sample_token(float temperature, float top_p) {
    if (!ctx_ || !vocab_) return 0;
    
    // Get logits for last token
    float* logits = llama_get_logits(ctx_);
    int n_vocab = llama_vocab_n_tokens(vocab_);
    
    // Simple greedy sampling for temperature = 0
    if (temperature <= 0.0f) {
        llama_token best = 0;
        float best_logit = logits[0];
        for (int i = 1; i < n_vocab; i++) {
            if (logits[i] > best_logit) {
                best_logit = logits[i];
                best = i;
            }
        }
        return best;
    }
    
    // Temperature and top-p sampling
    // Create candidates
    std::vector<llama_token_data> candidates;
    candidates.reserve(n_vocab);
    
    for (int i = 0; i < n_vocab; i++) {
        candidates.push_back({i, logits[i], 0.0f});
    }
    
    llama_token_data_array candidates_array = {
        candidates.data(),
        candidates.size(),
        -1,  // selected - not used
        false  // sorted
    };
    
    // Apply temperature - scale logits
    for (size_t i = 0; i < candidates_array.size; i++) {
        candidates_array.data[i].logit /= temperature;
    }
    
    // Sort by logit descending
    std::sort(candidates_array.data, candidates_array.data + candidates_array.size,
              [](const llama_token_data& a, const llama_token_data& b) {
                  return a.logit > b.logit;
              });
    candidates_array.sorted = true;
    
    // Apply softmax
    float max_logit = candidates_array.data[0].logit;
    float sum_exp = 0.0f;
    for (size_t i = 0; i < candidates_array.size; i++) {
        candidates_array.data[i].p = std::exp(candidates_array.data[i].logit - max_logit);
        sum_exp += candidates_array.data[i].p;
    }
    for (size_t i = 0; i < candidates_array.size; i++) {
        candidates_array.data[i].p /= sum_exp;
    }
    
    // Apply top-p nucleus sampling
    float cumulative_prob = 0.0f;
    size_t last_idx = 0;
    for (size_t i = 0; i < candidates_array.size; i++) {
        cumulative_prob += candidates_array.data[i].p;
        last_idx = i;
        if (cumulative_prob >= top_p) {
            break;
        }
    }
    candidates_array.size = last_idx + 1;
    
    // Renormalize
    sum_exp = 0.0f;
    for (size_t i = 0; i < candidates_array.size; i++) {
        sum_exp += candidates_array.data[i].p;
    }
    for (size_t i = 0; i < candidates_array.size; i++) {
        candidates_array.data[i].p /= sum_exp;
    }
    
    // Sample from distribution
    static std::random_device rd;
    static std::mt19937 gen(rd());
    std::uniform_real_distribution<float> dist(0.0f, 1.0f);
    
    float r = dist(gen);
    float cumsum = 0.0f;
    for (size_t i = 0; i < candidates_array.size; i++) {
        cumsum += candidates_array.data[i].p;
        if (r < cumsum) {
            return candidates_array.data[i].id;
        }
    }
    
    // Fallback to last token if we somehow didn't sample
    return candidates_array.data[candidates_array.size - 1].id;
}

bool LlamaBackend::is_eog(llama_token token) const {
    if (!vocab_) return true;
    return llama_vocab_is_eog(vocab_, token);
}

std::string LlamaBackend::token_to_piece(llama_token token) const {
    if (!vocab_) return "";
    
    char buf[256];
    int n = llama_token_to_piece(vocab_, token, buf, sizeof(buf), 0, false);
    
    if (n < 0) {
        return "";
    }
    
    return std::string(buf, n);
}

} // namespace cortexd
