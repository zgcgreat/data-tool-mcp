import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import './styles/global.css';
import AppLayout from './components/Layout';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const QuickConnect = lazy(() => import('./pages/QuickConnect'));
const Sources = lazy(() => import('./pages/Sources'));
const Tools = lazy(() => import('./pages/Tools'));
const QueryConsole = lazy(() => import('./pages/QueryConsole'));
const McpStats = lazy(() => import('./pages/McpStats'));

function PageLoader() {
  return <div style={{ textAlign: 'center', padding: 80, color: '#888' }}>加载中...</div>;
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<Suspense fallback={<PageLoader />}><Dashboard /></Suspense>} />
        <Route path="quick-connect" element={<Suspense fallback={<PageLoader />}><QuickConnect /></Suspense>} />
        <Route path="sources" element={<Suspense fallback={<PageLoader />}><Sources /></Suspense>} />
        <Route path="tools" element={<Suspense fallback={<PageLoader />}><Tools /></Suspense>} />
        <Route path="query" element={<Suspense fallback={<PageLoader />}><QueryConsole /></Suspense>} />
        <Route path="mcp-stats" element={<Suspense fallback={<PageLoader />}><McpStats /></Suspense>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
