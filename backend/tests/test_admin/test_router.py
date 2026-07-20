from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from unittest.mock import AsyncMock, MagicMock

from data_tool_mcp.admin.router import router


@pytest.fixture
def app():
    app = FastAPI()
    rm = MagicMock()
    # 同步方法: 返回空集合/False/None 以模拟"无数据"状态
    rm.get_all_source_configs.return_value = {}
    rm.get_source_config.return_value = None
    rm.has_source.return_value = False
    rm.get_tools_map.return_value = {}
    rm.get_toolsets_map.return_value = {}
    rm.get_prompts_map.return_value = {}
    rm.get_toolset.return_value = None
    # async 方法: 使用 AsyncMock(方案 C 改造后 RM 接口为 async)
    rm.get_source = AsyncMock(return_value=None)
    rm.release_source = AsyncMock(return_value=None)
    rm.add_source = AsyncMock(return_value=None)
    rm.remove_source = AsyncMock(return_value=None)
    rm.invalidate_source = AsyncMock(return_value=None)
    app.state.resource_manager = rm
    app.state.config = MagicMock()
    app.state.config.version = "0.1.0"
    # 默认全部启用: enabled_source_types 为空列表
    app.state.config.enabled_source_types = []
    app.include_router(router)
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_dashboard(client):
    resp = await client.get("/mcp-api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "sourceCount" in data
    assert "toolCount" in data


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/mcp-api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data


@pytest.mark.asyncio
async def test_health_with_sources(app, client, monkeypatch):
    """/health 应对每个数据源执行真实健康检测,返回 healthy/unhealthy 状态。

    场景:store 中有 2 个数据源,一个连接成功(healthy),一个连接失败(unhealthy)。
    """
    import sys

    router_mod = sys.modules["data_tool_mcp.admin.router"]

    # mock store:is_persistent=True,load_sources 返回 2 个数据源
    store = MagicMock()
    store.is_persistent = True
    store.load_sources = AsyncMock(
        return_value=[
            {"name": "src-ok", "type": "postgres"},
            {"name": "src-fail", "type": "mysql"},
        ]
    )
    # store.get_source 返回非 None 配置,通过存在性检查
    store.get_source = AsyncMock(
        side_effect=lambda n: {"name": n, "type": "x", "systemId": "", "environment": ""}
    )
    monkeypatch.setattr(router_mod, "get_store", lambda: store)

    # mock rm:has_source 返回 True,get_source 返回 mock source
    rm = app.state.resource_manager
    rm.has_source.return_value = True
    rm.get_source_config.return_value = {"name": "x", "type": "x"}

    # 构造两个 mock source:一个 connect 成功,一个 connect 抛异常
    async def _connect_ok():
        pass

    async def _connect_fail():
        raise ConnectionError("DB unreachable")

    src_ok = MagicMock()
    src_ok.connect = _connect_ok
    src_fail = MagicMock()
    src_fail.connect = _connect_fail

    # get_source 第一次返回 src_ok,第二次返回 src_fail
    rm.get_source = AsyncMock(side_effect=[src_ok, src_fail])
    rm.release_source = AsyncMock(return_value=None)

    resp = await client.get("/mcp-api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["server"] == "running"
    # 2 个数据源都有健康项
    assert len(data["sources"]) == 2
    health_map = {item["name"]: item for item in data["sources"]}
    # src-ok 应为 healthy
    assert health_map["src-ok"]["status"] == "healthy"
    assert health_map["src-ok"]["latency"] is not None
    assert health_map["src-ok"]["lastError"] is None
    # src-fail 应为 unhealthy
    assert health_map["src-fail"]["status"] == "unhealthy"
    assert "DB unreachable" in health_map["src-fail"]["lastError"]


@pytest.mark.asyncio
async def test_sources_list_empty(client):
    resp = await client.get("/mcp-api/sources")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_source_types(client):
    resp = await client.get("/mcp-api/source-types")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "postgres" in data
    assert "fields" in data["postgres"]


@pytest.mark.asyncio
async def test_source_types_with_whitelist(app, client):
    """启用白名单后,/source-types 只返回白名单内的类型。"""
    app.state.config.enabled_source_types = ["postgres", "mysql"]
    resp = await client.get("/mcp-api/source-types")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"postgres", "mysql"}


@pytest.mark.asyncio
async def test_create_source_blocked_by_whitelist(app, client):
    """启用白名单后,创建被禁用类型的数据源应返回 403。"""
    app.state.config.enabled_source_types = ["postgres"]
    resp = await client.post(
        "/mcp-api/sources",
        json={
            "name": "test-mysql",
            "type": "mysql",
            "systemId": "sys001",
            "environment": "dev",
            "host": "localhost",
            "port": 3306,
            "database": "test",
            "user": "root",
            "password": "secret",
        },
    )
    assert resp.status_code == 403
    assert "未启用" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_tools_list(client):
    resp = await client.get("/mcp-api/tools")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_tools_list_from_store(app, client, monkeypatch):
    """启用持久化 store 后,/tools 应优先从 store 查询(多实例一致性)。"""
    import sys

    router_mod = sys.modules["data_tool_mcp.admin.router"]

    # mock store: is_persistent=True,load_tools 返回 1 个工具
    store = MagicMock()
    store.is_persistent = True
    store.load_tools = AsyncMock(
        return_value=[
            {
                "name": "pg-execute_sql",
                "type": "postgres-execute-sql",
                "source": "pg-src",
                "description": "执行 SQL",
                "systemId": "sys001",
                "environment": "dev",
            }
        ]
    )
    monkeypatch.setattr(router_mod, "get_store", lambda: store)
    # rm.get_tool 返回 None(模拟 rm 内存未命中,强制走 store 分类回退)
    rm = app.state.resource_manager
    rm.get_tool.return_value = None

    resp = await client.get("/mcp-api/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    item = data[0]
    assert item["name"] == "pg-execute_sql"
    assert item["type"] == "postgres-execute-sql"
    assert item["source"] == "pg-src"
    assert item["systemId"] == "sys001"
    assert item["environment"] == "dev"
    # 无 templateParameters + 无 statement + -execute-sql 类型 → "sql"
    assert item["category"] == "sql"


@pytest.mark.asyncio
async def test_get_tool_from_store(app, client, monkeypatch):
    """启用持久化 store 后,/tools/{name} 应优先从 store 查询。"""
    import sys

    router_mod = sys.modules["data_tool_mcp.admin.router"]

    store = MagicMock()
    store.is_persistent = True
    store.get_tool = AsyncMock(
        return_value={
            "name": "pg-list_tables",
            "type": "postgres-list-tables",
            "source": "pg-src",
            "description": "列出所有表",
            "systemId": "sys001",
            "environment": "dev",
        }
    )
    monkeypatch.setattr(router_mod, "get_store", lambda: store)
    rm = app.state.resource_manager
    rm.get_tool.return_value = None  # rm 未命中,走 store 回退

    resp = await client.get("/mcp-api/tools/pg-list_tables")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "pg-list_tables"
    assert data["type"] == "postgres-list-tables"
    assert data["source"] == "pg-src"
    # list-tables 工具无参数 → oneclick
    assert data["category"] == "oneclick"
    # 无参数工具 → inputSchema 为 None
    assert data.get("inputSchema") is None


@pytest.mark.asyncio
async def test_get_tool_404_from_store(app, client, monkeypatch):
    """store 中工具不存在时,回退到 rm,rm 也无则返回 404。"""
    import sys

    router_mod = sys.modules["data_tool_mcp.admin.router"]

    store = MagicMock()
    store.is_persistent = True
    store.get_tool = AsyncMock(return_value=None)
    monkeypatch.setattr(router_mod, "get_store", lambda: store)
    # rm.get_tool 也返回 None,模拟 store 和 rm 都未命中
    rm = app.state.resource_manager
    rm.get_tool.return_value = None

    resp = await client.get("/mcp-api/tools/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_config(client):
    resp = await client.get("/mcp-api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "yaml" in data
    assert "prebuiltNames" in data


@pytest.mark.asyncio
async def test_get_source_404(client):
    resp = await client.get("/mcp-api/sources/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_source_204(client):
    resp = await client.delete("/mcp-api/sources/nonexistent")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_query_missing_params(client):
    resp = await client.post("/mcp-api/query", json={})
    assert resp.status_code == 400
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_mcp_test_system_only(app, client):
    """system-only 访问(仅 systemId 无 environment/toolset)应返回该系统工具列表。

    验证 /{systemId}/sse 路径对应的 mcp-test 调用不再返回 404。
    ResourceManager 创建 {systemId} toolset 后,mcp-test 能正确解析并返回工具。
    """
    from data_tool_mcp.resources import Toolset

    # 配置 mock:rm.get_toolset("sys001") 返回非 None,模拟系统级 toolset 已创建
    rm = app.state.resource_manager
    rm.get_toolset.return_value = Toolset(name="sys001", tools=["tool1", "tool2"])
    # MCPProtocol.handle_tools_list 内部调用 get_toolset_tools,返回工具列表
    # 用 MagicMock 模拟工具对象(有 name 和 manifest 方法)
    mock_tool = MagicMock()
    mock_tool.name = "tool1"
    mock_tool.manifest.return_value = MagicMock(description="test tool")
    rm.get_toolset_tools.return_value = [mock_tool]

    resp = await client.post(
        "/mcp-api/mcp-test",
        json={"toolset": "", "systemId": "sys001", "environment": ""},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["count"] == 1
    assert data["tools"][0]["name"] == "tool1"


@pytest.mark.asyncio
async def test_mcp_test_system_only_not_found(app, client):
    """system-only 访问不存在的 systemId 应返回 404(而非误返回全部工具)。"""
    rm = app.state.resource_manager
    # get_toolset 默认返回 None(fixture 配置),无需额外设置

    resp = await client.post(
        "/mcp-api/mcp-test",
        json={"toolset": "", "systemId": "nonexistent", "environment": ""},
    )
    assert resp.status_code == 404
    assert "toolset 'nonexistent' not found" in resp.json()["detail"]


# ===========================================================================
# toolsets 表移除后的动态聚合测试
# ===========================================================================


def _make_store_mock(tools_list):
    """构造一个 mock store,load_tools 返回 tools_list,is_persistent=True。"""
    store = MagicMock()
    store.is_persistent = True
    store.load_tools = AsyncMock(return_value=tools_list)
    return store


@pytest.mark.asyncio
async def test_check_toolset_exists_in_store_all_types():
    """_check_toolset_exists_in_store 应能识别 5 种 toolset 类型(source/system/system-env/custom)。"""
    from data_tool_mcp.admin._stats import _check_toolset_exists_in_store

    tools_list = [
        # source = pg-src,systemId = sys001,environment = dev,toolsetNames = ["reporting"]
        {
            "name": "pg-list_tables",
            "type": "postgres-list-tables",
            "source": "pg-src",
            "systemId": "sys001",
            "environment": "dev",
            "toolsetNames": ["reporting"],
        },
        # source = mysql-src,systemId = sys002,environment = prod(无 custom toolset)
        {
            "name": "mysql-execute_sql",
            "type": "mysql-execute-sql",
            "source": "mysql-src",
            "systemId": "sys002",
            "environment": "prod",
            "toolsetNames": [],
        },
    ]
    store = _make_store_mock(tools_list)

    # source toolset
    assert await _check_toolset_exists_in_store(store, "pg-src") is True
    assert await _check_toolset_exists_in_store(store, "mysql-src") is True
    # system toolset
    assert await _check_toolset_exists_in_store(store, "sys001") is True
    assert await _check_toolset_exists_in_store(store, "sys002") is True
    # system-env toolset
    assert await _check_toolset_exists_in_store(store, "sys001-dev") is True
    assert await _check_toolset_exists_in_store(store, "sys002-prod") is True
    # custom toolset
    assert await _check_toolset_exists_in_store(store, "reporting") is True
    # 不存在的 toolset
    assert await _check_toolset_exists_in_store(store, "nonexistent") is False
    assert await _check_toolset_exists_in_store(store, "sys001-prod") is False


@pytest.mark.asyncio
async def test_build_toolsets_from_store_aggregation():
    """_build_toolsets_from_store 应动态聚合 5 类 toolset(all/source/system/system-env/custom)。"""
    from data_tool_mcp.admin._tools import _build_toolsets_from_store

    tools_list = [
        {
            "name": "pg-list_tables",
            "type": "postgres-list-tables",
            "source": "pg-src",
            "systemId": "sys001",
            "environment": "dev",
            "toolsetNames": ["reporting"],
        },
        {
            "name": "pg-execute_sql",
            "type": "postgres-execute-sql",
            "source": "pg-src",
            "systemId": "sys001",
            "environment": "dev",
            "toolsetNames": ["reporting", "analytics"],
        },
        {
            "name": "mysql-list_tables",
            "type": "mysql-list-tables",
            "source": "mysql-src",
            "systemId": "sys002",
            "environment": "prod",
            "toolsetNames": [],
        },
    ]
    store = _make_store_mock(tools_list)
    result = await _build_toolsets_from_store(store)

    # 应包含 6 个 toolset:all + 2 source + 2 system + 2 system-env + 2 custom
    # (sys001-dev 有 2 个工具,sys002-prod 有 1 个工具;reporting 2 个,analytics 1 个)
    assert result is not None
    names = {item["name"]: item for item in result}

    # all toolset
    assert "" in names
    assert names[""]["type"] == "all"
    assert names[""]["toolCount"] == 3
    assert names[""]["displayName"] == "全部工具"

    # source toolset
    assert names["pg-src"]["type"] == "source"
    assert names["pg-src"]["toolCount"] == 2
    assert names["mysql-src"]["type"] == "source"
    assert names["mysql-src"]["toolCount"] == 1

    # system toolset
    assert names["sys001"]["type"] == "system"
    assert names["sys001"]["toolCount"] == 2
    assert names["sys002"]["type"] == "system"
    assert names["sys002"]["toolCount"] == 1

    # system-env toolset(归类为 "custom",因为名字含 "-" 不在 system_ids 集合中)
    assert names["sys001-dev"]["type"] == "custom"
    assert names["sys001-dev"]["toolCount"] == 2
    assert names["sys002-prod"]["type"] == "custom"
    assert names["sys002-prod"]["toolCount"] == 1

    # custom toolset(从 toolsetNames 反向聚合)
    assert names["reporting"]["type"] == "custom"
    assert names["reporting"]["toolCount"] == 2
    assert names["analytics"]["type"] == "custom"
    assert names["analytics"]["toolCount"] == 1

    # 验证排序:all → system → source → custom,每组内按名称排序
    types_in_order = [item["type"] for item in result]
    assert types_in_order == sorted(
        types_in_order,
        key=lambda t: {"all": 0, "system": 1, "source": 2, "custom": 3}.get(t, 9),
    )


@pytest.mark.asyncio
async def test_mcp_test_store_priority_zero_latency(app, client, monkeypatch):
    """多实例一致性:store 中有 toolset 但 rm 内存未热重载时,/mcp-test 应通过(store 优先)。

    场景:在实例 A 创建了 sys001 环境的数据源,实例 B 在 5s 热重载窗口内
    尚未拉到 rm 内存,但 store 中已经写入。/mcp-test 应通过 store 立即确认存在。
    """
    import sys

    router_mod = sys.modules["data_tool_mcp.admin.router"]

    # store 中已有 sys001-dev toolset(模拟实例 A 写入后,实例 B 立即查询)
    store = _make_store_mock(
        [
            {
                "name": "pg-list_tables",
                "type": "postgres-list-tables",
                "source": "pg-src",
                "systemId": "sys001",
                "environment": "dev",
            }
        ]
    )
    monkeypatch.setattr(router_mod, "get_store", lambda: store)
    # rm.get_toolset 返回 None(模拟实例 B 内存未热重载)
    rm = app.state.resource_manager
    rm.get_toolset.return_value = None

    # 模拟 MCPProtocol.handle_tools_list 走通
    mock_tool = MagicMock()
    mock_tool.name = "pg-list_tables"
    mock_tool.manifest.return_value = MagicMock(description="list tables")
    rm.get_toolset_tools.return_value = [mock_tool]

    resp = await client.post(
        "/mcp-api/mcp-test",
        json={"toolset": "", "systemId": "sys001", "environment": "dev"},
    )
    # store 优先:即便 rm 内存未热重载,也不应 404
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_mcp_test_404_when_store_says_no(app, client, monkeypatch):
    """store 确认 toolset 不存在时,应直接 404,不回退 rm(避免脏数据)。"""
    import sys

    router_mod = sys.modules["data_tool_mcp.admin.router"]

    # store 中无任何工具(模拟 toolset 不存在)
    store = _make_store_mock([])
    monkeypatch.setattr(router_mod, "get_store", lambda: store)

    # 即便 rm 内存中有 toolset(脏数据/陈旧缓存),也应被 store 否决
    rm = app.state.resource_manager
    from data_tool_mcp.resources import Toolset

    rm.get_toolset.return_value = Toolset(name="ghost", tools=["t1"])

    resp = await client.post(
        "/mcp-api/mcp-test",
        json={"toolset": "", "systemId": "ghost-env", "environment": ""},
    )
    assert resp.status_code == 404
    assert "toolset 'ghost-env' not found" in resp.json()["detail"]


def test_prebuilt_yaml_toolset_names_injection():
    """_build_tool_to_toolsets_map 应从 kind: toolset 块反向构造 {tool: [toolset]} 映射。"""
    from data_tool_mcp.admin._sources import _build_tool_to_toolsets_map

    docs = [
        # kind: tool 块(应被忽略)
        {"kind": "tool", "name": "list-tables", "type": "postgres-list-tables"},
        {"kind": "tool", "name": "execute-sql", "type": "postgres-execute-sql"},
        # kind: toolset 块 1:reporting 包含 list-tables 和 execute-sql
        {
            "kind": "toolset",
            "name": "reporting",
            "tools": [
                {"name": "list-tables"},
                {"name": "execute-sql"},
            ],
        },
        # kind: toolset 块 2:analytics 只包含 execute-sql(多对一)
        {
            "kind": "toolset",
            "name": "analytics",
            "tools": [{"name": "execute-sql"}],
        },
        # 无 name 的 toolset 块(应被忽略)
        {"kind": "toolset", "tools": [{"name": "orphan"}]},
        # tools 中无 name 的项(应被忽略)
        {"kind": "toolset", "name": "empty-tools", "tools": [{"foo": "bar"}]},
    ]

    mapping = _build_tool_to_toolsets_map(docs)

    # execute-sql 同时归属 reporting 和 analytics(多对一)
    assert set(mapping["execute-sql"]) == {"reporting", "analytics"}
    # list-tables 只归属 reporting
    assert mapping["list-tables"] == ["reporting"]
    # 无 toolset 引用的工具不应出现在映射中
    assert "orphan" not in mapping
    # toolset 自身的名字不应作为 key(只有 tool 的 yaml_name 才是 key)
    assert "reporting" not in mapping
    assert "analytics" not in mapping


@pytest.mark.asyncio
async def test_toolsets_endpoint_dynamic_aggregation(app, client, monkeypatch):
    """/toolsets 端点启用 store 后应返回动态聚合的 5 类 toolset。"""
    import sys

    router_mod = sys.modules["data_tool_mcp.admin.router"]

    tools_list = [
        {
            "name": "pg-list_tables",
            "type": "postgres-list-tables",
            "source": "pg-src",
            "systemId": "sys001",
            "environment": "dev",
            "toolsetNames": ["reporting"],
        },
        {
            "name": "mysql-execute_sql",
            "type": "mysql-execute-sql",
            "source": "mysql-src",
            "systemId": "sys002",
            "environment": "prod",
            "toolsetNames": [],
        },
    ]
    store = _make_store_mock(tools_list)
    monkeypatch.setattr(router_mod, "get_store", lambda: store)

    resp = await client.get("/mcp-api/toolsets")
    assert resp.status_code == 200
    data = resp.json()

    # 5 类 toolset:all + 2 source + 2 system + 2 system-env + 1 custom
    assert len(data) == 8

    names = {item["name"]: item for item in data}
    # all
    assert names[""]["type"] == "all"
    assert names[""]["toolCount"] == 2
    assert names[""]["displayName"] == "全部工具"
    # source
    assert names["pg-src"]["type"] == "source"
    assert names["mysql-src"]["type"] == "source"
    # system
    assert names["sys001"]["type"] == "system"
    assert names["sys002"]["type"] == "system"
    # system-env(归类为 custom,因为含 "-")
    assert names["sys001-dev"]["type"] == "custom"
    assert names["sys002-prod"]["type"] == "custom"
    # custom
    assert names["reporting"]["type"] == "custom"
    assert names["reporting"]["toolCount"] == 1
