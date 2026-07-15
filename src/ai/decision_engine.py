"""
decision_engine.py - AI Decision Engine for Life in Adventure.
Combines fast offline RL/Heuristic policy evaluation with optional LLM (Claude/OpenAI)
deep reasoning to provide best quest choice recommendations and combat strategy.

Phase P2.3: PPO Actor-Critic is loaded as a low-confidence heuristic fallback.
Inference uses a validated 20-dimensional observation vector derived from player state
and the currently visible event choices.
"""

import os
import json
from typing import Dict, List, Any, Optional
import loguru

from src.ai.policy import CombatStatCalculator, HeuristicPolicy
from src.core.response_cache import ResponseCache

logger = loguru.logger

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


class AIDecisionEngine:
    """
    Core decision-making engine for the quest assistant.
    Evaluates retrieved event options and outputs win-rate probabilities and best choices.
    """

    def __init__(
        self,
        provider: str = "claude",
        model: str = "claude-3-5-sonnet-20241022",
        verbosity: str = "verbose",
        ppo_confidence_threshold: float = 0.55,
        ppo_score_margin_threshold: float = 5.0,
    ):
        self.provider = provider
        self.model = model
        self.verbosity = verbosity

        # Low-confidence trigger thresholds (Phase P2.3)
        self._ppo_confidence_threshold = ppo_confidence_threshold
        self._ppo_score_margin_threshold = ppo_score_margin_threshold

        self.anthropic_client = None
        if _ANTHROPIC_AVAILABLE and os.getenv("ANTHROPIC_API_KEY"):
            try:
                self.anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                logger.info(f"Initialized Anthropic client for model {model}")
            except Exception as e:
                logger.warning(f"Failed initializing Anthropic client: {e}")

        # Persistent LRU+TTL cache for AI evaluations.
        # Version "v2_" distinguishes entries that may include PPO fallback results.
        self._eval_cache = ResponseCache(maxsize=500, ttl=3600.0, persist_path="data/ai_eval_cache.json")

        # Load PPO checkpoint as low-confidence fallback (Phase P2.3).
        self._ppo_model = None
        self._ppo_valid = False
        self._load_ppo_if_available()

    # ------------------------------------------------------------------ #
    #  Phase P2.3 — PPO Inference Fallback
    # ------------------------------------------------------------------ #

    def _load_ppo_if_available(self) -> None:
        """
        Load the PPO Actor-Critic checkpoint if it exists and is compatible.
        Instantiates ActorCritic, loads policy_state_dict, and validates shapes.
        Sets self._ppo_model to the validated ActorCritic instance (or None on failure).
        """
        ckpt_path = "data/models/ppo_curiosity_latest.pt"
        if not os.path.exists(ckpt_path):
            return
        try:
            import torch
            ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)

            # Validate checkpoint structure
            if not isinstance(ckpt, dict):
                logger.warning("PPO checkpoint: not a dict, skipping.")
                return
            if "policy_state_dict" not in ckpt:
                logger.warning("PPO checkpoint: missing 'policy_state_dict', skipping.")
                return

            # Instantiate the same ActorCritic architecture used during training.
            from src.ai.ppo_trainer import ActorCritic
            policy = ActorCritic(obs_dim=20, action_dim=5, hidden_dim=128)

            # Validate tensor shapes before loading
            policy_sd = ckpt["policy_state_dict"]
            model_sd = policy.state_dict()
            shape_ok = all(
                policy_sd[k].shape == model_sd[k].shape
                for k in policy_sd
                if k in model_sd
            )
            if not shape_ok:
                logger.warning(
                    "PPO checkpoint: policy_state_dict shapes do not match "
                    f"expected ActorCritic(obs_dim=20, action_dim=5). "
                    "Check that checkpoint was trained with the same architecture."
                )
                return

            policy.load_state_dict(policy_sd)
            policy.eval()  # inference mode — disables dropout/batchnorm
            self._ppo_model = policy
            self._ppo_valid = True
            epoch = ckpt.get("epoch", "?")
            discoveries = ckpt.get("total_discoveries", "?")
            logger.info(
                f"PPO Actor-Critic loaded (epoch={epoch}, discoveries={discoveries}). "
                f"Valid inference: obs_dim=20, action_dim=5."
            )
        except Exception as e:
            logger.warning(f"Could not load PPO checkpoint: {e}")
            self._ppo_model = None
            self._ppo_valid = False

    def _get_ppo_observation_vector(
        self,
        player_state: Dict[str, Any],
        event_choices: List[Dict[str, Any]],
        num_slots: int = 5,
    ) -> "torch.Tensor":
        """
        Encode live game state into the same 20-dim observation vector used
        during PPO training (mirrors LifeInAdventureEnv._get_obs_vector).

        Indices 0-5:  six stats / 20.0
        Index  6:     HP / 100.0
        Index  7:     sanity / 100.0
        Index  8:     gold / 100.0, capped at 10.0
        Index  9:     step / 100.0
        Indices 10-14: choice DCs / 20.0  (0 if no choice)
        Indices 15-19: choice stat IDs   (0 if no choice)
        """
        import torch

        vec = torch.zeros(20, dtype=torch.float32)

        # Player stats (indices 0-5)
        # player_state may have stats at top level OR nested under "stats" key
        if isinstance(player_state, dict) and "stats" in player_state:
            stats = player_state["stats"]
        else:
            stats = player_state or {}
        vec[0] = (stats.get("str", 10) or 10) / 20.0
        vec[1] = (stats.get("dex", 10) or 10) / 20.0
        vec[2] = (stats.get("int", 10) or 10) / 20.0
        vec[3] = (stats.get("cha", 10) or 10) / 20.0
        vec[4] = (stats.get("con", 10) or 10) / 20.0
        vec[5] = (stats.get("wis", 10) or 10) / 20.0

        # Index 6-9: HP, sanity, gold, step — also read from stats dict
        # (in the LiA data model these are all player character attributes)
        hp = stats.get("hp", 100)
        vec[6] = hp / 100.0

        sanity = stats.get("sanity", 100)
        vec[7] = sanity / 100.0

        gold = stats.get("gold", 50)
        vec[8] = min(10.0, gold / 100.0)

        step = (player_state or {}).get("step", 0)
        vec[9] = step / 100.0

        # Indices 10-19: choice DCs and stat IDs
        for i in range(min(num_slots, len(event_choices))):
            req = event_choices[i].get("required", "") or ""
            if req and req != "0":
                tokens = req.split("|")[0].split("_")
                if len(tokens) >= 3:
                    try:
                        stat_id = float(tokens[0])
                        dc = float(tokens[2]) / 20.0
                        vec[10 + i] = dc
                        vec[15 + i] = stat_id
                    except ValueError:
                        pass

        return vec

    def _should_use_ppo_fallback(
        self,
        evaluations: List[Dict[str, Any]],
        confidence: float,
    ) -> bool:
        """
        Decide whether to invoke the PPO Actor-Critic for a second opinion.
        Triggers when:
          - heuristic confidence (pass_probability) is below threshold, OR
          - best-vs-second-best score margin is narrow (indicates weak preference)
        """
        if not self._ppo_valid:
            return False

        if confidence < self._ppo_confidence_threshold:
            return True

        if len(evaluations) < 2:
            return False

        scores = sorted([ev.get("score", 0.0) for ev in evaluations], reverse=True)
        margin = scores[0] - scores[1] if len(scores) >= 2 else 0.0
        if margin < self._ppo_score_margin_threshold:
            return True

        return False

    def _select_with_ppo(
        self,
        obs_vector: "torch.Tensor",
        evaluations: List[Dict[str, Any]],
    ) -> int:
        """
        Run the PPO Actor-Critic forward pass and return a visible (reindexed)
        choice index with action masking applied.

        Only returns an index in range [0, len(evaluations)-1].
        Returns the heuristic best index on any error.
        """
        import torch
        from torch.distributions.categorical import Categorical

        try:
            with torch.no_grad():
                features = self._ppo_model.backbone(obs_vector)
                logits = self._ppo_model.actor(features)  # shape (5,)

            num_visible = len(evaluations)
            # Mask: set logits for unavailable actions (>= num_visible) to -inf
            mask = torch.full_like(logits, float("-inf"))
            mask[:num_visible] = 0.0
            masked_logits = logits + mask

            dist = Categorical(logits=masked_logits)
            ppo_action = int(dist.sample().item())
            ppo_prob = float(dist.probs[ppo_action].item())

            logger.info(
                f"PPO fallback: selected action {ppo_action} "
                f"(prob={ppo_prob:.3f}, num_visible={num_visible})"
            )
            return ppo_action
        except Exception as e:
            logger.warning(f"PPO inference failed: {e}. Using heuristic.")
            return evaluations[0].get("original_idx", 0) if evaluations else 0

    # ------------------------------------------------------------------ #
    #  Main recommendation API
    # ------------------------------------------------------------------ #

    def recommend_choice(
        self,
        retrieved_event: Dict[str, Any],
        player_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate all available choices for the given event and recommend the optimal option.
        Uses offline Heuristic/RL Policy evaluation + optional LLM rationale, with smart caching.
        """
        if not retrieved_event or not retrieved_event.get("choices"):
            return {
                "recommended_choice_idx": -1,
                "recommended_choice_text": "No choices detected",
                "confidence": 0.0,
                "reasoning": "Could not identify choices for this event.",
                "choice_evaluations": []
            }

        event_key = retrieved_event.get("event_key", "")
        player_stats = player_state.get("stats", {}) if player_state else None
        player_exp = player_state.get("player_exp", 0) if player_state else 0
        player_alignment = player_state.get("player_alignment", 0) if player_state else 0
        # Cache key version "v2_" includes PPO fallback potential
        cache_key = f"v2_{event_key}_{json.dumps(player_stats, sort_keys=True)}_{player_exp}_{player_alignment}" if player_stats else f"v2_{event_key}"

        if (cached := self._eval_cache.get(cache_key)) is not None:
            return cached

        choices = retrieved_event["choices"]
        evaluations = []
        best_idx = 0
        best_score = -999.0

        for idx, ch in enumerate(choices):
            ev_res = HeuristicPolicy.evaluate_choice(
                ch,
                player_stats=player_stats,
                player_exp=player_exp,
                player_alignment=player_alignment,
            )
            evaluations.append(ev_res)
            if ev_res["score"] > best_score:
                best_score = ev_res["score"]
                best_idx = idx

        # Current confidence = pass_probability of best choice (0-1 scale)
        best_choice = evaluations[best_idx] if evaluations else {}
        current_confidence = round(
            min(1.0, max(0.0, best_choice.get("pass_probability", 0.8) * 100.0) / 100.0), 2
        )

        # ── Phase P2.3: Low-confidence PPO fallback ──────────────────────
        decision_source = "heuristic"
        if self._should_use_ppo_fallback(evaluations, current_confidence):
            try:
                obs = self._get_ppo_observation_vector(
                    player_state or {},
                    choices,
                    num_slots=5,
                )
                ppo_idx = self._select_with_ppo(obs, evaluations)
                # Only override if PPO selects a different, valid choice
                if ppo_idx != best_idx and 0 <= ppo_idx < len(evaluations):
                    heuristic_idx = best_idx
                    best_idx = ppo_idx
                    best_choice = evaluations[best_idx]
                    decision_source = "ppo_fallback"
                    logger.info(
                        f"PPO override: heuristic chose #{heuristic_idx} "
                        f"(score={evaluations[heuristic_idx]['score']:.1f}), "
                        f"PPO chose #{ppo_idx} (score={evaluations[ppo_idx]['score']:.1f})"
                    )
            except Exception as e:
                logger.warning(f"PPO fallback inference error: {e}. Using heuristic result.")

        # Mark best choice
        for idx, ev in enumerate(evaluations):
            ev["recommended"] = (idx == best_idx)

        reasoning = (
            f"Recommended '{best_choice.get('text', '')}' (Score: {best_choice.get('score')}/100). "
            f"Stat check: {best_choice.get('stat_checked')} "
            f"(Pass chance: {best_choice.get('pass_probability', 0)*100:.0f}%). "
            f"Expected utility delta: +{best_choice.get('expected_reward', 0)}."
        )

        res = {
            "recommended_choice_idx": best_idx,
            "recommended_choice_text": best_choice.get("text", ""),
            "confidence": current_confidence,
            "reasoning": reasoning,
            "choice_evaluations": evaluations,
            # Diagnostic — not consumed by UI but useful for logging
            "_decision_source": decision_source,
        }
        self._eval_cache.set(cache_key, res)
        return res

    def evaluate_combat(
        self,
        player_stats: Dict[str, int],
        player_hp: int,
        player_weapon_atk: int,
        monster_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate exact win probability and combat turns against a monster."""
        return CombatStatCalculator.evaluate_combat(player_stats, player_hp, player_weapon_atk, monster_info)
