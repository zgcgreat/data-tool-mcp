import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
import App from './App';

dayjs.locale('zh-cn');

// 生产环境部署在 /data-tool-mcp-ui 子路径,开发环境为根路径 /
const basename = import.meta.env.PROD ? '/data-tool-mcp-ui' : '/';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter basename={basename}>
      <ConfigProvider theme={{ token: { colorPrimary: '#1677ff' } }} locale={zhCN}>
        <App />
      </ConfigProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
