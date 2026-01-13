#pragma once

#include <string>
#include <memory>
#include <thread>
#include <atomic>
#include "cortexd_common.h"

namespace cortex {
namespace daemon {

// Forward declaration
class SystemMonitor;

// Unix socket server
class SocketServer {
public:
    SocketServer(const std::string& socket_path = SOCKET_PATH);
    ~SocketServer();

    // Start listening on socket
    bool start();

    // Stop the server
    void stop();

    // Check if running
    bool is_running() const;

    // Get socket path
    const std::string& get_socket_path() const { return socket_path_; }

    // Set system monitor for health checks (must be called before start)
    void set_system_monitor(SystemMonitor* monitor) { system_monitor_ = monitor; }

private:
    std::string socket_path_;
    int server_fd_;
    std::atomic<bool> running_;
    std::unique_ptr<std::thread> accept_thread_;
    SystemMonitor* system_monitor_ = nullptr;  // Non-owning pointer

    // Accept connections and handle requests
    void accept_connections();

    // Handle single client connection
    void handle_client(int client_fd);

    // Create Unix socket
    bool create_socket();

    // Setup socket permissions
    bool setup_permissions();

    // Cleanup socket file
    void cleanup_socket();
};

} // namespace daemon
} // namespace cortex
