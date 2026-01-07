/**
 * @file service.h
 * @brief Base interface for daemon services
 */

#pragma once

#include <string>

namespace cortexd {

/**
 * @brief Base class for all daemon services
 * 
 * Services are managed by the Daemon class and have a defined lifecycle:
 * 1. Construction
 * 2. start() - Initialize and begin operation
 * 3. Running state (is_healthy() called periodically)
 * 4. stop() - Graceful shutdown
 * 5. Destruction
 */
class Service {
public:
    virtual ~Service() = default;
    
    /**
     * @brief Start the service
     * @return true if started successfully
     */
    virtual bool start() = 0;
    
    /**
     * @brief Stop the service gracefully
     */
    virtual void stop() = 0;
    
    /**
     * @brief Get service name for logging
     */
    virtual const char* name() const = 0;
    
    /**
     * @brief Check if service is healthy
     * @return true if operating normally
     */
    virtual bool is_healthy() const { return true; }
    
    /**
     * @brief Get startup priority (higher = start earlier)
     * 
     * Suggested priorities:
     * - 100: IPC Server (must start first to accept connections)
     * - 50: System Monitor
     * - 10: LLM Engine (optional, can start last)
     */
    virtual int priority() const { return 0; }
    
    /**
     * @brief Check if service is currently running
     */
    virtual bool is_running() const = 0;
};

} // namespace cortexd

