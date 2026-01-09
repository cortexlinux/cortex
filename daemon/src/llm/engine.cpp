/**
 * @file engine.cpp
 * @brief LLM engine implementation
 */

#include "cortexd/llm/engine.h"
#include "cortexd/llm/llama_backend.h"
#include "cortexd/config.h"
#include "cortexd/logger.h"
#include <uuid/uuid.h>

namespace cortexd {

LLMEngine::LLMEngine()
    : backend_(std::make_unique<LlamaBackend>())
    , rate_limit_window_(std::chrono::steady_clock::now()) {
}

LLMEngine::~LLMEngine() {
    stop();
}

bool LLMEngine::start() {
    if (running_) {
        return true;
    }
    
    running_ = true;
    
    // Start worker thread
    worker_thread_ = std::make_unique<std::thread>([this] { worker_loop(); });
    
    // Check if we should load model on startup
    const auto& config = ConfigManager::instance().get();
    if (!config.llm_lazy_load && !config.model_path.empty()) {
        load_model(config.model_path);
    }
    
    LOG_INFO("LLMEngine", "Started");
    return true;
}

void LLMEngine::stop() {
    if (!running_) {
        return;
    }
    
    running_ = false;
    queue_cv_.notify_all();
    
    if (worker_thread_ && worker_thread_->joinable()) {
        worker_thread_->join();
    }
    
    unload_model();
    
    LOG_INFO("LLMEngine", "Stopped");
}

bool LLMEngine::is_healthy() const {
    return running_.load();
}

bool LLMEngine::load_model(const std::string& model_path) {
    std::string path = expand_path(model_path);
    
    LOG_INFO("LLMEngine", "Loading model: " + path);
    
    const auto& config = ConfigManager::instance().get();
    
    std::lock_guard<std::mutex> lock(mutex_);
    if (backend_->load(path, config.llm_context_length, config.llm_threads)) {
        LOG_INFO("LLMEngine", "Model loaded successfully");
        return true;
    }
    
    LOG_ERROR("LLMEngine", "Failed to load model: " + path);
    return false;
}

void LLMEngine::unload_model() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (backend_->is_loaded()) {
        backend_->unload();
        LOG_INFO("LLMEngine", "Model unloaded");
    }
}

bool LLMEngine::is_loaded() const {
    // No mutex needed - backend_->is_loaded() just checks pointer state
    // Acquiring mutex here would block during long inference operations
    return backend_->is_loaded();
}

std::optional<ModelInfo> LLMEngine::get_model_info() const {
    // No mutex needed for read-only state query
    // This avoids blocking during long inference operations
    if (!backend_->is_loaded()) {
        return std::nullopt;
    }
    return backend_->get_info();
}

std::future<InferenceResult> LLMEngine::infer_async(const InferenceRequest& request) {
    auto queued = std::make_shared<QueuedRequest>();
    queued->request = request;
    
    // Generate request ID if not set
    if (queued->request.request_id.empty()) {
        uuid_t uuid;
        char uuid_str[37];
        uuid_generate(uuid);
        uuid_unparse_lower(uuid, uuid_str);
        queued->request.request_id = uuid_str;
    }
    
    auto future = queued->promise.get_future();
    
    // Check rate limit
    if (!check_rate_limit()) {
        InferenceResult result;
        result.request_id = queued->request.request_id;
        result.success = false;
        result.error = "Rate limit exceeded";
        queued->promise.set_value(result);
        return future;
    }
    
    // Check queue size
    const auto& config = ConfigManager::instance().get();
    {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        if (request_queue_.size() >= static_cast<size_t>(config.max_inference_queue)) {
            InferenceResult result;
            result.request_id = queued->request.request_id;
            result.success = false;
            result.error = "Inference queue full";
            queued->promise.set_value(result);
            return future;
        }
        
        request_queue_.push(queued);
    }
    
    queue_cv_.notify_one();
    
    LOG_DEBUG("LLMEngine", "Queued inference request: " + queued->request.request_id);
    return future;
}

InferenceResult LLMEngine::infer_sync(const InferenceRequest& request) {
    // Direct synchronous inference - acquire mutex to prevent TOCTOU race
    std::lock_guard<std::mutex> lock(mutex_);
    
    if (!backend_->is_loaded()) {
        InferenceResult result;
        result.request_id = request.request_id;
        result.success = false;
        result.error = "Model not loaded";
        return result;
    }
    
    return backend_->generate(request);
}

void LLMEngine::infer_stream(const InferenceRequest& request, TokenCallback callback) {
    // Acquire mutex to prevent TOCTOU race
    std::lock_guard<std::mutex> lock(mutex_);
    
    if (!backend_->is_loaded()) {
        callback("[ERROR: Model not loaded]");
        return;
    }
    
    backend_->generate_stream(request, callback);
}

size_t LLMEngine::queue_size() const {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    return request_queue_.size();
}

void LLMEngine::clear_queue() {
    std::lock_guard<std::mutex> lock(queue_mutex_);
    
    while (!request_queue_.empty()) {
        auto queued = request_queue_.front();
        request_queue_.pop();
        
        InferenceResult result;
        result.request_id = queued->request.request_id;
        result.success = false;
        result.error = "Queue cleared";
        queued->promise.set_value(result);
    }
    
    LOG_INFO("LLMEngine", "Inference queue cleared");
}

size_t LLMEngine::memory_usage() const {
    // No mutex needed for read-only state query
    return backend_->memory_usage();
}

json LLMEngine::status_json() const {
    // No mutex needed for read-only state query
    // This avoids blocking during long inference operations
    json status = {
        {"loaded", backend_->is_loaded()},
        {"queue_size", queue_size()},
        {"memory_bytes", backend_->memory_usage()}
    };
    
    if (backend_->is_loaded()) {
        auto info = backend_->get_info();
        status["model"] = info.to_json();
    }
    
    return status;
}

void LLMEngine::worker_loop() {
    LOG_DEBUG("LLMEngine", "Worker loop started");
    
    while (running_) {
        std::shared_ptr<QueuedRequest> queued;
        
        {
            std::unique_lock<std::mutex> lock(queue_mutex_);
            queue_cv_.wait(lock, [this] {
                return !request_queue_.empty() || !running_;
            });
            
            if (!running_) break;
            if (request_queue_.empty()) continue;
            
            queued = request_queue_.front();
            request_queue_.pop();
        }
        
        // Process request
        LOG_DEBUG("LLMEngine", "Processing request: " + queued->request.request_id);
        
        InferenceResult result;
        
        // Acquire mutex to protect against TOCTOU race with unload()
        // The is_loaded() check and generate() call must be atomic
        {
            std::lock_guard<std::mutex> lock(mutex_);
            
            if (!backend_->is_loaded()) {
                result.request_id = queued->request.request_id;
                result.success = false;
                result.error = "Model not loaded";
            } else {
                auto start = std::chrono::high_resolution_clock::now();
                result = backend_->generate(queued->request);
                auto end = std::chrono::high_resolution_clock::now();
                
                result.time_ms = std::chrono::duration<float, std::milli>(end - start).count();
            }
        }
        
        queued->promise.set_value(result);
        
        LOG_DEBUG("LLMEngine", "Request completed: " + queued->request.request_id +
                  " (" + std::to_string(result.time_ms) + "ms)");
    }
    
    LOG_DEBUG("LLMEngine", "Worker loop ended");
}

bool LLMEngine::check_rate_limit() {
    std::lock_guard<std::mutex> lock(rate_mutex_);
    
    auto now = std::chrono::steady_clock::now();
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - rate_limit_window_);
    
    // Reset window every second
    if (elapsed.count() >= 1000) {
        requests_this_second_ = 0;
        rate_limit_window_ = now;
    }
    
    const auto& config = ConfigManager::instance().get();
    if (requests_this_second_ >= config.max_requests_per_sec) {
        return false;
    }
    
    requests_this_second_++;
    return true;
}

} // namespace cortexd

