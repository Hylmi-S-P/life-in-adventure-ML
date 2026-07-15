# Data Schema

> Complete schema definitions for the LifeInAdventure-Tools knowledge base.
> These schemas are used for: ChromaDB storage, JSON parsing, validation, and API contracts.
>
> **v1.1 (2026-07-06)**: Patches per `docs/review/REVIEW_REPORT.md`:
> - C2: Alignment enum changed from linear -100..+100 to 5 discrete tiers
> - C1: `Choice.exp_cost` + `exp_avoidance` fields added; `GameStateContext.current_exp` + `exp_remaining`
> - C3: Stat threshold bonus table expanded with tier 27 (Super X+2)

---

## 1. Overview

The knowledge base consists of **5 core entities** with relationships:

```
Quest (1) ──────< Event (N)
  │                    │
  │                    │
  └──> Epilogue (N)    │
                        │
                        └──< Choice (N)
                                 │
                                 └──< Outcome (N)
```

| Entity | Count (est.) | Primary Key | ChromaDB Collection |
|--------|-------------|-------------|---------------------|
| `Quest` | ~50 | `quest_id` | `quests` |
| `Event` | ~900 | `event_id` | `events` |
| `Choice` | ~1,200 | `choice_id` | `choices` |
| `Outcome` | ~2,500 | `outcome_id` | (embedded in Choice) |
| `Epilogue` | ~90 | `epilogue_id` | `epilogues` |
| `Background` | ~15 | `bg_id` | (metadata only) |
| `Item` | ~200 | `item_id` | (metadata only) |
| `NPC` | ~100 | `npc_id` | (metadata only) |

---

## 2. Core Data Types

### 2.1 Enumerations

```python
from enum import Enum

class QuestType(str, Enum):
    MAIN = "main"           # Main storyline quests
    SIDE = "side"          # Side quests
    RANDOM = "random"      # Random encounters
    TALE = "tale"          # Tale (alternate storylines) — purchasable DLC
    CHALLENGE = "challenge" # Challenge/task system

class StatType(str, Enum):
    STR = "str"   # Strength — combat, physical checks
    DEX = "dex"   # Dexterity — speed, traps, sneaking
    INT = "int"   # Intelligence — magic, knowledge checks
    CHA = "cha"   # Charisma — persuasion, deception, bartering
    CON = "con"   # Constitution — HP, endurance
    WIS = "wis"   # Wisdom — perception, insight, survival

class OutcomeCondition(str, Enum):
    SUCCESS = "success"    # Stat check passed, best outcome
    FAIL = "fail"          # Stat check failed, negative outcome
    PARTIAL = "partial"    # Mixed result
    NEUTRAL = "neutral"    # No stat check, always succeeds
    CRITICAL_SUCCESS = "critical_success"  # Natural 20 / perfect roll
    CRITICAL_FAIL = "critical_fail"       # Natural 1 / worst outcome

class EpilogueCategory(str, Enum):
    DEATH = "death"        # Character died
    SUCCESS = "success"    # Achieved goals
    FAILURE = "failure"    # Failed goals
    SPECIAL = "special"    # Special/secret ending
    NEUTRAL = "neutral"    # Ambiguous ending

class Alignment(str, Enum):
    """5 discrete alignment tiers used by game (verified via Scribd community guide +
    Cobraknife traits guide — see GAME_MECHANICS.md §5).

    Threshold tier is INFERRED from trait sum deltas (Bright +20, Dark -20, dst).
    APK extraction must verify exact threshold.

    Internally we store raw int alignment value (-100..+100) for granularity,
    but expose tier via `tier` property. Tiers matter for epilogue + skill unlocks.
    """
    GOOD = "good"            # alignment >= 60 (approx)
    MORAL = "moral"          # 20 <= alignment < 60
    TRUE_NEUTRAL = "neutral" # -20 < alignment < 20
    IMPURE = "impure"        # -60 < alignment <= -20
    EVIL = "evil"            # alignment <= -60 (approx)

    @classmethod
    def from_int(cls, value: int) -> "Alignment":
        """Map raw alignment int to discrete tier (inferensi)."""
        if value >= 60:
            return cls.GOOD
        elif value >= 20:
            return cls.MORAL
        elif value > -20:
            return cls.TRUE_NEUTRAL
        elif value > -60:
            return cls.IMPURE
        else:
            return cls.EVIL

    @property
    def effective_range(self) -> tuple[int, int]:
        return {
            Alignment.GOOD: (60, 100),
            Alignment.MORAL: (20, 59),
            Alignment.TRUE_NEUTRAL: (-19, 19),
            Alignment.IMPURE: (-60, -20),
            Alignment.EVIL: (-100, -61),
        }[self]

class GameLanguage(str, Enum):
    EN = "en"   # English
    KR = "kr"   # Korean
    ID = "id"   # Indonesian
    ES = "es"   # Spanish (future)
    IT = "it"   # Italian (future)
    PT = "pt"   # Portuguese (future)
```

---

## 3. Entity Schemas

### 3.1 Quest

```python
@dataclass
class Quest:
    """
    Represents a complete quest/storyline in the game.
    """
    # ─── Identification ────────────────────────────────────────
    id: str                               # Unique ID, e.g. "q_main_001"
    title: str                            # Display name, e.g. "The Haunted Manor"

    # ─── Classification ────────────────────────────────────────
    type: QuestType                       # main | side | random | tale | challenge
    tier: int                            # Difficulty tier 1-5

    # ─── Content ──────────────────────────────────────────────
    description: str                      # Brief description for RAG matching
    synopsis: str | None                  # Detailed synopsis (optional)

    # ─── Context ──────────────────────────────────────────────
    location: str                         # Where quest occurs, e.g. "Town", "Forest"
    prerequisites: list[str]              # Quest IDs that must be completed first
    unlocked_by: list[str]                # Items, NPCs, or conditions to unlock
    affected_by_backgrounds: list[str]     # Background IDs that change this quest

    # ─── Structure ─────────────────────────────────────────────
    event_ids: list[str]                  # Ordered list of event IDs in this quest
    outcomes: dict[str, list[str]]         # outcome_condition → list of epilogue IDs
                                           # e.g. {"success": ["ep_01", "ep_02"], "fail": ["ep_03"]}

    # ─── Metadata ─────────────────────────────────────────────
    version_added: str                    # Game version when added, e.g. "1.0.0"
    version_updated: str | None          # Last game version that modified this
    languages: list[GameLanguage]          # Available languages
    source: str                           # "apk_extraction" | "community" | "manual"

    # ─── Computed (populated at runtime) ─────────────────────
    @property
    def total_choices(self) -> int:
        return sum(len(e.choices) for e in self.events)

    @property
    def has_stat_checks(self) -> bool:
        return any(
            any(c.stat_check for c in e.choices)
            for e in self.events
        )
```

**Example JSON**:
```json
{
  "id": "q_side_haunted_manor",
  "title": "The Haunted Manor",
  "type": "side",
  "tier": 2,
  "description": "Help the priest investigate a haunted manor north of town",
  "location": "Town > North Road > Old Manor",
  "prerequisites": [],
  "unlocked_by": ["talk_to_priest"],
  "affected_by_backgrounds": ["bg_adventurer"],
  "event_ids": ["evt_haunted_01", "evt_haunted_02", "evt_haunted_03"],
  "outcomes": {
    "success": ["ep_ghost_hunter"],
    "partial": ["ep_manor_escaped"],
    "fail": ["ep_manor_death"]
  },
  "version_added": "1.0.0",
  "version_updated": "1.2.0",
  "languages": ["en", "kr", "id"],
  "source": "apk_extraction"
}
```

### 3.2 Event

```python
@dataclass
class Event:
    """
    Represents a single event/moment within a quest.
    Contains narrative text and choices.
    """
    # ─── Identification ────────────────────────────────────────
    id: str                               # Unique ID, e.g. "evt_haunted_01"
    quest_id: str                         # Parent quest ID
    order: int                            # Sequence order within quest (1-indexed)

    # ─── Content ──────────────────────────────────────────────
    text: str                             # Narrative text (original language)
    text_translated: dict[str, str]       # Translations: lang_code → text
                                           # e.g. {"en": "...", "kr": "..."}

    # ─── Choices ──────────────────────────────────────────────
    choices: list[Choice]                 # All available choices in this event

    # ─── Effects ──────────────────────────────────────────────
    alignment_shift: int                  # Alignment change from this event (-10 to +10)
                                           # Positive = more lawful/good
                                           # Negative = more chaotic/evil
    stat_changes: dict[str, int] | None    # Permanent stat changes, e.g. {"str": +1}
    gold_change: int | None               # Gold gained/lost
    exp_gain: int | None                  # EXP gained
    items_given: list[str] | None          # Item IDs given
    items_removed: list[str] | None        # Item IDs removed

    # ─── Context ──────────────────────────────────────────────
    background: str | None                # Background image/setting, e.g. "manor_entrance"
    mood: str | None                      # Emotional tone: "dark", "tense", "comedic", etc.
    character_speaking: str | None        # NPC ID if a character is speaking

    # ─── Metadata ─────────────────────────────────────────────
    is_combat: bool                       # True if this event involves combat
    is_dialogue: bool                     # True if this is primarily dialogue
    is_random_encounter: bool             # True if this is a random event
    version_added: str
    source: str
```

**Example JSON**:
```json
{
  "id": "evt_haunted_01",
  "quest_id": "q_side_haunted_manor",
  "order": 1,
  "text": "The manor looms before you, its windows dark and broken. A cold wind whistles through the cracked walls. Father Aldric stands beside you, clutching his holy symbol.",
  "text_translated": {
    "en": "The manor looms before you...",
    "kr": "저택이 당신 앞에 우뚝 서 있고...",
    "id": "Permintaan itu ada di depan anda..."
  },
  "choices": [
    {
      "id": "ch_haunted_01_a",
      "text": "Enter through the front door quietly",
      "order": 1,
      "stat_check": {
        "stat": "DEX",
        "threshold": 5,
        "description": "Sneak past the spectral guardian"
      },
      "outcomes": [
        {
          "condition": "success",
          "result": "You slip through the doorway undetected. The guardian's gaze passes over you without interest.",
          "reward": null,
          "risk": null,
          "unlocks": ["evt_haunted_02a"],
          "next_event": "evt_haunted_02a"
        },
        {
          "condition": "fail",
          "result": "A floorboard creaks! The guardian's hollow eyes turn toward you.",
          "reward": null,
          "risk": "Combat with Spectral Guardian",
          "unlocks": [],
          "next_event": "evt_haunted_02b"
        }
      ],
      "alignment_effect": 0
    },
    {
      "id": "ch_haunted_01_b",
      "text": "Knock on the door politely",
      "order": 2,
      "stat_check": {
        "stat": "CHA",
        "threshold": 6,
        "description": "Charm your way into the manor"
      },
      "outcomes": [
        {
          "condition": "success",
          "result": "The door swings open with a respectful creak. The spirits seem... amused.",
          "reward": {"unlocks": ["npc_ghost_friendly"]},
          "risk": null,
          "unlocks": ["evt_haunted_02c"],
          "next_event": "evt_haunted_02c"
        },
        {
          "condition": "fail",
          "result": "The door remains firmly shut. No one answers.",
          "reward": null,
          "risk": "Time wasted — lose 1 turn",
          "unlocks": [],
          "next_event": "evt_haunted_01_retry"
        }
      ],
      "alignment_effect": 1
    }
  ],
  "alignment_shift": 0,
  "stat_changes": null,
  "gold_change": null,
  "exp_gain": 10,
  "is_combat": false,
  "is_dialogue": false,
  "is_random_encounter": false,
  "version_added": "1.0.0",
  "source": "apk_extraction"
}
```

### 3.3 Choice

```python
@dataclass
class Choice:
    """
    Represents a single choice option within an event.
    """
    id: str                               # Unique ID, e.g. "ch_haunted_01_a"
    text: str                             # Choice text shown to player
    order: int                            # Display order (1-indexed)

    # ─── Stat Requirements ─────────────────────────────────────
    stat_check: StatCheck | None         # Stat requirement to pass, None = always succeed

    # ─── Outcomes ──────────────────────────────────────────────
    outcomes: list[Outcome]               # All possible outcomes
    default_outcome: Outcome | None       # Fallback if no condition matches

    # ─── Effects ──────────────────────────────────────────────
    alignment_effect: int                 # Alignment shift from choosing this (-5 to +5)

    # ─── EXP / Fasting Strategy ──────────────────────────────
    exp_cost: int = 0                     # EXP gained by this choice (0 = non-progressing,
                                          # supports EXP Fasting strategy — see GAME_MECHANICS §4.3)
    exp_avoidance: bool = False           # True if this choice explicitly avoids EXP (skip/avoid)
    exp_reward: int = 0                   # EXP caused as side-effect (divergent from main choice EXP).

    # ─── Metadata ─────────────────────────────────────────────
    is_combat_action: bool                # True if this is a combat action
    is_dialogue_option: bool              # True if this is dialogue
    requires_item: str | None              # Item ID required to select this choice
    locked_by_flag: str | None            # Game flag that must be set to show this choice
```

### 3.4 StatCheck

```python
@dataclass
class StatCheck:
    """
    Represents a stat check (D20 + stat modifier vs threshold).
    Roll: 1d20 + stat_modifier >= threshold
    Stat modifier: (stat_value - 10) // 2
    """
    stat: StatType                        # Which stat is checked
    threshold: int                        # DC (Difficulty Class) — must roll >= this

    # ─── Context ──────────────────────────────────────────────
    description: str                     # Human-readable description, e.g. "Sneak past the guard"
    advantage: bool                       # True if player can roll with advantage
    disavantage: bool                     # True if player rolls with disadvantage
    roll_override: int | None            # Fixed roll value (for scripted events), None = random
```

**Stat Check Examples**:

| Stat | Threshold | Scenario | Modifier Needed |
|------|-----------|----------|----------------|
| DEX | 5 | Sneak past guard | DEX 10+ (mod +0) |
| DEX | 10 | Pick a lock | DEX 14+ (mod +2) |
| CHA | 6 | Persuade guard | CHA 12+ (mod +1) |
| CHA | 10 | Lie to merchant | CHA 14+ (mod +2) |
| INT | 7 | Recall lore | INT 14+ (mod +2) |
| WIS | 8 | Spot a trap | WIS 12+ (mod +1) |
| STR | 8 | Break down door | STR 14+ (mod +2) |
| CON | 5 | Endure poison | CON 10+ (mod +0) |

### 3.5 Outcome

```python
@dataclass
class Outcome:
    """
    Represents a possible result of a choice.
    """
    condition: OutcomeCondition            # success | fail | partial | neutral
    result: str                           # Text shown to player describing what happens

    # ─── Rewards ───────────────────────────────────────────────
    reward: Reward | None                 # Rewards if successful

    # ─── Consequences ────────────────────────────────────────
    risk: str | None                      # Description of potential negative outcome
    penalty: Penalty | None               # What happens if this is a fail/partial outcome

    # ─── Progression ──────────────────────────────────────────
    unlocks: list[str]                    # Items, achievements, or flags unlocked
    next_event: str | None                # Next event ID (quest continuation)
    ends_quest: bool                      # True if this outcome ends the quest

    # ─── Epilogue ─────────────────────────────────────────────
    epilogue_id: str | None               # Epilogue triggered by this outcome
```

### 3.6 Reward & Penalty

```python
@dataclass
class Reward:
    """Reward given for a successful outcome."""
    gold: int | None                      # e.g. 200
    exp: int | None                       # e.g. 50
    items: list[str] | None               # Item IDs, e.g. ["item_holy_water", "item_silver_ring"]
    stat_bonus: dict[str, int] | None     # Permanent stat bonuses, e.g. {"cha": 1}
    unlocks: list[str] | None             # Unlocked content, e.g. ["epilogue_ghost_hunter"]

@dataclass
class Penalty:
    """Penalty for a failed/partial outcome."""
    gold_loss: int | None                 # e.g. 50
    exp_loss: int | None                  # e.g. 10
    items_lost: list[str] | None           # Item IDs lost
    stat_penalty: dict[str, int] | None    # Temporary or permanent stat penalties
    hp_damage: int | None                 # HP lost
    status_effect: str | None             # e.g. "poisoned", "cursed"
```

### 3.7 Epilogue

```python
@dataclass
class Epilogue:
    """
    Represents an ending state for the game or a quest.
    """
    id: str                               # e.g. "ep_ghost_hunter"
    name: str                             # e.g. "Ghost Hunter"
    description: str                      # Brief description of this ending

    # ─── Classification ────────────────────────────────────────
    category: EpilogueCategory             # death | success | failure | special | neutral

    # ─── Requirements ─────────────────────────────────────────
    requirements: list[str]               # Quest IDs, event IDs, item IDs, or conditions needed
                                           # e.g. ["q_side_haunted_manor", "evt_haunted_final"]
    alignment_required: tuple[int, int] | None  # (min, max) alignment range, e.g. (-50, 50)

    # ─── Rewards ──────────────────────────────────────────────
    rewards: Reward                        # Bonuses for achieving this epilogue
    score_bonus: int | None               # Score/rank system bonus

    # ─── Lore ─────────────────────────────────────────────────
    lore_text: str | None                 # Lore/backstory text for this ending

    # ─── Metadata ─────────────────────────────────────────────
    is_secret: bool                        # True if this is a secret ending
    is_canonical: bool                     # True if this is a canon ending (from community consensus)
    rarity: str                           # "common" | "uncommon" | "rare" | "legendary"
    version_added: str
    source: str
```

### 3.8 Background

```python
@dataclass
class Background:
    """
    Represents a character background (paid DLC / unlockable).
    Affects main storyline and starting conditions.
    """
    id: str                               # e.g. "bg_adventurer"
    name: str                             # e.g. "Adventurer's Dream"
    description: str                      # Lore and mechanics description

    # ─── Starting Conditions ──────────────────────────────────
    stat_modifier: dict[str, int]         # e.g. {"str": 1, "dex": -1}
    starting_items: list[str]             # Item IDs
    starting_gold: int                    # Starting gold amount
    starting_level: int                   # Starting level (usually 1)

    # ─── Gameplay Effects ─────────────────────────────────────
    affects_quests: list[str]             # Quest IDs that are different with this background
    changes_main_story: bool              # True if this changes the main questline
    unique_events: list[str]              # Event IDs only available with this background
    exclusive_epilogues: list[str]        # Epilogue IDs only reachable with this background

    # ─── Content ──────────────────────────────────────────────
    content_tier: str                     # "free" | "basic" | "premium"
    gem_cost: int | None                  # Gem cost (None if free)
    source: str                           # "apk_extraction" | "community"
```

### 3.9 Item

```python
@dataclass
class Item:
    """
    Represents an item in the game.
    """
    id: str                               # e.g. "item_rusty_sword"
    name: str                             # e.g. "Rusty Sword"
    description: str                      # Item description

    # ─── Classification ────────────────────────────────────────
    type: ItemType                        # weapon | armor | consumable | quest | misc
    rarity: str                           # common | uncommon | rare | epic | legendary
    slot: str | None                      # equipment slot, e.g. "main_hand", "off_hand"

    # ─── Stats ────────────────────────────────────────────────
    stats: dict[str, int] | None          # Stat bonuses, e.g. {"str": 2, "dex": 1}
    damage: int | None                    # Weapon damage
    armor: int | None                     # Armor class bonus

    # ─── Effects ──────────────────────────────────────────────
    is_magical: bool
    is_quest_item: bool                   # True if this is a quest item (can't be sold/dropped)
    effect_description: str | None        # Special effect description

    # ─── Acquisition ───────────────────────────────────────────
    how_to_obtain: list[str]              # Quest IDs or conditions to obtain
    sell_price: int | None
    buy_price: int | None
```

---

## 4. ChromaDB Collection Schemas

### 4.1 Quests Collection

```python
collection_quests = {
    "name": "quests",
    "metadata": {
        "description": "All quests in Life in Adventure",
        "version": "1.2.42",
        "count_estimate": 50,
    },
    "schema": {
        "ids": ["q_main_001", "q_main_002", ...],
        "embeddings": [[384 floats], ...],  # all-MiniLM-L6-v2
        "documents": [
            "Main Quest: The Beginning. Start your adventure as a new adventurer. "
            "Location: Town Square. Type: main. Tier: 1. "
            "Help the guild receptionist understand your goals and begin your journey."
        ],
        "metadatas": [
            {
                "id": "q_main_001",
                "title": "The Beginning",
                "type": "main",
                "tier": 1,
                "location": "Town",
                "language": "en",
                "source": "apk_extraction",
            }
        ],
    }
}
```

### 4.2 Events Collection

```python
collection_events = {
    "name": "events",
    "schema": {
        "documents": [
            "The guild receptionist looks up from her ledger. 'Ah, a new face! "
            "Welcome to the Adventurers' Guild. What brings you here?' "
            "Choices: [A] I'd like to register as an adventurer. [B] Do you have any jobs?"
        ],
        "metadatas": [
            {
                "id": "evt_guild_01",
                "quest_id": "q_main_001",
                "quest_title": "The Beginning",
                "order": 1,
                "type": "main",
                "has_combat": False,
                "has_stat_check": False,
                "num_choices": 2,
                "language": "en",
            }
        ],
    }
}
```

### 4.3 Choices Collection

```python
collection_choices = {
    "name": "choices",
    "schema": {
        "documents": [
            "[A] I'd like to register as an adventurer. "
            "No stat check required. "
            "Outcome: Gain guild membership, receive starter equipment."
        ],
        "metadatas": [
            {
                "id": "ch_guild_01_a",
                "event_id": "evt_guild_01",
                "quest_id": "q_main_001",
                "order": 1,
                "has_stat_check": False,
                "stat_type": None,
                "threshold": None,
                "primary_outcome": "success",
                "is_combat": False,
            }
        ],
    }
}
```

### 4.4 Epilogues Collection

```python
collection_epilogues = {
    "name": "epilogues",
    "schema": {
        "documents": [
            "Ghost Hunter. You cleared the old manor of restless spirits, "
            "bringing peace to the haunted dead. Father Aldric celebrates your victory. "
            "Requirements: Complete Haunted Manor quest with success outcome. "
            "Rewards: 200 gold, Holy Water, Ghost Hunter epilogue."
        ],
        "metadatas": [
            {
                "id": "ep_ghost_hunter",
                "name": "Ghost Hunter",
                "category": "success",
                "rarity": "common",
                "is_secret": False,
                "is_canonical": True,
                "requirements_count": 2,
            }
        ],
    }
}
```

---

## 5. Validation Rules

### 5.1 Required Fields

| Entity | Required Fields |
|--------|----------------|
| Quest | `id`, `title`, `type`, `description`, `event_ids` |
| Event | `id`, `quest_id`, `order`, `text`, `choices` |
| Choice | `id`, `text`, `order`, `outcomes` |
| Outcome | `condition`, `result` |
| StatCheck | `stat`, `threshold`, `description` |
| Reward | (all fields optional, but at least one should be set) |
| Epilogue | `id`, `name`, `category`, `requirements` |

### 5.2 Cross-Entity Validation

```python
VALIDATION_RULES = [
    # Quest → Events: All event_ids must exist in events collection
    "FOR EACH quest.event_ids: event_id IN events[]",
    
    # Event → Quest: Event's quest_id must match parent quest
    "FOR EACH event: event.quest_id IN quests[].id",
    
    # Choice → Event: Choice's event_id must be set
    "FOR EACH choice: choice.event_id IS NOT NULL",
    
    # Outcome → Events: outcome.next_event must exist or be null
    "FOR EACH outcome.next_event: next_event IN events[] OR next_event IS NULL",
    
    # Outcome → Epilogue: outcome.epilogue_id must exist or be null
    "FOR EACH outcome.epilogue_id: epilogue_id IN epilogues[] OR epilogue_id IS NULL",
    
    # Stat check threshold: must be 1-20 (D20 range)
    "FOR EACH stat_check: 1 <= threshold <= 20",
    
    # Stat check stat type: must be valid enum
    "FOR EACH stat_check.stat: stat IN [STR, DEX, INT, CHA, CON, WIS]",
    
    # Stat / Super X+2 unlock: stat >= 27 (verified via Fandom Wiki Stats)
    "STATS valid range: 1 <= value <= 27+ (no hard upper bound for endgame)",
    
    # EXP: 0 <= exp_gain/exp_cost <= 3 per choice (verified source: LDPlayer guide)
    "FOR EACH choice.exp_cost AND outcome.exp_gain: 0 <= value <= 10",
    "FOR EACH choice.exp_avoidance == True: choice.exp_cost MUST == 0",
    
    # Alignment: -100 to +100 (raw storage; tier is computed)
    "FOR EACH alignment_value: -100 <= value <= 100",
    
    # Alignment tier mapping (5 tiers verified via Scribd + Cobraknife)
    "FOR EACH alignment_value: tier = Alignment.from_int(value)",
    
    # Epilogue requirement alignment tuple: (min, max) within -100..+100
    "FOR EACH epilogue.alignment_required: -100 <= min <= max <= 100 OR alignment_required IS NULL",
]
```

---

## 6. Export Formats

### 6.1 JSON (Primary Format)

All entities stored as JSON for portability.

### 6.2 Markdown (Human-Readable Export)

```markdown
## Quest: The Haunted Manor

**Type**: Side Quest | **Tier**: 2 | **Location**: Town > North Road

### Description
Help the priest investigate a haunted manor north of town.

### Events
1. [evt_haunted_01](#evt_haunted_01) - Manor Approach
2. [evt_haunted_02a](#evt_haunted_02a) - Inside (sneaked)
3. [evt_haunted_02b](#evt_haunted_02b) - Combat with Guardian

### Outcomes
| Outcome | Condition | Epilogue |
|---------|-----------|----------|
| Ghost Hunter | success | ep_ghost_hunter |
| Manor Escaped | partial | ep_manor_escaped |
| Manor Death | fail | ep_manor_death |
```

---

*End of DATA_SCHEMA.md*
