#!/bin/sh
set -e

# 分开部署时通过环境变量注入后端地址；默认指向同机 5000 端口的后端
export BACKEND_URL="${BACKEND_URL:-http://localhost:5000}"

# 校验 BACKEND_URL：必须以 http:// 或 https:// 开头
case "$BACKEND_URL" in
    http://*|https://*) ;;
    *)
        echo "ERROR: BACKEND_URL must start with 'http://' or 'https://'. Got: $BACKEND_URL" >&2
        exit 1
        ;;
esac

# 校验 BACKEND_URL：禁止包含可能注入 nginx 指令的危险字符
# （分号、大括号、换行、反斜杠、$、反引号、引号、空白等）
case "$BACKEND_URL" in
    *[;\{\}\\\$\"\`\'\ \	]*)
        echo "ERROR: BACKEND_URL contains forbidden characters that could inject nginx directives." >&2
        echo "       Forbidden: ; { } \\ \$ \" \` ' space tab" >&2
        echo "       Got: $BACKEND_URL" >&2
        exit 1
        ;;
esac

# 单独检测换行符（case 模式中以字面量换行书写）
case "$BACKEND_URL" in
    *'
'*)
        echo "ERROR: BACKEND_URL must not contain newline characters." >&2
        exit 1
        ;;
esac

# 用真实后端地址渲染 nginx 配置模板
envsubst '${BACKEND_URL}' \
  < /etc/nginx/conf.d/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
