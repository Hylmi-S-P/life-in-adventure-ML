"""
test_action_aware.py - ButtonScanner, SessionMemory, ActionSelector unit tests.
"""

import sys
import unittest

sys.path.insert(0, ".")

from src.core.button_scanner import ButtonScanner
from src.core.session_memory import SessionMemory
from src.core.action_selector import ActionSelector
from src.core.screen_state import ScreenState


class TestButtonScanner(unittest.TestCase):
    def setUp(self):
        self.bs = ButtonScanner()
        self.rect = {"top": 0, "left": 0, "width": 600, "height": 1000}

    def test_continue_button(self):
        btns = self.bs.scan(
            [{"text": "Continue", "center": (300, 800)}],
            "Some story Continue",
            self.rect,
        )
        kinds = [b.kind for b in btns]
        self.assertIn("continue", kinds)
        cont = self.bs.first_of(btns, "continue")
        self.assertIsNotNone(cont)
        self.assertEqual(cont.center, (300, 800))

    def test_choice_numbers(self):
        btns = self.bs.scan(
            [
                {"text": "1. Attack", "center": (300, 700)},
                {"text": "2. Run", "center": (300, 780)},
            ],
            "1. Attack 2. Run",
            self.rect,
        )
        choices = [b for b in btns if b.kind == "choice"]
        self.assertGreaterEqual(len(choices), 2)
        self.assertEqual(choices[0].choice_idx, 0)
        self.assertEqual(choices[1].choice_idx, 1)

    def test_battle_begin(self):
        btns = self.bs.scan(
            [{"text": "Begin Battle", "center": (300, 750)}],
            "Begin Battle Chance Abandon Battle",
            self.rect,
        )
        self.assertTrue(self.bs.has_kind(btns, "battle_begin"))

    def test_choices_visible_separator(self):
        self.assertTrue(
            self.bs.choices_visible(
                [{"text": "════ 13 ════", "center": (300, 600)}],
                "════ 13 ════",
            )
        )


class TestSessionMemory(unittest.TestCase):
    def test_force_continue_after_choice(self):
        m = SessionMemory()
        m.record("choice", event_key="EventNormal1_288_288", choice_idx=0, choice_text="No")
        self.assertTrue(m.pending_continue)
        self.assertTrue(m.should_force_continue("EventNormal1_288_288"))
        self.assertFalse(m.should_force_continue("EventOther_1_1"))
        m.clear_pending()
        self.assertFalse(m.should_force_continue("EventNormal1_288_288"))

    def test_history_bounded(self):
        m = SessionMemory()
        for i in range(30):
            m.record("wait", reason=str(i))
        self.assertLessEqual(len(m.action_history), 20)


class TestActionSelector(unittest.TestCase):
    def setUp(self):
        self.bs = ButtonScanner()
        self.sel = ActionSelector(scanner=self.bs)
        self.rect = {"top": 0, "left": 0, "width": 600, "height": 1000}

    def test_continue_beats_rag_when_pending(self):
        mem = SessionMemory()
        mem.record("choice", event_key="E1", choice_idx=0)
        btns = self.bs.scan(
            [
                {"text": "Continue", "center": (300, 800)},
                {"text": "1. Attack", "center": (300, 700)},
            ],
            "Continue 1. Attack",
            self.rect,
        )
        action = self.sel.select(
            ScreenState.CHOICE,
            btns,
            mem,
            rag_result={"matched": True, "event": {"event_key": "E1"}},
            recommendation={"recommended_choice_idx": 0, "recommended_choice_text": "Attack"},
        )
        self.assertEqual(action.type, "continue")
        self.assertIn("pending", action.reason)

    def test_same_event_force_continue(self):
        mem = SessionMemory()
        mem.record("choice", event_key="E1", choice_idx=0)
        # No continue button classified — still force advance
        action = self.sel.select(
            ScreenState.CHOICE,
            [],
            mem,
            rag_result={"matched": True, "event": {"event_key": "E1"}},
            recommendation={"recommended_choice_idx": 0, "recommended_choice_text": "X"},
        )
        self.assertIn(action.type, ("continue", "advance"))
        self.assertTrue(
            "pending" in action.reason or "same_event" in action.reason or "force" in action.reason
        )

    def test_needs_rag_false_on_dialogue(self):
        mem = SessionMemory()
        btns = self.bs.scan(
            [{"text": "Continue", "center": (300, 800)}], "Continue", self.rect
        )
        self.assertFalse(
            self.sel.needs_rag(ScreenState.DIALOGUE, btns, mem, ad_playing=False)
        )

    def test_needs_rag_true_on_choice(self):
        mem = SessionMemory()
        btns = self.bs.scan(
            [{"text": "1. Attack", "center": (300, 700)}], "1. Attack", self.rect
        )
        self.assertTrue(
            self.sel.needs_rag(ScreenState.CHOICE, btns, mem, ad_playing=False)
        )

    def test_battle_action(self):
        mem = SessionMemory()
        btns = self.bs.scan(
            [{"text": "Begin Battle", "center": (300, 750)}],
            "Begin Battle",
            self.rect,
        )
        action = self.sel.select(ScreenState.COMBAT, btns, mem)
        self.assertEqual(action.type, "battle")


if __name__ == "__main__":
    unittest.main()
