# data-tool-mcp

<p align="center">
  <b>An open-source MCP (Model Context Protocol) Toolbox for Databases — in Python.</b><br/>
  Give your AI agents secure, unified, read/write access to <b>45+ databases</b> through one MCP server,
  with an optional web Admin UI for managing data sources, tools, and live SQL.
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> ·
  <a href="#-connect-your-mcp-client">Connect a client</a> ·
  <a href="#️-configuration">Configuration</a> ·
  <a href="#-security">Security</a> ·
  <a href="./README.md">📖 中文文档</a>
</p>

---

> 📌 **data-tool-mcp is a derivative work based on [Google's open-source MCP Toolbox](https://github.com/googleapis/mcp-toolbox) (also Apache-2.0 licensed).**
> We adopted its declarative config model (`source` / `tool` / `toolset`) and core design philosophy, reimplemented
> it entirely in Python, and added: a web Admin UI, config hot-reload, credential encryption at rest, and safer
> security defaults. We thank the upstream project for the ideas and foundation, and release this project under the
> same Apache-2.0 license.

## What is data-tool-mcp?

**data-tool-mcp** is a Python implementation and derivative of the
[MCP Toolbox for Databases](https://github.com/googleapis/mcp-toolbox) — an open-source project by Google.
It exposes your databases to LLM-powered tools and agents over the [Model Context Protocol](https://modelcontextprotocol.io),
so an AI assistant can run parameterized queries, manage tools, and inspect schema — without you hand-writing
database connectors for every model. Building on the upstream's declarative config model (`source` / `tool` / `toolset`)
and core design, we focused our extensions on:

- a **web Admin UI** (React) for managing data sources / tools / live SQL from a browser,
- **configuration hot-reload** (edit YAML, no restart),
- **credential encryption at rest**, and
- **sane safety defaults** (query row limits, timeouts, safe CORS).

> Use it to let Claude, GPT, or any MCP-compatible client talk to Postgres, MySQL, SQLite, MongoDB, Redis,
> ClickHouse, Snowflake, BigQuery, and 35+ more — behind one controlled, observable gateway.

---

## ✨ Features

- **One MCP server, 45+ data sources.** PostgreSQL, MySQL, SQLite, MSSQL, Oracle, ClickHouse, Snowflake,
  MongoDB, Redis, Neo4j, Elasticsearch, Cassandra, Trino, OceanBase, BigQuery, Spanner, Firestore, and more.
- **Three transports.** SSE, Streamable HTTP, and STDIO — pick what your client supports.
- **Web Admin UI.** A separate React SPA to CRUD data sources, browse/invoke tools, run a SQL console, and
  health-check connections. Strictly decoupled from the backend (served by nginx, talks to the API over HTTP).
- **Config hot-reload.** Change `sources` / `tools` / `toolsets` in YAML and they take effect without restarting.
- **Prebuilt configs.** 38 ready-to-use YAML snippets (`--prebuilt sqlite`, `--prebuilt postgres`, …).
- **Env-var substitution.** `${VAR}` and `${VAR:-default}` in any config value; `.env` supported.
- **Toolbox = tools + templates.** Parameterized SQL tools with `{{.Param}}` templates, plus resource & prompt
  management for richer agent workflows.
- **Observability.** Optional OpenTelemetry traces/metrics (`--telemetry-otlp`, `--telemetry-gcp`).
- **Safety-conscious defaults.**
  - Queries are bounded by `max_rows` (default 10 000) and a `query_timeout` (default 30 s) to prevent OOM.
  - Data-source **passwords are encrypted at rest** (Fernet) before they hit the store.
  - CORS is *safe by default*: a wildcard origin automatically disables credentials.
  - Request bodies are size-limited (default 10 MB, enforced on chunked streams too).

---

## 🏗️ Architecture

```
                ┌──────────────────────────────────────────────┐
                │               AI Client / Agent              │
                │   (Claude, GPT, IDE plugin, custom script)    │
                └───────────┬───────────────────────┬──────────┘
                   MCP/SSE  │                MCP/HTTP│  (or STDIO)
                            ▼                        ▼
                ┌──────────────────────────────────────────────┐
                │            data-tool-mcp  (backend)           │
                │   FastAPI + MCP server  (port 5000)           │
                │   ┌─────────┐ ┌────────┐ ┌─────────────────┐  │
                │   │  MCP    │ │/mcp-api│ │ config hot-reload│  │
                │   │ routes  │ │  API   │ │ + prebuilt cfgs  │  │
                │   └────┬────┘ └───┬────┘ └────────┬────────┘  │
                │        ▼          ▼               ▼           │
                │   ┌──────────────────────────────────────┐   │
                │   │  sources (45+) · tools · resources    │   │
                │   │  prompts · telemetry · store (SQLite/  │   │
                │   │  MySQL, encrypted credentials)         │   │
                │   └──────────────────────────────────────┘   │
                └───────────────┬──────────────────────────────┘
                                │  HTTP API  (CORS / Host check / API key)
                                ▼
                ┌──────────────────────────────────────────────┐
                │   Admin UI  (React SPA, nginx, port 80/8080)  │
                │   /data-tool-mcp-ui/  →  proxies /mcp-api & MCP │
                └──────────────────────────────────────────────┘
```

The backend is a **pure API/MCP service** — it does **not** serve or embed the frontend. The two are deployed
independently and communicate over HTTP (CORS for direct calls, nginx reverse proxy in production).

---

## 🚀 Quick Start

### Option A — Docker Compose (recommended)

Spin up the MCP server **and** the Admin UI with one command:

```bash
# from the repo root
docker compose up --build
```

- MCP endpoint: `http://localhost:5000/sse` (SSE) or `http://localhost:5000/` (Streamable HTTP)
- Admin UI: open **http://localhost:8080/data-tool-mcp-ui/**

Want auth? Set a key before starting:

```bash
export DATA_TOOL_MCP_API_KEY="$(openssl rand -hex 24)"
docker compose up --build
```

> See [`docker-compose.yml`](./docker-compose.yml). The backend image builds from `backend/Dockerfile`
> (non-root user, health-checked); the UI image builds from `frontend/Dockerfile` (nginx + `BACKEND_URL` proxy).

### Option B — Local development

```bash
# ---- Backend (terminal 1) ----
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[all]"                              # or pick drivers: .[postgres]
toolbox serve --prebuilt sqlite --port 5000

# ---- Frontend (terminal 2) ----
cd frontend
npm install
npm run dev        # http://localhost:5173/data-tool-mcp-ui/
```

Vite proxies `/mcp-api` and the MCP endpoints to the backend on `:5000`, so the dev UI just works.

### Install backend drivers only (minimal footprint)

```bash
pip install -e .                 # SQLite + core only
pip install -e ".[postgres]"     # + asyncpg
pip install -e ".[mysql]"        # + pymysql
pip install -e ".[mongodb]"      # + motor
pip install -e ".[sql-all]"      # all SQL drivers
pip install -e ".[all]"          # everything
```

---

## 🔌 Connect your MCP client

**Streamable HTTP** (recommended for web clients):

```jsonc
// mcp client config
{
  "mcpServers": {
    "data-tool-mcp": {
      "url": "http://localhost:5000/"
      // add header if API key is set:
      // "headers": { "X-API-Key": "YOUR_KEY" }
    }
  }
}
```

**SSE**:

```jsonc
{
  "mcpServers": {
    "data-tool-mcp": {
      "url": "http://localhost:5000/sse"
    }
  }
}
```

**STDIO** (client launches the server as a subprocess — great for local tools):

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

## ⚙️ Configuration

Configuration is declarative YAML with three top-level kinds: `source`, `tool`, `toolset`.

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
    password: ${PG_PASSWORD}      # from env / .env
    maxOpenConns: 10

tools:
  list-orders:
    kind: tool
    name: list-orders
    type: postgres-execute-sql
    source: my-pg
    description: "List recent orders"
    statement: "SELECT * FROM orders WHERE created_at > NOW() - INTERVAL '1 day'"

toolsets:
  read-only:
    kind: toolset
    name: read-only
    tools:
      - name: list-orders
```

- **Env substitution:** `${VAR}` and `${VAR:-default}`. A `.env` file in the working directory is loaded automatically.
- **Multiple files:** `--config a.yaml --config b.yaml` (merged) or `--config-folder ./configs`.
- **Prebuilt:** `--prebuilt sqlite --prebuilt redis` loads bundled configs.

### Persisting Admin-UI changes (store)

Edits made in the Admin UI are saved to a store selected by `DATA_TOOL_MCP_STORE_URL`:

| Value | Meaning |
|-------|---------|
| _(empty)_ | SQLite file `toolbox_data.db` in the working dir (zero-config) |
| `sqlite:///path/to/data.db` | explicit SQLite file |
| `mysql://host:3306/db` | MySQL (for team/prod deployments) |

For MySQL, prefer the **three-part form** so credentials aren't baked into the URL:

```ini
# backend/.env
DATA_TOOL_MCP_STORE_URL=mysql://127.0.0.1:3306/data_tool_mcp   # address only
DATA_TOOL_MCP_STORE_USERNAME=root
DATA_TOOL_MCP_STORE_PASSWORD=yourpassword
```

The MySQL database/tables must exist first:

```bash
mysql -u root -p < backend/docker/init-mysql.sql
```

---

## 🖥️ Admin UI

A standalone React SPA (no server-side rendering). Pages:

| Page | What it does |
|------|--------------|
| Overview | service status, source/tool counts |
| Data Sources | CRUD data sources, **test connection** |
| Tools | list / inspect / **invoke tools live** |
| Config | view active config, hot-reload |
| Query Console | run SQL against any source |
| Health | per-source health checks |

Local dev: `http://localhost:5173/data-tool-mcp-ui/`.
Production: served by nginx at `/data-tool-mcp-ui/`, proxying `/mcp-api` and MCP endpoints to the backend.

---

## 🗄️ Supported data sources

**45+ types** across SQL, NoSQL, and major cloud data platforms:

- **SQL (15+):** PostgreSQL, MySQL, SQLite, MSSQL, Oracle, ClickHouse, Snowflake, CockroachDB, TiDB,
  Trino, OceanBase, Firebird, SingleStore, MindsDB, YugabyteDB
- **NoSQL (10+):** Redis, Valkey, MongoDB, Cassandra, ScyllaDB, Elasticsearch, Neo4j, Couchbase, Dgraph
- **Cloud data services:** BigQuery, Spanner, Firestore, Bigtable, AlloyDB, Cloud SQL (PG/MySQL/MSSQL),
  Cloud Storage, Cloud Healthcare, Looker, Dataplex, Dataproc, Data Lineage, Serverless Spark,
  Cloud Monitoring/Logging, Cloud Gemini Data Analytics
- **HTTP** source for calling generic REST endpoints

> Each optional driver is **lazily imported** inside `initialize()`/`connect()` — so installing the base
> package never forces you to pull every database driver.

---

## 🧰 CLI reference

```
toolbox serve [options]
```

| Flag | Description | Default |
|------|-------------|---------|
| `--config, -c` | config file path | — |
| `--configs` | multiple config files (merged) | — |
| `--config-folder` | directory of config files | — |
| `--prebuilt` | prebuilt config name (repeatable) | — |
| `--address, -a` | bind address | `0.0.0.0` |
| `--port, -p` | bind port | `5000` |
| `--stdio` | run in STDIO mode (for subprocess clients) | `false` |
| `--log-level` | log level | `INFO` |
| `--disable-reload` | disable config hot-reload | `false` |
| `--api-key` | enable global API-key auth (X-API-Key / Bearer) | _(off)_ |
| `--allowed-origins` | CORS allow-list (`*` = wildcard, credentials off) | `*` |
| `--allowed-hosts` | Host-header allow-list (DNS-rebinding protection) | _(off)_ |
| `--store-url` | admin store URL (SQLite/MySQL) | zero-config SQLite |
| `--store-username` | store DB username (MySQL) | — |
| `--store-password` | store DB password (MySQL) | — |
| `--tls-cert` / `--tls-key` | enable HTTPS | — |
| `--version, -v` | print version and exit | — |

Additional flags: `--config-db-url`, `--env-passwords`, `--logging-format`, `--enable-api`,
`--enable-draft-specs`, `--ignore-unknown-tools`, `--telemetry-otlp`, `--telemetry-gcp`,
`--telemetry-gcp-project`, `--telemetry-service-name`, `--sql-commenter`, `--user-agent-metadata`.

Examples:

```bash
toolbox serve -c config.yaml --port 8080
toolbox serve --prebuilt postgres --port 15000
toolbox serve --prebuilt sqlite --prebuilt redis
toolbox serve --prebuilt sqlite --stdio
toolbox serve --prebuilt sqlite --api-key "$DATA_TOOL_MCP_API_KEY" --allowed-hosts my.host
toolbox serve --prebuilt sqlite --tls-cert cert.pem --tls-key key.pem
```

---

## 🔒 Security

data-tool-mcp is a **high-privilege database gateway**. Read this before exposing it.

**Default posture (intranet trust model):** authentication is **off** by default and the server binds
`0.0.0.0`. This is safe *only* behind a trusted network / reverse proxy. **Do not** expose it directly to
the public internet without the steps below.

**Harden before any untrusted exposure:**

1. **Enable API-key auth** — pass `--api-key` (or `DATA_TOOL_MCP_API_KEY`). Every request except health checks
   then requires `X-API-Key` or `Authorization: Bearer <key>` (constant-time compare). The Admin API and MCP
   endpoints share this gate.
2. **Restrict Host header** — pass `--allowed-hosts your.host` to block DNS-rebinding.
3. **Front with TLS + reverse proxy** — terminate HTTPS, and keep the MCP server on a private network.
4. **Least privilege DB accounts** — grant the connected DB users only what the agents need.
5. **Watch the SQL console / templates** — parameterized template tools run caller-supplied values by string
   interpolation (consistent with the upstream design). Treat admin-created tools as trusted code.

**What is safe by default:**

- Data-source **passwords are encrypted at rest** (Fernet) before being written to the store
  (falls back to plaintext only if `cryptography` is unavailable — it is a core dependency, so normally on).
- Queries are bounded by `max_rows` (10 000) and `query_timeout` (30 s) → no unbounded result sets / OOM.
- CORS: a wildcard origin automatically disables credentials (no accidental credentialed cross-origin).
- Request bodies are capped at 10 MB, enforced on chunked transfers too.

> Found a vulnerability? Please see [SECURITY.md](./SECURITY.md) (or email the maintainers) and **do not**
> open a public issue for it.

---

## 📁 Project structure

Monorepo, strict front/back separation:

```
data-tool-mcp/
├── README.md
├── README_EN.md               # this file
├── docker-compose.yml         # one-command backend + UI
├── backend/                   # Python MCP Toolbox (pure API/MCP service)
│   ├── main.py                # shortcut launcher
│   ├── pyproject.toml
│   ├── Dockerfile             # backend image (non-root, health-checked)
│   ├── docker/                # config example + init-mysql.sql
│   ├── src/data_tool_mcp/
│   │   ├── cli/main.py        # CLI entrypoint
│   │   ├── config/            # loader + models + store (encrypted creds)
│   │   ├── server/            # FastAPI app, routes, mcp/, middleware/
│   │   ├── admin/             # Admin UI REST API
│   │   ├── sources/           # 45+ data-source implementations
│   │   ├── tools/             # tool + template implementations
│   │   ├── resources/ prompts/ embeddingmodels/ telemetry/
│   │   └── prebuiltconfigs/   # 38 ready-made YAMLs
│   └── tests/
└── frontend/                  # React Admin UI (separate nginx deployment)
    ├── src/  vite.config.ts  Dockerfile  nginx.conf.template  docker-entrypoint.sh
    └── dist/                  # build output (npm run build)
```

---

## 🛠️ Development

```bash
# Backend
cd backend && pip install -e ".[dev,all]"
pytest                 # tests
mypy src/              # type check (strict)
ruff format src/ && ruff check src/

# Frontend
cd frontend && npm install
npm run dev            # dev server (proxies /admin + MCP to :5000)
npm run build          # -> frontend/dist/ (nginx-served)
```

---

## 🤝 Contributing

Contributions are welcome! Please open an issue to discuss significant changes first.
See [CONTRIBUTING.md](./CONTRIBUTING.md) for setup, branching, and PR guidelines, and
[CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) for community norms.

---

## 🗺️ Roadmap

- [ ] Per-tool / per-toolset authorization policies (beyond the global API key)
- [ ] Result streaming / pagination for very large queries
- [ ] First-class read-only / statement-allowlist mode for untrusted clients
- [ ] More data sources & cloud providers
- [ ] Kubernetes / Helm chart & hosted quick-start

---

## 📄 License

[Apache License 2.0](./LICENSE). © data-tool-mcp contributors.

## 🙏 Acknowledgements

This project's design is derived from and built upon Google's open-source [MCP Toolbox](https://github.com/googleapis/mcp-toolbox) (Apache-2.0).
Thanks to the upstream community for the work and inspiration. Built with FastAPI, SQLAlchemy, and React.
