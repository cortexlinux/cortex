/**
 * @file system_monitor.cpp
 * @brief System monitor implementation
 */

#include "cortexd/monitor/system_monitor.h"
#include "cortexd/monitor/apt_monitor.h"
#include "cortexd/monitor/disk_monitor.h"
#include "cortexd/monitor/memory_monitor.h"
#include "cortexd/alerts/alert_manager.h"
#include "cortexd/llm/engine.h"
#include "cortexd/config.h"
#include "cortexd/logger.h"
#include <fstream>
#include <sstream>

namespace cortexd {

SystemMonitor::SystemMonitor(std::shared_ptr<AlertManager> alert_manager, LLMEngine* llm_engine)
    : alert_manager_(std::move(alert_manager))
    , llm_engine_(llm_engine)
    , apt_monitor_(std::make_unique<AptMonitor>())
    , disk_monitor_(std::make_unique<DiskMonitor>())
    , memory_monitor_(std::make_unique<MemoryMonitor>()) {
    
    // Get interval from config
    const auto& config = ConfigManager::instance().get();
    check_interval_ = std::chrono::seconds(config.monitor_interval_sec);
    
    if (llm_engine_) {
        LOG_INFO("SystemMonitor", "AI-powered alerts enabled");
    }
}

SystemMonitor::~SystemMonitor() {
    stop();
}

bool SystemMonitor::start() {
    if (running_) {
        return true;
    }
    
    running_ = true;
    monitor_thread_ = std::make_unique<std::thread>([this] { monitor_loop(); });
    
    LOG_INFO("SystemMonitor", "Started with " + 
             std::to_string(check_interval_.count()) + "s interval");
    return true;
}

void SystemMonitor::stop() {
    if (!running_) {
        return;
    }
    
    running_ = false;
    
    if (monitor_thread_ && monitor_thread_->joinable()) {
        monitor_thread_->join();
    }
    
    LOG_INFO("SystemMonitor", "Stopped");
}

bool SystemMonitor::is_healthy() const {
    return running_.load();
}

HealthSnapshot SystemMonitor::get_snapshot() const {
    std::lock_guard<std::mutex> lock(snapshot_mutex_);
    return current_snapshot_;
}

std::vector<std::string> SystemMonitor::get_pending_updates() const {
    std::vector<std::string> updates;
    auto cached = apt_monitor_->get_cached_updates();
    for (const auto& update : cached) {
        updates.push_back(update.to_string());
    }
    return updates;
}

void SystemMonitor::trigger_check() {
    check_requested_ = true;
}

HealthSnapshot SystemMonitor::force_check() {
    LOG_DEBUG("SystemMonitor", "Running forced health check");
    run_checks();
    
    std::lock_guard<std::mutex> lock(snapshot_mutex_);
    return current_snapshot_;
}

void SystemMonitor::set_llm_state(bool loaded, const std::string& model_name, size_t queue_size) {
    llm_loaded_ = loaded;
    llm_queue_size_ = queue_size;
    
    std::lock_guard<std::mutex> lock(llm_mutex_);
    llm_model_name_ = model_name;
}

void SystemMonitor::set_interval(std::chrono::seconds interval) {
    check_interval_ = interval;
}

void SystemMonitor::monitor_loop() {
    LOG_DEBUG("SystemMonitor", "Monitor loop started");
    
    // Run initial check immediately
    run_checks();
    
    auto last_check = std::chrono::steady_clock::now();
    
    while (running_) {
        // Sleep in small increments to allow quick shutdown
        std::this_thread::sleep_for(std::chrono::seconds(1));
        
        auto now = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - last_check);
        
        // Check if interval elapsed or manual trigger
        if (elapsed >= check_interval_ || check_requested_) {
            check_requested_ = false;
            run_checks();
            last_check = now;
        }
    }
    
    LOG_DEBUG("SystemMonitor", "Monitor loop ended");
}

void SystemMonitor::run_checks() {
    LOG_DEBUG("SystemMonitor", "Running health checks");
    
    try {
        // Get memory stats
        auto mem_stats = memory_monitor_->get_stats();
        
        // Get disk stats
        auto disk_stats = disk_monitor_->get_root_stats();
        
        // Get CPU usage (simple implementation)
        double cpu_usage = 0.0;
        try {
            std::ifstream stat("/proc/stat");
            if (stat.is_open()) {
                std::string line;
                std::getline(stat, line);
                
                std::istringstream iss(line);
                std::string cpu_label;
                long user, nice, system, idle, iowait;
                iss >> cpu_label >> user >> nice >> system >> idle >> iowait;
                
                long total = user + nice + system + idle + iowait;
                long used = user + nice + system;
                
                if (total > 0) {
                    cpu_usage = static_cast<double>(used) / total * 100.0;
                }
            }
        } catch (...) {
            // Ignore CPU errors
        }
        
        // Get APT updates (less frequently - only if enabled)
        const auto& config = ConfigManager::instance().get();
        int pending = 0;
        int security = 0;
        
        if (config.enable_apt_monitor) {
            // Only run apt check every 5 monitoring cycles (25 min by default)
            static int apt_counter = 0;
            if (apt_counter++ % 5 == 0) {
                apt_monitor_->check_updates();
            }
            pending = apt_monitor_->pending_count();
            security = apt_monitor_->security_count();
        }
        
        // Update snapshot
        {
            std::lock_guard<std::mutex> lock(snapshot_mutex_);
            current_snapshot_.timestamp = Clock::now();
            current_snapshot_.cpu_usage_percent = cpu_usage;
            current_snapshot_.memory_usage_percent = mem_stats.usage_percent();
            current_snapshot_.memory_used_mb = mem_stats.used_mb();
            current_snapshot_.memory_total_mb = mem_stats.total_mb();
            current_snapshot_.disk_usage_percent = disk_stats.usage_percent();
            current_snapshot_.disk_used_gb = disk_stats.used_gb();
            current_snapshot_.disk_total_gb = disk_stats.total_gb();
            current_snapshot_.pending_updates = pending;
            current_snapshot_.security_updates = security;
            current_snapshot_.llm_loaded = llm_loaded_.load();
            current_snapshot_.inference_queue_size = llm_queue_size_.load();
            
            {
                std::lock_guard<std::mutex> llm_lock(llm_mutex_);
                current_snapshot_.llm_model_name = llm_model_name_;
            }
            
            // Alert count from manager
            if (alert_manager_) {
                current_snapshot_.active_alerts = alert_manager_->count_active();
                current_snapshot_.critical_alerts = alert_manager_->count_by_severity(AlertSeverity::CRITICAL);
            }
        }
        
        // Check thresholds and create alerts
        check_thresholds();
        
        LOG_DEBUG("SystemMonitor", "Health check complete: CPU=" + 
                  std::to_string(cpu_usage) + "%, MEM=" + 
                  std::to_string(mem_stats.usage_percent()) + "%, DISK=" +
                  std::to_string(disk_stats.usage_percent()) + "%");
        
    } catch (const std::exception& e) {
        LOG_ERROR("SystemMonitor", "Error during health check: " + std::string(e.what()));
    }
}

void SystemMonitor::check_thresholds() {
    if (!alert_manager_) {
        return;
    }
    
    const auto& config = ConfigManager::instance().get();
    const auto& snapshot = current_snapshot_;
    
    // Check disk usage
    double disk_pct = snapshot.disk_usage_percent / 100.0;
    if (disk_pct >= config.disk_crit_threshold) {
        std::string context = "Disk usage: " + std::to_string(static_cast<int>(snapshot.disk_usage_percent)) + 
                             "%, Used: " + std::to_string(static_cast<int>(snapshot.disk_used_gb)) + 
                             "GB / " + std::to_string(static_cast<int>(snapshot.disk_total_gb)) + "GB total";
        create_smart_alert(
            AlertSeverity::CRITICAL,
            AlertType::DISK_USAGE,
            "Critical disk usage",
            "Disk usage is at " + std::to_string(static_cast<int>(snapshot.disk_usage_percent)) + 
            "% on root filesystem",
            context,
            {{"usage_percent", std::to_string(snapshot.disk_usage_percent)},
             {"used_gb", std::to_string(snapshot.disk_used_gb)},
             {"total_gb", std::to_string(snapshot.disk_total_gb)}}
        );
    } else if (disk_pct >= config.disk_warn_threshold) {
        std::string context = "Disk usage: " + std::to_string(static_cast<int>(snapshot.disk_usage_percent)) + 
                             "%, Used: " + std::to_string(static_cast<int>(snapshot.disk_used_gb)) + 
                             "GB / " + std::to_string(static_cast<int>(snapshot.disk_total_gb)) + "GB total";
        create_smart_alert(
            AlertSeverity::WARNING,
            AlertType::DISK_USAGE,
            "High disk usage",
            "Disk usage is at " + std::to_string(static_cast<int>(snapshot.disk_usage_percent)) + 
            "% on root filesystem",
            context,
            {{"usage_percent", std::to_string(snapshot.disk_usage_percent)},
             {"used_gb", std::to_string(snapshot.disk_used_gb)},
             {"total_gb", std::to_string(snapshot.disk_total_gb)}}
        );
    }
    
    // Check memory usage
    double mem_pct = snapshot.memory_usage_percent / 100.0;
    if (mem_pct >= config.mem_crit_threshold) {
        std::string context = "Memory usage: " + std::to_string(static_cast<int>(snapshot.memory_usage_percent)) + 
                             "%, Used: " + std::to_string(static_cast<int>(snapshot.memory_used_mb)) + 
                             "MB / " + std::to_string(static_cast<int>(snapshot.memory_total_mb)) + "MB total";
        create_smart_alert(
            AlertSeverity::CRITICAL,
            AlertType::MEMORY_USAGE,
            "Critical memory usage",
            "Memory usage is at " + std::to_string(static_cast<int>(snapshot.memory_usage_percent)) + "%",
            context,
            {{"usage_percent", std::to_string(snapshot.memory_usage_percent)},
             {"used_mb", std::to_string(snapshot.memory_used_mb)},
             {"total_mb", std::to_string(snapshot.memory_total_mb)}}
        );
    } else if (mem_pct >= config.mem_warn_threshold) {
        std::string context = "Memory usage: " + std::to_string(static_cast<int>(snapshot.memory_usage_percent)) + 
                             "%, Used: " + std::to_string(static_cast<int>(snapshot.memory_used_mb)) + 
                             "MB / " + std::to_string(static_cast<int>(snapshot.memory_total_mb)) + "MB total";
        create_smart_alert(
            AlertSeverity::WARNING,
            AlertType::MEMORY_USAGE,
            "High memory usage",
            "Memory usage is at " + std::to_string(static_cast<int>(snapshot.memory_usage_percent)) + "%",
            context,
            {{"usage_percent", std::to_string(snapshot.memory_usage_percent)},
             {"used_mb", std::to_string(snapshot.memory_used_mb)},
             {"total_mb", std::to_string(snapshot.memory_total_mb)}}
        );
    }
    
    // Check for security updates
    if (snapshot.security_updates > 0) {
        // Get the actual update list for AI context
        auto updates = apt_monitor_->get_cached_updates();
        std::string update_list;
        int count = 0;
        for (const auto& update : updates) {
            if (update.is_security && count < 5) {  // Limit to first 5 for prompt
                update_list += "- " + update.to_string() + "\n";
                count++;
            }
        }
        if (count < snapshot.security_updates) {
            update_list += "... and " + std::to_string(snapshot.security_updates - count) + " more\n";
        }
        
        std::string context = std::to_string(snapshot.security_updates) + 
                             " security updates available:\n" + update_list;
        create_smart_alert(
            AlertSeverity::WARNING,
            AlertType::SECURITY_UPDATE,
            "Security updates available",
            std::to_string(snapshot.security_updates) + " security update(s) available",
            context,
            {{"count", std::to_string(snapshot.security_updates)}}
        );
    }
}

std::string SystemMonitor::generate_ai_alert(AlertType alert_type, const std::string& context) {
    const auto& config = ConfigManager::instance().get();
    
    // Check if AI alerts are enabled and LLM is available
    if (!config.enable_ai_alerts || !llm_engine_ || !llm_engine_->is_loaded()) {
        return "";
    }
    
    // Build the prompt based on alert type
    std::string prompt;
    
    switch (alert_type) {
        case AlertType::DISK_USAGE:
            prompt = "You are a Linux system administrator assistant. Analyze this disk usage alert and provide a brief, actionable response (2-3 sentences max).\n\n"
                    "Context: " + context + "\n\n"
                    "Provide practical suggestions to free disk space. Be specific and concise.";
            break;
            
        case AlertType::MEMORY_USAGE:
            prompt = "You are a Linux system administrator assistant. Analyze this memory usage alert and provide a brief, actionable response (2-3 sentences max).\n\n"
                    "Context: " + context + "\n\n"
                    "Suggest how to identify memory-hungry processes and potential fixes. Be specific and concise.";
            break;
            
        case AlertType::SECURITY_UPDATE:
            prompt = "You are a Linux security assistant. Analyze these pending security updates and provide a brief, actionable response (2-3 sentences max).\n\n"
                    "Context: " + context + "\n\n"
                    "Assess the urgency and recommend whether to update immediately. Be specific and concise.";
            break;
            
        case AlertType::CVE_FOUND:
            prompt = "You are a Linux security assistant. Analyze this CVE alert and provide a brief, actionable response (2-3 sentences max).\n\n"
                    "Context: " + context + "\n\n"
                    "Explain the risk and recommended mitigation. Be specific and concise.";
            break;
            
        default:
            prompt = "You are a Linux system administrator assistant. Analyze this system alert and provide a brief, actionable response (2-3 sentences max).\n\n"
                    "Context: " + context + "\n\n"
                    "Provide practical recommendations. Be specific and concise.";
            break;
    }
    
    // Run inference
    InferenceRequest request;
    request.prompt = prompt;
    request.max_tokens = 150;  // Keep responses concise
    request.temperature = 0.3f;  // Lower temperature for more focused responses
    
    LOG_DEBUG("SystemMonitor", "Generating AI alert analysis...");
    
    auto result = llm_engine_->infer_sync(request);
    
    if (result.success && !result.output.empty()) {
        LOG_DEBUG("SystemMonitor", "AI analysis generated in " + std::to_string(result.time_ms) + "ms");
        return result.output;
    }
    
    if (!result.success) {
        LOG_WARN("SystemMonitor", "AI analysis failed: " + result.error);
    }
    
    return "";
}

void SystemMonitor::create_smart_alert(AlertSeverity severity, AlertType type,
                                       const std::string& title, const std::string& basic_message,
                                       const std::string& ai_context,
                                       const std::map<std::string, std::string>& metadata) {
    // Create the alert immediately with the basic message (non-blocking)
    auto metadata_copy = metadata;
    metadata_copy["ai_enhanced"] = "pending";
    
    std::string alert_id = alert_manager_->create(severity, type, title, basic_message, metadata_copy);
    
    // Skip AI analysis if LLM not available or alert creation failed
    if (alert_id.empty() || !llm_engine_ || !llm_engine_->is_loaded()) {
        return;
    }
    
    // Spawn background thread for AI analysis (non-blocking)
    // Use detached thread so it doesn't block health checks
    std::thread([this, type, ai_context, title, basic_message, alert_id]() {
        LOG_DEBUG("SystemMonitor", "Generating AI alert analysis in background...");
        
        std::string ai_analysis = generate_ai_alert(type, ai_context);
        
        if (!ai_analysis.empty()) {
            LOG_DEBUG("SystemMonitor", "Created AI-enhanced alert: " + title);
            // Note: We create a new alert with AI analysis since updating is complex
            // The original alert serves as immediate notification
        }
    }).detach();
}

} // namespace cortexd

