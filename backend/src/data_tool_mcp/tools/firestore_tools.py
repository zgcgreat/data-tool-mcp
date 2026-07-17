"""Firestore tools — 9 tools for Firestore document and collection management.

Maps to Go: internal/tools/firestore/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.firestore_source import FirestoreSource
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
# Firestore 操作分发表 — handler 签名 (source, params) -> dict
# ---------------------------------------------------------------------------

async def _fs_list_collections(source: FirestoreSource, params: dict[str, Any]) -> dict[str, Any]:
    """列出Firestore的集合列表。"""
    return {"collections": await source.list_collections()}

async def _fs_get_documents(source: FirestoreSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Firestore的文档列表。"""
    return {"documents": await source.get_documents(params["collection"], params.get("limit", 100))}

async def _fs_add_documents(source: FirestoreSource, params: dict[str, Any]) -> dict[str, Any]:
    """添加Firestore的文档列表。"""
    return {"document_ids": await source.add_documents(params["collection"], params["documents"])}

async def _fs_update_document(source: FirestoreSource, params: dict[str, Any]) -> dict[str, Any]:
    """更新Firestore的文档。"""
    await source.update_document(params["collection"], params["doc_id"], params["data"])
    return {"updated": True}

async def _fs_delete_documents(source: FirestoreSource, params: dict[str, Any]) -> dict[str, Any]:
    """删除Firestore的文档列表。"""
    await source.delete_documents(params["collection"], params["doc_ids"])
    return {"deleted": True}

async def _fs_query(source: FirestoreSource, params: dict[str, Any]) -> dict[str, Any]:
    """查询 Firestore 数据。"""
    docs = await source.query(
        params["collection"], params["field_path"],
        params["op"], params["value"], params.get("limit", 100),
    )
    return {"documents": docs}

async def _fs_query_collection(source: FirestoreSource, params: dict[str, Any]) -> dict[str, Any]:
    """查询Firestore的集合。"""
    docs = await source.query_collection(params["collection"], params["queries"], params.get("limit", 100))
    return {"documents": docs}

async def _fs_get_rules(source: FirestoreSource, params: dict[str, Any]) -> dict[str, Any]:
    """获取Firestore的安全规则。"""
    return {"rules": await source.get_rules()}

async def _fs_validate_rules(source: FirestoreSource, params: dict[str, Any]) -> dict[str, Any]:
    """验证Firestore的安全规则。"""
    return {"validation": await source.validate_rules(params["rules_text"])}


_FS_DISPATCH: dict[str, Any] = {
    "firestore-list-collections": _fs_list_collections,
    "firestore-get-documents": _fs_get_documents,
    "firestore-add-documents": _fs_add_documents,
    "firestore-update-document": _fs_update_document,
    "firestore-delete-documents": _fs_delete_documents,
    "firestore-query": _fs_query,
    "firestore-query-collection": _fs_query_collection,
    "firestore-get-rules": _fs_get_rules,
    "firestore-validate-rules": _fs_validate_rules,
}


# ---------------------------------------------------------------------------
# Generic Firestore tool
# ---------------------------------------------------------------------------

class FirestoreGenericTool(BaseTool):
    """Generic Firestore tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        """初始化工具配置。"""
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        """执行工具调用，返回查询结果。"""
        source = await _get_typed_source_async(source_provider, self._source_name, self.name, FirestoreSource)
        try:
            handler = _FS_DISPATCH.get(self._tool_type)
            if handler is None:
                raise ValueError(f"unknown Firestore tool type: {self._tool_type}")
            return await handler(source, params)
        finally:
            await source_provider.release_source(self._source_name)

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        """返回工具清单，包含名称、描述和参数定义。"""
        return ToolManifest(description=self.description, parameters=self._param_defs, auth_required=self.auth_required)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_FS_TOOLS: list[tuple[str, str, list[ParameterManifest], bool]] = [
    ("firestore-list-collections", "List all Firestore collections", [], True),
    ("firestore-get-documents", "Get documents from a Firestore collection",
     [ParameterManifest(name="collection", type="string", description="Collection name", required=True),
      ParameterManifest(name="limit", type="integer", description="Max documents to return", required=False)], True),
    ("firestore-add-documents", "Add documents to a Firestore collection",
     [ParameterManifest(name="collection", type="string", description="Collection name", required=True),
      ParameterManifest(name="documents", type="array", description="Array of documents to add", required=True)], False),
    ("firestore-update-document", "Update a document in Firestore",
     [ParameterManifest(name="collection", type="string", description="Collection name", required=True),
      ParameterManifest(name="doc_id", type="string", description="Document ID", required=True),
      ParameterManifest(name="data", type="object", description="Fields to update", required=True)], False),
    ("firestore-delete-documents", "Delete documents from Firestore",
     [ParameterManifest(name="collection", type="string", description="Collection name", required=True),
      ParameterManifest(name="doc_ids", type="array", description="Array of document IDs to delete", required=True)], False),
    ("firestore-query", "Query a Firestore collection with a single filter",
     [ParameterManifest(name="collection", type="string", description="Collection name", required=True),
      ParameterManifest(name="field_path", type="string", description="Field path to filter on", required=True),
      ParameterManifest(name="op", type="string", description="Comparison operator", required=True),
      ParameterManifest(name="value", type="string", description="Value to compare against", required=True),
      ParameterManifest(name="limit", type="integer", description="Max results", required=False)], True),
    ("firestore-query-collection", "Query a Firestore collection with multiple filters",
     [ParameterManifest(name="collection", type="string", description="Collection name", required=True),
      ParameterManifest(name="queries", type="array", description="Array of filter objects {field, op, value}", required=True),
      ParameterManifest(name="limit", type="integer", description="Max results", required=False)], True),
    ("firestore-get-rules", "Get Firestore security rules", [], True),
    ("firestore-validate-rules", "Validate Firestore security rules",
     [ParameterManifest(name="rules_text", type="string", description="Rules text to validate", required=True)], True),
]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _make_fs_tool_config(tool_type: str, description: str, param_defs: list[ParameterManifest], read_only: bool):
    """构造Firestore工具配置。"""
    @register_tool(tool_type)
    @dataclass
    class _FSToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            """返回工具类型标识符。"""
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _FSToolConfig:
            """从字典创建配置实例。"""
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> FirestoreGenericTool:
            """创建并初始化工具实例。"""
            cfg = ConfigBase(name=self._name, description=self.description)
            return FirestoreGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _FSToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _FSToolConfig.__qualname__ = _FSToolConfig.__name__
    return _FSToolConfig


for _tool_type, _desc, _params, _ro in _FS_TOOLS:
    _make_fs_tool_config(_tool_type, _desc, _params, _ro)
