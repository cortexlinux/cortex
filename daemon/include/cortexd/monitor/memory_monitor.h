/**
 * @file memory_monitor.h
 * @brief Memory usage monitoring
 */

#pragma once

#include <cstdint>

namespace cortexd {

/**
 * @brief Memory statistics
 */
struct MemoryStats {
    uint64_t total_bytes = 0;
    uint64_t available_bytes = 0;
    uint64_t used_bytes = 0;
    uint64_t buffers_bytes = 0;
    uint64_t cached_bytes = 0;
    uint64_t swap_total_bytes = 0;
    uint64_t swap_used_bytes = 0;
    
    double usage_percent() const {
        if (total_bytes == 0) return 0.0;
        return static_cast<double>(total_bytes - available_bytes) / total_bytes * 100.0;
    }
    
    double total_mb() const { return total_bytes / (1024.0 * 1024.0); }
    double used_mb() const { return (total_bytes - available_bytes) / (1024.0 * 1024.0); }
    double available_mb() const { return available_bytes / (1024.0 * 1024.0); }
};

/**
 * @brief Memory usage monitor
 */
class MemoryMonitor {
public:
    MemoryMonitor() = default;
    
    /**
     * @brief Get current memory statistics
     */
    MemoryStats get_stats() const;
    
    /**
     * @brief Get memory usage percentage
     */
    double get_usage_percent() const;
    
    /**
     * @brief Check if memory usage exceeds threshold
     * @param threshold Threshold percentage (0.0 - 1.0)
     */
    bool exceeds_threshold(double threshold) const;
};

} // namespace cortexd

