"""
text_normalizer.py - Text Normalization for multilingual OCR output (Korean, English, Indonesian).
Cleans punctuation, normalizes spacing, and corrects common OCR misrecognitions.
"""

import re
import loguru

logger = loguru.logger


class TextNormalizer:
    """Normalizes raw OCR string before querying the RAG knowledge base."""

    @staticmethod
    def normalize(text: str) -> str:
        """Clean and normalize raw text extracted from screen images."""
        if not text:
            return ""

        # Remove HTML/XML-like formatting tokens or stray control characters
        cleaned = re.sub(r"<[^>]+>", "", text)
        
        # Replace multiple spaces/newlines with single space
        cleaned = re.sub(r"\s+", " ", cleaned)
        
        # Strip excessive decorative symbols around text
        cleaned = re.sub(r"[=*~_#^/]+", " ", cleaned)
        
        return cleaned.strip()
