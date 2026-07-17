"""Source base classes and decorator registry.

Maps to Go: internal/sources/sources.go
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer


class Source(ABC):
    """Database source interface.

    Maps to Go Source interface:
      SourceType() string
      ToConfig() SourceConfig
    """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier (e.g., 'postgres', 'mysql')."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        """Initialize the database connection pool."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the database connection pool."""
        ...


class SourceConfig(ABC):
    """Source configuration interface.

    Maps to Go SourceConfig interface:
      SourceConfigType() string
      Initialize(ctx, tracer) (Source, error)
    """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier."""
        ...

    @abstractmethod
    async def initialize(self, tracer: Tracer | None = None) -> Source:
        """Create and initialize a Source from this config."""
        ...


class SQLSource(Source):
    """Base class for SQL database sources (PostgreSQL, MySQL, SQLite).

    Provides a unified interface for SQL execution via SQLAlchemy.
    """

    # Default max rows to prevent OOM from large result sets.
    # Individual sources can override this.
    max_rows: int = 10000

    # Default query timeout (seconds) to prevent runaway queries from
    # holding connections indefinitely. Individual sources can override.
    query_timeout: float = 30.0

    @abstractmethod
    async def execute_sql(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a SQL statement and return results as list of dicts.

        Implementations MUST enforce ``self.max_rows`` to prevent unbounded
        result sets from causing OOM, and SHOULD wrap the DB call with
        ``asyncio.wait_for(..., timeout=self.query_timeout)`` to enforce
        a per-query execution timeout.
        """
        ...

    @abstractmethod
    async def list_tables(self) -> list[str]:
        """List all tables in the database."""
        ...

    @abstractmethod
    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        """Describe the structure of a table."""
        ...


class NoSQLSource(Source):
    """Base class for NoSQL database sources (Redis, MongoDB)."""
    pass


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_source_registry: dict[str, type[SourceConfig]] = {}
_source_aliases: dict[str, str] = {}  # alias -> canonical name


def register_source(source_type: str):
    """Decorator: register a SourceConfig class for a given source type.

    Usage:
        @register_source("postgres")
        class PostgreSQLSourceConfig(SourceConfig):
            ...
    """
    def decorator(cls: type[SourceConfig]) -> type[SourceConfig]:
        """将 SourceConfig 子类注册到全局注册表。"""
        if source_type in _source_registry:
            raise ValueError(f"source type {source_type!r} already registered")
        _source_registry[source_type] = cls
        return cls
    return decorator


def _check_alias_conflict(alias: str, canonical: str) -> str | None:
    """检查别名注册冲突,返回错误消息;无冲突返回 None。"""
    checks: list[tuple[bool, str]] = [
        (alias in _source_registry, f"cannot register source alias {alias!r}: already registered as a primary"),
        (alias in _source_aliases, f"alias {alias!r} already registered"),
        (canonical not in _source_registry, f"cannot register alias {alias!r} -> {canonical!r}: canonical {canonical!r} not registered"),
    ]
    for condition, message in checks:
        if condition:
            return message
    return None


def register_source_alias(alias: str, canonical: str):
    """Register an alias for an existing source type.

    Allows backward compatibility when renaming a source type.
    """
    error = _check_alias_conflict(alias, canonical)
    if error:
        raise ValueError(error)
    _source_aliases[alias] = canonical


def get_source_config_class(source_type: str) -> type[SourceConfig]:
    """Look up a registered SourceConfig class by type, resolving aliases."""
    cls = _source_registry.get(source_type) or _source_registry.get(_source_aliases.get(source_type, ""))
    if cls is None:
        raise ValueError(f"unknown source type: {source_type!r}")
    return cls


def list_source_types() -> list[str]:
    """Return all registered source type names, including aliases."""
    return sorted(set(_source_registry.keys()) | set(_source_aliases.keys()))


def decode_source_config(source_type: str, name: str, config_data: dict[str, Any]) -> SourceConfig:
    """Decode a source config from raw dict data using the registered class."""
    cls = get_source_config_class(source_type)
    # pydantic models will be validated in the concrete class
    return cls.from_dict(name, config_data)  # type: ignore[attr-defined]
