import { useEffect, useRef, useState } from 'react';
import { fetchSources, executeQuery, fetchSourceTables, fetchSystems, fetchEnvironments } from '../api/client';
import type { SystemInfo } from '../api/client';
import { toast } from '../components/Toast';
import type { SourceInfo, QueryResult } from '../api/types';
import './QueryConsole.css';

const SQL_SOURCE_TYPES = [
  'postgres', 'mysql', 'mssql', 'sqlite', 'clickhouse', 'snowflake',
  'oracle', 'oceanbase', 'trino', 'tidb', 'yugabytedb', 'cockroachdb',
  'firebird', 'singlestore', 'mindsdb',
];

function QueryIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="8" cy="3.5" rx="5.5" ry="2" />
      <path d="M2.5 3.5v9c0 1.1 2.46 2 5.5 2s5.5-.9 5.5-2v-9" />
      <path d="M2.5 8c0 1.1 2.46 2 5.5 2s5.5-.9 5.5-2" />
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

function ClockIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4.5V8l2.5 1.5" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 8a5.5 5.5 0 0 1 9.39-3.89L14 6" />
      <path d="M14 3v3h-3" />
      <path d="M13.5 8a5.5 5.5 0 0 1-9.39 3.89L2 10" />
      <path d="M2 13v-3h3" />
    </svg>
  );
}

function TableIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2.5" width="12" height="11" rx="1" />
      <path d="M2 6h12M2 9.5h12M6 2.5v11" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" />
    </svg>
  );
}

export default function QueryConsole() {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [selectedSource, setSelectedSource] = useState<string>('');
  const [selectedSystemId, setSelectedSystemId] = useState('');
  const [selectedEnvironment, setSelectedEnvironment] = useState('');
  const [systems, setSystems] = useState<SystemInfo[]>([]);
  const [environments, setEnvironments] = useState<string[]>(['dev', 'st', 'uat', 'prd']);
  const [sql, setSql] = useState('');
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [tables, setTables] = useState<string[]>([]);
  const [tablesLoading, setTablesLoading] = useState(false);
  const [tableFilter, setTableFilter] = useState('');
  const [history, setHistory] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('query_history') || '[]'); } catch { return []; }
  });
  const sqlRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetchSources()
      .then(setSources)
      .catch(() => toast.error('加载数据源失败'));
    fetchSystems()
      .then(setSystems)
      .catch(() => { /* 静默失败 */ });
    fetchEnvironments()
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setEnvironments(data);
        }
      })
      .catch(() => { /* 静默失败 */ });
  }, []);

  useEffect(() => {
    if (!selectedSource) {
      setTables([]);
      setTableFilter('');
      return;
    }
    setTablesLoading(true);
    setTableFilter('');
    setResult(null);
    fetchSourceTables(selectedSource)
      .then((res) => setTables(res.tables))
      .catch(() => {
        setTables([]);
        toast.error('加载表列表失败');
      })
      .finally(() => setTablesLoading(false));
  }, [selectedSource]);

  const handleRun = async () => {
    if (!selectedSource) {
      toast.warning('请先选择数据源');
      return;
    }
    if (!sql.trim()) {
      toast.warning('请输入 SQL 查询语句');
      return;
    }

    setLoading(true);
    try {
      const res = await executeQuery(selectedSource, sql);
      setResult(res);
      toast.success(`查询成功，返回 ${res.rowCount} 行数据`);

      const newHistory = [sql, ...history.filter((h) => h !== sql)].slice(0, 20);
      setHistory(newHistory);
      localStorage.setItem('query_history', JSON.stringify(newHistory));
    } catch (e: unknown) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      toast.error(`查询失败: ${errorMsg}`);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSystemChange = (sid: string) => {
    setSelectedSystemId(sid);
    setSelectedEnvironment('');
    setSelectedSource('');
  };

  const handleEnvironmentChange = (env: string) => {
    setSelectedEnvironment(env);
    setSelectedSource('');
  };

  const handleClearHistory = () => {
    setHistory([]);
    localStorage.removeItem('query_history');
    toast.success('已清空历史记录');
  };

  const handleTableClick = (tableName: string) => {
    const prev = sql;
    let next: string;
    let cursorPos: number;

    if (!prev.trim()) {
      next = `SELECT * FROM ${tableName} LIMIT 10;`;
      cursorPos = next.length;
    } else {
      const textarea = sqlRef.current;
      if (!textarea) {
        next = prev + ' ' + tableName;
        cursorPos = next.length;
      } else {
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const before = prev.slice(0, start);
        const needSpace = before.length > 0 && !/\s$/.test(before);
        const insert = (needSpace ? ' ' : '') + tableName;
        next = before + insert + prev.slice(end);
        cursorPos = (before + insert).length;
      }
    }

    setSql(next);
    requestAnimationFrame(() => {
      const ta = sqlRef.current;
      if (ta) {
        ta.focus();
        ta.setSelectionRange(cursorPos, cursorPos);
      }
    });
  };

  const sqlSources = sources.filter((s) => {
    if (!SQL_SOURCE_TYPES.includes(s.type)) return false;
    if (selectedSystemId && String(s.systemId || '') !== selectedSystemId) return false;
    if (selectedEnvironment && String(s.environment || '') !== selectedEnvironment) return false;
    return true;
  });
  const filteredTables = tableFilter.trim()
    ? tables.filter((t) => t.toLowerCase().includes(tableFilter.trim().toLowerCase()))
    : tables;

  return (
    <div className="query-console fade-in">
      <div className="page-header">
        <div className="page-title-group">
          <span className="page-eyebrow">数据查询</span>
          <h1 className="page-title">
            <span className="title-icon">
              <QueryIcon />
            </span>
            查询控制台
          </h1>
        </div>
      </div>

      <div className="qc-layout">
        {/* 表浏览器侧边栏 — 固定显示,未选数据源时提示选择 */}
        <aside className="qc-sidebar card">
          <div className="qc-sidebar-header">
            <span className="section-label qc-sidebar-label">表</span>
            {!tablesLoading && tables.length > 0 && (
              <span className="qc-table-count">{tables.length}</span>
            )}
          </div>

          {tables.length > 0 && (
            <div className="qc-search">
              <span className="qc-search-icon"><SearchIcon /></span>
              <input
                className="qc-search-input"
                type="text"
                value={tableFilter}
                onChange={(e) => setTableFilter(e.target.value)}
                placeholder="筛选表名..."
                aria-label="筛选表名"
              />
            </div>
          )}

          <div className="qc-table-list">
            {tablesLoading ? (
              <div className="qc-sidebar-state">
                <span className="spinner qc-sidebar-spinner" />
                <span className="qc-sidebar-state-text">加载表列表...</span>
              </div>
            ) : !selectedSource ? (
              <div className="qc-sidebar-empty">
                <span className="qc-sidebar-empty-icon"><TableIcon /></span>
                <span className="qc-sidebar-empty-title">暂无表</span>
                <span className="qc-sidebar-empty-hint">请先选择数据源</span>
              </div>
            ) : tables.length === 0 ? (
              <div className="qc-sidebar-empty">
                <span className="qc-sidebar-empty-icon"><TableIcon /></span>
                <span className="qc-sidebar-empty-title">暂无表</span>
                <span className="qc-sidebar-empty-hint">该数据源未返回任何表</span>
              </div>
            ) : filteredTables.length === 0 ? (
              <div className="qc-sidebar-empty">
                <span className="qc-sidebar-empty-icon"><SearchIcon /></span>
                <span className="qc-sidebar-empty-title">无匹配的表</span>
                <span className="qc-sidebar-empty-hint">调整筛选条件试试</span>
              </div>
            ) : (
              filteredTables.map((t) => (
                <button
                  key={t}
                  type="button"
                  className="qc-table-item"
                  onClick={() => handleTableClick(t)}
                  title={`插入表名: ${t}`}
                >
                  <span className="qc-table-item-icon"><TableIcon /></span>
                  <span className="qc-table-name">{t}</span>
                </button>
              ))
            )}
          </div>
        </aside>

        {/* 右侧主区域 */}
        <div className="qc-main">
          {/* 工作区：控制条 + 编辑器 合并为单卡片 */}
          <div className="qc-workspace card">
            <div className="qc-control-bar">
              <div className="qc-control-group">
                {systems.length > 0 && (
                  <div className="form-group qc-field">
                    <label className="form-label">系统编号</label>
                    <select
                      className="form-select"
                      value={selectedSystemId}
                      onChange={(e) => handleSystemChange(e.target.value)}
                    >
                      <option value="">全部</option>
                      {systems.map((sys) => (
                        <option key={sys.systemId} value={sys.systemId}>
                          {sys.systemId}（{sys.sourceCount} 个数据源）
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="form-group qc-field">
                  <label className="form-label">环境</label>
                  <select
                    className="form-select"
                    value={selectedEnvironment}
                    onChange={(e) => handleEnvironmentChange(e.target.value)}
                  >
                    <option value="">全部</option>
                    {environments.map((env) => (
                      <option key={env} value={env}>{env}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group qc-field">
                  <label className="form-label">数据源</label>
                  <select
                    className="form-select"
                    value={selectedSource}
                    onChange={(e) => setSelectedSource(e.target.value)}
                  >
                    <option value="">选择数据源...</option>
                    {sqlSources.map((s) => (
                      <option key={s.name} value={s.name}>
                        {s.name} ({s.type})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group qc-field">
                  <div className="qc-history-header">
                    <label className="form-label qc-history-label">
                      <ClockIcon />
                      历史记录
                    </label>
                    {history.length > 0 && (
                      <button
                        type="button"
                        className="qc-clear-btn"
                        onClick={handleClearHistory}
                      >
                        清空
                      </button>
                    )}
                  </div>
                  <select
                    className="form-select"
                    value=""
                    onChange={(e) => {
                      if (e.target.value) {
                        setSql(e.target.value);
                        toast.info('已加载历史查询');
                      }
                    }}
                  >
                    <option value="">选择历史查询...</option>
                    {history.map((h, idx) => (
                      <option key={idx} value={h}>
                        {h.length > 60 ? h.slice(0, 60) + '...' : h}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <button
                type="button"
                className="btn-primary qc-run-btn"
                onClick={handleRun}
                disabled={loading}
                title="Ctrl + Enter"
              >
                {loading ? (
                  <>
                    <span className="spinner qc-run-spinner" />
                    执行中
                  </>
                ) : (
                  <>
                    <PlayIcon />
                    执行查询
                  </>
                )}
              </button>
            </div>

            <div className="qc-editor-body">
              <textarea
                ref={sqlRef}
                className="qc-sql-input"
                value={sql}
                onChange={(e) => setSql(e.target.value)}
                placeholder="SELECT * FROM your_table LIMIT 10;"
                spellCheck={false}
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    e.preventDefault();
                    handleRun();
                  }
                }}
              />
              <span className="qc-shortcut-hint">
                <span className="qc-kbd">Ctrl</span>
                <span className="qc-kbd-plus">+</span>
                <span className="qc-kbd">Enter</span>
              </span>
            </div>
          </div>

          {/* 结果区 */}
          {result ? (
            <div className="qc-results card">
              <div className="qc-result-header">
                <div className="qc-result-meta">
                  <span className="qc-meta-count">{result.rowCount} 行</span>
                  <span className="qc-meta-sep" />
                  <span className="qc-meta-time">{result.durationMs}ms</span>
                  {result.columns.length > 0 && (
                    <>
                      <span className="qc-meta-sep" />
                      <span className="qc-meta-cols">{result.columns.length} 列</span>
                    </>
                  )}
                </div>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={handleRun}
                  disabled={loading}
                  title="重新执行查询"
                  aria-label="重新执行查询"
                >
                  <RefreshIcon />
                </button>
              </div>
              <div className="qc-table-wrapper">
                <table className="qc-result-table">
                  <thead>
                    <tr>
                      <th className="qc-row-num-col">#</th>
                      {result.columns.map((col) => (
                        <th key={col}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.length === 0 ? (
                      <tr>
                        <td className="qc-empty-row" colSpan={result.columns.length + 1}>
                          查询返回 0 行数据
                        </td>
                      </tr>
                    ) : (
                      result.rows.map((row, i) => (
                        <tr key={i}>
                          <td className="qc-row-num-col">{i + 1}</td>
                          {row.map((cell, j) => (
                            <td key={j}>
                              {cell != null ? String(cell) : <span className="qc-null">NULL</span>}
                            </td>
                          ))}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="qc-results-empty card">
              <span className="qc-empty-icon"><QueryIcon /></span>
              <p className="qc-empty-text">执行查询后，结果将显示在此处</p>
              <p className="qc-empty-hint">选择数据源 · 编写 SQL · 按 Ctrl+Enter 运行</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
