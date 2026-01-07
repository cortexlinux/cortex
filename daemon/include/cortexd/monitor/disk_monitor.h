/**
 * @file disk_monitor.h
 * @brief Disk usage monitoring
 */

#pragma once

#include <string>
#include <vector>
#include <cstdint>

namespace cortexd {

/**
 * @brief Disk statistics for a mount point
 */
struct DiskStats {
    std::string mount_point;
    std::string device;
    std::string filesystem;
    uint64_t total_bytes = 0;
    uint64_t available_bytes = 0;
    uint64_t used_bytes = 0;
    
    double usage_percent() const {
        if (total_bytes == 0) return 0.0;
        return static_cast<double>(used_bytes) / total_bytes * 100.0;
    }
    
    double total_gb() const { return total_bytes / (1024.0 * 1024.0 * 1024.0); }
    double used_gb() const { return used_bytes / (1024.0 * 1024.0 * 1024.0); }
    double available_gb() const { return available_bytes / (1024.0 * 1024.0 * 1024.0); }
};

/**
 * @brief Disk usage monitor
 */
class DiskMonitor {
public:
    DiskMonitor() = default;
    
    /**
     * @brief Get disk stats for root filesystem
     */
    DiskStats get_root_stats() const;
    
    /**
     * @brief Get disk stats for all mounted filesystems
     */
    std::vector<DiskStats> get_all_stats() const;
    
    /**
     * @brief Get disk usage percentage for root
     */
    double get_usage_percent() const;
    
    /**
     * @brief Check if disk usage exceeds threshold
     * @param threshold Threshold percentage (0.0 - 1.0)
     */
    bool exceeds_threshold(double threshold) const;
};

} // namespace cortexd

