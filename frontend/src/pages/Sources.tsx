import { useEffect, useState } from 'react';
import { fetchSources, fetchSource, fetchSourceTypes, createSource, updateSource, deleteSource, testSourceConnection, fetchSystems, fetchEnvironments } from '../api/client';
import { toast } from '../components/Toast';
import { ConfirmDialog } from '../components/ConfirmDialog';
import type { SystemInfo } from '../api/client';
import type { SourceInfo, SourceTypeSchema } from '../api/types';
import './Sources.css';

// --- 类型配色系统 ---
const TYPE_COLORS: Record<string, { color: string; bg: string; border: string; label: string }> = {
  postgresql: { color: '#1f4ea8', bg: 'rgba(47,111,219,0.10)', border: 'rgba(47,111,219,0.30)', label: 'PostgreSQL' },
  postgres:   { color: '#1f4ea8', bg: 'rgba(47,111,219,0.10)', border: 'rgba(47,111,219,0.30)', label: 'PostgreSQL' },
  mysql:      { color: '#a85a18', bg: 'rgba(232,135,58,0.12)', border: 'rgba(232,135,58,0.32)', label: 'MySQL' },
  tdsql:      { color: '#0e8a7a', bg: 'rgba(14,138,122,0.12)', border: 'rgba(14,138,122,0.32)', label: 'TDSQL' },
  mssql:      { color: '#6b32b8', bg: 'rgba(124,58,237,0.10)', border: 'rgba(124,58,237,0.30)', label: 'SQL Server' },
  sqlite:     { color: '#0e7c8a', bg: 'rgba(14,124,138,0.10)', border: 'rgba(14,124,138,0.30)', label: 'SQLite' },
  oracle:     { color: '#a8341a', bg: 'rgba(220,80,40,0.10)', border: 'rgba(220,80,40,0.30)', label: 'Oracle' },
  default:    { color: '#475569', bg: 'rgba(100,116,139,0.10)', border: 'rgba(100,116,139,0.28)', label: '数据库' },
};

function typeColor(type: string) {
  const t = type.toLowerCase();
  for (const key of Object.keys(TYPE_COLORS)) {
    if (t.includes(key)) return TYPE_COLORS[key];
  }
  return TYPE_COLORS.default;
}

// --- 从 source 配置字段提取连接摘要 ---
function extractConnectionSummary(source: SourceInfo): string | null {
  const host = source.host as string | undefined;
  const port = source.port as number | string | undefined;
  const database = (source.database || source.dbname || source.path) as string | undefined;
  const parts: string[] = [];
  if (host) parts.push(host);
  if (port) parts.push(String(port));
  if (parts.length > 0 && database) return `${parts.join(':')} · ${database}`;
  if (database) return database;
  if (parts.length > 0) return parts.join(':');
  return null;
}

function DatabaseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <ellipse cx="8" cy="3.5" rx="5.5" ry="2" />
      <path d="M2.5 3.5v9c0 1.1 2.46 2 5.5 2s5.5-.9 5.5-2v-9" />
      <path d="M2.5 8c0 1.1 2.46 2 5.5 2s5.5-.9 5.5-2" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M8 3v10M3 8h10" />
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

function EditIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11.5 2.5l2 2L5 13l-2.5.5L3 11l8.5-8.5z" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  );
}

export default function Sources() {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [sourceTypes, setSourceTypes] = useState<Record<string, SourceTypeSchema>>({});
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingSource, setEditingSource] = useState<SourceInfo | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; latency: number; error: string | null }>>({});
  // 已应用的筛选条件(点击"查询"后更新,筛选不实时生效)
  const [appliedFilters, setAppliedFilters] = useState({ systemId: '', environment: '' });
  // 查询中加载态(点击"查询"后短暂显示页面加载效果)
  const [querying, setQuerying] = useState(false);
  const [selectedSystemId, setSelectedSystemId] = useState('');
  const [systems, setSystems] = useState<SystemInfo[]>([]);
  const [environments, setEnvironments] = useState<string[]>(['dev', 'st', 'uat', 'prd']);
  const [selectedEnvironment, setSelectedEnvironment] = useState('');
  // 列表排序
  type SortKey = 'name' | 'systemId' | 'environment' | 'toolCount' | 'type';
  type SortDir = 'asc' | 'desc';
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  // 分页: 列表展示，默认每页 10 条
  const [currentPage, setCurrentPage] = useState(1);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const pageSize = 10;

  useEffect(() => {
    loadData();
    loadSystems();
    loadEnvironments();
  }, []);

  // 应用筛选条件后(点击查询)重置到第 1 页
  useEffect(() => {
    setCurrentPage(1);
  }, [appliedFilters]);

  const loadData = async () => {
    try {
      const [sourcesData, typesData] = await Promise.all([fetchSources(), fetchSourceTypes()]);
      setSources(sourcesData);
      setSourceTypes(typesData);
    } catch (error) {
      toast.error('加载数据失败');
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadSystems = async () => {
    try {
      const data = await fetchSystems();
      setSystems(data);
    } catch {
      // 静默失败
    }
  };

  const loadEnvironments = async () => {
    try {
      const data = await fetchEnvironments();
      if (Array.isArray(data) && data.length > 0) {
        setEnvironments(data);
      }
    } catch {
      // 静默失败, 保留预设列表
    }
  };

  const handleTest = async (name: string) => {
    setTesting(name);
    try {
      const result = await testSourceConnection(name);
      setTestResults(prev => ({ ...prev, [name]: result }));
      if (result.ok) {
        toast.success(`连接成功 (${result.latency}ms)`);
      } else {
        toast.error(`连接失败: ${result.error}`);
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : '连接失败';
      setTestResults(prev => ({ ...prev, [name]: { ok: false, latency: 0, error: errorMsg } }));
      toast.error(errorMsg);
    } finally {
      setTesting(null);
    }
  };

  // 点击编辑: 调用详情接口获取含密码密文/明文的完整配置, 而非直接用列表项(列表项密码是 ******** 占位)
  const handleEditClick = async (name: string) => {
    try {
      const detail = await fetchSource(name);
      setEditingSource(detail);
    } catch (error) {
      const msg = error instanceof Error ? error.message : '加载数据源详情失败';
      toast.error(msg);
    }
  };

  const handleDelete = (name: string) => {
    setDeleteTarget(name);
  };

  const confirmDelete = async () => {
    const name = deleteTarget;
    setDeleteTarget(null);
    if (!name) return;
    try {
      await deleteSource(name);
      setSources(prev => prev.filter(s => s.name !== name));
      setTestResults(prev => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
      toast.success(`已删除数据源 "${name}"`);
    } catch (error) {
      const msg = error instanceof Error ? error.message : '删除失败';
      toast.error(msg);
    }
  };

  const handleCreate = async (data: { name: string; type: string; [key: string]: unknown }) => {
    try {
      const result = await createSource(data);
      setShowModal(false);
      const toolCount = result.toolCount ?? 0;
      if (toolCount > 0) {
        toast.success(`已创建数据源 "${data.name}"，自动生成 ${toolCount} 个工具`);
      } else {
        toast.success(`已创建数据源 "${data.name}"`);
      }
      loadData();
    } catch (error) {
      const msg = error instanceof Error ? error.message : '创建失败';
      toast.error(msg);
      throw error;
    }
  };

  const handleEdit = async (data: { name: string; type: string; [key: string]: unknown }) => {
    try {
      await updateSource(data.name, data);
      setEditingSource(null);
      toast.success(`已更新数据源 "${data.name}"`);
      loadData();
    } catch (error) {
      const msg = error instanceof Error ? error.message : '更新失败';
      toast.error(msg);
      throw error;
    }
  };

  // 按已应用的筛选条件(系统+环境)过滤数据源
  const filteredSources = sources.filter(s => {
    if (appliedFilters.systemId && String(s.systemId || '') !== appliedFilters.systemId) return false;
    if (appliedFilters.environment && String(s.environment || '') !== appliedFilters.environment) return false;
    return true;
  });

  // 排序后的数据源列表
  const sortedSources = [...filteredSources].sort((a, b) => {
    const dir = sortDir === 'asc' ? 1 : -1;
    let av: string | number = '';
    let bv: string | number = '';
    switch (sortKey) {
      case 'name':
        av = String(a.name || ''); bv = String(b.name || ''); break;
      case 'systemId':
        av = String(a.systemId || ''); bv = String(b.systemId || ''); break;
      case 'environment':
        av = String(a.environment || ''); bv = String(b.environment || ''); break;
      case 'toolCount':
        av = Number(a.toolCount || 0); bv = Number(b.toolCount || 0); break;
      case 'type':
        av = String(a.type || ''); bv = String(b.type || ''); break;
    }
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return 0;
  });

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const sortIndicator = (key: SortKey) => {
    if (sortKey !== key) return '';
    return sortDir === 'asc' ? ' \u2191' : ' \u2193';
  };

  // 点击"查询"按钮：短暂显示加载效果后应用筛选条件
  const handleSearch = () => {
    setQuerying(true);
    // 给浏览器一帧渲染加载层,再用 setTimeout 应用筛选(纯前端过滤,无网络请求)
    setTimeout(() => {
      setAppliedFilters({
        systemId: selectedSystemId,
        environment: selectedEnvironment,
      });
      setQuerying(false);
    }, 300);
  };

  // 分页计算（边界保护：删除后当前页可能超出范围）
  const totalPages = Math.max(1, Math.ceil(sortedSources.length / pageSize));
  const safePage = Math.min(currentPage, totalPages);
  const pageStart = (safePage - 1) * pageSize;
  const pagedSources = sortedSources.slice(pageStart, pageStart + pageSize);

  const goToPage = (page: number) => {
    setCurrentPage(Math.max(1, Math.min(page, totalPages)));
  };

  return (
    <div className="sources-page fade-in">
      <div className="page-header">
        <div className="page-title-group">
          <span className="page-eyebrow">资源管理</span>
          <h1 className="page-title">
            <span className="title-icon"><DatabaseIcon /></span>
            数据源
            {sources.length > 0 && <span className="title-count">{sources.length}</span>}
          </h1>
        </div>
        <div className="page-header-actions">
          {systems.length > 0 && (
            <label className="filter-field">
              <span className="filter-label">系统</span>
              <select
                className="form-select tools-filter"
                value={selectedSystemId}
                onChange={e => setSelectedSystemId(e.target.value)}
              >
                <option value="">全部</option>
                {systems.map(sys => (
                  <option key={sys.systemId} value={sys.systemId}>
                    {sys.systemId}（{sys.sourceCount} 个数据源）
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="filter-field">
            <span className="filter-label">环境</span>
            <select
              className="form-select tools-filter"
              value={selectedEnvironment}
              onChange={e => setSelectedEnvironment(e.target.value)}
            >
              <option value="">全部</option>
              {environments.map(env => <option key={env} value={env}>{env}</option>)}
            </select>
          </label>
          <button className="btn-primary" onClick={handleSearch} title="按当前筛选条件查询">
            查询
          </button>
          <button className="btn-secondary" onClick={() => setShowModal(true)}>
            <PlusIcon /> 添加数据源
          </button>
        </div>
      </div>

      {loading ? (
        <div className="page-loading page-loading-inline">
          <div className="spinner" />
          <div className="loading-text">加载中...</div>
        </div>
      ) : filteredSources.length === 0 ? (
        <div className="empty-state card">
          <div className="empty-icon"><DatabaseIcon /></div>
          <h3>还没有数据源</h3>
          <p>添加数据源后，系统会自动生成对应的工具</p>
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            <PlusIcon /> 添加第一个数据源
          </button>
        </div>
      ) : (
        <>
          <div className="sources-table-wrap card">
            <div className="sources-table-scroll">
              <table className="sources-table">
                <thead>
                  <tr>
                    <th className="col-type sortable" onClick={() => handleSort('type')}>类型{sortIndicator('type')}</th>
                    <th className="col-name sortable" onClick={() => handleSort('name')}>名称{sortIndicator('name')}</th>
                    <th className="col-system sortable" onClick={() => handleSort('systemId')}>系统{sortIndicator('systemId')}</th>
                    <th className="col-env sortable" onClick={() => handleSort('environment')}>环境{sortIndicator('environment')}</th>
                    <th className="col-conn">连接</th>
                    <th className="col-status">状态</th>
                    <th className="col-tools sortable" onClick={() => handleSort('toolCount')}>工具{sortIndicator('toolCount')}</th>
                    <th className="col-actions">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedSources.map(source => {
                    const test = testResults[source.name];
                    const tc = typeColor(source.type);
                    const summary = extractConnectionSummary(source);
                    return (
                      <tr key={source.name} className="source-row">
                        <td className="col-type">
                          <span className="source-type-chip" style={{ color: tc.color, background: tc.bg, borderColor: tc.border }}>
                            {tc.label}
                          </span>
                        </td>
                        <td className="col-name">
                          <span className="source-name-text">{source.name}</span>
                        </td>
                        <td className="col-system">
                          {source.systemId ? (
                            <span className="source-system-chip">{String(source.systemId)}</span>
                          ) : <span className="cell-dash">—</span>}
                        </td>
                        <td className="col-env">
                          {source.environment ? (
                            <span className="source-env-chip">{String(source.environment)}</span>
                          ) : <span className="cell-dash">—</span>}
                        </td>
                        <td className="col-conn">
                          {summary ? (
                            <span className="source-conn-summary">{summary}</span>
                          ) : <span className="cell-dash">—</span>}
                        </td>
                        <td className="col-status">
                          <div className="status-cell">
                            {!test ? (
                              <span className="status-indicator status-idle">
                                <span className="status-pulse" />
                                未测试
                              </span>
                            ) : test.ok ? (
                              <span className="status-indicator status-ok">
                                <span className="status-pulse" />
                                已连接
                              </span>
                            ) : (
                              <span className="status-indicator status-fail">
                                <span className="status-pulse" />
                                未连接
                              </span>
                            )}
                            {test?.latency !== undefined && test.latency > 0 && (
                              <span className="latency-pill">{test.latency}ms</span>
                            )}
                          </div>
                          {test && !test.ok && test.error && (
                            <div className="source-error-inline" title={test.error}>{test.error}</div>
                          )}
                        </td>
                        <td className="col-tools">
                          <span className="tool-count-text">{source.toolCount || 0}</span>
                        </td>
                        <td className="col-actions">
                          <div className="row-actions">
                            <button
                              className="icon-btn"
                              onClick={() => handleTest(source.name)}
                              disabled={testing === source.name}
                              title="测试连接"
                              aria-label={`测试数据源 ${source.name} 的连接`}
                            >
                              {testing === source.name ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> : <PlayIcon />}
                            </button>
                            <button
                              className="icon-btn"
                              onClick={() => handleEditClick(source.name)}
                              title="编辑"
                              aria-label={`编辑数据源 ${source.name}`}
                            >
                              <EditIcon />
                            </button>
                            <button
                              className="icon-btn danger"
                              onClick={() => handleDelete(source.name)}
                              title="删除"
                              aria-label={`删除数据源 ${source.name}`}
                            >
                              <TrashIcon />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="pagination">
            <span className="pagination-info">
              共 {totalPages} 页，当前第 {safePage}/{totalPages} 页
            </span>
            <div className="pagination-controls">
              <button
                className="page-btn"
                onClick={() => goToPage(safePage - 1)}
                disabled={safePage === 1}
              >
                上一页
              </button>
              <button
                className="page-btn"
                onClick={() => goToPage(safePage + 1)}
                disabled={safePage === totalPages}
              >
                下一页
              </button>
            </div>
          </div>
        </>
      )}

      {showModal && (
        <SourceFormModal
          mode="create"
          sourceTypes={sourceTypes}
          environments={environments}
          onClose={() => setShowModal(false)}
          onSubmit={handleCreate}
        />
      )}

      {editingSource && (
        <SourceFormModal
          mode="edit"
          sourceTypes={sourceTypes}
          environments={environments}
          source={editingSource}
          onClose={() => setEditingSource(null)}
          onSubmit={handleEdit}
        />
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除数据源"
        message={`确定要删除数据源 "${deleteTarget}" 吗？关联的工具也会被删除。`}
        confirmText="删除"
        variant="danger"
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      {querying && (
        <div className="query-loading-overlay" role="status" aria-live="polite">
          <div className="query-loading-box">
            <span className="spinner" />
            <span className="loading-text">查询中...</span>
          </div>
        </div>
      )}
    </div>
  );
}

// --- 配置字段元信息：哪些字段不展示在表单中 ---
const HIDDEN_FIELDS = new Set(['name', 'type', 'status', 'latency', 'error', 'toolCount', 'createdTools', 'systemId', 'environment']);

function SourceFormModal({
  mode,
  sourceTypes,
  environments,
  source,
  onClose,
  onSubmit,
}: {
  mode: 'create' | 'edit';
  sourceTypes: Record<string, SourceTypeSchema>;
  environments: string[];
  source?: SourceInfo | null;
  onClose: () => void;
  onSubmit: (data: { name: string; type: string; [key: string]: unknown }) => Promise<void>;
}) {
  const isEdit = mode === 'edit';
  const [type, setType] = useState(source?.type || Object.keys(sourceTypes)[0] || 'postgres');
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [submitting, setSubmitting] = useState(false);
  // 标记密码字段是否被用户修改过
  // 编辑模式下初始留空, 用户输入新值后标记为 true, 提交时发送新密码
  // 未修改则不提交 password 字段, 让后端保留原密码
  const [passwordModified, setPasswordModified] = useState(false);

  // 初始化表单数据
  useEffect(() => {
    // 重置密码修改标记
    setPasswordModified(false);
    if (isEdit && source) {
      // 编辑模式：从 source 对象提取配置字段
      const configFields: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(source)) {
        if (!HIDDEN_FIELDS.has(key)) {
          if (key === 'password') {
            // 编辑模式: 密码字段留空, 不回填任何值(安全考虑)
            // 用户输入新值后提交, 不输入则保留原密码
            continue;
          } else {
            configFields[key] = value;
          }
        }
      }
      setFormData({ systemId: (source.systemId as string) || '', environment: (source.environment as string) || '', name: source.name, ...configFields });
    } else {
      // 创建模式: 使用 schema 默认值
      const schema = sourceTypes[type];
      if (!schema) return;
      const defaults: Record<string, unknown> = {};
      schema.fields.forEach(f => {
        if (f.default !== undefined) defaults[f.name] = f.default;
      });
      setFormData(prev => ({ systemId: prev['systemId'] || '', environment: prev['environment'] || '', name: prev['name'] || '', ...defaults }));
    }
  }, [isEdit, source, type, sourceTypes]);

  const currentSchema = sourceTypes[type];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = formData['name'] as string;
    const systemId = (formData['systemId'] as string || '').trim();
    const environment = (formData['environment'] as string || '').trim();
    if (!systemId) {
      toast.warning('请输入系统编号');
      return;
    }
    if (systemId.length > 10) {
      toast.warning('系统编号长度不能超过 10 位');
      return;
    }
    if (!environment) {
      toast.warning('请选择环境');
      return;
    }
    if (!name) {
      toast.warning('请输入数据源名称');
      return;
    }
    setSubmitting(true);
    try {
      const { name: _, systemId: __, environment: ___, ...rest } = formData;
      const payload: { name: string; type: string; systemId: string; environment: string; [key: string]: unknown } = { name, type, systemId, environment, ...rest };
      // 密码字段处理:
      // - 编辑模式下用户未改密码(passwordModified=false): 从 payload 删除, 让后端保留原密码
      // - 用户输入了新密码(passwordModified=true): 提交新值, 后端加密后覆盖
      // - 列表项残留的 "********" 占位: 也删除(向后兼容)
      if (isEdit && !passwordModified) {
        delete payload['password'];
      } else {
        for (const [key, value] of Object.entries(payload)) {
          if (value === '********') {
            delete payload[key];
          }
        }
      }
      await onSubmit(payload);
    } catch {
      // 错误已在 onSubmit 中处理
    } finally {
      setSubmitting(false);
    }
  };

  const handleFieldChange = (fieldName: string, value: unknown) => {
    // 密码字段被修改时标记, 后续提交时发送新值而非保留原密码
    if (fieldName === 'password') {
      setPasswordModified(true);
    }
    setFormData(prev => ({ ...prev, [fieldName]: value }));
  };

  // 获取字段的 schema 信息（编辑/新增统一用 schema 渲染表单）
  const fields = currentSchema?.fields || [];

  return (
    <div className="modal-overlay">
      <div className="modal-content source-modal-content">
        <div className="modal-header">
          <div>
            <span className="modal-eyebrow">{isEdit ? '编辑现有' : '新建'}</span>
            <h2>{isEdit ? '编辑数据源' : '添加数据源'}</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="关闭"><CloseIcon /></button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body source-modal-body">
            {(() => {
              // 统一构建字段列表: 标识字段 + schema 连接字段,均分到两栏避免滚动
              type FieldDef = {
                key: string;
                label: string;
                required?: boolean;
                node: React.ReactNode;
              };
              const allFields: FieldDef[] = [
                {
                  key: 'systemId',
                  label: '系统编号',
                  required: true,
                  node: (
                    <input
                      className={`form-input${isEdit ? ' input-disabled' : ''}`}
                      type="text"
                      value={(formData['systemId'] as string) || ''}
                      onChange={e => handleFieldChange('systemId', e.target.value.slice(0, 10))}
                      placeholder="例如：SYS001"
                      maxLength={10}
                      disabled={isEdit}
                      readOnly={isEdit}
                      required
                    />
                  ),
                },
                {
                  key: 'environment',
                  label: '环境',
                  required: true,
                  node: (
                    <select
                      className={`form-select${isEdit ? ' input-disabled' : ''}`}
                      value={(formData['environment'] as string) || ''}
                      onChange={e => handleFieldChange('environment', e.target.value)}
                      disabled={isEdit}
                      required
                    >
                      <option value="">请选择环境</option>
                      {environments.map(env => <option key={env} value={env}>{env}</option>)}
                    </select>
                  ),
                },
                {
                  key: 'name',
                  label: '数据源名称',
                  required: true,
                  node: (
                    <input
                      className={`form-input${isEdit ? ' input-disabled' : ''}`}
                      type="text"
                      value={(formData['name'] as string) || ''}
                      onChange={e => handleFieldChange('name', e.target.value)}
                      placeholder="例如：my_database"
                      disabled={isEdit}
                      readOnly={isEdit}
                      required
                    />
                  ),
                },
                {
                  key: 'type',
                  label: '数据源类型',
                  node: (
                    <select
                      className="form-select"
                      value={type}
                      onChange={e => setType(e.target.value)}
                    >
                      {Object.keys(sourceTypes).map(t => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  ),
                },
                ...fields.map(f => {
                  const isPassword = f.type === 'password';
                  // 密码字段始终用 type=password, 编辑模式下留空不回填
                  // 用户输入新值后提交, 不输入则保留原密码
                  const showPasswordHint = isPassword && isEdit && !passwordModified;
                  return {
                    key: f.name,
                    label: f.label,
                    required: f.required,
                    node: (
                      <>
                        <input
                          className="form-input"
                          type={isPassword ? 'password' : f.type}
                          value={formData[f.name] !== undefined ? String(formData[f.name]) : ''}
                          onChange={e => {
                            const val = f.type === 'number' && e.target.value !== '' ? Number(e.target.value) : e.target.value;
                            handleFieldChange(f.name, val);
                          }}
                          placeholder={f.placeholder || (isPassword && isEdit ? '不修改请留空' : '')}
                          required={f.required && !(isPassword && isEdit)}
                          // 创建模式用 new-password, 编辑模式用 current-password
                          autoComplete={isPassword ? (isEdit ? 'current-password' : 'new-password') : undefined}
                        />
                        {showPasswordHint && (
                          <span className="form-hint password-hint">
                            已存在密文, 不修改请留空
                          </span>
                        )}
                      </>
                    ),
                  };
                }),
              ];
              // 按数量均分: 前一半左栏,后一半右栏
              const mid = Math.ceil(allFields.length / 2);
              const leftCol = allFields.slice(0, mid);
              const rightCol = allFields.slice(mid);

              const renderField = (field: FieldDef) => (
                <div key={field.key} className="form-group">
                  <label className="form-label">
                    {field.label}
                    {field.required && <span className="required-mark">*</span>}
                  </label>
                  {field.node}
                </div>
              );

              return (
                <div className="source-form-grid">
                  <div className="source-form-col">{leftCol.map(renderField)}</div>
                  <div className="source-form-col">{rightCol.map(renderField)}</div>
                </div>
              );
            })()}
          </div>

          <div className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose}>取消</button>
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? (isEdit ? '更新中...' : '创建中...') : (isEdit ? '更新数据源' : '创建数据源')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
