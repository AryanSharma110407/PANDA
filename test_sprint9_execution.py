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

if __name__ == "__main__":
    unittest.main()
