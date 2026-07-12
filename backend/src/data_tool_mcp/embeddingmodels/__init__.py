"""Embedding model system for vector operations.

Maps to Go: internal/embeddingmodels/
"""

from data_tool_mcp.embeddingmodels.base import (
    EmbeddingModel,
    EmbeddingModelConfig,
    VectorFormatter,
    FormatVectorForPgvector,
    register_embedding_model,
    get_embedding_model_config_class,
    decode_embedding_model_config,
)
from data_tool_mcp.embeddingmodels.gemini import GeminiEmbeddingModelConfig

__all__ = [
    "EmbeddingModel",
    "EmbeddingModelConfig",
    "VectorFormatter",
    "FormatVectorForPgvector",
    "register_embedding_model",
    "get_embedding_model_config_class",
    "decode_embedding_model_config",
    "GeminiEmbeddingModelConfig",
]
