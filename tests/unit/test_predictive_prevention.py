import unittest
from unittest.mock import MagicMock, patch

from cortex.hardware_detection import CPUInfo, MemoryInfo, StorageInfo, SystemInfo
from cortex.installation_history import InstallationRecord, InstallationStatus, InstallationType
from cortex.predictive_prevention import FailurePrediction, PredictiveErrorManager, RiskLevel


class TestPredictiveErrorManager(unittest.TestCase):
    def setUp(self):
        self.manager = PredictiveErrorManager(api_key="fake-key", provider="ollama")

    @patch("cortex.hardware_detection.HardwareDetector.detect")
    @patch("cortex.installation_history.InstallationHistory.get_history")
    @patch("cortex.llm_router.LLMRouter.complete")
    def test_analyze_installation_high_risk(self, mock_llm, mock_history, mock_detect):
        # Setup mock system info (Low RAM, Old Kernel)
        system_info = SystemInfo(
            kernel_version="4.15.0-generic",
            memory=MemoryInfo(total_mb=1024),  # 1GB RAM
            storage=[StorageInfo(mount_point="/", available_gb=1.0, total_gb=100.0)],
        )
        mock_detect.return_value = system_info

        # Mock history (No previous failures)
        mock_history.return_value = []

        # Mock LLM response
        mock_llm.return_value.content = '{"risk_level": "high", "reasons": ["Old kernel", "Low RAM"], "recommendations": ["Upgrade kernel"], "predicted_errors": ["Out of memory"]}'

        prediction = self.manager.analyze_installation("cuda-12.0", ["sudo apt install cuda-12.0"])

        self.assertEqual(
            prediction.risk_level, RiskLevel.CRITICAL
        )  # static check for disk space makes it critical
        self.assertTrue(any("Kernel version" in r for r in prediction.reasons))
        self.assertTrue(any("Low RAM" in r for r in prediction.reasons))

    @patch("cortex.hardware_detection.HardwareDetector.detect")
    @patch("cortex.installation_history.InstallationHistory.get_history")
    def test_static_compatibility_check(self, mock_history, mock_detect):
        system_info = SystemInfo(
            kernel_version="5.15.0",
            memory=MemoryInfo(total_mb=8192),
            storage=[StorageInfo(mount_point="/", available_gb=0.5, total_gb=100.0)],
        )
        mock_detect.return_value = system_info
        mock_history.return_value = []

        prediction = self.manager.analyze_installation("nginx", ["sudo apt install nginx"])

        self.assertEqual(prediction.risk_level, RiskLevel.CRITICAL)
        self.assertTrue(any("disk space" in r.lower() for r in prediction.reasons))

    @patch("cortex.hardware_detection.HardwareDetector.detect")
    @patch("cortex.installation_history.InstallationHistory.get_history")
    def test_history_pattern_failure(self, mock_history, mock_detect):
        system_info = SystemInfo(
            kernel_version="6.0.0",
            memory=MemoryInfo(total_mb=16384),
            storage=[StorageInfo(mount_point="/", available_gb=50.0, total_gb=100.0)],
        )
        mock_detect.return_value = system_info

        # Mock history with some matches and some non-matches
        match_record = InstallationRecord(
            id="1",
            timestamp="now",
            operation_type=InstallationType.INSTALL,
            packages=["docker.io"],
            status=InstallationStatus.FAILED,
            before_snapshot=[],
            after_snapshot=[],
            commands_executed=[],
            error_message="Connection timeout",
        )

        mismatch_record = InstallationRecord(
            id="2",
            timestamp="now",
            operation_type=InstallationType.INSTALL,
            packages=["nginx"],
            status=InstallationStatus.FAILED,
            before_snapshot=[],
            after_snapshot=[],
            commands_executed=[],
            error_message="Other error",
        )

        mock_history.return_value = [match_record, mismatch_record]

        prediction = self.manager.analyze_installation("docker", ["sudo apt install docker.io"])

        # Should be HIGH risk because it's a direct match and failure
        self.assertEqual(prediction.risk_level, RiskLevel.HIGH)
        self.assertTrue(any("failed 1 times" in r for r in prediction.reasons))

    @patch("cortex.hardware_detection.HardwareDetector.detect")
    @patch("cortex.installation_history.InstallationHistory.get_history")
    @patch("cortex.llm_router.LLMRouter.complete")
    def test_llm_malformed_json_fallback(self, mock_llm, mock_history, mock_detect):
        mock_detect.return_value = SystemInfo(
            kernel_version="6.0.0",
            memory=MemoryInfo(total_mb=16384),
            storage=[StorageInfo(mount_point="/", available_gb=50.0, total_gb=100.0)],
        )
        mock_history.return_value = []

        # Mock LLM with non-JSON content
        mock_llm.return_value.content = "Risk: This is a text response"

        prediction = self.manager.analyze_installation("nginx", ["apt install nginx"])
        self.assertTrue(any("LLM detected risks" in r for r in prediction.reasons))

    @patch("cortex.hardware_detection.HardwareDetector.detect")
    def test_critical_risk_finalization(self, mock_detect):
        mock_detect.return_value = SystemInfo(
            kernel_version="6.0.0",
            memory=MemoryInfo(total_mb=16384),
            storage=[StorageInfo(mount_point="/", available_gb=50.0, total_gb=100.0)],
        )

        prediction = self.manager.analyze_installation("test", ["test"])
        prediction.reasons.append("This is a CRITICAL failure")
        self.manager._finalize_risk_level(prediction)
        self.assertEqual(prediction.risk_level, RiskLevel.HIGH)


if __name__ == "__main__":
    unittest.main()
