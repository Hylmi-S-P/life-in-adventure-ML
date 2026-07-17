"""
screen_capture.py - High-speed Screen Capture & Ad Detection for MuMuPlayer/LDPlayer.
Uses thread-local mss and win32gui to locate emulator window,
with configurable window-relative capture regions,
automatic fallback to PIL.ImageGrab,
and Ad-Shield detection to pause automation during ads.

Coordinate metadata (capture_origin):
  All captured images include their screen-space origin so that OCR bounding
  boxes can be converted back to absolute screen coordinates for click targeting.
  The emulator window rectangle (window_rect) is kept SEPARATE from the capture
  rectangle (capture_rect) — use window_rect for scrolling/focus, use
  capture_origin for OCR→screen coordinate conversion.
"""

import time
import threading
from typing import Dict, List, Any, Optional, Tuple
import loguru

try:
    import mss
    import mss.tools
    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False

try:
    import win32gui
    import win32con
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False

try:
    from PIL import Image, ImageGrab
    import numpy as np
    _PIL_AVAILABLE = True
    _IMAGE_GRAB_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    _IMAGE_GRAB_AVAILABLE = False

logger = loguru.logger


class CapturedFrame:
    """
    Container for a captured frame plus its screen-space coordinate metadata.

    Attributes:
      image:       PIL Image of the captured region (already cropped).
      window_rect:  Full emulator window rect in screen coords {top,left,width,height}.
      capture_rect: Absolute screen rect of the captured image {top,left,width,height}.
      capture_origin: (capture_left, capture_top) — the screen-space origin of the
                   cropped image. Use this to convert OCR box centers back to
                   absolute screen coordinates:  screen_x = capture_left + box_center_x.
    """

    def __init__(
        self,
        image: Any,
        window_rect: Dict[str, int],
        capture_rect: Dict[str, int],
        capture_origin: Tuple[int, int],
    ):
        self.image = image
        self.window_rect = window_rect   # full window rect (for scroll/focus)
        self.capture_rect = capture_rect  # absolute capture rect
        self.capture_origin = capture_origin  # (left, top) screen origin of cropped image


class ScreenCapture:
    """
    Captures frames from LDPlayer/MuMuPlayer or primary screen using thread-local mss
    with automatic high-speed PIL.ImageGrab fallback for robust cross-thread execution.
    Includes Ad-Shield detection to pause AI automation when ads are playing.

    Supports configurable window-relative capture regions to exclude emulator
    toolbar/controls from the captured image. When a region is configured,
    OCR boxes are relative to the cropped image; use CapturedFrame.capture_origin
    to convert them to absolute screen coordinates for click targeting.
    """

    # Fraction of the top of each captured image that is excluded from OCR
    # (emulator toolbar / game chrome).  Applied after capture_region cropping.
    # Crop top 35% of captured frame — the game's static UI header (title bar,
    # character name, HP bar) lives here. OCR, dedup, and click coordinate
    # conversion all crop before processing so they operate on the dialog region.
    # Shared constant; defined here and imported by consumers.
    _ROI_CROP_TOP_FRACTION: float = 0.35

    def __init__(
        self,
        emulator_type: str = "ldplayer",
        capture_interval: float = 1.0,
        capture_region: Optional[Tuple[int, int, int, int]] = None,
    ):
        self.emulator_type = emulator_type
        self.capture_interval = capture_interval
        self.window_rect: Optional[Dict[str, int]] = None
        self.hwnd: Optional[int] = None

        # Window-relative capture region: (rel_x, rel_y, rel_w, rel_h)
        # None = capture the full window.
        self._capture_region: Optional[Tuple[int, int, int, int]] = None
        self._set_capture_region(capture_region)

        self._thread_local = threading.local()
        self.last_capture_time = 0.0
        self.ad_playing = False

        # Thread-safety: lock for shared window_rect / hwnd reads & writes
        # and timing guard for periodic window re-scans.
        self._rect_lock = threading.Lock()
        self._last_window_scan = 0.0

        self._find_emulator_window()

    def _set_capture_region(
        self, region: Optional[Tuple[int, int, int, int]]
    ) -> bool:
        """
        Validate and store a window-relative capture region.
        Returns True if the region is valid, False if it was cleared.
        Raises ValueError for malformed input.
        """
        if region is None:
            self._capture_region = None
            return True
        if not isinstance(region, (tuple, list)) or len(region) != 4:
            raise ValueError(
                f"capture_region must be a 4-element tuple (x, y, w, h), got {region!r}"
            )
        rx, ry, rw, rh = region
        if not all(isinstance(v, (int, float)) for v in region):
            raise ValueError(
                f"capture_region values must be numeric, got {region!r}"
            )
        rx, ry, rw, rh = int(rx), int(ry), int(rw), int(rh)
        if rw <= 0 or rh <= 0:
            raise ValueError(
                f"capture_region width and height must be positive, got w={rw}, h={rh}"
            )
        self._capture_region = (rx, ry, rw, rh)
        return True

    def _get_sct(self) -> Optional[Any]:
        """Get or create a thread-local mss instance to avoid cross-thread GDI/BitBlt errors."""
        if not _MSS_AVAILABLE:
            return None
        if not hasattr(self._thread_local, "sct") or self._thread_local.sct is None:
            try:
                self._thread_local.sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
            except Exception as e:
                logger.debug(f"Could not initialize thread-local mss: {e}")
                self._thread_local.sct = None
        return getattr(self._thread_local, "sct", None)

    def _find_emulator_window(self) -> bool:
        """Locate emulator window coordinates on Windows."""
        if not _WIN32_AVAILABLE:
            logger.debug("win32gui not available. Using primary monitor capture region.")
            return False

        def enum_win_callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if any(k in title.lower() for k in ["mumu", "ldplayer", "bluestacks", "nox", "life in adventure"]):
                    rect = win32gui.GetWindowRect(hwnd)
                    w = rect[2] - rect[0]
                    h = rect[3] - rect[1]
                    if (w > 200 and h > 200) or rect[0] <= -20000:
                        extra.append((hwnd, title, rect))
            return True

        matches = []
        try:
            win32gui.EnumWindows(enum_win_callback, matches)
            if matches:
                target = self.emulator_type.lower() if self.emulator_type else "ldplayer"
                matches.sort(key=lambda x: 0 if target in x[1].lower()
                            else (1 if "ldplayer" in x[1].lower()
                                  else (2 if "life in adventure" in x[1].lower() else 3)))
                hwnd, title, rect = matches[0]
                if rect[0] <= -20000:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    rect = win32gui.GetWindowRect(hwnd)
                new_rect = {
                    "top": rect[1],
                    "left": rect[0],
                    "width": rect[2] - rect[0],
                    "height": rect[3] - rect[1]
                }
                with self._rect_lock:
                    self.hwnd = hwnd
                    self.window_rect = new_rect
                logger.info(f"Found emulator window: '{title}' (HWND: {hwnd}) at {new_rect}")
                return True
        except Exception as e:
            logger.warning(f"Error enumerating windows: {e}")

        sct = self._get_sct()
        if sct:
            monitor = sct.monitors[1]
            with self._rect_lock:
                self.window_rect = {
                    "top": monitor["top"],
                    "left": monitor["left"],
                    "width": monitor["width"],
                    "height": monitor["height"]
                }
            logger.info(f"Using primary monitor region for capture: {self.window_rect}")
        return False

    def _compute_capture_rect(self) -> Optional[Dict[str, int]]:
        """
        Compute the absolute screen rectangle to capture based on window_rect
        and the configured window-relative capture_region.
        Returns None if no window is available.
        """
        if not self.window_rect:
            return None

        wrect = self.window_rect
        if self._capture_region is None:
            # Full window capture
            return dict(wrect)

        rx, ry, rw, rh = self._capture_region
        win_w, win_h = wrect["width"], wrect["height"]

        # Clamp: region must overlap the window
        abs_left   = wrect["left"] + rx
        abs_top    = wrect["top"]  + ry
        abs_width  = min(rw, win_w - rx)
        abs_height = min(rh, win_h - ry)

        if abs_width < 1 or abs_height < 1:
            logger.warning(
                f"capture_region ({rx},{ry},{rw},{rh}) does not overlap "
                f"window {win_w}x{win_h}, ignoring."
            )
            return dict(wrect)  # Fall back to full window

        return {
            "left":   abs_left,
            "top":    abs_top,
            "width":  abs_width,
            "height": abs_height,
        }

    def capture_frame(self) -> Optional[CapturedFrame]:
        """
        Capture a screenshot and return it with coordinate metadata.

        Includes periodic HWND health check + reconnect if emulator closed.
        """
        now = time.time()

        # Rate-limit captures to configured interval.
        if now - self.last_capture_time < self.capture_interval:
            time.sleep(self.capture_interval - (now - self.last_capture_time))
        self.last_capture_time = time.time()

        # Periodic window re-scan + HWND health check.
        if now - self._last_window_scan > 15.0:
            self._health_check_hwnd()
            self._find_emulator_window()
            self._last_window_scan = now

        # Snapshot window_rect under lock for consistent reads.
        with self._rect_lock:
            window_rect = dict(self.window_rect) if self.window_rect else None

        # Compute what to actually capture (window + optional region).
        capture_rect = self._compute_capture_rect()

        # Capture outside the lock — mss/PIL I/O can safely overlap.
        img = None
        if capture_rect:
            try:
                img = self._capture_raw(capture_rect)
            except Exception as e:
                logger.error(f"Failed capturing frame: {e}")

        if img is None:
            return None

        # Ad detection on the captured (possibly cropped) image.
        self.ad_playing = self.detect_ad_state(img)

        return CapturedFrame(
            image=img,
            window_rect=window_rect or {},
            capture_rect=capture_rect or {},
            capture_origin=(
                (capture_rect["left"], capture_rect["top"])
                if capture_rect else (0, 0)
            ),
        )

    # ── HWND health check (A.6) ────────────────────────────────────────
    def _health_check_hwnd(self) -> bool:
        """
        Verify emulator HWND is still valid. If not, log warning and
        allow _find_emulator_window to re-discover it.
        Returns True if HWND is alive.
        """
        if not _WIN32_AVAILABLE:
            return bool(self.window_rect)
        with self._rect_lock:
            hwnd = self.hwnd
        if hwnd is None:
            return False
        try:
            if not win32gui.IsWindow(hwnd):
                logger.warning(
                    f"🪟 Emulator HWND {hwnd} invalid (closed/crashed) — "
                    f"will re-discover on next scan"
                )
                with self._rect_lock:
                    self.hwnd = None
                    self.window_rect = None
                return False
            # Also check if window is still visible
            if not win32gui.IsWindowVisible(hwnd):
                logger.info(f"🪟 Emulator HWND {hwnd} exists but hidden — restoring")
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            return True
        except Exception as e:
            logger.error(f"HWND health check failed: {e}")
            with self._rect_lock:
                self.hwnd = None
                self.window_rect = None
            return False


    def _capture_raw(self, region: Optional[Dict[str, int]]) -> Optional[Any]:
        """Raw capture — no ad detection, no locking. Called by capture_frame()."""
        sct = self._get_sct()
        if sct:
            try:
                if region:
                    mon0 = sct.monitors[0]
                    left = max(mon0["left"], region["left"])
                    top = max(mon0["top"], region["top"])
                    width = min(region["width"], mon0["left"] + mon0["width"] - left)
                    height = min(region["height"], mon0["top"] + mon0["height"] - top)
                    grab_box = {"left": left, "top": top,
                                "width": max(width, 1), "height": max(height, 1)}
                else:
                    grab_box = sct.monitors[1]
                shot = sct.grab(grab_box)
                if not _PIL_AVAILABLE:
                    return shot
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            except Exception as mss_err:
                logger.debug(f"mss grab failed ({mss_err}), resetting thread-local sct...")
                if hasattr(self._thread_local, "sct") and self._thread_local.sct is not None:
                    try:
                        self._thread_local.sct.close()
                    except Exception:
                        pass
                    self._thread_local.sct = None

        # Fallback: PIL.ImageGrab
        if _PIL_AVAILABLE and _IMAGE_GRAB_AVAILABLE:
            try:
                if region:
                    bbox = (region["left"], region["top"],
                            region["left"] + region["width"],
                            region["top"] + region["height"])
                else:
                    bbox = None
                return ImageGrab.grab(bbox=bbox, all_screens=True)
            except Exception as grab_err:
                logger.error(f"PIL.ImageGrab fallback also failed: {grab_err}")

        logger.error("Failed capturing frame: all capture engines failed.")
        return None

    def detect_ad_state(self, img: Any) -> bool:
        """
        Ad-Shield detection: checks for dark screens (video ad transitions)
        and high-contrast top-right 'Skip Ad' areas.

        Optimized: samples a 64x64 thumbnail instead of converting the
        full frame to numpy — ~100x fewer pixels processed per frame.
        """
        if not _PIL_AVAILABLE or not isinstance(img, Image.Image):
            return False

        try:
            thumb = img.resize((64, 64)).convert("L")
            arr = np.frombuffer(thumb.tobytes(), dtype=np.uint8).reshape(64, 64)
            mean_brightness = arr.mean()
            if mean_brightness < 12.0:
                return True

            top_right = arr[:8, 56:]
            if np.std(top_right) > 85.0 and mean_brightness < 45.0:
                return True
        except Exception as e:
            logger.debug(f"Ad check failed: {e}")

        return False

    # ------------------------------------------------------------------ #
    #  Backward-compatible: capture_frame returns a CapturedFrame.
    #  Legacy callers that unpack (image, ad_state) should migrate to
    #   frame = capture_frame()
    #   img   = frame.image
    #   window_rect = frame.window_rect
    #   capture_origin = frame.capture_origin
    # ------------------------------------------------------------------ #
