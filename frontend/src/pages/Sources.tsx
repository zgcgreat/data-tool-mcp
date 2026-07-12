import { useEffect, useMemo, useState } from 'react';
import { fetchSources, fetchSourceTypes, createSource, updateSource, deleteSource, testSourceConnection } from '../api/client';
import { toast } from '../components/Toast';
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

function ToolCountIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
      <path d="M14.5 1.5a3 3 0 00-4.24 0L7.4 4.36a.75.75 0 101.06 1.06l2.86-2.86a1.5 1.5 0 012.12 2.12l-2.86 2.86a.75.75 0 101.06 1.06l2.86-2.86a3 3 0 000-4.24z" />
      <path d="M7.3 7.42l-4.33 4.34a1.5 1.5 0 00-.42 1.06l-.3 2.36a.5.5 0 00.57.57l2.36-.3a1.5 1.5 0 001.06-.42l4.34-4.33-3.28-3.28z" fillOpacity="0.85" />
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

  useEffect(() => {
    loadData();
  }, []);

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
        <button className="btn-primary" onClick={() => setShowModal(true)}>
          <PlusIcon /> 添加数据源
        </button>
      </div>

      {sources.length === 0 ? (
        <div className="empty-state card">
          <div className="empty-icon"><DatabaseIcon /></div>
          <h3>还没有数据源</h3>
          <p>添加数据源后，系统会自动生成对应的工具</p>
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            <PlusIcon /> 添加第一个数据源
          </button>
        </div>
      ) : (
        <div className="sources-grid">
          {sources.map((source, idx) => {
            const test = testResults[source.name];
            const tc = typeColor(source.type);
            const summary = extractConnectionSummary(source);
            return (
              <div
                key={source.name}
                className="source-card card card-hover"
                style={{ animationDelay: `${idx * 0.04}s` }}
              >
                {/* 顶部彩条 */}
                <div className="source-type-bar" style={{ background: tc.color }} />
                <div className="source-card-header">
                  <div className="source-card-info">
                    <span className="source-type-chip" style={{ color: tc.color, background: tc.bg, borderColor: tc.border }}>
                      {tc.label}
                    </span>
                    <h3 className="source-card-name">{source.name}</h3>
                    {summary && (
                      <div className="source-conn-summary">{summary}</div>
                    )}
                  </div>
                  <div className="source-card-actions">
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
                </div>

                <div className="source-card-body">
                  <div className="source-status-row">
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
                    <span className="source-tool-count">
                      <ToolCountIcon />
                      {source.toolCount || 0} 工具
                    </span>
                  </div>
                  {test && !test.ok && test.error && (
                    <div className="source-error">{test.error}</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
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
const HIDDEN_FIELDS = new Set(['name', 'type', 'status', 'latency', 'error', 'toolCount', 'createdTools']);

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
      setFormData({ name: source.name, ...configFields });
    } else {
      // 创建模式：从 schema 读取默认值
      const schema = sourceTypes[type];
      if (!schema) return;
      const defaults: Record<string, unknown> = {};
      schema.fields.forEach(f => {
        if (f.default !== undefined) defaults[f.name] = f.default;
      });
      setFormData(prev => ({ name: prev['name'] || '', ...defaults }));
    }
  }, [isEdit, source, type, sourceTypes]);

  const currentSchema = sourceTypes[type];
  const currentTypeColor = useMemo(() => typeColor(type), [type]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = formData['name'] as string;
    if (!name) {
      toast.warning('请输入数据源名称');
      return;
    }
    setSubmitting(true);
    try {
      const { name: _, ...rest } = formData;
      // 密码脱敏占位符 "********" 不提交（让后端保留原密码）
      const payload: { name: string; type: string; [key: string]: unknown } = { name, type, ...rest };
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

  // 获取字段的 schema 信息（编辑模式也用 schema 渲染表单）
  const fields = currentSchema?.fields || [];

  // 编辑模式可能有 schema 中没有的字段，补充展示
  const schemaFieldNames = new Set(fields.map(f => f.name));
  const extraFields = isEdit
    ? Object.entries(formData).filter(
        ([key]) => !HIDDEN_FIELDS.has(key) && !schemaFieldNames.has(key) && key !== 'name'
      )
    : [];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <span className="modal-eyebrow">{isEdit ? '编辑现有' : '新建'}</span>
            <h2>{isEdit ? '编辑数据源' : '添加数据源'}</h2>
          </div>
          <button className="icon-btn" onClick={onClose}><CloseIcon /></button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label className="form-label">数据源名称</label>
              <input
                className="form-input"
                type="text"
                value={(formData['name'] as string) || ''}
                onChange={e => handleFieldChange('name', e.target.value)}
                placeholder="例如：my_database"
                disabled={isEdit}
                required
              />
              {isEdit && <span className="form-help-text">名称不可修改</span>}
            </div>

            <div className="form-group">
              <label className="form-label">数据源类型</label>
              {isEdit ? (
                <div className="type-chip-large" style={{ color: currentTypeColor.color, background: currentTypeColor.bg, borderColor: currentTypeColor.border }}>
                  {currentTypeColor.label}
                </div>
              ) : (
                <select
                  className="form-select"
                  value={type}
                  onChange={e => setType(e.target.value)}
                >
                  {Object.keys(sourceTypes).map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              )}
            </div>

            {fields.map(field => (
              <div key={field.name} className="form-group">
                <label className="form-label">
                  {field.label}
                  {field.required && <span className="required-mark">*</span>}
                </label>
                <input
                  className="form-input"
                  type={field.type}
                  value={formData[field.name] !== undefined ? String(formData[field.name]) : ''}
                  onChange={e => {
                    const val = field.type === 'number' && e.target.value !== '' ? Number(e.target.value) : e.target.value;
                    handleFieldChange(field.name, val);
                  }}
                  placeholder={field.placeholder || ''}
                  required={field.required}
                />
              </div>
            ))}

            {/* 编辑模式：展示 schema 中未定义的额外字段 */}
            {extraFields.map(([key, value]) => (
              <div key={key} className="form-group">
                <label className="form-label">{key}</label>
                <input
                  className="form-input"
                  type="text"
                  value={String(value ?? '')}
                  onChange={e => handleFieldChange(key, e.target.value)}
                />
              </div>
            ))}

            {isEdit && (
              <div className="edit-notice">
                密码字段显示为 ********，留空表示不修改原密码。修改后会自动重建关联的工具。
              </div>
            )}
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
