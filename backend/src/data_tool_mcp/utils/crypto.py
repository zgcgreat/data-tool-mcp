"""加解密工具 — 应用层密码/敏感数据加解密。

本模块是项目中**唯一**的加解密入口，集中所有加密相关逻辑，便于企业部署时
替换为内部加解密实现（如国密 SM4、KMS 服务等）。

## 替换指南

企业替换加解密实现时，只需修改本文件，无需改动其他模块。保持以下 4 个
公开函数签名不变即可：

    encrypt(plaintext: str) -> str          # 加密明文 → 密文
    decrypt(ciphertext: str) -> str         # 解密密文 → 明文
    is_encrypted(value: str) -> bool        # 判断字符串是否是有效密文
    normalize_password_for_storage(raw: str) -> str
                                            # 归一化密码：空→空 / 已加密→保留 / 明文→加密

## 默认实现说明

默认基于 `cryptography.Fernet`（AES-128-CBC + HMAC-SHA256）：
- 密钥来源：环境变量 `TOOLBOX_ENCRYPTION_KEY`（必须是 urlsafe-base64 编码的 32 字节）
- 开发回退：未配置时使用固定开发密钥（仅限本地开发，生产必须配置）

## 国密 SM4 替换示例

替换为 SM4-CBC 时，可参考以下骨架：

    from gmssl import sm4  # 或企业内部 SM4 库
    _KEY = os.environ["TOOLBOX_SM4_KEY"].encode()  # 16 字节

    def encrypt(plaintext: str) -> str:
        iv = os.urandom(16)
        cipher = sm4.CryptSM4()
        cipher.set_key(_KEY, sm4.SM4_ENCRYPT)
        ct = cipher.crypt_cbc(iv, plaintext.encode("utf-8"))
        return base64.b64encode(iv + ct).decode("utf-8")

    def decrypt(ciphertext: str) -> str:
        raw = base64.b64decode(ciphertext)
        iv, ct = raw[:16], raw[16:]
        cipher = sm4.CryptSM4()
        cipher.set_key(_KEY, sm4.SM4_DECRYPT)
        return cipher.crypt_cbc(iv, ct).decode("utf-8")

    def is_encrypted(value: str) -> bool:
        try:
            decrypt(value)
            return True
        except Exception:
            return False

    # normalize_password_for_storage 无需修改（仅依赖上述三个函数）
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 密钥配置（默认 Fernet 实现）
# ---------------------------------------------------------------------------
_ENCRYPTION_KEY_ENV = "TOOLBOX_ENCRYPTION_KEY"
_DEFAULT_KEY_FALLBACK = "dev-only-key-do-not-use-in-production-0123456789"
_fernet = None


def _derive_dev_key() -> bytes:
    """从固定字符串派生开发回退密钥(仅限本地开发)。"""
    import hashlib
    return base64.urlsafe_b64encode(
        hashlib.sha256(_DEFAULT_KEY_FALLBACK.encode()).digest()
    )


def _import_fernet() -> Any:
    """导入 cryptography.Fernet,不可用时返回 None 并记录警告。"""
    try:
        from cryptography.fernet import Fernet
        return Fernet
    except ImportError:
        logger.warning("cryptography not available — passwords stored in plaintext")
        return None


def _resolve_encryption_key() -> bytes:
    """解析加密密钥:优先环境变量,回退到开发密钥。"""
    key_env = os.environ.get(_ENCRYPTION_KEY_ENV, "")
    if isinstance(key_env, str) and key_env:
        return key_env.encode()
    return _derive_dev_key()


def _try_create_fernet(Fernet: Any) -> Any:
    """尝试创建 Fernet 实例,失败返回 False 哨兵。"""
    try:
        return Fernet(_resolve_encryption_key())
    except Exception as exc:
        logger.warning("Fernet init failed (%s) — passwords stored in plaintext", exc)
        return False


def _create_fernet_from_env() -> Any:
    """根据环境变量创建 Fernet 实例,失败返回 False 哨兵。"""
    Fernet = _import_fernet()
    if Fernet is None:
        return False
    return _try_create_fernet(Fernet)


def _get_fernet() -> Any:
    """Lazy-initialize Fernet cipher for password encryption.

    企业替换为 SM4/KMS 时，此函数可删除，改为在 encrypt/decrypt 中直接使用
    企业加解密库。
    """
    global _fernet
    if _fernet is not None:
        return _fernet
    _fernet = _create_fernet_from_env()
    return _fernet


def validate_encryption_key() -> bool:
    """校验加密密钥是否已正确配置。

    Returns:
        True 表示密钥已配置且有效
        False 表示使用开发回退密钥（生产环境应警告）
    """
    key_env = os.environ.get(_ENCRYPTION_KEY_ENV, "")
    if not key_env:
        logger.warning(
            "TOOLBOX_ENCRYPTION_KEY 未配置，使用开发回退密钥。"
            "生产环境必须配置该环境变量，且多实例必须使用相同密钥，"
            "否则无法解密数据源密码。"
        )
        return False
    return True


# ---------------------------------------------------------------------------
# 公开 API — 企业替换时只需修改这三个函数的实现
# ---------------------------------------------------------------------------

def _do_encrypt(f: Any, plaintext: str, fallback: str) -> str:
    """执行实际加密,失败时返回 fallback。"""
    try:
        return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.warning("password encryption failed: %s", exc)
        return fallback


def _do_decrypt(f: Any, ciphertext: str, fallback: str) -> str:
    """执行实际解密,失败时返回 fallback。"""
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.warning(
            "解密失败（密钥不匹配或数据损坏）: %s。原样返回，可能导致数据源连接失败。",
            exc,
        )
        return fallback


def _try_decrypt(f: Any, value: str) -> bool:
    """尝试解密以判断是否为有效密文,成功返回 True。"""
    try:
        f.decrypt(value.encode("utf-8"))
        return True
    except Exception:
        return False


def encrypt(plaintext: str) -> str:
    """加密明文字符串，返回密文。

    若加密不可用（cryptography 未安装），返回明文（仅开发环境）。
    """
    if not plaintext:
        return ""
    f = _get_fernet()
    if not f:
        return plaintext
    return _do_encrypt(f, plaintext, plaintext)


def decrypt(ciphertext: str) -> str:
    """解密密文字符串，返回明文。

    若解密失败（密钥不匹配、不是密文），返回原值（兼容旧明文数据）。
    """
    if not ciphertext:
        return ""
    f = _get_fernet()
    if not f:
        return ciphertext
    return _do_decrypt(f, ciphertext, ciphertext)


def is_encrypted(value: str) -> bool:
    """判断字符串是否是有效密文（能被当前密钥解密）。

    用于编辑场景：用户未改密码时回传的值已是密文，存储时不应重复加密。
    """
    if not value:
        return False
    f = _get_fernet()
    if not f:
        return False
    return _try_decrypt(f, value)


def normalize_password_for_storage(raw: str) -> str:
    """归一化待存储的密码值。

    - 空字符串 → 空字符串（无密码）
    - 已是有效密文（编辑未改动密码） → 原样保留，不重复加密
    - 其他（新明文密码） → encrypt 加密后返回

    此函数无需企业替换实现，它仅依赖 encrypt/is_encrypted。
    """
    if not raw:
        return ""
    if is_encrypted(raw):
        return raw
    return encrypt(raw)


# ---------------------------------------------------------------------------
# 向后兼容别名 — 旧代码中的 encrypt_password / decrypt_password 仍可用
# ---------------------------------------------------------------------------
encrypt_password = encrypt
decrypt_password = decrypt