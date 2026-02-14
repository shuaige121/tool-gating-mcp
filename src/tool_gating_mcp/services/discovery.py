# Tool discovery service
# Implements semantic search and tag-based tool discovery

import logging
import os
import re
import zlib
from threading import Lock
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer

from ..models.tool import ToolMatch

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Service for discovering relevant tools based on queries and context."""

    _encoder_lock: Lock = Lock()
    _shared_encoder: SentenceTransformer | None = None
    _encoder_failed: bool = False

    def __init__(self, tool_repo: Any, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Initialize discovery service with tool repository."""
        self.tool_repo = tool_repo
        self.encoder = self._get_shared_encoder(model_name)
        self._tool_embeddings_cache: dict[str, NDArray[np.float64]] = {}

    async def find_relevant_tools(
        self,
        query: str,
        context: str | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[ToolMatch]:
        """Find tools relevant to the query using semantic search and tag matching."""
        # Backward-compatible repository access for older tests/helpers.
        if hasattr(self.tool_repo, "get_all_tools"):
            all_tools = await self.tool_repo.get_all_tools()
        else:
            all_tools = await self.tool_repo.get_all()

        # Filter by tags if provided
        if tags:
            all_tools = [t for t in all_tools if any(tag in t.tags for tag in tags)]

        # If no tools match filters, return empty list
        if not all_tools:
            return []

        # Compute query embedding
        query_text = f"{query} {context or ''}"
        query_embedding = self._get_embedding(query_text)
        query_tokens = set(re.findall(r"[a-z0-9]+", query_text.lower()))

        # Score tools by semantic similarity
        tool_scores: list[ToolMatch] = []
        for tool in all_tools:
            # Guard against malformed repository records.
            if not getattr(tool, "id", None) or not getattr(tool, "name", None):
                continue
            if getattr(tool, "description", None) is None:
                continue

            # Get or compute tool embedding
            tool_text = f"{tool.name} {tool.description} {' '.join(tool.tags)}"
            tool_embedding = self._get_embedding(tool_text, cache_key=tool.id)

            # Compute cosine similarity
            similarity = self._cosine_similarity(query_embedding, tool_embedding)
            lexical_similarity = self._lexical_similarity(query_text, tool_text)
            combined_similarity = max(similarity, lexical_similarity) + (
                0.1 * lexical_similarity
            )

            if tags:
                matched_tags = list(set(tags) & set(tool.tags))
            else:
                matched_tags = [
                    tag for tag in tool.tags if tag.lower() in query_tokens
                ]
            tag_boost = 0.2 * len(matched_tags)

            tool_scores.append(
                ToolMatch(
                    tool=tool,
                    score=float(
                        max(0.0, min(1.0, combined_similarity + tag_boost))
                    ),  # Ensure between 0 and 1
                    matched_tags=matched_tags,
                )
            )

        # Sort by score and return top results
        tool_scores.sort(key=lambda x: x.score, reverse=True)
        return tool_scores[:limit]

    def _get_embedding(
        self, text: str, cache_key: str | None = None
    ) -> NDArray[np.float64]:
        """Get embedding for text, using cache if available."""
        if cache_key and cache_key in self._tool_embeddings_cache:
            return self._tool_embeddings_cache[cache_key]

        if self.encoder is None:
            embedding = self._fallback_embedding(text)
        else:
            try:
                embedding_result = self.encoder.encode(text)
                embedding = np.array(embedding_result, dtype=np.float64)
            except Exception:
                logger.warning("Falling back to hashed embeddings", exc_info=True)
                self.encoder = None
                embedding = self._fallback_embedding(text)

        if cache_key:
            self._tool_embeddings_cache[cache_key] = embedding

        return embedding

    def _fallback_embedding(
        self,
        text: str,
        dimensions: int = 256,
    ) -> NDArray[np.float64]:
        """Cheap deterministic embedding when transformer model is unavailable."""
        vector = np.zeros(dimensions, dtype=np.float64)
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            index = zlib.crc32(token.encode("utf-8")) % dimensions
            vector[index] += 1.0
        return vector

    def _lexical_similarity(self, query_text: str, tool_text: str) -> float:
        """Simple token-overlap score to keep matching fast and deterministic."""
        query_tokens = set(re.findall(r"[a-z0-9]+", query_text.lower()))
        tool_tokens = set(re.findall(r"[a-z0-9]+", tool_text.lower()))
        if not query_tokens or not tool_tokens:
            return 0.0
        overlap = len(query_tokens & tool_tokens)
        return overlap / max(len(query_tokens), len(tool_tokens))

    def _cosine_similarity(self, vec1: Any, vec2: Any) -> float:
        """Compute cosine similarity between two vectors."""
        # Handle numpy arrays and lists
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)

        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    async def search_tools(
        self,
        query: str,
        tags: list[str] | None = None,
        top_k: int = 10,
    ) -> list[ToolMatch]:
        """Search for tools using semantic search (simplified interface)."""
        return await self.find_relevant_tools(
            query=query, context=None, tags=tags, limit=top_k
        )

    @classmethod
    def _get_shared_encoder(cls, model_name: str) -> SentenceTransformer | None:
        use_transformer = os.getenv("TOOL_GATING_USE_TRANSFORMER", "").lower()
        if use_transformer not in {"1", "true", "yes"}:
            cls._encoder_failed = True
            return None

        if cls._shared_encoder is not None:
            return cls._shared_encoder
        if cls._encoder_failed:
            return None

        with cls._encoder_lock:
            if cls._shared_encoder is not None:
                return cls._shared_encoder
            if cls._encoder_failed:
                return None

            try:
                cls._shared_encoder = SentenceTransformer(model_name, device="cpu")
                return cls._shared_encoder
            except Exception:
                logger.warning(
                    "Failed to initialize sentence-transformers model '%s'",
                    model_name,
                    exc_info=True,
                )
                cls._encoder_failed = True
                return None
