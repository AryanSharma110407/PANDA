"""
PANDA — Action Critic Test Suite (Plan 2 Verification)
======================================================
Validates the Critic overseer agent, its critique logic, and its integration 
within the OODA loop (retries on rejection, success on approval).
"""

import unittest
from unittest.mock import patch, MagicMock
import json
from action.action_critic import critique_action
from action.task_executor import execute_autonomous_task

class TestActionCritic(unittest.TestCase):

    def setUp(self):
        # Reset stop event and patch sleep/idle checks to ensure fast, deterministic tests
        from action import action_executor
        action_executor.reset_stop()
        
        # Initialize memory database schema (including new lessons table)
        import memory_manager
        memory_manager.initialize_memory()
        
        self.sleep_patcher1 = patch('action.task_executor.time.sleep')
        self.sleep_patcher2 = patch('action.mouse_controller.time.sleep')
        self.idle_patcher = patch('action.mouse_controller.wait_for_user_idle')
        self.mock_sleep1 = self.sleep_patcher1.start()
        self.mock_sleep2 = self.sleep_patcher2.start()
        self.mock_idle = self.idle_patcher.start()

    def tearDown(self):
        self.sleep_patcher1.stop()
        self.sleep_patcher2.stop()
        self.idle_patcher.stop()

    @patch('action.action_critic._client.chat')
    def test_critic_approval(self, mock_chat):
        """Test that critique_action parses and returns approved response correctly."""
        mock_chat.return_value = {
            "message": {
                "content": '{"approved": true, "feedback": "Looks good"}'
            }
        }
        res = critique_action("Open notepad", "Notepad is not open", {"action": "system_search", "parameters": {"query": "notepad"}})
        self.assertTrue(res["approved"])
        self.assertEqual(res["feedback"], "Looks good")

    @patch('action.action_critic._client.chat')
    def test_critic_rejection_for_hallucination(self, mock_chat):
        """Test that the critic rejects action searching inside an already open app."""
        mock_chat.return_value = {
            "message": {
                "content": '{"approved": false, "feedback": "Do not search start menu for button when Notepad is active"}'
            }
        }
        res = critique_action(
            goal="Write hello",
            screen_state_summary="Notepad window is active. Focus is inside the text area.",
            proposed_action={"action": "system_search", "parameters": {"query": "File menu"}}
        )
        self.assertFalse(res["approved"])
        self.assertIn("Do not search start menu", res["feedback"])

    @patch('action.task_executor._client.chat')
    @patch('action.action_critic._client.chat')
    @patch('action.task_executor._capture_screen_with_retry')
    @patch('action.action_tools.handle_click')
    @patch('builtins.input')
    def test_ooda_loop_retries_on_critic_rejection(self, mock_input, mock_click, mock_capture, mock_critic_chat, mock_actor_chat):
        """
        Test that task_executor retries calling the Actor if the Critic rejects the action.
        Then, when the Actor corrects the action and the Critic approves, it completes successfully.
        """
        # Return empty feedback so that user feedback extraction is skipped, keeping Actor call count to exactly 3
        mock_input.return_value = ""
        mock_capture.return_value = {"summary": "Fake screen state", "ui_controls": []}
        mock_click.return_value = "Clicked successfully"
        
        # 1st Actor decision: system_search (rejected)
        # 2nd Actor decision: click (approved)
        # 3rd Actor decision: complete
        mock_actor_chat.side_effect = [
            {"message": {"content": '{"think": "Let me search", "action": "system_search", "parameters": {"query": "Button"}}'}},
            {"message": {"content": '{"think": "Let me click", "action": "click", "parameters": {"target": "Button"}}'}},
            {"message": {"content": '{"think": "Done", "action": "complete", "parameters": {}}'}}
        ]

        # Critic responses:
        # 1. Reject first action (system_search)
        # 2. Approve second action (click)
        # 3. Approve third action (complete)
        mock_critic_chat.side_effect = [
            {"message": {"content": '{"approved": false, "feedback": "CRITIC REJECTION: Do not use system_search for buttons inside open apps"}'}},
            {"message": {"content": '{"approved": true, "feedback": "Approved click"}'}},
            {"message": {"content": '{"approved": true, "feedback": "Approved completion"}'}}
        ]

        result = execute_autonomous_task("Click the button")
        self.assertIn("Successfully completed", result)
        
        # Actor chat should have been called 3 times (1 rejected + 1 correct + 1 complete)
        self.assertEqual(mock_actor_chat.call_count, 3)
        # Critic chat should have been called 3 times
        self.assertEqual(mock_critic_chat.call_count, 3)
        # Verify click action was run, system_search was NOT run because it was rejected by critic
        self.assertEqual(mock_click.call_count, 1)

    @patch('action.task_executor._client.chat')
    @patch('memory_manager.save_preference')
    def test_user_feedback_extraction(self, mock_save_pref, mock_chat):
        """Test that user feedback preference extractor correctly parses and saves rules."""
        from action.task_executor import _extract_and_save_user_preference
        
        mock_chat.return_value = {
            "message": {
                "content": "Do not close Chrome browser window after finding the address\nAlways right click on targets"
            }
        }
        
        _extract_and_save_user_preference("please don't close Chrome window, also always right click", "session_test")
        
        self.assertEqual(mock_save_pref.call_count, 2)
        mock_save_pref.assert_any_call("session_test", "Do not close Chrome browser window after finding the address")
        mock_save_pref.assert_any_call("session_test", "Always right click on targets")

if __name__ == '__main__':
    unittest.main()
