-- MCP Toolbox 配置持久化存储 — MySQL 表结构
--
-- 与 MCP 协议表（Config DB）完全对齐，权威定义见 backend/src/data_tool_mcp/config/store.py
-- （SQLAlchemy Base.metadata）。表结构由代码自动创建（Base.metadata.create_all），
-- 此脚本用于手动初始化或参考，并补全了完整的 MySQL 表/列 COMMENT 元数据，
-- 便于在 information_schema 中检索、做数据治理与文档化。
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

-- 部门表（多租户隔离的核心）
CREATE TABLE IF NOT EXISTS departments (
    id           INT          NOT NULL AUTO_INCREMENT COMMENT '主键，自增',
    name         VARCHAR(64)  NOT NULL COMMENT '部门唯一标识（英文短名，如 default），用于代码引用',
    display_name VARCHAR(128) NOT NULL COMMENT '部门显示名称（中文可读）',
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（行变更时自动维护）',
    PRIMARY KEY (id),
    UNIQUE KEY uk_departments_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='部门表 — 多租户隔离的核心，所有数据源/工具/密钥按部门隔离';

-- 数据源表（用户添加的数据库连接配置）
CREATE TABLE IF NOT EXISTS sources (
    id          INT          NOT NULL AUTO_INCREMENT COMMENT '主键，自增',
    dept_id     INT          NULL     COMMENT '所属部门 ID；NULL = 默认部门（单租户模式）',
    name        VARCHAR(128) NOT NULL COMMENT '数据源名称（部门内唯一）',
    type        VARCHAR(64)  NOT NULL COMMENT '数据源类型（mysql / postgres / sqlite / clickhouse 等）',
    host        VARCHAR(255) NOT NULL DEFAULT '' COMMENT '数据库主机地址',
    port        INT          NOT NULL DEFAULT 0  COMMENT '数据库端口',
    `database`  VARCHAR(128) NOT NULL DEFAULT '' COMMENT '数据库名（sqlite 类型此处存文件路径 path）',
    username    VARCHAR(128) NOT NULL DEFAULT '' COMMENT '连接用户名',
    password    VARCHAR(512) NOT NULL DEFAULT '' COMMENT '连接密码（明文存储，生产建议结合密钥管理）',
    params      TEXT                 COMMENT '扩展参数字段（JSON 字符串，存非结构化连接参数）',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（行变更时自动维护）',
    PRIMARY KEY (id),
    UNIQUE KEY uk_dept_source (dept_id, name),
    INDEX idx_sources_name (name),
    INDEX idx_sources_dept (dept_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='数据源表 — 用户添加的数据库连接配置，结构化字段（host/port/database/username/password）+ params（JSON）扩展';

-- 工具表（MCP 工具定义）
CREATE TABLE IF NOT EXISTS tools (
    id          INT          NOT NULL AUTO_INCREMENT COMMENT '主键，自增',
    dept_id     INT          NULL     COMMENT '所属部门 ID；NULL = 默认部门（单租户模式）',
    name        VARCHAR(128) NOT NULL COMMENT '工具名称（部门内唯一）',
    type        VARCHAR(64)  NOT NULL COMMENT '工具类型（mysql-execute-sql / postgres-execute-sql 等）',
    source_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '关联数据源名称（引用 sources.name）',
    description TEXT                 COMMENT '工具描述',
    params      TEXT                 COMMENT '扩展参数字段（JSON 字符串，存额外工具参数）',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（行变更时自动维护）',
    PRIMARY KEY (id),
    UNIQUE KEY uk_dept_tool (dept_id, name),
    INDEX idx_tools_name (name),
    INDEX idx_tools_dept (dept_id),
    INDEX idx_tools_source (source_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='工具表 — MCP 工具定义，source_name 引用 sources.name，params 存额外工具参数';

-- 工具集表（将工具聚合为 toolset）
CREATE TABLE IF NOT EXISTS toolsets (
    id          INT          NOT NULL AUTO_INCREMENT COMMENT '主键，自增',
    dept_id     INT          NULL     COMMENT '所属部门 ID；NULL = 默认部门（单租户模式）',
    name        VARCHAR(128) NOT NULL COMMENT '工具集名称',
    tool_names  TEXT                 COMMENT '工具名称列表（逗号分隔字符串，读取时解析为列表）',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间（行变更时自动维护）',
    PRIMARY KEY (id),
    INDEX idx_toolsets_dept (dept_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='工具集表 — 将多个工具聚合为一个 toolset 对外暴露，tool_names 用逗号分隔字符串存储';

-- API 密钥表（员工访问鉴权）
CREATE TABLE IF NOT EXISTS api_keys (
    id          INT          NOT NULL AUTO_INCREMENT COMMENT '主键，自增',
    dept_id     INT          NULL     COMMENT '所属部门 ID；NULL = 默认部门（单租户模式）',
    key_hash    VARCHAR(128) NOT NULL COMMENT '密钥哈希值（SHA256(原始密钥)），唯一',
    description VARCHAR(255) NOT NULL DEFAULT '' COMMENT '密钥用途描述',
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    expires_at  TIMESTAMP    NULL     COMMENT '过期时间；NULL = 不过期',
    PRIMARY KEY (id),
    UNIQUE KEY uk_api_keys_hash (key_hash),
    INDEX idx_api_keys_dept (dept_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='API 密钥表 — 员工访问鉴权，key_hash = SHA256(原始密钥)';

-- 默认部门（单租户模式）
INSERT INTO departments (name, display_name) VALUES ('default', '默认部门')
ON DUPLICATE KEY UPDATE display_name = display_name;
