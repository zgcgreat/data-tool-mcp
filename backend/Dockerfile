# ---- Stage 1: builder ----
# 编译期安装依赖到 /install,与运行期镜像隔离,减小最终镜像体积
FROM python:3.12-slim AS builder

# 可选 extras: docker build --build-arg EXTRAS=postgres,mysql,redis .
# 默认仅安装核心依赖(含 sqlite + mysql config store 驱动)
ARG EXTRAS=""
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# 先复制依赖清单,利用 Docker layer 缓存
COPY pyproject.toml ./
COPY src/ src/

# 安装到独立 prefix /install,便于第二阶段拷贝
RUN if [ -n "$EXTRAS" ]; then \
        pip install --target=/install ".[${EXTRAS}]"; \
    else \
        pip install --target=/install .; \
    fi

# ---- Stage 2: runtime ----
# 精简运行期镜像,仅包含 Python 解释器 + 依赖 + 源码
FROM python:3.12-slim AS runtime

# 运行期环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/install \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 从 builder 拷贝已安装的依赖(不含 .cache、源码 egg-info 等)
COPY --from=builder /install /install

# 拷贝项目源码(仅 src/ 必需,main.py 为可选便捷启动器)
COPY src/ src/
COPY pyproject.toml ./

# 创建非 root 用户并切换(最小权限原则)
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && chown -R appuser:appuser /app /install

USER appuser

EXPOSE 5000

# 健康检查:使用 /live 端点(轻量级,不查依赖)
# /ready 用于 K8s readinessProbe(查 ConfigStore + ResourceManager)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:5000/live', timeout=5).read(); sys.exit(0)" || exit 1

ENTRYPOINT ["python", "-m", "data_tool_mcp.cli.main", "serve"]
CMD ["--address", "0.0.0.0", "--port", "5000"]
