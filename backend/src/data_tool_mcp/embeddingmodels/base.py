"""Embedding model base classes and registry.

Maps to Go: internal/embeddingmodels/embeddingmodels.go
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class EmbeddingModel(ABC):
    """Embedding model interface.

    Maps to Go:
      EmbeddingModelType() string
      ToConfig() EmbeddingModelConfig
      EmbedParameters(ctx, []string) ([][]float32, error)
    """

    @property
    @abstractmethod
    def embedding_model_type(self) -> str:
        """Return the embedding model type identifier."""
        ...

    @abstractmethod
    async def embed_parameters(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of text strings into vectors.

        Maps to Go: EmbedParameters(ctx, []string) ([][]float32, error)
        """
        ...


class EmbeddingModelConfig(ABC):
    """Embedding model configuration interface.

    Maps to Go:
      EmbeddingModelConfigType() string
      Initialize(ctx) (EmbeddingModel, error)
    """

    @property
    @abstractmethod
    def embedding_model_type(self) -> str:
        """Return the embedding model type identifier."""
        ...

    @abstractmethod
    async def initialize(self) -> EmbeddingModel:
        """Create and initialize an EmbeddingModel from this config."""
        ...


# ---------------------------------------------------------------------------
# Vector Formatter
# ---------------------------------------------------------------------------

VectorFormatter = Callable[[list[float]], Any]


def FormatVectorForPgvector(vector_floats: list[float]) -> str:
    """Format a vector as a PostgreSQL pgvector literal string.

    Maps to Go: FormatVectorForPgvector(vectorFloats []float32) any
    Returns: '[0.1,0.2,0.3]' format string
    """
    return "[" + ",".join(str(v) for v in vector_floats) + "]"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_embedding_model_registry: dict[str, type[EmbeddingModelConfig]] = {}


def register_embedding_model(model_type: str):
    """Decorator: register an EmbeddingModelConfig class for a given type."""
    def decorator(cls: type[EmbeddingModelConfig]) -> type[EmbeddingModelConfig]:
        _embedding_model_registry[model_type] = cls
        return cls
    return decorator


def get_embedding_model_config_class(model_type: str) -> type[EmbeddingModelConfig]:
    """Look up a registered EmbeddingModelConfig class by type."""
    cls = _embedding_model_registry.get(model_type)
    if cls is None:
        raise ValueError(f"unknown embedding model type: {model_type!r}")
    return cls


def decode_embedding_model_config(model_type: str, name: str, config_data: dict[str, Any]) -> EmbeddingModelConfig:
    """Decode an embedding model config from raw dict data."""
    cls = get_embedding_model_config_class(model_type)
    return cls.from_dict(name, config_data)
