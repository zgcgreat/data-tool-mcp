-- 表结构迁移脚本：清空旧表（含 departments / api_keys / dept_id 列），重启后端后自动创建新表结构
--
-- 使用方法：
--   mysql -h <host> -P <port> -u <user> -p <database> < docker/migrate-rebuild.sql
--
-- 执行后：
--   1. 旧表全部删除（departments / sources / tools / toolsets / api_keys）
--   2. 重启后端服务，Base.metadata.create_all 会自动按新 schema 创建表
--      （新表：sources / tools / toolsets / mcp_request_logs，均使用 system_id + environment 双维度隔离）
--   3. 也可直接执行 docker/init-mysql.sql 手动创建新表
--
-- ⚠️ 警告：此脚本会删除所有数据，请确认无需保留后执行！

-- 关闭外键检查，避免表间依赖导致 DROP 失败
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS api_keys;
DROP TABLE IF EXISTS toolsets;
DROP TABLE IF EXISTS tools;
DROP TABLE IF EXISTS sources;
DROP TABLE IF EXISTS departments;

SET FOREIGN_KEY_CHECKS = 1;

-- 完成。现在可以：
--   方式 A（推荐）：重启后端服务，代码自动创建新表
--   方式 B：手动执行 docker/init-mysql.sql 创建新表
