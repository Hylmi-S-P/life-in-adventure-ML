"""
test_session_logger.py - Unit tests for SessionLogger.
"""

import os
import unittest
import shutil
import tempfile
import sqlite3
from PIL import Image
from src.capture.session_logger import SessionLogger


class TestSessionLogger(unittest.TestCase):
    """Verifies feedback logging, database updates, and screenshot saving functionality."""

    def setUp(self):
        # Create a temporary directory for test logs and screenshots
        self.test_dir = tempfile.mkdtemp()
        self.logger = SessionLogger(base_dir=self.test_dir)

    def tearDown(self):
        # Close connection and remove temp directory
        self.logger.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_database_initialization(self):
        """Verify SQLite DB creates feedback_logs table successfully."""
        self.assertTrue(os.path.exists(self.logger.db_path))
        conn = sqlite3.connect(self.logger.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback_logs'")
        table_exists = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(table_exists)

    def test_log_event_without_screenshot(self):
        """Verify logging an event registers in the database and buffer."""
        log_id = self.logger.log_event(
            event_key="EventNormal1_143",
            ocr_text="You walk by a chilling cemetery...",
            choice_recommended="Ignore it",
            choice_index=0
        )
        
        self.assertIsNotNone(log_id)
        
        # Verify in-memory buffer
        pending = self.logger.get_pending_logs()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], log_id)
        self.assertEqual(pending[0]["event_key"], "EventNormal1_143")
        self.assertEqual(pending[0]["status"], "pending")

        # Verify in SQLite
        conn = sqlite3.connect(self.logger.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM feedback_logs WHERE id = ?", (log_id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row["event_key"], "EventNormal1_143")
        self.assertEqual(row["choice_recommended"], "Ignore it")
        self.assertEqual(row["status"], "pending")

    def test_log_event_with_screenshot(self):
        """Verify screenshots are saved to disk with sanitized file names."""
        # Create a mock PIL image
        img = Image.new("RGB", (100, 100), color="blue")
        
        log_id = self.logger.log_event(
            event_key="EventNormal_Special/Characters?",
            ocr_text="Some text",
            choice_recommended="Option A",
            choice_index=1,
            screenshot_image=img
        )
        
        self.assertIsNotNone(log_id)
        
        # Verify in SQLite path
        conn = sqlite3.connect(self.logger.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM feedback_logs WHERE id = ?", (log_id,))
        row = cursor.fetchone()
        conn.close()
        
        screenshot_path = row["screenshot_path"]
        self.assertTrue(os.path.exists(screenshot_path))
        self.assertTrue(screenshot_path.endswith(".png"))
        self.assertIn("EventNormal_Special_Characters_", screenshot_path)

    def test_update_feedback_success(self):
        """Verify updating log status to success reflects in DB and buffer."""
        log_id = self.logger.log_event(
            event_key="TestEvent",
            ocr_text="Context",
            choice_recommended="Do it",
            choice_index=0
        )
        
        success = self.logger.update_feedback(log_id, "success")
        self.assertTrue(success)
        
        # Check buffer (should not be in pending anymore)
        pending = self.logger.get_pending_logs()
        self.assertEqual(len(pending), 0)
        
        # Check database directly
        conn = sqlite3.connect(self.logger.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM feedback_logs WHERE id = ?", (log_id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["comments"], "")

    def test_update_feedback_failure_with_comments(self):
        """Verify updating log status to failure stores comments correctly."""
        log_id = self.logger.log_event(
            event_key="TestEvent",
            ocr_text="Context",
            choice_recommended="Do it",
            choice_index=0
        )
        
        success = self.logger.update_feedback(log_id, "failure", "AI misidentified choices")
        self.assertTrue(success)
        
        # Check database directly
        conn = sqlite3.connect(self.logger.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM feedback_logs WHERE id = ?", (log_id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertEqual(row["status"], "failure")
        self.assertEqual(row["comments"], "AI misidentified choices")


if __name__ == "__main__":
    unittest.main()
