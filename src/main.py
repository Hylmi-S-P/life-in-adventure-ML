#!/usr/bin/env python3
"""
LifeInAdventure-Tools — AI Quest Assistant
Main entry point.

Usage:
    python src/main.py
    python src/main.py --config configs/local_config.yaml
    python src/main.py --no-ai  # RAG-only mode (no AI recommendations)
"""

import argparse
import os
import sys
import time
import signal
import atexit
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import threading
from pathlib import Path

# Suppress Windows symlink warning on HF cache (doesn't affect API limits)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Ensure project root directory is in sys.path so 'from src....' imports work when invoked as 'python src/main.py'
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import loguru

# Setup logging
logger = loguru.logger
logger.add(
    "logs/app.log",
    rotation="10 MB",
    level=os.getenv("LIA_LOG_LEVEL", "INFO"),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
)

# ── Graceful shutdown registry (Phase P3.2) ────────────────────────────────
# Components that need cleanup are registered here after init completes.
_app_components = {
    "running": False,
}
_shutdown_in_progress = False


def _graceful_shutdown(signum=None, frame=None):
    """Stop the app cleanly: stop autoplay, persist caches, close DB."""
    global _shutdown_in_progress
    if _shutdown_in_progress:
        return
    if not _app_components.get("running", False):
        return
    _shutdown_in_progress = True
    logger.info(f"Shutdown signal received (signal={signum}). Starting graceful shutdown...")
    _app_components["running"] = False

    # Stop auto-play loop
    state = _app_components.get("state")
    if state:
        state.autoplay_active = False

    # Wait briefly for auto-play thread to exit
    thread = _app_components.get("autoplay_thread")
    if thread and thread.is_alive():
        thread.join(timeout=3.0)

    # Persist caches
    for name in ("ai_cache", "rag_cache"):
        cache = _app_components.get(name)
        if cache and hasattr(cache, "save"):
            try:
                cache.save()
                logger.info(f"Cache '{name}' persisted.")
            except Exception as e:
                logger.warning(f"Cache '{name}' persist failed: {e}")

    # Close knowledge base
    kb = _app_components.get("kb")
    if kb and hasattr(kb, "close"):
        try:
            kb.close()
            logger.info("Knowledge base closed.")
        except Exception as e:
            logger.warning(f"KB close failed: {e}")

    logger.info("Graceful shutdown complete.")


def _register_shutdown_hooks():
    """Register signal handlers and atexit for graceful shutdown."""
    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    atexit.register(_graceful_shutdown)
    logger.debug("Shutdown hooks registered.")

# EventBus is defined in ARCHITECTURE.md §1.2 as a local module.
# For MVP we use a minimal inline stub; replace with real module when created.
class _EventBusStub:
    """Minimal EventBus placeholder — see ARCHITECTURE.md §1.2 for full spec."""
    def subscribe(self, event, handler): pass
    def publish(self, event, *args, **kwargs): pass

event_bus = _EventBusStub()
EVENT_CAPTURED = "screen_captured"
EVENT_OCR_COMPLETED = "ocr_completed"
EVENT_RAG_MATCHED = "rag_completed"
EVENT_AI_RESPONSE = "ai_completed"
EVENT_CONFIG_CHANGED = "config_changed"
EVENT_OVERLAY_READY = "overlay_ready"
EVENT_SHUTDOWN = "shutdown"

# Component imports — modules will be implemented incrementally;
# gracefully degrade when a module is not yet built.
_MISSING_IMPORTS = []
try:
    from src.config import Config
except ImportError as e:
    _MISSING_IMPORTS.append(f"Config: {e}")

try:
    from src.capture.screen_capture import ScreenCapture
    from src.capture.auto_clicker import AutoClicker
except ImportError as e:
    ScreenCapture = None
    AutoClicker = None
    _MISSING_IMPORTS.append(f"ScreenCapture/AutoClicker: {e}")

try:
    from src.ocr.text_extractor import OcrEngine
except ImportError as e:
    OcrEngine = None
    _MISSING_IMPORTS.append(f"OcrEngine: {e}")

try:
    from src.ocr.text_normalizer import TextNormalizer
except ImportError as e:
    TextNormalizer = None
    _MISSING_IMPORTS.append(f"TextNormalizer: {e}")

try:
    from src.rag.knowledge_base import KnowledgeBase
except ImportError as e:
    KnowledgeBase = None
    _MISSING_IMPORTS.append(f"KnowledgeBase: {e}")

try:
    from src.rag.retriever import RAGRetriever
except ImportError as e:
    RAGRetriever = None
    _MISSING_IMPORTS.append(f"RAGRetriever: {e}")

try:
    from src.ai.decision_engine import AIDecisionEngine
except ImportError as e:
    AIDecisionEngine = None
    _MISSING_IMPORTS.append(f"AIDecisionEngine: {e}")

try:
    from src.ui.overlay_window import OverlayWindow
except ImportError as e:
    OverlayWindow = None
    _MISSING_IMPORTS.append(f"OverlayWindow: {e}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LifeInAdventure AI Quest Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/default_config.yaml"),
        help="Path to configuration file",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Run in RAG-only mode (no AI recommendations)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print live system, KB, Pathfinder, and RL checkpoint diagnostics and exit",
    )
    return parser.parse_args()


def _init_components(config, no_ai, overlay):
    """Heavy initialization run in background thread."""
    try:
        capture = ScreenCapture(
            emulator_type=config.emulator.type,
            capture_interval=config.emulator.capture_interval,
            capture_region=config.emulator.capture_region,
        ) if ScreenCapture else None

        clicker = AutoClicker(screen_capture=capture) if AutoClicker else None

        # OCR: GPU auto-detect (Phase P0.2) — gpu="auto" reads torch.cuda.is_available()
        ocr = OcrEngine(languages=["ko", "en"], gpu="auto") if OcrEngine else None

        normalizer = TextNormalizer() if TextNormalizer else None

        kb = KnowledgeBase(db_path=config.rag.db_path) if KnowledgeBase else None
        if kb:
            logger.info(f"KB loaded: Version {kb.get_version()}")
            _app_components["kb"] = kb

        retriever = RAGRetriever(
            knowledge_base=kb,
            top_k_events=config.rag.top_k_events,
            top_k_choices=config.rag.top_k_choices,
        ) if RAGRetriever else None
        if retriever:
            _app_components["rag_cache"] = retriever._cache

        ai_engine = None
        if not no_ai and AIDecisionEngine:
            ai_engine = AIDecisionEngine(
                provider=config.ai.provider,
                model=config.ai.model,
                verbosity=config.ai.verbosity,
            )
            if ai_engine:
                _app_components["ai_cache"] = ai_engine._eval_cache

        if overlay:
            overlay.attach_components(capture, ocr, normalizer, retriever, ai_engine, clicker)
            _app_components["state"] = overlay.state

        event_bus.publish(EVENT_OVERLAY_READY)
        _app_components["running"] = True
    except Exception as e:
        logger.exception(f"Component init failed: {e}")
        if overlay:
            overlay.show_error(f"Initialization failed: {e}")


def main() -> None:
    args = parse_args()

    if getattr(args, "status", False):
        print("\n=== 🔮 Life in Adventure AI Quest Assistant — Live Diagnostics ===")
        import sqlite3
        kb_path = Path("data/knowledge_base/lia_kb.sqlite").resolve()
        if not kb_path.exists():
            kb_path = Path("data/lia_kb.sqlite/lia_kb.sqlite").resolve()
        if kb_path.exists():
            try:
                uri = f"{kb_path.as_uri()}?mode=ro"
                with sqlite3.connect(uri, uri=True) as conn:
                    count = conn.execute("SELECT count(*) FROM events").fetchone()[0]
                print(f" ∙ RAG Knowledge Base (`{kb_path.parent.name}/{kb_path.name}`): {count:,} events indexed [READY]")
            except Exception:
                try:
                    with sqlite3.connect(kb_path) as conn:
                        count = conn.execute("SELECT count(*) FROM events").fetchone()[0]
                    print(f" ∙ RAG Knowledge Base (`{kb_path.parent.name}/{kb_path.name}`): {count:,} events indexed [READY]")
                except Exception as e:
                    print(f" ∙ RAG Knowledge Base (`{kb_path.parent.name}/{kb_path.name}`): [LOCKED/BUSY] ({e})")
        else:
            print(" ∙ RAG Knowledge Base (`data/knowledge_base/lia_kb.sqlite`): NOT FOUND")
            
        path_db = Path("data/discovered_paths.db").resolve()
        if path_db.exists():
            try:
                uri = f"{path_db.as_uri()}?mode=ro"
                with sqlite3.connect(uri, uri=True) as conn:
                    p_count = conn.execute("SELECT count(*) FROM discovered_nodes").fetchone()[0]
                print(f" ∙ RL Pathfinder Database (`data/discovered_paths.db`): {p_count:,} unique secrets discovered [ACTIVE/READY]")
            except Exception as e:
                print(f" ∙ RL Pathfinder Database (`data/discovered_paths.db`): [LOCKED/BUSY] ({e})")
        else:
            print(" ∙ RL Pathfinder Database (`data/discovered_paths.db`): NOT FOUND")
            
        model_pt = Path("data/models/ppo_curiosity_latest.pt")
        if model_pt.exists():
            size_kb = model_pt.stat().st_size / 1024
            print(f" ∙ RL PPO Neural Network Checkpoint (`data/models/ppo_curiosity_latest.pt`): {size_kb:.1f} KB [CHECKPOINT SAVED]")
        else:
            print(" ∙ RL PPO Neural Network Checkpoint (`data/models/ppo_curiosity_latest.pt`): TRAINING IN PROGRESS")
        print("==================================================================\n")
        return

    # Set log level
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")

    logger.info("Starting LifeInAdventure-Tools v1.0.0")
    logger.info(f"Config: {args.config}")

    # Register graceful shutdown hooks (Phase P3.2)
    _register_shutdown_hooks()

    # Report missing component modules
    if _MISSING_IMPORTS:
        logger.warning(f"{len(_MISSING_IMPORTS)} component(s) not yet implemented:")
        for m in _MISSING_IMPORTS:
            logger.warning(f"  ∙ {m}")

    # Load configuration
    config = Config.from_yaml(args.config)
    logger.info(f"Emulator: {config.emulator.type}")
    logger.info(f"AI Provider: {config.ai.provider}")
    logger.info(f"RAG KB: {config.rag.db_path}")

    # Phase P3.4: config validation
    issues = config.validate()
    if issues:
        for issue in issues:
            logger.warning(f"Config issue: {issue}")

    # Overlay UI (opened first — shows "Loading KB..." state initially)
    overlay = None
    if OverlayWindow:
        overlay = OverlayWindow(config=config.overlay)
        overlay.show_loading()

    # Background worker for heavy initialization
    threading.Thread(
        target=_init_components,
        args=(config, args.no_ai, overlay),
        daemon=True,
    ).start()
    logger.info("Background initialization worker started. Overlay responsive.")

    try:
        if overlay:
            overlay.run()
        else:
            logger.warning("Overlay not available — running headless (REPL mode).")
            threading.Event().wait()
    except KeyboardInterrupt:
        _graceful_shutdown(signum=2, frame=None)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        raise
    finally:
        _graceful_shutdown()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
