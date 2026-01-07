/**
 * @file handlers.h
 * @brief IPC request handlers
 */

#pragma once

#include "cortexd/ipc/server.h"
#include "cortexd/ipc/protocol.h"
#include <memory>

namespace cortexd {

// Forward declarations
class SystemMonitor;
class LLMEngine;
class AlertManager;

/**
 * @brief IPC request handlers
 */
class Handlers {
public:
    /**
     * @brief Register all handlers with IPC server
     */
    static void register_all(
        IPCServer& server,
        SystemMonitor& monitor,
        LLMEngine& llm,
        std::shared_ptr<AlertManager> alerts
    );
    
private:
    // Handler implementations
    static Response handle_ping(const Request& req);
    static Response handle_status(const Request& req, SystemMonitor& monitor, LLMEngine& llm, std::shared_ptr<AlertManager> alerts);
    static Response handle_health(const Request& req, SystemMonitor& monitor, LLMEngine& llm, std::shared_ptr<AlertManager> alerts);
    static Response handle_version(const Request& req);
    
    // Alert handlers
    static Response handle_alerts(const Request& req, std::shared_ptr<AlertManager> alerts);
    static Response handle_alerts_ack(const Request& req, std::shared_ptr<AlertManager> alerts);
    static Response handle_alerts_dismiss(const Request& req, std::shared_ptr<AlertManager> alerts);
    
    // Config handlers
    static Response handle_config_get(const Request& req);
    static Response handle_config_reload(const Request& req);
    
    // LLM handlers
    static Response handle_llm_status(const Request& req, LLMEngine& llm);
    static Response handle_llm_load(const Request& req, LLMEngine& llm);
    static Response handle_llm_unload(const Request& req, LLMEngine& llm);
    static Response handle_llm_infer(const Request& req, LLMEngine& llm);
    
    // Daemon control
    static Response handle_shutdown(const Request& req);
};

} // namespace cortexd

