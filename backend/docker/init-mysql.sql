-- MCP Toolbox 配置持久化存储 — MySQL 表结构
--
-- 与 MCP 协议表（Config DB）完全对齐，权威定义见 backend/src/data_tool_mcp/config/store.py
-- （SQLAlchemy Base.metadata）。表结构由代码自动创建（Base.metadata.create_all），
-- 此脚本用于手动初始化或参考，并补全了完整的 MySQL 表/列 COMMENT 元数据，
-- 便于在 information_schema 中检索、做数据治理与文档化。
--
-- ⚠️ 重要：列名避开 MySQL/PG 保留字（name/type/database/host/password 等都是保留字），
-- 加 `src_` / `db_` / `tool_` / `set_` 前缀。Python 代码中通过 SQLAlchemy 的
-- Column("db_col_name", ...) 映射保持 Python 属性名简洁。
--
-- 使用方法：
--   mysql -u root -p < docker/init-mysql.sql
--
-- 当 store_url 指向 MySQL 时，与 Config DB 使用同一套表，
-- Admin UI（独立部署）与 Config DB 通过 HTTP API 操作同一份数据。
--
-- 注意：MySQL 不允许 TEXT / JSON / BLOB / GEOMETRY 列带 DEFAULT 值（< 8.0.13 直接报
-- ERROR 1101），因此 params / description / tool_names 等 TEXT 列均为可空、无默认值，
-- 与 store.py 的 Column(Text, default="...")（Python 侧默认值，不生成 server DEFAULT）保持一致。

CREATE DATABASE IF NOT EXISTS data_tool_mcp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE data_tool_mcp;

-- 数据源表（用户添加的数据库连接配置）
-- 列名加 src_/db_ 前缀避开保留字（name/type/database/host/password/username）
CREATE TABLE IF NOT EXISTS sources (
    id          INT          NOT NULL AUTO_INCREMENT COMMENT '主键，自增',
    system_id   VARCHAR(10)  NOT NULL DEFAULT '' COMMENT '系统编号（业务隔离维度，用户指定，最多 10 位）',
    environment VARCHAR(16)  NOT NULL DEFAULT '' COMMENT '环境标识（dev/st/uat/prd）',
    src_name    VARCHAR(128) NOT NULL COMMENT '数据源名称（同一系统编号下唯一）',
    src_type    VARCHAR(64)  NOT NULL COMMENT '数据源类型（mysql / postgres / sqlite / clickhouse 等）',
    db_host     VARCHAR(255) NOT NULL DEFAULT '' COMMENT '数据库主机地址',
    db_port     INT          NOT NULL DEFAULT 0  COMMENT '数据库端口',
    db_name     VARCHAR(128) NOT NULL DEFAULT '' COMMENT '数据库名（sqlite 类型此处存文件路径 path）',
    db_user     VARCHAR(128) NOT NULL DEFAULT '' COMMENT '连接用户名',
    db_password VARCHAR(512) NOT NULL DEFAULT '' COMMENT '连接密码（应用层加密存储，密钥由 DATA_TOOL_MCP_ENCRYPTION_KEY 提供）',
    params      TEXT                 COMMENT '扩展参数字段（JSON 字符串，存非结构化连接参数）',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（行变更时自动维护）',
    PRIMARY KEY (id),
    UNIQUE KEY uk_system_env_source (system_id, environment, src_name),
    INDEX idx_sources_name (src_name),
    INDEX idx_sources_system (system_id),
    INDEX idx_sources_env (environment)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='数据源表 — 用户添加的数据库连接配置，结构化字段（host/port/database/username/password）+ params（JSON）扩展';

-- 工具表（MCP 工具定义）
-- 列名加 tool_/src_ 前缀避开保留字（name/type/description/source）
-- toolset_names 字段存储该工具所属的 custom toolset 名称列表(JSON 数组)，
-- 用于动态聚合 custom toolset（替代独立的 toolsets 表）
CREATE TABLE IF NOT EXISTS tools (
    id          INT          NOT NULL AUTO_INCREMENT COMMENT '主键，自增',
    system_id   VARCHAR(10)  NOT NULL DEFAULT '' COMMENT '系统编号（冗余存储，便于按系统编号查询工具）',
    environment VARCHAR(16)  NOT NULL DEFAULT '' COMMENT '环境标识（dev/st/uat/prd）',
    tool_name   VARCHAR(128) NOT NULL COMMENT '工具名称（同一系统编号下唯一）',
    tool_type   VARCHAR(64)  NOT NULL COMMENT '工具类型（mysql-execute-sql / postgres-execute-sql 等）',
    src_name    VARCHAR(128) NOT NULL DEFAULT '' COMMENT '关联数据源名称（引用 sources.src_name）',
    tool_desc   TEXT                 COMMENT '工具描述',
    params      TEXT                 COMMENT '扩展参数字段（JSON 字符串，存额外工具参数）',
    toolset_names TEXT               COMMENT '所属 custom toolset 名称列表（JSON 数组，如 ["data","monitor"]，NULL 表示无 custom 归属）',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（行变更时自动维护）',
    PRIMARY KEY (id),
    UNIQUE KEY uk_system_env_tool (system_id, environment, tool_name),
    INDEX idx_tools_name (tool_name),
    INDEX idx_tools_system (system_id),
    INDEX idx_tools_source (src_name),
    INDEX idx_tools_env (environment)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='工具表 — MCP 工具定义，src_name 引用 sources.src_name；toolset_names 存 custom toolset 归属（动态聚合 4 类 toolset: all/source/system/system-env + custom）';

-- MCP 请求日志表 — 记录每次 tools/list 或 tools/call 调用，用于统计审计
-- method/success 在日志表中作为字段名影响较小且可读性高，保留原样
CREATE TABLE IF NOT EXISTS mcp_request_logs (
    id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键，自增',
    system_id   VARCHAR(10)  NOT NULL DEFAULT '' COMMENT '系统编号（请求上下文）',
    environment VARCHAR(16)  NOT NULL DEFAULT '' COMMENT '环境标识（请求上下文）',
    source_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '数据源名称（工具所属数据源）',
    tool_name   VARCHAR(128) NOT NULL DEFAULT '' COMMENT '工具名称（tools/call 才有值）',
    method      VARCHAR(32)  NOT NULL COMMENT 'MCP 方法名（tools/list, tools/call 等）',
    success     TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否成功（1成功 0失败）',
    latency_ms  INT          NOT NULL DEFAULT 0 COMMENT '请求耗时毫秒',
    client_addr VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '客户端 IP 地址',
    error_msg   TEXT                  COMMENT '错误信息（失败时记录）',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '请求时间',
    PRIMARY KEY (id),
    INDEX idx_logs_created (created_at),
    INDEX idx_logs_system (system_id),
    INDEX idx_logs_source (source_name),
    INDEX idx_logs_env (environment)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='MCP 请求日志表 — 记录每次 MCP 协议调用，支持按系统/数据源/日期范围统计';
