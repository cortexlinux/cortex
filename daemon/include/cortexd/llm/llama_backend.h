/**
 * @file llama_backend.h
 * @brief llama.cpp backend implementation
 */

#pragma once

#include "cortexd/llm/engine.h"
#include <mutex>
#include <vector>

// Forward declarations for llama.cpp types
struct llama_model;
struct llama_context;
struct llama_vocab;
typedef int32_t llama_token;

namespace cortexd {

/**
 * @brief llama.cpp backend for LLM inference
 */
class LlamaBackend {
public:
    LlamaBackend();
    ~LlamaBackend();
    
    /**
     * @brief Load model from GGUF file
     * @param path Path to model file
     * @param n_ctx Context length
     * @param n_threads Number of threads
     * @return true if successful
     */
    bool load(const std::string& path, int n_ctx = 2048, int n_threads = 4);
    
    /**
     * @brief Unload model
     */
    void unload();
    
    /**
     * @brief Check if model is loaded
     */
    bool is_loaded() const { return model_ != nullptr && ctx_ != nullptr; }
    
    /**
     * @brief Run inference
     */
    InferenceResult generate(const InferenceRequest& request);
    
    /**
     * @brief Run streaming inference
     */
    void generate_stream(const InferenceRequest& request, TokenCallback callback);
    
    /**
     * @brief Tokenize text
     */
    std::vector<llama_token> tokenize(const std::string& text, bool add_bos = true);
    
    /**
     * @brief Convert tokens to string
     */
    std::string detokenize(const std::vector<llama_token>& tokens);
    
    /**
     * @brief Get model info
     */
    ModelInfo get_info() const;
    
    /**
     * @brief Get context length
     */
    int context_length() const { return n_ctx_; }
    
    /**
     * @brief Get vocabulary size
     */
    int vocab_size() const;
    
    /**
     * @brief Estimate memory usage
     */
    size_t memory_usage() const;
    
private:
    llama_model* model_ = nullptr;
    llama_context* ctx_ = nullptr;
    const llama_vocab* vocab_ = nullptr;  // Vocabulary (owned by model)
    mutable std::mutex mutex_;
    
    std::string model_path_;
    int n_ctx_ = 2048;
    int n_threads_ = 4;
    
    /**
     * @brief Sample next token
     */
    llama_token sample_token(float temperature, float top_p);
    
    /**
     * @brief Check if token is end of generation
     */
    bool is_eog(llama_token token) const;
    
    /**
     * @brief Convert single token to string
     */
    std::string token_to_piece(llama_token token) const;
    
    /**
     * @brief Internal unload (assumes mutex is already held)
     */
    void unload_internal();
};

} // namespace cortexd

