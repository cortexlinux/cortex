/**
 * @file system_monitor.h
 * @brief System health monitoring service
 */

#pragma once

#include "cortexd/core/service.h"
#include "cortexd/alerts/alert_manager.h"
#include <memory>
#include <thread>
#include <atomic>
#include <chrono>
#include <mutex>
#include <shared_mutex>
#include <unordered_set>
#include <string>

namespace cortexd {

/**
 * @brief System health metrics
 */
struct SystemHealth {
    // CPU metrics
    double cpu_usage_percent;
    int cpu_cores;
    
    // Memory metrics
    double memory_usage_percent;
    uint64_t memory_total_bytes;
    uint64_t memory_used_bytes;
    uint64_t memory_available_bytes;
    
    // Disk metrics
    double disk_usage_percent;
    uint64_t disk_total_bytes;
    uint64_t disk_used_bytes;
    uint64_t disk_available_bytes;
    std::string disk_mount_point;  // Primary mount point monitored
    
    // System metrics
    uint64_t uptime_seconds;
    int failed_services_count;
    
    /**
     * @brief Convert to JSON
     */
    json to_json() const;
};

/**
 * @brief Monitoring thresholds
 */
struct MonitoringThresholds {
    double cpu_warning;
    double cpu_critical;
    double memory_warning;
    double memory_critical;
    double disk_warning;
    double disk_critical;
};

/**
 * @brief System monitoring service
 * 
 * Monitors system health (CPU, memory, disk, services) and creates alerts
 * when thresholds are exceeded.
 */
class SystemMonitor : public Service {
public:
    /**
     * @brief Construct system monitor
     * @param alert_manager Shared pointer to alert manager
     * @param check_interval_seconds Interval between health checks
     * @param thresholds Monitoring thresholds (required)
     */
    explicit SystemMonitor(
        std::shared_ptr<AlertManager> alert_manager,
        int check_interval_seconds,
        const MonitoringThresholds& thresholds
    );
    
    ~SystemMonitor() override;
    
    // Service interface
    bool start() override;
    void stop() override;
    const char* name() const override { return "SystemMonitor"; }
    int priority() const override { return 50; }  // Start after IPC server
    bool is_running() const override;
    bool is_healthy() const override;
    
    /**
     * @brief Get current system health
     */
    SystemHealth get_health() const;
    
    /**
     * @brief Get monitoring thresholds
     */
    MonitoringThresholds get_thresholds() const;
    
    /**
     * @brief Set monitoring thresholds
     */
    void set_thresholds(const MonitoringThresholds& thresholds);

private:
    std::shared_ptr<AlertManager> alert_manager_;
    std::atomic<bool> running_{false};
    std::unique_ptr<std::thread> monitor_thread_;
    int check_interval_seconds_;
    
    mutable std::shared_mutex thresholds_mutex_;
    MonitoringThresholds thresholds_;
    
    mutable std::mutex health_mutex_;
    SystemHealth current_health_;
    
    // CPU usage calculation state (thread-safe)
    mutable std::mutex cpu_state_mutex_;
    mutable double last_cpu_idle_ = 0.0;
    mutable double last_cpu_total_ = 0.0;
    mutable std::chrono::steady_clock::time_point last_cpu_time_;
    mutable bool cpu_first_call_ = true;
    
    // Persistent systemd bus connection (reused across calls)
    mutable void* systemd_bus_;  // sd_bus* (opaque to avoid including systemd headers)
    mutable std::mutex bus_mutex_;
    
    // /proc file cache (reduces I/O overhead)
    struct ProcFileCache {
        std::string content;
        std::chrono::steady_clock::time_point timestamp;
        static constexpr std::chrono::milliseconds ttl{1000};  // 1 second TTL
    };
    mutable std::mutex proc_cache_mutex_;
    mutable ProcFileCache proc_stat_cache_;
    mutable ProcFileCache proc_meminfo_cache_;
    mutable ProcFileCache proc_uptime_cache_;
    
    // Hash set for O(1) alert deduplication (tracks active alerts by key)
    mutable std::unordered_set<std::string> active_alert_keys_;
    mutable std::mutex alert_keys_mutex_;
    
    /**
     * @brief Get or create systemd bus connection
     * @return sd_bus* or nullptr on error
     */
    void* get_systemd_bus() const;
    
    /**
     * @brief Read /proc file with caching
     * @param path File path (e.g., "/proc/stat")
     * @param cache Cache entry to use
     * @return File content or empty string on error
     */
    std::string read_proc_file_cached(const std::string& path, ProcFileCache& cache) const;
    
    /**
     * @brief Monitoring thread function
     */
    void monitor_loop();
    
    /**
     * @brief Perform health check
     */
    SystemHealth check_health();
    
    /**
     * @brief Check CPU usage
     */
    double get_cpu_usage() const;
    
    /**
     * @brief Check memory usage
     */
    void get_memory_usage(uint64_t& total, uint64_t& used, uint64_t& available) const;
    
    /**
     * @brief Check disk usage
     */
    void get_disk_usage(uint64_t& total, uint64_t& used, uint64_t& available, std::string& mount_point) const;
    
    /**
     * @brief Get system uptime
     */
    uint64_t get_uptime() const;
    
    /**
     * @brief Check for failed systemd services
     */
    int get_failed_services_count() const;
    
    /**
     * @brief Check thresholds and create alerts if needed
     */
    void check_thresholds(const SystemHealth& health);
    
    /**
     * @brief Create basic alert (non-AI version for PR 2)
     */
    void create_basic_alert(
        AlertSeverity severity,
        AlertCategory category,
        const std::string& source,
        const std::string& message,
        const std::string& description
    );
};

} // namespace cortexd
