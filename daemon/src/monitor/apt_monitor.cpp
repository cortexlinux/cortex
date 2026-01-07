/**
 * @file apt_monitor.cpp
 * @brief APT package monitoring implementation
 */

#include "cortexd/monitor/apt_monitor.h"
#include "cortexd/logger.h"
#include <array>
#include <memory>
#include <sstream>
#include <regex>
#include <cstdio>

namespace cortexd {

std::vector<PackageUpdate> AptMonitor::check_updates() {
    std::lock_guard<std::mutex> lock(mutex_);
    
    LOG_DEBUG("AptMonitor", "Checking for package updates...");
    
    // Run apt list --upgradable
    std::string output = run_command("apt list --upgradable 2>/dev/null");
    
    cached_updates_ = parse_apt_output(output);
    last_check_ = std::chrono::system_clock::now();
    
    // Count security updates inline (avoid calling security_count() which would deadlock)
    int sec_count = 0;
    for (const auto& update : cached_updates_) {
        if (update.is_security) {
            sec_count++;
        }
    }
    
    LOG_INFO("AptMonitor", "Found " + std::to_string(cached_updates_.size()) + 
             " updates (" + std::to_string(sec_count) + " security)");
    
    return cached_updates_;
}

std::vector<PackageUpdate> AptMonitor::get_cached_updates() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return cached_updates_;
}

bool AptMonitor::has_pending_updates() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return !cached_updates_.empty();
}

int AptMonitor::pending_count() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return static_cast<int>(cached_updates_.size());
}

int AptMonitor::security_count() const {
    std::lock_guard<std::mutex> lock(mutex_);
    int count = 0;
    for (const auto& update : cached_updates_) {
        if (update.is_security) {
            count++;
        }
    }
    return count;
}

std::chrono::system_clock::time_point AptMonitor::last_check_time() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return last_check_;
}

std::vector<PackageUpdate> AptMonitor::parse_apt_output(const std::string& output) {
    std::vector<PackageUpdate> updates;
    
    // apt list --upgradable output format:
    // package/source version [upgradable from: old_version]
    // Example: vim/focal-updates 2:8.2.123-1ubuntu1 amd64 [upgradable from: 2:8.2.100-1]
    
    std::regex pattern(R"(^([^/]+)/([^\s]+)\s+([^\s]+)\s+[^\[]*\[upgradable from:\s+([^\]]+)\])");
    
    std::istringstream stream(output);
    std::string line;
    
    while (std::getline(stream, line)) {
        // Skip header line "Listing..."
        if (line.find("Listing") != std::string::npos) {
            continue;
        }
        
        std::smatch match;
        if (std::regex_search(line, match, pattern)) {
            PackageUpdate update;
            update.name = match[1].str();
            update.source = match[2].str();
            update.available_version = match[3].str();
            update.current_version = match[4].str();
            
            // Check if it's a security update
            update.is_security = (update.source.find("security") != std::string::npos);
            
            updates.push_back(update);
        }
    }
    
    return updates;
}

std::string AptMonitor::run_command(const std::string& cmd) {
    std::array<char, 4096> buffer;
    std::string result;
    
    // Use lambda deleter to avoid warning about function pointer attributes
    auto pipe_deleter = [](FILE* f) { if (f) pclose(f); };
    std::unique_ptr<FILE, decltype(pipe_deleter)> pipe(
        popen(cmd.c_str(), "r"), pipe_deleter);
    
    if (!pipe) {
        LOG_ERROR("AptMonitor", "Failed to run command: " + cmd);
        return "";
    }
    
    while (fgets(buffer.data(), buffer.size(), pipe.get()) != nullptr) {
        result += buffer.data();
    }
    
    return result;
}

} // namespace cortexd

