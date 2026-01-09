/**
 * @file alert_manager.h
 * @brief Alert management with SQLite persistence
 */

#pragma once

#include "cortexd/common.h"
#include <string>
#include <vector>
#include <memory>
#include <functional>
#include <mutex>
#include <chrono>
#include <map>
#include <optional>

namespace cortexd {

/**
 * @brief Alert structure
 */
struct Alert {
    std::string id;
    TimePoint timestamp;
    AlertSeverity severity = AlertSeverity::INFO;
    AlertType type = AlertType::SYSTEM;
    std::string title;
    std::string message;
    std::map<std::string, std::string> metadata;
    bool acknowledged = false;
    bool resolved = false;
    TimePoint acknowledged_at;
    TimePoint resolved_at;
    std::string resolution;
    
    json to_json() const {
        json j = {
            {"id", id},
            {"timestamp", Clock::to_time_t(timestamp)},
            {"severity", to_string(severity)},
            {"type", to_string(type)},
            {"title", title},
            {"message", message},
            {"acknowledged", acknowledged},
            {"resolved", resolved}
        };
        
        if (!metadata.empty()) {
            j["metadata"] = metadata;
        }
        if (acknowledged) {
            j["acknowledged_at"] = Clock::to_time_t(acknowledged_at);
        }
        if (resolved) {
            j["resolved_at"] = Clock::to_time_t(resolved_at);
            j["resolution"] = resolution;
        }
        
        return j;
    }
    
    static Alert from_json(const json& j);
};

// Forward declaration
class AlertStore;

/**
 * @brief Alert callback for notifications
 */
using AlertCallback = std::function<void(const Alert&)>;

/**
 * @brief Alert manager with SQLite persistence
 */
class AlertManager {
public:
    /**
     * @brief Construct alert manager
     * @param db_path Path to SQLite database (~ expanded)
     */
    explicit AlertManager(const std::string& db_path = DEFAULT_ALERT_DB);
    ~AlertManager();
    
    /**
     * @brief Create a new alert
     * @return Alert ID
     */
    std::string create(
        AlertSeverity severity,
        AlertType type,
        const std::string& title,
        const std::string& message,
        const std::map<std::string, std::string>& metadata = {}
    );
    
    /**
     * @brief Get all alerts
     * @param limit Maximum number to return
     */
    std::vector<Alert> get_all(int limit = 100);
    
    /**
     * @brief Get active (unacknowledged) alerts
     */
    std::vector<Alert> get_active();
    
    /**
     * @brief Get alerts by severity
     */
    std::vector<Alert> get_by_severity(AlertSeverity severity);
    
    /**
     * @brief Get alerts by type
     */
    std::vector<Alert> get_by_type(AlertType type);
    
    /**
     * @brief Get alert by ID
     */
    std::optional<Alert> get_by_id(const std::string& id);
    
    /**
     * @brief Acknowledge an alert
     * @return true if successful
     */
    bool acknowledge(const std::string& id);
    
    /**
     * @brief Resolve an alert
     * @param id Alert ID
     * @param resolution Optional resolution message
     * @return true if successful
     */
    bool resolve(const std::string& id, const std::string& resolution = "");
    
    /**
     * @brief Dismiss (delete) an alert
     * @return true if successful
     */
    bool dismiss(const std::string& id);
    
    /**
     * @brief Acknowledge all active alerts
     * @return Number acknowledged
     */
    int acknowledge_all();
    
    /**
     * @brief Clean up old alerts
     * @param max_age Maximum age to keep
     * @return Number deleted
     */
    int cleanup_old(std::chrono::hours max_age = std::chrono::hours(168));
    
    /**
     * @brief Count active alerts
     */
    int count_active() const;
    
    /**
     * @brief Count alerts by severity
     */
    int count_by_severity(AlertSeverity severity) const;
    
    /**
     * @brief Register callback for new alerts
     */
    void on_alert(AlertCallback callback);
    
    /**
     * @brief Export all alerts as JSON
     */
    json export_json();
    
private:
    std::unique_ptr<AlertStore> store_;
    std::vector<AlertCallback> callbacks_;
    mutable std::mutex mutex_;
    bool initialized_ = false;  // Track initialization status
    
    // Deduplication - recent alert hashes
    std::map<std::string, TimePoint> recent_alerts_;
    std::chrono::minutes dedup_window_{5};
    
    /**
     * @brief Generate unique alert ID
     */
    std::string generate_id();
    
    /**
     * @brief Notify registered callbacks
     */
    void notify_callbacks(const Alert& alert);
    
    /**
     * @brief Check if alert is duplicate
     */
    bool is_duplicate(const Alert& alert);
    
    /**
     * @brief Get alert hash for deduplication
     */
    std::string get_alert_hash(const Alert& alert);
};

/**
 * @brief SQLite-based alert storage
 * 
 * Non-copyable and non-movable to prevent double-closing the SQLite handle.
 */
class AlertStore {
public:
    explicit AlertStore(const std::string& db_path);
    ~AlertStore();
    
    // Non-copyable: prevent double-closing the raw sqlite handle
    AlertStore(const AlertStore&) = delete;
    AlertStore& operator=(const AlertStore&) = delete;
    
    // Non-movable: prevent ownership transfer issues with db_
    AlertStore(AlertStore&&) = delete;
    AlertStore& operator=(AlertStore&&) = delete;
    
    bool init();
    bool insert(const Alert& alert);
    bool update(const Alert& alert);
    bool remove(const std::string& id);
    
    std::optional<Alert> get(const std::string& id);
    std::vector<Alert> get_all(int limit);
    std::vector<Alert> get_active();
    std::vector<Alert> get_by_severity(AlertSeverity severity);
    std::vector<Alert> get_by_type(AlertType type);
    
    int count_active();
    int count_by_severity(AlertSeverity severity);
    int cleanup_before(TimePoint cutoff);
    
private:
    std::string db_path_;
    void* db_ = nullptr;  // sqlite3*
    
    bool execute(const std::string& sql);
    Alert row_to_alert(void* stmt);  // sqlite3_stmt*
};

} // namespace cortexd

