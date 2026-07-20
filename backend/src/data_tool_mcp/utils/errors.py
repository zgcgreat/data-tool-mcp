"""统一的错误消息格式化工具。

将 SQLAlchemy / DBAPI 等原始异常消息转换为对用户友好的提示,
剥离技术细节链接(如 https://sqlalche.me/e/20/xxx)与冗余的
SQL/参数回显,避免泄漏内部信息。

设计原则:
1. 剥离 sqlalche.me / docs.python.org 等技术文档跳转链接
2. 提取核心错误描述(去除 [SQL: ...] [parameters: ...] 等内部回显)
3. 根据异常类型补充友好提示(语法错误 / 表不存在 / 权限不足等)
4. 保持原始异常的可用性 — 仅格式化面向用户的 message
"""

from __future__ import annotations

import re
from typing import Any

# 常见的 SQLAlchemy / DBAPI 文档链接前缀,需从消息中剥离
_DOC_LINK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\s*\(Background on this error is at: https?://\S+\)?\.?\s*", re.IGNORECASE),
    re.compile(r"\s*https?://sqlalche\.me/e/\S+\.?\s*", re.IGNORECASE),
    re.compile(r"\s*\(Background on this error at: https?://\S+\)?\.?\s*", re.IGNORECASE),
]

# 内部回显块: [SQL: ...] [parameters: ...] [context: ...]
_INTERNAL_BLOCK_RE = re.compile(
    r"\s*\[(?:SQL|parameters|context|key|cause)\s*:[^\]]*\]\s*",
    re.IGNORECASE | re.DOTALL,
)

# Python 异常类名前缀(如 "(pymysql.err.OperationalError)" / "(sqlite3.OperationalError)")
# 注意: 实际 SQLAlchemy 异常格式为 (<fully.qualified.ClassName>),括号内无空格;
# DBAPI 错误码格式 (1109, "Unknown table ...") 含逗号与引号,不会被此正则匹配。
_EXC_CLASS_PREFIX_RE = re.compile(r"^\s*\([a-zA-Z][a-zA-Z0-9_.]*\)\s*")

# 数据库供应商错误码格式 (1109, "Unknown table ...") -> 提取 message 部分
_DBAPI_CODE_RE = re.compile(r"^\s*\(\d+,\s*\"?(.*?)\"?\)\s*$", re.DOTALL)


def _strip_doc_links(message: str) -> str:
    """剥离 sqlalche.me 等技术文档跳转链接。"""
    result = message
    for pattern in _DOC_LINK_PATTERNS:
        result = pattern.sub("", result)
    return result


def _strip_internal_blocks(message: str) -> str:
    """剥离 [SQL: ...] [parameters: ...] 等内部回显块。"""
    return _INTERNAL_BLOCK_RE.sub(" ", message)


def _strip_exc_class_prefix(message: str) -> str:
    """剥离异常类名前缀,如 (pymysql.err.OperationalError)。"""
    return _EXC_CLASS_PREFIX_RE.sub("", message)


def _extract_dbapi_message(message: str) -> str:
    """从 (1109, "Unknown table ...") 格式中提取引号内的描述。"""
    match = _DBAPI_CODE_RE.match(message)
    if match:
        return match.group(1)
    return message


def _classify_error(exc: Exception, cleaned_message: str) -> str:
    """根据异常类型与消息内容生成友好提示。

    返回的字符串会附加在 cleaned_message 之前,引导用户排查。
    """
    msg_lower = cleaned_message.lower()
    exc_type_name = type(exc).__name__

    # 友好提示仅在能识别时附加,避免无谓的"内部错误"前缀
    if "operationalerror" in exc_type_name.lower():
        if (
            "unknown table" in msg_lower
            or "doesn't exist" in msg_lower
            or "does not exist" in msg_lower
            or "no such table" in msg_lower
        ):
            return f"数据表不存在: {cleaned_message}"
        if "access denied" in msg_lower or "permission" in msg_lower:
            return f"数据库访问权限不足: {cleaned_message}"
        if (
            "lost connection" in msg_lower
            or "server has gone away" in msg_lower
            or "connection" in msg_lower
            or "can't connect" in msg_lower
            or "cannot connect" in msg_lower
        ):
            return f"数据库连接异常: {cleaned_message}"
        if "unknown column" in msg_lower or "no such column" in msg_lower:
            return f"字段不存在: {cleaned_message}"
        return f"数据库操作失败: {cleaned_message}"

    if "programmingerror" in exc_type_name.lower():
        if "syntax" in msg_lower:
            return f"SQL 语法错误: {cleaned_message}"
        if (
            "unknown table" in msg_lower
            or "doesn't exist" in msg_lower
            or "does not exist" in msg_lower
            or "no such table" in msg_lower
        ):
            return f"数据表不存在: {cleaned_message}"
        if "unknown column" in msg_lower or "no such column" in msg_lower:
            return f"字段不存在: {cleaned_message}"
        return f"SQL 执行错误: {cleaned_message}"

    if "integrityerror" in exc_type_name.lower():
        if "duplicate" in msg_lower or "unique" in msg_lower:
            return f"唯一约束冲突(数据已存在): {cleaned_message}"
        if "foreign key" in msg_lower or "constraint" in msg_lower:
            return f"外键或约束冲突: {cleaned_message}"
        return f"数据完整性错误: {cleaned_message}"

    if "timeouterror" in exc_type_name.lower() or "timeout" in msg_lower:
        return f"查询超时: {cleaned_message}"

    if "valueerror" in exc_type_name.lower():
        # 业务层 ValueError(如 missing 'sql' parameter) 保持原样
        return cleaned_message

    # 兜底:已清洗过的消息
    return cleaned_message


def format_error_message(exc: Exception) -> str:
    """将异常转换为对用户友好的错误消息。

    处理步骤:
      1. str(exc) 原始消息
      2. 剥离异常类名前缀 (pymysql.err.OperationalError)
      3. 剥离 DBAPI 错误码外层括号 (1109, "...")
      4. 剥离 [SQL: ...] [parameters: ...] 等内部回显
      5. 剥离 sqlalche.me 等技术文档链接
      6. 根据异常类型添加友好前缀
    """
    raw = str(exc)
    if not raw:
        return type(exc).__name__

    cleaned = _strip_exc_class_prefix(raw)
    cleaned = _extract_dbapi_message(cleaned)
    cleaned = _strip_internal_blocks(cleaned)
    cleaned = _strip_doc_links(cleaned)
    # 折叠多余空白
    cleaned = " ".join(cleaned.split()).strip()

    # 清洗后为空(如原始消息仅含链接) → 直接返回异常类名,不再附加友好前缀
    if not cleaned:
        return type(exc).__name__

    return _classify_error(exc, cleaned)


def format_exception_detail(exc: Exception) -> dict[str, Any]:
    """构造统一的错误响应体。

    返回包含 error_type / message 两个字段的 dict,
    可直接作为 HTTPException(detail=...) 或 JSONResponse 的 content。
    """
    return {
        "error_type": type(exc).__name__,
        "message": format_error_message(exc),
    }
