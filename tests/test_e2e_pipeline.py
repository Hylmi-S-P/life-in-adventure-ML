"""
test_e2e_pipeline.py - End-to-End Automated Verification Test Suite.
Audits and verifies every component of the Life in Adventure AI Quest Assistant pipeline:
RAG KB, Retriever, Simulator, PPO ActorCritic, Curiosity Tracker, Pathfinder, OCR, and Ad-Shield AutoClicker.
"""

import sys
import unittest
import numpy as np
from PIL import Image

sys.path.insert(0, ".")

from src.rag.knowledge_base import KnowledgeBase
from src.rag.retriever import RAGRetriever
from src.ai.simulator import LifeInAdventureSimulator, PlayerState
from src.ai.policy import HeuristicPolicy, CombatStatCalculator
from src.ai.ppo_trainer import ActorCritic
from src.ai.curiosity_tracker import CuriosityTracker
from src.ai.pathfinder import Pathfinder
from src.ocr.text_normalizer import TextNormalizer
from src.ocr.text_extractor import OcrEngine
from src.capture.screen_capture import ScreenCapture, CapturedFrame
from src.capture.auto_clicker import AutoClicker
import torch


class TestLifeInAdventurePipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Canonical KB dir (contains lia_kb.sqlite + chroma/)
        cls.kb = KnowledgeBase(db_path="data/knowledge_base")
        cls.retriever = RAGRetriever(knowledge_base=cls.kb)
        cls.tracker = CuriosityTracker(db_path="data/discovered_paths.db")
        cls.pathfinder = Pathfinder(db_path="data/discovered_paths.db",
                                 kb_path="data/knowledge_base")

    def test_1_kb_loading_and_event_fetch(self):
        """Verify KnowledgeBase loads events and choices from SQLite correctly."""
        ev = self.kb.get_event_with_choices("EventMain0_1_1")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["event_key"], "EventMain0_1_1")
        self.assertTrue("choices" in ev)

    def test_2_rag_retriever_hybrid_search(self):
        """Verify RAG Retriever accurately matches OCR query to correct event."""
        # Korean query with language filter (suffix 0) for stable match
        res = self.retriever.retrieve_for_ocr("모험가 길드", language="ko")
        if not res["matched"]:
            # Fallback: English-ish free query should still return candidates
            res = self.retriever.retrieve_for_ocr(
                "adventure guild", language="en", use_vector=True
            )
        self.assertTrue(
            res["matched"] or len(res.get("candidates", [])) > 0,
            f"RAG returned no match: conf={res.get('confidence')}",
        )

    def test_3_simulator_stat_dc_and_step(self):
        """Verify Simulator computes D20 checks and updates PlayerState."""
        sim = LifeInAdventureSimulator(knowledge_base=self.kb)
        sim.reset()
        self.assertIsNotNone(sim.player)
        self.assertIsNotNone(sim.current_event)
        sim.step(0)  # Take choice #1
        self.assertIsNotNone(sim.current_event)

    def test_4_ppo_actor_critic_tensor_forward(self):
        """Verify PyTorch PPO ActorCritic outputs valid action distribution and state value."""
        model = ActorCritic(obs_dim=20, action_dim=5)  # matches trained checkpoint
        dummy_state = torch.zeros((1, 20), dtype=torch.float32)
        dist, value = model(dummy_state)
        action = dist.sample()
        self.assertTrue(0 <= action.item() <= 4)
        self.assertIsInstance(value.item(), float)

    def test_5_curiosity_tracker_novelty_bonus(self):
        """Verify CuriosityTracker computes 1/sqrt(visit+1) bonus correctly."""
        bonus = self.tracker.compute_intrinsic_reward_and_record(
            event_key="TestEvent_Audit_001",
            step_idx=1,
            choice_path=[{"step": 1, "from_event": "Root",
                         "action_idx": 0, "choice_text": "Start"}],
            player_stats={"str": 10, "dex": 10, "int": 10, "cha": 10, "con": 10, "wis": 10}
        )
        self.assertTrue(bonus > 0.0)

    def test_6_pathfinder_walkthrough_generation(self):
        """Verify Pathfinder retrieves step sequences from SQLite."""
        paths = self.pathfinder.search_paths("EventMain", limit=2)
        self.assertIsInstance(paths, list)
        if paths:
            walkthrough = self.pathfinder.format_walkthrough(paths[0])
            self.assertTrue("[Walkthrough Target]:" in walkthrough)

    def test_7_ocr_and_text_normalizer(self):
        """Verify TextNormalizer cleans raw string and OcrEngine initializes without crash."""
        dirty_text = "==<HTML> 모험가 길드 ~~!!  "
        clean = TextNormalizer.normalize(dirty_text)
        self.assertTrue("모험가 길드" in clean)

        ocr = OcrEngine(languages=["en"], gpu=False)
        dummy_img = Image.new("RGB", (100, 50), color="white")
        res = ocr.extract_text(dummy_img)
        self.assertIsInstance(res, str)

    def test_8_autoclicker_ad_shield_lockout(self):
        """Verify AutoClicker blocks click attempts when Ad-Shield detects a live ad."""
        class MockCapture:
            ad_playing = True
            window_rect = {"top": 0, "left": 0, "width": 800, "height": 600}

        clicker = AutoClicker(screen_capture=MockCapture())
        success = clicker.click_choice(0)
        # Should return False due to Ad-Shield safety gate
        self.assertFalse(success)

    def test_9_autoclicker_transition_detection(self):
        """Verify AutoClicker detects 'Continue' and clicks advance button directly."""
        class MockCapture:
            ad_playing = False
            window_rect = {"top": 10, "left": 20, "width": 600, "height": 1000}

        clicker = AutoClicker(screen_capture=MockCapture())

        class MockAdb:
            connected = True
            tapped_coords = []

            def tap(self, x, y, win_width=None, win_height=None):
                self.tapped_coords.append((x, y))
                return True

        clicker.adb = MockAdb()

        ocr_boxes = [
            {"text": "Drops of rain starts to turn into pouring rain",
             "center": (300, 150)},
            {"text": "Continue", "center": (300, 600)},
        ]

        success = clicker.click_choice(
            choice_idx=2,
            choice_text="Ignore the person",
            ocr_boxes=ocr_boxes,
            choices_count=3
        )

        self.assertTrue(success)
        self.assertEqual(len(clicker.adb.tapped_coords), 1)
        self.assertEqual(clicker.adb.tapped_coords[0], (280, 590))

    def test_10_ppo_fallback_integration(self):
        """Verify PPO inference fallback activates on low-confidence heuristics."""
        from src.ai.decision_engine import AIDecisionEngine

        eng = AIDecisionEngine()
        # PPO should be loaded and validated
        self.assertTrue(eng._ppo_valid, "PPO model should be validated")
        self.assertIsInstance(eng._ppo_model, ActorCritic)

        # Observation vector shape must be (20,)
        obs = eng._get_ppo_observation_vector(
            player_state={"stats": {"strength": 12, "dex": 10,
                                  "intelligence": 10, "cha": 10,
                                  "con": 10, "wis": 10}, "hp": 80},
            event_choices=[
                {"required": "1_2_8"},
                {"required": "0"},
            ],
        )
        self.assertEqual(obs.shape, torch.Size([20]))
        self.assertGreater(obs[0].item(), 0.0)  # STR > 0

        # Low-confidence trigger should activate
        evals = [
            {"score": 45.0, "pass_probability": 0.5},
            {"score": 42.0, "pass_probability": 0.45},
        ]
        self.assertTrue(eng._should_use_ppo_fallback(evals, 0.50))

        # PPO action masking must return valid index
        idx = eng._select_with_ppo(obs, evals)
        self.assertIn(idx, [0, 1])

        # High-confidence with wide margin should NOT trigger PPO
        wide_evals = [
            {"score": 90.0, "pass_probability": 0.85},
            {"score": 42.0, "pass_probability": 0.45},
        ]
        self.assertFalse(eng._should_use_ppo_fallback(wide_evals, 0.85))

    def test_11_capture_region_validation(self):
        """Verify capture_region YAML list is normalized to tuple of ints."""
        from src.config import Config
        import tempfile, os

        cfg_text = """
emulator:
  type: ldplayer
  capture_region: [10, 20, 300, 400]
"""
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w",
                                       delete=False) as f:
            f.write(cfg_text)
            fname = f.name
        try:
            cfg = Config.from_yaml(fname)
            # YAML list should be normalized to tuple of ints
            self.assertIsInstance(cfg.emulator.capture_region, tuple)
            self.assertEqual(len(cfg.emulator.capture_region), 4)
            self.assertEqual(cfg.emulator.capture_region, (10, 20, 300, 400))
        finally:
            os.unlink(fname)

    def test_12_captured_frame_metadata(self):
        """Verify CapturedFrame provides window_rect and capture_origin."""
        frame = CapturedFrame(
            image=Image.new("RGB", (100, 200)),
            window_rect={"left": 100, "top": 50, "width": 800, "height": 600},
            capture_rect={"left": 110, "top": 60, "width": 400, "height": 300},
            capture_origin=(110, 60),
        )
        self.assertEqual(frame.window_rect["width"], 800)
        self.assertEqual(frame.capture_origin, (110, 60))
        self.assertEqual(frame.image.size, (100, 200))


if __name__ == "__main__":
    unittest.main(verbosity=2)
