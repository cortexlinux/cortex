/**
 * @file server.cpp
 * @brief Unix socket IPC server implementation
 */

 #include "cortexd/ipc/server.h"
 #include "cortexd/logger.h"
 #include <sys/socket.h>
 #include <sys/un.h>
 #include <sys/stat.h>
 #include <unistd.h>
 #include <fcntl.h>
 #include <cstring>
 #include <filesystem>
 
 namespace cortexd {
 
// RateLimiter implementation (lock-free)

RateLimiter::RateLimiter(int max_per_second)
    : max_per_second_(max_per_second) {
    auto now = std::chrono::steady_clock::now();
    auto now_rep = now.time_since_epoch().count();
    window_start_rep_.store(now_rep, std::memory_order_relaxed);
}

bool RateLimiter::allow() {
    auto now = std::chrono::steady_clock::now();
    auto now_rep = now.time_since_epoch().count();
    auto window_start_rep = window_start_rep_.load(std::memory_order_acquire);
    
    std::chrono::steady_clock::time_point window_start{
        std::chrono::steady_clock::duration{window_start_rep}
    };
    
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - window_start);
    
    // Reset window every second (lock-free compare-and-swap)
    if (elapsed.count() >= 1000) {
        // Try to update window_start atomically
        auto expected = window_start_rep;
        if (window_start_rep_.compare_exchange_weak(
                expected, now_rep, 
                std::memory_order_acq_rel, 
                std::memory_order_acquire)) {
            // We won the race to reset - reset count atomically
            count_.store(0, std::memory_order_release);
        } else {
            // If we lost the race, reload window_start as another thread may have reset
            window_start_rep = window_start_rep_.load(std::memory_order_acquire);
            // Recalculate elapsed time with new window_start
            std::chrono::steady_clock::time_point new_window_start{
                std::chrono::steady_clock::duration{window_start_rep}
            };
            elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - new_window_start);
            // If still in new window and count was reset, current will be 0, which is fine
        }
    }
    
    // Secure lock-free increment with check: use compare-and-swap loop
    // This ensures we never exceed the limit, even under high concurrency
    int current;
    int next;
    do {
        current = count_.load(std::memory_order_acquire);
        
        // Check limit BEFORE incrementing (security: never exceed limit)
        if (current >= max_per_second_) {
            return false;  // Rate limit exceeded
        }
        
        next = current + 1;
        // Atomically increment only if count hasn't changed (prevents race conditions)
    } while (!count_.compare_exchange_weak(
        current, next,
        std::memory_order_release,
        std::memory_order_acquire));
    
    // Successfully incremented without exceeding limit
    return true;
}

void RateLimiter::reset() {
    auto now = std::chrono::steady_clock::now();
    auto now_rep = now.time_since_epoch().count();
    count_.store(0, std::memory_order_relaxed);
    window_start_rep_.store(now_rep, std::memory_order_relaxed);
}
 
 // IPCServer implementation
 
 IPCServer::IPCServer(const std::string& socket_path, int max_requests_per_sec)
     : socket_path_(socket_path)
     , rate_limiter_(max_requests_per_sec) {
 }
 
 IPCServer::~IPCServer() {
     stop();
 }
 
 bool IPCServer::start() {
     if (running_) {
         return true;
     }
     
     if (!create_socket()) {
         return false;
     }
     
     running_ = true;
     accept_thread_ = std::make_unique<std::thread>([this] { accept_loop(); });
     
     LOG_INFO("IPCServer", "Started on " + socket_path_);
     return true;
 }
 
 void IPCServer::stop() {
     if (!running_) {
         return;
     }
     
     running_ = false;
     
     // Shutdown socket to unblock accept() and stop new connections
     {
         std::lock_guard<std::mutex> lock(server_fd_mutex_);
         if (server_fd_ != -1) {
             shutdown(server_fd_, SHUT_RDWR);
         }
     }
     
     // Wait for accept thread
     if (accept_thread_ && accept_thread_->joinable()) {
         accept_thread_->join();
     }
     
     // Wait for all in-flight handlers to finish before cleanup
     // This prevents dangling references to server state
     {
         std::unique_lock<std::mutex> lock(connections_mutex_);
         connections_cv_.wait(lock, [this] {
             return active_connections_.load() == 0;
         });
     }
     
     cleanup_socket();
     LOG_INFO("IPCServer", "Stopped");
 }
 
 bool IPCServer::is_healthy() const {
     std::lock_guard<std::mutex> lock(server_fd_mutex_);
     return running_.load() && server_fd_ != -1;
 }
 
void IPCServer::register_handler(const std::string& method, RequestHandler handler) {
    std::unique_lock<std::shared_mutex> lock(handlers_mutex_);  // Exclusive lock for write
    handlers_[method] = std::move(handler);
    LOG_DEBUG("IPCServer", "Registered handler for: " + method);
}
 
 bool IPCServer::create_socket() {
     std::lock_guard<std::mutex> lock(server_fd_mutex_);
     
     // Create socket
     server_fd_ = socket(AF_UNIX, SOCK_STREAM, 0);
     if (server_fd_ == -1) {
         LOG_ERROR("IPCServer", "Failed to create socket: " + std::string(strerror(errno)));
         return false;
     }
     
     // Set socket options
     int opt = 1;
     setsockopt(server_fd_, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
     
     // Remove existing socket file
     if (std::filesystem::exists(socket_path_)) {
         std::filesystem::remove(socket_path_);
         LOG_DEBUG("IPCServer", "Removed existing socket file");
     }
     
     // Create parent directory if needed
     auto parent = std::filesystem::path(socket_path_).parent_path();
     if (!parent.empty() && !std::filesystem::exists(parent)) {
         std::filesystem::create_directories(parent);
     }
     
    // Bind socket
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    
    // Check socket path length before copying to prevent silent truncation
    if (socket_path_.size() > sizeof(addr.sun_path) - 1) {
        LOG_ERROR("IPCServer", "Socket path too long: " + socket_path_ + " (max " + 
                  std::to_string(sizeof(addr.sun_path) - 1) + " bytes)");
        close(server_fd_);
        server_fd_ = -1;
        return false;
    }
    
    strncpy(addr.sun_path, socket_path_.c_str(), sizeof(addr.sun_path) - 1);
    addr.sun_path[sizeof(addr.sun_path) - 1] = '\0';  // Ensure null termination
    
    if (bind(server_fd_, (struct sockaddr*)&addr, sizeof(addr)) == -1) {
        LOG_ERROR("IPCServer", "Failed to bind socket: " + std::string(strerror(errno)));
        close(server_fd_);
        server_fd_ = -1;
        return false;
    }
     
     // Listen
     if (listen(server_fd_, SOCKET_BACKLOG) == -1) {
         LOG_ERROR("IPCServer", "Failed to listen: " + std::string(strerror(errno)));
         close(server_fd_);
         server_fd_ = -1;
         return false;
     }
     
     return setup_permissions();
 }
 
bool IPCServer::setup_permissions() {
    // Set socket permissions to 0666 (world read/write)
    // This is safe for Unix domain sockets as they are local-only (not network accessible).
    // The socket directory (/run/cortex/) provides additional access control if needed.
    if (chmod(socket_path_.c_str(), 0666) == -1) {
        LOG_WARN("IPCServer", "Failed to set socket permissions: " + std::string(strerror(errno)));
        // Continue anyway
    }
    return true;
}
 
 void IPCServer::cleanup_socket() {
     std::lock_guard<std::mutex> lock(server_fd_mutex_);
     if (server_fd_ != -1) {
         close(server_fd_);
         server_fd_ = -1;
     }
     
     if (std::filesystem::exists(socket_path_)) {
         std::filesystem::remove(socket_path_);
     }
 }
 
 void IPCServer::accept_loop() {
     LOG_DEBUG("IPCServer", "Accept loop started");
     
     while (running_) {
         int fd_to_accept = -1;
         {
             std::lock_guard<std::mutex> lock(server_fd_mutex_);
             fd_to_accept = server_fd_;
         }
         
         if (fd_to_accept == -1) {
             // Socket not ready yet or closed
             std::this_thread::sleep_for(std::chrono::milliseconds(10));
             continue;
         }
         
         int client_fd = accept(fd_to_accept, nullptr, nullptr);
         
         if (client_fd == -1) {
             if (running_) {
                 LOG_ERROR("IPCServer", "Accept failed: " + std::string(strerror(errno)));
             }
             continue;
         }
         
         // Set socket timeout
         struct timeval timeout;
         timeout.tv_sec = SOCKET_TIMEOUT_MS / 1000;
         timeout.tv_usec = (SOCKET_TIMEOUT_MS % 1000) * 1000;
         setsockopt(client_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
         setsockopt(client_fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
         
         // Handle client (could be async in future)
         handle_client(client_fd);
     }
     
     LOG_DEBUG("IPCServer", "Accept loop ended");
 }
 
 void IPCServer::handle_client(int client_fd) {
     {
         std::lock_guard<std::mutex> lock(connections_mutex_);
         active_connections_++;
         connections_served_++;
     }
     
     try {
         // Read request - use heap allocation for large buffer to avoid stack overflow
         // if we ever move to threaded handling
         std::vector<char> buffer(MAX_MESSAGE_SIZE);
         ssize_t bytes = recv(client_fd, buffer.data(), buffer.size() - 1, 0);
         
         if (bytes <= 0) {
             LOG_DEBUG("IPCServer", "Client disconnected without data");
             close(client_fd);
             {
                 std::lock_guard<std::mutex> lock(connections_mutex_);
                 active_connections_--;
             }
             connections_cv_.notify_all();
             return;
         }
         
        buffer[bytes] = '\0';
        std::string raw_request(buffer.data());
        LOG_DEBUG("IPCServer", "Received request (" + std::to_string(bytes) + " bytes)");
         
         // Check rate limit
         if (!rate_limiter_.allow()) {
             LOG_WARN("IPCServer", "Rate limit exceeded");
             auto resp = Response::err("Rate limit exceeded", ErrorCodes::RATE_LIMITED);
             std::string response_str = resp.to_json();
             send(client_fd, response_str.c_str(), response_str.length(), 0);
             close(client_fd);
             {
                 std::lock_guard<std::mutex> lock(connections_mutex_);
                 active_connections_--;
             }
             connections_cv_.notify_all();
             return;
         }
         
         // Parse request
         auto request = Request::parse(raw_request);
         Response response;
         
         if (!request) {
             response = Response::err("Invalid request format", ErrorCodes::PARSE_ERROR);
         } else {
             response = dispatch(*request);
         }
         
        // Send response
        std::string response_str = response.to_json();
        LOG_DEBUG("IPCServer", "Sending response (" + std::to_string(response_str.length()) + " bytes)");
         
         if (send(client_fd, response_str.c_str(), response_str.length(), 0) == -1) {
             LOG_ERROR("IPCServer", "Failed to send response: " + std::string(strerror(errno)));
         }
         
     } catch (const std::exception& e) {
         LOG_ERROR("IPCServer", "Exception handling client: " + std::string(e.what()));
         auto resp = Response::err(e.what(), ErrorCodes::INTERNAL_ERROR);
         std::string response_str = resp.to_json();
         send(client_fd, response_str.c_str(), response_str.length(), 0);
     }
     
     close(client_fd);
     {
         std::lock_guard<std::mutex> lock(connections_mutex_);
         active_connections_--;
     }
     connections_cv_.notify_all();
 }
 
Response IPCServer::dispatch(const Request& request) {
    RequestHandler handler;
    {
        std::shared_lock<std::shared_mutex> lock(handlers_mutex_);  // Shared lock for read
        
        auto it = handlers_.find(request.method);
        if (it == handlers_.end()) {
            LOG_WARN("IPCServer", "Unknown method: " + request.method);
            return Response::err("Method not found: " + request.method, ErrorCodes::METHOD_NOT_FOUND);
        }
        
        // Copy handler to execute outside the lock
        handler = it->second;
    }
     
    // Execute handler without holding the mutex to prevent deadlock
    // if handler calls back into server (e.g., registering another handler)
    LOG_DEBUG("IPCServer", "Handler found, invoking: " + request.method);
    try {
        Response resp = handler(request);
        LOG_DEBUG("IPCServer", "Handler completed: " + request.method);
        return resp;
     } catch (const std::exception& e) {
         LOG_ERROR("IPCServer", "Handler error for " + request.method + ": " + e.what());
         return Response::err(e.what(), ErrorCodes::INTERNAL_ERROR);
     }
 }
 
 } // namespace cortexd
 