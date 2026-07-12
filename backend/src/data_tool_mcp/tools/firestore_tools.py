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
    register_tool,
)


def _get_firestore_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> FirestoreSource:
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, FirestoreSource):
        raise TypeError(f"source {source_name!r} is not a Firestore source")
    return source


# ---------------------------------------------------------------------------
# Generic Firestore tool
# ---------------------------------------------------------------------------

class FirestoreGenericTool(BaseTool):
    """Generic Firestore tool that dispatches based on tool type."""

    def __init__(self, cfg: ConfigBase, source_name: str, tool_type: str, param_defs: list[ParameterManifest], read_only: bool):
        ann = ToolAnnotations(read_only_hint=True) if read_only else ToolAnnotations(read_only_hint=False, destructive_hint=True)
        super().__init__(cfg, annotations=ann)
        self._source_name = source_name
        self._tool_type = tool_type
        self._param_defs = param_defs

    async def invoke(self, params: dict[str, Any], source_provider: SourceProvider | None = None, access_token: str = "") -> Any:
        source = _get_firestore_source(source_provider, self._source_name, self.name)

        if self._tool_type == "firestore-list-collections":
            collections = await source.list_collections()
            return {"collections": collections}
        elif self._tool_type == "firestore-get-documents":
            docs = await source.get_documents(params["collection"], params.get("limit", 100))
            return {"documents": docs}
        elif self._tool_type == "firestore-add-documents":
            ids = await source.add_documents(params["collection"], params["documents"])
            return {"document_ids": ids}
        elif self._tool_type == "firestore-update-document":
            await source.update_document(params["collection"], params["doc_id"], params["data"])
            return {"updated": True}
        elif self._tool_type == "firestore-delete-documents":
            await source.delete_documents(params["collection"], params["doc_ids"])
            return {"deleted": True}
        elif self._tool_type == "firestore-query":
            docs = await source.query(
                params["collection"], params["field_path"],
                params["op"], params["value"], params.get("limit", 100),
            )
            return {"documents": docs}
        elif self._tool_type == "firestore-query-collection":
            docs = await source.query_collection(
                params["collection"], params["queries"], params.get("limit", 100),
            )
            return {"documents": docs}
        elif self._tool_type == "firestore-get-rules":
            rules = await source.get_rules()
            return {"rules": rules}
        elif self._tool_type == "firestore-validate-rules":
            result = await source.validate_rules(params["rules_text"])
            return {"validation": result}
        else:
            raise ValueError(f"unknown Firestore tool type: {self._tool_type}")

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
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
    @register_tool(tool_type)
    @dataclass
    class _FSToolConfig(ToolConfig):
        _name: str = field(init=True, repr=False)
        source: str = ""
        description: str = ""

        @property
        def tool_type(self) -> str:
            return tool_type

        @classmethod
        def from_dict(cls, name: str, data: dict[str, Any]) -> _FSToolConfig:
            return cls(_name=name, source=data.get("source", ""), description=data.get("description", description))

        async def initialize(self) -> FirestoreGenericTool:
            cfg = ConfigBase(name=self._name, description=self.description)
            return FirestoreGenericTool(cfg=cfg, source_name=self.source, tool_type=tool_type, param_defs=param_defs, read_only=read_only)

    _FSToolConfig.__name__ = f"{tool_type.replace('-', '_').title().replace('_', '')}ToolConfig"
    _FSToolConfig.__qualname__ = _FSToolConfig.__name__
    return _FSToolConfig


for _tool_type, _desc, _params, _ro in _FS_TOOLS:
    _make_fs_tool_config(_tool_type, _desc, _params, _ro)
