import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchSourceTypes, createSource, testSourceConnection } from '../api/client';
import { toast } from '../components/Toast';
import type { SourceTypeSchema, SourceInfo } from '../api/types';
import './QuickConnect.css';

/* --- Icons --- */

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8l3.5 3.5L13 5" />
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

function ArrowRight() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8h10M9 4l4 4-4 4" />
    </svg>
  );
}

function ArrowLeft() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 8H3M7 4L3 8l4 4" />
    </svg>
  );
}

function ToolIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
      <path d="M14.5 1.5a3 3 0 00-4.24 0L7.4 4.36a.75.75 0 101.06 1.06l2.86-2.86a1.5 1.5 0 012.12 2.12l-2.86 2.86a.75.75 0 101.06 1.06l2.86-2.86a3 3 0 000-4.24z" />
      <path d="M7.3 7.42l-4.33 4.34a1.5 1.5 0 00-.42 1.06l-.3 2.36a.5.5 0 00.57.57l2.36-.3a1.5 1.5 0 001.06-.42l4.34-4.33-3.28-3.28z" fillOpacity="0.85" />
    </svg>
  );
}

/* --- 常用数据库类型描述 --- */

const DB_DESCRIPTIONS: Record<string, { label: string; desc: string; category: string }> = {
  // --- 关系型数据库 (SQL) ---
  postgres: { label: 'PostgreSQL', desc: '功能强大的开源关系数据库', category: 'SQL' },
  mysql: { label: 'MySQL', desc: '广泛使用的开源关系数据库', category: 'SQL' },
  mssql: { label: 'SQL Server', desc: '微软企业级关系数据库', category: 'SQL' },
  oracle: { label: 'Oracle', desc: '企业级商业关系数据库', category: 'SQL' },
  sqlite: { label: 'SQLite', desc: '轻量级本地文件数据库', category: 'SQL' },
  clickhouse: { label: 'ClickHouse', desc: '高性能列式分析数据库', category: 'SQL' },
  snowflake: { label: 'Snowflake', desc: '云数据仓库平台', category: 'SQL' },
  tidb: { label: 'TiDB', desc: '兼容 MySQL 的分布式数据库', category: 'SQL' },
  oceanbase: { label: 'OceanBase', desc: '蚂蚁分布式关系数据库', category: 'SQL' },
  tdsql: { label: 'TDSQL', desc: '腾讯云分布式数据库', category: 'SQL' },
  gaussdb: { label: 'GaussDB', desc: '华为云分布式数据库', category: 'SQL' },
  cockroachdb: { label: 'CockroachDB', desc: '兼容 PostgreSQL 的分布式数据库', category: 'SQL' },
  yugabytedb: { label: 'YugabyteDB', desc: '分布式 SQL 数据库', category: 'SQL' },
  trino: { label: 'Trino', desc: '分布式 SQL 查询引擎', category: 'SQL' },
  firebird: { label: 'Firebird', desc: '开源关系数据库', category: 'SQL' },
  singlestore: { label: 'SingleStore', desc: '实时分布式数据库', category: 'SQL' },
  mindsdb: { label: 'MindsDB', desc: 'AI 驱动的数据平台', category: 'SQL' },
  // --- NoSQL 数据库 ---
  mongodb: { label: 'MongoDB', desc: '文档型 NoSQL 数据库', category: 'NoSQL' },
  redis: { label: 'Redis', desc: '高性能键值内存数据库', category: 'NoSQL' },
  cassandra: { label: 'Cassandra', desc: '分布式宽列数据库', category: 'NoSQL' },
  neo4j: { label: 'Neo4j', desc: '图数据库', category: 'NoSQL' },
  elasticsearch: { label: 'Elasticsearch', desc: '搜索与分析引擎', category: 'NoSQL' },
  valkey: { label: 'Valkey', desc: 'Redis 兼容的内存数据库', category: 'NoSQL' },
  scylladb: { label: 'ScyllaDB', desc: '高性能 NoSQL 数据库', category: 'NoSQL' },
  couchbase: { label: 'Couchbase', desc: 'NoSQL 文档数据库', category: 'NoSQL' },
  hbase: { label: 'HBase', desc: 'Hadoop 列式 NoSQL 数据库', category: 'NoSQL' },
  dgraph: { label: 'Dgraph', desc: '分布式图数据库', category: 'NoSQL' },
  // --- 其他 ---
  http: { label: 'HTTP API', desc: '自定义 HTTP 接口', category: '其他' },
};

// category 分组展示顺序与标题
const DB_CATEGORY_ORDER: { category: string; title: string }[] = [
  { category: 'SQL', title: '关系型数据库' },
  { category: 'NoSQL', title: 'NoSQL 数据库' },
  { category: '其他', title: '其他' },
];

/* --- 组件 --- */

type Step = 1 | 2 | 3;

export default function QuickConnect() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>(1);
  const [sourceTypes, setSourceTypes] = useState<Record<string, SourceTypeSchema>>({});
  const [selectedType, setSelectedType] = useState('');
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [createdSource, setCreatedSource] = useState<SourceInfo | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    loadSourceTypes();
  }, []);

  const loadSourceTypes = async () => {
    try {
      const data = await fetchSourceTypes();
      setSourceTypes(data);
    } catch (error) {
      toast.error('加载数据源类型失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectType = (type: string) => {
    setSelectedType(type);
    const schema = sourceTypes[type];
    const defaults: Record<string, unknown> = {};
    if (schema) {
      schema.fields.forEach(f => {
        if (f.default !== undefined) defaults[f.name] = f.default;
      });
    }
    setFormData({ systemId: '', name: '', ...defaults });
    setShowPassword(false);
    setStep(2);
  };

  const handleFieldChange = (name: string, value: unknown) => {
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleCreate = async () => {
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
      const result = await createSource({ name, type: selectedType, systemId, ...rest });
      setCreatedSource(result);
      setStep(3);
      const toolCount = result.toolCount ?? 0;
      if (toolCount > 0) {
        toast.success(`接入成功，自动生成 ${toolCount} 个工具`);
      } else {
        toast.success('接入成功');
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : '创建失败';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleTestAndCreate = async () => {
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
      // 先创建
      const { name: _, systemId: __, ...rest } = formData;
      const result = await createSource({ name, type: selectedType, systemId, ...rest });
      // 创建后测试连接
      try {
        const testResult = await testSourceConnection(name);
        if (testResult.ok) {
          toast.success(`连接成功 (${testResult.latency}ms)`);
        } else {
          toast.warning(`已创建但连接失败: ${testResult.error}`);
        }
      } catch {
        toast.warning('数据源已创建，连接测试失败');
      }
      setCreatedSource(result);
      setStep(3);
    } catch (error) {
      const msg = error instanceof Error ? error.message : '创建失败';
      toast.error(msg);
    } finally {
      setSubmitting(false);
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
    <div className="quick-connect fade-in">
      {/* 步骤指示器 */}
      <div className="steps-indicator">
        <div className={`step-item ${step >= 1 ? 'active' : ''} ${step > 1 ? 'done' : ''}`}>
          <div className="step-num">{step > 1 ? <CheckIcon /> : '1'}</div>
          <span className="step-text">选择类型</span>
        </div>
        <div className={`step-line ${step > 1 ? 'active' : ''}`} />
        <div className={`step-item ${step >= 2 ? 'active' : ''} ${step > 2 ? 'done' : ''}`}>
          <div className="step-num">{step > 2 ? <CheckIcon /> : '2'}</div>
          <span className="step-text">配置连接</span>
        </div>
        <div className={`step-line ${step > 2 ? 'active' : ''}`} />
        <div className={`step-item ${step >= 3 ? 'active' : ''}`}>
          <div className="step-num">{step === 3 ? <CheckIcon /> : '3'}</div>
          <span className="step-text">完成</span>
        </div>
      </div>

      {/* 步骤 1: 选择类型 */}
      {step === 1 && (
        <div className="step-content">
          <div className="step-header">
            <h2>选择数据库类型</h2>
            <p>选择要接入的数据库类型，系统将自动生成对应的工具</p>
          </div>
          {DB_CATEGORY_ORDER.map(({ category, title }) => {
            // 按 category 分组: 保留 DB_DESCRIPTIONS 中定义的顺序,
            // 仅筛选出属于当前 category 且后端实际支持的类型。
            const typesInCategory = Object.keys(DB_DESCRIPTIONS).filter(
              (type) => DB_DESCRIPTIONS[type].category === category && sourceTypes[type]
            );
            if (typesInCategory.length === 0) return null;
            return (
              <div key={category} className="db-type-group">
                <div className="db-type-group-title">{title}</div>
                <div className="db-type-grid">
                  {typesInCategory.map((type) => {
                    const meta = DB_DESCRIPTIONS[type];
                    return (
                      <button
                        key={type}
                        className="db-type-card card card-hover"
                        onClick={() => handleSelectType(type)}
                      >
                        <div className="db-type-icon" data-category={meta.category}>
                          {meta.label.charAt(0)}
                        </div>
                        <div className="db-type-body">
                          <div className="db-type-name">{meta.label}</div>
                          <div className="db-type-desc">{meta.desc}</div>
                        </div>
                        <ArrowRight />
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 步骤 2: 配置连接 */}
      {step === 2 && (
        <div className="step-content">
          <div className="step-header">
            <h2>配置连接信息</h2>
            <p>
              正在接入 <span className="text-accent">{DB_DESCRIPTIONS[selectedType]?.label || selectedType}</span>
              ，填写以下信息完成接入
            </p>
          </div>

          <div className="config-form card">
            {/* 两栏布局: 所有字段均分到两栏,避免左栏空白 */}
            <div className="config-form-grid">
              {(() => {
                // 统一构建字段列表: 标识字段 + schema 连接字段
                const schemaFields = sourceTypes[selectedType]?.fields || [];
                type FieldDef = {
                  key: string;
                  label: string;
                  required?: boolean;
                  inputType: string;
                  value: string;
                  onChange: (v: string | number) => void;
                  placeholder?: string;
                  maxLength?: number;
                  autoFocus?: boolean;
                  isPassword?: boolean;
                };
                const allFields: FieldDef[] = [
                  {
                    key: 'systemId',
                    label: '系统编号',
                    required: true,
                    inputType: 'text',
                    value: (formData['systemId'] as string) || '',
                    onChange: v => handleFieldChange('systemId', String(v).slice(0, 10)),
                    placeholder: '例如：SYS001',
                    maxLength: 10,
                    autoFocus: true,
                  },
                  {
                    key: 'name',
                    label: '数据源名称',
                    required: true,
                    inputType: 'text',
                    value: (formData['name'] as string) || '',
                    onChange: v => handleFieldChange('name', v),
                    placeholder: '例如：my_database',
                  },
                  ...schemaFields.map((f): FieldDef => ({
                    key: f.name,
                    label: f.label,
                    required: f.required,
                    inputType: f.type === 'number' ? 'number' : (f.type === 'password' ? 'password' : 'text'),
                    value: formData[f.name] !== undefined ? String(formData[f.name]) : '',
                    onChange: v => handleFieldChange(f.name, f.type === 'number' && v !== '' ? Number(v) : v),
                    placeholder: f.placeholder || '',
                    isPassword: f.type === 'password',
                  })),
                ];
                // 按数量均分: 前一半左栏,后一半右栏
                const mid = Math.ceil(allFields.length / 2);
                const leftCol = allFields.slice(0, mid);
                const rightCol = allFields.slice(mid);

                const renderField = (field: FieldDef) => {
                  const inputType = field.isPassword ? (showPassword ? 'text' : 'password') : field.inputType;
                  return (
                    <div key={field.key} className="form-group">
                      <label className="form-label">
                        {field.label}
                        {field.required && <span className="required-mark">*</span>}
                      </label>
                      <div className="input-with-toggle">
                        <input
                          className="form-input"
                          type={inputType}
                          value={field.value}
                          onChange={e => field.onChange(e.target.value)}
                          placeholder={field.placeholder || ''}
                          required={field.required}
                          maxLength={field.maxLength}
                          autoFocus={field.autoFocus}
                        />
                        {field.isPassword && (
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
                    </div>
                  );
                };

                return (
                  <>
                    <div className="config-form-col">
                      {leftCol.map(renderField)}
                    </div>
                    <div className="config-form-col">
                      {rightCol.map(renderField)}
                    </div>
                  </>
                );
              })()}
            </div>

            <div className="form-actions">
              <button className="btn-secondary" onClick={() => setStep(1)}>
                <ArrowLeft /> 上一步
              </button>
              <div className="form-actions-right">
                <button
                  className="btn-secondary"
                  onClick={handleTestAndCreate}
                  disabled={submitting}
                >
                  {submitting ? '创建中...' : '创建并测试'}
                </button>
                <button
                  className="btn-primary"
                  onClick={handleCreate}
                  disabled={submitting}
                >
                  {submitting ? '创建中...' : '创建'}
                  <ArrowRight />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 步骤 3: 完成 */}
      {step === 3 && createdSource && (
        <div className="step-content">
          <div className="success-banner">
            <div className="success-icon-wrap">
              <CheckIcon />
            </div>
            <div className="success-body">
              <h2>接入成功</h2>
              <p>
                数据源 <span className="text-accent">{createdSource.name}</span> 已创建
                {createdSource.toolCount ? `，自动生成 ${createdSource.toolCount} 个工具` : ''}
              </p>
            </div>
          </div>

          {createdSource.createdTools && createdSource.createdTools.length > 0 && (
            <div className="created-tools card">
              <div className="created-tools-header">
                <ToolIcon />
                <span>自动生成的工具</span>
              </div>
              <div className="created-tools-list">
                {createdSource.createdTools.map(toolName => (
                  <div key={toolName} className="created-tool-item">
                    <span className="badge badge-accent">{toolName}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="finish-actions">
            <button className="btn-secondary" onClick={() => {
              setStep(1);
              setSelectedType('');
              setFormData({});
              setCreatedSource(null);
            }}>
              继续接入
            </button>
            <button className="btn-secondary" onClick={() => navigate('/sources')}>
              查看数据源
            </button>
            <button className="btn-primary" onClick={() => navigate('/tools')}>
              查看工具 <ArrowRight />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
