import { useEffect, useState } from 'react';
import { fetchMcpStats, fetchMcpLogs, fetchSystems, fetchSources } from '../api/client';
import type { SystemInfo, McpStatsResult, McpLogsResult } from '../api/client';
import type { SourceInfo } from '../api/types';
import { toast } from '../components/Toast';
import './McpStats.css';

function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function ChartIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 13h12M4 13V8M7 13V4M10 13V6M13 13V9" />
    </svg>
  );
}

export default function McpStats() {
  const [stats, setStats] = useState<McpStatsResult | null>(null);
  const [logs, setLogs] = useState<McpLogsResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsPageSize] = useState(20);
  const [systems, setSystems] = useState<SystemInfo[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [selectedSystemId, setSelectedSystemId] = useState('');
  const [selectedSourceName, setSelectedSourceName] = useState('');
  // 日期直接用输入框,默认近30天
  const today = new Date();
  const defaultStart = new Date(today);
  defaultStart.setDate(defaultStart.getDate() - 29);
  const [startDate, setStartDate] = useState(formatDate(defaultStart));
  const [endDate, setEndDate] = useState(formatDate(today));

  useEffect(() => {
    // 初始化系统/数据源列表
    Promise.all([fetchSystems(), fetchSources()])
      .then(([sysData, srcData]) => {
        setSystems(sysData);
        setSources(srcData);
      })
      .catch(() => {
        // 静默
      });
  }, []);

  // 首次加载
  useEffect(() => {
    loadStats(startDate, endDate);
    loadLogs(startDate, endDate, 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadStats = async (start: string, end: string) => {
    setLoading(true);
    try {
      const data = await fetchMcpStats({
        startDate: start,
        endDate: end,
        systemId: selectedSystemId,
        sourceName: selectedSourceName,
      });
      setStats(data);
    } catch (error) {
      toast.error('加载统计数据失败');
      console.error('Failed to load mcp stats:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadLogs = async (start: string, end: string, page: number) => {
    setLogsLoading(true);
    try {
      const data = await fetchMcpLogs({
        page,
        pageSize: logsPageSize,
        startDate: start,
        endDate: end,
        systemId: selectedSystemId,
        sourceName: selectedSourceName,
      });
      setLogs(data);
    } catch (error) {
      toast.error('加载请求记录失败');
      console.error('Failed to load mcp logs:', error);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleQuery = () => {
    if (!startDate || !endDate) {
      toast.error('请选择完整的起止日期');
      return;
    }
    if (startDate > endDate) {
      toast.error('起始日期不能晚于截止日期');
      return;
    }
    loadStats(startDate, endDate);
    loadLogs(startDate, endDate, 1);
  };

  const handleSystemChange = (value: string) => {
    setSelectedSystemId(value);
    setSelectedSourceName(''); // 切换系统时清空数据源筛选
  };

  const handleLogsPageChange = (newPage: number) => {
    loadLogs(startDate, endDate, newPage);
  };

  // 当前展示的数据源列表（按系统筛选）
  const filteredSources = selectedSystemId
    ? sources.filter(s => String(s.systemId || '') === selectedSystemId)
    : sources;

  // 趋势图最大值（用于柱状图高度计算）
  const timelineMax = stats?.timeline?.reduce((max, item) => Math.max(max, item.total), 0) || 0;

  return (
    <div className="mcp-stats-page fade-in">
      <div className="page-header">
        <div className="page-title-group">
          <span className="page-eyebrow">数据分析</span>
          <h1 className="page-title">
            <span className="title-icon"><ChartIcon /></span>
            MCP 请求统计
          </h1>
        </div>
      </div>

      {/* 筛选栏 */}
      <div className="stats-filters card">
        <div className="filter-row">
          <div className="filter-item">
            <label className="filter-label">系统</label>
            <select
              className="form-select"
              value={selectedSystemId}
              onChange={e => handleSystemChange(e.target.value)}
            >
              <option value="">全部系统</option>
              {systems.map(sys => (
                <option key={sys.systemId} value={sys.systemId}>
                  {sys.systemId}
                </option>
              ))}
            </select>
          </div>
          <div className="filter-item">
            <label className="filter-label">数据源</label>
            <select
              className="form-select"
              value={selectedSourceName}
              onChange={e => setSelectedSourceName(e.target.value)}
            >
              <option value="">全部数据源</option>
              {filteredSources.map(s => (
                <option key={s.name} value={s.name}>{s.name}</option>
              ))}
            </select>
          </div>
          <div className="filter-item">
            <label className="filter-label">开始日期</label>
            <input
              type="date"
              className="form-input date-input"
              value={startDate}
              onChange={e => setStartDate(e.target.value)}
            />
          </div>
          <div className="filter-item">
            <label className="filter-label">结束日期</label>
            <input
              type="date"
              className="form-input date-input"
              value={endDate}
              onChange={e => setEndDate(e.target.value)}
            />
          </div>
          <button className="btn-primary query-btn" onClick={handleQuery}>查询</button>
        </div>
      </div>

      {loading ? (
        <div className="page-loading">
          <div className="spinner" />
          <div className="loading-text">统计中...</div>
        </div>
      ) : stats ? (
        <>
          {/* 概览卡片 */}
          <div className="stats-summary">
            <div className="stat-card card tone-blue">
              <div className="stat-card-label">总请求</div>
              <div className="stat-card-value">{stats.summary.total.toLocaleString()}</div>
            </div>
            <div className="stat-card card tone-green">
              <div className="stat-card-label">成功</div>
              <div className="stat-card-value">{stats.summary.success.toLocaleString()}</div>
            </div>
            <div className="stat-card card tone-red">
              <div className="stat-card-label">失败</div>
              <div className="stat-card-value">{stats.summary.fail.toLocaleString()}</div>
            </div>
            <div className="stat-card card tone-amber">
              <div className="stat-card-label">平均延迟</div>
              <div className="stat-card-value">{stats.summary.avg_latency_ms}<span className="unit">ms</span></div>
            </div>
          </div>

          {stats.note && (
            <div className="stats-note card">{stats.note}</div>
          )}

          {/* 趋势图 */}
          {stats.timeline.length > 0 && (
            <div className="stats-section card">
              <div className="section-header">
                <h3>请求趋势</h3>
                <span className="section-meta">{stats.start_date} ~ {stats.end_date}</span>
              </div>
              <div className="timeline-chart">
                {stats.timeline.map(item => {
                  const heightPct = timelineMax > 0 ? (item.total / timelineMax) * 100 : 0;
                  const failPct = item.total > 0 ? (item.fail / item.total) * 100 : 0;
                  return (
                    <div key={item.date} className="timeline-bar-col" title={`${item.date}：${item.total} 次（失败 ${item.fail}）`}>
                      <div className="timeline-bar" style={{ height: `${heightPct}%` }}>
                        <div className="timeline-bar-fail" style={{ height: `${failPct}%` }} />
                      </div>
                      <span className="timeline-date">{item.date.slice(5)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 分组表格 */}
          <div className="stats-grid">
            {stats.by_system.length > 0 && (
              <div className="stats-section card">
                <div className="section-header">
                  <h3>按系统</h3>
                </div>
                <table className="stats-table">
                  <thead>
                    <tr>
                      <th>系统编号</th>
                      <th className="num-col">总数</th>
                      <th className="num-col">成功</th>
                      <th className="num-col">失败</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.by_system.map((item, i) => (
                      <tr key={i}>
                        <td>{item.system_id}</td>
                        <td className="num-col">{item.total}</td>
                        <td className="num-col success">{item.success}</td>
                        <td className="num-col fail">{item.fail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {stats.by_source.length > 0 && (
              <div className="stats-section card">
                <div className="section-header">
                  <h3>按数据源</h3>
                </div>
                <table className="stats-table">
                  <thead>
                    <tr>
                      <th>数据源</th>
                      <th className="num-col">总数</th>
                      <th className="num-col">成功</th>
                      <th className="num-col">失败</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.by_source.map((item, i) => (
                      <tr key={i}>
                        <td>{item.source_name}</td>
                        <td className="num-col">{item.total}</td>
                        <td className="num-col success">{item.success}</td>
                        <td className="num-col fail">{item.fail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {stats.by_tool.length > 0 && (
              <div className="stats-section card">
                <div className="section-header">
                  <h3>按工具（Top 50）</h3>
                </div>
                <table className="stats-table">
                  <thead>
                    <tr>
                      <th>工具名称</th>
                      <th className="num-col">总数</th>
                      <th className="num-col">成功</th>
                      <th className="num-col">失败</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.by_tool.map((item, i) => (
                      <tr key={i}>
                        <td className="tool-name-cell">{item.tool_name}</td>
                        <td className="num-col">{item.total}</td>
                        <td className="num-col success">{item.success}</td>
                        <td className="num-col fail">{item.fail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {stats.summary.total === 0 && !stats.note && (
            <div className="empty-state card">
              <div className="empty-icon"><ChartIcon /></div>
              <h3>暂无请求数据</h3>
              <p>所选时间范围内没有 MCP 请求记录</p>
            </div>
          )}

          {/* 请求记录明细 */}
          {stats.summary.total > 0 && (
            <div className="stats-section card logs-section">
              <div className="section-header">
                <h3>请求记录</h3>
                {logs && (
                  <span className="section-meta">
                    共 {logs.total} 条，第 {logs.page}/{logs.total_pages} 页
                  </span>
                )}
              </div>
              {logsLoading ? (
                <div className="logs-loading"><div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /></div>
              ) : logs && logs.items.length > 0 ? (
                <>
                  <div className="logs-table-wrap">
                    <table className="stats-table logs-table">
                      <thead>
                        <tr>
                          <th>时间</th>
                          <th>系统</th>
                          <th>数据源</th>
                          <th>工具</th>
                          <th>方法</th>
                          <th className="num-col">状态</th>
                          <th className="num-col">延迟</th>
                          <th>客户端</th>
                        </tr>
                      </thead>
                      <tbody>
                        {logs.items.map(item => (
                          <tr key={item.id}>
                            <td className="time-cell">{item.created_at}</td>
                            <td>{item.system_id || '-'}</td>
                            <td>{item.source_name || '-'}</td>
                            <td className="tool-name-cell" title={item.tool_name}>{item.tool_name || '-'}</td>
                            <td className="method-cell">{item.method}</td>
                            <td className="num-col">
                              {item.success ? (
                                <span className="status-badge status-ok">成功</span>
                              ) : (
                                <span className="status-badge status-fail">失败</span>
                              )}
                            </td>
                            <td className="num-col">{item.latency_ms}ms</td>
                            <td className="client-cell">{item.client_addr || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="logs-pagination">
                    <button
                      className="page-btn"
                      onClick={() => handleLogsPageChange(logs.page - 1)}
                      disabled={logs.page <= 1}
                    >
                      上一页
                    </button>
                    <span className="page-info">
                      第 {logs.page}/{logs.total_pages} 页
                    </span>
                    <button
                      className="page-btn"
                      onClick={() => handleLogsPageChange(logs.page + 1)}
                      disabled={logs.page >= logs.total_pages}
                    >
                      下一页
                    </button>
                  </div>
                </>
              ) : (
                <div className="logs-empty">暂无请求记录</div>
              )}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
