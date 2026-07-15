"""
metrics.py - Per-stage timing, error rate, and cache hit-rate collector.
Logs structured telemetry for the auto-play loop so performance regressions
can be spotted quickly. The health report is surfaced via a button in the
overlay UI.
"""

import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Optional

import loguru

logger = loguru.logger

# Known pipeline stages.
STAGE_CAPTURE = "capture"
STAGE_OCR = "ocr"
STAGE_RAG = "rag"
STAGE_DECIDE = "decide"
STAGE_CLICK = "click"
STAGE_TOTAL = "total"


class MetricsCollector:
    """
    Thread-safe-ish metrics collector (safe for the single auto-play thread).

    Usage::

        m = MetricsCollector()

        with m.time_stage("ocr"):
            text, boxes = ocr.extract_text_and_boxes(img)
        # appends elapsed_ms to m._timings["ocr"]

        m.record_cache("rag", hit=True)   # cache hit
        m.record_cache("rag", hit=False)  # cache miss

        report = m.get_health_report()
        print(report)
    """

    def __init__(self, window_size: int = 100):
        self._timings: dict = defaultdict(lambda: deque(maxlen=window_size))
        self._errors: defaultdict = defaultdict(int)
        self._cache_hits: defaultdict = defaultdict(int)
        self._cache_misses: defaultdict = defaultdict(int)

    @contextmanager
    def time_stage(self, stage: str):
        """Context manager — records elapsed milliseconds on exit."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self._timings[stage].append(elapsed_ms)

    def record_error(self, stage: str, error_type: str) -> None:
        """Increment error counter for stage."""
        self._errors[f"{stage}:{error_type}"] += 1

    def record_cache(self, component: str, hit: bool) -> None:
        """Record a cache hit or miss for a component."""
        if hit:
            self._cache_hits[component] += 1
        else:
            self._cache_misses[component] += 1

    def get_health_report(self) -> dict:
        """
        Return a dict with summary statistics over the rolling window::

            {
              "capture": {"avg_ms": float, "p95_ms": float, "count": int},
              "ocr":     {...},
              "rag":     {...},
              "decide":  {...},
              "click":   {...},
              "total":   {...},
              "errors":  {"capture:KeyError": int, ...},
              "cache_hit_rate:rag": 0.73,
              "cache_hit_rate:decide": 0.91,
            }
        """
        report: dict = {}

        for stage, times in self._timings.items():
            if not times:
                continue
            sorted_times = sorted(times)
            n = len(sorted_times)
            report[stage] = {
                "avg_ms": round(sum(times) / n, 1),
                "p95_ms": round(sorted_times[int(n * 0.95)], 1),
                "min_ms": round(sorted_times[0], 1),
                "max_ms": round(sorted_times[-1], 1),
                "count": n,
            }

        if self._errors:
            report["errors"] = dict(self._errors)

        for comp in set(list(self._cache_hits) + list(self._cache_misses)):
            h = self._cache_hits.get(comp, 0)
            m = self._cache_misses.get(comp, 0)
            total = h + m
            if total > 0:
                report[f"cache_hit_rate:{comp}"] = round(h / total, 3)

        return report

    def log_summary(self) -> None:
        """Log a compact one-line summary to the app log."""
        r = self.get_health_report()
        parts = []
        for stage in (STAGE_CAPTURE, STAGE_OCR, STAGE_RAG, STAGE_DECIDE, STAGE_CLICK):
            if stage in r:
                parts.append(f"{stage}={r[stage]['avg_ms']:.0f}ms")
        if parts:
            logger.info(" | ".join(parts))

    def reset(self) -> None:
        """Clear all collected metrics."""
        self._timings.clear()
        self._errors.clear()
        self._cache_hits.clear()
        self._cache_misses.clear()
