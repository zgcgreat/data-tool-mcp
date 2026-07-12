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
        self._name = name
        self._client = client
        self._project_id = project_id

    @property
    def source_type(self) -> str:
        return "cloud-sql-admin"

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def _execute(self, fn):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn)

    async def list_instances(self) -> list[dict[str, Any]]:
        resp = await self._execute(lambda: self._client.instances().list(project=self._project_id).execute())
        return resp.get("items", [])

    async def get_instance(self, instance_id: str) -> dict[str, Any]:
        return dict(await self._execute(lambda: self._client.instances().get(project=self._project_id, instance=instance_id).execute()))

    async def create_database(self, instance_id: str, database: str) -> Any:
        return await self._execute(lambda: self._client.databases().insert(project=self._project_id, instance=instance_id, body={"name": database}).execute())

    async def list_databases(self, instance_id: str) -> list[dict[str, Any]]:
        resp = await self._execute(lambda: self._client.databases().list(project=self._project_id, instance=instance_id).execute())
        return resp.get("items", [])

    async def create_users(self, instance_id: str, name: str, password: str) -> Any:
        return await self._execute(lambda: self._client.users().insert(project=self._project_id, instance=instance_id, body={"name": name, "password": password}).execute())

    async def clone_instance(self, instance_id: str, clone_body: dict) -> Any:
        return await self._execute(lambda: self._client.instances().clone(project=self._project_id, instance=instance_id, body=clone_body).execute())

    async def create_backup(self, instance_id: str, body: dict) -> Any:
        return await self._execute(lambda: self._client.backupRuns().insert(project=self._project_id, instance=instance_id, body=body).execute())

    async def restore_backup(self, instance_id: str, body: dict) -> Any:
        return await self._execute(lambda: self._client.instances().restoreBackup(project=self._project_id, instance=instance_id, body=body).execute())

    async def execute_sql(self, project: str, instance: str, database: str, sql: str, access_token: str = "") -> Any:
        body = {"database": database, "sqlStatement": sql}
        if access_token:
            # Build a new service with the provided access token for client OAuth
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            creds = Credentials(token=access_token)
            client = build("sqladmin", "v1", credentials=creds)
            return await self._execute(lambda: client.instances().executeSql(project=project, instance=instance, body=body).execute())
        return await self._execute(lambda: self._client.instances().executeSql(project=project, instance=instance, body=body).execute())

    async def wait_for_operation(self, operation_id: str) -> Any:
        return await self._execute(lambda: self._client.operations().get(project=self._project_id, operation=operation_id).execute())


@register_source("cloud-sql-admin")
@dataclass
class CloudSQLAdminSourceConfig(SourceConfig):
    _name: str = field(init=True, repr=False)
    project_id: str = ""

    @property
    def source_type(self) -> str:
        return "cloud-sql-admin"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> CloudSQLAdminSourceConfig:
        return cls(_name=name, project_id=data.get("projectId", ""))

    async def initialize(self, tracer=None) -> CloudSQLAdminSource:
        try:
            from googleapiclient.discovery import build
        except ImportError as e:
            raise ImportError("google-api-python-client is required: pip install google-api-python-client") from e

        client = build("sqladmin", "v1")
        source = CloudSQLAdminSource(name=self._name, client=client, project_id=self.project_id)
        await source.connect()
        return source
