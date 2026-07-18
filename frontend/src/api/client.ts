import axios from 'axios';
import type {
  SourceInfo,
  SourceTypeSchema,
  ToolInfo,
  DashboardStats,
  QueryResult,
  TestConnectionResult,
  ToolInvokeResult,
  TablesList,
} from './types';

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE || '/mcp-api', timeout: 30000 });

// 从后端 detail 中提取友好的错误消息
// 支持字符串、{code, fields}、[{msg, param}] 等多种格式
function parseDetailMessage(detail: unknown): string {
  if (!detail) return '';
  // 字符串直接返回
  if (typeof detail === 'string') return detail;
  // 数组：通常是 FastAPI 422 校验错误 [{msg, loc, param}, ...]
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item: any) => {
        if (typeof item === 'string') return item;
        if (!item || typeof item !== 'object') return '';
        // 优先使用 msg 字段
        const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : item.param || item.field;
        const text = item.msg || item.message || '';
        return field ? `${field}: ${text}` : text;
      })
      .filter(Boolean);
    return parts.join('；');
  }
  // 对象：可能是 {code, fields}, {message}, {msg} 等
  if (typeof detail === 'object') {
    const obj = detail as Record<string, any>;
    // 显式 message/msg 字段优先
    if (typeof obj.message === 'string') return obj.message;
    if (typeof obj.msg === 'string') return obj.msg;
    // {code, fields} 形式：拼接字段错误
    if (obj.code && obj.fields && typeof obj.fields === 'object') {
      const fieldParts = Object.entries(obj.fields).map(([k, v]) => `${k}: ${v}`);
      return `${obj.code}${fieldParts.length ? '（' + fieldParts.join('；') + '）' : ''}`;
    }
    // 兜底：转成可读字符串
    try {
      return JSON.stringify(detail);
    } catch {
      return '未知错误';
    }
  }
  return String(detail);
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status: number = error.response?.status ?? 0;
    const code: string = error.code || '';
    const rawDetail: unknown = error.response?.data?.detail ?? error.response?.data?.message ?? null;
    let message = '';

    // 按状态码/错误类型分类处理
    if (status === 0 || code === 'ERR_NETWORK') {
      message = '网络连接失败，请检查网络';
    } else if (code === 'ECONNABORTED') {
      message = '请求超时，请稍后重试';
    } else {
      switch (status) {
        case 400:
          message = parseDetailMessage(rawDetail) || '请求参数有误';
          break;
        case 401:
          message = '未授权，请检查认证信息';
          break;
        case 403:
          message = '没有权限执行此操作';
          break;
        case 404:
          message = '请求的资源不存在';
          break;
        case 409:
          message = '资源已存在或存在冲突';
          break;
        case 422:
          message = parseDetailMessage(rawDetail) || '请求数据校验失败';
          break;
        default:
          if (status >= 500 && status < 600) {
            message = '服务异常，请稍后重试';
          } else {
            message = '请求失败，请稍后重试';
          }
      }
    }

    // 记录完整错误信息供开发者调试
    console.error(`[API] ${error.config?.url} status=${status} code=${code}`, {
      status,
      code,
      detail: rawDetail,
      message,
    });

    // reject 结构化对象，message 供 UI 直接展示，detail 保留原始数据供调试
    return Promise.reject({ message, status, detail: rawDetail });
  },
);

export async function fetchDashboard(): Promise<DashboardStats> {
  const { data } = await api.get('/dashboard');
  return data;
}

export async function fetchSources(): Promise<SourceInfo[]> {
  const { data } = await api.get('/sources');
  return data;
}

// 获取单个数据源详情(含密码密文, 供编辑表单使用)
export async function fetchSource(name: string): Promise<SourceInfo> {
  const { data } = await api.get(`/sources/${encodeURIComponent(name)}`);
  return data;
}

export async function createSource(payload: { name: string; type: string; [key: string]: unknown }): Promise<SourceInfo> {
  const { data } = await api.post('/sources', payload);
  return data;
}

export async function updateSource(name: string, payload: Record<string, unknown>): Promise<SourceInfo> {
  const { data } = await api.put(`/sources/${encodeURIComponent(name)}`, payload);
  return data;
}

export async function deleteSource(name: string): Promise<void> {
  await api.delete(`/sources/${encodeURIComponent(name)}`);
}

export async function testSourceConnection(name: string): Promise<TestConnectionResult> {
  const { data } = await api.post(`/sources/${encodeURIComponent(name)}/test`);
  return data;
}

export async function fetchSourceTypes(): Promise<Record<string, SourceTypeSchema>> {
  const { data } = await api.get('/source-types');
  return data;
}

export async function fetchTools(): Promise<ToolInfo[]> {
  const { data } = await api.get('/tools');
  return data;
}

export async function getTool(name: string): Promise<ToolInfo> {
  const { data } = await api.get(`/tools/${encodeURIComponent(name)}`);
  return data;
}

export async function invokeTool(name: string, params: Record<string, unknown>): Promise<ToolInvokeResult> {
  const { data } = await api.post(`/tools/${encodeURIComponent(name)}/invoke`, { params });
  return data;
}

export async function deleteTool(name: string): Promise<void> {
  await api.delete(`/tools/${encodeURIComponent(name)}`);
}

export async function executeQuery(sourceName: string, statement: string): Promise<QueryResult> {
  const { data } = await api.post('/query', { sourceName, statement });
  return data;
}

export async function fetchSourceTables(name: string): Promise<TablesList> {
  const { data } = await api.get(`/sources/${encodeURIComponent(name)}/tables`);
  return data;
}

export interface McpTestTool {
  name: string;
  description: string;
}

export interface McpTestResult {
  ok: boolean;
  count: number;
  tools: McpTestTool[];
}

export async function mcpTest(toolset: string, systemId: string = '', environment: string = ''): Promise<McpTestResult> {
  const { data } = await api.post('/mcp-test', { toolset, systemId, environment });
  return data;
}

export interface ToolsetInfo {
  name: string;
  displayName: string;
  toolCount: number;
  type?: 'all' | 'system' | 'source' | 'custom';
}

export async function fetchToolsets(): Promise<ToolsetInfo[]> {
  const { data } = await api.get('/toolsets');
  return data;
}

export interface SystemInfo {
  systemId: string;
  sourceCount: number;
  sources: string[];
  environments: string[];
}

export async function fetchEnvironments(): Promise<string[]> {
  const { data } = await api.get('/environments');
  return data;
}

export async function fetchSystems(): Promise<SystemInfo[]> {
  const { data } = await api.get('/systems');
  return data;
}

export async function fetchSourcesBySystem(systemId: string): Promise<SourceInfo[]> {
  const { data } = await api.get(`/systems/${encodeURIComponent(systemId)}/sources`);
  return data;
}

// --- MCP 请求统计 ---

export interface McpStatsSummary {
  total: number;
  success: number;
  fail: number;
  avg_latency_ms: number;
}

export interface McpStatsGroupItem {
  system_id?: string;
  source_name?: string;
  tool_name?: string;
  environment?: string;
  total: number;
  success: number;
  fail: number;
}

export interface McpStatsTimelineItem {
  date: string;
  total: number;
  success: number;
  fail: number;
}

export interface McpStatsResult {
  summary: McpStatsSummary;
  by_system: McpStatsGroupItem[];
  by_environment: McpStatsGroupItem[];
  by_source: McpStatsGroupItem[];
  by_tool: McpStatsGroupItem[];
  timeline: McpStatsTimelineItem[];
  start_date: string;
  end_date: string;
  note?: string;
}

export async function fetchMcpStats(params: {
  startDate?: string;
  endDate?: string;
  systemId?: string;
  sourceName?: string;
  environment?: string;
}): Promise<McpStatsResult> {
  const query: Record<string, string> = {};
  if (params.startDate) query.start_date = params.startDate;
  if (params.endDate) query.end_date = params.endDate;
  if (params.systemId) query.system_id = params.systemId;
  if (params.sourceName) query.source_name = params.sourceName;
  if (params.environment) query.environment = params.environment;
  const { data } = await api.get('/mcp-stats', { params: query });
  return data;
}

// --- MCP 请求记录明细（分页） ---

export interface McpLogItem {
  id: number;
  system_id: string;
  source_name: string;
  tool_name: string;
  method: string;
  success: boolean;
  latency_ms: number;
  client_addr: string;
  error_msg: string;
  created_at: string;
  environment: string;
}

export interface McpLogsResult {
  items: McpLogItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  start_date: string;
  end_date: string;
  note?: string;
}

export async function fetchMcpLogs(params: {
  page?: number;
  pageSize?: number;
  startDate?: string;
  endDate?: string;
  systemId?: string;
  sourceName?: string;
  environment?: string;
}): Promise<McpLogsResult> {
  const query: Record<string, string> = {};
  if (params.page) query.page = String(params.page);
  if (params.pageSize) query.page_size = String(params.pageSize);
  if (params.startDate) query.start_date = params.startDate;
  if (params.endDate) query.end_date = params.endDate;
  if (params.systemId) query.system_id = params.systemId;
  if (params.sourceName) query.source_name = params.sourceName;
  if (params.environment) query.environment = params.environment;
  const { data } = await api.get('/mcp-logs', { params: query });
  return data;
}
