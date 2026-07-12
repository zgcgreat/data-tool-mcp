"""MongoDB tools — find, find-one, aggregate, insert, delete, update.

Maps to Go: internal/tools/mongodb/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.mongodb import MongoDBSource
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


def _get_mongo_source(
    source_provider: SourceProvider | None,
    source_name: str,
    tool_name: str,
) -> MongoDBSource:
    """Resolve a MongoDBSource from the SourceProvider."""
    if source_provider is None:
        raise ValueError(f"tool {tool_name!r} requires a source provider")
    source = source_provider.get_source(source_name)
    if source is None:
        raise ValueError(f"source {source_name!r} not found for tool {tool_name!r}")
    if not isinstance(source, MongoDBSource):
        raise TypeError(f"source {source_name!r} is not a MongoDB source")
    return source


# ---------------------------------------------------------------------------
# mongodb-find
# ---------------------------------------------------------------------------

class MongodbFindTool(BaseTool):
    """Find documents in a MongoDB collection."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = _get_mongo_source(source_provider, self._source_name, self.name)
        collection = params.get("collection", "")
        query = params.get("query")
        limit = params.get("limit", 100)
        results = await source.find(collection, query, limit=limit)
        return {"documents": results, "count": len(results)}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="collection", type="string", description="Collection name", required=True),
                ParameterManifest(name="query", type="object", description="MongoDB query filter", required=False),
                ParameterManifest(name="limit", type="integer", description="Max documents to return", required=False),
            ],
            auth_required=self.auth_required,
        )


@register_tool("mongodb-find")
@dataclass
class MongodbFindToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 MongoDB 集合中查找文档"

    @property
    def tool_type(self) -> str:
        return "mongodb-find"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MongodbFindToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "查找文档"))

    async def initialize(self) -> MongodbFindTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MongodbFindTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# mongodb-find-one
# ---------------------------------------------------------------------------

class MongodbFindOneTool(BaseTool):
    """Find a single document in a MongoDB collection."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = _get_mongo_source(source_provider, self._source_name, self.name)
        collection = params.get("collection", "")
        query = params.get("query", {})
        projection = params.get("projection")
        doc = await source.find_one(collection, query, projection=projection)
        return {"document": doc}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="collection", type="string", description="Collection name", required=True),
                ParameterManifest(name="query", type="object", description="MongoDB query filter", required=True),
                ParameterManifest(name="projection", type="object", description="Fields to include/exclude", required=False),
            ],
            auth_required=self.auth_required,
        )


@register_tool("mongodb-find-one")
@dataclass
class MongodbFindOneToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 MongoDB 集合中查询单个文档"

    @property
    def tool_type(self) -> str:
        return "mongodb-find-one"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MongodbFindOneToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "查询单个文档"))

    async def initialize(self) -> MongodbFindOneTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MongodbFindOneTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# mongodb-aggregate
# ---------------------------------------------------------------------------

class MongodbAggregateTool(BaseTool):
    """Run an aggregation pipeline on a MongoDB collection."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=True))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = _get_mongo_source(source_provider, self._source_name, self.name)
        collection = params.get("collection", "")
        pipeline = params.get("pipeline", [])
        results = await source.aggregate(collection, pipeline)
        return {"documents": results, "count": len(results)}

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="collection", type="string", description="Collection name", required=True),
                ParameterManifest(
                    name="pipeline", type="array", description="Aggregation pipeline stages",
                    required=True, items={"type": "object"},
                ),
            ],
            auth_required=self.auth_required,
        )


@register_tool("mongodb-aggregate")
@dataclass
class MongodbAggregateToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "在 MongoDB 集合上运行聚合管道"

    @property
    def tool_type(self) -> str:
        return "mongodb-aggregate"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MongodbAggregateToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "聚合文档"))

    async def initialize(self) -> MongodbAggregateTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MongodbAggregateTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# mongodb-insert-one
# ---------------------------------------------------------------------------

class MongodbInsertOneTool(BaseTool):
    """Insert a single document into a MongoDB collection."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = _get_mongo_source(source_provider, self._source_name, self.name)
        collection = params.get("collection", "")
        document = params.get("document", {})
        result = await source.insert_one(collection, document)
        return result

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="collection", type="string", description="Collection name", required=True),
                ParameterManifest(name="document", type="object", description="Document to insert", required=True),
            ],
            auth_required=self.auth_required,
        )


@register_tool("mongodb-insert-one")
@dataclass
class MongodbInsertOneToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "向 MongoDB 集合中插入单个文档"

    @property
    def tool_type(self) -> str:
        return "mongodb-insert-one"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MongodbInsertOneToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "插入单个文档"))

    async def initialize(self) -> MongodbInsertOneTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MongodbInsertOneTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# mongodb-insert-many
# ---------------------------------------------------------------------------

class MongodbInsertManyTool(BaseTool):
    """Insert multiple documents into a MongoDB collection."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = _get_mongo_source(source_provider, self._source_name, self.name)
        collection = params.get("collection", "")
        documents = params.get("documents", [])
        result = await source.insert_many(collection, documents)
        return result

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="collection", type="string", description="Collection name", required=True),
                ParameterManifest(
                    name="documents", type="array", description="Documents to insert",
                    required=True, items={"type": "object"},
                ),
            ],
            auth_required=self.auth_required,
        )


@register_tool("mongodb-insert-many")
@dataclass
class MongodbInsertManyToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "向 MongoDB 集合中插入多个文档"

    @property
    def tool_type(self) -> str:
        return "mongodb-insert-many"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MongodbInsertManyToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "插入多个文档"))

    async def initialize(self) -> MongodbInsertManyTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MongodbInsertManyTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# mongodb-delete-one
# ---------------------------------------------------------------------------

class MongodbDeleteOneTool(BaseTool):
    """Delete a single document from a MongoDB collection."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = _get_mongo_source(source_provider, self._source_name, self.name)
        collection = params.get("collection", "")
        query = params.get("query", {})
        result = await source.delete_one(collection, query)
        return result

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="collection", type="string", description="Collection name", required=True),
                ParameterManifest(name="query", type="object", description="MongoDB query filter", required=True),
            ],
            auth_required=self.auth_required,
        )


@register_tool("mongodb-delete-one")
@dataclass
class MongodbDeleteOneToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "从 MongoDB 集合中删除单个文档"

    @property
    def tool_type(self) -> str:
        return "mongodb-delete-one"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MongodbDeleteOneToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "删除单个文档"))

    async def initialize(self) -> MongodbDeleteOneTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MongodbDeleteOneTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# mongodb-delete-many
# ---------------------------------------------------------------------------

class MongodbDeleteManyTool(BaseTool):
    """Delete multiple documents from a MongoDB collection."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = _get_mongo_source(source_provider, self._source_name, self.name)
        collection = params.get("collection", "")
        query = params.get("query", {})
        result = await source.delete_many(collection, query)
        return result

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="collection", type="string", description="Collection name", required=True),
                ParameterManifest(name="query", type="object", description="MongoDB query filter", required=True),
            ],
            auth_required=self.auth_required,
        )


@register_tool("mongodb-delete-many")
@dataclass
class MongodbDeleteManyToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "从 MongoDB 集合中删除多个文档"

    @property
    def tool_type(self) -> str:
        return "mongodb-delete-many"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MongodbDeleteManyToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "删除多个文档"))

    async def initialize(self) -> MongodbDeleteManyTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MongodbDeleteManyTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# mongodb-update-one
# ---------------------------------------------------------------------------

class MongodbUpdateOneTool(BaseTool):
    """Update a single document in a MongoDB collection."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = _get_mongo_source(source_provider, self._source_name, self.name)
        collection = params.get("collection", "")
        query = params.get("query", {})
        update = params.get("update", {})
        result = await source.update_one(collection, query, update)
        return result

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="collection", type="string", description="Collection name", required=True),
                ParameterManifest(name="query", type="object", description="MongoDB query filter", required=True),
                ParameterManifest(name="update", type="object", description="Update operations (e.g. {$set: {...}})", required=True),
            ],
            auth_required=self.auth_required,
        )


@register_tool("mongodb-update-one")
@dataclass
class MongodbUpdateOneToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "更新 MongoDB 集合中的单个文档"

    @property
    def tool_type(self) -> str:
        return "mongodb-update-one"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MongodbUpdateOneToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "更新单个文档"))

    async def initialize(self) -> MongodbUpdateOneTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MongodbUpdateOneTool(cfg=cfg, source_name=self.source)


# ---------------------------------------------------------------------------
# mongodb-update-many
# ---------------------------------------------------------------------------

class MongodbUpdateManyTool(BaseTool):
    """Update multiple documents in a MongoDB collection."""

    def __init__(self, cfg: ConfigBase, source_name: str):
        super().__init__(cfg, annotations=ToolAnnotations(read_only_hint=False))
        self._source_name = source_name

    async def invoke(
        self,
        params: dict[str, Any],
        source_provider: SourceProvider | None = None,
        access_token: str = "",
    ) -> Any:
        source = _get_mongo_source(source_provider, self._source_name, self.name)
        collection = params.get("collection", "")
        query = params.get("query", {})
        update = params.get("update", {})
        result = await source.update_many(collection, query, update)
        return result

    def manifest(self, sources: dict[str, Any] | None = None) -> ToolManifest:
        return ToolManifest(
            description=self.description,
            parameters=[
                ParameterManifest(name="collection", type="string", description="Collection name", required=True),
                ParameterManifest(name="query", type="object", description="MongoDB query filter", required=True),
                ParameterManifest(name="update", type="object", description="Update operations (e.g. {$set: {...}})", required=True),
            ],
            auth_required=self.auth_required,
        )


@register_tool("mongodb-update-many")
@dataclass
class MongodbUpdateManyToolConfig(ToolConfig):
    _name: str = field(init=True, repr=False)
    source: str = ""
    description: str = "更新 MongoDB 集合中的多个文档"

    @property
    def tool_type(self) -> str:
        return "mongodb-update-many"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> MongodbUpdateManyToolConfig:
        return cls(_name=name, source=data.get("source", ""), description=data.get("description", "更新多个文档"))

    async def initialize(self) -> MongodbUpdateManyTool:
        cfg = ConfigBase(name=self._name, description=self.description)
        return MongodbUpdateManyTool(cfg=cfg, source_name=self.source)
