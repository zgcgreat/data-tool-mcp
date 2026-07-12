import { useEffect, useState } from 'react';
import { fetchTools, getTool, invokeTool, deleteTool } from '../api/client';
import { toast } from '../components/Toast';
import type { ToolInfo, ToolParam } from '../api/types';
import './Tools.css';

type ToolCategory = 'oneclick' | 'parameterized' | 'sql';

const CATEGORY_LABELS: Record<ToolCategory, string> = {
  oneclick: '一键执行',
  parameterized: '参数输入',
  sql: 'SQL 编辑',
};

function ToolIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <path d="M14.5 1.5a3 3 0 00-4.24 0L7.4 4.36a.75.75 0 101.06 1.06l2.86-2.86a1.5 1.5 0 012.12 2.12l-2.86 2.86a.75.75 0 101.06 1.06l2.86-2.86a3 3 0 000-4.24z" />
      <path d="M7.3 7.42l-4.33 4.34a1.5 1.5 0 00-.42 1.06l-.3 2.36a.5.5 0 00.57.57l2.36-.3a1.5 1.5 0 001.06-.42l4.34-4.33-3.28-3.28z" fillOpacity="0.85" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
      <path d="M4 2.75v10.5a.5.5 0 0 0 .76.43l8.25-5.25a.5.5 0 0 0 0-.86L4.76 2.32A.5.5 0 0 0 4 2.75z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 4h10M6.5 4V2.5h3V4M5 4l.5 9a1 1 0 001 1h3a1 1 0 001-1L11 4" />
    </svg>
  );
}

function BoltIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
      <path d="M9 1L2.5 9h4L6 15l6.5-8h-4L9 1z" />
    </svg>
  );
}

function ChevronRight() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 4l4 4-4 4" />
    </svg>
  );
}

export default function Tools() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTool, setSelectedTool] = useState<ToolInfo | null>(null);
  const [toolDetail, setToolDetail] = useState<ToolInfo | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [invokeResult, setInvokeResult] = useState<string>('');
  const [invoking, setInvoking] = useState(false);
  const [filterSource, setFilterSource] = useState<string>('');

  useEffect(() => {
    loadTools();
  }, []);

  const loadTools = async () => {
    try {
      const data = await fetchTools();
      setTools(data);
    } catch (error) {
      toast.error('加载工具列表失败');
      console.error('Failed to load tools:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectTool = async (tool: ToolInfo) => {
    setSelectedTool(tool);
    setToolDetail(null);
    setLoadingDetail(true);
    setInvokeResult('');
    try {
      const detail = await getTool(tool.name);
      setToolDetail(detail);
    } catch (error) {
      toast.error('加载工具详情失败');
      console.error('Failed to load tool details:', error);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleInvoke = async (tool: ToolInfo, params: Record<string, unknown>) => {
    setInvoking(true);
    setInvokeResult('');
    try {
      const result = await invokeTool(tool.name, params);
      setInvokeResult(JSON.stringify(result, null, 2));
      toast.success('工具调用成功');
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : '未知错误';
      setInvokeResult(`错误: ${errorMsg}`);
      toast.error(`调用失败: ${errorMsg}`);
    } finally {
      setInvoking(false);
    }
  };

  const handleDelete = async (name: string) => {
    if (!confirm(`确定要删除工具 "${name}" 吗？`)) return;
    try {
      await deleteTool(name);
      setTools(prev => prev.filter(t => t.name !== name));
      if (selectedTool?.name === name) {
        setSelectedTool(null);
        setToolDetail(null);
      }
      toast.success(`已删除工具 "${name}"`);
    } catch (error) {
      toast.error('删除失败');
      console.error('Failed to delete tool:', error);
    }
  };

  const sourceNames = Array.from(new Set(tools.map(t => t.source).filter(Boolean))) as string[];
  const filteredTools = filterSource ? tools.filter(t => t.source === filterSource) : tools;

  const grouped: Record<ToolCategory, ToolInfo[]> = { oneclick: [], parameterized: [], sql: [] };
  filteredTools.forEach(t => {
    const cat = (t.category || 'parameterized') as ToolCategory;
    grouped[cat].push(t);
  });

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        <div className="loading-text">加载中...</div>
      </div>
    );
  }

  return (
    <div className="tools-page fade-in">
      <div className="page-header">
        <div className="page-title-group">
          <span className="page-eyebrow">工具管理</span>
          <h1 className="page-title">
            <span className="title-icon"><ToolIcon /></span>
            工具
          </h1>
        </div>
        {sourceNames.length > 0 && (
          <select
            className="form-select tools-filter"
            value={filterSource}
            onChange={e => setFilterSource(e.target.value)}
            style={{ width: 'auto', minWidth: '200px' }}
          >
            <option value="">全部数据源 ({tools.length})</option>
            {sourceNames.map(src => {
              const count = tools.filter(t => t.source === src).length;
              return <option key={src} value={src}>{src} ({count})</option>;
            })}
          </select>
        )}
      </div>

      <div className="tools-layout">
        <div className="tools-list">
          {filteredTools.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><ToolIcon /></div>
              <h3>还没有工具</h3>
              <p>添加数据源后会自动生成工具</p>
            </div>
          ) : (
            <>
              {(['oneclick', 'parameterized', 'sql'] as ToolCategory[]).map(cat => {
                if (grouped[cat].length === 0) return null;
                return (
                  <div key={cat} className="tool-group">
                    <div className={`tool-group-header cat-${cat}`}>
                      <span className="tool-group-label">{CATEGORY_LABELS[cat]}</span>
                      <span className="tool-group-count">{grouped[cat].length}</span>
                    </div>
                    {grouped[cat].map((tool, idx) => (
                      <div
                        key={tool.name}
                        className={`tool-list-item cat-${cat} ${selectedTool?.name === tool.name ? 'selected' : ''}`}
                        style={{ animationDelay: `${idx * 0.03}s` }}
                        role="button"
                        tabIndex={0}
                        onClick={() => handleSelectTool(tool)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            handleSelectTool(tool);
                          }
                        }}
                      >
                        <div className="tool-list-main">
                          <div className="tool-list-name">{tool.name}</div>
                          {tool.description && (
                            <div className="tool-list-desc">
                              {tool.description.length > 52 ? tool.description.slice(0, 52) + '…' : tool.description}
                            </div>
                          )}
                        </div>
                        <button
                          className="icon-btn danger tool-delete"
                          onClick={(e) => { e.stopPropagation(); handleDelete(tool.name); }}
                          title="删除"
                          aria-label={`删除工具 ${tool.name}`}
                        >
                          <TrashIcon />
                        </button>
                      </div>
                    ))}
                  </div>
                );
              })}
            </>
          )}
        </div>

        <div className="tool-detail">
          {selectedTool ? (
            loadingDetail ? (
              <div className="page-loading">
                <div className="spinner" />
                <div className="loading-text">加载中...</div>
              </div>
            ) : (
              <ToolDetail
                tool={toolDetail || selectedTool}
                onInvoke={handleInvoke}
                invokeResult={invokeResult}
                invoking={invoking}
              />
            )
          ) : (
            <div className="empty-state">
              <div className="empty-icon"><ToolIcon /></div>
              <h3>选择一个工具</h3>
              <p>从左侧列表选择工具查看详情并调用</p>
              <div className="tool-legend">
                <div className="legend-item">
                  <span className="legend-dot cat-oneclick" />
                  <span className="legend-text">一键执行 — 无需输入</span>
                </div>
                <div className="legend-item">
                  <span className="legend-dot cat-parameterized" />
                  <span className="legend-text">参数输入 — 填写表单</span>
                </div>
                <div className="legend-item">
                  <span className="legend-dot cat-sql" />
                  <span className="legend-text">SQL 编辑 — 编写语句</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ToolDetail({
  tool,
  onInvoke,
  invokeResult,
  invoking,
}: {
  tool: ToolInfo;
  onInvoke: (tool: ToolInfo, params: Record<string, unknown>) => void;
  invokeResult: string;
  invoking: boolean;
}) {
  const category = (tool.category || 'parameterized') as ToolCategory;

  const paramDefs: ToolParam[] = tool.inputSchema?.properties
    ? Object.entries(tool.inputSchema.properties).map(([name, schema]) => ({
        name,
        type: schema.type || 'string',
        description: schema.description || '',
        required: tool.inputSchema?.required?.includes(name) || false,
        default: schema.default,
        enum: schema.enum,
      }))
    : [];

  return (
    <div className="detail-content fade-in">
      <div className="detail-header">
        <h2 className="detail-title">{tool.name}</h2>
        <div className="detail-badges">
          <span className={`badge cat-${category}`}>{CATEGORY_LABELS[category]}</span>
          <span className="badge badge-neutral">{tool.type}</span>
          {tool.source && <span className="badge badge-accent">{tool.source}</span>}
        </div>
      </div>

      {tool.description && (
        <div className="detail-section">
          <div className="section-label">描述</div>
          <p className="detail-desc">{tool.description}</p>
        </div>
      )}

      {category === 'oneclick' && (
        <OneClickPanel tool={tool} paramDefs={paramDefs} onInvoke={onInvoke} invoking={invoking} />
      )}
      {category === 'parameterized' && (
        <ParameterizedPanel tool={tool} paramDefs={paramDefs} onInvoke={onInvoke} invoking={invoking} />
      )}
      {category === 'sql' && (
        <SqlPanel tool={tool} onInvoke={onInvoke} invoking={invoking} />
      )}

      {invokeResult && (
        <div className="detail-section">
          <div className="section-label">执行结果</div>
          <pre className="result-output">{invokeResult}</pre>
        </div>
      )}
    </div>
  );
}

function OneClickPanel({
  tool, paramDefs, onInvoke, invoking,
}: {
  tool: ToolInfo;
  paramDefs: ToolParam[];
  onInvoke: (tool: ToolInfo, params: Record<string, unknown>) => void;
  invoking: boolean;
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [params, setParams] = useState<Record<string, unknown>>({});

  useEffect(() => {
    const defaults: Record<string, unknown> = {};
    paramDefs.forEach(p => { if (p.default !== undefined) defaults[p.name] = p.default; });
    setParams(defaults);
  }, [tool.name]);

  const hasOptionalParams = paramDefs.length > 0;

  const handleExecute = () => {
    const finalParams: Record<string, unknown> = {};
    paramDefs.forEach(def => {
      const value = params[def.name];
      if (value !== undefined && value !== '') {
        if (def.type === 'number' || def.type === 'integer') {
          finalParams[def.name] = Number(value);
        } else if (def.type === 'boolean') {
          finalParams[def.name] = value === true || value === 'true';
        } else {
          finalParams[def.name] = value;
        }
      } else if (def.default !== undefined) {
        finalParams[def.name] = def.default;
      }
    });
    onInvoke(tool, finalParams);
  };

  return (
    <div className="detail-section">
      <div className="section-label">执行</div>
      <div className="oneclick-panel">
        <div className="oneclick-hint">
          <span className="oneclick-hint-icon"><BoltIcon /></span>
          <span>此工具无需输入参数，直接点击执行即可</span>
        </div>
        {hasOptionalParams && (
          <button className="advanced-toggle" onClick={() => setShowAdvanced(!showAdvanced)}>
            <ChevronRight /> {showAdvanced ? '收起可选参数' : '显示可选参数'}
          </button>
        )}
        {hasOptionalParams && showAdvanced && (
          <div className="params-form">
            {paramDefs.map(def => (
              <div key={def.name} className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">{def.name}</label>
                {def.description && <span className="param-hint">{def.description}</span>}
                <input
                  className="form-input"
                  type={def.type === 'number' || def.type === 'integer' ? 'number' : 'text'}
                  value={params[def.name] !== undefined ? String(params[def.name]) : ''}
                  onChange={e => setParams(prev => ({ ...prev, [def.name]: e.target.value }))}
                  placeholder={def.default !== undefined ? `默认: ${def.default}` : ''}
                />
              </div>
            ))}
          </div>
        )}
        <button className="btn-primary oneclick-btn" onClick={handleExecute} disabled={invoking}>
          {invoking ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2, borderTopColor: '#fff' }} /> : <PlayIcon />}
          {invoking ? '执行中...' : '立即执行'}
        </button>
      </div>
    </div>
  );
}

function ParameterizedPanel({
  tool, paramDefs, onInvoke, invoking,
}: {
  tool: ToolInfo;
  paramDefs: ToolParam[];
  onInvoke: (tool: ToolInfo, params: Record<string, unknown>) => void;
  invoking: boolean;
}) {
  const [params, setParams] = useState<Record<string, unknown>>({});

  useEffect(() => {
    const defaults: Record<string, unknown> = {};
    paramDefs.forEach(p => { if (p.default !== undefined) defaults[p.name] = p.default; });
    setParams(defaults);
  }, [tool.name]);

  const handleExecute = () => {
    const finalParams: Record<string, unknown> = {};
    paramDefs.forEach(def => {
      const value = params[def.name];
      if (value !== undefined && value !== '') {
        if (def.type === 'number' || def.type === 'integer') {
          finalParams[def.name] = Number(value);
        } else if (def.type === 'boolean') {
          finalParams[def.name] = value === true || value === 'true';
        } else {
          finalParams[def.name] = value;
        }
      } else if (def.default !== undefined) {
        finalParams[def.name] = def.default;
      }
    });
    onInvoke(tool, finalParams);
  };

  const handleUseExample = () => {
    const example: Record<string, unknown> = {};
    paramDefs.forEach(def => {
      if (def.default !== undefined) example[def.name] = def.default;
      else if (def.enum && def.enum.length > 0) example[def.name] = def.enum[0];
      else if (def.type === 'string') example[def.name] = `example_${def.name}`;
      else if (def.type === 'number' || def.type === 'integer') example[def.name] = 1;
      else if (def.type === 'boolean') example[def.name] = false;
    });
    setParams(example);
    toast.info('已填入示例参数');
  };

  const requiredParams = paramDefs.filter(p => p.required);
  const optionalParams = paramDefs.filter(p => !p.required);
  const missingRequired = requiredParams.some(p => params[p.name] === undefined || params[p.name] === '');

  return (
    <div className="detail-section">
      <div className="params-section-header">
        <div className="section-label" style={{ marginBottom: 0 }}>参数</div>
        <button className="btn-ghost" onClick={handleUseExample} style={{ padding: '4px 10px', fontSize: 12 }}>填入示例</button>
      </div>

      {requiredParams.length > 0 && (
        <div className="params-form">
          {requiredParams.map(def => (
            <div key={def.name} className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">
                {def.name}
                {def.required && <span className="required-mark">*</span>}
              </label>
              {def.description && <span className="param-hint">{def.description}</span>}
              {def.enum ? (
                <select
                  className="form-select"
                  value={params[def.name] !== undefined ? String(params[def.name]) : ''}
                  onChange={e => setParams(prev => ({ ...prev, [def.name]: e.target.value }))}
                >
                  <option value="">选择...</option>
                  {def.enum.map(opt => <option key={String(opt)} value={String(opt)}>{String(opt)}</option>)}
                </select>
              ) : def.type === 'boolean' ? (
                <select
                  className="form-select"
                  value={params[def.name] !== undefined ? String(params[def.name]) : ''}
                  onChange={e => setParams(prev => ({ ...prev, [def.name]: e.target.value === 'true' }))}
                >
                  <option value="">选择...</option>
                  <option value="true">是</option>
                  <option value="false">否</option>
                </select>
              ) : (
                <input
                  className="form-input"
                  type={def.type === 'number' || def.type === 'integer' ? 'number' : 'text'}
                  value={params[def.name] !== undefined ? String(params[def.name]) : ''}
                  onChange={e => setParams(prev => ({ ...prev, [def.name]: e.target.value }))}
                  placeholder={`请输入${def.name}`}
                />
              )}
            </div>
          ))}
        </div>
      )}

      {optionalParams.length > 0 && (
        <details className="optional-params">
          <summary>可选参数 ({optionalParams.length})</summary>
          <div className="params-form">
            {optionalParams.map(def => (
              <div key={def.name} className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">{def.name}</label>
                {def.description && <span className="param-hint">{def.description}</span>}
                <input
                  className="form-input"
                  type={def.type === 'number' || def.type === 'integer' ? 'number' : 'text'}
                  value={params[def.name] !== undefined ? String(params[def.name]) : ''}
                  onChange={e => setParams(prev => ({ ...prev, [def.name]: e.target.value }))}
                  placeholder={def.default !== undefined ? `默认: ${def.default}` : ''}
                />
              </div>
            ))}
          </div>
        </details>
      )}

      <button className="btn-primary" onClick={handleExecute} disabled={invoking || missingRequired}>
        {invoking ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2, borderTopColor: '#fff' }} /> : <PlayIcon />}
        {invoking ? '执行中...' : '执行工具'}
      </button>
      {missingRequired && (
        <p className="required-warning">请填写所有必填参数（* 标记）后再执行</p>
      )}
    </div>
  );
}

function SqlPanel({
  tool, onInvoke, invoking,
}: {
  tool: ToolInfo;
  onInvoke: (tool: ToolInfo, params: Record<string, unknown>) => void;
  invoking: boolean;
}) {
  const [sql, setSql] = useState('');

  const handleExecute = () => {
    if (!sql.trim()) { toast.error('请输入 SQL 语句'); return; }
    onInvoke(tool, { sql });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleExecute();
    }
  };

  return (
    <div className="detail-section">
      <div className="params-section-header">
        <div className="section-label" style={{ marginBottom: 0 }}>SQL 语句</div>
        <span className="param-hint">Ctrl+Enter 执行</span>
      </div>
      <textarea
        className="form-textarea sql-textarea"
        value={sql}
        onChange={e => setSql(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={10}
        placeholder={'-- 输入要执行的 SQL 语句\nSELECT * FROM ...'}
        spellCheck={false}
      />
      <button className="btn-primary sql-btn" onClick={handleExecute} disabled={invoking}>
        {invoking ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2, borderTopColor: '#fff' }} /> : <PlayIcon />}
        {invoking ? '执行中...' : '执行 SQL'}
      </button>
    </div>
  );
}
