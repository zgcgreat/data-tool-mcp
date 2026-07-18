import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 生产环境部署在 nginx 子路径 /data-tool-mcp-ui/ 下;
// 开发环境直接访问 http://localhost:5173,base 为 /。
const base = process.env.NODE_ENV === 'production' ? '/data-tool-mcp-ui/' : '/';

export default defineConfig({
  plugins: [react()],
  base,
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // 代码分包:将第三方依赖拆分到独立 chunk,提升缓存命中率与首屏加载性能
    rollupOptions: {
      output: {
        manualChunks: {
          // React 核心(react/react-dom/react-router-dom)
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          // antd 组件库(体积较大,单独分包)
          'antd-vendor': ['antd'],
          // 工具库
          'utils-vendor': ['axios', 'dayjs'],
        },
      },
    },
  },
  server: {
    port: 5173,
    // 监听所有网卡（含 IPv4 127.0.0.1 与 IPv6 [::1]），便于本机/容器/局域网访问
    host: true,
    // 关闭 Vite 内置的 Host 头校验，避免 "403 Invalid host header / Blocked request"
    // 该 403 在 Host 既不是 localhost 也不是裸 IP 时触发（如经代理/隧道/容器转发访问）。
    // ⚠️ 仅建议在受信任的内网/开发环境使用；公网暴露请改为具体的白名单数组，例如：
    // allowedHosts: ['admin.example.com', '.internal', '127.0.0.1', '[::1]']
    allowedHosts: true,
    proxy: {
      '/mcp-api': { target: 'http://localhost:15000', changeOrigin: true },
      // MCP SSE 和 Streamable HTTP 端点代理（含 toolset 前缀路由）
      // 匹配: /sse, /{toolset}/sse, /message, /{toolset}/message, POST /, POST /{toolset}/
      '/': {
        target: 'http://localhost:15000',
        changeOrigin: true,
        bypass: (req) => {
          const url = req.url || '';
          const method = req.method || '';
          // SSE 路由: GET /sse, GET /{toolset}/sse
          // Message 路由: POST /message, POST /{toolset}/message
          // Streamable HTTP: POST /, POST /{toolset}/
          const isSse = url === '/sse' || url.endsWith('/sse');
          const isMessage = url.includes('/message');
          const isStreamable = method === 'POST' && (url === '/' || /^\/[^/]+\/?$/.test(url));
          if (isSse || isMessage || isStreamable) {
            return undefined; // 代理到后端
          }
          return url; // 不代理，交给 Vite 处理
        },
      },
    },
  },
});
