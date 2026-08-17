"""
PANDA — Sprint 9 Action Executor Test Suite
===========================================
Validates the new decomposed execution loop: limits, retries, destructive actions,
and action dispatching.
"""

import unittest
from unittest.mock import patch, MagicMock
import json
from action.task_executor import execute_autonomous_task
from action.action_executor import is_destructive

class TestTaskExecutor(unittest.TestCase):

    def setUp(self):
        # Reset the stop event just in case
        from action import action_executor
        action_executor.reset_stop()
        
        # Initialize memory database schema
        import memory_manager
        memory_manager.initialize_memory()
        
        # Mock time.sleep to run instantly
        self.sleep_patcher1 = patch('action.task_executor.time.sleep')
        self.sleep_patcher2 = patch('action.mouse_controller.time.sleep')
        self.critic_patcher = patch('action.action_critic.critique_action', return_value={"approved": True, "feedback": "Auto-approved in execution tests"})
        self.input_patcher = patch('builtins.input', return_value="")
        self.mock_sleep1 = self.sleep_patcher1.start()
        self.mock_sleep2 = self.sleep_patcher2.start()
        self.mock_critic = self.critic_patcher.start()
        self.mock_input = self.input_patcher.start()

    def tearDown(self):
        self.sleep_patcher1.stop()
        self.sleep_patcher2.stop()
        self.critic_patcher.stop()
        self.input_patcher.stop()

    def test_destructive_action_detection(self):
        """Test that destructive actions are properly detected."""
        self.assertTrue(is_destructive("click", {"target": "Submit Payment"}))
        self.assertTrue(is_destructive("click", {"target": "Delete All"}))
        self.assertTrue(is_destructive("type", {"text": "transfer money"}))
        self.assertFalse(is_destructive("click", {"target": "Home"}))
        self.assertFalse(is_destructive("type", {"text": "hello world"}))

    @patch('action.task_executor._client.chat')
    @patch('action.task_executor._capture_screen_with_retry')
    @patch('action.action_tools.handle_click')
    def test_successful_task_sequence(self, mock_click, mock_capture, mock_chat):
        """Test a clean execution loop that hits 'complete'."""
        mock_capture.return_value = {"summary": "Fake screen", "visible_text": []}
        mock_click.return_value = "Clicked successfully"
        
        # 1st turn: click. 2nd turn: complete.
        mock_chat.side_effect = [
            {"message": {"content": '{"think": "Need to click", "action": "click", "parameters": {"target": "Button"}}'}},
            {"message": {"content": '{"think": "Done", "action": "milestone_complete", "parameters": {}}'}}
        ]

        result = execute_autonomous_task("Test task", milestones=["Milestone 1"])
        self.assertIn("Successfully completed", result)
        self.assertEqual(mock_click.call_count, 1)

    @patch('action.task_executor._client.chat')
    @patch('action.task_executor._capture_screen_with_retry')
    @patch('action.action_tools.handle_type')
    @patch('action.action_executor.kill_active_app')
    def test_milestone_stuck_and_reset(self, mock_kill, mock_type, mock_capture, mock_chat):
        """Test that the loop triggers Home Base Reset after consecutive failures."""
        mock_capture.return_value = {"summary": "Fake screen", "visible_text": []}
        mock_type.return_value = "Error: couldn't find element"
        mock_kill.return_value = {"success": True, "details": "Killed app"}
        
        # LLM keeps trying to type
        mock_chat.return_value = {"message": {"content": '{"think": "Try again", "action": "type", "parameters": {"text": "Hello"}}'}}

        result = execute_autonomous_task("Test task", milestones=["Milestone 1"])
        self.assertIn("resets", result.lower())
        self.assertGreater(mock_kill.call_count, 0)

    @patch('action.task_executor._client.chat')
    @patch('action.task_executor._capture_screen_with_retry')
    def test_destructive_aborts_if_no(self, mock_capture, mock_chat):
        """Test that destructive actions wait for confirmation, and abort if denied."""
        mock_capture.return_value = {"summary": "Fake screen", "visible_text": []}
        mock_chat.return_value = {"message": {"content": '{"think": "Paying", "action": "click", "parameters": {"target": "Submit Payment"}}'}}

        with patch('builtins.input', return_value='n'):
            result = execute_autonomous_task("Test task", milestones=["Milestone 1"])
            
        self.assertEqual(result, "Task was aborted by user.")

    @patch('action.app_detector.is_app_installed')
    @patch('action.action_tools.handle_system_search')
    @patch('action.action_tools.handle_browser_open')
    def test_open_application_routing(self, mock_browser_open, mock_system_search, mock_is_installed):
        """Test that open_application dynamically routes to local or web fallback."""
        from action.action_tools import handle_open_application
        
        # Test Case 1: App is installed (should launch local app)
        mock_is_installed.return_value = True
        mock_system_search.return_value = "System search successful"
        
        res1 = handle_open_application("Spotify", "https://spotify.com", "session_123")
        self.assertIn("launched the desktop application", res1)
        mock_system_search.assert_called_once_with("Spotify", "session_123")
        mock_browser_open.assert_not_called()
        
        # Reset mocks
        mock_system_search.reset_mock()
        mock_browser_open.reset_mock()
        
        # Test Case 2: App is not installed (should open browser URL)
        mock_is_installed.return_value = False
        mock_browser_open.return_value = "Opened browser page"
        
        res2 = handle_open_application("Spotify", "https://spotify.com", "session_123")
        self.assertIn("opened its web version", res2)
        mock_browser_open.assert_called_once_with("https://spotify.com", "session_123")
        mock_system_search.assert_not_called()


class TestSTDPHabitTracker(unittest.TestCase):
    """Tests the experimental STDP (Spike-Timing-Dependent Plasticity) habit learning system."""

    def setUp(self):
        """Reset the STDP tracker state before each test."""
        import numpy as np
        from action import stdp_habit_tracker as tracker
        self.tracker = tracker
        # Reset internal state
        tracker._event_to_id.clear()
        tracker._id_to_event.clear()
        tracker._next_neuron_id = 0
        tracker._weights = np.zeros((tracker.MAX_NEURONS, tracker.MAX_NEURONS), dtype=np.float32)
        tracker._spike_history.clear()
        tracker._dirty = False

    def test_event_registration_creates_neurons(self):
        """Verify that registering events creates unique neuron IDs."""
        self.tracker.register_event("window:brave")
        self.tracker.register_event("type:youtube.com")
        self.tracker.register_event("key:enter")

        self.assertEqual(self.tracker._next_neuron_id, 3)
        self.assertIn("window:brave", self.tracker._event_to_id)
        self.assertIn("type:youtube.com", self.tracker._event_to_id)
        self.assertIn("key:enter", self.tracker._event_to_id)

    def test_repeated_sequence_strengthens_weights(self):
        """Verify that repeating a causal sequence strengthens synaptic weights."""
        import time

        # Simulate the user opening Brave -> typing youtube -> pressing enter
        # Repeat this 8 times to build strong weights
        for _ in range(8):
            self.tracker.register_event("window:brave")
            time.sleep(0.05)  # Small delay to ensure causal ordering
            self.tracker.register_event("type:youtube.com")
            time.sleep(0.05)
            self.tracker.register_event("key:enter")
            time.sleep(0.05)

        # Check that brave -> youtube weight is strong
        brave_id = self.tracker._event_to_id["window:brave"]
        youtube_id = self.tracker._event_to_id["type:youtube.com"]
        enter_id = self.tracker._event_to_id["key:enter"]

        w_brave_youtube = self.tracker._weights[brave_id, youtube_id]
        w_youtube_enter = self.tracker._weights[youtube_id, enter_id]

        self.assertGreater(w_brave_youtube, 0.1,
            f"Weight brave->youtube should be strong, got {w_brave_youtube}")
        self.assertGreater(w_youtube_enter, 0.1,
            f"Weight youtube->enter should be strong, got {w_youtube_enter}")

    def test_predictions_return_learned_habits(self):
        """Verify that get_predictions returns the learned next action."""
        import time

        # Train: brave -> youtube (repeat 10 times for strong weight)
        for _ in range(10):
            self.tracker.register_event("window:brave")
            time.sleep(0.05)
            self.tracker.register_event("type:youtube.com")
            time.sleep(0.05)

        predictions = self.tracker.get_predictions("window:brave")

        # Should predict youtube.com as the next action
        event_names = [p["event"] for p in predictions]
        self.assertIn("type:youtube.com", event_names,
            f"Expected 'type:youtube.com' in predictions, got {predictions}")

    def test_habit_summary_generates_readable_text(self):
        """Verify that get_habit_summary returns human-readable text."""
        import time

        # Train a sequence
        for _ in range(10):
            self.tracker.register_event("window:brave")
            time.sleep(0.05)
            self.tracker.register_event("type:youtube.com")
            time.sleep(0.05)

        summary = self.tracker.get_habit_summary()

        if summary:
            self.assertIn("HABIT PATTERNS", summary)
            self.assertIn("window:brave", summary)
            self.assertIn("type:youtube.com", summary)

    def test_stats_report(self):
        """Verify get_stats returns correct diagnostic info."""
        self.tracker.register_event("test:event_a")
        self.tracker.register_event("test:event_b")

        stats = self.tracker.get_stats()
        self.assertEqual(stats["neurons"], 2)
        self.assertEqual(stats["total_events_registered"], 2)
        self.assertGreaterEqual(stats["spikes_in_history"], 2)


if __name__ == "__main__":
    unittest.main()

