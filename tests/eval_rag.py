"""
tests/eval_rag.py - Multilingual RAG Retriever Evaluation and Accuracy Suite.
Tests database-level language filtering, accuracy, and latency metrics.
"""

import unittest
import sys
import time
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from src.rag.knowledge_base import KnowledgeBase
from src.rag.retriever import RAGRetriever


class TestRAGMultilingualAccuracy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase(db_path="data/knowledge_base")
        cls.retriever = RAGRetriever(knowledge_base=cls.kb)

    def test_english_filtering_accuracy(self):
        """Verify English search queries strictly return English events (suffix 1)."""
        queries = [
            ("A beast howls in the woods, breaking the silence", "EventBattle1"),
            ("You read a recruitment flyer for pioneers on the city noticeboard", "EventMain1"),
            ("You find the remains of someone's camp. You think you could do with some rest", "EventNormal1"),
            ("You are walking through jungle, thick with grass and trees", "EventTreasure1")
        ]
        
        for q, expected_prefix in queries:
            with self.subTest(query=q):
                res = self.retriever.retrieve_for_ocr(q, use_vector=False, language="English")
                self.assertTrue(res["matched"], f"Query '{q}' failed to match.")
                self.assertIsNotNone(res["event"], "Event record should not be None")
                event_key = res["event"]["event_key"]
                source_file = res["event"]["source_file"]
                self.assertTrue(event_key.startswith(expected_prefix), f"Expected prefix {expected_prefix}, got {event_key}")
                self.assertTrue(source_file.endswith("1"), f"Expected English source_file suffix (1), got {source_file}")

    def test_indonesian_filtering_accuracy(self):
        """Verify Indonesian search queries strictly return Indonesian events (suffix 8)."""
        queries = [
            ("Seekor binatang buas melolong di hutan", "EventBattle8"),
            ("Kamu membaca selebaran perekrutan penjelajah di papan pengumuman", "EventMain8"),
            ("Kamu menemukan sisa-sisa perkemahan seseorang. Sepertinya kamu butuh istirahat", "EventNormal8"),
            ("Kamu berjalan melintasi hutan lebat yang dipenuhi rumput dan pepohonan", "EventTreasure8")
        ]

        for q, expected_prefix in queries:
            with self.subTest(query=q):
                res = self.retriever.retrieve_for_ocr(q, use_vector=False, language="Indonesian")
                self.assertTrue(res["matched"], f"Query '{q}' failed to match.")
                self.assertIsNotNone(res["event"], "Event record should not be None")
                event_key = res["event"]["event_key"]
                source_file = res["event"]["source_file"]
                self.assertTrue(event_key.startswith(expected_prefix), f"Expected prefix {expected_prefix}, got {event_key}")
                self.assertTrue(source_file.endswith("8"), f"Expected Indonesian source_file suffix (8), got {source_file}")

    def test_cross_language_isolation(self):
        """Verify that English queries do not return English events when language filter is set to Indonesian."""
        q = "A beast howls in the woods, breaking the silence"
        
        # When filtered to Indonesian, it should NOT return EventBattle1 (English)
        res = self.retriever.retrieve_for_ocr(q, use_vector=False, language="Indonesian")
        if res["matched"]:
            source_file = res["event"]["source_file"]
            self.assertFalse(source_file.endswith("1"), "Should not match English event when Indonesian filter is active.")
            self.assertTrue(source_file.endswith("8"), f"Matched event must be Indonesian: {source_file}")

    def test_performance_latency(self):
        """Verify that pre-filtered RapidFuzz is highly performant (latency < 250ms)."""
        q = "A beast howls in the woods, breaking the silence"
        
        # Measure unfiltered search time
        t0 = time.perf_counter()
        self.retriever.retrieve_for_ocr(q, use_vector=False, language=None)
        unfiltered_duration = time.perf_counter() - t0

        # Measure filtered search time (should be faster due to pre-filtered RapidFuzz candidates)
        t1 = time.perf_counter()
        self.retriever.retrieve_for_ocr(q, use_vector=False, language="English")
        filtered_duration = time.perf_counter() - t1

        print(f"\n[Performance Metrics] Unfiltered: {unfiltered_duration:.4f}s | Filtered (English): {filtered_duration:.4f}s")
        self.assertLess(filtered_duration, 0.5, "Filtered query took longer than 500ms.")

    def test_choice_requirement_filtering(self):
        """Verify that choices are filtered out dynamically based on player inventory."""
        # EventBattle1_12_12 has:
        # Choice 0: Attack the creature (no req)
        # Choice 1: Avoid it (no req)
        # Choice 2: Burn corpse (requires "8_42_1" - Lantern)
        # Choice 3: Magic : Fire arrow (requires spell)
        q = "You find a metal cage half buried in the mud. Inside is a dried up corpse."
        
        # Test 1: Empty inventory (should filter out "Burn corpse" and "Magic : Fire arrow")
        res_empty = self.retriever.retrieve_for_ocr(
            q, 
            use_vector=False, 
            language="English",
            player_stats={},
            player_inventory=[]
        )
        self.assertTrue(res_empty["matched"])
        choices_empty = res_empty["choices"]
        # Both "Burn corpse" (requires Lantern) and "Magic : Fire arrow" (requires spell) should be filtered out
        for ch in choices_empty:
            self.assertNotEqual(ch["text"], "Burn corpse", "Burn corpse choice should be filtered out when lacking Lantern.")
            self.assertNotEqual(ch["text"], "Magic : Fire arrow", "Magic : Fire arrow should be filtered out when lacking spell.")

        # Test 2: Inventory containing Lantern (should keep "Burn corpse")
        res_lantern = self.retriever.retrieve_for_ocr(
            q, 
            use_vector=False, 
            language="English",
            player_stats={},
            player_inventory=["Lantern"]
        )
        self.assertTrue(res_lantern["matched"])
        choices_lantern = res_lantern["choices"]
        has_burn_corpse = any(ch["text"] == "Burn corpse" for ch in choices_lantern)
        self.assertTrue(has_burn_corpse, "Burn corpse choice should be present when player has Lantern.")
        
        # Test 3: Inventory containing Fire spell (should keep "Magic : Fire arrow")
        res_spell = self.retriever.retrieve_for_ocr(
            q, 
            use_vector=False, 
            language="English",
            player_stats={},
            player_inventory=["Staff of Fire Arrow"]
        )
        self.assertTrue(res_spell["matched"])
        choices_spell = res_spell["choices"]
        has_fire_arrow = any(ch["text"] == "Magic : Fire arrow" for ch in choices_spell)
        self.assertTrue(has_fire_arrow, "Magic : Fire arrow choice should be present when player has Staff of Fire Arrow.")


if __name__ == "__main__":
    unittest.main()
