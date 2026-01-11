/**
 * @file handlers.cpp
 * @brief IPC request handler implementations
 */

#include "cortexd/ipc/handlers.h"
#include "cortexd/core/daemon.h"
#include "cortexd/monitor/system_monitor.h"
#include "cortexd/llm/engine.h"
#include "cortexd/alerts/alert_manager.h"
#include "cortexd/config.h"
#include "cortexd/logger.h"

namespace cortexd {

void Handlers::register_all(
    IPCServer& server,
    SystemMonitor& monitor,
    LLMEngine& llm,
    std::shared_ptr<AlertManager> alerts) {
    
    // Basic handlers
    server.register_handler(Methods::PING, [](const Request& req) {
        return handle_ping(req);
    });
    
    server.register_handler(Methods::VERSION, [](const Request& req) {
        return handle_version(req);
    });
    
    server.register_handler(Methods::STATUS, [&monitor, &llm, alerts](const Request& req) {
        return handle_status(req, monitor, llm, alerts);
    });
    
    server.register_handler(Methods::HEALTH, [&monitor, &llm, alerts](const Request& req) {
        return handle_health(req, monitor, llm, alerts);
    });
    
    // Alert handlers
    server.register_handler(Methods::ALERTS, [alerts](const Request& req) {
        return handle_alerts(req, alerts);
    });
    
    server.register_handler(Methods::ALERTS_GET, [alerts](const Request& req) {
        return handle_alerts(req, alerts);
    });
    
    server.register_handler(Methods::ALERTS_ACK, [alerts](const Request& req) {
        return handle_alerts_ack(req, alerts);
    });
    
    server.register_handler(Methods::ALERTS_DISMISS, [alerts](const Request& req) {
        return handle_alerts_dismiss(req, alerts);
    });
    
    // Config handlers
    server.register_handler(Methods::CONFIG_GET, [](const Request& req) {
        return handle_config_get(req);
    });
    
    server.register_handler(Methods::CONFIG_RELOAD, [](const Request& req) {
        return handle_config_reload(req);
    });
    
    // LLM handlers
    server.register_handler(Methods::LLM_STATUS, [&llm](const Request& req) {
        return handle_llm_status(req, llm);
    });
    
    server.register_handler(Methods::LLM_LOAD, [&llm, &monitor](const Request& req) {
        auto response = handle_llm_load(req, llm);
        // Update monitor with LLM load state
        if (response.success) {
            auto info = llm.get_model_info();
            monitor.set_llm_state(true, info ? info->name : "", 0);
        }
        return response;
    });
    
    server.register_handler(Methods::LLM_UNLOAD, [&llm, &monitor](const Request& req) {
        auto response = handle_llm_unload(req, llm);
        // Update monitor with LLM unload state
        monitor.set_llm_state(false, "", 0);
        return response;
    });
    
    server.register_handler(Methods::LLM_INFER, [&llm](const Request& req) {
        return handle_llm_infer(req, llm);
    });
    
    // Daemon control
    server.register_handler(Methods::SHUTDOWN, [](const Request& req) {
        return handle_shutdown(req);
    });
    
    LOG_INFO("Handlers", "Registered " + std::to_string(14) + " IPC handlers");
}

Response Handlers::handle_ping(const Request& /*req*/) {
    return Response::ok({{"pong", true}});
}

Response Handlers::handle_status(const Request& /*req*/, SystemMonitor& monitor, LLMEngine& llm, std::shared_ptr<AlertManager> alerts) {
    auto& daemon = Daemon::instance();
    auto snapshot = monitor.get_snapshot();
    
    // Override alert counts with fresh values from AlertManager
    if (alerts) {
        snapshot.active_alerts = alerts->count_active();
        snapshot.critical_alerts = alerts->count_by_severity(AlertSeverity::CRITICAL);
    }
    
    json result = {
        {"version", VERSION},
        {"uptime_seconds", daemon.uptime().count()},
        {"running", daemon.is_running()},
        {"health", snapshot.to_json()},
        {"llm", llm.status_json()}
    };
    
    return Response::ok(result);
}

Response Handlers::handle_health(const Request& /*req*/, SystemMonitor& monitor, LLMEngine& llm, std::shared_ptr<AlertManager> alerts) {
    auto snapshot = monitor.get_snapshot();
    
    // If snapshot seems uninitialized (timestamp is epoch), force a sync check
    if (snapshot.timestamp == TimePoint{}) {
        LOG_DEBUG("Handlers", "Running forced health check (snapshot empty)");
        snapshot = monitor.force_check();
    }
    
    // Override LLM status with actual engine state
    auto info = llm.get_model_info();
    snapshot.llm_loaded = llm.is_loaded();
    snapshot.llm_model_name = info ? info->name : "";
    
    // Override alert counts with fresh values from AlertManager
    if (alerts) {
        snapshot.active_alerts = alerts->count_active();
        snapshot.critical_alerts = alerts->count_by_severity(AlertSeverity::CRITICAL);
    }
    
    return Response::ok(snapshot.to_json());
}

Response Handlers::handle_version(const Request& /*req*/) {
    return Response::ok({
        {"version", VERSION},
        {"name", NAME}
    });
}

Response Handlers::handle_alerts(const Request& req, std::shared_ptr<AlertManager> alerts) {
    if (!alerts) {
        return Response::err("Alert manager not available", ErrorCodes::INTERNAL_ERROR);
    }
    
    // Check for filters
    std::string severity_filter;
    std::string type_filter;
    int limit = 100;
    
    if (req.params.contains("severity")) {
        severity_filter = req.params["severity"].get<std::string>();
    }
    if (req.params.contains("type")) {
        type_filter = req.params["type"].get<std::string>();
    }
    if (req.params.contains("limit")) {
        limit = req.params["limit"].get<int>();
    }
    
    std::vector<Alert> alert_list;
    
    if (!severity_filter.empty()) {
        alert_list = alerts->get_by_severity(severity_from_string(severity_filter));
    } else if (!type_filter.empty()) {
        alert_list = alerts->get_by_type(alert_type_from_string(type_filter));
    } else {
        alert_list = alerts->get_active();
    }
    
    // Limit results
    if (static_cast<int>(alert_list.size()) > limit) {
        alert_list.resize(limit);
    }
    
    json alerts_json = json::array();
    for (const auto& alert : alert_list) {
        alerts_json.push_back(alert.to_json());
    }
    
    return Response::ok({
        {"alerts", alerts_json},
        {"count", alerts_json.size()},
        {"total_active", alerts->count_active()}
    });
}

Response Handlers::handle_alerts_ack(const Request& req, std::shared_ptr<AlertManager> alerts) {
    if (!alerts) {
        return Response::err("Alert manager not available", ErrorCodes::INTERNAL_ERROR);
    }
    
    if (req.params.contains("id")) {
        std::string id = req.params["id"].get<std::string>();
        if (alerts->acknowledge(id)) {
            return Response::ok({{"acknowledged", id}});
        }
        return Response::err("Alert not found", ErrorCodes::ALERT_NOT_FOUND);
    }
    
    if (req.params.contains("all") && req.params["all"].get<bool>()) {
        int count = alerts->acknowledge_all();
        return Response::ok({{"acknowledged_count", count}});
    }
    
    return Response::err("Missing 'id' or 'all' parameter", ErrorCodes::INVALID_PARAMS);
}

Response Handlers::handle_alerts_dismiss(const Request& req, std::shared_ptr<AlertManager> alerts) {
    if (!alerts) {
        return Response::err("Alert manager not available", ErrorCodes::INTERNAL_ERROR);
    }
    
    if (!req.params.contains("id")) {
        return Response::err("Missing 'id' parameter", ErrorCodes::INVALID_PARAMS);
    }
    
    std::string id = req.params["id"].get<std::string>();
    if (alerts->dismiss(id)) {
        return Response::ok({{"dismissed", id}});
    }
    
    return Response::err("Alert not found", ErrorCodes::ALERT_NOT_FOUND);
}

Response Handlers::handle_config_get(const Request& /*req*/) {
    const auto& config = ConfigManager::instance().get();
    
    json result = {
        {"socket_path", config.socket_path},
        {"model_path", config.model_path},
        {"llm_context_length", config.llm_context_length},
        {"llm_threads", config.llm_threads},
        {"monitor_interval_sec", config.monitor_interval_sec},
        {"log_level", config.log_level},
        {"thresholds", {
            {"disk_warn", config.disk_warn_threshold},
            {"disk_crit", config.disk_crit_threshold},
            {"mem_warn", config.mem_warn_threshold},
            {"mem_crit", config.mem_crit_threshold}
        }}
    };
    
    return Response::ok(result);
}

Response Handlers::handle_config_reload(const Request& /*req*/) {
    if (Daemon::instance().reload_config()) {
        return Response::ok({{"reloaded", true}});
    }
    return Response::err("Failed to reload configuration", ErrorCodes::CONFIG_ERROR);
}

Response Handlers::handle_llm_status(const Request& /*req*/, LLMEngine& llm) {
    return Response::ok(llm.status_json());
}

Response Handlers::handle_llm_load(const Request& req, LLMEngine& llm) {
    if (!req.params.contains("model_path")) {
        return Response::err("Missing 'model_path' parameter", ErrorCodes::INVALID_PARAMS);
    }
    
    std::string path = req.params["model_path"].get<std::string>();
    
    if (llm.load_model(path)) {
        auto info = llm.get_model_info();
        return Response::ok({
            {"loaded", true},
            {"model", info ? info->to_json() : json::object()}
        });
    }
    
    return Response::err("Failed to load model", ErrorCodes::INTERNAL_ERROR);
}

Response Handlers::handle_llm_unload(const Request& /*req*/, LLMEngine& llm) {
    llm.unload_model();
    return Response::ok({{"unloaded", true}});
}

Response Handlers::handle_llm_infer(const Request& req, LLMEngine& llm) {
    if (!llm.is_loaded()) {
        return Response::err("Model not loaded", ErrorCodes::LLM_NOT_LOADED);
    }
    
    if (!req.params.contains("prompt")) {
        return Response::err("Missing 'prompt' parameter", ErrorCodes::INVALID_PARAMS);
    }
    
    InferenceRequest infer_req;
    infer_req.prompt = req.params["prompt"].get<std::string>();
    
    if (req.params.contains("max_tokens")) {
        infer_req.max_tokens = req.params["max_tokens"].get<int>();
    }
    if (req.params.contains("temperature")) {
        infer_req.temperature = req.params["temperature"].get<float>();
    }
    if (req.params.contains("top_p")) {
        infer_req.top_p = req.params["top_p"].get<float>();
    }
    if (req.params.contains("stop")) {
        infer_req.stop_sequence = req.params["stop"].get<std::string>();
    }
    
    // Synchronous inference for IPC
    auto result = llm.infer_sync(infer_req);
    
    return Response::ok(result.to_json());
}

Response Handlers::handle_shutdown(const Request& /*req*/) {
    LOG_INFO("Handlers", "Shutdown requested via IPC");
    Daemon::instance().request_shutdown();
    return Response::ok({{"shutdown", "initiated"}});
}

} // namespace cortexd

