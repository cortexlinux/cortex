/**
 * @file system_monitor.cpp
 * @brief System monitor implementation
 */

#include "cortexd/monitor/system_monitor.h"
#include "cortexd/monitor/apt_monitor.h"
#include "cortexd/monitor/disk_monitor.h"
#include "cortexd/monitor/memory_monitor.h"
#include "cortexd/alerts/alert_manager.h"
#include "cortexd/config.h"
#include "cortexd/logger.h"
#include <fstream>
#include <sstream>

namespace cortexd {

SystemMonitor::SystemMonitor(std::shared_ptr<AlertManager> alert_manager)
    : alert_manager_(std::move(alert_manager))
    , apt_monitor_(std::make_unique<AptMonitor>())
    , disk_monitor_(std::make_unique<DiskMonitor>())
    , memory_monitor_(std::make_unique<MemoryMonitor>()) {
    
    // Get interval from config
    const auto& config = ConfigManager::instance().get();
    check_interval_ = std::chrono::seconds(config.monitor_interval_sec);
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
        alert_manager_->create(
            AlertSeverity::CRITICAL,
            AlertType::DISK_USAGE,
            "Critical disk usage",
            "Disk usage is at " + std::to_string(static_cast<int>(snapshot.disk_usage_percent)) + 
            "% on root filesystem",
            {{"usage_percent", std::to_string(snapshot.disk_usage_percent)}}
        );
    } else if (disk_pct >= config.disk_warn_threshold) {
        alert_manager_->create(
            AlertSeverity::WARNING,
            AlertType::DISK_USAGE,
            "High disk usage",
            "Disk usage is at " + std::to_string(static_cast<int>(snapshot.disk_usage_percent)) + 
            "% on root filesystem",
            {{"usage_percent", std::to_string(snapshot.disk_usage_percent)}}
        );
    }
    
    // Check memory usage
    double mem_pct = snapshot.memory_usage_percent / 100.0;
    if (mem_pct >= config.mem_crit_threshold) {
        alert_manager_->create(
            AlertSeverity::CRITICAL,
            AlertType::MEMORY_USAGE,
            "Critical memory usage",
            "Memory usage is at " + std::to_string(static_cast<int>(snapshot.memory_usage_percent)) + "%",
            {{"usage_percent", std::to_string(snapshot.memory_usage_percent)}}
        );
    } else if (mem_pct >= config.mem_warn_threshold) {
        alert_manager_->create(
            AlertSeverity::WARNING,
            AlertType::MEMORY_USAGE,
            "High memory usage",
            "Memory usage is at " + std::to_string(static_cast<int>(snapshot.memory_usage_percent)) + "%",
            {{"usage_percent", std::to_string(snapshot.memory_usage_percent)}}
        );
    }
    
    // Check for security updates
    if (snapshot.security_updates > 0) {
        alert_manager_->create(
            AlertSeverity::WARNING,
            AlertType::SECURITY_UPDATE,
            "Security updates available",
            std::to_string(snapshot.security_updates) + " security update(s) available",
            {{"count", std::to_string(snapshot.security_updates)}}
        );
    }
}

} // namespace cortexd

