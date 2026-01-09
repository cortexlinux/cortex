/**
 * @file cve_scanner.cpp
 * @brief CVE vulnerability scanner implementation
 */

#include "cortexd/monitor/cve_scanner.h"
#include "cortexd/logger.h"
#include <array>
#include <memory>
#include <sstream>
#include <regex>
#include <cstdio>
#include <unistd.h>
#include <sys/wait.h>
#include <signal.h>
#include <cstring>
#include <fcntl.h>

namespace cortexd {

std::vector<CVEResult> CVEScanner::scan() {
    std::lock_guard<std::mutex> lock(mutex_);
    
    LOG_INFO("CVEScanner", "Starting CVE scan...");
    
    // Try ubuntu-security-status first
    if (command_exists("ubuntu-security-status")) {
        cached_results_ = scan_ubuntu_security();
    }
    // Fallback to debsecan
    else if (command_exists("debsecan")) {
        cached_results_ = scan_debsecan();
    }
    // No scanner available
    else {
        LOG_WARN("CVEScanner", "No CVE scanner available (install ubuntu-security-status or debsecan)");
        cached_results_.clear();
    }
    
    last_scan_ = std::chrono::system_clock::now();
    
    LOG_INFO("CVEScanner", "Found " + std::to_string(cached_results_.size()) + " potential vulnerabilities");
    return cached_results_;
}

std::vector<CVEResult> CVEScanner::get_cached() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return cached_results_;
}

bool CVEScanner::has_vulnerabilities() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return !cached_results_.empty();
}

int CVEScanner::count_by_severity(CVESeverity severity) const {
    std::lock_guard<std::mutex> lock(mutex_);
    int count = 0;
    for (const auto& cve : cached_results_) {
        if (cve.severity == severity) {
            count++;
        }
    }
    return count;
}

std::optional<CVEResult> CVEScanner::check_package(const std::string& package_name) {
    std::lock_guard<std::mutex> lock(mutex_);
    
    for (const auto& cve : cached_results_) {
        if (cve.package_name == package_name) {
            return cve;
        }
    }
    
    return std::nullopt;
}

std::chrono::system_clock::time_point CVEScanner::last_scan_time() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return last_scan_;
}

std::vector<CVEResult> CVEScanner::scan_ubuntu_security() {
    std::vector<CVEResult> results;
    
    std::string output = run_command("ubuntu-security-status --thirdparty 2>/dev/null");
    
    // Parse ubuntu-security-status output
    // Look for packages that need attention
    std::istringstream stream(output);
    std::string line;
    
    // Regex to match CVE identifiers
    std::regex cve_regex(R"(CVE-\d{4}-\d+)");
    
    while (std::getline(stream, line)) {
        // Look for lines mentioning CVEs
        std::smatch match;
        if (std::regex_search(line, match, cve_regex)) {
            CVEResult result;
            result.cve_id = match[0].str();
            
            // Try to extract package name from line
            // Format varies, but package is often first word or after specific patterns
            std::istringstream line_stream(line);
            std::string word;
            if (line_stream >> word) {
                if (word.find("CVE-") != 0) {
                    result.package_name = word;
                }
            }
            
            // Determine severity from context
            if (line.find("critical") != std::string::npos || 
                line.find("CRITICAL") != std::string::npos) {
                result.severity = CVESeverity::CRITICAL;
            } else if (line.find("high") != std::string::npos ||
                       line.find("HIGH") != std::string::npos) {
                result.severity = CVESeverity::HIGH;
            } else if (line.find("medium") != std::string::npos ||
                       line.find("MEDIUM") != std::string::npos) {
                result.severity = CVESeverity::MEDIUM;
            } else if (line.find("low") != std::string::npos ||
                       line.find("LOW") != std::string::npos) {
                result.severity = CVESeverity::LOW;
            }
            
            result.url = "https://ubuntu.com/security/" + result.cve_id;
            results.push_back(result);
        }
    }
    
    return results;
}

std::vector<CVEResult> CVEScanner::scan_debsecan() {
    std::vector<CVEResult> results;
    
    std::string output = run_command("debsecan --format detail 2>/dev/null");
    
    // Parse debsecan output
    // Format: CVE-YYYY-NNNN package version severity description
    
    std::istringstream stream(output);
    std::string line;
    
    while (std::getline(stream, line)) {
        if (line.find("CVE-") == 0) {
            CVEResult result;
            
            std::istringstream line_stream(line);
            std::string severity_str;
            
            line_stream >> result.cve_id >> result.package_name 
                        >> result.installed_version >> severity_str;
            
            // Get rest as description
            std::getline(line_stream, result.description);
            if (!result.description.empty() && result.description[0] == ' ') {
                result.description = result.description.substr(1);
            }
            
            // Parse severity
            if (severity_str == "high" || severity_str == "urgent") {
                result.severity = CVESeverity::HIGH;
            } else if (severity_str == "medium") {
                result.severity = CVESeverity::MEDIUM;
            } else if (severity_str == "low") {
                result.severity = CVESeverity::LOW;
            }
            
            result.url = "https://security-tracker.debian.org/tracker/" + result.cve_id;
            results.push_back(result);
        }
    }
    
    return results;
}

std::string CVEScanner::run_command(const std::string& cmd) {
    std::array<char, 4096> buffer;
    std::string result;
    
    // Use lambda deleter to avoid warning about function pointer attributes
    auto pipe_deleter = [](FILE* f) { if (f) pclose(f); };
    std::unique_ptr<FILE, decltype(pipe_deleter)> pipe(
        popen(cmd.c_str(), "r"), pipe_deleter);
    
    if (!pipe) {
        LOG_ERROR("CVEScanner", "Failed to run command: " + cmd);
        return "";
    }
    
    while (fgets(buffer.data(), buffer.size(), pipe.get()) != nullptr) {
        result += buffer.data();
    }
    
    return result;
}

bool CVEScanner::command_exists(const std::string& cmd) {
    // Avoid shell injection by using fork/exec instead of system()
    // The command name is passed as a separate argument to "which"
    
    pid_t pid = fork();
    if (pid == -1) {
        LOG_ERROR("CVEScanner", "fork() failed: " + std::string(strerror(errno)));
        return false;
    }
    
    if (pid == 0) {
        // Child process
        // Redirect stdout/stderr to /dev/null
        int devnull = open("/dev/null", O_WRONLY);
        if (devnull != -1) {
            dup2(devnull, STDOUT_FILENO);
            dup2(devnull, STDERR_FILENO);
            close(devnull);
        }
        
        // Execute "which <cmd>" - cmd is passed as separate argument (no shell)
        const char* args[] = {"which", cmd.c_str(), nullptr};
        execvp("which", const_cast<char* const*>(args));
        
        // If execvp returns, it failed
        _exit(127);
    }
    
    // Parent process - wait for child with timeout
    constexpr int TIMEOUT_SECONDS = 5;
    int status = 0;
    time_t start_time = time(nullptr);
    
    while (true) {
        pid_t result = waitpid(pid, &status, WNOHANG);
        
        if (result == pid) {
            // Child exited
            if (WIFEXITED(status)) {
                return WEXITSTATUS(status) == 0;
            }
            return false;  // Child terminated abnormally
        }
        
        if (result == -1) {
            LOG_ERROR("CVEScanner", "waitpid() failed: " + std::string(strerror(errno)));
            return false;
        }
        
        // Check timeout
        if (time(nullptr) - start_time >= TIMEOUT_SECONDS) {
            LOG_WARN("CVEScanner", "command_exists timeout for: " + cmd);
            kill(pid, SIGKILL);
            waitpid(pid, &status, 0);  // Reap the killed child
            return false;
        }
        
        // Brief sleep to avoid busy-waiting
        usleep(10000);  // 10ms
    }
}

} // namespace cortexd

