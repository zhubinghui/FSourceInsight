# OVH MySQL 验证与首批 M0 发布记录

## 授权/边界
用户明确允许登录 OVH 验证 SQL，验证后提交部署；后续功能与修复采用 TDD。本批仅发布已实现的首批 M0 修复，M0.5 和动态 Agent 尚未完成。

主机通过既有 SSH 别名 `france-vps` 访问，严格校验主机密钥；未读取私钥、生产 env 密钥值或数据库备份内容。直接 IP 首次连接因未匹配专用 IdentityFile 被拒绝，随后按本机明确配置使用同一主机别名成功。

## 只读盘点
- VPS `vps-babefee9`，目录 `/home/ubuntu/FSourceInsight`，部署前 `master@bf9cc61`、工作区干净。
- Docker 29.4.1 / Compose 5.1.3；FSourceInsight 的 web/worker/worker_fast/beat/mysql/redis 正常；web 仅 `127.0.0.1:8800`。同机其他应用不修改。
- 可用内存约 3.6 GiB，磁盘约 15 GiB；临时 MySQL 限 768 MiB/1 CPU，测试进程限 512 MiB/1 CPU，无宿主端口，专用 internal 网络/卷。
- 生产 MySQL **8.0.46**，revision **fd3132082a6b**，`llm_usage_log.task_type` 实际已为 **VARCHAR(50) NOT NULL**；company JSON/counter 列正确。
- 生产模型/数据库结构的只读 Alembic comparison：**0 differences**。未导出业务行、账户资料或 LLM 配置密钥。

## TDD 补强
新增 `tests/integration/test_mysql_m0.py`。仅在显式指定 disposable `m0-mysql` + `fsource_m0_validation` + `FSI_DESTRUCTIVE_TESTS=1` 时允许执行，不能用于生产库；测试网络仅允许该 MySQL 连接。

先运行“列已是 VARCHAR 时不得执行 ALTER”用例，确认原候选迁移失败；再为 `c821b4f7d901` 添加在线类型检查，复跑通过。离线 SQL 仍生成真实 Enum→VARCHAR 扩展语句，不修改旧 revision，不丢用量历史。

## 实机结果
在 VPS 上复用实际 MySQL 8.0.46 镜像启动隔离实例，以合成数据执行：

| 用例 | 结果 |
|---|---|
| 空库迁移到 head，模型 comparison 为空 | PASS |
| 已是 VARCHAR(50) 的部署型结构只推进 revision，不重复 ALTER | PASS（先 red 后 green） |
| 旧公司合法 JSON 文本迁移、非空计数列回填 | PASS |
| 旧 Enum 用量/Article FK/费用保留，新 digest/insight/company_analysis 可写 | PASS |
| MySQL 爬虫批内去重及重复运行 | PASS |
| MySQL trigger 模拟第二条写失败，整批回滚且日志终止 | PASS |
| 两个独立会话并发竞争同一外部 ID，保留一条且两个 run 正确结束 | PASS |

初始整组 **7/7 通过**，约 7 秒。生产 web 镜像依赖：Python 3.12.13、Flask 3.1.3、SQLAlchemy 2.0.51、Alembic 1.18.5、PyMySQL 1.2.0。

本地 `pytest tests/`：**49 passed + 7 skipped**（本地无 disposable MySQL；上面的 7 项已在 VPS 实跑，而非跳过视为通过）。CI 新增独立 MySQL service job，以 unittest 执行这 7 项；原 job 继续隔离 SQLite/HTTP/Compose 回归。

注意：旧 JSON 文本路径测试使用合法 JSON。任意旧 free-text 转 JSON 的历史数据清洗不在本批迁移中；生产库已为 JSON，不会重跑历史转换。

## 发布状态
- [x] 生产只读盘点、隔离 SQL 验证、针对性 red/green、本地全套回归。
- [ ] 提交/推送当前首批修复。
- [ ] 备份与回滚镜像记录；构建候选镜像并再次验证。
- [ ] 受控更新应用服务、前向迁移、上线只读冒烟。
- [ ] 清理本批临时资源、记录最终 ref/健康结果。

当前验证工作目录 `/home/ubuntu/fsi-m0-verify.EYVS00`；临时资源前缀 `fsi-m0-20260906100910`，与业务资源分开。临时测试密码文件只在服务器受限目录，既不读取值也不进入 Git。

执行细节见 [受控发布计划](../superpowers/plans/2026-09-06-ovh-m0-validation-deploy.md)。不得重跑旧 OVH 安装/dump 恢复脚本或使用 down -v。
