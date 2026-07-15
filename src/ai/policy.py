"""
policy.py - AI Policies and Combat Stat Calculator for Life in Adventure.
Evaluates stat checks and estimates combat outcomes and Q-values using offline game formulas.
"""

import math
from typing import Dict, List, Any, Optional
import loguru

logger = loguru.logger

# Alignment keywords per language.
_ALIGNMENT_KEYWORDS = {
    "good": ["protect", "save", "help", "kind", "mercy", "honest", "hero", "善良", "善", "선", "양호"],
    "evil": ["kill", "attack", "ruthless", "dark", "evil", "steal", "chaos", "邪恶", "악", "적대"],
    "neutral": ["pragmatic", "practical", "opportunistic", "neutral", "实惠"],
}


class CombatStatCalculator:
    """
    Calculates combat win probability, expected damage dealt/received, and turn duration
    using formulas extracted from Life in Adventure Unity IL2CPP code.
    """

    @staticmethod
    def evaluate_combat(
        player_stats: Dict[str, int],
        player_hp: int,
        player_weapon_atk: int,
        monster_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Estimate combat outcome between player and monster."""
        m_hp = monster_info.get("hp", 50)
        m_name = monster_info.get("name_en") or monster_info.get("name_ko") or "Monster"

        p_str = player_stats.get("str", 10)
        p_dex = player_stats.get("dex", 10)
        p_con = player_stats.get("con", 10)

        effective_atk = max(1, int((p_str * 1.5) + (p_dex * 0.5) + player_weapon_atk))
        monster_atk = max(5, int(m_hp * 0.2))  # Monster atk scales with max HP
        player_def = p_con * 0.8

        dmg_to_monster = max(1.0, float(effective_atk))
        dmg_to_player = max(1.0, monster_atk - player_def * 0.5)

        turns_to_kill = math.ceil(m_hp / dmg_to_monster)
        turns_to_die = math.ceil(player_hp / dmg_to_player)

        win_prob = min(1.0, max(0.0, turns_to_die / (turns_to_kill + turns_to_die)))

        return {
            "monster_name": m_name,
            "win_probability": round(win_prob, 3),
            "expected_turns": turns_to_kill,
            "player_damage_per_turn": round(dmg_to_monster, 1),
            "monster_damage_per_turn": round(dmg_to_player, 1),
            "survives": turns_to_die > turns_to_kill,
        }


class HeuristicPolicy:
    """
    Fast offline heuristic policy evaluator that scores choices based on:
    - Stat success probability (D20 check)
    - Expected reward value
    - EXP pacing (rest penalty when EXP is high)
    - Alignment consistency with player
    """

    @staticmethod
    def _alignment_score(choice_text: str, player_alignment: int = 0) -> float:
        """
        Score alignment consistency: +2 for matching alignment keywords, -2 for opposing.
        player_alignment: -1 (evil) / 0 (neutral) / 1 (good)
        """
        text_lower = choice_text.lower()
        good_hits = sum(1 for kw in _ALIGNMENT_KEYWORDS["good"] if kw in text_lower)
        evil_hits = sum(1 for kw in _ALIGNMENT_KEYWORDS["evil"] if kw in text_lower)

        if player_alignment >= 1 and good_hits > evil_hits:
            return 3.0
        if player_alignment <= -1 and evil_hits > good_hits:
            return 3.0
        if player_alignment == 0 and (good_hits > 0 or evil_hits > 0):
            return 1.0  # neutral player gets small bonus for any moral choice
        return 0.0

    @staticmethod
    def _exp_score(choice_text: str, player_exp: int = 0) -> float:
        """
        EXP pacing penalty: discourage combat/risk when EXP is high (>80).
        Encourage rest/recovery when EXP is high so levels aren't wasted.
        """
        if player_exp < 50:
            return 0.0
        text_lower = choice_text.lower()
        # Rest/recovery bonus when EXP is high
        if player_exp >= 80:
            if any(kw in text_lower for kw in ["rest", "sleep", "camp", "recover", "heal", "숙박", "휴식"]):
                return 8.0
            if any(kw in text_lower for kw in ["fight", "battle", "combat", "attack", "전투", "전투"]):
                return -3.0  # slight penalty for risky fights at high EXP
        return 0.0

    @staticmethod
    def evaluate_choice(
        choice: Dict[str, Any],
        player_stats: Optional[Dict[str, int]] = None,
        player_exp: int = 0,
        player_alignment: int = 0,
    ) -> Dict[str, Any]:
        """
        Score a single choice option from 0.0 to 100.0.

        Components:
        - Stat pass probability × 50 (max 50 pts)
        - Expected reward value (max ~20 pts)
        - EXP pacing bonus/penalty (max ±8 pts)
        - Alignment bonus (max +3 pts)
        """
        if player_stats is None:
            player_stats = {"str": 10, "dex": 10, "int": 10, "cha": 10, "con": 10, "wis": 10}

        req = choice.get("required", "")
        text = choice.get("text", "")
        results = choice.get("results", [])

        # 1. Stat Check Pass Probability
        pass_prob = 1.0
        dc = 0
        stat_name = "Free Check"
        if req and req != "0":
            tokens = req.split("|")[0].split("_")
            stat_map = {0: "STR", 1: "DEX", 2: "INT", 3: "CHA", 4: "CON", 5: "WIS"}
            if len(tokens) >= 3:
                try:
                    s_id = int(tokens[0])
                    dc = int(tokens[2])
                    stat_name = stat_map.get(s_id, "STR")
                    p_val = player_stats.get(stat_name.lower(), 10)
                    mod = (p_val - 10) // 2
                    needed_roll = max(1, min(20, dc - mod))
                    pass_prob = (21 - needed_roll) / 20.0
                except ValueError:
                    pass

        # 2. Expected Reward Value
        expected_reward = 0.0
        for res in results:
            reward_str = str(res.get("reward", ""))
            if reward_str:
                for part in reward_str.split("|"):
                    tokens = part.split("_")
                    if len(tokens) >= 3:
                        try:
                            r_cat = int(tokens[0])
                            r_val = int(tokens[2])
                            if r_cat == 0:  # HP / Stat gain
                                expected_reward += r_val * 2.0
                            elif r_cat == 1:  # Gold / XP
                                expected_reward += r_val * 0.1
                        except ValueError:
                            pass

        # 3. EXP pacing bonus/penalty (Phase P2.2)
        exp_adj = HeuristicPolicy._exp_score(text, player_exp)

        # 4. Alignment consistency bonus (Phase P2.2)
        align_adj = HeuristicPolicy._alignment_score(text, player_alignment)

        # Combine into total score
        total_score = (pass_prob * 50.0) + expected_reward + exp_adj + align_adj

        return {
            "choice_idx": choice.get("choice_idx", 0),
            "text": text,
            "pass_probability": round(pass_prob, 3),
            "stat_checked": stat_name,
            "dc": dc,
            "expected_reward": round(expected_reward, 2),
            "exp_adj": round(exp_adj, 2),
            "align_adj": round(align_adj, 2),
            "score": round(total_score, 2),
        }
