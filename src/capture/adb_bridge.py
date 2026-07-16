"""
adb_bridge.py - High-Performance Android Debug Bridge (ADB) & UIAutomator Interface.
Provides native Android UI hierarchy dumps and zero-drift OS-level tap commands for
LDPlayer/MuMuPlayer when ADB debugging is enabled, with auto-port discovery.
"""

import subprocess
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple, Any
import loguru

logger = loguru.logger

COMMON_ADB_PORTS = [5555, 5554, 5556, 5558, 62001, 7555]


class AdbBridge:
    """
    Manages ADB connection to local Android emulator instances.
    When connected, enables instant UI DOM extraction and pixel-perfect native taps.
    """

    def __init__(self, target_device: Optional[str] = None):
        self.target_device = target_device
        self.connected = False
        self.adb_screen_size: Optional[Tuple[int, int]] = None
        self._auto_connect()

    def _run_cmd(self, args: List[str], timeout: float = 3.0) -> Optional[str]:
        """Run adb command with safety timeout."""
        cmd = ["adb"]
        if self.target_device and args[0] != "connect" and args[0] != "devices":
            cmd.extend(["-s", self.target_device])
        cmd.extend(args)

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if res.returncode == 0:
                return res.stdout
            return None
        except Exception as e:
            logger.debug(f"ADB command {' '.join(args)} failed: {e}")
            return None

    def _get_screen_size(self) -> Optional[Tuple[int, int]]:
        """
        Query the coordinate space used by `input tap`.

        CRITICAL: `wm size` often reports physical (e.g. 1600x900 landscape) while
        the focused app is rotated portrait (900x1600). Input coordinates follow the
        *logical/app* frame, not physical — using physical size misses every tap.
        Prefer dumpsys window app bounds, then DisplayViewport, then wm size.
        """
        # 1) Focused app bounds: mBounds=[0,0][W,H] under Application tokens
        out = self._run_cmd(["shell", "dumpsys", "window", "displays"], timeout=3.0)
        if out:
            # Prefer app=WxH on Display line, or mBounds of task
            m_app = re.search(r"\bapp=(\d+)x(\d+)\b", out)
            if m_app:
                w, h = int(m_app.group(1)), int(m_app.group(2))
                logger.info(f"📱 ADB app/logical size (dumpsys window app=): {w}x{h}")
                return (w, h)
            # First task mBounds=[0,0][W,H]
            m_bounds = re.search(r"mBounds=\[0,0\]\[(\d+),(\d+)\]", out)
            if m_bounds:
                w, h = int(m_bounds.group(1)), int(m_bounds.group(2))
                logger.info(f"📱 ADB app size (mBounds): {w}x{h}")
                return (w, h)

        # 2) DisplayViewport logicalFrame
        out = self._run_cmd(["shell", "dumpsys", "display"], timeout=3.0)
        if out:
            m = re.search(
                r"logicalFrame=Rect\(0,\s*0\s*-\s*(\d+),\s*(\d+)\)", out
            )
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                logger.info(f"📱 ADB logicalFrame size: {w}x{h}")
                return (w, h)

        # 3) Fallback: wm size (may be wrong orientation)
        out = self._run_cmd(["shell", "wm", "size"], timeout=2.0)
        if out:
            m = re.findall(r"(\d+)x(\d+)", out)
            if m:
                w, h = int(m[-1][0]), int(m[-1][1])
                logger.warning(
                    f"📱 ADB using wm size fallback {w}x{h} "
                    f"(may mismatch rotated app — taps can miss)"
                )
                return (w, h)
        return None

    def _auto_connect(self) -> bool:
        """Attempt to discover and connect to local emulator ADB daemon."""
        # 1. Check if already attached
        out = self._run_cmd(["devices"])
        if out:
            for line in out.strip().splitlines()[1:]:
                parts = line.strip().split("\t")
                if len(parts) == 2 and parts[1] == "device":
                    self.target_device = parts[0]
                    self.connected = True
                    self.adb_screen_size = self._get_screen_size()
                    logger.info(f"🔗 ADB Bridge connected to active emulator: {self.target_device} {self.adb_screen_size or ''}")
                    return True

        # 2. Try common ports if not attached
        for port in COMMON_ADB_PORTS:
            addr = f"127.0.0.1:{port}"
            res = self._run_cmd(["connect", addr], timeout=1.5)
            if res and ("connected to" in res.lower() or "already connected" in res.lower()):
                self.target_device = addr
                self.connected = True
                self.adb_screen_size = self._get_screen_size()
                logger.info(f"🔗 ADB Bridge auto-connected to {addr} {self.adb_screen_size or ''}")
                return True

        logger.debug("ADB Bridge not connected. Emulator ADB debugging may be disabled (will use Win32+OCR fallback).")
        self.connected = False
        return False

    def _scale_pc_to_adb(
        self, x: float, y: float, win_width: int, win_height: int
    ) -> Tuple[int, int]:
        """
        Map PC client-relative coords → emulator internal coords.

        LDPlayer typically *stretches* the Android framebuffer to the client area
        (independent X/Y scale). Also support letterbox/pillarbox when AR differs
        and the content is centered with uniform scale — pick the mapping that
        keeps the point inside [0, adb_w] x [0, adb_h].
        """
        adb_w, adb_h = self.adb_screen_size or (0, 0)
        if not adb_w or not adb_h or win_width <= 0 or win_height <= 0:
            return int(x), int(y)

        # Stretch (default LDPlayer): independent axes
        sx = int(x * adb_w / win_width)
        sy = int(y * adb_h / win_height)

        win_ar = win_width / float(win_height)
        adb_ar = adb_w / float(adb_h)
        if abs(win_ar - adb_ar) > 0.05:
            # Candidate: uniform scale + center offset (letterbox/pillarbox)
            if win_ar > adb_ar:
                scaled_w = win_height * adb_ar
                ox = (win_width - scaled_w) / 2.0
                ux = int((x - ox) * (adb_w / scaled_w))
                uy = int(y * (adb_h / win_height))
            else:
                scaled_h = win_width / adb_ar
                oy = (win_height - scaled_h) / 2.0
                ux = int(x * (adb_w / win_width))
                uy = int((y - oy) * (adb_h / scaled_h))
            # Prefer uniform mapping only if result stays in-bounds
            if 0 <= ux < adb_w and 0 <= uy < adb_h:
                # If stretch is also in-bounds, keep stretch (LDPlayer default).
                # Only switch when stretch is out of bounds.
                if not (0 <= sx < adb_w and 0 <= sy < adb_h):
                    sx, sy = ux, uy

        sx = max(0, min(adb_w - 1, sx))
        sy = max(0, min(adb_h - 1, sy))
        return sx, sy

    def tap(self, x: int, y: int, win_width: Optional[int] = None, win_height: Optional[int] = None) -> bool:
        """Tap at emulator coords; scales from PC client-relative with AR clamp."""
        if not self.connected:
            return False
        if win_width and win_height and self.adb_screen_size:
            ox, oy = x, y
            x, y = self._scale_pc_to_adb(x, y, win_width, win_height)
            logger.info(
                f"📱 ADB tap client({ox},{oy})→device({x},{y}) "
                f"win={win_width}x{win_height} adb={self.adb_screen_size}"
            )
        res = self._run_cmd(["shell", "input", "tap", str(max(0, x)), str(max(0, y))])
        return res is not None

    def tap_text(self, text: str, partial: bool = True) -> bool:
        """
        Pixel-perfect tap via UIAutomator: find node by text, tap its center.
        Best path for choice buttons when OCR text matches Android accessibility tree.
        Unity games often expose little text — returns False if no node found.
        """
        if not self.connected or not text or not text.strip():
            return False
        needle = text.strip().lower()
        nodes = self.dump_ui_nodes()
        if not nodes:
            logger.debug("ADB tap_text: no UIAutomator nodes (Unity may not expose text)")
            return False
        best = None
        best_score = 0
        for n in nodes:
            t = (n.get("text") or "").strip().lower()
            if not t:
                continue
            if t == needle:
                best = n
                best_score = 100
                break
            if partial and (needle in t or t in needle) and len(t) >= 2:
                score = min(len(needle), len(t))
                if score > best_score:
                    best_score = score
                    best = n
        if not best:
            return False
        cx, cy = best["center"]
        logger.info(f"📱 ADB UIAutomator tap_text '{text[:40]}' → device({cx},{cy})")
        res = self._run_cmd(["shell", "input", "tap", str(cx), str(cy)])
        return res is not None

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
        win_width: Optional[int] = None,
        win_height: Optional[int] = None,
    ) -> bool:
        """Swipe inside emulator; same scaling as tap."""
        if not self.connected:
            return False
        if win_width and win_height and self.adb_screen_size:
            x1, y1 = self._scale_pc_to_adb(x1, y1, win_width, win_height)
            x2, y2 = self._scale_pc_to_adb(x2, y2, win_width, win_height)
        res = self._run_cmd(
            [
                "shell", "input", "swipe",
                str(max(0, x1)), str(max(0, y1)),
                str(max(0, x2)), str(max(0, y2)),
                str(duration_ms),
            ]
        )
        return res is not None

    def dump_ui_nodes(self) -> List[Dict[str, Any]]:
        """
        Extract exact UIAutomator XML hierarchy and parse text nodes with bounding boxes.
        Returns list of dicts: [{'text': str, 'bounds': (left, top, right, bottom), 'center': (x, y)}]
        """
        if not self.connected:
            return []

        # Dump XML hierarchy to device and read output
        self._run_cmd(["shell", "uiautomator", "dump", "/sdcard/window_dump.xml"], timeout=4.0)
        xml_data = self._run_cmd(["shell", "cat", "/sdcard/window_dump.xml"], timeout=3.0)
        
        if not xml_data or "<?xml" not in xml_data:
            return []

        nodes = []
        try:
            root = ET.fromstring(xml_data)
            for node in root.iter("node"):
                text = node.get("text", "").strip()
                bounds_str = node.get("bounds", "")
                if text and bounds_str:
                    # Parse bounds string like "[300,670][900,740]"
                    m = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
                    if len(m) == 2:
                        left, top = int(m[0][0]), int(m[0][1])
                        right, bottom = int(m[1][0]), int(m[1][1])
                        center_x = int((left + right) / 2)
                        center_y = int((top + bottom) / 2)
                        nodes.append({
                            "text": text,
                            "bounds": (left, top, right, bottom),
                            "center": (center_x, center_y)
                        })
        except Exception as e:
            logger.debug(f"UIAutomator XML parse failed: {e}")

        return nodes
