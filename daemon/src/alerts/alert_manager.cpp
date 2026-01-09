/**
 * @file alert_manager.cpp
 * @brief Alert manager implementation
 */

#include "cortexd/alerts/alert_manager.h"
#include "cortexd/logger.h"
#include <uuid/uuid.h>
#include <functional>
#include <filesystem>

namespace cortexd {

Alert Alert::from_json(const json& j) {
    Alert alert;
    alert.id = j.value("id", "");
    alert.timestamp = Clock::from_time_t(j.value("timestamp", 0L));
    alert.severity = severity_from_string(j.value("severity", "info"));
    alert.type = alert_type_from_string(j.value("type", "system"));
    alert.title = j.value("title", "");
    alert.message = j.value("message", "");
    alert.acknowledged = j.value("acknowledged", false);
    alert.resolved = j.value("resolved", false);
    
    if (j.contains("metadata")) {
        for (auto& [key, value] : j["metadata"].items()) {
            alert.metadata[key] = value.get<std::string>();
        }
    }
    
    if (j.contains("acknowledged_at")) {
        alert.acknowledged_at = Clock::from_time_t(j["acknowledged_at"].get<long>());
    }
    if (j.contains("resolved_at")) {
        alert.resolved_at = Clock::from_time_t(j["resolved_at"].get<long>());
    }
    if (j.contains("resolution")) {
        alert.resolution = j["resolution"].get<std::string>();
    }
    
    return alert;
}

// AlertManager implementation

AlertManager::AlertManager(const std::string& db_path) {
    std::string expanded = expand_path(db_path);
    
    // Create parent directory if needed
    auto parent = std::filesystem::path(expanded).parent_path();
    if (!parent.empty() && !std::filesystem::exists(parent)) {
        std::filesystem::create_directories(parent);
    }
    
    store_ = std::make_unique<AlertStore>(expanded);
    if (!store_->init()) {
        LOG_ERROR("AlertManager", "Failed to initialize alert store");
    }
    
    LOG_INFO("AlertManager", "Initialized with database: " + expanded);
}

AlertManager::~AlertManager() = default;

std::string AlertManager::create(
    AlertSeverity severity,
    AlertType type,
    const std::string& title,
    const std::string& message,
    const std::map<std::string, std::string>& metadata) {
    
    Alert alert;
    alert.id = generate_id();
    alert.timestamp = Clock::now();
    alert.severity = severity;
    alert.type = type;
    alert.title = title;
    alert.message = message;
    alert.metadata = metadata;
    
    // Acquire lock before checking for duplicate to avoid race condition
    std::lock_guard<std::mutex> lock(mutex_);
    
    // Check for duplicate (now protected by mutex_)
    if (is_duplicate(alert)) {
        LOG_DEBUG("AlertManager", "Duplicate alert suppressed: " + title);
        return "";
    }
    
    if (store_->insert(alert)) {
        LOG_INFO("AlertManager", "Created alert: [" + std::string(to_string(severity)) + 
                 "] " + title + " (" + alert.id.substr(0, 8) + ")");
        
        // Track for deduplication
        recent_alerts_[get_alert_hash(alert)] = alert.timestamp;
        
        // Notify callbacks
        notify_callbacks(alert);
        
        return alert.id;
    }
    
    LOG_ERROR("AlertManager", "Failed to create alert: " + title);
    return "";
}

std::vector<Alert> AlertManager::get_all(int limit) {
    std::lock_guard<std::mutex> lock(mutex_);
    return store_->get_all(limit);
}

std::vector<Alert> AlertManager::get_active() {
    std::lock_guard<std::mutex> lock(mutex_);
    return store_->get_active();
}

std::vector<Alert> AlertManager::get_by_severity(AlertSeverity severity) {
    std::lock_guard<std::mutex> lock(mutex_);
    return store_->get_by_severity(severity);
}

std::vector<Alert> AlertManager::get_by_type(AlertType type) {
    std::lock_guard<std::mutex> lock(mutex_);
    return store_->get_by_type(type);
}

std::optional<Alert> AlertManager::get_by_id(const std::string& id) {
    std::lock_guard<std::mutex> lock(mutex_);
    return store_->get(id);
}

bool AlertManager::acknowledge(const std::string& id) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    auto alert = store_->get(id);
    if (!alert) {
        return false;
    }
    
    alert->acknowledged = true;
    alert->acknowledged_at = Clock::now();
    
    if (store_->update(*alert)) {
        LOG_INFO("AlertManager", "Acknowledged alert: " + id.substr(0, 8));
        return true;
    }
    
    return false;
}

bool AlertManager::resolve(const std::string& id, const std::string& resolution) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    auto alert = store_->get(id);
    if (!alert) {
        return false;
    }
    
    alert->resolved = true;
    alert->resolved_at = Clock::now();
    alert->resolution = resolution;
    
    if (store_->update(*alert)) {
        LOG_INFO("AlertManager", "Resolved alert: " + id.substr(0, 8));
        return true;
    }
    
    return false;
}

bool AlertManager::dismiss(const std::string& id) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    if (store_->remove(id)) {
        LOG_INFO("AlertManager", "Dismissed alert: " + id.substr(0, 8));
        return true;
    }
    
    return false;
}

int AlertManager::acknowledge_all() {
    std::lock_guard<std::mutex> lock(mutex_);
    
    auto active = store_->get_active();
    int count = 0;
    
    for (auto& alert : active) {
        alert.acknowledged = true;
        alert.acknowledged_at = Clock::now();
        if (store_->update(alert)) {
            count++;
        }
    }
    
    LOG_INFO("AlertManager", "Acknowledged " + std::to_string(count) + " alerts");
    return count;
}

int AlertManager::cleanup_old(std::chrono::hours max_age) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    auto cutoff = Clock::now() - max_age;
    int count = store_->cleanup_before(cutoff);
    
    // Also clean up deduplication map
    for (auto it = recent_alerts_.begin(); it != recent_alerts_.end();) {
        if (it->second < cutoff) {
            it = recent_alerts_.erase(it);
        } else {
            ++it;
        }
    }
    
    LOG_INFO("AlertManager", "Cleaned up " + std::to_string(count) + " old alerts");
    return count;
}

int AlertManager::count_active() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return store_->count_active();
}

int AlertManager::count_by_severity(AlertSeverity severity) const {
    std::lock_guard<std::mutex> lock(mutex_);
    return store_->count_by_severity(severity);
}

void AlertManager::on_alert(AlertCallback callback) {
    std::lock_guard<std::mutex> lock(mutex_);
    callbacks_.push_back(std::move(callback));
}

json AlertManager::export_json() {
    std::lock_guard<std::mutex> lock(mutex_);
    
    json j = json::array();
    auto all = store_->get_all(1000);
    
    for (const auto& alert : all) {
        j.push_back(alert.to_json());
    }
    
    return j;
}

std::string AlertManager::generate_id() {
    uuid_t uuid;
    char uuid_str[37];
    uuid_generate(uuid);
    uuid_unparse_lower(uuid, uuid_str);
    return std::string(uuid_str);
}

void AlertManager::notify_callbacks(const Alert& alert) {
    for (const auto& callback : callbacks_) {
        try {
            callback(alert);
        } catch (const std::exception& e) {
            LOG_ERROR("AlertManager", "Callback error: " + std::string(e.what()));
        }
    }
}

bool AlertManager::is_duplicate(const Alert& alert) {
    std::string hash = get_alert_hash(alert);
    auto now = Clock::now();
    
    // Clean old entries
    for (auto it = recent_alerts_.begin(); it != recent_alerts_.end();) {
        if (now - it->second > dedup_window_) {
            it = recent_alerts_.erase(it);
        } else {
            ++it;
        }
    }
    
    // Check if recent
    auto it = recent_alerts_.find(hash);
    return it != recent_alerts_.end();
}

std::string AlertManager::get_alert_hash(const Alert& alert) {
    // Simple hash based on type, severity, and title
    return std::to_string(static_cast<int>(alert.type)) + ":" +
           std::to_string(static_cast<int>(alert.severity)) + ":" +
           alert.title;
}

} // namespace cortexd

