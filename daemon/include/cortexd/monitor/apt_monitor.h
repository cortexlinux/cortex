/**
 * @file apt_monitor.h
 * @brief APT package monitoring
 */

#pragma once

#include <string>
#include <vector>
#include <chrono>
#include <mutex>

namespace cortexd {

/**
 * @brief Information about a package update
 */
struct PackageUpdate {
    std::string name;
    std::string current_version;
    std::string available_version;
    std::string source;       // e.g., "focal-updates", "focal-security"
    bool is_security = false;
    
    std::string to_string() const {
        return name + " " + current_version + " -> " + available_version;
    }
};

/**
 * @brief APT package monitor
 */
class AptMonitor {
public:
    AptMonitor() = default;
    
    /**
     * @brief Check for available updates
     * @return List of available updates
     * 
     * Note: This may take several seconds as it runs apt commands.
     */
    std::vector<PackageUpdate> check_updates();
    
    /**
     * @brief Get cached list of updates
     */
    std::vector<PackageUpdate> get_cached_updates() const;
    
    /**
     * @brief Check if there are pending updates (cached)
     */
    bool has_pending_updates() const;
    
    /**
     * @brief Get count of pending updates
     */
    int pending_count() const;
    
    /**
     * @brief Get count of security updates
     */
    int security_count() const;
    
    /**
     * @brief Get time of last check
     */
    std::chrono::system_clock::time_point last_check_time() const;
    
private:
    mutable std::mutex mutex_;
    std::vector<PackageUpdate> cached_updates_;
    std::chrono::system_clock::time_point last_check_;
    
    /**
     * @brief Parse output from apt list --upgradable
     */
    std::vector<PackageUpdate> parse_apt_output(const std::string& output);
    
    /**
     * @brief Run command and get output
     */
    std::string run_command(const std::string& cmd);
};

} // namespace cortexd

