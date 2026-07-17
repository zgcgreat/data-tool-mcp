FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

# 创建非 root 用户并切换
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

# 健康检查：探活后端 /mcp-api/health 端点
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:5000/mcp-api/health', timeout=5).read(); sys.exit(0)" || exit 1

ENTRYPOINT ["toolbox", "serve"]
CMD ["--address", "0.0.0.0", "--port", "5000"]
