import unittest
import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from cortex.health import HealthEngine

class TestHealthEngine(unittest.TestCase):
    def setUp(self):
        """Set up temporary environment and test data for each test case."""
        # Create a temporary directory for history files during testing
        self.test_dir = TemporaryDirectory()
        self.history_path = Path(self.test_dir.name) / "health_history.json"
        
        # Scenario 1: The "Perfect" System (Expect 100/100)
        # Removed 'role' and 'role_set' to satisfy Issue #128 decoupling.
        self.perfect_data = {
            "firejail_installed": True,
            "api_keys_set": True,
            "ram_gb": 16.0,
            "gpu_detected": True
        }
        
        # Scenario 2: The "Failing" System (Expect low score)
        self.failing_data = {
            "firejail_installed": False,
            "api_keys_set": False,
            "ram_gb": 2.0,
            "gpu_detected": False
        }

    def tearDown(self):
        """Clean up temporary resources."""
        self.test_dir.cleanup()

    def test_calculate_overall_score_perfect(self):
        """Verify that a system meeting all criteria scores 100."""
        engine = HealthEngine(self.perfect_data)
        score = engine.calculate_overall_score()
        self.assertEqual(score, 100)

    def test_calculate_overall_score_penalties(self):
        """Verify that missing components significantly reduce the score."""
        engine = HealthEngine(self.failing_data)
        score = engine.calculate_overall_score()
        # With 2GB RAM (-50) and missing security (-50), score should be very low
        self.assertLess(score, 70)

    def test_factor_scores_breakdown(self):
        """Test that individual factors are calculated correctly."""
        engine = HealthEngine(self.failing_data)
        factors = engine.get_factor_scores()
        
        # Security: 100 - 30 (firejail) - 20 (keys) = 50
        self.assertEqual(factors["security"], 50) 
        # Resources: 100 - 50 (RAM < 4GB) = 50
        self.assertEqual(factors["resources"], 50)

    def test_gpu_penalty(self):
        """Verify performance penalty when GPU is missing."""
        data = self.perfect_data.copy()
        data["gpu_detected"] = False
        
        engine = HealthEngine(data)
        factors = engine.get_factor_scores()
        # Performance should drop because there is no hardware acceleration
        self.assertEqual(factors["performance"], 80) # 100 - 20

    def test_recommendations_actionable(self):
        """Ensure recommendations contain both actionable fixes and advice."""
        engine = HealthEngine(self.failing_data)
        recs = engine.get_recommendations()
        
        # Should have a fix command for firejail
        firejail_rec = next((r for r in recs if "firejail" in r["text"].lower()), None)
        self.assertIsNotNone(firejail_rec)
        self.assertIn("sudo apt-get install", firejail_rec["fix"])

    def test_history_persistence_and_sliding_window(self):
        """Verify history saving and the 10-entry limit."""
        engine = HealthEngine(self.perfect_data)
        # Override history file to point to our temporary test directory
        engine.history_file = self.history_path
        
        # Save 15 scores to test the sliding window logic
        for i in range(15):
            engine.save_history(score=i)
            
        # Verify file actually exists
        self.assertTrue(self.history_path.exists())
        
        # Verify sliding window (should only keep 10 latest entries)
        with open(self.history_path, "r") as f:
            history = json.load(f)
            self.assertEqual(len(history), 10)
            # The last entry should be the last score we saved (14)
            self.assertEqual(history[-1]["score"], 14)

if __name__ == "__main__":
    unittest.main()