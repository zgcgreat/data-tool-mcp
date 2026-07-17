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


def _import_genai() -> Any:
    """导入 google.genai,未安装时抛出带提示的 ImportError。"""
    try:
        from google import genai
    except ImportError:
        raise ImportError(
            "google-genai is required for Gemini embedding model. "
            "Install with: pip install google-genai"
        )
    return genai


def _extract_embedding_values(embedding: Any) -> list[float]:
    """从 embedding 对象中提取 values 列表。"""
    return embedding.values if hasattr(embedding, "values") else list(embedding)


def _add_task_type(genai: Any, kwargs: dict[str, Any]) -> None:
    """若 genai.types 存在,添加 SEMANTIC_SIMILARITY 任务类型。"""
    if hasattr(genai, "types"):
        kwargs["config"] = {"task_type": "SEMANTIC_SIMILARITY"}


class GeminiEmbeddingModel(EmbeddingModel):
    """Gemini embedding model using Google GenAI SDK.

    Maps to Go: internal/embeddingmodels/gemini/ EmbeddingModel struct
    """

    def __init__(self, client: Any, config: GeminiEmbeddingModelConfig):
        """初始化实例。"""
        self._client = client
        self._config = config

    @property
    def embedding_model_type(self) -> str:
        """返回嵌入模型类型标识。"""
        return "gemini"

    def _add_dimension(self, kwargs: dict[str, Any]) -> None:
        """若配置了有效 dimension,添加 output_dimensionality。"""
        if self._config.dimension and self._config.dimension > 0:
            kwargs["output_dimensionality"] = self._config.dimension

    def _build_embed_kwargs(self, genai: Any, batch: list[str]) -> dict[str, Any]:
        """构造单批次 embed 调用的 kwargs。"""
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "contents": batch,
        }
        _add_task_type(genai, kwargs)
        self._add_dimension(kwargs)
        return kwargs

    async def _embed_batch(self, genai: Any, batch: list[str]) -> list[list[float]]:
        """嵌入单批次文本并返回 embedding 向量列表。"""
        kwargs = self._build_embed_kwargs(genai, batch)
        response = await self._client.aio.models.embed(**kwargs)
        return [_extract_embedding_values(e) for e in response.embeddings]

    async def embed_parameters(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using Gemini API.

        Maps to Go: EmbedParameters(ctx, []string) ([][]float32, error)
        Uses SEMANTIC_SIMILARITY task type per Go implementation.
        """
        genai = _import_genai()
        results: list[list[float]] = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            results.extend(await self._embed_batch(genai, texts[i : i + batch_size]))
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
        """返回嵌入模型类型标识。"""
        return "gemini"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> GeminiEmbeddingModelConfig:
        """从字典构造 GeminiEmbeddingModelConfig 实例。"""
        return cls(
            _name=name,
            model=data.get("model", "text-embedding-004"),
            api_key=data.get("apiKey", ""),
            project=data.get("project", ""),
            location=data.get("location", ""),
            dimension=data.get("dimension", 0),
        )

    def _resolve_api_key(self) -> str:
        """解析 API key:配置 > GOOGLE_API_KEY > GEMINI_API_KEY。"""
        return self.api_key or os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")

    def _resolve_project(self) -> str:
        """解析 GCP project:配置 > GOOGLE_CLOUD_PROJECT。"""
        return self.project or os.environ.get("GOOGLE_CLOUD_PROJECT", "")

    def _resolve_location(self) -> str:
        """解析 GCP location:配置 > us-central1 默认值。"""
        return self.location or "us-central1"

    def _create_genai_client(self, genai: Any, api_key: str, project: str) -> Any:
        """根据 api_key/project 创建 genai.Client。"""
        if api_key:
            return genai.Client(api_key=api_key)
        if project:
            return genai.Client(
                vertexai=True,
                project=project,
                location=self._resolve_location(),
            )
        return genai.Client()

    async def initialize(self) -> GeminiEmbeddingModel:
        """Create Gemini client and return initialized model.

        Maps to Go: Initialize(ctx) (EmbeddingModel, error)

        API Key priority: cfg.ApiKey > GOOGLE_API_KEY > GEMINI_API_KEY
        Project priority: cfg.Project > GOOGLE_CLOUD_PROJECT
        """
        genai = _import_genai()
        api_key = self._resolve_api_key()
        project = self._resolve_project()
        client = self._create_genai_client(genai, api_key, project)
        return GeminiEmbeddingModel(client=client, config=self)
