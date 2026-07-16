"""
Vector utility helpers for the Tattva Exam Engine.

Provides :func:`generate_embedding`, which calls the Gemini embeddings API
(``models/text-embedding-004``) and returns a 1 536-dimensional float vector
suitable for storing in the ``chunks.embedding vector(1536)`` column.
"""

from __future__ import annotations

import os
from typing import List


def generate_embedding(text: str) -> List[float]:
    """Return a 1 536-dimensional embedding for *text* using Gemini.

    The Gemini model ``models/text-embedding-004`` is called with
    ``output_dimensionality=1536`` so the result always matches the
    ``vector(1536)`` column defined on the ``chunks`` table.

    Parameters
    ----------
    text:
        The plain-text content to embed. Must be a non-empty string.

    Returns
    -------
    list[float]
        A list of 1 536 floats representing the embedding vector.

    Raises
    ------
    RuntimeError
        If the ``GEMINI_API_KEY`` environment variable is not set.
    ValueError
        If *text* is empty or not a string.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set. "
            "Set it to your Google AI Studio API key before calling generate_embedding()."
        )

    import google.generativeai as genai  # deferred import — avoids hard dependency at module load

    genai.configure(api_key=api_key)

    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        output_dimensionality=1536,
    )

    # The SDK returns a dict with an "embedding" key containing the vector.
    embedding: List[float] = result["embedding"]
    return embedding
