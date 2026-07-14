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

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE || '/admin', timeout: 30000 });

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail || error.response?.data?.message;
    const msg = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : error.message;
    console.error(`[API] ${error.config?.url}: ${msg}`);
    return Promise.reject(new Error(msg));
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

export async function mcpTest(toolset: string, systemId: string = ''): Promise<McpTestResult> {
  const { data } = await api.post('/mcp-test', { toolset, systemId });
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
}): Promise<McpStatsResult> {
  const query: Record<string, string> = {};
  if (params.startDate) query.start_date = params.startDate;
  if (params.endDate) query.end_date = params.endDate;
  if (params.systemId) query.system_id = params.systemId;
  if (params.sourceName) query.source_name = params.sourceName;
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
}): Promise<McpLogsResult> {
  const query: Record<string, string> = {};
  if (params.page) query.page = String(params.page);
  if (params.pageSize) query.page_size = String(params.pageSize);
  if (params.startDate) query.start_date = params.startDate;
  if (params.endDate) query.end_date = params.endDate;
  if (params.systemId) query.system_id = params.systemId;
  if (params.sourceName) query.source_name = params.sourceName;
  const { data } = await api.get('/mcp-logs', { params: query });
  return data;
}
