/**
 * @file engine.h
 * @brief LLM inference engine interface
 */

#pragma once

#include "cortexd/core/service.h"
#include "cortexd/common.h"
#include <string>
#include <memory>
#include <functional>
#include <future>
#include <optional>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <atomic>

namespace cortexd {

/**
 * @brief Model information
 */
struct ModelInfo {
    std::string path;
    std::string name;
    size_t size_bytes = 0;
    int context_length = 0;
    int vocab_size = 0;
    bool quantized = false;
    std::string quantization_type;
    
    json to_json() const {
        return {
            {"path", path},
            {"name", name},
            {"size_bytes", size_bytes},
            {"context_length", context_length},
            {"vocab_size", vocab_size},
            {"quantized", quantized},
            {"quantization_type", quantization_type}
        };
    }
};

/**
 * @brief Inference request
 */
struct InferenceRequest {
    std::string prompt;
    int max_tokens = 256;
    float temperature = 0.7f;
    float top_p = 0.9f;
    std::string stop_sequence;
    std::string request_id;
};

/**
 * @brief Inference result
 */
struct InferenceResult {
    std::string request_id;
    std::string output;
    int tokens_generated = 0;
    float time_ms = 0.0f;
    bool success = false;
    std::string error;
    
    json to_json() const {
        json j = {
            {"request_id", request_id},
            {"output", output},
            {"tokens_generated", tokens_generated},
            {"time_ms", time_ms},
            {"success", success}
        };
        if (!success) {
            j["error"] = error;
        }
        return j;
    }
};

/**
 * @brief Token callback for streaming inference
 */
using TokenCallback = std::function<void(const std::string& token)>;

// Forward declaration
class LlamaBackend;

/**
 * @brief LLM inference engine service
 */
class LLMEngine : public Service {
public:
    LLMEngine();
    ~LLMEngine() override;
    
    // Service interface
    bool start() override;
    void stop() override;
    const char* name() const override { return "LLMEngine"; }
    int priority() const override { return 10; }  // Start last
    bool is_running() const override { return running_.load(); }
    bool is_healthy() const override;
    
    /**
     * @brief Load a model
     * @param model_path Path to GGUF model file
     * @return true if loaded successfully
     */
    bool load_model(const std::string& model_path);
    
    /**
     * @brief Unload current model
     */
    void unload_model();
    
    /**
     * @brief Check if model is loaded
     */
    bool is_loaded() const;
    
    /**
     * @brief Get loaded model info
     */
    std::optional<ModelInfo> get_model_info() const;
    
    /**
     * @brief Queue async inference request
     * @return Future with result
     */
    std::future<InferenceResult> infer_async(const InferenceRequest& request);
    
    /**
     * @brief Synchronous inference
     */
    InferenceResult infer_sync(const InferenceRequest& request);
    
    /**
     * @brief Streaming inference with token callback
     */
    void infer_stream(const InferenceRequest& request, TokenCallback callback);
    
    /**
     * @brief Get current queue size
     */
    size_t queue_size() const;
    
    /**
     * @brief Clear inference queue
     */
    void clear_queue();
    
    /**
     * @brief Get memory usage in bytes
     */
    size_t memory_usage() const;
    
    /**
     * @brief Get LLM status as JSON
     */
    json status_json() const;
    
private:
    std::unique_ptr<LlamaBackend> backend_;
    std::atomic<bool> running_{false};
    
    // Inference queue
    struct QueuedRequest {
        InferenceRequest request;
        std::promise<InferenceResult> promise;
    };
    
    std::queue<std::shared_ptr<QueuedRequest>> request_queue_;
    mutable std::mutex queue_mutex_;
    std::condition_variable queue_cv_;
    std::unique_ptr<std::thread> worker_thread_;
    
    // Rate limiting
    std::atomic<int> requests_this_second_{0};
    std::chrono::steady_clock::time_point rate_limit_window_;
    std::mutex rate_mutex_;
    
    // Mutex to protect backend_ against TOCTOU races (is_loaded + generate)
    mutable std::mutex mutex_;
    
    void worker_loop();
    bool check_rate_limit();
};

} // namespace cortexd

