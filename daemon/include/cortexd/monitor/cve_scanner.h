/**
 * @file cve_scanner.h
 * @brief CVE vulnerability scanning
 */

#pragma once

#include "cortexd/common.h"
#include <string>
#include <vector>
#include <chrono>
#include <mutex>
#include <optional>

namespace cortexd {

/**
 * @brief CVE severity level
 */
enum class CVESeverity {
    LOW,
    MEDIUM,
    HIGH,
    CRITICAL,
    UNKNOWN
};

/**
 * @brief CVE scan result
 */
struct CVEResult {
    std::string cve_id;           // e.g., "CVE-2024-1234"
    std::string package_name;
    std::string installed_version;
    std::string fixed_version;    // Empty if not fixed yet
    CVESeverity severity = CVESeverity::UNKNOWN;
    std::string description;
    std::string url;
    
    json to_json() const {
        const char* sev_str;
        switch (severity) {
            case CVESeverity::LOW: sev_str = "low"; break;
            case CVESeverity::MEDIUM: sev_str = "medium"; break;
            case CVESeverity::HIGH: sev_str = "high"; break;
            case CVESeverity::CRITICAL: sev_str = "critical"; break;
            default: sev_str = "unknown"; break;
        }
        
        return {
            {"cve_id", cve_id},
            {"package_name", package_name},
            {"installed_version", installed_version},
            {"fixed_version", fixed_version},
            {"severity", sev_str},
            {"description", description},
            {"url", url}
        };
    }
};

/**
 * @brief CVE vulnerability scanner
 */
class CVEScanner {
public:
    CVEScanner() = default;
    
    /**
     * @brief Run a full CVE scan
     * @return List of found vulnerabilities
     * 
     * This may take several seconds as it runs system commands.
     */
    std::vector<CVEResult> scan();
    
    /**
     * @brief Get cached scan results
     */
    std::vector<CVEResult> get_cached() const;
    
    /**
     * @brief Check if there are known vulnerabilities
     */
    bool has_vulnerabilities() const;
    
    /**
     * @brief Get count of vulnerabilities by severity
     */
    int count_by_severity(CVESeverity severity) const;
    
    /**
     * @brief Check specific package for CVEs
     */
    std::optional<CVEResult> check_package(const std::string& package_name);
    
    /**
     * @brief Get time of last scan
     */
    std::chrono::system_clock::time_point last_scan_time() const;
    
private:
    mutable std::mutex mutex_;
    std::vector<CVEResult> cached_results_;
    std::chrono::system_clock::time_point last_scan_;
    
    /**
     * @brief Scan using ubuntu-security-status
     */
    std::vector<CVEResult> scan_ubuntu_security();
    
    /**
     * @brief Scan using debsecan (fallback)
     */
    std::vector<CVEResult> scan_debsecan();
    
    /**
     * @brief Run command and get output
     */
    std::string run_command(const std::string& cmd);
    
    /**
     * @brief Check if command exists
     */
    bool command_exists(const std::string& cmd);
};

} // namespace cortexd

