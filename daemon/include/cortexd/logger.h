/**
 * @file logger.h
 * @brief Structured logging to journald with fallback to stderr
 */

#pragma once

#include <string>
#include <mutex>

// Save syslog macros before including syslog.h
#include <syslog.h>

// Save the syslog priority values before we might redefine macros
namespace cortexd {
namespace internal {
    constexpr int SYSLOG_DEBUG = LOG_DEBUG;
    constexpr int SYSLOG_INFO = LOG_INFO;
    constexpr int SYSLOG_WARNING = LOG_WARNING;
    constexpr int SYSLOG_ERR = LOG_ERR;
    constexpr int SYSLOG_CRIT = LOG_CRIT;
}
}

// Undefine syslog macros that conflict with our convenience macros
#ifdef LOG_DEBUG
#undef LOG_DEBUG
#endif
#ifdef LOG_INFO
#undef LOG_INFO
#endif

namespace cortexd {

/**
 * @brief Log levels matching syslog priorities
 */
enum class LogLevel {
    DEBUG = internal::SYSLOG_DEBUG,
    INFO = internal::SYSLOG_INFO,
    WARN = internal::SYSLOG_WARNING,
    ERROR = internal::SYSLOG_ERR,
    CRITICAL = internal::SYSLOG_CRIT
};

/**
 * @brief Thread-safe logger with journald support
 */
class Logger {
public:
    /**
     * @brief Initialize the logging system
     * @param min_level Minimum log level to output
     * @param use_journald Whether to use journald (true) or stderr (false)
     */
    static void init(LogLevel min_level = LogLevel::INFO, bool use_journald = true);
    
    /**
     * @brief Shutdown logging system
     */
    static void shutdown();
    
    /**
     * @brief Set minimum log level
     */
    static void set_level(LogLevel level);
    
    /**
     * @brief Get current log level
     */
    static LogLevel get_level();
    
    /**
     * @brief Log a debug message
     */
    static void debug(const std::string& component, const std::string& message);
    
    /**
     * @brief Log an info message
     */
    static void info(const std::string& component, const std::string& message);
    
    /**
     * @brief Log a warning message
     */
    static void warn(const std::string& component, const std::string& message);
    
    /**
     * @brief Log an error message
     */
    static void error(const std::string& component, const std::string& message);
    
    /**
     * @brief Log a critical message
     */
    static void critical(const std::string& component, const std::string& message);
    
    /**
     * @brief Generic log method
     */
    static void log(LogLevel level, const std::string& component, const std::string& message);

private:
    static LogLevel min_level_;
    static bool use_journald_;
    static std::mutex mutex_;
    static bool initialized_;
    
    static int level_to_priority(LogLevel level);
    static const char* level_to_string(LogLevel level);
    static void log_to_journald(LogLevel level, const std::string& component, const std::string& message);
    static void log_to_stderr(LogLevel level, const std::string& component, const std::string& message);
};

// Convenience macros (prefixed with CORTEX_ to avoid conflicts)
#define CORTEX_LOG_DEBUG(comp, msg) cortexd::Logger::debug(comp, msg)
#define CORTEX_LOG_INFO(comp, msg) cortexd::Logger::info(comp, msg)
#define CORTEX_LOG_WARN(comp, msg) cortexd::Logger::warn(comp, msg)
#define CORTEX_LOG_ERROR(comp, msg) cortexd::Logger::error(comp, msg)
#define CORTEX_LOG_CRITICAL(comp, msg) cortexd::Logger::critical(comp, msg)

// Shorter aliases
#define LOG_DEBUG(comp, msg) cortexd::Logger::debug(comp, msg)
#define LOG_INFO(comp, msg) cortexd::Logger::info(comp, msg)
#define LOG_WARN(comp, msg) cortexd::Logger::warn(comp, msg)
#define LOG_ERROR(comp, msg) cortexd::Logger::error(comp, msg)
#define LOG_CRITICAL(comp, msg) cortexd::Logger::critical(comp, msg)

} // namespace cortexd
