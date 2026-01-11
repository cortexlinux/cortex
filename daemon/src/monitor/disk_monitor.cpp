/**
 * @file disk_monitor.cpp
 * @brief Disk monitoring implementation
 */

#include "cortexd/monitor/disk_monitor.h"
#include "cortexd/logger.h"
#include <fstream>
#include <sstream>
#include <sys/statvfs.h>

namespace cortexd {

DiskStats DiskMonitor::get_root_stats() const {
    DiskStats stats;
    stats.mount_point = "/";
    stats.device = "rootfs";
    stats.filesystem = "ext4";  // Assume ext4
    
    try {
        struct statvfs stat;
        if (statvfs("/", &stat) == 0) {
            stats.total_bytes = static_cast<uint64_t>(stat.f_blocks) * stat.f_frsize;
            stats.available_bytes = static_cast<uint64_t>(stat.f_bavail) * stat.f_frsize;
            stats.used_bytes = stats.total_bytes - 
                              (static_cast<uint64_t>(stat.f_bfree) * stat.f_frsize);
        }
    } catch (const std::exception& e) {
        LOG_ERROR("DiskMonitor", "Error getting root stats: " + std::string(e.what()));
    }
    
    return stats;
}

std::vector<DiskStats> DiskMonitor::get_all_stats() const {
    std::vector<DiskStats> all_stats;
    
    try {
        std::ifstream mounts("/proc/mounts");
        if (!mounts.is_open()) {
            LOG_ERROR("DiskMonitor", "Cannot open /proc/mounts");
            return all_stats;
        }
        
        std::string line;
        while (std::getline(mounts, line)) {
            std::istringstream iss(line);
            std::string device, mount_point, filesystem;
            iss >> device >> mount_point >> filesystem;
            
            // Skip virtual filesystems
            if (filesystem == "proc" || filesystem == "sysfs" || 
                filesystem == "devtmpfs" || filesystem == "tmpfs" ||
                filesystem == "cgroup" || filesystem == "cgroup2" ||
                filesystem == "securityfs" || filesystem == "pstore" ||
                filesystem == "debugfs" || filesystem == "configfs" ||
                filesystem == "fusectl" || filesystem == "hugetlbfs" ||
                filesystem == "mqueue" || filesystem == "binfmt_misc") {
                continue;
            }
            
            // Skip snap/loop mounts
            if (device.find("/dev/loop") == 0) {
                continue;
            }
            
            DiskStats stats;
            stats.device = device;
            stats.mount_point = mount_point;
            stats.filesystem = filesystem;
            
            struct statvfs stat;
            if (statvfs(mount_point.c_str(), &stat) == 0) {
                stats.total_bytes = static_cast<uint64_t>(stat.f_blocks) * stat.f_frsize;
                stats.available_bytes = static_cast<uint64_t>(stat.f_bavail) * stat.f_frsize;
                stats.used_bytes = stats.total_bytes - 
                                  (static_cast<uint64_t>(stat.f_bfree) * stat.f_frsize);
                
                // Only add if has meaningful size
                if (stats.total_bytes > 0) {
                    all_stats.push_back(stats);
                }
            }
        }
        
    } catch (const std::exception& e) {
        LOG_ERROR("DiskMonitor", "Error getting disk stats: " + std::string(e.what()));
    }
    
    return all_stats;
}

double DiskMonitor::get_usage_percent() const {
    return get_root_stats().usage_percent();
}

bool DiskMonitor::exceeds_threshold(double threshold) const {
    return get_usage_percent() > (threshold * 100.0);
}

} // namespace cortexd

