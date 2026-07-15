# Life in Adventure — AI Quest Assistant
## Technical Specification (SPEC.md)

> **Document Status**: Draft v1.1 (review patch)
> **Audience**: Developers, contributors
> **Last Updated**: 2026-07-06
> **Revision**: v1.1 fixes C1 (EXP-aware reasoning), C2 (alignment model), C3 (stat range 1-27+ + power points), C5 (IL2CPP blocker + error type), I2 (adaptive capture note). Per `docs/review/REVIEW_REPORT.md`.

---

## 1. Overview

**Life in Adventure Tools** adalah overlay companion untuk game mobile "Life in Adventure" oleh Studio Wheel. Tool ini menangkap layar game, mengekstrak teks via OCR, mencocokkan dengan knowledge base lokal (RAG), dan memberikan rekomendasi pilihan via AI.

### 1.1 Non-Goals (Out of Scope for MVP)
- Modding atau modifying file game
- Automated gameplay / botting
- Mobile app version (iOS)
- Cloud hosting / SaaS deployment
- Multiplayer / sync features

---

## 2. System Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           HOST MACHINE                                   │
│                                                                         │
│  ┌──────────────────────────┐    ┌──────────────────────────────────┐ │
│  │    MuMuPlayer Emulator    │    │      Overlay Tool (Python)       │ │
│  │                           │    │                                  │ │
│  │  ┌────────────────────┐  │    │  ┌────────────┐  ┌────────────┐│ │
│  │  │                    │  │    │  │  Capture   │  │   OCR      ││ │
│  │  │  Life in Adventure │  │◄──►│  │  Loop      │──►│  Engine    ││ │
│  │  │  (game window)     │  │cap │  │  (mss)     │  │  (EasyOCR) ││ │
│  │  │                    │  │    │  └────────────┘  └─────┬──────┘│ │
│  │  └────────────────────┘  │    │         │              │       │ │
│  │                           │    │         ▼              ▼       │ │
│  │                           │    │  ┌────────────────────────────────┐│ │
│  │                           │    │  │       Text Normalizer          ││ │
│  │                           │    │  │  - Remove OCR noise             ││ │
│  │                           │    │  │  - Detect quest boundaries      ││ │
│  │                           │    │  │  - Parse choices list           ││ │
│  │                           │    │  └───────────────┬────────────────┘│ │
│  │                           │    │                  │                 │ │
│  │                           │    │         ┌────────▼────────┐       │ │
│  │                           │    │         │  Quest          │       │ │
│  │                           │    │         │  Recognizer     │       │ │
│  │                           │    │         │  (fuzzy match)  │       │ │
│  │                           │    │         └────────┬────────┘       │ │
│  │                           │    │                  │                 │ │
│  │                           │    │  ┌──────────────▼──────────────┐ │ │
│  │                           │    │  │   RAG Retrieval Engine     │ │ │
│  │                           │    │  │   (ChromaDB + embeddings)  │ │ │
│  │                           │    │   └──────────────┬──────────────┘ │ │
│  │                           │    │                  │                 │ │
│  │                           │    │         ┌────────▼────────┐       │ │
│  │                           │    │         │  AI Decision    │       │ │
│  │                           │    │         │  Engine         │       │ │
│  │                           │    │         │  (ZCode API)    │       │ │
│  │                           │    │         └────────┬────────┘       │ │
│  │                           │    │                  │                 │ │
│  │                           │    │         ┌────────▼────────┐       │ │
│  │                           │    │         │  Overlay Panel  │       │ │
│  │                           │    │         │  (customtkinter)│       │ │
│  │                           │    │         └────────────────┘       │ │
│  │                           │    └──────────────────────────────────┘ │
│  │                           │                                           │
│  │  ═══════════════════════  │    ═══════════════════════════════════  │
│  └───────────────────────────┘                                           │
│                              │                                            │
│         ════════════════════╪══════════════════════════════════          │
│                              ▼                                            │
│                   ┌──────────────────────┐                              │
│                   │   ChromaDB            │                              │
│                   │   Knowledge Base       │                              │
│                   │   (local SQLite)      │                              │
│                   └──────────────────────┘                              │
│                                                                         │
│  ════════════════════════════════════════════════════════════════════════ │
│                                                                         │
│                      EXTERNAL SERVICES                                   │
│  ┌──────────────────────────────┐                                      │
│  │   ZCode / Claude API          │   (cloud, optional for AI)          │
│  │   gateway.olagon.site        │                                      │
│  └──────────────────────────────┘                                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
1. CAPTURE   : MuMuPlayer window → mss screenshot → PIL Image
2. OCR       : PIL Image → EasyOCR → raw text string
3. NORMALIZE : raw text → cleaned text + parsed structure (quest title, choices)
4. RETRIEVE  : cleaned text → ChromaDB similarity search → matched quest context
5. DECIDE    : quest context + player stats → ZCode API → AI recommendation
6. DISPLAY   : recommendation → Overlay panel update
```

### 2.3 State Machine

```
                    ┌─────────────┐
                    │   IDLE      │
                    │  (startup)  │
                    └──────┬──────┘
                           │ start_capture
                           ▼
                    ┌─────────────┐
                    │  CAPTURING  │◄────────────────┐
                    │  loop active│                 │
                    └──────┬──────┘                 │
                           │ new_frame              │ pause_hotkey
              ┌────────────┴────────────┐           │
              │ no_change              │ change_detected
              │ (skip)                ▼
              │                 ┌─────────────┐
              │                 │   OCR       │
              │                 │   PROCESS   │
              │                 └──────┬──────┘
              │                        │ text_extracted
              │                        ▼
              │                 ┌─────────────┐
              │                 │   RAG       │
              │                 │   QUERY     │
              │                 └──────┬──────┘
              │                        │ context_found
              │                        ▼
              │                 ┌─────────────┐
              │                 │   AI        │
              │                 │   DECISION  │
              │                 └──────┬──────┘
              │                        │ recommendation_ready
              │                        ▼
              │                 ┌─────────────┐
              │                 │  OVERLAY   │
              │                 │  UPDATE    │
              │                 └──────┬──────┘
              │                        │
              └────────────────────────┘
```

---

## 3. Component Specifications

### 3.1 Screen Capture Module (`src/capture/`)

#### `screen_capture.py`

```python
class ScreenCapture:
    """
    Continuously captures screenshots of the emulator window.
    """

    def __init__(
        self,
        emulator_type: str = "mumuproplayer",
        capture_interval: float = 3.0,
        region: tuple[int, int, int, int] | None = None
    ):
        """
        Args:
            emulator_type: One of "mumuproplayer", "bluestacks", "ldplayer",
                          "android_studio", "genymotion"
            capture_interval: Seconds between captures
            region: (x, y, width, height) crop region, None = full window
        """

    def capture(self) -> Image:
        """
        Returns a PIL Image of the current emulator window.
        Raises CaptureError if window not found.
        """

    def start(self) -> None:
        """Start the capture loop in a background thread."""

    def stop(self) -> None:
        """Stop the capture loop."""

    def get_window_rect(self) -> tuple[int, int, int, int]:
        """Returns (x, y, width, height) of emulator window."""
```

#### `emulator_detector.py`

```python
EMULATOR_CONFIGS: dict[str, EmulatorConfig] = {
    "mumuproplayer": EmulatorConfig(
        window_title_patterns=["MuMu", "MuMu Player", "Nemu"],
        executable_names=["NemuPlayer.exe", "NemuHeadless.exe"],
        capture_method="windowed",
        color_scheme="dark",
    ),
    "bluestacks": EmulatorConfig(...),
    "ldplayer": EmulatorConfig(...),
    "android_studio": EmulatorConfig(...),
    "genymotion": EmulatorConfig(...),
}

def detect_emulator() -> str:
    """
    Auto-detect which emulator is running.
    Returns emulator type string or raises EmulatorNotFoundError.
    """

def find_emulator_window(emulator_type: str) -> HWND:
    """
    Find the window handle for the specified emulator.
    Uses Win32 API (pywin32) for Windows.
    """
```

### 3.2 OCR Module (`src/ocr/`)

#### `text_extractor.py`

```python
class OcrEngine:
    """
    EasyOCR-based text extraction for game screenshots.
    """

    def __init__(
        self,
        languages: list[str] = ["en"],
        gpu: bool = False,
        model_name: str = "easyocr_model"
    ):
        """
        Args:
            languages: OCR languages (game supports EN/KR/ID)
            gpu: Use GPU acceleration if available
            model_name: Path to custom model weights (optional)
        """

    def extract(self, image: Image) -> OcrResult:
        """
        Args:
            image: PIL Image of game screen

        Returns:
            OcrResult with:
            - full_text: str (raw extracted text)
            - blocks: list[TextBlock] (structured text regions)
            - confidence: float (average confidence score)
        """

    def extract_choices(self, ocr_result: OcrResult) -> list[str]:
        """
        Identify and extract choice options from OCR result.
        Heuristic: lines starting with [A], [B], [C], or bullet points
        after a question/statement block.
        """

    def extract_quest_title(self, ocr_result: OcrResult) -> str | None:
        """
        Identify quest/event title from OCR result.
        Heuristic: first bold/large text block, or text before first divider.
        """
```

#### `text_normalizer.py`

```python
class TextNormalizer:
    """
    Cleans OCR output and parses into structured format.
    """

    def normalize(self, raw_text: str) -> NormalizedText:
        """
        Steps:
        1. Remove OCR artifacts (garbage characters, repeated spaces)
        2. Fix common OCR misreads (e.g., "0" → "O", "rn" → "m")
        3. Split into quest narrative + choices sections
        4. Return structured NormalizedText
        """

    def is_duplicate(self, text: str, recent_texts: list[str], threshold: float = 0.85) -> bool:
        """
        Check if text is duplicate of recent captures.
        Prevents unnecessary re-processing.
        """

    def detect_language(self, text: str) -> str:
        """
        Detect game language (en/ko/id/es/it/pt).
        Returns language code string.
        """
```

### 3.3 RAG Module (`src/rag/`)

#### `knowledge_base.py`

```python
class KnowledgeBase:
    """
    ChromaDB-backed RAG knowledge base for Life in Adventure.
    """

    def __init__(self, db_path: str = "data/knowledge_base"):
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection_quests = self.client.get_collection("quests")
        self.collection_events = self.client.get_collection("events")
        self.collection_choices = self.client.get_collection("choices")
        self.collection_epilogues = self.client.get_collection("epilogues")

    def query(
        self,
        query_text: str,
        n_results: int = 3,
        collection: str = "events"
    ) -> QueryResult:
        """
        Semantic search against knowledge base.
        """

    def add_quest(self, quest: Quest) -> None:
        """Add a quest to the knowledge base."""

    def add_event(self, event: Event) -> None:
        """Add an event to the knowledge base."""

    def get_quest_by_id(self, quest_id: str) -> Quest | None:
        """Retrieve full quest by ID."""

    def get_event_chain(self, event_id: str) -> list[Event]:
        """Get all events in a quest chain."""

    def get_version(self) -> str:
        """Return KB version (matches game version)."""

    def build_from_parsed_data(self, data_dir: str) -> BuildReport:
        """
        Build entire KB from parsed game JSON files.
        Returns build report with counts and stats.
        """
```

#### `embedder.py`

```python
class Embedder:
    """
    Sentence transformer embedding generator.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        all-MiniLM-L6-v2: 384-dim, fast, CPU-friendly
        Alternatives: "all-mpnet-base-v2" (768-dim, more accurate)
        """
        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""

    def embed_quest(self, quest: Quest) -> list[str]:
        """Generate searchable text representations of a quest."""
```

#### `retriever.py`

```python
class RAGRetriever:
    """
    High-level RAG retrieval with reranking.
    """

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        embedder: Embedder,
        reranker_model: str | None = None
    ):
        self.kb = knowledge_base
        self.embedder = embedder
        self.reranker = CrossEncoder(reranker_model) if reranker_model else None

    def retrieve_for_game_state(
        self,
        quest_text: str,
        choices: list[str],
        player_stats: dict | None = None
    ) -> GameStateContext:
        """
        Main retrieval method. Given current game state:
        1. Find matching events in KB
        2. Extract relevant choices and outcomes
        3. Factor in player stats if provided
        4. Return structured GameStateContext for AI engine

        Returns:
            GameStateContext with:
            - matched_quest: Quest | None
            - matched_events: list[Event]
            - relevant_choices: list[ChoiceWithOutcome]
            - stat_recommendations: dict[str, int]
        """
```

### 3.4 AI Decision Engine (`src/ai/`)

#### `decision_engine.py`

```python
SYSTEM_PROMPT = """You are an expert Life in Adventure game assistant.
The player is playing a text-based D&D-style RPG. You have a RAG knowledge base
with quest data, choice outcomes, stat requirements, and epilogue conditions.

For every response, follow this structure:
1. **Quest**: Identify what quest/event is happening
2. **Analysis**: Briefly explain each choice and its likely outcomes
3. **Recommendation**: State the best choice with clear reasoning
4. **Risk Warning**: Mention if any choice could lead to bad outcomes
5. **Tip**: Optional tactical tip based on stats or game state

Be concise (MVP). Max 3 sentences per choice analysis.
If uncertain, say "Not enough data — your call!" rather than guessing.

Game stats: STR (Strength), DEX (Dexterity), INT (Intelligence),
CHA (Charisma), CON (Constitution), WIS (Wisdom).
Stats range from 1-27 (Super X+2 unlock at 27; Super X+1 at 18).
Stat modifier: (stat - 10) // 2, rounded down.
Combat uses D20 roll + stat_modifier + Power Points (from equipment).
Social checks use CHA or WIS.
Trap detection uses DEX.
Spellcasting uses INT.

EXP MANAGEMENT RULE (CRITICAL):
- EXP max = 100. When bar fills, adventure ends (epilogue triggered).
- Each choice has exp_cost: 0 (non-progressing) or positive (gives EXP).
- Player strategy may be "EXP fasting" — actively avoiding EXP to gain
  stat levels at merchants/random events before ending trigger.
- Bila player's current_exp in OCR > 80 AND target_epilogue not yet unlocked,
  set risk_level="critical" and recommend Choice.exp_cost=0 first.
- Always display exp_delta per choice in choice_analysis output.

ALIGNMENT MODEL (CRITICAL):
- Game uses 5 discrete tiers: Good / Moral / Neutral / Impure / Evil.
- Trait-driven shifts: Bright +20, Dark -20, Innately Good/Evil +/-20, Savior/Butcher +/-20.
- Do NOT model as linear -100..+100 gauge; tier threshold inferred
  from trait deltas (Good >= 60, Moral 20-59, Neutral -19..19, Impure -60..-20, Evil <= -60).
"""

class AIDecisionEngine:
    """
    ZCode/Claude API wrapper for AI recommendations.
    """

    def __init__(
        self,
        provider: str = "zcode",  # "zcode" | "openai" | "ollama"
        model: str = "claude-opus-4-6",
        api_key: str | None = None,
        base_url: str | None = None,
        verbosity: str = "brief"
    ):
        self.provider = provider
        self.model = model
        self.verbosity = verbosity
        self.client = self._init_client(provider, api_key, base_url)

    def _init_client(self, provider, api_key, base_url) -> Any:
        """Initialize API client based on provider."""

    def get_recommendation(
        self,
        context: GameStateContext,
        player_stats: dict[str, int] | None = None
    ) -> AIRecommendation:
        """
        Generate AI recommendation for current game state.

        Args:
            context: RAG retrieval result (quest, choices, outcomes)
            player_stats: Player's current stats (optional, improves accuracy)

        Returns:
            AIRecommendation with:
            - quest_identified: str
            - choice_analysis: list[ChoiceAnalysis]
            - recommendation: str (choice ID)
            - reasoning: str
            - risk_level: "safe" | "moderate" | "risky"
            - raw_response: str (full AI text)
        """

    def _build_prompt(
        self,
        context: GameStateContext,
        player_stats: dict | None
    ) -> str:
        """Build prompt from game state context."""
```

### 3.5 Overlay UI (`src/ui/`)

#### `overlay_window.py`

```python
class OverlayWindow:
    """
    Semi-transparent overlay panel using customtkinter.
    Always-on-top, draggable, resizable.
    """

    def __init__(self, config: OverlayConfig):
        self.root = ctk.CTk()
        self.root.overrideredirect(True)  # Borderless
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "black")

        # Window setup
        self.root.geometry(f"{config.width}x{config.height}+{config.x}+{config.y}")
        self.root.configure(fg_color=config.bg_color)

        # Drag support
        self._drag_data = {"x": 0, "y": 0}
        self._setup_drag()

    def update_content(self, recommendation: AIRecommendation) -> None:
        """
        Update overlay panel with new recommendation data.
        Called whenever AI returns a new result.
        """

    def show_loading(self) -> None:
        """Show loading state (spinner or text)."""

    def show_no_data(self) -> None:
        """Show 'no match found' state."""

    def show_error(self, message: str) -> None:
        """Show error message."""

    def toggle_visibility(self) -> None:
        """Toggle overlay visibility (hotkey F9)."""

    def set_opacity(self, opacity: float) -> None:
        """Adjust window opacity (0.0-1.0)."""
```

#### `settings_panel.py`

```python
class SettingsPanel(ctk.CTkToplevel):
    """
    Settings/configuration window. Opened from overlay menu.
    """

    def __init__(self, parent, config_manager: ConfigManager):
        super().__init__(parent)
        self.title("Life in Adventure — Settings")
        self.geometry("600x700")
        self.config_manager = config_manager

    def build_ui(self) -> None:
        """Build settings form with sections."""
```

### 3.6 Data Extraction (`src/data_extraction/`)

#### `apk_extractor.py`

```python
class APKExtractor:
    """
    Downloads and decompiles Life in Adventure APK.
    """

    APK_INFO = {
        "package": "com.StudioWheel.Bard",
        "version": "1.2.42",
        "apkmirror_slug": "life-in-adventure-1-2-42-release",
        "download_url_template": (
            "https://www.apkmirror.com/apk/studiowheel/"
            "life-in-adventure/life-in-adventure-{version}-release/"
        )
    }

    def download_apk(self, output_path: str) -> str:
        """Download APK from APKMirror. Returns path to downloaded file."""

    def decompile(self, apk_path: str, output_dir: str) -> None:
        """
        Decompile APK using jadx.
        Extracts: Java source, resources, assets, dex files.
        """

    def extract_assets(self, decompiled_dir: str, output_dir: str) -> list[str]:
        """
        Extract Unity asset bundles and data files from assets/.
        Returns list of extracted file paths.
        """

    def detect_game_engine(self, decompiled_dir: str) -> str:
        """
        Detect if game uses Unity, native, or webview.
        Returns: "unity_mono" | "unity_il2cpp" | "native" | "unknown"
        """

    def full_pipeline(self, apk_path: str | None = None) -> ExtractionReport:
        """
        Run full extraction pipeline.
        Returns detailed report with success/failure per step.
        """
```

#### `game_data_parser.py`

```python
class GameDataParser:
    """
    Parses extracted game files into structured JSON.
    """

    # Known data file patterns (to be verified after first extraction)
    KNOWN_PATTERNS = {
        "quests": ["quest*.json", "quest_data*.json", "missions*.json"],
        "events": ["event*.json", "story*.json", "encounter*.json"],
        "items": ["item*.json", "item_data*.json", "equipment*.json"],
        "npcs": ["npc*.json", "character*.json"],
        "epilogues": ["epilogue*.json", "ending*.json"],
        "config": ["config*.json", "game_config*.json"],
    }

    def parse_all(self, raw_dir: str) -> ParsedData:
        """
        Parse all game data files in raw directory.
        Returns structured ParsedData object.
        """

    def parse_quest_file(self, file_path: str) -> list[Quest]:
        """Parse a quest JSON file into Quest objects."""

    def parse_event_file(self, file_path: str) -> list[Event]:
        """Parse an event JSON file into Event objects."""

    def infer_schema(self, sample_file: str) -> dict:
        """
        Attempt to infer JSON schema from a sample file.
        Useful for first-time extraction when schema is unknown.
        """

    def validate_data(self, parsed: ParsedData) -> ValidationReport:
        """
        Validate parsed data for completeness and consistency.
        Checks: required fields, foreign keys, data types.
        """
```

---

## 4. Data Schema

### 4.1 Core Entities

See [docs/data/DATA_SCHEMA.md](docs/data/DATA_SCHEMA.md) for full schema definitions.

```python
@dataclass
class Quest:
    id: str                      # e.g. "q_main_001"
    title: str                   # e.g. "The Haunted Manor"
    type: QuestType              # main | side | random | tale
    tier: int                    # 1-5 difficulty tier
    location: str                 # e.g. "Town", "Forest"
    description: str
    requirements: QuestRequirements
    events: list[str]             # event IDs in order
    outcomes: dict[str, list[str]] # outcome → epilogue IDs
    background_affects: list[str] # which backgrounds affect this

@dataclass
class Event:
    id: str
    quest_id: str
    order: int
    text: str                     # narrative text (original)
    text_translated: dict[str, str] # translated versions
    choices: list[Choice]
    alignment_shift: int          # -10 to +10

@dataclass
class Choice:
    id: str
    text: str
    stat_check: StatCheck | None
    outcomes: list[Outcome]
    alignment_effect: int

@dataclass
class StatCheck:
    stat: StatType    # STR | DEX | INT | CHA | CON | WIS
    threshold: int
    description: str  # e.g. "Sneak past the guard"

@dataclass
class Outcome:
    condition: str   # success | fail | partial | neutral
    result: str      # outcome text
    reward: Reward | None
    risk: str | None
    unlocks: list[str]  # epilogue/item/NPC IDs
    next_event: str | None

@dataclass
class Epilogue:
    id: str
    name: str
    description: str
    category: EpilogueCategory  # death | success | special
    requirements: list[str]     # quest/event IDs needed
    rewards: Reward

@dataclass
class Reward:
    gold: int | None
    exp: int | None
    items: list[str] | None
    stat_bonus: dict[str, int] | None
    unlocks: list[str] | None

@dataclass
class Background:
    id: str
    name: str
    stat_modifier: dict[str, int]
    starting_items: list[str]
    affects_quests: list[str]
    description: str
```

### 4.2 ChromaDB Collections

| Collection | Embedding Field | Dimension | Description |
|------------|-----------------|------------|-------------|
| `quests` | title + description | 384 | All quests |
| `events` | narrative text | 384 | Event text blocks |
| `choices` | choice text + outcome preview | 384 | All choices |
| `epilogues` | name + description + requirements | 384 | All endings |

---

## 5. Configuration

### 5.1 Config File Format

`configs/default_config.yaml`:

```yaml
# Application
app:
  name: "LiA Quest Assistant"
  version: "1.0.0"
  log_level: "INFO"  # DEBUG | INFO | WARNING | ERROR
  log_file: "logs/app.log"

# Emulator
emulator:
  type: "mumuproplayer"  # mumuproplayer | bluestacks | ldplayer | android_studio | genymotion
  capture_interval: 3.0  # seconds
  auto_detect: true
  window_title: null  # override auto-detect
  capture_region: null  # (x, y, w, h) or null for full window

# Overlay
overlay:
  position: "right"  # left | right | top | custom
  custom_pos: null  # (x, y) if position == custom
  width: 450
  height: 650
  opacity: 0.85
  bg_color: "#1a1a2e"
  text_color: "#e0e0e0"
  accent_color: "#00d4ff"
  font_size: 11
  theme: "dark"  # dark | light
  hotkeys:
    toggle: "F9"
    refresh_kb: "F10"
    quit: "F12"
    settings: "F11"

# AI Engine
ai:
  provider: "zcode"  # zcode | openai | ollama
  model: "claude-opus-4-6"
  verbosity: "brief"  # brief | detailed | expert
  temperature: 0.7
  max_tokens: 1024
  # ZCode config
  zcode:
    base_url: "https://gateway.olagon.site/anthropic"  # Aligned with config.py + ARCHITECTURE.md
    api_key_env: "ZCODE_API_KEY"  # env var name
  # OpenAI config (if provider == openai)
  openai:
    base_url: "https://api.openai.com/v1"
    api_key_env: "OPENAI_API_KEY"
  # Ollama config (if provider == ollama)
  ollama:
    base_url: "http://localhost:11434"

# RAG
rag:
  db_path: "data/knowledge_base"
  embedding_model: "all-MiniLM-L6-v2"
  embedding_dim: 384
  top_k_events: 3
  top_k_choices: 5
  reranker: null  # "cross-encoder/ms-marco-MiniLM-L-6-v2" or null
  similarity_threshold: 0.6

# Knowledge Base
knowledge_base:
  version: "1.2.42"  # auto-detected from parsed data
  source_apk_version: null
  last_updated: null
  total_quests: 0
  total_events: 0
  total_choices: 0
  total_epilogues: 0

# Player (optional - can be input manually)
player:
  stats:
    str: null
    dex: null
    int: null
    cha: null
    con: null
    wis: null
  level: null
  gold: null
  alignment: null  # -100 to +100
  background: null
  companions: []

# Capture
capture:
  format: "PNG"
  quality: 95
  resize_factor: 1.0  # scale down for faster OCR
  preprocess: true  # apply image preprocessing
  preprocess_steps:
    - grayscale
    - contrast
    # - deskew  # optional
    # - denoise  # optional
```

---

## 6. API Contracts

### 6.1 AI Engine Contract

See [docs/api/API_CONTRACT.md](docs/api/API_CONTRACT.md) for full API specification.

### 6.2 Module Interface Summary

```
src/
├── capture/
│   ├── ScreenCapture.capture()    → PIL.Image
│   ├── ScreenCapture.start()      → None
│   ├── ScreenCapture.stop()       → None
│   ├── detect_emulator()          → str
│   └── find_window()              → HWND
├── ocr/
│   ├── OcrEngine.extract()        → OcrResult
│   ├── OcrEngine.extract_choices()→ list[str]
│   ├── OcrEngine.extract_quest_title() → str | None
│   ├── TextNormalizer.normalize() → NormalizedText
│   └── TextNormalizer.is_duplicate() → bool
├── rag/
│   ├── KnowledgeBase.query()      → QueryResult
│   ├── KnowledgeBase.build_from_parsed_data() → BuildReport
│   ├── Embedder.embed()            → list[list[float]]
│   └── RAGRetriever.retrieve_for_game_state() → GameStateContext
├── ai/
│   └── AIDecisionEngine.get_recommendation() → AIRecommendation
├── ui/
│   ├── OverlayWindow.update_content() → None
│   ├── OverlayWindow.toggle_visibility() → None
│   └── SettingsPanel.build_ui()    → None
└── data_extraction/
    ├── APKExtractor.full_pipeline() → ExtractionReport
    └── GameDataParser.parse_all()  → ParsedData
```

---

## 7. Performance Requirements

| Metric | Target | Maximum | Measurement |
|--------|--------|---------|-------------|
| Screenshot capture | < 200ms | 500ms | Per frame |
| OCR processing | < 1.0s | 3.0s | Per frame (CPU EasyOCR) |
| Text normalization | < 50ms | 100ms | Per frame |
| Duplicate detection | < 20ms | 50ms | Per frame |
| RAG retrieval | < 300ms | 800ms | Per query |
| AI response | < 3.0s | 8.0s | Per query |
| **Total pipeline** | **< 5.0s** | **12.0s** | End-to-end |
| Memory (idle) | < 200MB | 500MB | Baseline |
| Memory (peak) | < 500MB | 800MB | During OCR |
| CPU (idle) | < 5% | 15% | Between captures |
| CPU (processing, EasyOCR CPU) | < 60% | 95% | During OCR+AI |

> **Note I2 (REVIEW_REPORT)**: Capture interval fixed 3s can cause OCR backlog if EasyOCR CPU mode takes 1-3s per frame. Recommend adaptive interval: no-change >3 captures → extend to 6s; change detected → drop to 1s. See `capture.adaptive_mode: true` in config §5.1.

---

## 8. Error Handling

### 8.1 Error Types

```python
class CaptureError(Exception):
    """Window not found, permission denied, etc."""

class OCRError(Exception):
    """OCR processing failed (corrupt image, unsupported format, etc.)"""

class KBNotFoundError(Exception):
    """Knowledge base not initialized or version mismatch."""

class KBVersionMismatchError(Exception):
    """Game version doesn't match KB version."""

class AIError(Exception):
    """AI API error (rate limit, timeout, auth failure)."""

class EmulatorNotFoundError(Exception):
    """No supported emulator detected."""

class APKExtractionError(Exception):
    """APK download or decompilation failed."""

class IL2CPPNotSupportedError(Exception):
    """APK uses IL2CPP backend — quest data not readable as JSON dumps.
    MVP must pivot to community Fandom scrape fallback. See
    docs/data/DATA_EXTRACTION_FORENSICS.md for pre-flight check."""
```

### 8.2 Recovery Strategies

| Error | Recovery |
|-------|----------|
| `CaptureError` | Retry 3x with 1s delay, then show error in overlay |
| `OCRError` | Skip frame, continue capture loop |
| `KBNotFoundError` | Prompt user to run first_time_setup.py |
| `AIError` (rate limit) | Exponential backoff, show cached response |
| `AIError` (timeout) | Retry once, then show "AI unavailable" |
| `EmulatorNotFoundError` | Show setup wizard with emulator selection |
| `IL2CPPNotSupportedError` | Show pivot-to-community modal. Disable APK extraction flow. Direct user to community Fandom scrape fallback. |

---

## 9. Testing Strategy

### 9.1 Test Categories

| Test | Location | Run |
|------|----------|-----|
| Unit: ScreenCapture | `tests/test_capture.py` | CI + manual |
| Unit: OCR | `tests/test_ocr.py` | CI + manual |
| Unit: TextNormalizer | `tests/test_normalizer.py` | CI |
| Unit: Embedder | `tests/test_embedder.py` | CI |
| Unit: KnowledgeBase | `tests/test_kb.py` | CI + manual |
| Integration: Full pipeline | `tests/test_integration.py` | Manual only |
| Integration: MuMuPlayer | `tests/test_mumuproplayer.py` | Manual only |

### 9.2 Test Fixtures

```
tests/
├── fixtures/
│   ├── screenshots/          # Sample game screenshots
│   │   ├── quest_01_haunted_manor.png
│   │   ├── quest_02_dragon_fight.png
│   │   ├── combat_screen.png
│   │   └── dialogue_choice.png
│   ├── ocr_output/            # Pre-processed OCR outputs
│   ├── game_data/             # Sample parsed game JSON
│   └── kb_snapshots/          # Pre-built ChromaDB snapshots
```

---

## 10. Deployment

### 10.1 Packaging

- **Windows**: PyInstaller → single `.exe` or installer
- **Distribution**: GitHub Releases
- **KB Distribution**: Separate `data/` download or auto-build on first run

### 10.2 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ZCODE_API_KEY` | No* | - | ZCode API key for AI |
| `OPENAI_API_KEY` | No* | - | OpenAI API key (fallback) |
| `LIA_CONFIG_PATH` | No | `./configs/default_config.yaml` | Config file path |
| `LIA_KB_PATH` | No | `./data/knowledge_base` | KB directory |
| `LIA_LOG_LEVEL` | No | `INFO` | Logging level |

*One AI provider key is required for AI recommendations. Without it, tool falls back to basic RAG-only display.

---

*End of SPEC.md*
