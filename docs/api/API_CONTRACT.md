# API Contract

> AI Engine interface contracts, prompts, and response formats for LifeInAdventure-Tools.
>
> **v1.1 (2026-07-06)**: Patches per `docs/review/REVIEW_REPORT.md`:
> - C1: System prompt now includes EXP MANAGEMENT RULE (CRITICAL) + new fields in GameStateContext
> - C3: Stat range 1-27+ (Super X+2 unlocks at 27); power points formula revealed
> - C2: Alignment model described as 5 discrete tiers (not linear gauge)

---

## 1. Overview

The AI Engine provides a unified interface for getting game recommendations. It accepts the current game state and player context, queries the RAG knowledge base, and returns structured recommendations.

### 1.1 High-Level Flow

```
Capture → OCR → RAG Retrieval → [GameStateContext]
                                          │
                                          ▼
                              ┌──────────────────────┐
                              │   AI Decision Engine  │
                              │   (ZCode / OpenAI)    │
                              └──────────┬───────────┘
                                         │
                                         ▼
                              ┌──────────────────────┐
                              │  AIRecommendation     │
                              │  (Structured JSON)   │
                              └──────────────────────┘
```

---

## 2. AI Provider Interfaces

### 2.1 ZCode (Claude via Ollagon Gateway)

```python
# src/ai/providers/zcode_provider.py

class ZCodeProvider:
    """
    ZCode / Ollagon Gateway — uses Anthropic API compatible interface.
    Endpoint: https://gateway.olagon.site/anthropic
    """

    BASE_URL = "https://gateway.olagon.site/anthropic"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: str | None = None):
        # API key auto-detected from environment:
        # ZCODE_API_KEY env var
        # Or from ZCode config at ~/.zcode/v2/config.json
        self.client = anthropic.Anthropic(
            base_url=self.BASE_URL,
            api_key=api_key,
        )

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        model: str = "claude-opus-4-6",
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """
        Send a completion request to Claude via ZCode gateway.
        """
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ],
        )
        return response.content[0].text
```

### 2.2 OpenAI Provider

```python
# src/ai/providers/openai_provider.py

class OpenAIProvider:
    """
    OpenAI API — GPT-4o-mini fallback.
    """

    def __init__(self, api_key: str | None = None):
        self.client = openai.OpenAI(
            api_key=api_key,
        )

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        response = self.client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content
```

### 2.3 Ollama Provider

```python
# src/ai/providers/ollama_provider.py

class OllamaProvider:
    """
    Ollama local LLM — fully offline, no API key needed.
    """

    BASE_URL = "http://localhost:11434"

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or self.BASE_URL

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        model: str = "llama3.2",
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        import httpx
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                },
            },
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
```

---

## 3. Data Transfer Objects (DTOs)

### 3.1 Request DTOs

```python
# src/ai/dto.py

@dataclass
class GameStateContext:
    """
    Complete game state for AI decision making.
    Built by RAG retriever from capture + knowledge base.
    """

    # ─── Raw Input ─────────────────────────────────────────────
    raw_quest_text: str                   # Raw OCR text from screenshot
    raw_choices: list[str]               # Raw choice texts from OCR
    detected_quest_title: str | None      # Quest title if recognized
    detected_language: str                 # Game language (en/kr/id)

    # ─── RAG Matches ──────────────────────────────────────────
    matched_quest: Quest | None            # Best matching quest from KB
    matched_events: list[Event]            # Top matching events from KB
    matched_choices: list[Choice]          # Top matching choices from KB
    matched_epilogues: list[Epilogue]      # Related epilogues
    retrieval_confidence: float            # 0.0-1.0, overall match confidence

    # ─── Player State (optional) ───────────────────────────────
    player_stats: PlayerStats | None        # Current player stats
    player_level: int | None
    player_gold: int | None
    player_alignment: int | None            # Raw -100..+100; use Alignment.from_int() for tier
    player_alignment_tier: str | None      # "good" | "moral" | "neutral" | "impure" | "evil"
    player_background: str | None

    # ─── EXP State (CRITICAL per REVIEW_REPORT C1) ─────────────
    current_exp: int | None                 # 0-100; None if not detected from OCR / not input
    exp_remaining: int | None               # 100 - current_exp (computed)
    target_epilogue_id: str | None          # User's target ending (for EXP Fasting strategy)
    exp_fasting_mode: bool = False          # True if player follows EXP Fasting (avoid EXP)

    # ─── Context Metadata ──────────────────────────────────────
    kb_version: str                        # Knowledge base version
    game_version: str                      # Game version
    timestamp: datetime                    # When this context was built

    # ─── Cache ────────────────────────────────────────────────
    cache_key: str | None                  # For response caching

    def compute_cache_key(self) -> str:
        """Generate cache key from quest text + normalized choices."""
        import hashlib
        text = self.raw_quest_text + "|".join(sorted(self.raw_choices))
        return hashlib.md5(text.encode()).hexdigest()


@dataclass
class PlayerStats:
    """Player's current stat values."""
    str: int | None = None
    dex: int | None = None
    int: int | None = None
    cha: int | None = None
    con: int | None = None
    wis: int | None = None

    def to_display_dict(self) -> dict[str, int | None]:
        return {
            "STR": self.str,
            "DEX": self.dex,
            "INT": self.int,
            "CHA": self.cha,
            "CON": self.con,
            "WIS": self.wis,
        }
```

### 3.2 Response DTOs

```python
@dataclass
class AIRecommendation:
    """
    AI-generated recommendation for current game state.
    """

    # ─── Identification ────────────────────────────────────────
    quest_identified: str                  # Quest name if recognized, else "Unknown Quest"
    confidence: float                      # 0.0-1.0, confidence in identification

    # ─── Analysis ──────────────────────────────────────────────
    choice_analysis: list[ChoiceAnalysis]   # Analysis of each available choice
    best_choice: str                        # Choice ID of recommended choice

    # ─── Recommendation ────────────────────────────────────────
    reasoning: str                         # Short explanation of recommendation
    risk_level: RiskLevel                  # safe | moderate | risky

    # ─── Tactical ──────────────────────────────────────────────
    stat_tips: list[str]                   # Tips based on player stats
    alternative_paths: list[str]           # Other viable choices

    # ─── Raw ──────────────────────────────────────────────────
    raw_response: str                       # Full AI response text (for debug/logging)

    # ─── Metadata ─────────────────────────────────────────────
    model_used: str                        # e.g. "claude-opus-4-6"
    provider: str                          # "zcode" | "openai" | "ollama"
    latency_ms: int                        # API response time in milliseconds
    cached: bool                           # True if served from cache
    timestamp: datetime

    # ─── UI Formatting ─────────────────────────────────────────
    def to_overlay_format(self) -> dict:
        """Convert to format expected by overlay UI."""
        return {
            "quest": self.quest_identified,
            "confidence": f"{self.confidence:.0%}",
            "choices": [ca.to_dict() for ca in self.choice_analysis],
            "best": self.best_choice,
            "reasoning": self.reasoning,
            "risk": self.risk_level.value,
            "tips": self.stat_tips,
        }


@dataclass
class ChoiceAnalysis:
    """Analysis of a single choice option."""
    choice_id: str                         # e.g. "ch_haunted_01_a"
    choice_text: str                       # Original choice text
    choice_letter: str                     # "A", "B", "C", etc.

    # ─── Analysis ──────────────────────────────────────────────
    stat_check: str | None                 # "DEX 5+" or None
    stat_description: str | None            # "Sneak past the guardian"
    success_probability: str                # "High", "Medium", "Low", "N/A"

    # ─── Outcomes ──────────────────────────────────────────────
    success_outcome: str | None            # What happens on success
    fail_outcome: str | None               # What happens on fail
    rewards: str | None                   # Potential rewards
    risks: str | None                      # Potential risks

    # ─── Ranking ──────────────────────────────────────────────
    rank: int                              # 1 = best, 2 = second best, etc.
    is_recommended: bool                   # True if this is the top choice
    score: float                           # 0.0-1.0, internal recommendation score

    def to_dict(self) -> dict:
        return {
            "id": self.choice_id,
            "letter": self.choice_letter,
            "text": self.choice_text,
            "stat_check": self.stat_check,
            "stat_desc": self.stat_description,
            "prob": self.success_probability,
            "success": self.success_outcome,
            "fail": self.fail_outcome,
            "rewards": self.rewards,
            "risks": self.risks,
            "rank": self.rank,
            "recommended": self.is_recommended,
        }


class RiskLevel(str, Enum):
    SAFE = "safe"        # Minimal risk, good outcome either way
    MODERATE = "moderate"  # Some risk, but manageable
    RISKY = "risky"      # High risk of bad outcome
    UNKNOWN = "unknown"   # Insufficient data
```

---

## 4. Prompt Templates

### 4.1 System Prompt

```text
SYSTEM_PROMPT = """
You are an expert tactical advisor for the text-based RPG "Life in Adventure"
by Studio Wheel. You have deep knowledge of D&D-style mechanics and the
specific game content from version 1.2.42.

YOUR ROLE:
- Analyze the current game situation from OCR text
- Identify the quest and available choices
- Evaluate each choice based on stat requirements and potential outcomes
- Recommend the optimal choice given the player's stats
- Warn about risks and suggest alternatives

GAME MECHANICS YOU KNOW:
- 6 Stats: STR (Strength), DEX (Dexterity), INT (Intelligence),
  CHA (Charisma), CON (Constitution), WIS (Wisdom)
- Range: 1-27+ (Super X+1 unlock at 18, Super X+2 unlock at 27). Average is 10.
- Stat Modifier: (stat - 10) / 2, rounded down.
  (10→+0, 12→+1, 14→+2, 16→+3, 18→+4, 20→+5, 27→+8 ish)
- Stat Check: Roll 1d20 + stat_modifier + Power Points (from equipment)
  vs effective DC. Hybrid system, NOT pure D&D DC.
  Example: DC 10 on DEX check → need DEX 14+ (mod +2) for likely success.
- Alignment: 5 discrete tiers — Good / Moral / Neutral / Impure / Evil.
  Stored internally as -100..+100, but ONLY tier matters for unlocks.
  Trait deltas: Bright +20, Dark -20, Innately Good/Evil +/-20, Savior/Butcher +/-20.
  Do NOT report raw int to user; report tier name.
- EXP bar fills based on choices → max 100 → triggers epilogue (adventure end).
  Per-event gain: enemy=1, random=1-2, major=2-3; some choices give 0 EXP.

EXP MANAGEMENT RULE (CRITICAL — per REVIEW_REPORT C1):
1. If GameStateContext.current_exp >= 80 AND target_epilogue_id NOT yet unlocked,
   set risk_level = "critical" regardless of recommended choice.
2. Always include `exp_delta` per choice in ChoiceAnalysis.
3. If GameStateContext.exp_fasting_mode == True, prefer choices with exp_cost=0
   (mark them rank=1 even if reward is lower).
4. Show risk indicator "⚠️ EXP > 80% — ending imminent" in stat_tips
   when current_exp > 80.

STAT ROLES:
- STR: Combat damage, breaking things, physical checks; inventory slot +1 / 3 STR
- DEX: Sneaking, traps, initiative, acrobatics; Acrobatic +1 at 18, +2 at 27
- INT: Magic damage, knowledge checks, spell success
- CHA: Persuasion, deception, bartering, crowd control; Grace/Intimidating alignment-locked
- CON: HP, poison resistance, endurance
- WIS: Perception, insight, survival, wisdom saves

YOUR OUTPUT FORMAT:
Always respond with valid JSON matching the AIRecommendation schema.
Be concise. Be honest. If you don't know something, say so.

RESPONSE FORMAT (JSON):
{
  "quest_identified": "Quest Name or 'Unknown Quest'",
  "confidence": 0.0-1.0,
  "choice_analysis": [
    {
      "choice_id": "ch_xxx_a",
      "choice_letter": "A",
      "stat_check": "DEX 5+" or null,
      "stat_description": "Sneak past the guard" or null,
      "success_probability": "High/Medium/Low/N/A",
      "success_outcome": "What happens on success" or null,
      "fail_outcome": "What happens on fail" or null,
      "rewards": "Gold, items, unlocks" or null,
      "risks": "Negative consequences" or null,
      "exp_delta": 0,  # NEW (C1): EXP gained/avoided by this choice
      "is_exp_avoidance": false,  # NEW: True if choice skips EXP
      "rank": 1,
      "is_recommended": true/false,
    }
  ],
  "best_choice": "choice_id",
  "reasoning": "Why this choice is recommended (1-2 sentences)",
  "risk_level": "safe/moderate/risky/unknown",
  "stat_tips": ["Tip 1", "Tip 2"],
  "alternative_paths": ["Alternative 1", "Alternative 2"],
}
"""
```

### 4.2 User Message Template

```text
USER_MESSAGE_TEMPLATE = """
## CURRENT GAME STATE

### OCR Text (from screen):
```
{raw_quest_text}
```

### Detected Choices:
{choices_list}

### Player Stats (if known):
{player_stats_display}

### Alignment: {alignment}
### Gold: {gold}

## KNOWLEDGE BASE CONTEXT

### Matched Quest:
{matched_quest_info}

### Related Events:
{related_events_info}

### Relevant Choices with Outcomes:
{choices_with_outcomes}

### Relevant Epilogues:
{epilogues_info}

---

Based on the above information:
1. Identify the quest and current situation
2. Analyze each choice with stat requirements and outcomes
3. Recommend the best choice with reasoning
4. Warn about risks
5. Give tactical tips based on player stats

Respond with JSON only. No markdown code blocks. No extra text.
"""
```

### 4.3 Verbosity Modes

```python
VERBOSITY_CONFIGS = {
    "brief": {
        "max_tokens": 512,
        "temperature": 0.7,
        "include_tips": True,
        "include_alternatives": False,
        "include_raw": False,
    },
    "detailed": {
        "max_tokens": 1024,
        "temperature": 0.7,
        "include_tips": True,
        "include_alternatives": True,
        "include_raw": False,
    },
    "expert": {
        "max_tokens": 2048,
        "temperature": 0.5,
        "include_tips": True,
        "include_alternatives": True,
        "include_raw": True,
        "include_probability": True,
    },
}
```

---

## 5. Error Handling

### 5.1 Error Response DTO

```python
@dataclass
class AIErrorResponse:
    """Error response when AI engine fails."""
    error_type: str           # "rate_limit" | "timeout" | "auth_failure" | "parse_error" | "unknown"
    message: str              # Human-readable error message
    fallback_action: str      # "use_cache" | "rag_only" | "show_no_data"
    cached_response: AIRecommendation | None  # If served from cache
    retry_after: int | None   # Seconds until retry is safe (for rate limits)

    def to_overlay_format(self) -> dict:
        return {
            "error": self.error_type,
            "message": self.message,
            "fallback": self.fallback_action,
            "cached": self.cached_response is not None,
            "retry_after": self.retry_after,
        }
```

### 5.2 Error Handling Strategy

```python
def get_recommendation_with_fallback(
    context: GameStateContext,
) -> AIRecommendation | AIErrorResponse:
    """
    Attempts to get AI recommendation with automatic fallback.
    """

    # 1. Check cache
    cache_key = context.compute_cache_key()
    cached = cache.get(cache_key)
    if cached:
        cached.cached = True
        return cached

    # 2. Try AI provider
    try:
        response = ai_engine.get_recommendation(context)
        cache.set(cache_key, response)
        return response

    except RateLimitError as e:
        # Exponential backoff
        sleep_time = compute_backoff(e.retry_after)
        time.sleep(sleep_time)
        return AIErrorResponse(
            error_type="rate_limit",
            message="AI rate limit reached. Try again in a moment.",
            fallback_action="rag_only",
            cached_response=cached,
            retry_after=sleep_time,
        )

    except TimeoutError:
        return AIErrorResponse(
            error_type="timeout",
            message="AI took too long to respond. Showing knowledge base data.",
            fallback_action="rag_only",
            cached_response=cached,
            retry_after=10,
        )

    except AuthenticationError:
        return AIErrorResponse(
            error_type="auth_failure",
            message="AI API key issue. Check your configuration.",
            fallback_action="rag_only",
            cached_response=None,
            retry_after=None,
        )

    except ParseError:
        # AI returned non-JSON response
        return AIErrorResponse(
            error_type="parse_error",
            message="AI response format issue. Showing basic data.",
            fallback_action="rag_only",
            cached_response=cached,
            retry_after=None,
        )
```

---

## 6. Caching Strategy

### 6.1 Cache Configuration

```python
@lru_cache(maxsize=100)
class ResponseCache:
    """
    LRU cache for AI responses.
    Key: MD5(quest_text + normalized_choices)
    TTL: 300 seconds (5 minutes)
    """

    def __init__(self, maxsize: int = 100, ttl: int = 300):
        self.cache: OrderedDict[str, tuple[AIRecommendation, float]] = OrderedDict()
        self.maxsize = maxsize
        self.ttl = ttl

    def get(self, key: str) -> AIRecommendation | None:
        if key not in self.cache:
            return None

        response, timestamp = self.cache[key]
        if time.time() - timestamp > self.ttl:
            del self.cache[key]
            return None

        # Move to end (most recently used)
        self.cache.move_to_end(key)
        return response

    def set(self, key: str, response: AIRecommendation) -> None:
        self.cache[key] = (response, time.time())
        self.cache.move_to_end(key)

        if len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)  # Remove LRU
```

---

## 7. Rate Limiting

### 7.1 Per-Provider Limits

```python
RATE_LIMITS = {
    "zcode": {
        "requests_per_minute": 60,
        "tokens_per_minute": 100000,
        "burst": 20,
    },
    "openai": {
        "requests_per_minute": 60,      # GPT-4o-mini
        "tokens_per_minute": 200000,
        "burst": 10,
    },
    "ollama": {
        "requests_per_minute": 999999,  # Local, no limits
        "tokens_per_minute": 999999,
        "burst": 999999,
    },
}
```

---

*End of API_CONTRACT.md*
