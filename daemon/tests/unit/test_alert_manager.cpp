/**
 * @file test_alert_manager.cpp
 * @brief Unit tests for AlertManager
 */

#include <gtest/gtest.h>
#include "cortexd/alerts/alert_manager.h"
#include <filesystem>
#include <fstream>
#include <cstdio>
#include <thread>
#include <vector>
#include <atomic>
#include <chrono>
#include <unordered_set>

using namespace cortexd;

class AlertManagerTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Create temporary database path
        test_db_path_ = "/tmp/test_alerts_" + std::to_string(getpid()) + ".db";
        
        // Remove test database if it exists
        if (std::filesystem::exists(test_db_path_)) {
            std::filesystem::remove(test_db_path_);
        }
        
        alert_manager_ = std::make_unique<AlertManager>(test_db_path_);
        ASSERT_TRUE(alert_manager_->initialize());
    }
    
    void TearDown() override {
        alert_manager_.reset();
        
        // Clean up test database
        if (std::filesystem::exists(test_db_path_)) {
            std::filesystem::remove(test_db_path_);
        }
    }
    
    std::string test_db_path_;
    std::unique_ptr<AlertManager> alert_manager_;
};

TEST_F(AlertManagerTest, CreateAlert) {
    Alert alert;
    alert.severity = AlertSeverity::WARNING;
    alert.category = AlertCategory::CPU;
    alert.source = "test_source";
    alert.message = "Test alert message";
    alert.description = "Test alert description";
    alert.status = AlertStatus::ACTIVE;
    alert.timestamp = std::chrono::system_clock::now();
    
    auto created = alert_manager_->create_alert(alert);
    ASSERT_TRUE(created.has_value());
    ASSERT_FALSE(created->uuid.empty());
    ASSERT_EQ(created->message, "Test alert message");
}

TEST_F(AlertManagerTest, GetAlert) {
    Alert alert;
    alert.severity = AlertSeverity::ERROR;
    alert.category = AlertCategory::MEMORY;
    alert.source = "test_source";
    alert.message = "Test alert";
    alert.status = AlertStatus::ACTIVE;
    
    auto created = alert_manager_->create_alert(alert);
    ASSERT_TRUE(created.has_value());
    
    auto retrieved = alert_manager_->get_alert(created->uuid);
    ASSERT_TRUE(retrieved.has_value());
    ASSERT_EQ(retrieved->uuid, created->uuid);
    ASSERT_EQ(retrieved->message, "Test alert");
    ASSERT_EQ(retrieved->severity, AlertSeverity::ERROR);
}

TEST_F(AlertManagerTest, GetAlertsFilterBySeverity) {
    // Create alerts with different severities
    Alert alert1;
    alert1.severity = AlertSeverity::WARNING;
    alert1.category = AlertCategory::CPU;
    alert1.source = "test";
    alert1.message = "Warning alert";
    alert1.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert1);
    
    Alert alert2;
    alert2.severity = AlertSeverity::ERROR;
    alert2.category = AlertCategory::MEMORY;
    alert2.source = "test";
    alert2.message = "Error alert";
    alert2.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert2);
    
    AlertFilter filter;
    filter.severity = AlertSeverity::WARNING;
    auto alerts = alert_manager_->get_alerts(filter);
    
    ASSERT_EQ(alerts.size(), 1);
    ASSERT_EQ(alerts[0].severity, AlertSeverity::WARNING);
}

TEST_F(AlertManagerTest, GetAlertsFilterByCategory) {
    Alert alert1;
    alert1.severity = AlertSeverity::INFO;
    alert1.category = AlertCategory::CPU;
    alert1.source = "test";
    alert1.message = "CPU alert";
    alert1.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert1);
    
    Alert alert2;
    alert2.severity = AlertSeverity::INFO;
    alert2.category = AlertCategory::DISK;
    alert2.source = "test";
    alert2.message = "Disk alert";
    alert2.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert2);
    
    AlertFilter filter;
    filter.category = AlertCategory::CPU;
    auto alerts = alert_manager_->get_alerts(filter);
    
    ASSERT_EQ(alerts.size(), 1);
    ASSERT_EQ(alerts[0].category, AlertCategory::CPU);
}

TEST_F(AlertManagerTest, AcknowledgeAlert) {
    Alert alert;
    alert.severity = AlertSeverity::WARNING;
    alert.category = AlertCategory::CPU;
    alert.source = "test";
    alert.message = "Test alert";
    alert.status = AlertStatus::ACTIVE;
    
    auto created = alert_manager_->create_alert(alert);
    ASSERT_TRUE(created.has_value());
    
    bool acknowledged = alert_manager_->acknowledge_alert(created->uuid);
    ASSERT_TRUE(acknowledged);
    
    auto retrieved = alert_manager_->get_alert(created->uuid);
    ASSERT_TRUE(retrieved.has_value());
    ASSERT_EQ(retrieved->status, AlertStatus::ACKNOWLEDGED);
    ASSERT_TRUE(retrieved->acknowledged_at.has_value());
}

TEST_F(AlertManagerTest, AcknowledgeAll) {
    // Create multiple active alerts
    for (int i = 0; i < 3; ++i) {
        Alert alert;
        alert.severity = AlertSeverity::WARNING;
        alert.category = AlertCategory::CPU;
        alert.source = "test";
        alert.message = "Alert " + std::to_string(i);
        alert.status = AlertStatus::ACTIVE;
        alert_manager_->create_alert(alert);
    }
    
    size_t count = alert_manager_->acknowledge_all();
    ASSERT_EQ(count, 3);
    
    AlertFilter filter;
    filter.status = AlertStatus::ACKNOWLEDGED;
    auto alerts = alert_manager_->get_alerts(filter);
    ASSERT_EQ(alerts.size(), 3);
}

TEST_F(AlertManagerTest, DismissAlert) {
    Alert alert;
    alert.severity = AlertSeverity::WARNING;
    alert.category = AlertCategory::CPU;
    alert.source = "test";
    alert.message = "Test alert";
    alert.status = AlertStatus::ACTIVE;
    
    auto created = alert_manager_->create_alert(alert);
    ASSERT_TRUE(created.has_value());
    
    bool dismissed = alert_manager_->dismiss_alert(created->uuid);
    ASSERT_TRUE(dismissed);
    
    auto retrieved = alert_manager_->get_alert(created->uuid);
    ASSERT_TRUE(retrieved.has_value());
    ASSERT_EQ(retrieved->status, AlertStatus::DISMISSED);
    ASSERT_TRUE(retrieved->dismissed_at.has_value());
}

TEST_F(AlertManagerTest, DismissAll) {
    // Create multiple active and acknowledged alerts
    for (int i = 0; i < 3; ++i) {
        Alert alert;
        alert.severity = AlertSeverity::WARNING;
        alert.category = AlertCategory::CPU;
        alert.source = "test";
        alert.message = "Alert " + std::to_string(i);
        alert.status = AlertStatus::ACTIVE;
        alert_manager_->create_alert(alert);
    }
    
    // Acknowledge one alert
    AlertFilter filter;
    filter.status = AlertStatus::ACTIVE;
    auto active_alerts = alert_manager_->get_alerts(filter);
    if (!active_alerts.empty()) {
        alert_manager_->acknowledge_alert(active_alerts[0].uuid);
    }
    
    size_t count = alert_manager_->dismiss_all();
    ASSERT_GE(count, 3);  // Should dismiss all active and acknowledged alerts
    
    AlertFilter dismissed_filter;
    dismissed_filter.status = AlertStatus::DISMISSED;
    auto dismissed_alerts = alert_manager_->get_alerts(dismissed_filter);
    ASSERT_GE(dismissed_alerts.size(), 3);
}

TEST_F(AlertManagerTest, ConcurrentAccess) {
    const int num_threads = 10;
    const int alerts_per_thread = 50;
    std::vector<std::thread> threads;
    std::atomic<int> success_count{0};
    std::atomic<int> read_count{0};
    
    // Concurrent writes
    for (int i = 0; i < num_threads; ++i) {
        threads.emplace_back([this, i, alerts_per_thread, &success_count]() {
            for (int j = 0; j < alerts_per_thread; ++j) {
                Alert alert;
                alert.severity = static_cast<AlertSeverity>(j % 4);
                alert.category = static_cast<AlertCategory>(j % 7);
                alert.source = "thread_" + std::to_string(i);
                alert.message = "Alert " + std::to_string(j);
                alert.status = AlertStatus::ACTIVE;
                
                auto created = alert_manager_->create_alert(alert);
                if (created.has_value()) {
                    success_count.fetch_add(1, std::memory_order_relaxed);
                }
            }
        });
    }
    
    // Concurrent reads
    for (int i = 0; i < num_threads; ++i) {
        threads.emplace_back([this, &read_count]() {
            for (int j = 0; j < 100; ++j) {
                AlertFilter filter;
                auto alerts = alert_manager_->get_alerts(filter);
                read_count.fetch_add(1, std::memory_order_relaxed);
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        });
    }
    
    // Concurrent acknowledge/dismiss operations
    for (int i = 0; i < num_threads / 2; ++i) {
        threads.emplace_back([this]() {
            for (int j = 0; j < 20; ++j) {
                AlertFilter filter;
                filter.status = AlertStatus::ACTIVE;
                auto alerts = alert_manager_->get_alerts(filter);
                if (!alerts.empty()) {
                    alert_manager_->acknowledge_alert(alerts[0].uuid);
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(5));
            }
        });
    }
    
    // Wait for all threads
    for (auto& t : threads) {
        t.join();
    }
    
    // Verify data integrity
    auto all_alerts = alert_manager_->get_alerts(AlertFilter{});
    ASSERT_GT(all_alerts.size(), 0);
    ASSERT_GE(success_count.load(), num_threads * alerts_per_thread * 0.9); // Allow some failures due to duplicates
    ASSERT_GE(read_count.load(), num_threads * 100);
    
    // Verify no duplicate UUIDs
    std::unordered_set<std::string> uuids;
    for (const auto& alert : all_alerts) {
        ASSERT_TRUE(uuids.insert(alert.uuid).second) << "Duplicate UUID found: " << alert.uuid;
    }
}

TEST_F(AlertManagerTest, DatabaseCorruptionRecovery) {
    // Create some alerts first
    for (int i = 0; i < 10; ++i) {
        Alert alert;
        alert.severity = AlertSeverity::WARNING;
        alert.category = AlertCategory::CPU;
        alert.source = "test";
        alert.message = "Alert " + std::to_string(i);
        alert.status = AlertStatus::ACTIVE;
        alert_manager_->create_alert(alert);
    }
    
    // Corrupt the database by writing invalid data
    std::ofstream corrupt_file(test_db_path_, std::ios::binary | std::ios::trunc);
    corrupt_file << "CORRUPTED DATABASE DATA";
    corrupt_file.close();
    
    // Try to create a new AlertManager with the corrupted database
    // SQLite should handle corruption gracefully
    AlertManager corrupted_manager(test_db_path_);
    
    // Initialize should either succeed (SQLite recovers) or fail gracefully
    bool init_result = corrupted_manager.initialize();
    
    if (init_result) {
        // If initialization succeeded, SQLite may have recovered or created a new database
        // Try to create an alert to verify it works
        Alert alert;
        alert.severity = AlertSeverity::INFO;
        alert.category = AlertCategory::SYSTEM;
        alert.source = "recovery_test";
        alert.message = "Recovery test";
        alert.status = AlertStatus::ACTIVE;
        
        auto created = corrupted_manager.create_alert(alert);
        ASSERT_TRUE(created.has_value()) << "AlertManager should be able to create alerts after recovery";
    } else {
        // If initialization failed, that's also acceptable - the corruption was detected
        // The important thing is that it failed gracefully without crashing
        GTEST_LOG_(INFO) << "Database corruption detected and initialization failed gracefully (expected behavior)";
    }
}

TEST_F(AlertManagerTest, StressTestLargeNumberOfAlerts) {
    const int num_alerts = 10000;
    std::vector<std::string> created_uuids;
    created_uuids.reserve(num_alerts);
    
    auto start = std::chrono::steady_clock::now();
    
    // Create a large number of alerts
    for (int i = 0; i < num_alerts; ++i) {
        Alert alert;
        alert.severity = static_cast<AlertSeverity>(i % 4);
        alert.category = static_cast<AlertCategory>(i % 7);
        alert.source = "stress_test";
        alert.message = "Stress test alert " + std::to_string(i);
        alert.description = "Description for alert " + std::to_string(i);
        alert.status = AlertStatus::ACTIVE;
        
        auto created = alert_manager_->create_alert(alert);
        ASSERT_TRUE(created.has_value()) << "Failed to create alert " << i;
        created_uuids.push_back(created->uuid);
    }
    
    auto create_end = std::chrono::steady_clock::now();
    auto create_duration = std::chrono::duration_cast<std::chrono::milliseconds>(create_end - start);
    
    // Verify all alerts were created
    auto all_alerts = alert_manager_->get_alerts(AlertFilter{});
    ASSERT_GE(all_alerts.size(), num_alerts);
    
    // Verify we can retrieve specific alerts
    for (int i = 0; i < std::min(100, num_alerts); ++i) {
        auto retrieved = alert_manager_->get_alert(created_uuids[i]);
        ASSERT_TRUE(retrieved.has_value()) << "Failed to retrieve alert " << i;
        ASSERT_EQ(retrieved->uuid, created_uuids[i]);
    }
    
    // Test filtering with large dataset
    AlertFilter filter;
    filter.severity = AlertSeverity::WARNING;
    auto warning_alerts = alert_manager_->get_alerts(filter);
    ASSERT_GT(warning_alerts.size(), 0);
    
    // Test acknowledge operations on large dataset
    size_t ack_count = alert_manager_->acknowledge_all();
    ASSERT_GT(ack_count, 0);
    
    // Verify counts are correct
    auto counts = alert_manager_->get_alert_counts();
    ASSERT_EQ(counts["total"], 0) << "All alerts should be acknowledged";
    
    auto end = std::chrono::steady_clock::now();
    auto total_duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
    
    GTEST_LOG_(INFO) << "Created " << num_alerts << " alerts in " << create_duration.count() << "ms";
    GTEST_LOG_(INFO) << "Total test duration: " << total_duration.count() << "ms";
    
    // Performance check: should be able to create at least 100 alerts per second
    double alerts_per_second = (num_alerts * 1000.0) / create_duration.count();
    ASSERT_GT(alerts_per_second, 100.0) << "Performance too slow: " << alerts_per_second << " alerts/sec";
}

TEST_F(AlertManagerTest, GetAlertCounts) {
    // Create alerts with different severities
    Alert alert1;
    alert1.severity = AlertSeverity::INFO;
    alert1.category = AlertCategory::CPU;
    alert1.source = "test";
    alert1.message = "Info alert";
    alert1.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert1);
    
    Alert alert2;
    alert2.severity = AlertSeverity::WARNING;
    alert2.category = AlertCategory::MEMORY;
    alert2.source = "test";
    alert2.message = "Warning alert";
    alert2.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert2);
    
    Alert alert3;
    alert3.severity = AlertSeverity::ERROR;
    alert3.category = AlertCategory::DISK;
    alert3.source = "test";
    alert3.message = "Error alert";
    alert3.status = AlertStatus::ACTIVE;
    alert_manager_->create_alert(alert3);
    
    auto counts = alert_manager_->get_alert_counts();
    ASSERT_EQ(counts["info"], 1);
    ASSERT_EQ(counts["warning"], 1);
    ASSERT_EQ(counts["error"], 1);
    ASSERT_EQ(counts["total"], 3);
}

TEST_F(AlertManagerTest, AlertJsonConversion) {
    Alert alert;
    alert.uuid = AlertManager::generate_uuid();
    alert.severity = AlertSeverity::CRITICAL;
    alert.category = AlertCategory::CPU;
    alert.source = "test_source";
    alert.message = "Critical alert";
    alert.description = "Test description";
    alert.status = AlertStatus::ACTIVE;
    alert.timestamp = std::chrono::system_clock::now();
    
    json j = alert.to_json();
    ASSERT_EQ(j["uuid"], alert.uuid);
    ASSERT_EQ(j["severity"], static_cast<int>(AlertSeverity::CRITICAL));
    ASSERT_EQ(j["severity_name"], "critical");
    ASSERT_EQ(j["message"], "Critical alert");
    
    Alert restored = Alert::from_json(j);
    ASSERT_EQ(restored.uuid, alert.uuid);
    ASSERT_EQ(restored.severity, AlertSeverity::CRITICAL);
    ASSERT_EQ(restored.message, "Critical alert");
}

TEST_F(AlertManagerTest, ExcludeDismissedAlerts) {
    Alert alert1;
    alert1.severity = AlertSeverity::WARNING;
    alert1.category = AlertCategory::CPU;
    alert1.source = "test";
    alert1.message = "Active alert";
    alert1.status = AlertStatus::ACTIVE;
    auto created1 = alert_manager_->create_alert(alert1);
    
    Alert alert2;
    alert2.severity = AlertSeverity::WARNING;
    alert2.category = AlertCategory::CPU;
    alert2.source = "test";
    alert2.message = "Dismissed alert";
    alert2.status = AlertStatus::ACTIVE;
    auto created2 = alert_manager_->create_alert(alert2);
    
    alert_manager_->dismiss_alert(created2->uuid);
    
    // Default filter should exclude dismissed
    AlertFilter filter;
    auto alerts = alert_manager_->get_alerts(filter);
    ASSERT_EQ(alerts.size(), 1);
    ASSERT_EQ(alerts[0].uuid, created1->uuid);
}
