"""
test_action_aware.py - ButtonScanner, SessionMemory, ActionSelector unit tests.
"""
import sys, unittest
sys.path.insert(0,".")
from src.core.button_scanner import ButtonScanner
from src.core.session_memory import SessionMemory
from src.core.action_selector import ActionSelector
from src.core.screen_state import ScreenState

class TestButtonScanner(unittest.TestCase):
    def setUp(self):
        self.bs = ButtonScanner()
        self.rect = {"top": 0, "left": 0, "width": 600, "height": 1000}
    def test_continue(self):
        btns = self.bs.scan([{"text":"Continue","center":(300,800)}],"Continue",self.rect)
        self.assertTrue(self.bs.has_kind(btns,"continue"))
    def test_choice(self):
        btns = self.bs.scan([{"text":"1. Attack","center":(300,700)},{"text":"2. Run","center":(300,780)}],"1. Attack 2. Run",self.rect)
        cs = [b for b in btns if b.kind=="choice_numbered"]
        self.assertGreaterEqual(len(cs),2)
    def test_combat(self):
        btns = self.bs.scan([{"text":"Begin Battle","center":(300,750)}],"Begin Battle",self.rect)
        self.assertTrue(self.bs.has_kind(btns,"combat"))
    def test_generic_action(self):
        btns = self.bs.scan([{"text":"Proceed","center":(300,850)}],"Proceed",self.rect)
        self.assertTrue(self.bs.has_kind(btns,"action"))

class TestSessionMemory(unittest.TestCase):
    def test_force_continue(self):
        m = SessionMemory()
        m.record("choice",event_key="E1",choice_idx=0)
        self.assertTrue(m.pending_continue)
        self.assertTrue(m.should_force_continue("E1"))
        m.clear_pending()
        self.assertFalse(m.should_force_continue("E1"))

class TestActionSelector(unittest.TestCase):
    def setUp(self):
        self.bs = ButtonScanner()
        self.sel = ActionSelector(scanner=self.bs)
        self.rect = {"top":0,"left":0,"width":600,"height":1000}
    def test_continue_beats_choice(self):
        mem = SessionMemory()
        mem.record("choice",event_key="E1",choice_idx=0)
        btns = self.bs.scan([{"text":"Continue","center":(300,800)},{"text":"1. Attack","center":(300,700)}],"Continue 1. Attack",self.rect)
        a = self.sel.select(ScreenState.CHOICE,btns,mem,rag_result={"matched":True,"event":{"event_key":"E1"}},recommendation={"recommended_choice_idx":0,"recommended_choice_text":"Attack"})
        self.assertEqual(a.type,"continue")
    def test_combat_action(self):
        mem = SessionMemory()
        btns = self.bs.scan([{"text":"Begin Battle","center":(300,750)}],"Begin Battle",self.rect)
        a = self.sel.select(ScreenState.COMBAT,btns,mem)
        self.assertEqual(a.type,"combat")
    def test_merchant_action(self):
        mem = SessionMemory()
        btns = self.bs.scan([{"text":"Buy","center":(300,750)}],"Buy",self.rect)
        a = self.sel.select(ScreenState.CHOICE,btns,mem)
        self.assertEqual(a.type,"merchant")
    def test_recovery_action(self):
        mem = SessionMemory()
        btns = self.bs.scan([{"text":"Rest","center":(300,750)}],"Rest",self.rect)
        a = self.sel.select(ScreenState.CHOICE,btns,mem)
        self.assertEqual(a.type,"recovery")

if __name__ == "__main__":
    unittest.main()
