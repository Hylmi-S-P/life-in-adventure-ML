"""
screen_dedup.py - Perceptual-hash frame deduplication for the auto-play loop.
When the screen has not changed since the last cycle, OCR + RAG can be skipped
entirely, saving the dominant CPU/GPU cost per idle cycle.

Uses aHash (average hash): resize → grayscale → mean threshold → bit pack.
A mean-brightness delta pre-check handles large brightness transitions.
For solid-color frames (all comparison bits = 0), a raw mean comparison is used
as the hash has no entropy to distinguish them.
"""

from typing import Tuple
import numpy as np
from PIL import Image
import loguru

logger = loguru.logger

# Reject frames whose mean pixel brightness differs by more than this from the
# previous frame.  Solid-color screens (e.g. loading vs gameplay) differ by
# 30+ brightness units; anti-aliased sub-pixel noise is ±2 units.
# Reduced from 8→5: tighter threshold prevents false dedup on similar dialog frames.
_MEAN_BRIGHTNESS_DELTA_THRESHOLD = 5


class ScreenDeduplicator:
    """
    Detect whether a captured frame is (near-)identical to the previous one.

    Two checks are applied:
    1. Brightness delta — if the mean pixel brightness changed by more than
       _MEAN_BRIGHTNESS_DELTA_THRESHOLD, the frames are considered different.
    2. Hamming distance between perceptual hashes — if ≤ similarity_threshold,
       the frames are considered the same (handles sub-pixel noise).

    For solid-color frames (all pixels identical → hash comparison bits all 0),
    the raw mean brightness is used as a secondary signal.  If two consecutive
    solid-color frames have the same mean brightness they are considered
    identical; if means differ they are treated as distinct frames.
    """

    def __init__(self, hash_size: int = 8, similarity_threshold: int = 5):
        self._hash_size = hash_size
        self._threshold = similarity_threshold
        self._last_hash: int = 0
        self._has_last = False
        self._repeat_count = 0
        self._last_mean: float = 0.0
        self._last_is_solid: bool = False

    def is_duplicate(self, img) -> Tuple[bool, int]:
        """
        Compare ``img`` against the previous frame.

        Returns ``(is_duplicate, repeat_count)`` where *repeat_count* is how
        many consecutive frames have matched (1 = first repeat).
        """
        h, mean, is_solid = self._ahash_with_mean(img)

        # Pre-check: reject immediately if mean brightness jumped.
        if self._has_last:
            if abs(mean - self._last_mean) > _MEAN_BRIGHTNESS_DELTA_THRESHOLD:
                self._last_hash = h
                self._last_mean = mean
                self._last_is_solid = is_solid
                self._has_last = True
                self._repeat_count = 0
                return False, 0

            # Solid-color fallback: for solid-color frames, the aHash has no
            # entropy (all comparison bits = 0), so two such frames with the SAME
            # mean brightness are the same frame → count as duplicate.
            # Two solid-color frames with DIFFERENT means are distinct → not dup.
            # Pre-check already caught cases where |mean_diff| > 8, so here
            # |mean_diff| ≤ 8. We treat same solid-color as duplicate.
            if is_solid and self._last_is_solid:
                if mean == self._last_mean:
                    # Same solid-color brightness → treat as duplicate
                    self._repeat_count += 1
                    self._last_hash = h
                    self._last_mean = mean
                    self._last_is_solid = is_solid
                    return True, self._repeat_count
                else:
                    # Same-type but different brightness (within threshold)
                    # → treat as new frame, reset count
                    self._last_hash = h
                    self._last_mean = mean
                    self._last_is_solid = is_solid
                    self._repeat_count = 0
                    return False, 0

        if self._has_last:
            diff = bin(h ^ self._last_hash).count("1")
            if diff <= self._threshold:
                self._repeat_count += 1
                self._last_hash = h
                self._last_mean = mean
                self._last_is_solid = is_solid
                return True, self._repeat_count

        self._last_hash = h
        self._last_mean = mean
        self._last_is_solid = is_solid
        self._has_last = True
        self._repeat_count = 0
        return False, 0

    def reset(self):
        """Clear history — call after a click/transition so the next frame is fresh."""
        self._last_hash = 0
        self._has_last = False
        self._repeat_count = 0
        self._last_mean = 0.0
        self._last_is_solid = False

    # ------------------------------------------------------------------ #
    #  aHash with solid-color detection
    # ------------------------------------------------------------------ #
    def _ahash_with_mean(self, img) -> Tuple[int, float, bool]:
        """
        Compute aHash + mean brightness + solid-color flag.

        Returns (hash, mean_brightness, is_solid) where is_solid is True when
        the image is a solid-color frame (all pixels identical after resize).
        Solid-color frames have no entropy in their aHash comparison bits.
        """
        if isinstance(img, np.ndarray):
            if img.ndim == 3 and img.shape[2] in (3, 4):
                img = Image.fromarray(img)
            elif img.ndim == 2:
                img = Image.fromarray(img)
            else:
                img = Image.fromarray(img.astype(np.uint8))

        thumb = img.resize((self._hash_size, self._hash_size), Image.LANCZOS).convert("L")
        arr = np.asarray(thumb, dtype=np.float64)
        mean_val = arr.mean()

        bits = (arr > mean_val).flatten()

        # Detect solid-color: for a solid-color image all pixels equal the mean
        # (or differ only by rounding), so all comparison bits are 0.
        bit_arr = bits.astype(np.float64)
        bit_variance = np.var(bit_arr)
        is_solid = (bit_variance < 0.01)

        # Pack comparison bits into a 64-bit hash.
        result = 0
        for bit in bits:
            result = (result << 1) | int(bit)

        return result, mean_val, bool(is_solid)
