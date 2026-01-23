/**
 * @file system_monitor.cpp
 * @brief System monitoring implementation
 */

#include "cortexd/monitor/system_monitor.h"
#include "cortexd/logger.h"
#include <fstream>
#include <sstream>
#include <filesystem>
#include <systemd/sd-bus.h>
#include <unistd.h>
#include <sys/statvfs.h>
#include <algorithm>
#include <mutex>
#include <thread>
#include <chrono>
#include <climits>

namespace cortexd {

// SystemHealth JSON conversion
json SystemHealth::to_json() const {
    json j;
    j["cpu"] = {
        {"usage_percent", cpu_usage_percent},
        {"cores", cpu_cores}
    };
    j["memory"] = {
        {"usage_percent", memory_usage_percent},
        {"total_bytes", memory_total_bytes},
        {"used_bytes", memory_used_bytes},
        {"available_bytes", memory_available_bytes}
    };
    j["disk"] = {
        {"usage_percent", disk_usage_percent},
        {"total_bytes", disk_total_bytes},
        {"used_bytes", disk_used_bytes},
        {"available_bytes", disk_available_bytes},
        {"mount_point", disk_mount_point}
    };
    j["system"] = {
        {"uptime_seconds", uptime_seconds},
        {"failed_services_count", failed_services_count}
    };
    return j;
}

// SystemMonitor implementation
SystemMonitor::SystemMonitor(
    std::shared_ptr<AlertManager> alert_manager,
    int check_interval_seconds,
    const MonitoringThresholds& thresholds
) : alert_manager_(alert_manager),
    check_interval_seconds_(check_interval_seconds),
    thresholds_(thresholds),
    current_health_{},
    last_cpu_time_(std::chrono::steady_clock::now()),
    systemd_bus_(nullptr) {
    // Validate check_interval_seconds to prevent busy-spin
    if (check_interval_seconds_ <= 0) {
        LOG_WARN("SystemMonitor", "Invalid check_interval_seconds (" + std::to_string(check_interval_seconds_) + "), clamping to minimum of 1 second");
        check_interval_seconds_ = 1;
    }
}

SystemMonitor::~SystemMonitor() {
    stop();
    // Clean up systemd bus connection
    std::lock_guard<std::mutex> lock(bus_mutex_);
    if (systemd_bus_) {
        sd_bus_unref(static_cast<sd_bus*>(systemd_bus_));
        systemd_bus_ = nullptr;
    }
}

bool SystemMonitor::start() {
    if (running_.load()) {
        LOG_WARN("SystemMonitor", "Already running");
        return true;
    }
    
    if (!alert_manager_) {
        LOG_ERROR("SystemMonitor", "Alert manager not set");
        return false;
    }
    
    running_.store(true);
    monitor_thread_ = std::make_unique<std::thread>(&SystemMonitor::monitor_loop, this);
    
    LOG_INFO("SystemMonitor", "Started monitoring (interval: " + 
             std::to_string(check_interval_seconds_) + "s)");
    return true;
}

void SystemMonitor::stop() {
    if (!running_.load()) {
        return;
    }
    
    running_.store(false);
    
    if (monitor_thread_ && monitor_thread_->joinable()) {
        monitor_thread_->join();
    }
    
    monitor_thread_.reset();
    LOG_INFO("SystemMonitor", "Stopped");
}

bool SystemMonitor::is_running() const {
    return running_.load();
}

bool SystemMonitor::is_healthy() const {
    return running_.load();
}

SystemHealth SystemMonitor::get_health() const {
    std::lock_guard<std::mutex> lock(health_mutex_);
    return current_health_;
}

MonitoringThresholds SystemMonitor::get_thresholds() const {
    std::shared_lock<std::shared_mutex> lock(thresholds_mutex_);
    return thresholds_;
}

void SystemMonitor::set_thresholds(const MonitoringThresholds& thresholds) {
    std::unique_lock<std::shared_mutex> lock(thresholds_mutex_);
    thresholds_ = thresholds;
}

void SystemMonitor::monitor_loop() {
    while (running_.load()) {
        try {
            SystemHealth health = check_health();
            
            {
                std::lock_guard<std::mutex> lock(health_mutex_);
                current_health_ = health;
            }
            
            check_thresholds(health);
            
        } catch (const std::exception& e) {
            LOG_ERROR("SystemMonitor", "Error in monitoring loop: " + std::string(e.what()));
        }
        
        // Sleep with periodic checks for shutdown
        for (int i = 0; i < check_interval_seconds_ && running_.load(); ++i) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }
}

SystemHealth SystemMonitor::check_health() {
    SystemHealth health;
    
    // CPU
    health.cpu_usage_percent = get_cpu_usage();
    long cores = sysconf(_SC_NPROCESSORS_ONLN);
    // sysconf returns -1 on error, ensure at least 1 core
    // Add bounds check to prevent integer overflow
    health.cpu_cores = (cores > 0) ? static_cast<int>(std::min(cores, static_cast<long>(INT_MAX))) : 1;
    
    // Memory
    get_memory_usage(health.memory_total_bytes, 
                     health.memory_used_bytes, 
                     health.memory_available_bytes);
    if (health.memory_total_bytes > 0) {
        health.memory_usage_percent = 
            (static_cast<double>(health.memory_used_bytes) / health.memory_total_bytes) * 100.0;
    } else {
        health.memory_usage_percent = 0.0;
    }
    
    // Disk
    get_disk_usage(health.disk_total_bytes,
                   health.disk_used_bytes,
                   health.disk_available_bytes,
                   health.disk_mount_point);
    if (health.disk_total_bytes > 0) {
        health.disk_usage_percent = 
            (static_cast<double>(health.disk_used_bytes) / health.disk_total_bytes) * 100.0;
    } else {
        health.disk_usage_percent = 0.0;
    }
    
    // System
    health.uptime_seconds = get_uptime();
    health.failed_services_count = get_failed_services_count();
    
    return health;
}

std::string SystemMonitor::read_proc_file_cached(const std::string& path, ProcFileCache& cache) const {
    auto now = std::chrono::steady_clock::now();
    
    std::lock_guard<std::mutex> lock(proc_cache_mutex_);
    
    // Check if cache is valid
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - cache.timestamp);
    if (!cache.content.empty() && elapsed < ProcFileCache::ttl) {
        return cache.content;
    }
    
    // Read file
    std::ifstream file(path);
    if (!file.is_open()) {
        return "";
    }
    
    std::string content;
    std::string line;
    while (std::getline(file, line)) {
        content += line + "\n";
    }
    
    // Update cache
    cache.content = content;
    cache.timestamp = now;
    
    return content;
}

double SystemMonitor::get_cpu_usage() const {
    std::string stat_content = read_proc_file_cached("/proc/stat", proc_stat_cache_);
    if (stat_content.empty()) {
        return 0.0;
    }
    
    std::istringstream stat_file(stat_content);
    std::string line;
    if (!std::getline(stat_file, line)) {
        return 0.0;
    }
    
    std::istringstream iss(line);
    std::string cpu;
    long user, nice, system, idle, iowait, irq, softirq, steal;
    
    iss >> cpu >> user >> nice >> system >> idle >> iowait >> irq >> softirq >> steal;
    
    if (iss.fail()) {
        return 0.0;
    }
    
    long total_idle = idle + iowait;
    long total_non_idle = user + nice + system + irq + softirq + steal;
    long total = total_idle + total_non_idle;
    
    auto now = std::chrono::steady_clock::now();
    
    // Thread-safe access to CPU state
    std::lock_guard<std::mutex> lock(cpu_state_mutex_);
    
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - last_cpu_time_).count();
    
    if (cpu_first_call_ || elapsed < 100) {
        // First call or not enough time elapsed, initialize and return 0
        last_cpu_idle_ = static_cast<double>(total_idle);
        last_cpu_total_ = static_cast<double>(total);
        last_cpu_time_ = now;
        cpu_first_call_ = false;
        return 0.0;
    }
    
    double idle_diff = static_cast<double>(total_idle) - last_cpu_idle_;
    double total_diff = static_cast<double>(total) - last_cpu_total_;
    
    last_cpu_idle_ = static_cast<double>(total_idle);
    last_cpu_total_ = static_cast<double>(total);
    last_cpu_time_ = now;
    
    if (total_diff == 0.0) {
        return 0.0;
    }
    
    double cpu_percent = (1.0 - (idle_diff / total_diff)) * 100.0;
    return std::max(0.0, std::min(100.0, cpu_percent));
}

void SystemMonitor::get_memory_usage(uint64_t& total, uint64_t& used, uint64_t& available) const {
    std::string meminfo_content = read_proc_file_cached("/proc/meminfo", proc_meminfo_cache_);
    if (meminfo_content.empty()) {
        total = used = available = 0;
        return;
    }
    
    std::istringstream meminfo(meminfo_content);
    uint64_t mem_total = 0, mem_free = 0, mem_available = 0, buffers = 0, cached = 0;
    std::string line;
    
    while (std::getline(meminfo, line)) {
        std::istringstream iss(line);
        std::string key;
        uint64_t value;
        std::string unit;
        
        iss >> key >> value >> unit;
        
        if (key == "MemTotal:") {
            mem_total = value * 1024;  // Convert from KB to bytes
        } else if (key == "MemFree:") {
            mem_free = value * 1024;
        } else if (key == "MemAvailable:") {
            mem_available = value * 1024;
        } else if (key == "Buffers:") {
            buffers = value * 1024;
        } else if (key == "Cached:") {
            cached = value * 1024;
        }
    }
    
    total = mem_total;
    
    if (mem_available > 0) {
        // Use MemAvailable if available (more accurate)
        available = mem_available;
        used = total - available;
    } else {
        // Fallback calculation
        available = mem_free + buffers + cached;
        used = total - available;
    }
}

void SystemMonitor::get_disk_usage(uint64_t& total, uint64_t& used, uint64_t& available, std::string& mount_point) const {
    // Monitor root filesystem by default
    mount_point = "/";
    
    struct statvfs stat;
    if (statvfs("/", &stat) != 0) {
        total = used = available = 0;
        return;
    }
    
    total = static_cast<uint64_t>(stat.f_blocks) * stat.f_frsize;
    available = static_cast<uint64_t>(stat.f_bavail) * stat.f_frsize;
    used = total - (static_cast<uint64_t>(stat.f_bfree) * stat.f_frsize);
}

uint64_t SystemMonitor::get_uptime() const {
    std::string uptime_content = read_proc_file_cached("/proc/uptime", proc_uptime_cache_);
    if (uptime_content.empty()) {
        return 0;
    }
    
    std::istringstream uptime_file(uptime_content);
    double uptime_seconds;
    uptime_file >> uptime_seconds;
    
    return static_cast<uint64_t>(uptime_seconds);
}

void* SystemMonitor::get_systemd_bus() const {
    std::lock_guard<std::mutex> lock(bus_mutex_);
    
    // Reuse existing connection if available
    if (systemd_bus_) {
        return systemd_bus_;
    }
    
    // Create new connection
    sd_bus* bus = nullptr;
    int r = sd_bus_default_system(&bus);
    if (r < 0) {
        LOG_DEBUG("SystemMonitor", "Failed to connect to systemd bus");
        return nullptr;
    }
    
    systemd_bus_ = bus;
    return systemd_bus_;
}

int SystemMonitor::get_failed_services_count() const {
    sd_bus* bus = static_cast<sd_bus*>(get_systemd_bus());
    if (!bus) {
        return 0;
    }
    
    sd_bus_message* reply = nullptr;
    int r = sd_bus_call_method(
        bus,
        "org.freedesktop.systemd1",
        "/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager",
        "ListUnits",
        nullptr,
        &reply,
        ""
    );
    
    int failed_count = 0;
    
    if (r >= 0 && reply) {
        r = sd_bus_message_enter_container(reply, 'a', "(ssssssouso)");
        if (r > 0) {
            while (true) {
                const char* name = nullptr;
                const char* desc = nullptr;
                const char* load = nullptr;
                const char* active = nullptr;
                const char* sub = nullptr;
                const char* following = nullptr;
                const char* object_path = nullptr;
                uint32_t job_id = 0;
                const char* job_type = nullptr;
                const char* job_path = nullptr;
                
                r = sd_bus_message_read(reply, "(ssssssouso)", 
                    &name, &desc, &load, &active, &sub, &following, 
                    &object_path, &job_id, &job_type, &job_path);
                
                if (r <= 0) {
                    break;
                }
                
                if (active && std::string(active) == "failed") {
                    failed_count++;
                }
            }
        }
        sd_bus_message_unref(reply);
    } else if (r < 0) {
        // Connection error - reset bus connection for next call
        LOG_DEBUG("SystemMonitor", "systemd bus call failed, will reconnect next time");
        std::lock_guard<std::mutex> lock(bus_mutex_);
        if (systemd_bus_) {
            sd_bus_unref(static_cast<sd_bus*>(systemd_bus_));
            systemd_bus_ = nullptr;
        }
    }
    
    return failed_count;
}

void SystemMonitor::check_thresholds(const SystemHealth& health) {
    // Acquire shared lock for reading thresholds
    std::shared_lock<std::shared_mutex> lock(thresholds_mutex_);
    
    // CPU checks
    std::string cpu_critical_key = std::to_string(static_cast<int>(AlertCategory::CPU)) + ":" + 
                                    std::to_string(static_cast<int>(AlertSeverity::CRITICAL)) + ":" + 
                                    "system_monitor:CPU usage critical";
    std::string cpu_warning_key = std::to_string(static_cast<int>(AlertCategory::CPU)) + ":" + 
                                  std::to_string(static_cast<int>(AlertSeverity::WARNING)) + ":" + 
                                  "system_monitor:CPU usage high";
    
    if (health.cpu_usage_percent >= thresholds_.cpu_critical) {
        create_basic_alert(
            AlertSeverity::CRITICAL,
            AlertCategory::CPU,
            "system_monitor",
            "CPU usage critical",
            "CPU usage is at " + std::to_string(static_cast<int>(health.cpu_usage_percent)) + 
            "% (threshold: " + std::to_string(static_cast<int>(thresholds_.cpu_critical)) + "%)"
        );
    } else if (health.cpu_usage_percent >= thresholds_.cpu_warning) {
        create_basic_alert(
            AlertSeverity::WARNING,
            AlertCategory::CPU,
            "system_monitor",
            "CPU usage high",
            "CPU usage is at " + std::to_string(static_cast<int>(health.cpu_usage_percent)) + 
            "% (threshold: " + std::to_string(static_cast<int>(thresholds_.cpu_warning)) + "%)"
        );
        // Remove critical key if it exists (downgraded from critical to warning)
        {
            std::lock_guard<std::mutex> lock(alert_keys_mutex_);
            active_alert_keys_.erase(cpu_critical_key);
        }
    } else {
        // CPU usage recovered - remove both keys
        {
            std::lock_guard<std::mutex> lock(alert_keys_mutex_);
            active_alert_keys_.erase(cpu_critical_key);
            active_alert_keys_.erase(cpu_warning_key);
        }
    }
    
    // Memory checks
    std::string mem_critical_key = std::to_string(static_cast<int>(AlertCategory::MEMORY)) + ":" + 
                                   std::to_string(static_cast<int>(AlertSeverity::CRITICAL)) + ":" + 
                                   "system_monitor:Memory usage critical";
    std::string mem_warning_key = std::to_string(static_cast<int>(AlertCategory::MEMORY)) + ":" + 
                                  std::to_string(static_cast<int>(AlertSeverity::WARNING)) + ":" + 
                                  "system_monitor:Memory usage high";
    
    if (health.memory_usage_percent >= thresholds_.memory_critical) {
        create_basic_alert(
            AlertSeverity::CRITICAL,
            AlertCategory::MEMORY,
            "system_monitor",
            "Memory usage critical",
            "Memory usage is at " + std::to_string(static_cast<int>(health.memory_usage_percent)) + 
            "% (threshold: " + std::to_string(static_cast<int>(thresholds_.memory_critical)) + "%)"
        );
    } else if (health.memory_usage_percent >= thresholds_.memory_warning) {
        create_basic_alert(
            AlertSeverity::WARNING,
            AlertCategory::MEMORY,
            "system_monitor",
            "Memory usage high",
            "Memory usage is at " + std::to_string(static_cast<int>(health.memory_usage_percent)) + 
            "% (threshold: " + std::to_string(static_cast<int>(thresholds_.memory_warning)) + "%)"
        );
        // Remove critical key if it exists (downgraded from critical to warning)
        {
            std::lock_guard<std::mutex> lock(alert_keys_mutex_);
            active_alert_keys_.erase(mem_critical_key);
        }
    } else {
        // Memory usage recovered - remove both keys
        {
            std::lock_guard<std::mutex> lock(alert_keys_mutex_);
            active_alert_keys_.erase(mem_critical_key);
            active_alert_keys_.erase(mem_warning_key);
        }
    }
    
    // Disk checks
    std::string disk_critical_key = std::to_string(static_cast<int>(AlertCategory::DISK)) + ":" + 
                                    std::to_string(static_cast<int>(AlertSeverity::CRITICAL)) + ":" + 
                                    "system_monitor:Disk usage critical";
    std::string disk_warning_key = std::to_string(static_cast<int>(AlertCategory::DISK)) + ":" + 
                                   std::to_string(static_cast<int>(AlertSeverity::WARNING)) + ":" + 
                                   "system_monitor:Disk usage high";
    
    if (health.disk_usage_percent >= thresholds_.disk_critical) {
        create_basic_alert(
            AlertSeverity::CRITICAL,
            AlertCategory::DISK,
            "system_monitor",
            "Disk usage critical",
            "Disk usage on " + health.disk_mount_point + " is at " + 
            std::to_string(static_cast<int>(health.disk_usage_percent)) + 
            "% (threshold: " + std::to_string(static_cast<int>(thresholds_.disk_critical)) + "%)"
        );
    } else if (health.disk_usage_percent >= thresholds_.disk_warning) {
        create_basic_alert(
            AlertSeverity::WARNING,
            AlertCategory::DISK,
            "system_monitor",
            "Disk usage high",
            "Disk usage on " + health.disk_mount_point + " is at " + 
            std::to_string(static_cast<int>(health.disk_usage_percent)) + 
            "% (threshold: " + std::to_string(static_cast<int>(thresholds_.disk_warning)) + "%)"
        );
        // Remove critical key if it exists (downgraded from critical to warning)
        {
            std::lock_guard<std::mutex> lock(alert_keys_mutex_);
            active_alert_keys_.erase(disk_critical_key);
        }
    } else {
        // Disk usage recovered - remove both keys
        {
            std::lock_guard<std::mutex> lock(alert_keys_mutex_);
            active_alert_keys_.erase(disk_critical_key);
            active_alert_keys_.erase(disk_warning_key);
        }
    }
    
    // Failed services check
    std::string service_key = std::to_string(static_cast<int>(AlertCategory::SERVICE)) + ":" + 
                             std::to_string(static_cast<int>(AlertSeverity::ERROR)) + ":" + 
                             "system_monitor:Failed systemd services detected";
    
    if (health.failed_services_count > 0) {
        create_basic_alert(
            AlertSeverity::ERROR,
            AlertCategory::SERVICE,
            "system_monitor",
            "Failed systemd services detected",
            std::to_string(health.failed_services_count) + " systemd service(s) are in failed state"
        );
    } else {
        // No failed services - remove key if it exists
        {
            std::lock_guard<std::mutex> lock(alert_keys_mutex_);
            active_alert_keys_.erase(service_key);
        }
    }
}

void SystemMonitor::create_basic_alert(
    AlertSeverity severity,
    AlertCategory category,
    const std::string& source,
    const std::string& message,
    const std::string& description
) {
    if (!alert_manager_) {
        return;
    }
    
    // Create hash key for O(1) deduplication check
    std::string alert_key = std::to_string(static_cast<int>(category)) + ":" + 
                           std::to_string(static_cast<int>(severity)) + ":" + 
                           source + ":" + message;
    
    // RAII guard to ensure key is removed if alert creation fails
    // This prevents the key from remaining in the set forever if create_alert fails
    struct AlertKeyGuard {
        std::string key;
        std::unordered_set<std::string>& keys;
        std::mutex& mutex;
        bool committed = false;
        
        AlertKeyGuard(const std::string& k, std::unordered_set<std::string>& ks, std::mutex& m)
            : key(k), keys(ks), mutex(m) {}
        
        ~AlertKeyGuard() {
            if (!committed) {
                std::lock_guard<std::mutex> lock(mutex);
                keys.erase(key);
            }
        }
        
        void commit() { committed = true; }
    };
    
    // Check if already exists and insert if not
    {
        std::lock_guard<std::mutex> lock(alert_keys_mutex_);
        if (active_alert_keys_.find(alert_key) != active_alert_keys_.end()) {
            // Alert already exists, don't create duplicate
            return;
        }
        // Insert BEFORE creating alert to prevent race condition
        active_alert_keys_.insert(alert_key);
    }
    
    // Create RAII guard - will remove key if we return early or throw
    AlertKeyGuard guard(alert_key, active_alert_keys_, alert_keys_mutex_);
    
    Alert alert;
    alert.severity = severity;
    alert.category = category;
    alert.source = source;
    alert.message = message;
    alert.description = description;
    alert.status = AlertStatus::ACTIVE;
    alert.timestamp = std::chrono::system_clock::now();
    
    auto created = alert_manager_->create_alert(alert);
    if (!created.has_value()) {
        // Creation failed - guard will remove key in destructor
        return;
    }
    
    // Success - commit the guard so key remains in set
    guard.commit();
    LOG_DEBUG("SystemMonitor", "Created alert: " + message);
}

} // namespace cortexd
