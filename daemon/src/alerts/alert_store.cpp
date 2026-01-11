/**
 * @file alert_store.cpp
 * @brief SQLite-based alert storage implementation
 */

#include "cortexd/alerts/alert_manager.h"
#include "cortexd/logger.h"
#include <sqlite3.h>
#include <sstream>

namespace cortexd {

AlertStore::AlertStore(const std::string& db_path)
    : db_path_(db_path) {
}

AlertStore::~AlertStore() {
    if (db_) {
        sqlite3_close(static_cast<sqlite3*>(db_));
    }
}

bool AlertStore::init() {
    int rc = sqlite3_open(db_path_.c_str(), reinterpret_cast<sqlite3**>(&db_));
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertStore", "Cannot open database: " + db_path_);
        return false;
    }
    
    // Create alerts table
    const char* create_sql = R"(
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            timestamp INTEGER NOT NULL,
            severity INTEGER NOT NULL,
            type INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            metadata TEXT,
            acknowledged INTEGER DEFAULT 0,
            resolved INTEGER DEFAULT 0,
            acknowledged_at INTEGER,
            resolved_at INTEGER,
            resolution TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
        CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
        CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(acknowledged);
    )";
    
    char* err_msg = nullptr;
    rc = sqlite3_exec(static_cast<sqlite3*>(db_), create_sql, nullptr, nullptr, &err_msg);
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertStore", "Failed to create tables: " + std::string(err_msg));
        sqlite3_free(err_msg);
        return false;
    }
    
    LOG_DEBUG("AlertStore", "Initialized database: " + db_path_);
    return true;
}

bool AlertStore::insert(const Alert& alert) {
    const char* sql = R"(
        INSERT INTO alerts (id, timestamp, severity, type, title, message, metadata,
                           acknowledged, resolved, acknowledged_at, resolved_at, resolution)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    )";
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(static_cast<sqlite3*>(db_), sql, -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertStore", "Failed to prepare insert statement");
        return false;
    }
    
    // Convert metadata to JSON string
    json metadata_json = alert.metadata;
    std::string metadata_str = metadata_json.dump();
    
    sqlite3_bind_text(stmt, 1, alert.id.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 2, Clock::to_time_t(alert.timestamp));
    sqlite3_bind_int(stmt, 3, static_cast<int>(alert.severity));
    sqlite3_bind_int(stmt, 4, static_cast<int>(alert.type));
    sqlite3_bind_text(stmt, 5, alert.title.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 6, alert.message.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 7, metadata_str.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, 8, alert.acknowledged ? 1 : 0);
    sqlite3_bind_int(stmt, 9, alert.resolved ? 1 : 0);
    sqlite3_bind_int64(stmt, 10, alert.acknowledged ? Clock::to_time_t(alert.acknowledged_at) : 0);
    sqlite3_bind_int64(stmt, 11, alert.resolved ? Clock::to_time_t(alert.resolved_at) : 0);
    sqlite3_bind_text(stmt, 12, alert.resolution.c_str(), -1, SQLITE_TRANSIENT);
    
    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    return rc == SQLITE_DONE;
}

bool AlertStore::update(const Alert& alert) {
    const char* sql = R"(
        UPDATE alerts SET
            acknowledged = ?,
            resolved = ?,
            acknowledged_at = ?,
            resolved_at = ?,
            resolution = ?
        WHERE id = ?
    )";
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(static_cast<sqlite3*>(db_), sql, -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return false;
    }
    
    sqlite3_bind_int(stmt, 1, alert.acknowledged ? 1 : 0);
    sqlite3_bind_int(stmt, 2, alert.resolved ? 1 : 0);
    sqlite3_bind_int64(stmt, 3, alert.acknowledged ? Clock::to_time_t(alert.acknowledged_at) : 0);
    sqlite3_bind_int64(stmt, 4, alert.resolved ? Clock::to_time_t(alert.resolved_at) : 0);
    sqlite3_bind_text(stmt, 5, alert.resolution.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 6, alert.id.c_str(), -1, SQLITE_TRANSIENT);
    
    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    return rc == SQLITE_DONE;
}

bool AlertStore::remove(const std::string& id) {
    const char* sql = "DELETE FROM alerts WHERE id = ?";
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(static_cast<sqlite3*>(db_), sql, -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return false;
    }
    
    sqlite3_bind_text(stmt, 1, id.c_str(), -1, SQLITE_TRANSIENT);
    
    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    return rc == SQLITE_DONE;
}

std::optional<Alert> AlertStore::get(const std::string& id) {
    const char* sql = "SELECT * FROM alerts WHERE id = ?";
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(static_cast<sqlite3*>(db_), sql, -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return std::nullopt;
    }
    
    sqlite3_bind_text(stmt, 1, id.c_str(), -1, SQLITE_TRANSIENT);
    
    std::optional<Alert> result;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        result = row_to_alert(stmt);
    }
    
    sqlite3_finalize(stmt);
    return result;
}

std::vector<Alert> AlertStore::get_all(int limit) {
    std::string sql = "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT " + std::to_string(limit);
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(static_cast<sqlite3*>(db_), sql.c_str(), -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return {};
    }
    
    std::vector<Alert> results;
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        results.push_back(row_to_alert(stmt));
    }
    
    sqlite3_finalize(stmt);
    return results;
}

std::vector<Alert> AlertStore::get_active() {
    const char* sql = "SELECT * FROM alerts WHERE acknowledged = 0 ORDER BY timestamp DESC";
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(static_cast<sqlite3*>(db_), sql, -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return {};
    }
    
    std::vector<Alert> results;
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        results.push_back(row_to_alert(stmt));
    }
    
    sqlite3_finalize(stmt);
    return results;
}

std::vector<Alert> AlertStore::get_by_severity(AlertSeverity severity) {
    const char* sql = "SELECT * FROM alerts WHERE severity = ? AND acknowledged = 0 ORDER BY timestamp DESC";
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(static_cast<sqlite3*>(db_), sql, -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return {};
    }
    
    sqlite3_bind_int(stmt, 1, static_cast<int>(severity));
    
    std::vector<Alert> results;
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        results.push_back(row_to_alert(stmt));
    }
    
    sqlite3_finalize(stmt);
    return results;
}

std::vector<Alert> AlertStore::get_by_type(AlertType type) {
    const char* sql = "SELECT * FROM alerts WHERE type = ? AND acknowledged = 0 ORDER BY timestamp DESC";
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(static_cast<sqlite3*>(db_), sql, -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return {};
    }
    
    sqlite3_bind_int(stmt, 1, static_cast<int>(type));
    
    std::vector<Alert> results;
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        results.push_back(row_to_alert(stmt));
    }
    
    sqlite3_finalize(stmt);
    return results;
}

int AlertStore::count_active() {
    const char* sql = "SELECT COUNT(*) FROM alerts WHERE acknowledged = 0";
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(static_cast<sqlite3*>(db_), sql, -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return 0;
    }
    
    int count = 0;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        count = sqlite3_column_int(stmt, 0);
    }
    
    sqlite3_finalize(stmt);
    return count;
}

int AlertStore::count_by_severity(AlertSeverity severity) {
    const char* sql = "SELECT COUNT(*) FROM alerts WHERE severity = ? AND acknowledged = 0";
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(static_cast<sqlite3*>(db_), sql, -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return 0;
    }
    
    sqlite3_bind_int(stmt, 1, static_cast<int>(severity));
    
    int count = 0;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        count = sqlite3_column_int(stmt, 0);
    }
    
    sqlite3_finalize(stmt);
    return count;
}

int AlertStore::cleanup_before(TimePoint cutoff) {
    const char* sql = "DELETE FROM alerts WHERE timestamp < ? AND resolved = 1";
    
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(static_cast<sqlite3*>(db_), sql, -1, &stmt, nullptr);
    if (rc != SQLITE_OK) {
        return 0;
    }
    
    sqlite3_bind_int64(stmt, 1, Clock::to_time_t(cutoff));
    
    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    
    if (rc == SQLITE_DONE) {
        return sqlite3_changes(static_cast<sqlite3*>(db_));
    }
    
    return 0;
}

Alert AlertStore::row_to_alert(void* stmt_ptr) {
    sqlite3_stmt* stmt = static_cast<sqlite3_stmt*>(stmt_ptr);
    Alert alert;
    
    alert.id = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
    alert.timestamp = Clock::from_time_t(sqlite3_column_int64(stmt, 1));
    alert.severity = static_cast<AlertSeverity>(sqlite3_column_int(stmt, 2));
    alert.type = static_cast<AlertType>(sqlite3_column_int(stmt, 3));
    alert.title = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 4));
    
    const char* message = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 5));
    if (message) alert.message = message;
    
    const char* metadata_str = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 6));
    if (metadata_str) {
        try {
            json metadata_json = json::parse(metadata_str);
            for (auto& [key, value] : metadata_json.items()) {
                alert.metadata[key] = value.get<std::string>();
            }
        } catch (...) {
            // Ignore parse errors
        }
    }
    
    alert.acknowledged = sqlite3_column_int(stmt, 7) != 0;
    alert.resolved = sqlite3_column_int(stmt, 8) != 0;
    
    int64_t ack_at = sqlite3_column_int64(stmt, 9);
    if (ack_at > 0) {
        alert.acknowledged_at = Clock::from_time_t(ack_at);
    }
    
    int64_t res_at = sqlite3_column_int64(stmt, 10);
    if (res_at > 0) {
        alert.resolved_at = Clock::from_time_t(res_at);
    }
    
    const char* resolution = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 11));
    if (resolution) alert.resolution = resolution;
    
    return alert;
}

bool AlertStore::execute(const std::string& sql) {
    char* err_msg = nullptr;
    int rc = sqlite3_exec(static_cast<sqlite3*>(db_), sql.c_str(), nullptr, nullptr, &err_msg);
    if (rc != SQLITE_OK) {
        LOG_ERROR("AlertStore", "SQL error: " + std::string(err_msg));
        sqlite3_free(err_msg);
        return false;
    }
    return true;
}

} // namespace cortexd

