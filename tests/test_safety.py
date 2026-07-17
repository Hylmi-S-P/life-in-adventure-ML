"""test_safety.py - Unit tests for LoadingState, DeadLoopState, MultiStepPlan, DLC detection."""
import sys, unittest
sys.path.insert(0, ".")
from src.core.safety import LoadingState, DeadLoopState, MultiStepPlan, detect_dlc

class TestLoadingState(unittest.TestCase):
    def test_empty_text(self):
        ls = LoadingState()
        self.assertFalse(ls.check(""))   # 1st empty → not yet detected
        self.assertFalse(ls.detected)
        self.assertTrue(ls.check(""))   # 2nd consecutive → detected
        self.assertTrue(ls.detected)

    def test_loading_keyword(self):
        ls = LoadingState()
        self.assertTrue(ls.check("Now Loading..."))
        self.assertTrue(ls.detected)

    def test_spinner(self):
        ls = LoadingState()
        self.assertTrue(ls.check("|"))
        self.assertTrue(ls.detected)

    def test_repeated_percent(self):
        ls = LoadingState()
        self.assertFalse(ls.check("50%"))   # first
        self.assertFalse(ls.check("50%"))   # second (consecutive_same_short=1)
        self.assertTrue(ls.check("50%"))   # third (consecutive_same_short>=2)
        self.assertTrue(ls.detected)

    def test_normal_text_resets(self):
        ls = LoadingState()
        ls.check("")
        ls.check("")
        self.assertTrue(ls.detected)
        self.assertFalse(ls.check("Hello adventurer!"))
        self.assertFalse(ls.detected)

    def test_reset(self):
        ls = LoadingState()
        ls.check("")
        ls.check("")
        self.assertTrue(ls.detected)
        ls.reset()
        self.assertFalse(ls.detected)
        self.assertEqual(ls.consecutive_no_text, 0)

class TestDeadLoop(unittest.TestCase):
    def test_identical_actions(self):
        dl = DeadLoopState(max_repeat=4)
        for _ in range(4):
            dl.record_and_check("advance", "E1", "same screen")
        self.assertTrue(dl.dead_loop_triggered)

    def test_different_actions_no_trigger(self):
        dl = DeadLoopState(max_repeat=4)
        dl.record_and_check("choice", "E1", "text")
        dl.record_and_check("continue", "E1", "text2")
        dl.record_and_check("advance", "E2", "text3")
        dl.record_and_check("choice", "E3", "text4")
        self.assertFalse(dl.dead_loop_triggered)

    def test_break_count_triggers_kill(self):
        dl = DeadLoopState(max_repeat=3)
        for _ in range(9):
            dl.record_and_check("advance", "E1", "")
        self.assertGreater(dl.break_count, 0)
        self.assertTrue(dl.dead_loop_triggered)

class TestMultiStepPlan(unittest.TestCase):
    def test_match_merchant_buy(self):
        name = MultiStepPlan.match_plan("Buy")
        self.assertEqual(name, "merchant_buy")

    def test_match_quest_accept(self):
        name = MultiStepPlan.match_plan("Accept")
        self.assertEqual(name, "quest_accept")

    def test_no_match_non_action(self):
        name = MultiStepPlan.match_plan("Continue")
        self.assertIsNone(name)

    def test_plan_advance(self):
        plan = MultiStepPlan()
        plan.start_plan("merchant_buy", "E1")
        self.assertEqual(plan.get_next_action(), "confirm")
        plan.advance_step()
        self.assertEqual(plan.get_next_action(), "pay")
        plan.advance_step()
        self.assertIsNone(plan.get_next_action())
        self.assertFalse(plan.active)

    def test_plan_cancel(self):
        plan = MultiStepPlan()
        plan.start_plan("quest_accept", "E1")
        self.assertTrue(plan.active)
        plan.cancel()
        self.assertFalse(plan.active)

class TestDLC(unittest.TestCase):
    def test_tales_keyword(self):
        is_dlc, name = detect_dlc("Forest's Invitation tales content")
        self.assertTrue(is_dlc)

    def test_main_event(self):
        is_dlc, name = detect_dlc("The Haunted Manor", "EventMain0_1_1")
        self.assertFalse(is_dlc)

    def test_no_false_positive(self):
        is_dlc, name = detect_dlc("You find a tavern", "EventNormal0_1")
        self.assertFalse(is_dlc)

if __name__ == "__main__":
    unittest.main()
