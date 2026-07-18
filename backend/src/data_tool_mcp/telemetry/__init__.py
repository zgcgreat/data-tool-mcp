"""OpenTelemetry instrumentation for mcp-toolbox.

Maps to Go: internal/telemetry/telemetry.go + instrumentation.go

Provides:
  - SetupOTel: Initialize TracerProvider + MeterProvider (OTLP HTTP + GCP)
  - Instrumentation: 4 MCP semantic metrics
  - W3C Trace Context propagation support
"""

from __future__ import annotations

import os
from typing import Any

# ---------------------------------------------------------------------------
# Constants (matching Go)
# ---------------------------------------------------------------------------

TRACER_NAME = "data_tool_mcp.opentel"
METRIC_NAME = "data_tool_mcp.opentel"

# MCP semantic metric names (per OpenTelemetry semantic conventions)
MCP_OPERATION_DURATION_NAME = "mcp.server.operation.duration"
MCP_SESSION_DURATION_NAME = "mcp.server.session.duration"
MCP_ACTIVE_SESSIONS_NAME = "toolbox.server.mcp.active_sessions"
TOOL_EXECUTION_DURATION_NAME = "toolbox.tool.execution.duration"

# Duration histogram bucket boundaries (matching Go)
DURATION_HISTOGRAM_BUCKETS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 30, 60, 120, 300]


# ---------------------------------------------------------------------------
# Instrumentation
# ---------------------------------------------------------------------------


class Instrumentation:
    """Holds OpenTelemetry tracer and 4 MCP metrics.

    Maps to Go: Instrumentation struct
      Tracer                trace.Tracer
      McpOperationDuration  metric.Float64Histogram   // MCP operation duration (s)
      McpSessionDuration    metric.Float64Histogram   // MCP session duration (s)
      McpActiveSessions     metric.Int64UpDownCounter // Currently active sessions
      ToolExecutionDuration metric.Float64Histogram   // Tool execution duration (s)
    """

    def __init__(
        self,
        tracer: Any = None,
        mcp_operation_duration: Any = None,
        mcp_session_duration: Any = None,
        mcp_active_sessions: Any = None,
        tool_execution_duration: Any = None,
    ):
        """初始化实例。"""
        self.tracer = tracer
        self.mcp_operation_duration = mcp_operation_duration
        self.mcp_session_duration = mcp_session_duration
        self.mcp_active_sessions = mcp_active_sessions
        self.tool_execution_duration = tool_execution_duration


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def _import_otel_core() -> Any:
    """导入 OpenTelemetry 核心模块,未安装时返回 None。"""
    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    except ImportError:
        # OpenTelemetry not installed — return None (no-op)
        return None
    return trace, metrics, TracerProvider, MeterProvider, Resource, SERVICE_NAME, SERVICE_VERSION


def _build_resource(
    Resource: Any,
    SERVICE_NAME: Any,
    SERVICE_VERSION: Any,
    version_string: str,
    telemetry_service_name: str,
) -> Any:
    """构建 OpenTelemetry Resource。"""
    return Resource.create(
        {
            SERVICE_NAME: telemetry_service_name,
            SERVICE_VERSION: version_string,
        }
    )


def _resolve_gcp_project(telemetry_gcp_project: str) -> str:
    """解析 GCP project:参数 > GOOGLE_CLOUD_PROJECT 环境变量。"""
    return telemetry_gcp_project or os.environ.get("GOOGLE_CLOUD_PROJECT", "")


def _make_otlp_trace_exporter(telemetry_otlp: str) -> Any:
    """创建 OTLP trace exporter,未配置或未安装依赖时返回 None。"""
    if not telemetry_otlp:
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(endpoint=telemetry_otlp)
    except ImportError:
        return None


def _create_cloud_trace_exporter(project: str) -> Any:
    """创建 CloudTraceSpanExporter,导入失败返回 None。"""
    try:
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

        return CloudTraceSpanExporter(project_id=project)
    except ImportError:
        return None


def _make_gcp_trace_exporter(telemetry_gcp: bool, telemetry_gcp_project: str) -> Any:
    """创建 GCP Cloud Trace exporter,未启用/无 project/未安装依赖时返回 None。"""
    if not telemetry_gcp:
        return None
    project = _resolve_gcp_project(telemetry_gcp_project)
    if not project:
        return None
    return _create_cloud_trace_exporter(project)


def _build_trace_exporters(
    telemetry_otlp: str,
    telemetry_gcp: bool,
    telemetry_gcp_project: str,
) -> list:
    """构造 trace exporter 列表(过滤 None)。"""
    candidates = [
        _make_otlp_trace_exporter(telemetry_otlp),
        _make_gcp_trace_exporter(telemetry_gcp, telemetry_gcp_project),
    ]
    return [e for e in candidates if e]


def _setup_tracer_provider(
    trace: Any,
    TracerProvider: Any,
    resource: Any,
    trace_exporters: list,
) -> None:
    """创建并注册 TracerProvider,有 exporter 时添加 BatchSpanProcessor。"""
    tracer_provider = TracerProvider(resource=resource)
    if trace_exporters:
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        for exporter in trace_exporters:
            tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(tracer_provider)


def _make_otlp_metric_reader(telemetry_otlp: str) -> Any:
    """创建 OTLP metric reader,未配置或未安装依赖时返回 None。"""
    if not telemetry_otlp:
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        exporter = OTLPMetricExporter(endpoint=telemetry_otlp)
        return PeriodicExportingMetricReader(exporter)
    except ImportError:
        return None


def _create_cloud_monitoring_reader(project: str) -> Any:
    """创建 CloudMonitoringMetricReader,导入失败返回 None。"""
    try:
        from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        exporter = CloudMonitoringMetricExporter(project_id=project)
        return PeriodicExportingMetricReader(exporter)
    except ImportError:
        return None


def _make_gcp_metric_reader(telemetry_gcp: bool, telemetry_gcp_project: str) -> Any:
    """创建 GCP Cloud Monitoring metric reader,未启用/无 project/未安装依赖时返回 None。"""
    if not telemetry_gcp:
        return None
    project = _resolve_gcp_project(telemetry_gcp_project)
    if not project:
        return None
    return _create_cloud_monitoring_reader(project)


def _build_metric_readers(
    telemetry_otlp: str,
    telemetry_gcp: bool,
    telemetry_gcp_project: str,
) -> list:
    """构造 metric reader 列表(过滤 None)。"""
    candidates = [
        _make_otlp_metric_reader(telemetry_otlp),
        _make_gcp_metric_reader(telemetry_gcp, telemetry_gcp_project),
    ]
    return [r for r in candidates if r]


def setup_otel(
    version_string: str = "0.0.0",
    telemetry_otlp: str = "",
    telemetry_gcp: bool = False,
    telemetry_gcp_project: str = "",
    telemetry_service_name: str = "toolbox",
) -> Instrumentation | None:
    """Initialize OpenTelemetry pipeline (TracerProvider + MeterProvider).

    Maps to Go: SetupOTel(ctx, versionString, telemetryOTLP, telemetryGCP, ...)

    Supports:
      - OTLP HTTP exporter (telemetry_otlp endpoint)
      - GCP Cloud Trace + Cloud Monitoring exporter (telemetry_gcp=True)
    """
    core = _import_otel_core()
    if core is None:
        return None
    trace, metrics, TracerProvider, MeterProvider, Resource, SERVICE_NAME, SERVICE_VERSION = core

    resource = _build_resource(
        Resource,
        SERVICE_NAME,
        SERVICE_VERSION,
        version_string,
        telemetry_service_name,
    )

    # --- TracerProvider ---
    trace_exporters = _build_trace_exporters(telemetry_otlp, telemetry_gcp, telemetry_gcp_project)
    _setup_tracer_provider(trace, TracerProvider, resource, trace_exporters)
    tracer = trace.get_tracer(TRACER_NAME, version_string)

    # --- MeterProvider ---
    metric_readers = _build_metric_readers(telemetry_otlp, telemetry_gcp, telemetry_gcp_project)
    meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
    metrics.set_meter_provider(meter_provider)

    # --- Create Instrumentation ---
    return _create_instrumentation(version_string, tracer, meter_provider)


def _create_instrumentation(
    version_string: str,
    tracer: Any,
    meter_provider: Any,
) -> Instrumentation:
    """Create Instrumentation instance with all 4 MCP metrics.

    Maps to Go: CreateTelemetryInstrumentation(versionString)
    """
    from opentelemetry import metrics

    meter = metrics.get_meter(METRIC_NAME, version_string)

    # MCP operation duration histogram (seconds)
    mcp_operation_duration = meter.create_histogram(
        name=MCP_OPERATION_DURATION_NAME,
        description="Duration of MCP operations",
        unit="s",
        explicit_bucket_boundaries=DURATION_HISTOGRAM_BUCKETS,
    )

    # MCP session duration histogram (seconds)
    mcp_session_duration = meter.create_histogram(
        name=MCP_SESSION_DURATION_NAME,
        description="Duration of MCP sessions",
        unit="s",
        explicit_bucket_boundaries=DURATION_HISTOGRAM_BUCKETS,
    )

    # Active sessions up/down counter
    mcp_active_sessions = meter.create_up_down_counter(
        name=MCP_ACTIVE_SESSIONS_NAME,
        description="Number of currently active MCP sessions",
    )

    # Tool execution duration histogram (seconds)
    tool_execution_duration = meter.create_histogram(
        name=TOOL_EXECUTION_DURATION_NAME,
        description="Duration of tool executions",
        unit="s",
        explicit_bucket_boundaries=DURATION_HISTOGRAM_BUCKETS,
    )

    return Instrumentation(
        tracer=tracer,
        mcp_operation_duration=mcp_operation_duration,
        mcp_session_duration=mcp_session_duration,
        mcp_active_sessions=mcp_active_sessions,
        tool_execution_duration=tool_execution_duration,
    )
