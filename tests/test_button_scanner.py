"""
button_scanner_test.py - Expanded unit tests for button_scanner, memory, selector.
"""

import sys
import unittest

sys.path.insert(0, ".")

from src.core.button_scanner import ButtonScanner
from src.core.session_memory import SessionMemory
from src.core.action_selector import ActionSelector
from src.core.screen_state import ScreenState


class TestButtonScannerExpanded(unittest.TestCase):
    def setUp(self):
        self.bs = ButtonScanner()
        self.rect = {"top": 0, "left": 0, "width": 600, "height": 1000}

    def test_continue(self):
        btns = self.bs.scan(
            [{"text": "Continue", "center": (300, 800)}],
            "Continue",
            self.rect,
        )
        self.assertTrue(self.bs.has_kind(btns, "continue"))

    def combat(self):
        btns = self.bs.scan(
            [{"text": "Begin Battle", "center": (300, 750)}],
            "Begin Battle Chance Abandon Battle",
            self.rect,
        )
        self.assertTrue(self.bs.has_kind(btns, "combat"))

    def test_choice_numbered(self):
        btns = self.bs.scan(
            [{"text": "1. Attack", "center": (300, 700)},
             {"text": "2. Run", "center": (300, 780)}],
            "1. Attack 2. Run",
            self.rect,
        )
        choices = [b for b in btns if b.kind == "choice_numbered"]
        self.assertGreaterEqual(len(choices), 2)
        self.assertEqual(choices[0].choice_idx, 0)
        self.assertEqual(choices[1].choice_idx, 1)

    def test_merchant(self):
        btns = self.bs.scan(
            [{"text": "Buy", "center": (300, 700)},
             {"text": "Sell", "center": (300, 780)}],
            "Buy Sell",
            self.rect,
        )
        self.assertTrue(self.bs.has_kind(btns, "merchant"))

    def test_recovery(self):
        btns = self.bs.scan(
            [{"text": "Rest", "center": (300, 750)}],
            "Rest Camp Sleep",
            self.rect,
        )
        self.assertTrue(self.bs.has_kind(btns, "recovery"))

    def test_explore(self):
        btns = self.bs.scan(
            [{"text": "Search", "center": (300, 750)},
             {"text": "Open", "center": (300, 800)}],
            "Search Open",
            self.rect,
        )
        self.assertTrue(self.bs.has_kind(btns, "explore"))

    def test_social(self):
        btns = self.bs.scan(
            [{"text": "Talk", "center": (300, 750)}],
            "Talk Ask Bribe",
            self.rect,
        )
        self.assertTrue(self.bs.has_kind(btns, "social"))

    def test_quest(self):
        btns = self.bs.scan(
            [{"text": "Accept", "center": (300, 750)}],
            "Accept Decline",
            self.rect,
        )
        self.assertTrue(self.bs.has_kind(btns, "quest"))

    def test_binary(self):
        btns = self.bs.scan(
            [{"text": "Yes", "center": (300, 750)},
             {"text": "No", "center": (300, 800)}],
            "Yes No",
            self.rect,
        )
        # Either binary or action
        kinds = [b.kind for b in btns]
        self.assertTrue("binary" in kinds or "action" in kinds)

    def test_generic_action_fallback(self):
        """Short unknown text in bottom zone → action."""
        btns = self.bs.scan(
            [{"text": "Proceed", "center": (300, 850)},
             {"text": "Advance", "center": (300, 900)}],
            "Proceed Advance",
            self.rect,
        )
        self.assertTrue(self.bs.has_kind(btns, "action"))

    def test_narrative_ignored(self):
        """Long text in bottom zone should NOT be a button."""
        btns = self.bs.scan(
            [{"text": "You arrive at a big city where supplies come in from all over the empire.", "center": (300, 500)}],
            "Long narrative text...",
            self.rect,
        )
        if btns:
            for b in btns:
                self.assertNotEqual(b.kind, "action", f"narrative misclassified as action: {b.text[:30]}")


class TestSessionMemory(unittest.TestCase):
    def test_force_continue(self):
        m = SessionMemory()
        m.record("choice", event_key="E1", choice_idx=0)
        self.assertTrue(m.pending_continue)
        self.assertTrue(m.should_force_continue("E1"))
        m.clear_pending()
        self.assertFalse(m.should_force_continue("E1"))

    def test_history_bounded(self):
        m = SessionMemory()
        for i in range(30):
            m.record("wait", reason=str(i))
        self.assertLessEqual(len(m.action_history), 20)


class TestActionSelectorExpanded(unittest.TestCase):
    def setUp(self):
        self.bs = ButtonScanner()
        self.sel = ActionSelector(scanner=self.bs)
        self.rect = {"top": 0, "left": 0, "width": 600, "height": 1000}

    def test_merchant_action(self):
        mem = SessionMemory()
        btns = self.bs.scan(
            [{"text": "Buy", "center": (300, 750)},
             {"text": "Sell", "center": (300, 800)}],
            "Buy Sell",
            self.rect,
        )
        action = self.sel.select(ScreenState.CHOICE, btns, mem)
        self.assertEqual(action.type, "merchant")

    def test_recovery_action(self):
        mem = SessionMemory()
        btns = self.bs.scan(
            [{"text": "Rest", "center": (300, 750)}],
            "Rest",
            self.rect,
        )
        action = self.sel.select(ScreenState.CHOICE, btns, mem)
        self.assertEqual(action.type, "recovery")

    def test_explore_action(self):
        mem = SessionMemory()
        btns = self.bs.scan(
            [{"text": "Search", "center": (300, 750)}],
            "Search",
            self.rect,
        )
        action = self.sel.select(ScreenState.CHOICE, btns, mem)
        self.assertEqual(action.type, "explore")

    def test_social_action(self):
        mem = SessionMemory()
        btns = self.bs.scan(
            [{"text": "Talk", "center": (300, 750)}],
            "Talk",
            self.rect,
        )
        action = self.sel.select(ScreenState.CHOICE, btns, mem)
        self.assertEqual(action.type, "social")

    def test_choice_beats_generic_when_rag(self):
        mem = SessionMemory()
        btns = self.bs.scan(
            [{"text": "1. Attack", "center": (300, 700)},
             {"text": "2. Run", "center": (300, 780)}],
            "1. Attack 2. Run",
            self.rect,
        )
        action = self.sel.select(
            ScreenState.CHOICE,
            btns,
            mem,
            rag_result={"matched": True, "event": {"event_key": "E1"}},
            recommendation={
                "recommended_choice_idx": 1,
                "recommended_choice_text": "Run",
            },
        )
        self.assertEqual(action.type, "choice")
        self.assertEqual(action.choice_idx, 1)

    def test_nav_beats_rag(self):
        mem = SessionMemory()
        btns = self.bs.scan(
            [{"text": "Continue", "center": (300, 800)},
             {"text": "1. Attack", "center": (300, 700)}],
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
        self.assertEqual(action.type, "continue",
                         f"Continue should beat RAG choice, got {action.type}")


if __name__ == "__main__":
    unittest.main()
