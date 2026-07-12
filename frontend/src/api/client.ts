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

export async function mcpTest(toolset: string): Promise<McpTestResult> {
  const { data } = await api.post('/mcp-test', { toolset });
  return data;
}

export interface ToolsetInfo {
  name: string;
  displayName: string;
  toolCount: number;
}

export async function fetchToolsets(): Promise<ToolsetInfo[]> {
  const { data } = await api.get('/toolsets');
  return data;
}
