/**
 * @file alert_manager_impl.cpp
 * @brief Implementation of AlertManagerImpl for the legacy cortex::daemon namespace
 * 
 * This provides a simple in-memory alert manager used by tests and the legacy
 * SocketServer. For production use, prefer cortexd::AlertManager which has
 * SQLite persistence.
 */

#include "alert_manager.h"
#include <uuid/uuid.h>
#include <algorithm>
#include <chrono>

namespace cortex {
namespace daemon {

// Alert JSON serialization
json Alert::to_json() const {
    json j = {
        {"id", id},
        {"timestamp", std::chrono::system_clock::to_time_t(timestamp)},
        {"severity", to_string(severity)},
        {"type", to_string(type)},
        {"title", title},
        {"description", description},
        {"acknowledged", acknowledged}
    };
    
    if (!metadata.empty()) {
        j["metadata"] = metadata;
    }
    
    return j;
}

Alert Alert::from_json(const json& j) {
    Alert alert;
    alert.id = j.value("id", "");
    alert.timestamp = std::chrono::system_clock::from_time_t(j.value("timestamp", 0L));
    alert.severity = severity_from_string(j.value("severity", "info"));
    alert.type = alert_type_from_string(j.value("type", "system"));
    alert.title = j.value("title", "");
    alert.description = j.value("description", "");
    alert.acknowledged = j.value("acknowledged", false);
    
    if (j.contains("metadata")) {
        for (auto& [key, value] : j["metadata"].items()) {
            alert.metadata[key] = value.get<std::string>();
        }
    }
    
    return alert;
}

// AlertManagerImpl implementation

AlertManagerImpl::AlertManagerImpl() {
    // No initialization needed for in-memory storage
}

std::string AlertManagerImpl::generate_alert_id() {
    uuid_t uuid;
    char uuid_str[37];
    uuid_generate(uuid);
    uuid_unparse_lower(uuid, uuid_str);
    return std::string(uuid_str);
}

std::string AlertManagerImpl::create_alert(
    AlertSeverity severity,
    AlertType type,
    const std::string& title,
    const std::string& description,
    const std::map<std::string, std::string>& metadata) {
    
    std::lock_guard<std::mutex> lock(alerts_mutex);
    
    Alert alert;
    alert.id = generate_alert_id();
    alert.timestamp = std::chrono::system_clock::now();
    alert.severity = severity;
    alert.type = type;
    alert.title = title;
    alert.description = description;
    alert.metadata = metadata;
    alert.acknowledged = false;
    
    alerts.push_back(alert);
    
    return alert.id;
}

std::vector<Alert> AlertManagerImpl::get_active_alerts() {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    
    std::vector<Alert> active;
    for (const auto& alert : alerts) {
        if (!alert.acknowledged) {
            active.push_back(alert);
        }
    }
    
    return active;
}

std::vector<Alert> AlertManagerImpl::get_alerts_by_severity(AlertSeverity severity) {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    
    std::vector<Alert> result;
    for (const auto& alert : alerts) {
        if (alert.severity == severity) {
            result.push_back(alert);
        }
    }
    
    return result;
}

std::vector<Alert> AlertManagerImpl::get_alerts_by_type(AlertType type) {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    
    std::vector<Alert> result;
    for (const auto& alert : alerts) {
        if (alert.type == type) {
            result.push_back(alert);
        }
    }
    
    return result;
}

bool AlertManagerImpl::acknowledge_alert(const std::string& alert_id) {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    
    for (auto& alert : alerts) {
        if (alert.id == alert_id) {
            alert.acknowledged = true;
            return true;
        }
    }
    
    return false;
}

void AlertManagerImpl::clear_acknowledged_alerts() {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    
    alerts.erase(
        std::remove_if(alerts.begin(), alerts.end(),
                       [](const Alert& a) { return a.acknowledged; }),
        alerts.end());
}

int AlertManagerImpl::get_alert_count() {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    return static_cast<int>(alerts.size());
}

json AlertManagerImpl::export_alerts_json() {
    std::lock_guard<std::mutex> lock(alerts_mutex);
    
    json j = json::array();
    for (const auto& alert : alerts) {
        j.push_back(alert.to_json());
    }
    
    return j;
}

} // namespace daemon
} // namespace cortex

