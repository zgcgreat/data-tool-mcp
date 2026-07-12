import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchDashboard, fetchToolsets, mcpTest } from '../api/client';
import type { McpTestTool, ToolsetInfo } from '../api/client';
import { toast } from '../components/Toast';
import type { DashboardStats } from '../api/types';
import './Dashboard.css';

function ArrowRight() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8h10M9 4l4 4-4 4" />
    </svg>
  );
}

function SparkIcon() {
  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round">
      <path d="M12 2L3 7v10l9 5 9-5V7l-9-5z" />
      <path d="M12 7v10M7 9.5v5M17 9.5v5" strokeWidth="1.2" opacity="0.6" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8l3.5 3.5L13 5" />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="5" y="5" width="8" height="8" rx="1" />
      <path d="M3 11V3a1 1 0 011-1h7" />
    </svg>
  );
}

function PlusSmallIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M8 3v10M3 8h10" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 4h10M6.5 4V2.5h3V4M5 4l.5 9a1 1 0 001 1h3a1 1 0 001-1L11 4" />
    </svg>
  );
}

// 指标条内联图标（线条统一风格）
function MetricIcon({ kind }: { kind: 'source' | 'online' | 'tool' | 'request' }) {
  const common = { width: 16, height: 16, viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor', strokeWidth: 1.4 } as const;
  if (kind === 'source' || kind === 'online') {
    return (
      <svg {...common}>
        <ellipse cx="8" cy="3.5" rx="5.5" ry="2" />
        <path d="M2.5 3.5v9c0 1.1 2.46 2 5.5 2s5.5-.9 5.5-2v-9" />
        <path d="M2.5 8c0 1.1 2.46 2 5.5 2s5.5-.9 5.5-2" />
      </svg>
    );
  }
  if (kind === 'tool') {
    return (
      <svg {...common} fill="currentColor" stroke="none">
        <path d="M14.5 1.5a3 3 0 00-4.24 0L7.4 4.36a.75.75 0 101.06 1.06l2.86-2.86a1.5 1.5 0 012.12 2.12l-2.86 2.86a.75.75 0 101.06 1.06l2.86-2.86a3 3 0 000-4.24z" />
        <path d="M7.3 7.42l-4.33 4.34a1.5 1.5 0 00-.42 1.06l-.3 2.36a.5.5 0 00.57.57l2.36-.3a1.5 1.5 0 001.06-.42l4.34-4.33-3.28-3.28z" fillOpacity="0.85" />
      </svg>
    );
  }
  return (
    <svg {...common} strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 2.5h6v6h-6z" />
      <path d="M5.5 8.5v3a2 2 0 002 2h4" />
      <path d="M10 12l1.5 1.5L13 12" />
    </svg>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [isFirstTime, setIsFirstTime] = useState(false);
  const [toolsets, setToolsets] = useState<ToolsetInfo[]>([]);

  // MCP 配置相关状态
  const [transport, setTransport] = useState<'sse' | 'streamable'>('sse');
  const [selectedToolset, setSelectedToolset] = useState('');
  const [headers, setHeaders] = useState<Array<{ key: string; value: string }>>([
    { key: 'X-Server-Name', value: 'data-tool-mcp' },
  ]);
  const [copied, setCopied] = useState(false);
  const [urlCopied, setUrlCopied] = useState(false);

  // 测试相关状态
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<McpTestTool[] | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  useEffect(() => {
    loadDashboard();
    loadToolsets();
  }, []);

  const loadDashboard = async () => {
    try {
      const data = await fetchDashboard();
      setStats(data);
      const hasSeenDashboard = localStorage.getItem('hasSeenDashboard');
      if (!hasSeenDashboard && data.sourceCount === 0 && data.toolCount === 0) {
        setIsFirstTime(true);
        localStorage.setItem('hasSeenDashboard', 'true');
      }
    } catch (error) {
      toast.error('加载仪表盘失败');
      console.error('Failed to load dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadToolsets = async () => {
    try {
      const data = await fetchToolsets();
      setToolsets(data);
    } catch {
      // 静默失败，不影响页面主流程
    }
  };

  // --- MCP 配置生成 ---

  const serverOrigin = `${window.location.protocol}//${window.location.host}`;
  const toolsetPrefix = selectedToolset ? `/${selectedToolset}` : '';
  const endpointPath = `${toolsetPrefix}${transport === 'sse' ? '/sse' : '/'}`;
  const endpointUrl = `${serverOrigin}${endpointPath}`;

  const jsonConfig = useMemo(() => {
    const serverCfg: Record<string, unknown> = { url: endpointUrl };
    const validHeaders = headers.filter(h => h.key.trim());
    if (validHeaders.length > 0) {
      const headersObj: Record<string, string> = {};
      validHeaders.forEach(h => {
        headersObj[h.key.trim()] = h.value;
      });
      serverCfg.headers = headersObj;
    }
    return JSON.stringify({ mcpServers: { 'data-tool-mcp': serverCfg } }, null, 2);
  }, [endpointUrl, headers]);

  // JSON 行号拆分
  const jsonLines = useMemo(() => jsonConfig.split('\n'), [jsonConfig]);

  const copyConfig = async () => {
    try {
      await navigator.clipboard.writeText(jsonConfig);
      setCopied(true);
      toast.success('配置已复制到剪贴板');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('复制失败，请手动选择复制');
    }
  };

  const copyUrl = async () => {
    try {
      await navigator.clipboard.writeText(endpointUrl);
      setUrlCopied(true);
      toast.success('URL 已复制');
      setTimeout(() => setUrlCopied(false), 2000);
    } catch {
      toast.error('复制失败');
    }
  };

  const addHeader = () => {
    setHeaders(prev => [...prev, { key: '', value: '' }]);
  };

  const updateHeader = (index: number, field: 'key' | 'value', value: string) => {
    setHeaders(prev => prev.map((h, i) => i === index ? { ...h, [field]: value } : h));
  };

  const removeHeader = (index: number) => {
    setHeaders(prev => prev.filter((_, i) => i !== index));
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    setTestError(null);
    try {
      const result = await mcpTest(selectedToolset);
      setTestResult(result.tools);
      toast.success(`测试成功，共 ${result.count} 个工具`);
    } catch (error) {
      const msg = error instanceof Error ? error.message : '测试失败';
      setTestError(msg);
      toast.error(msg);
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        <div className="loading-text">加载中...</div>
      </div>
    );
  }

  // 指标定义
  const metrics = [
    { kind: 'source' as const, label: '数据源', value: stats?.sourceCount ?? 0, onClick: () => navigate('/sources'), tone: 'blue' },
    { kind: 'online' as const, label: '在线', value: stats?.sourceOnline ?? 0, onClick: undefined, tone: 'green' },
    { kind: 'tool' as const, label: '工具', value: stats?.toolCount ?? 0, onClick: () => navigate('/tools'), tone: 'amber' },
    { kind: 'request' as const, label: '今日MCP请求数', value: stats?.todayRequests ?? 0, onClick: () => navigate('/query'), tone: 'violet' },
  ];

  return (
    <div className="dashboard fade-in">
      <div className="page-header">
        <div className="page-title-group">
          <span className="page-eyebrow">系统概览</span>
          <h1 className="page-title">
            <span className="title-icon"><MetricIcon kind="source" /></span>
            仪表盘
          </h1>
        </div>
      </div>

      {isFirstTime && (
        <div className="welcome-banner">
          <div className="welcome-eyebrow">开始使用</div>
          <div className="welcome-content">
            <h2>欢迎使用 数据工具 MCP</h2>
            <p>开始配置数据源，让 AI 能够安全访问您的数据库与工具</p>
            <button className="btn-primary welcome-btn" onClick={() => navigate('/quick-connect')}>
              开始配置 <ArrowRight />
            </button>
          </div>
          <div className="welcome-icon">
            <SparkIcon />
          </div>
        </div>
      )}

      {/* Hero 指标条 */}
      <div className="metrics-strip">
        {metrics.map((m, idx) => (
          <button
            key={m.label}
            className={`metric-cell tone-${m.tone} ${m.onClick ? 'is-clickable' : ''}`}
            style={{ animationDelay: `${idx * 0.06}s` }}
            onClick={m.onClick}
            disabled={!m.onClick}
            type="button"
          >
            <span className="metric-accent-bar" />
            <span className="metric-top">
              <span className="metric-icon"><MetricIcon kind={m.kind} /></span>
              <span className="metric-label">{m.label}</span>
            </span>
            <span className="metric-value">{m.value}</span>
          </button>
        ))}
      </div>

      {/* 运行时长（仅在有时显示） */}
      {stats?.uptime && (
        <div className="sys-info-bar">
          <div className="sys-info-item">
            <span className="sys-info-key">运行时长</span>
            <span className="sys-info-val">{stats.uptime}</span>
          </div>
        </div>
      )}

      {/* MCP 客户端接入配置 - 单卡片 */}
      <div className="mcp-config-dual">
        <div className="mcp-config-header">
          <div className="mcp-config-title-row">
            <div>
              <h3>MCP 客户端接入配置</h3>
              <p>将配置添加到 Claude、Cursor、Codex 等 MCP 客户端即可使用已接入的工具</p>
            </div>
            <button
              className="btn-secondary btn-sm"
              onClick={handleTest}
              disabled={testing}
            >
              {testing ? '测试中...' : '测试连接'}
            </button>
          </div>
        </div>

        <div className="mcp-config-card">
          <div className="mcp-config-grid">
            {/* 左栏：配置控件 */}
            <div className="mcp-config-left">
              {/* 第一行：传输模式 + 工具集（左右平齐） */}
              <div className="mcp-config-row-pair">
                {/* 传输模式 */}
                <div className="mcp-config-row">
                  <label className="form-label">传输模式</label>
                  <div className="segmented-control">
                    <button
                      className={`seg-btn ${transport === 'sse' ? 'active' : ''}`}
                      onClick={() => setTransport('sse')}
                    >
                      SSE
                    </button>
                    <button
                      className={`seg-btn ${transport === 'streamable' ? 'active' : ''}`}
                      onClick={() => setTransport('streamable')}
                    >
                      HTTP
                    </button>
                  </div>
                </div>

                {/* 工具集（有工具集时显示，与传输模式平齐） */}
                {toolsets.length > 0 && (
                  <div className="mcp-config-row">
                    <label className="form-label">工具集</label>
                    <select
                      className="form-select"
                      value={selectedToolset}
                      onChange={e => setSelectedToolset(e.target.value)}
                    >
                      {toolsets.map(ts => (
                        <option key={ts.name} value={ts.name}>
                          {ts.displayName}{ts.toolCount > 0 ? ` (${ts.toolCount})` : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {/* 端点 URL */}
              <div className="mcp-config-row">
                <label className="form-label">端点 URL</label>
                <div className="url-row">
                  <input
                    className="form-input url-input"
                    readOnly
                    value={endpointUrl}
                    onClick={e => (e.target as HTMLInputElement).select()}
                  />
                  <button
                    className="btn-secondary btn-sm"
                    onClick={copyUrl}
                    title="复制 URL"
                  >
                    {urlCopied ? <CheckIcon /> : <CopyIcon />}
                    {urlCopied ? '已复制' : '复制'}
                  </button>
                </div>
              </div>

              {/* 自定义 Header */}
              <div className="mcp-config-row">
                <div className="mcp-config-row-header">
                  <label className="form-label">
                    自定义 Header
                    <span className="form-hint">（可选）</span>
                  </label>
                  <button className="btn-text" onClick={addHeader}>
                    <PlusSmallIcon /> 添加
                  </button>
                </div>
                {headers.length > 0 && (
                  <div className="header-list">
                    {headers.map((h, i) => (
                      <div key={i} className="header-row">
                        <input
                          className="form-input header-key-input"
                          placeholder="Header 名称"
                          value={h.key}
                          onChange={e => updateHeader(i, 'key', e.target.value)}
                        />
                        <input
                          className="form-input header-value-input"
                          placeholder="Header 值"
                          value={h.value}
                          onChange={e => updateHeader(i, 'value', e.target.value)}
                        />
                        <button
                          className="icon-btn danger"
                          onClick={() => removeHeader(i)}
                          title="删除"
                        >
                          <TrashIcon />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* 右栏：JSON 配置预览 */}
            <div className="mcp-config-right">
              <div className="mcp-config-preview-header">
                <label className="form-label">JSON 配置</label>
                <button
                  className="btn-primary btn-sm"
                  onClick={copyConfig}
                  title="复制 JSON 配置"
                >
                  {copied ? <CheckIcon /> : <CopyIcon />}
                  {copied ? '已复制' : '一键复制'}
                </button>
              </div>
              <div className="json-pane">
                <div className="json-gutter">
                  {jsonLines.map((_, i) => (
                    <span key={i}>{i + 1}</span>
                  ))}
                </div>
                <pre className="json-code">{jsonConfig}</pre>
              </div>
            </div>
          </div>
        </div>

        {/* 测试结果 */}
        {testError && (
          <div className="mcp-test-result error">
            <span className="mcp-test-status">测试失败</span>
            <span className="mcp-test-error-msg">{testError}</span>
          </div>
        )}
        {testResult && (
          <div className="mcp-test-result success">
            <div className="mcp-test-result-header">
              <span className="mcp-test-status">测试成功</span>
              <span className="mcp-test-count">共 {testResult.length} 个工具</span>
            </div>
            {testResult.length > 0 && (
              <div className="mcp-test-tools">
                {testResult.map(tool => (
                  <div key={tool.name} className="mcp-test-tool-item">
                    <span className="mcp-test-tool-name">{tool.name}</span>
                    {tool.description && (
                      <span className="mcp-test-tool-desc">{tool.description}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
