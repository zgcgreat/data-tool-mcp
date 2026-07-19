import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import type { UserConfig } from 'vite';
import type { IncomingMessage } from 'http';

// ============================================================================
// 部署路径配置
// ============================================================================
// - 生产环境: 通过 VITE_BASE_PATH 指定 SPA 子路径（需以 / 开头并以 / 结尾）。
//   未设置时回退到 '/data-tool-mcp-ui/'，需与 nginx.conf.template 中
//   location /data-tool-mcp-ui/ 保持一致。
// - 开发环境: 直接访问 http://localhost:5173, base 固定为 '/'。
//
// 后端 API 基址由 VITE_API_BASE 控制（见 .env），生产环境应填
// 公司网关路径 + /mcp-api（如 /data-tool-mcp/mcp-api），与 nginx 代理规则一致。
// ============================================================================

// 判断 SSE / Streamable HTTP 请求时使用的精确 URL（去掉 query string）
function pathnameOf(url: string): string {
  const idx = url.indexOf('?');
  return idx >= 0 ? url.slice(0, idx) : url;
}

// 后端 MCP 端点代理规则（开发环境）
// 与 nginx.conf.template 中 location ~ ^/(sse|message)(/.*)?$ 及
// location ~ ^/[^/]+/?$ 必须保持一致，否则会出现 "开发能跑、生产 404" 差异。
function shouldProxyToBackend(req: IncomingMessage): boolean {
  const method = (req.method || '').toUpperCase();
  const pathname = pathnameOf(req.url || '');

  // 1) SSE 路由: GET /sse, GET /{toolset}/sse
  if (method === 'GET' && (pathname === '/sse' || pathname.endsWith('/sse'))) {
    return true;
  }
  // 2) Message 路由: POST /message, POST /{toolset}/message
  //    用精确匹配避免误伤 /message-board、/foo/message-list 等无关路径
  if (method === 'POST' && (pathname === '/message' || /^\/[^/]+\/message$/.test(pathname))) {
    return true;
  }
  // 3) Streamable HTTP: POST / 或 POST /{toolset}/
  //    严格校验路径形态，避免匹配 POST /index.html、POST /favicon.ico 等
  if (method === 'POST' && (pathname === '/' || /^\/[^/]+\/?$/.test(pathname))) {
    // 进一步通过 Accept 头识别（text/event-stream 或 application/json）
    const accept = (req.headers.accept || '').toLowerCase();
    if (accept.includes('text/event-stream') || accept.includes('application/json')) {
      return true;
    }
  }
  return false;
}

export default defineConfig(({ command }): UserConfig => {
  const isBuild = command === 'build';
  // 生产构建允许通过环境变量覆盖 SPA 子路径；开发环境固定 '/'
  const base =
    isBuild && process.env.VITE_BASE_PATH
      ? process.env.VITE_BASE_PATH
      : isBuild
        ? '/data-tool-mcp-ui/'
        : '/';

  return {
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
            // antd 组件库 + 图标包(二者耦合较深,合并分包避免应用 chunk 体积偏大)
            'antd-vendor': ['antd', '@ant-design/icons'],
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
        // 后端 Admin API（/mcp-api 路由）
        '/mcp-api': { target: 'http://localhost:15000', changeOrigin: true },
        // MCP SSE 和 Streamable HTTP 端点代理（含 toolset 前缀路由）
        // 匹配: /sse, /{toolset}/sse, /message, /{toolset}/message, POST /, POST /{toolset}/
        // bypass 返回 undefined 表示走代理；返回字符串表示绕过代理交由 Vite 处理。
        '/': {
          target: 'http://localhost:15000',
          changeOrigin: true,
          bypass: (req: IncomingMessage) => {
            return shouldProxyToBackend(req) ? undefined : req.url;
          },
        },
      },
    },
  };
});
