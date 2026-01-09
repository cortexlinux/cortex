/**
 * @file system_monitor.h
 * @brief Main system monitoring orchestrator
 */

#pragma once

#include "cortexd/core/service.h"
#include "cortexd/common.h"
#include <memory>
#include <thread>
#include <atomic>
#include <mutex>
#include <vector>
#include <chrono>
#include <map>
#include <string>

namespace cortexd {

// Forward declarations
class AptMonitor;
class DiskMonitor;
class MemoryMonitor;
class CVEScanner;
class DependencyChecker;
class AlertManager;
class LLMEngine;

/**
 * @brief System monitoring service
 * 
 * Orchestrates all monitoring subsystems and periodically checks
 * system health, creating alerts when thresholds are exceeded.
 */
class SystemMonitor : public Service {
public:
    /**
     * @brief Construct with optional alert manager and LLM engine
     * @param alert_manager Shared alert manager (can be nullptr)
     * @param llm_engine LLM engine for AI-powered alerts (can be nullptr)
     */
    explicit SystemMonitor(std::shared_ptr<AlertManager> alert_manager = nullptr,
                          LLMEngine* llm_engine = nullptr);
    ~SystemMonitor() override;
    
    // Service interface
    bool start() override;
    void stop() override;
    const char* name() const override { return "SystemMonitor"; }
    int priority() const override { return 50; }
    bool is_running() const override { return running_.load(); }
    bool is_healthy() const override;
    
    /**
     * @brief Get current health snapshot
     */
    HealthSnapshot get_snapshot() const;
    
    /**
     * @brief Get list of pending package updates
     */
    std::vector<std::string> get_pending_updates() const;
    
    /**
     * @brief Trigger immediate health check (async)
     */
    void trigger_check();
    
    /**
     * @brief Force synchronous health check and return snapshot
     * @return Fresh health snapshot
     */
    HealthSnapshot force_check();
    
    /**
     * @brief Update LLM state in snapshot
     */
    void set_llm_state(bool loaded, const std::string& model_name, size_t queue_size);
    
    /**
     * @brief Set check interval
     */
    void set_interval(std::chrono::seconds interval);
    
private:
    std::shared_ptr<AlertManager> alert_manager_;
    LLMEngine* llm_engine_ = nullptr;  // Non-owning pointer to LLM engine
    
    std::unique_ptr<AptMonitor> apt_monitor_;
    std::unique_ptr<DiskMonitor> disk_monitor_;
    std::unique_ptr<MemoryMonitor> memory_monitor_;
    
    std::unique_ptr<std::thread> monitor_thread_;
    std::atomic<bool> running_{false};
    std::atomic<bool> check_requested_{false};
    
    mutable std::mutex snapshot_mutex_;
    HealthSnapshot current_snapshot_;
    
    // LLM state (updated externally)
    std::atomic<bool> llm_loaded_{false};
    std::string llm_model_name_;
    std::atomic<size_t> llm_queue_size_{0};
    std::mutex llm_mutex_;
    
    std::chrono::seconds check_interval_{300};  // 5 minutes
    
    // Thread-safe APT check counter (replaces static local)
    std::atomic<int> apt_counter_{0};
    
    /**
     * @brief Main monitoring loop
     */
    void monitor_loop();
    
    /**
     * @brief Run all health checks
     */
    void run_checks();
    
    /**
     * @brief Check thresholds and create alerts
     * @param snapshot Copy of current health snapshot to check
     */
    void check_thresholds(const HealthSnapshot& snapshot);
    
    /**
     * @brief Generate AI-powered alert message using LLM
     * @param alert_type Type of alert
     * @param context Context information for the LLM
     * @return AI-generated message or empty string if unavailable
     */
    std::string generate_ai_alert(AlertType alert_type, const std::string& context);
    
    /**
     * @brief Create alert with optional AI enhancement
     */
    void create_smart_alert(AlertSeverity severity, AlertType type,
                           const std::string& title, const std::string& basic_message,
                           const std::string& ai_context,
                           const std::map<std::string, std::string>& metadata);
};

} // namespace cortexd

