# data-tool-mcp

<p align="center">
  <b>开源的 MCP（Model Context Protocol）数据库工具箱 —— Python 实现。</b><br/>
  通过一个 MCP 服务，让你的 AI 智能体安全、统一地读写 <b>45+ 种数据库</b>，
  并附带可选的 Web 管理后台，用于管理数据源、工具与实时 SQL。
</p>

<p align="center">
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-接入-mcp-客户端">接入客户端</a> ·
  <a href="#️-配置">配置</a> ·
  <a href="#-安全">安全</a> ·
  <a href="./README_EN.md">📖 English</a>
</p>

---

> 📌 **本项目基于 [Google 开源的 MCP Toolbox](https://github.com/googleapis/mcp-toolbox) 二次开发（上游同样采用 Apache-2.0 许可）。**
> 我们沿用了其声明式配置模型（`source` / `tool` / `toolset`）与核心设计理念，并用 Python 完整重新实现，
> 额外扩展了：Web 管理后台、配置热重载、凭据落库加密，以及更稳妥的安全默认值。
> 感谢上游项目提供的理念与基础，本项目遵循相同的 Apache-2.0 许可证。

## 这是什么？

**data-tool-mcp** 是一个用 Python 编写的、开源的 **MCP 数据库工具箱**，是
[Google 开源的 MCP Toolbox](https://github.com/googleapis/mcp-toolbox) 的 Python 实现与二次开发。
它通过 Model Context Protocol 把你的各类数据库暴露给基于大模型的工具与智能体，
让 AI 助手可以运行参数化查询、管理工具、查看表结构——而无需为每个模型手写数据库连接器。
在沿用上游声明式配置模型（`source` / `tool` / `toolset`）与核心设计的基础上，我们重点扩展了：

- 一个 **Web 管理后台**（React），可在浏览器里管理数据源、工具、执行实时 SQL；
- **配置热重载**（改 YAML 无需重启）；
- **凭据落库加密**；
- **更稳妥的安全默认值**（查询行数限制、超时、安全的 CORS）。

> 用它让 Claude、GPT 或任意兼容 MCP 的客户端，在一个受控、可观测的网关后，访问
> PostgreSQL、MySQL、SQLite、MongoDB、Redis、ClickHouse、Snowflake、BigQuery 等 45+ 种数据库。

---

## ✨ 功能特性

- **一个 MCP 服务，45+ 数据源**：PostgreSQL、MySQL、SQLite、MSSQL、Oracle、ClickHouse、Snowflake、
  MongoDB、Redis、Neo4j、Elasticsearch、Cassandra、Trino、OceanBase、BigQuery、Spanner、Firestore 等。
- **三种传输方式**：SSE、Streamable HTTP、STDIO，按客户端能力任选。
- **Web 管理后台**：独立 React SPA，支持数据源增删改查、工具浏览/调用、SQL 控制台、连接健康检查。
  与后端严格解耦（由 nginx 托管，通过 HTTP 调用 API）。
- **配置热重载**：修改 `sources` / `tools` / `toolsets` 即时生效，无需重启。
- **预置配置**：38 个开箱即用的 YAML（`--prebuilt sqlite`、`--prebuilt postgres` …）。
- **环境变量替换**：支持 `${VAR}` 与 `${VAR:-default}`；自动加载工作目录下的 `.env`。
- **工具与模板**：支持 `{{.Param}}` 参数化 SQL 工具，以及 resource / prompt 管理。
- **可观测性**：可选 OpenTelemetry 链路追踪与指标（`--telemetry-otlp`、`--telemetry-gcp`）。
- **安全默认值**：
  - 查询受 `max_rows`（默认 1 万行）与 `query_timeout`（默认 30 秒）约束，避免内存溢出；
  - 数据源 **密码落库前加密**（Fernet）；
  - CORS 通配符默认自动关闭凭据；
  - 请求体默认限制 10 MB（含分块流）。

---

## 🏗️ 架构

```
                ┌──────────────────────────────────────────────┐
                │               AI 客户端 / 智能体              │
                │   （Claude、GPT、IDE 插件、自定义脚本）        │
                └───────────┬───────────────────────┬──────────┘
                  MCP/SSE   │                MCP/HTTP│  （或 STDIO）
                            ▼                        ▼
                ┌──────────────────────────────────────────────┐
                │            data-tool-mcp（后端）              │
                │   FastAPI + MCP 服务（端口 5000）             │
                │   ┌─────────┐ ┌────────┐ ┌─────────────────┐  │
                │   │  MCP    │ │/mcp-api│ │ 配置热重载        │  │
                │   │ 路由    │ │  API   │ │ + 预置配置        │  │
                │   └────┬────┘ └───┬────┘ └────────┬────────┘  │
                │        ▼          ▼               ▼           │
                │   ┌──────────────────────────────────────┐   │
                │   │  sources（45+）· tools · resources    │   │
                │   │  prompts · telemetry · store（SQLite/  │   │
                │   │  MySQL，凭据加密存储）                 │   │
                │   └──────────────────────────────────────┘   │
                └───────────────┬──────────────────────────────┘
                                │  HTTP API（CORS / Host 校验 / API Key）
                                ▼
                ┌──────────────────────────────────────────────┐
                │   管理后台（React SPA，nginx，端口 80/8080）   │
                │   /data-tool-mcp-ui/  →  反代 /mcp-api 与 MCP  │
                └──────────────────────────────────────────────┘
```

后端是**纯 API/MCP 服务**，不托管前端；前后端独立部署，通过 HTTP 通信（直连走 CORS，生产走 nginx 反代）。

---

## 🚀 快速开始

### 方式一：Docker Compose（推荐）

一条命令同时拉起 MCP 服务与管理后台：

```bash
# 在仓库根目录
docker compose up --build
```

- MCP 端点：`http://localhost:5000/sse`（SSE）或 `http://localhost:5000/`（Streamable HTTP）
- 管理后台：打开 **http://localhost:8080/data-tool-mcp-ui/**

需要鉴权？启动前设置密钥：

```bash
export DATA_TOOL_MCP_API_KEY="$(openssl rand -hex 24)"
docker compose up --build
```

> 见 [`docker-compose.yml`](./docker-compose.yml)。后端镜像基于 `backend/Dockerfile`（非 root 用户、含健康检查）；
> 前端镜像基于 `frontend/Dockerfile`（nginx + 按 `BACKEND_URL` 反代）。

### 方式二：本地开发

```bash
# ---- 后端（终端 1）----
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[all]"                              # 或按需：.[postgres]
toolbox serve --prebuilt sqlite --port 5000

# ---- 前端（终端 2）----
cd frontend
npm install
npm run dev        # http://localhost:5173/data-tool-mcp-ui/
```

Vite 会把 `/mcp-api` 与 MCP 端点代理到后端 `:5000`，开发版后台开箱即用。

### 仅安装后端驱动（最小依赖）

```bash
pip install -e .                 # 仅 SQLite + 核心
pip install -e ".[postgres]"     # + asyncpg
pip install -e ".[mysql]"        # + aiomysql (已在 core, 保留 extras 以兼容旧调用)
pip install -e ".[mongodb]"      # + pymongo
pip install -e ".[clickhouse]"   # + clickhouse-connect
pip install -e ".[oracle]"       # + oracledb
pip install -e ".[mssql]"        # + aioodbc
pip install -e ".[neo4j]"        # + neo4j
pip install -e ".[elasticsearch]" # + elasticsearch
pip install -e ".[redis]"        # + redis[hiredis]
pip install -e ".[cassandra]"    # + cassandra-driver (cassandra + scylladb)
pip install -e ".[valkey]"       # + valkey
pip install -e ".[couchbase]"    # + couchbase
pip install -e ".[hbase]"        # + happybase
pip install -e ".[dgraph]"       # + pydgraph
pip install -e ".[snowflake]"    # + snowflake-sqlalchemy
pip install -e ".[trino]"       # + trino
pip install -e ".[firebird]"     # + fdb
pip install -e ".[http]"         # + httpx
pip install -e ".[gcp]"          # 全部 GCP / Cloud 数据源
pip install -e ".[gemini]"       # + google-genai (embedding 模型)
pip install -e ".[sql-all]"      # 全部 SQL 驱动
pip install -e ".[all]"          # 全部可选依赖
```

---

## 🔌 接入 MCP 客户端

**Streamable HTTP**（Web 客户端推荐）：

```jsonc
// MCP 客户端配置
{
  "mcpServers": {
    "data-tool-mcp": {
      "url": "http://localhost:5000/"
      // 若启用 API Key，加上请求头：
      // "headers": { "X-API-Key": "YOUR_KEY" }
    }
  }
}
```

**SSE**：

```jsonc
{
  "mcpServers": {
    "data-tool-mcp": {
      "url": "http://localhost:5000/sse"
    }
  }
}
```

**STDIO**（客户端以子进程方式拉起服务，适合本地工具）：

```jsonc
{
  "mcpServers": {
    "data-tool-mcp": {
      "command": "toolbox",
      "args": ["serve", "--prebuilt", "sqlite", "--stdio"]
    }
  }
}
```

---

## ⚙️ 配置

采用声明式 YAML，三类顶层 `kind`：`source`、`tool`、`toolset`。

```yaml
sources:
  my-pg:
    kind: source
    name: my-pg
    type: postgres
    host: localhost
    port: 5432
    database: mydb
    user: admin
    password: ${PG_PASSWORD}      # 来自环境变量 / .env
    maxOpenConns: 10

tools:
  list-orders:
    kind: tool
    name: list-orders
    type: postgres-execute-sql
    source: my-pg
    description: "列出近期订单"
    statement: "SELECT * FROM orders WHERE created_at > NOW() - INTERVAL '1 day'"

toolsets:
  read-only:
    kind: toolset
    name: read-only
    tools:
      - name: list-orders
```

- **环境变量替换**：`${VAR}` 与 `${VAR:-default}`；工作目录下的 `.env` 自动加载。
- **多文件**：`--config a.yaml --config b.yaml`（合并）或 `--config-folder ./configs`。
- **预置**：`--prebuilt sqlite --prebuilt redis` 加载内置配置。

### 管理后台改动的持久化（存储）

管理后台的增删改查会持久化到由 `DATA_TOOL_MCP_STORE_URL` 选择的存储：

| 取值 | 含义 |
|------|------|
| _（空）_ | 工作目录下的 SQLite 文件 `toolbox_data.db`（零配置） |
| `sqlite:///path/to/data.db` | 指定 SQLite 文件 |
| `mysql://host:3306/db` | MySQL（团队/生产部署） |

MySQL 推荐**三段式**，把账号密码从 URL 中拆出：

```ini
# backend/.env
DATA_TOOL_MCP_STORE_URL=mysql://127.0.0.1:3306/data_tool_mcp   # 仅连接地址
DATA_TOOL_MCP_STORE_USERNAME=root
DATA_TOOL_MCP_STORE_PASSWORD=yourpassword
```

MySQL 库需先建好：

```bash
mysql -u root -p < backend/docker/init-mysql.sql
```

---

## 🖥️ 管理后台

独立 React SPA（无服务端渲染）。页面：

| 页面 | 说明 |
|------|------|
| 总览 | 服务状态、数据源/工具统计 |
| 数据源 | 增删改查、**连接测试** |
| 工具 | 列表 / 详情 / **在线调用** |
| 配置 | 查看当前配置、热加载 |
| 查询控制台 | 对任意数据源执行 SQL |
| 健康 | 数据源健康检查 |

本地开发：`http://localhost:5173/data-tool-mcp-ui/`；
生产由 nginx 在 `/data-tool-mcp-ui/` 托管，并把 `/mcp-api` 与 MCP 端点反代到后端。

---

## 🗄️ 支持的数据源

**45+ 种**，覆盖 SQL / NoSQL / 主流云数据平台：

- **SQL（15+）**：PostgreSQL、MySQL、SQLite、MSSQL、Oracle、ClickHouse、Snowflake、CockroachDB、TiDB、
  Trino、OceanBase、Firebird、SingleStore、MindsDB、YugabyteDB
- **NoSQL（10+）**：Redis、Valkey、MongoDB、Cassandra、ScyllaDB、Elasticsearch、Neo4j、Couchbase、Dgraph
- **云数据服务**：BigQuery、Spanner、Firestore、Bigtable、AlloyDB、Cloud SQL（PG/MySQL/MSSQL）、
  Cloud Storage、Cloud Healthcare、Looker、Dataplex、Dataproc、Data Lineage、Serverless Spark、
  Cloud Monitoring/Logging、Cloud Gemini Data Analytics
- **HTTP** 数据源，可调用通用 REST 接口

> 每个可选驱动均在 `initialize()`/`connect()` 内**延迟导入**，装基础包不会被迫拉取全部驱动。

---

## 🧰 CLI 参考

```
toolbox serve [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--config, -c` | 配置文件路径 | — |
| `--configs` | 多个配置文件（合并） | — |
| `--config-folder` | 配置文件目录 | — |
| `--prebuilt` | 预置配置名称（可重复） | — |
| `--address, -a` | 监听地址 | `0.0.0.0` |
| `--port, -p` | 监听端口 | `5000` |
| `--stdio` | STDIO 模式（子进程客户端用） | `false` |
| `--log-level` | 日志级别 | `INFO` |
| `--disable-reload` | 禁用配置热重载 | `false` |
| `--api-key` | 开启全局 API Key 鉴权（X-API-Key / Bearer） | _（关闭）_ |
| `--allowed-origins` | CORS 允许列表（`*` = 通配符，自动关凭据） | `*` |
| `--allowed-hosts` | Host 头允许列表（防 DNS 重绑定） | _（关闭）_ |
| `--store-url` | 管理后台存储 URL（SQLite/MySQL） | 零配置 SQLite |
| `--store-username` | 存储库用户名（MySQL） | — |
| `--store-password` | 存储库密码（MySQL） | — |
| `--tls-cert` / `--tls-key` | 启用 HTTPS | — |
| `--version, -v` | 打印版本并退出 | — |

额外参数：`--config-db-url`、`--env-passwords`、`--logging-format`、`--enable-api`、
`--enable-draft-specs`、`--ignore-unknown-tools`、`--telemetry-otlp`、`--telemetry-gcp`、
`--telemetry-gcp-project`、`--telemetry-service-name`、`--sql-commenter`、`--user-agent-metadata`。

示例：

```bash
toolbox serve -c config.yaml --port 8080
toolbox serve --prebuilt postgres --port 15000
toolbox serve --prebuilt sqlite --prebuilt redis
toolbox serve --prebuilt sqlite --stdio
toolbox serve --prebuilt sqlite --api-key "$DATA_TOOL_MCP_API_KEY" --allowed-hosts my.host
toolbox serve --prebuilt sqlite --tls-cert cert.pem --tls-key key.pem
```

---

## 🔒 安全

data-tool-mcp 是一个**高权限数据库网关**，暴露前请务必阅读本节。

**默认姿态（企业内网可信模型）：** 默认**不开启鉴权**，且监听 `0.0.0.0`。这仅在可信网络/反向代理之后才安全，
**切勿**在未加固的情况下直接暴露到公网。

**对外暴露前的加固步骤：**

1. **开启 API Key 鉴权**——传入 `--api-key`（或 `DATA_TOOL_MCP_API_KEY`），除健康检查外所有请求都需
   `X-API-Key` 或 `Authorization: Bearer <key>`（恒定时间比较）。Admin API 与 MCP 端点共用此门禁。
2. **限制 Host 头**——传入 `--allowed-hosts your.host` 防 DNS 重绑定。
3. **前置 TLS + 反向代理**——终止 HTTPS，MCP 服务留在私网。
4. **最小权限数据库账号**——仅授予智能体所需权限。
5. **谨慎使用 SQL 控制台/模板**——参数化模板工具按字符串插值拼接调用方传入的值（与上游设计一致），
   把后台自建工具视为可信代码。

**默认已安全的部分：**

- 数据源**密码落库前加密**（Fernet，仅在 `cryptography` 不可用时降级明文，而该库是核心依赖）；
- 查询受行数（1 万）与超时（30 秒）约束，无无界结果集 / OOM；
- CORS 通配符自动关闭凭据，无意外跨域带凭证；
- 请求体限制 10 MB（含分块流）。

> 发现漏洞？请见 [SECURITY.md](./SECURITY.md)（或邮件联系维护者），**不要**公开提 issue。

---

## 📁 项目结构

采用严格前后端分离的 monorepo：

```
data-tool-mcp/
├── README.md                  # 本文（中文）
├── README_EN.md               # 英文版
├── docker-compose.yml         # 一键启动后端 + 后台
├── backend/                   # Python MCP 工具箱（纯 API/MCP 服务）
│   ├── main.py                # 快捷启动脚本
│   ├── pyproject.toml
│   ├── Dockerfile             # 后端镜像（非 root、含健康检查）
│   ├── docker/                # 配置示例 + init-mysql.sql
│   ├── src/data_tool_mcp/
│   │   ├── cli/main.py        # CLI 入口
│   │   ├── config/            # 加载器 + 模型 + store（凭据加密）
│   │   ├── server/            # FastAPI 应用、路由、mcp/、middleware/
│   │   ├── admin/             # 管理后台 REST API
│   │   ├── sources/           # 45+ 数据源实现
│   │   ├── tools/             # 工具 + 模板实现
│   │   ├── resources/ prompts/ embeddingmodels/ telemetry/
│   │   └── prebuiltconfigs/   # 38 个预置 YAML
│   └── tests/
└── frontend/                  # React 管理后台（独立 nginx 部署）
    ├── src/  vite.config.ts  Dockerfile  nginx.conf.template  docker-entrypoint.sh
    └── dist/                  # 构建产物（npm run build）
```

---

## 🛠️ 开发

```bash
# 后端
cd backend && pip install -e ".[dev,all]"
pytest                 # 测试
mypy src/              # 类型检查（严格）
ruff format src/ && ruff check src/

# 前端
cd frontend && npm install
npm run dev            # 开发服务器（反代 /mcp-api + MCP 到 :5000）
npm run build          # -> frontend/dist/（nginx 托管）
```

---

## 🤝 贡献

欢迎贡献！重大改动请先开 issue 讨论。参见 [CONTRIBUTING.md](./CONTRIBUTING.md) 了解环境搭建、分支与 PR 规范，
以及 [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) 社区守则。

---

## 🗺️ 路线图

- [ ] 工具级 / 工具集级鉴权策略（突破仅全局 API Key）
- [ ] 大查询结果流式 / 分页返回
- [ ] 面向不可信客户端的只读 / 语句白名单模式
- [ ] 更多数据源与云厂商
- [ ] Kubernetes / Helm  chart 与托管快速开始

---

## 📄 许可证

[Apache License 2.0](./LICENSE)。© data-tool-mcp 贡献者。

## 🙏 致谢

本项目的设计借鉴并基于 Google 开源的 [MCP Toolbox](https://github.com/googleapis/mcp-toolbox)（Apache-2.0）。
感谢上游社区的工作与启发。本项目基于 FastAPI、SQLAlchemy、React 构建。
