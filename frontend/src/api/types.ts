export interface SourceInfo {
  name: string;
  type: string;
  status: 'connected' | 'disconnected' | 'error' | 'unknown';
  latency: number | null;
  error: string | null;
  toolCount?: number;
  createdTools?: string[];
  // 配置字段（动态，取决于数据源类型；密码脱敏为 "********"）
  [key: string]: unknown;
}

interface SourceTypeField {
  name: string;
  label: string;
  type: 'text' | 'number' | 'password';
  required?: boolean;
  default?: string | number;
  placeholder?: string;
}

export interface SourceTypeSchema {
  fields: SourceTypeField[];
}

export interface ToolInfo {
  name: string;
  type: string;
  source: string | null;
  description: string | null;
  inputSchema?: {
    properties: Record<string, ToolParamSchema>;
    required: string[];
  };
  category?: 'oneclick' | 'parameterized' | 'sql';
}

interface ToolParamSchema {
  type: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
}

export interface ToolParam {
  name: string;
  type: string;
  description?: string;
  required?: boolean;
  default?: unknown;
  enum?: unknown[];
}

export interface DashboardStats {
  version: string;
  uptime: string | null;
  sourceCount: number;
  sourceOnline: number;
  toolCount: number;
  todayRequests: number;
  sourceHealth: SourceHealth[];
  recentErrors: ErrorEntry[];
}

interface SourceHealth {
  name: string;
  status: string;
  latency: number | null;
  lastError: string | null;
}

interface ErrorEntry {
  timestamp: string;
  message: string;
}

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  rowCount: number;
  durationMs: number;
}

export interface ToolInvokeResult {
  result: unknown;
}

export interface TestConnectionResult {
  ok: boolean;
  latency: number;
  error: string | null;
}

export interface TablesList {
  tables: string[];
}
