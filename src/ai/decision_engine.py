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
        # Prefers legacy ActorCritic .pt; falls back to SB3 .zip if present.
        self._ppo_model = None
        self._ppo_valid = False
        self._ppo_backend = None  # "actor_critic" | "sb3"
        self._load_ppo_if_available()

    # ------------------------------------------------------------------ #
    #  Phase P2.3 — PPO Inference Fallback
    # ------------------------------------------------------------------ #

    def _load_ppo_if_available(self) -> None:
        """
        Load PPO for low-confidence fallback.
        Priority: legacy ActorCritic .pt (ppo_curiosity_latest.pt) → SB3 .zip.
        """
        if self._load_legacy_actor_critic():
            return
        self._load_sb3_model()

    def _load_legacy_actor_critic(self) -> bool:
        """Load custom ActorCritic from ppo_curiosity_latest.pt (epoch-50 checkpoint)."""
        ckpt_path = "data/models/ppo_curiosity_latest.pt"
        if not os.path.exists(ckpt_path):
            return False
        try:
            import torch
            ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
            if not isinstance(ckpt, dict) or "policy_state_dict" not in ckpt:
                logger.warning("PPO checkpoint: invalid structure, skipping.")
                return False

            from src.ai.ppo_trainer import ActorCritic
            policy = ActorCritic(obs_dim=20, action_dim=5, hidden_dim=128)
            policy_sd = ckpt["policy_state_dict"]
            model_sd = policy.state_dict()
            shape_ok = all(
                policy_sd[k].shape == model_sd[k].shape
                for k in policy_sd if k in model_sd
            )
            if not shape_ok:
                logger.warning("PPO checkpoint: shape mismatch for ActorCritic.")
                return False

            policy.load_state_dict(policy_sd)
            policy.eval()
            self._ppo_model = policy
            self._ppo_valid = True
            self._ppo_backend = "actor_critic"
            logger.info(
                f"PPO Actor-Critic loaded (epoch={ckpt.get('epoch', '?')}, "
                f"discoveries={ckpt.get('total_discoveries', '?')})."
            )
            return True
        except Exception as e:
            logger.warning(f"Could not load legacy PPO checkpoint: {e}")
            return False

    def _load_sb3_model(self) -> bool:
        """Load Stable-Baselines3 PPO zip if present (new training path)."""
        for path in ("data/models/ppo_sb3_latest.zip", "data/models/ppo_sb3_latest"):
            zip_path = path if path.endswith(".zip") else f"{path}.zip"
            if not os.path.exists(zip_path) and not os.path.exists(path):
                continue
            try:
                from stable_baselines3 import PPO
                load_target = path if os.path.exists(path) else zip_path.replace(".zip", "")
                model = PPO.load(load_target, device="cpu")
                self._ppo_model = model
                self._ppo_valid = True
                self._ppo_backend = "sb3"
                logger.info(f"SB3 PPO loaded from {load_target}.")
                return True
            except Exception as e:
                logger.warning(f"Could not load SB3 PPO from {path}: {e}")
        return False

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
        # Accept nested "stats", top-level, and aliases (str/strength, int/intelligence)
        if isinstance(player_state, dict) and "stats" in player_state:
            stats = dict(player_state["stats"] or {})
        else:
            stats = dict(player_state or {})

        def _stat(short: str, *aliases: str, default: float = 10.0) -> float:
            for k in (short, *aliases):
                if k in stats and stats[k] is not None:
                    return float(stats[k])
            return default

        vec[0] = _stat("str", "strength") / 20.0
        vec[1] = _stat("dex") / 20.0
        vec[2] = _stat("int", "intelligence") / 20.0
        vec[3] = _stat("cha") / 20.0
        vec[4] = _stat("con") / 20.0
        vec[5] = _stat("wis") / 20.0

        # Index 6-9: HP, sanity, gold, step (top-level or inside stats)
        root = player_state if isinstance(player_state, dict) else {}
        hp = root.get("hp", stats.get("hp", 100)) or 100
        vec[6] = float(hp) / 100.0

        sanity = root.get("sanity", stats.get("sanity", 100)) or 100
        vec[7] = float(sanity) / 100.0

        gold = root.get("gold", stats.get("gold", 50)) or 50
        vec[8] = min(10.0, float(gold) / 100.0)

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
        PPO forward pass with action masking. Supports ActorCritic (.pt) and SB3.
        Returns index in [0, len(evaluations)-1], or heuristic best on error.
        """
        import torch
        from torch.distributions.categorical import Categorical

        num_visible = len(evaluations)
        if num_visible <= 0:
            return 0

        try:
            if self._ppo_backend == "sb3":
                import numpy as np
                obs_np = obs_vector.detach().cpu().numpy().astype(np.float32)
                if obs_np.ndim == 1:
                    obs_np = obs_np.reshape(1, -1)
                action, _ = self._ppo_model.predict(obs_np, deterministic=False)
                ppo_action = int(np.asarray(action).reshape(-1)[0])
                ppo_action = max(0, min(ppo_action, num_visible - 1))
                logger.info(
                    f"SB3 PPO fallback: action {ppo_action} (num_visible={num_visible})"
                )
                return ppo_action

            # Legacy ActorCritic path
            with torch.no_grad():
                features = self._ppo_model.backbone(obs_vector)
                logits = self._ppo_model.actor(features)

            mask = torch.full_like(logits, float("-inf"))
            mask[:num_visible] = 0.0
            dist = Categorical(logits=logits + mask)
            ppo_action = int(dist.sample().item())
            logger.info(
                f"PPO fallback: selected action {ppo_action} "
                f"(prob={float(dist.probs[ppo_action].item()):.3f}, num_visible={num_visible})"
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
