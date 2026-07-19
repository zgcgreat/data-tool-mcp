"""Cloud SQL Admin source — google-cloud-sql-admin REST API.

Maps to Go: internal/sources/cloudsqladmin/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from data_tool_mcp.sources.base import Source, SourceConfig, register_source


class CloudSQLAdminSource(Source):
    """Cloud SQL Admin source using google-cloud-sql-admin API."""

    def __init__(self, name: str, client: Any, project_id: str):
        """初始化数据源配置。"""
        self._name = name
        self._client = client
        self._project_id = project_id

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-sql-admin"

    async def connect(self) -> None:
        """建立数据库连接。"""
        pass  # GCP 无状态客户端：连接已在 initialize() 中建立，此处为有意空实现（no-op）

    async def close(self) -> None:
        """关闭数据库连接。"""
        pass  # GCP 无状态客户端：无需显式关闭，交由垃圾回收（no-op）

    async def _execute(self, fn):
        """在线程池中执行同步调用。"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn)

    async def list_instances(self) -> list[dict[str, Any]]:
        """列出所有 Cloud SQL 实例。"""
        resp = await self._execute(
            lambda: self._client.instances().list(project=self._project_id).execute()
        )
        return resp.get("items", [])

    async def get_instance(self, instance_id: str) -> dict[str, Any]:
        """获取指定实例的详细信息。"""
        return dict(
            await self._execute(
                lambda: self._client.instances()
                .get(project=self._project_id, instance=instance_id)
                .execute()
            )
        )

    async def create_database(self, instance_id: str, database: str) -> Any:
        """在指定实例中创建数据库。"""
        return await self._execute(
            lambda: self._client.databases()
            .insert(project=self._project_id, instance=instance_id, body={"name": database})
            .execute()
        )

    async def list_databases(self, instance_id: str) -> list[dict[str, Any]]:
        """列出指定实例中所有数据库。"""
        resp = await self._execute(
            lambda: self._client.databases()
            .list(project=self._project_id, instance=instance_id)
            .execute()
        )
        return resp.get("items", [])

    async def create_users(self, instance_id: str, name: str, password: str) -> Any:
        """在指定实例中创建用户。"""
        return await self._execute(
            lambda: self._client.users()
            .insert(
                project=self._project_id,
                instance=instance_id,
                body={"name": name, "password": password},
            )
            .execute()
        )

    async def clone_instance(self, instance_id: str, clone_body: dict) -> Any:
        """克隆指定实例。"""
        return await self._execute(
            lambda: self._client.instances()
            .clone(project=self._project_id, instance=instance_id, body=clone_body)
            .execute()
        )

    async def create_backup(self, instance_id: str, body: dict) -> Any:
        """为指定实例创建备份。"""
        return await self._execute(
            lambda: self._client.backupRuns()
            .insert(project=self._project_id, instance=instance_id, body=body)
            .execute()
        )

    async def restore_backup(self, instance_id: str, body: dict) -> Any:
        """从备份恢复指定实例。"""
        return await self._execute(
            lambda: self._client.instances()
            .restoreBackup(project=self._project_id, instance=instance_id, body=body)
            .execute()
        )

    async def execute_sql(
        self, project: str, instance: str, database: str, sql: str, access_token: str = ""
    ) -> Any:
        """在指定实例上执行 SQL 语句。"""
        body = {"database": database, "sqlStatement": sql}
        if access_token:
            # Build a new service with the provided access token for client OAuth
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
            except ImportError as e:
                raise ImportError(
                    "google-api-python-client and google-auth are required: "
                    "pip install google-api-python-client google-auth"
                ) from e
            creds = Credentials(token=access_token)
            client = build("sqladmin", "v1", credentials=creds)
            return await self._execute(
                lambda: client.instances()
                .executeSql(project=project, instance=instance, body=body)
                .execute()
            )
        return await self._execute(
            lambda: self._client.instances()
            .executeSql(project=project, instance=instance, body=body)
            .execute()
        )

    async def wait_for_operation(self, operation_id: str) -> Any:
        """等待指定操作完成。"""
        return await self._execute(
            lambda: self._client.operations()
            .get(project=self._project_id, operation=operation_id)
            .execute()
        )


@register_source("cloud-sql-admin")
@dataclass
class CloudSQLAdminSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""

    @property
    def source_type(self) -> str:
        """返回数据源类型标识符。"""
        return "cloud-sql-admin"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudSQLAdminSourceConfig:
        """从字典构造配置实例。"""
        return cls(_name=name, project_id=data.get("projectId", ""))

    async def initialize(self, tracer=None) -> CloudSQLAdminSource:
        """创建并初始化数据源实例。"""
        try:
            from googleapiclient.discovery import build
        except ImportError as e:
            raise ImportError(
                "google-api-python-client is required: pip install google-api-python-client"
            ) from e

        client = build("sqladmin", "v1")
        source = CloudSQLAdminSource(name=self._name, client=client, project_id=self.project_id)
        await source.connect()
        return source
