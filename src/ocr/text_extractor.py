"""
text_extractor.py - Optical Character Recognition (OCR) Engine.
Extracts event and choice text from screen capture frames using EasyOCR / Tesseract with fallback.

Performance notes:
- Single readtext() pass (detail=1) returns both text and bounding boxes.
- Thread-safe: all reader access is serialized via a Lock (EasyOCR/PyTorch not thread-safe).
- Optional GPU auto-detection and region-of-interest cropping for speed.
"""

import threading
from typing import List, Any, Optional, Tuple, Dict
import loguru

import numpy as np  # hoisted — was previously imported per-call

from src.ocr.text_normalizer import TextNormalizer

try:
    import easyocr
    _EASYOCR_AVAILABLE = True
except ImportError:
    _EASYOCR_AVAILABLE = False

try:
    import pytesseract
    _TESSERACT_AVAILABLE = True
except ImportError:
    _TESSERACT_AVAILABLE = False

logger = loguru.logger


class OcrEngine:
    """Extracts text (and bounding boxes) from PIL or NumPy image frames."""

    def __init__(
        self,
        languages: Optional[List[str]] = None,
        gpu: Any = "auto",
        roi_crop: bool = True,
        resize_factor: float = 1.0,
    ):
        self.languages = languages or ["ko", "en"]
        # EasyOCR Korean compatibility safeguard: max 2 langs when ko present
        if "ko" in self.languages and len(self.languages) > 2:
            logger.debug("EasyOCR Korean compatibility safeguard: restricting languages to ['ko', 'en'].")
            self.languages = ["ko", "en"]

        # GPU auto-detection
        if gpu == "auto":
            gpu = self._detect_gpu()
        self.gpu = gpu

        # ROI crop: LiA dialog + choices live in the bottom ~65% of the window.
        # Cropping the top band (~35%) before OCR cuts pixels processed significantly.
        self.roi_crop = roi_crop
        self.resize_factor = max(0.25, min(1.0, float(resize_factor)))

        # Thread safety: EasyOCR's Reader.readtext() is NOT thread-safe.
        self._lock = threading.Lock()
        self.reader = None

        if _EASYOCR_AVAILABLE:
            try:
                self.reader = easyocr.Reader(self.languages, gpu=self.gpu, verbose=False)
                logger.info(f"Initialized EasyOCR engine (gpu={self.gpu}, roi_crop={self.roi_crop}, resize={self.resize_factor}).")
            except Exception as e:
                logger.warning(f"EasyOCR init failed: {e}")

    @staticmethod
    def _detect_gpu() -> bool:
        """Detect NVIDIA CUDA availability via torch."""
        try:
            import torch
            return bool(torch.cuda.is_available())
        except ImportError:
            return False
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    #  Image preprocessing helpers
    # ------------------------------------------------------------------ #
    def _preprocess(self, image: Any) -> Any:
        """Apply optional ROI crop + resize to shrink the frame before OCR."""
        if image is None:
            return None
        img = image
        try:
            # ROI crop: keep bottom 65% (dialogue + choice region for LiA)
            if self.roi_crop and hasattr(img, "size"):
                w, h = img.size
                if h > 200:  # only crop reasonably-sized frames
                    img = img.crop((0, int(h * 0.35), w, h))
            # Downscale for faster OCR (EasyOCR re-scales internally anyway)
            if self.resize_factor < 1.0 and hasattr(img, "resize"):
                new_w = max(64, int(img.width * self.resize_factor))
                new_h = max(64, int(img.height * self.resize_factor))
                img = img.resize((new_w, new_h))
        except Exception as e:
            logger.debug(f"OCR preprocess skipped: {e}")
        return img

    @staticmethod
    def _build_box(bbox: Any, text: str, conf: Any) -> Optional[Dict[str, Any]]:
        """Convert a raw EasyOCR (bbox, text, conf) tuple into a structured dict."""
        clean_text = TextNormalizer.normalize(text).strip()
        if not clean_text:
            return None
        try:
            center_x = int((bbox[0][0] + bbox[2][0]) / 2)
            center_y = int((bbox[0][1] + bbox[2][1]) / 2)
        except (IndexError, TypeError):
            return None
        return {
            "text": clean_text,
            "bbox": bbox,
            "center": (center_x, center_y),
            "confidence": float(conf),
        }

    # ------------------------------------------------------------------ #
    #  Primary API — single-pass extraction
    # ------------------------------------------------------------------ #
    def extract_text_and_boxes(self, image: Any) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Run a SINGLE readtext(detail=1) pass and derive both plain text and
        bounding boxes from the same result. Eliminates the previous double-OCR
        bottleneck where extract_text() + extract_text_with_boxes() each ran
        a full forward pass on the same frame.

        Returns (plain_text, boxes) where boxes is a list of:
            {'text': str, 'bbox': list, 'center': (int, int), 'confidence': float}
        """
        if image is None:
            return "", []

        # Unpack CapturedFrame wrapper if passed
        if hasattr(image, "image"):
            image = image.image

        # Tesseract fallback path (no bounding-box lock issues, single call)
        if not self.reader:
            if _TESSERACT_AVAILABLE:
                try:
                    raw_text = pytesseract.image_to_string(self._preprocess(image), lang="kor+eng")
                    return TextNormalizer.normalize(raw_text), []
                except Exception as e:
                    logger.debug(f"Pytesseract extraction failed: {e}")
            return "", []

        img = self._preprocess(image)

        with self._lock:  # serialize reader access — EasyOCR is not thread-safe
            try:
                arr = np.asarray(img)
                raw_results = self.reader.readtext(arr, detail=1)
            except Exception as e:
                logger.debug(f"EasyOCR extraction failed: {e}")
                return "", []

        # Derive both outputs from the single pass
        boxes: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        for bbox, text, conf in raw_results:
            normalized = TextNormalizer.normalize(text).strip()
            if normalized:
                text_parts.append(normalized)
            box = self._build_box(bbox, text, conf)
            if box:
                boxes.append(box)

        plain_text = " ".join(text_parts)
        return plain_text, boxes

    # ------------------------------------------------------------------ #
    #  Backward-compatible wrappers (callers updated incrementally)
    # ------------------------------------------------------------------ #
    def extract_text(self, image: Any) -> str:
        """Extract all text lines from given image frame (backward compat)."""
        text, _ = self.extract_text_and_boxes(image)
        return text

    def extract_text_with_boxes(self, image: Any) -> List[Dict[str, Any]]:
        """Extract text with bounding boxes (backward compat)."""
        _, boxes = self.extract_text_and_boxes(image)
        return boxes
