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
    register_tool,
)


async def _get_spark_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> ServerlessSparkSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = await source_provider.get_source(source_name)
    if source is None:
        await source_provider.release_source(source_name)
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, ServerlessSparkSource):
        await source_provider.release_source(source_name)
        raise TypeError(f"source {source_name!r} is not a Serverless Spark source")
    return source


class SparkGenericTool(BaseTool):
    """Generic Serverless Spark tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = await _get_spark_source(source_provider, self._source_name, self.name)
        try:
            tt = self._tool_type

            if tt == "serverless-spark-list-sessions":
                sessions = await source.list_sessions()
                return {"sessions": sessions}
            elif tt == "serverless-spark-get-session":
                session = await source.get_session(params["session_id"])
                return {"session": session}
            elif tt == "serverless-spark-list-batches":
                batches = await source.list_batches()
                return {"batches": batches}
            elif tt == "serverless-spark-get-batch":
                batch = await source.get_batch(params["batch_id"])
                return {"batch": batch}
            elif tt == "serverless-spark-create-spark-batch":
                result = await source.create_spark_batch(params["batch_id"], params.get("batch", {}))
                return {"result": result}
            elif tt == "serverless-spark-create-pyspark-batch":
                result = await source.create_pyspark_batch(
                    params["batch_id"], params["main_python_file_uri"], params.get("args"),
                )
                return {"result": result}
            elif tt == "serverless-spark-cancel-batch":
                result = await source.cancel_batch(params["batch_id"])
                return {"result": result}
            elif tt == "serverless-spark-get-session-template":
                return {"tool_type": tt, "note": "Session template retrieval via Dataproc API"}
            else:
                raise ValueError(f"unknown Serverless Spark tool type: {tt}")
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


_SPARK_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    ("serverless-spark-list-sessions", "List all Serverless Spark sessions", [], True),
    ("serverless-spark-get-session", "Get a Serverless Spark session",
     [ParameterManifest(name="session_id", type="string", description="Session ID", required=True)], True),
    ("serverless-spark-list-batches", "List all Serverless Spark batches", [], True),
    ("serverless-spark-get-batch", "Get a Serverless Spark batch",
     [ParameterManifest(name="batch_id", type="string", description="Batch ID", required=True)], True),
    ("serverless-spark-create-spark-batch", "Create a Spark batch",
     [ParameterManifest(name="batch_id", type="string", description="Batch ID", required=True),
      ParameterManifest(name="batch", type="object", description="Batch configuration", required=False)], False),
    ("serverless-spark-create-pyspark-batch", "Create a PySpark batch",
     [ParameterManifest(name="batch_id", type="string", description="Batch ID", required=True),
      ParameterManifest(name="main_python_file_uri", type="string", description="Main Python file URI", required=True),
      ParameterManifest(name="args", type="array", description="Arguments", required=False)], False),
    ("serverless-spark-cancel-batch", "Cancel a Serverless Spark batch",
     [ParameterManifest(name="batch_id", type="string", description="Batch ID", required=True)], False),
    ("serverless-spark-get-session-template", "Get a Serverless Spark session template",
     [ParameterManifest(name="template_id", type="string", description="Session template ID", required=True)], True),
]


def _make_spark_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool):
    @register_tool(tool_type)
    @dataclass
    class _SparkToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _SparkToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> SparkGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return SparkGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _SparkToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _SparkToolConfig.__qualname__ = _SparkToolConfig.__name__
    return _SparkToolConfig


for _tool_type, _desc, _params, _ro in _SPARK_TOOLS:
    _make_spark_tool_config(_tool_type, _desc, _params, _ro)
