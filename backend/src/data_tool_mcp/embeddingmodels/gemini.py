"""Gemini embedding model implementation.

Maps to Go: internal/embeddingmodels/gemini/gemini.go

Supports two backends:
1. Google AI (API Key) — apiKey > GOOGLE_API_KEY > GEMINI_API_KEY
2. Vertex AI (ADC) — project > GOOGLE_CLOUD_PROJECT
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.embeddingmodels.base import (
    EmbeddingModel,
    EmbeddingModelConfig,
    register_embedding_model,
)


class GeminiEmbeddingModel(EmbeddingModel):
    """Gemini embedding model using Google GenAI SDK.

    Maps to Go: internal/embeddingmodels/gemini/ EmbeddingModel struct
    """

    def __init__(self, client: Any, config: GeminiEmbeddingModelConfig):
        self._client = client
        self._config = config

    @property
    def embedding_model_type(self) -> str:
        return "gemini"

    async def embed_parameters(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using Gemini API.

        Maps to Go: EmbedParameters(ctx, []string) ([][]float32, error)
        Uses SEMANTIC_SIMILARITY task type per Go implementation.
        """
        try:
            from google import genai
        except ImportError:
            raise ImportError(
                "google-genai is required for Gemini embedding model. "
                "Install with: pip install google-genai"
            )

        results = []
        # Process in batches (API may have limits)
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            kwargs: dict[str, Any] = {
                "model": self._config.model,
                "contents": batch,
            }
            # Use SEMANTIC_SIMILARITY task type as in Go
            if hasattr(genai, "types"):
                kwargs["config"] = {"task_type": "SEMANTIC_SIMILARITY"}
            if self._config.dimension and self._config.dimension > 0:
                kwargs["output_dimensionality"] = self._config.dimension

            response = await self._client.aio.models.embed(**kwargs)
            for embedding in response.embeddings:
                results.append(embedding.values if hasattr(embedding, "values") else list(embedding))

        return results


@register_embedding_model("gemini")
@dataclass
class GeminiEmbeddingModelConfig(EmbeddingModelConfig):
    """Gemini embedding model configuration.

    Maps to Go: internal/embeddingmodels/gemini/ Config struct

    Fields:
        name: Model instance name
        model: Gemini model name (e.g., "text-embedding-004")
        api_key: Google AI API key (optional, falls back to env vars)
        project: GCP project for Vertex AI (optional)
        location: GCP location for Vertex AI (optional)
        dimension: Output dimension (optional, for dimensionality reduction)
    """

    _name: str = field(init=True, repr=False)
    model: str = "text-embedding-004"
    api_key: str = ""
    project: str = ""
    location: str = ""
    dimension: int = 0

    @property
    def embedding_model_type(self) -> str:
        return "gemini"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> GeminiEmbeddingModelConfig:
        return cls(
            _name=name,
            model=data.get("model", "text-embedding-004"),
            api_key=data.get("apiKey", ""),
            project=data.get("project", ""),
            location=data.get("location", ""),
            dimension=data.get("dimension", 0),
        )

    async def initialize(self) -> GeminiEmbeddingModel:
        """Create Gemini client and return initialized model.

        Maps to Go: Initialize(ctx) (EmbeddingModel, error)

        API Key priority: cfg.ApiKey > GOOGLE_API_KEY > GEMINI_API_KEY
        Project priority: cfg.Project > GOOGLE_CLOUD_PROJECT
        """
        try:
            from google import genai
        except ImportError:
            raise ImportError(
                "google-genai is required for Gemini embedding model. "
                "Install with: pip install google-genai"
            )

        # Resolve API key (Go: API Key > GOOGLE_API_KEY > GEMINI_API_KEY)
        api_key = self.api_key or os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
        project = self.project or os.environ.get("GOOGLE_CLOUD_PROJECT", "")

        if api_key:
            # Google AI backend
            client = genai.Client(api_key=api_key)
        elif project:
            # Vertex AI backend (uses Application Default Credentials)
            client = genai.Client(
                vertexai=True,
                project=project,
                location=self.location or "us-central1",
            )
        else:
            # Fallback: try default credentials
            client = genai.Client()

        return GeminiEmbeddingModel(client=client, config=self)
