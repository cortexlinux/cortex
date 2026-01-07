/**
 * @file memory_monitor.cpp
 * @brief Memory monitoring implementation
 */

#include "cortexd/monitor/memory_monitor.h"
#include "cortexd/logger.h"
#include <fstream>
#include <sstream>
#include <string>

namespace cortexd {

MemoryStats MemoryMonitor::get_stats() const {
    MemoryStats stats;
    
    try {
        std::ifstream meminfo("/proc/meminfo");
        if (!meminfo.is_open()) {
            LOG_ERROR("MemoryMonitor", "Cannot open /proc/meminfo");
            return stats;
        }
        
        std::string line;
        while (std::getline(meminfo, line)) {
            std::istringstream iss(line);
            std::string key;
            uint64_t value;
            std::string unit;
            
            iss >> key >> value >> unit;
            
            // Values are in kB, convert to bytes
            value *= 1024;
            
            if (key == "MemTotal:") {
                stats.total_bytes = value;
            } else if (key == "MemAvailable:") {
                stats.available_bytes = value;
            } else if (key == "Buffers:") {
                stats.buffers_bytes = value;
            } else if (key == "Cached:") {
                stats.cached_bytes = value;
            } else if (key == "SwapTotal:") {
                stats.swap_total_bytes = value;
            } else if (key == "SwapFree:") {
                stats.swap_used_bytes = stats.swap_total_bytes - value;
            }
        }
        
        // Calculate used memory
        stats.used_bytes = stats.total_bytes - stats.available_bytes;
        
    } catch (const std::exception& e) {
        LOG_ERROR("MemoryMonitor", "Error reading memory stats: " + std::string(e.what()));
    }
    
    return stats;
}

double MemoryMonitor::get_usage_percent() const {
    return get_stats().usage_percent();
}

bool MemoryMonitor::exceeds_threshold(double threshold) const {
    return get_usage_percent() > (threshold * 100.0);
}

} // namespace cortexd

