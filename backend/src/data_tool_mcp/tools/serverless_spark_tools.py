"""Serverless Spark tools — 8 tools for Dataproc Serverless Spark.

Maps to Go: internal/tools/serverlessspark/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.serverlessspark import ServerlessSparkSource
from data_tool_mcp.tools.base import (
    BaseTool,
    ConfigBase,
    ParameterManifest,
    SourceProvider,
    ToolAnnotations,
    ToolConfig,
    ToolManifest,
    _get_typed_source_async,
    register_tool,
)


# ---------------------------------------------------------------------------
# Serverless Spark 操作分发表 — handler 签名 (source, params) -> dict
# ---------------------------------------------------------------------------


async def _sp_list_sessions(
    source: ServerlessSparkSource, params: dict[str, Any]
) -> dict[str, Any]:
    """列出Serverless Spark的会话列表。"""
    return {"sessions": await source.list_sessions()}


async def _sp_get_session(source: ServerlessSparkSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Serverless Spark的会话。"""
    return {"session": await source.get_session(params["session_id"])}


async def _sp_list_batches(source: ServerlessSparkSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Serverless Spark的批处理列表。"""
    return {"batches": await source.list_batches()}


async def _sp_get_batch(source: ServerlessSparkSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Serverless Spark的批处理。"""
    return {"batch": await source.get_batch(params["batch_id"])}


async def _sp_create_spark_batch(
    source: ServerlessSparkSource, params: dict[str, Any]
) -> dict[str, Any]:
    """创建Serverless Spark的Spark 批处理。"""
    return {"result": await source.create_spark_batch(params["batch_id"], params.get("batch", {}))}


async def _sp_create_pyspark_batch(
    source: ServerlessSparkSource, params: dict[str, Any]
) -> dict[str, Any]:
    """创建Serverless Spark的PySpark 批处理。"""
    return {
        "result": await source.create_pyspark_batch(
            params["batch_id"], params["main_python_file_uri"], params.get("args")
        )
    }


async def _sp_cancel_batch(source: ServerlessSparkSource, params: dict[str, Any]) -> dict[str, Any]:
    """取消Serverless Spark的批处理。"""
    return {"result": await source.cancel_batch(params["batch_id"])}


async def _sp_get_session_template(
    source: ServerlessSparkSource, params: dict[str, Any]
) -> dict[str, Any]:
    """获取Serverless Spark的会话模板。"""
    return {
        "tool_type": "serverless-spark-get-session-template",
        "note": "Session template retrieval via Dataproc API",
    }


_SP_DISPATCH: dict[str, Any] = {
    "serverless-spark-list-sessions": _sp_list_sessions,
    "serverless-spark-get-session": _sp_get_session,
    "serverless-spark-list-batches": _sp_list_batches,
    "serverless-spark-get-batch": _sp_get_batch,
    "serverless-spark-create-spark-batch": _sp_create_spark_batch,
    "serverless-spark-create-pyspark-batch": _sp_create_pyspark_batch,
    "serverless-spark-cancel-batch": _sp_cancel_batch,
    "serverless-spark-get-session-template": _sp_get_session_template,
}


class SparkGenericTool(BaseTool):
    """Generic Serverless Spark tool that dispatches based on tool type."""

    def __init__(
        self,
        cfg: ConfigBase,
        source_name: str,
        tool_type: str,
        param_defs: list[ParameterManifest],
        read_only: bool,
    ):
        """初始化工具配置。"""
        ann = (
            ToolAnnotations(read_only_hint=True)
            if read_only
            else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        )
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(
            source_provider, self._source_name, self.name, ServerlessSparkSource
        )
        try:
            handler = _SP_DISPATCH.get(self._tool_type)
            if handler is None:
                raise ValueError(f"unknown Serverless Spark tool type: {self._tool_type}")
            return await handler(source, params)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(
            description=self.description,
            parameters=self._param_defs,
            auth_required=self.auth_required,
        )


_SPARK_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    ("serverless-spark-list-sessions", "List all Serverless Spark sessions", [], True),
    (
        "serverless-spark-get-session",
        "Get a Serverless Spark session",
        [
            ParameterManifest(
                name="session_id", type="string", description="Session ID", required=True
            )
        ],
        True,
    ),
    ("serverless-spark-list-batches", "List all Serverless Spark batches", [], True),
    (
        "serverless-spark-get-batch",
        "Get a Serverless Spark batch",
        [ParameterManifest(name="batch_id", type="string", description="Batch ID", required=True)],
        True,
    ),
    (
        "serverless-spark-create-spark-batch",
        "Create a Spark batch",
        [
            ParameterManifest(
                name="batch_id", type="string", description="Batch ID", required=True
            ),
            ParameterManifest(
                name="batch", type="object", description="Batch configuration", required=False
            ),
        ],
        False,
    ),
    (
        "serverless-spark-create-pyspark-batch",
        "Create a PySpark batch",
        [
            ParameterManifest(
                name="batch_id", type="string", description="Batch ID", required=True
            ),
            ParameterManifest(
                name="main_python_file_uri",
                type="string",
                description="Main Python file URI",
                required=True,
            ),
            ParameterManifest(name="args", type="array", description="Arguments", required=False),
        ],
        False,
    ),
    (
        "serverless-spark-cancel-batch",
        "Cancel a Serverless Spark batch",
        [ParameterManifest(name="batch_id", type="string", description="Batch ID", required=True)],
        False,
    ),
    (
        "serverless-spark-get-session-template",
        "Get a Serverless Spark session template",
        [
            ParameterManifest(
                name="template_id", type="string", description="Session template ID", required=True
            )
        ],
        True,
    ),
]


def _make_spark_tool_config(
    tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool
):
    """构造Serverless Spark工具配置。"""

    @register_tool(tool_type)
    @dataclass
    class _SparkToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _SparkToolConfig:
            """从字典创建配置实例。"""
            return cls(
                _name=name,
                source=data.get("source", ""),
                description=data.get("description", description),
            )

        async def initialize(self) -> SparkGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return SparkGenericTool(
                cfg=cfg,
                source_name=self.source,
                tool_type=tool_type,
                param_defs=param_defs,
                read_only=read_only,
            )

    _SparkToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _SparkToolConfig.__qualname__ = _SparkToolConfig.__name__
    return _SparkToolConfig


for _tool_type, _desc, _params, _ro in _SPARK_TOOLS:
    _make_spark_tool_config(_tool_type, _desc, _params, _ro)
