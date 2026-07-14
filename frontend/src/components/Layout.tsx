import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import ToastContainer from './Toast';
import './Layout.css';

const Icon = {
  Dashboard: () => (
    <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
      <rect x="1.75" y="1.75" width="5.5" height="5.5" rx="1" fillOpacity="0.9" />
      <rect x="8.75" y="1.75" width="5.5" height="3.5" rx="1" fillOpacity="0.6" />
      <rect x="8.75" y="6.75" width="5.5" height="7.5" rx="1" fillOpacity="0.6" />
      <rect x="1.75" y="8.75" width="5.5" height="5.5" rx="1" fillOpacity="0.6" />
    </svg>
  ),
  Database: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" width="16" height="16">
      <ellipse cx="8" cy="3.5" rx="5.5" ry="2" />
      <path d="M2.5 3.5v9c0 1.1 2.46 2 5.5 2s5.5-.9 5.5-2v-9" />
      <path d="M2.5 8c0 1.1 2.46 2 5.5 2s5.5-.9 5.5-2" />
    </svg>
  ),
  Tool: () => (
    <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
      <path d="M14.5 1.5a3 3 0 00-4.24 0L7.4 4.36a.75.75 0 101.06 1.06l2.86-2.86a1.5 1.5 0 012.12 2.12l-2.86 2.86a.75.75 0 101.06 1.06l2.86-2.86a3 3 0 000-4.24z" />
      <path d="M8.6 6.13L2.97 11.76a1.5 1.5 0 00-.42 1.06l-.3 2.36a.5.5 0 00.57.57l2.36-.3a1.5 1.5 0 001.06-.42l5.63-5.63" fillOpacity="0" />
      <path d="M7.3 7.42l-4.33 4.34a1.5 1.5 0 00-.42 1.06l-.3 2.36a.5.5 0 00.57.57l2.36-.3a1.5 1.5 0 001.06-.42l4.34-4.33-3.28-3.28z" fillOpacity="0.85" />
    </svg>
  ),
  Query: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" width="16" height="16" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 2.5h6v6h-6z" />
      <path d="M5.5 8.5v3a2 2 0 002 2h4" />
      <path d="M10 12l1.5 1.5L13 12" />
    </svg>
  ),
  Bolt: () => (
    <svg viewBox="0 0 16 16" fill="currentColor" width="16" height="16">
      <path d="M9.5 1.5L3 9h4l-1.5 5.5L12 7H8l1.5-5.5z" />
    </svg>
  ),
  Chart: () => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" width="16" height="16" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 13.5h12M4 13.5V8M7 13.5V4M10 13.5V6.5M13 13.5V9.5" />
    </svg>
  ),
  Logo: () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" width="22" height="22" strokeLinejoin="round">
      <path d="M12 2L3 7v10l9 5 9-5V7l-9-5z" />
      <path d="M12 7v10M7 9.5v5M17 9.5v5" strokeWidth="1.4" opacity="0.6" />
    </svg>
  ),
  Collapse: ({ dir }: { dir: 'left' | 'right' }) => (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" width="14" height="14" strokeLinecap="round" strokeLinejoin="round">
      <path d={dir === 'left' ? 'M10 4L6 8l4 4' : 'M6 4l4 4-4 4'} />
    </svg>
  ),
};

const navItems = [
  { path: '/', label: '仪表盘', icon: <Icon.Dashboard /> },
  { path: '/quick-connect', label: '快速接入', icon: <Icon.Bolt /> },
  { path: '/sources', label: '数据源', icon: <Icon.Database /> },
  { path: '/tools', label: '工具', icon: <Icon.Tool /> },
  { path: '/query', label: '查询', icon: <Icon.Query /> },
  { path: '/mcp-stats', label: '统计', icon: <Icon.Chart /> },
];

const pageNames: Record<string, string> = {
  '/': '仪表盘',
  '/quick-connect': '快速接入',
  '/sources': '数据源',
  '/tools': '工具',
  '/query': '查询',
  '/mcp-stats': '统计',
};

export default function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);

  const currentName = pageNames[location.pathname] || '未知';

  return (
    <div className="layout">
      <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-header">
          <div className="brand">
            <span className="brand-icon"><Icon.Logo /></span>
            {!collapsed && (
              <div className="brand-text">
                <span className="brand-name">Data Tool MCP</span>
                <span className="brand-sub">管理控制台</span>
              </div>
            )}
          </div>
        </div>

        <nav className="nav">
          <div className="nav-section-label">{!collapsed && '导航'}</div>
          {navItems.map((item) => {
            const active = location.pathname === item.path;
            return (
              <button
                key={item.path}
                className={`nav-item ${active ? 'active' : ''}`}
                onClick={() => navigate(item.path)}
                title={collapsed ? item.label : undefined}
              >
                <span className="nav-icon">{item.icon}</span>
                {!collapsed && <span className="nav-label">{item.label}</span>}
                {active && <span className="nav-active-bar" />}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <button
            className="collapse-toggle"
            onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? '展开' : '收起'}
          >
            <Icon.Collapse dir={collapsed ? 'right' : 'left'} />
            {!collapsed && <span>收起侧栏</span>}
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <span className="topbar-crumb">{currentName}</span>
          </div>
          <div className="topbar-right">
            <div className="status-pill">
              <span className="status-dot" />
              <span className="status-text">服务运行中</span>
            </div>
          </div>
        </header>

        <div className="content">
          <Outlet />
        </div>

        <ToastContainer />
      </main>
    </div>
  );
}
