"""
PANDA — Sprint 9 Action Executor Test Suite
===========================================
Validates the OODA loop logic: limits, retries, high-risk detection,
and action dispatching.
"""

import unittest
from unittest.mock import patch, MagicMock
from action.task_executor import execute_autonomous_task, is_high_risk

class TestTaskExecutor(unittest.TestCase):

    def setUp(self):
        # Reset the stop event just in case
        from action import action_executor
        action_executor.reset_stop()
        
        # Initialize memory database schema (including new lessons table)
        import memory_manager
        memory_manager.initialize_memory()
        
        # Mock time.sleep only inside task_executor and mouse_controller to make tests run instantly
        # without affecting third-party libraries (e.g. sentence_transformers) during model loading
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

    def test_high_risk_detection(self):
        """Test that high-risk actions are properly detected."""
        self.assertTrue(is_high_risk("click", {"target": "Submit Payment"}))
        self.assertTrue(is_high_risk("click", {"target": "Delete All"}))
        self.assertTrue(is_high_risk("type", {"text": "transfer money"}))
        self.assertFalse(is_high_risk("click", {"target": "Home"}))
        self.assertFalse(is_high_risk("type", {"text": "hello world"}))

    @patch('action.task_executor._client.chat')
    @patch('action.task_executor._capture_screen_with_retry')
    @patch('action.action_tools.handle_click')
    def test_successful_task_sequence(self, mock_click, mock_capture, mock_chat):
        """Test a clean execution loop that hits 'complete'."""
        mock_capture.return_value = {"summary": "Fake screen"}
        mock_click.return_value = "Clicked successfully"
        
        # 1st turn: click. 2nd turn: complete.
        mock_chat.side_effect = [
            {"message": {"content": '{"think": "Need to click", "action": "click", "parameters": {"target": "Button"}}'}},
            {"message": {"content": '{"think": "Done", "action": "complete", "parameters": {}}'}}
        ]

        result = execute_autonomous_task("Test task")
        self.assertIn("Successfully completed", result)
        self.assertEqual(mock_click.call_count, 1)

    @patch('action.task_executor._client.chat')
    @patch('action.task_executor._capture_screen_with_retry')
    @patch('action.action_tools.handle_type')
    def test_retry_limit(self, mock_type, mock_capture, mock_chat):
        """Test that the loop aborts after 5 failures of the same step."""
        mock_capture.return_value = {"summary": "Fake screen"}
        # Handler returns an error string
        mock_type.return_value = "Error: couldn't find element"
        
        # LLM keeps trying to type
        mock_chat.return_value = {"message": {"content": '{"think": "Try again", "action": "type", "parameters": {"text": "Hello"}}'}}

        result = execute_autonomous_task("Test task")
        self.assertIn("Task failed after 5 retries", result)
        self.assertEqual(mock_type.call_count, 5)

    @patch('action.task_executor._client.chat')
    @patch('action.task_executor._capture_screen_with_retry')
    @patch('action.action_tools.handle_scroll')
    def test_hard_limit(self, mock_scroll, mock_capture, mock_chat):
        """Test that the loop aborts after hitting the hard limit (25)."""
        mock_capture.return_value = {"summary": "Fake screen"}
        mock_scroll.return_value = "Scrolled"
        
        # LLM keeps scrolling forever
        mock_chat.return_value = {"message": {"content": '{"think": "Keep going", "action": "scroll", "parameters": {"direction": "down"}}'}}

        # To skip the soft-limit input prompt, we mock `input` to return "yes"
        with patch('builtins.input', return_value='y'):
            result = execute_autonomous_task("Test task")
            
        self.assertIn("Task aborted automatically at hard limit", result)
        self.assertEqual(mock_scroll.call_count, 24) # Because check is at the start of loop

    @patch('action.task_executor._client.chat')
    @patch('action.task_executor._capture_screen_with_retry')
    def test_high_risk_aborts_if_no(self, mock_capture, mock_chat):
        """Test that high risk actions wait for confirmation, and abort if denied."""
        mock_capture.return_value = {"summary": "Fake screen"}
        mock_chat.return_value = {"message": {"content": '{"think": "Paying", "action": "click", "parameters": {"target": "Submit Payment"}}'}}

        with patch('builtins.input', return_value='n'):
            result = execute_autonomous_task("Test task")
            
        self.assertIn("aborted by user during safety check", result)

if __name__ == "__main__":
    unittest.main()
