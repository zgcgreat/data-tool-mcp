"""Pydantic configuration models.

Maps to Go: internal/server/config.go ServerConfig
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceEntry(BaseModel):
    """A single source definition in YAML config."""

    kind: Literal["source"] = "source"
    name: str
    type: str  # e.g., "postgres", "mysql", "redis"
    # Source-specific fields are stored as extra
    model_config = {"extra": "allow"}


class ToolEntry(BaseModel):
    """A single tool definition in YAML config."""

    kind: Literal["tool"] = "tool"
    name: str
    type: str  # e.g., "postgres-execute-sql", "redis"
    source: str = ""  # source name this tool uses
    description: str = ""
    # Tool-specific fields are stored as extra
    model_config = {"extra": "allow"}


class ToolsetToolRef(BaseModel):
    """Reference to a tool within a toolset."""

    name: str
    description: str = ""


class ToolsetEntry(BaseModel):
    """A single toolset definition in YAML config."""

    kind: Literal["toolset"] = "toolset"
    name: str
    tools: list[ToolsetToolRef] = Field(default_factory=list)


class PromptEntry(BaseModel):
    """A single prompt definition in YAML config.

    Maps to Go: prompt config in YAML with kind: prompt
    """

    kind: Literal["prompt"] = "prompt"
    name: str
    type: str = "custom"  # prompt type, defaults to "custom"
    description: str = ""
    messages: list[dict[str, str]] = Field(default_factory=list)
    arguments: list[dict[str, Any]] = Field(default_factory=list)
    # Prompt-specific fields are stored as extra
    model_config = {"extra": "allow"}


class PromptsetPromptRef(BaseModel):
    """Reference to a prompt within a promptset."""

    name: str


class PromptsetEntry(BaseModel):
    """A single promptset definition in YAML config.

    Maps to Go: promptset config in YAML with kind: promptset
    """

    kind: Literal["promptset"] = "promptset"
    name: str
    prompts: list[PromptsetPromptRef] = Field(default_factory=list)


class EmbeddingModelEntry(BaseModel):
    """A single embedding model definition in YAML config.

    Maps to Go: embeddingModel config in YAML with kind: embeddingModel
    """

    kind: Literal["embeddingModel"] = "embeddingModel"
    name: str
    type: str  # e.g., "gemini"
    model_config = {"extra": "allow"}


class ToolboxFile(BaseModel):
    """Root model for a single YAML config file.

    Maps to Go: the merged config structure from cmd/internal/config.go
    """

    sources: dict[str, Any] = Field(default_factory=dict)
    tools: dict[str, Any] = Field(default_factory=dict)
    toolsets: dict[str, Any] = Field(default_factory=dict)
    prompts: dict[str, Any] = Field(default_factory=dict)
    promptsets: dict[str, Any] = Field(default_factory=dict)
    embeddingModels: dict[str, Any] = Field(default_factory=dict)


class ServerConfig(BaseModel):
    """Server configuration.

    Maps to Go: internal/server/config.go ServerConfig
    """

    # Network
    address: str = "0.0.0.0"
    port: int = 5000
    cert_file: str = ""
    key_file: str = ""

    # Features
    stdio: bool = False
    disable_reload: bool = False
    enable_api: bool = False
    enable_draft_specs: bool = False
    # 多实例部署模式下禁用 SSE(返回 410 Gone),引导客户端使用 Streamable HTTP
    # SSE session 存储在实例内存,多实例下 /message 必定 404;Streamable HTTP 无状态可负载均衡
    disable_sse: bool = False

    # CORS
    allowed_origins: list[str] = Field(default_factory=list)
    allowed_hosts: list[str] = Field(default_factory=list)

    # Config sources
    config_file: str = ""
    config_files: list[str] = Field(default_factory=list)
    config_folder: str = ""
    prebuilt: str = ""

    # DB ConfigReader
    config_db_url: str = ""  # DATA_TOOL_MCP_CONFIG_DB_URL — e.g. mysql://user:pass@host:3306/configdb
    env_passwords: str = ""  # ENV_PASSWORDS — JSON mapping ${VAR} → real value

    # 配置持久化存储（Admin UI CRUD 持久化）
    # 不传 store_url = 默认当前目录 SQLite 文件 toolbox_data.db；sqlite:///path.db = 指定 SQLite 文件
    # MySQL 推荐三段式（凭据不写在 URL 里）：
    #   store_url = mysql://host:port/db（不含账号密码）
    #   store_username / store_password 单独传
    # 也兼容旧式：直接把账号密码写进 store_url = mysql://user:pass@host/db
    store_url: str = ""  # DATA_TOOL_MCP_STORE_URL
    store_username: str = ""  # DATA_TOOL_MCP_STORE_USERNAME — MySQL 用户名（与 store_url 分离）
    store_password: str = ""  # DATA_TOOL_MCP_STORE_PASSWORD — MySQL 密码（与 store_url 分离）

    # 数据库连接池大小（多实例部署时按 实例数×pool_size×数据源数 估算 MySQL max_connections）
    db_pool_size: int = 5

    # DB 配置热重载轮询间隔（秒），方案 C: 可配以平衡一致性和 DB 负载
    reload_interval: float = 5.0

    # Source LRU 缓存最大条目数（方案 C: 惰性加载 + 引用计数 + LRU 淘汰）
    # 默认 128 覆盖活跃数据源;内存受限环境(如 2GB)建议调小到 32-48
    # 估算: maxsize × maxOpenConns × 单连接内存(~3MB) = 缓存峰值占用
    source_cache_maxsize: int = 128

    # Logging
    log_level: str = "INFO"
    logging_format: Literal["standard", "json"] = "standard"

    # Telemetry
    telemetry_gcp: bool = False
    telemetry_otlp: str = ""
    telemetry_gcp_project: str = ""
    telemetry_service_name: str = "mcp-toolbox"

    # SQL
    sql_commenter: bool = False

    # HTTP
    http_max_request_bytes: int = 0
    max_body_size: int = 10 * 1024 * 1024  # 10MB default, maps to Go: maxBodySize
    poll_interval: int = 0

    # SQL safety
    max_query_rows: int = 10000  # Max rows returned by execute_sql to prevent OOM
    query_timeout_seconds: float = 30.0  # Max execution time for a single query

    # User agent
    user_agent_metadata: list[str] = Field(default_factory=list)

    # Runtime (populated from parsed config)
    source_configs: dict[str, Any] = Field(default_factory=dict)
    tool_configs: dict[str, Any] = Field(default_factory=dict)
    toolset_configs: dict[str, Any] = Field(default_factory=dict)
    prompt_configs: dict[str, Any] = Field(default_factory=dict)
    promptset_configs: dict[str, Any] = Field(default_factory=dict)
    embedding_model_configs: dict[str, Any] = Field(default_factory=dict)

    # Toolbox URL (for MCP PRM — now unused since auth removed, but kept for compatibility)
    toolbox_url: str = ""

    # Ignore unknown tools flag
    ignore_unknown_tools: bool = False

    # 启用的数据源类型白名单(空 = 全部启用;非空 = 仅列出的类型可用)
    # 通过 --enabled-source-types 参数或 DATA_TOOL_MCP_ENABLED_SOURCE_TYPES 环境变量设置
    # 影响: /mcp-api/source-types 接口仅返回白名单内类型,创建数据源时拒绝被禁用类型
    enabled_source_types: list[str] = Field(default_factory=list)
