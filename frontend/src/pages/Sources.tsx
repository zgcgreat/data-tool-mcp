import { useEffect, useState } from 'react';
import { fetchSources, fetchSourceTypes, createSource, updateSource, deleteSource, testSourceConnection, fetchSystems } from '../api/client';
import { toast } from '../components/Toast';
import type { SystemInfo } from '../api/client';
import type { SourceInfo, SourceTypeSchema } from '../api/types';
import './Sources.css';

// --- 类型配色系统 ---
const TYPE_COLORS: Record<string, { color: string; bg: string; border: string; label: string }> = {
  postgresql: { color: '#1f4ea8', bg: 'rgba(47,111,219,0.10)', border: 'rgba(47,111,219,0.30)', label: 'PostgreSQL' },
  postgres:   { color: '#1f4ea8', bg: 'rgba(47,111,219,0.10)', border: 'rgba(47,111,219,0.30)', label: 'PostgreSQL' },
  mysql:      { color: '#a85a18', bg: 'rgba(232,135,58,0.12)', border: 'rgba(232,135,58,0.32)', label: 'MySQL' },
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

function EyeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" />
      <circle cx="8" cy="8" r="2" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8c-.3.5-.7 1-1.1 1.4M5.5 5.5C6.3 5.2 7.1 5 8 5c4 0 6.5 3 6.5 3" />
      <path d="M2 2l12 12" />
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
  const [selectedSystemId, setSelectedSystemId] = useState('');
  const [systems, setSystems] = useState<SystemInfo[]>([]);
  // 分页: 列表展示，默认每页 10 条
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  useEffect(() => {
    loadData();
    loadSystems();
  }, []);

  // 筛选条件变化时重置到第 1 页
  useEffect(() => {
    setCurrentPage(1);
  }, [selectedSystemId]);

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

  const handleDelete = async (name: string) => {
    if (!confirm(`确定要删除数据源 "${name}" 吗？关联的工具也会被删除。`)) return;
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

  // 按系统编号筛选数据源
  const filteredSources = selectedSystemId
    ? sources.filter(s => String(s.systemId || '') === selectedSystemId)
    : sources;

  // 分页计算（边界保护：删除后当前页可能超出范围）
  const totalPages = Math.max(1, Math.ceil(filteredSources.length / pageSize));
  const safePage = Math.min(currentPage, totalPages);
  const pageStart = (safePage - 1) * pageSize;
  const pagedSources = filteredSources.slice(pageStart, pageStart + pageSize);

  const goToPage = (page: number) => {
    setCurrentPage(Math.max(1, Math.min(page, totalPages)));
  };

  if (loading) {
    return (
      <div className="page-loading">
        <div className="spinner" />
        <div className="loading-text">加载中...</div>
      </div>
    );
  }

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
            <select
              className="form-select tools-filter"
              value={selectedSystemId}
              onChange={e => setSelectedSystemId(e.target.value)}
              style={{ width: 'auto', minWidth: '180px' }}
            >
              <option value="">全部系统</option>
              {systems.map(sys => (
                <option key={sys.systemId} value={sys.systemId}>
                  {sys.systemId}（{sys.sourceCount} 个数据源）
                </option>
              ))}
            </select>
          )}
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            <PlusIcon /> 添加数据源
          </button>
        </div>
      </div>

      {filteredSources.length === 0 ? (
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
                    <th className="col-type">类型</th>
                    <th className="col-name">名称</th>
                    <th className="col-system">系统</th>
                    <th className="col-conn">连接</th>
                    <th className="col-status">状态</th>
                    <th className="col-tools">工具</th>
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
                            >
                              {testing === source.name ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> : <PlayIcon />}
                            </button>
                            <button
                              className="icon-btn"
                              onClick={() => setEditingSource(source)}
                              title="编辑"
                            >
                              <EditIcon />
                            </button>
                            <button
                              className="icon-btn danger"
                              onClick={() => handleDelete(source.name)}
                              title="删除"
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
          onClose={() => setShowModal(false)}
          onSubmit={handleCreate}
        />
      )}

      {editingSource && (
        <SourceFormModal
          mode="edit"
          sourceTypes={sourceTypes}
          source={editingSource}
          onClose={() => setEditingSource(null)}
          onSubmit={handleEdit}
        />
      )}
    </div>
  );
}

// --- 配置字段元信息：哪些字段不展示在表单中 ---
const HIDDEN_FIELDS = new Set(['name', 'type', 'status', 'latency', 'error', 'toolCount', 'createdTools', 'systemId']);

function SourceFormModal({
  mode,
  sourceTypes,
  source,
  onClose,
  onSubmit,
}: {
  mode: 'create' | 'edit';
  sourceTypes: Record<string, SourceTypeSchema>;
  source?: SourceInfo | null;
  onClose: () => void;
  onSubmit: (data: { name: string; type: string; [key: string]: unknown }) => Promise<void>;
}) {
  const isEdit = mode === 'edit';
  const [type, setType] = useState(source?.type || Object.keys(sourceTypes)[0] || 'postgres');
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // 初始化表单数据
  useEffect(() => {
    if (isEdit && source) {
      // 编辑模式：从 source 对象提取配置字段
      const configFields: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(source)) {
        if (!HIDDEN_FIELDS.has(key)) {
          configFields[key] = value;
        }
      }
      setFormData({ systemId: (source.systemId as string) || '', name: source.name, ...configFields });
    } else {
      // 创建模式：从 schema 读取默认值
      const schema = sourceTypes[type];
      if (!schema) return;
      const defaults: Record<string, unknown> = {};
      schema.fields.forEach(f => {
        if (f.default !== undefined) defaults[f.name] = f.default;
      });
      setFormData(prev => ({ systemId: prev['systemId'] || '', name: prev['name'] || '', ...defaults }));
    }
    setShowPassword(false);
  }, [isEdit, source, type, sourceTypes]);

  const currentSchema = sourceTypes[type];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = formData['name'] as string;
    const systemId = (formData['systemId'] as string || '').trim();
    if (!systemId) {
      toast.warning('请输入系统编号');
      return;
    }
    if (systemId.length > 10) {
      toast.warning('系统编号长度不能超过 10 位');
      return;
    }
    if (!name) {
      toast.warning('请输入数据源名称');
      return;
    }
    setSubmitting(true);
    try {
      const { name: _, systemId: __, ...rest } = formData;
      // 密码脱敏占位符 "********" 不提交（让后端保留原密码）
      const payload: { name: string; type: string; systemId: string; [key: string]: unknown } = { name, type, systemId, ...rest };
      for (const [key, value] of Object.entries(payload)) {
        if (value === '********') {
          delete payload[key];
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
    setFormData(prev => ({ ...prev, [fieldName]: value }));
  };

  // 获取字段的 schema 信息（编辑/新增统一用 schema 渲染表单）
  const fields = currentSchema?.fields || [];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content source-modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="modal-eyebrow">{isEdit ? '编辑现有' : '新建'}</span>
            <h2>{isEdit ? '编辑数据源' : '添加数据源'}</h2>
          </div>
          <button className="icon-btn" onClick={onClose}><CloseIcon /></button>
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
                ...fields.map(f => ({
                  key: f.name,
                  label: f.label,
                  required: f.required,
                  node: (
                    <div className="input-with-toggle">
                      <input
                        className="form-input"
                        type={f.type === 'password' ? (showPassword ? 'text' : 'password') : f.type}
                        value={formData[f.name] !== undefined ? String(formData[f.name]) : ''}
                        onChange={e => {
                          const val = f.type === 'number' && e.target.value !== '' ? Number(e.target.value) : e.target.value;
                          handleFieldChange(f.name, val);
                        }}
                        placeholder={f.placeholder || ''}
                        required={f.required}
                      />
                      {f.type === 'password' && (
                        <button
                          type="button"
                          className="password-toggle"
                          onClick={() => setShowPassword(prev => !prev)}
                          title={showPassword ? '隐藏密码' : '显示密码'}
                        >
                          {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                        </button>
                      )}
                    </div>
                  ),
                })),
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
