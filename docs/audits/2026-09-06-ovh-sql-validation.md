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
- [x] 提交/推送 `ea96dde21f0713dc1e658bcb53eddf7cad3d4b88`（保留远端新增README署名后提交）；[CI run 34027261828](https://github.com/zhubinghui/FSourceInsight/actions/runs/34027261828) 常规与MySQL两个job均成功。
- [x] 备份与回滚镜像已记录；候选镜像再次通过7项MySQL、40模板、匿名权限/CSRF/打包边界检查。
- [x] 运维修复 `858a14b210c904bd844a61994100c2f4ef1644b1` 推送并部署；[CI run34028232722](https://github.com/zhubinghui/FSourceInsight/actions/runs/34028232722) 成功。保留首次自动回滚记录，第二次发布通过全部门禁。
- [x] 精确清理本批临时容器/卷/internal网络/测试密码目录；保留备份、回滚镜像和验证日志。

验证工作目录曾为 `/home/ubuntu/fsi-m0-verify.EYVS00`，临时资源前缀 `fsi-m0-20260906100910`；已核对label后只删除这些本批资源。测试密码目录已清理，值从未进入 Git。

备份目录 `/home/ubuntu/fsourceinsight-backups/m0-20260906100910`，gzip 大小 21,571,984 bytes，权限600，gzip完整性通过，SHA256 `95c75ce75e703715d33765b276ddccfc232f858737ebdbe7dd5d8c7d14f67bee`；未读取备份内容。

候选镜像 SQLAlchemy2.0.52/Alembic1.19.2 与旧镜像不同，因此额外在真实候选镜像（不挂载替换 app 代码）重新跑7项MySQL全部通过；web image `sha256:d5417017132e9152948ec7c619f64e7a31b36f6d887b929a5db21893d0e6ac6f`。发布前各 worker active/reserved/scheduled 都为0。

### 发布过程中的偏差与TDD修复
- `docker compose run` 默认interactive读走SSH bash-s剩余stdin：发现缺失完成标记后立即盘点，确认迁移成功、旧Web持续200、后台正常停止；改用服务器文件脚本，不盲目认定成功。
- 首次激活 10:36:29Z→10:36:34Z Web恢复，worker注册门禁失败，已按旧镜像自动回滚。只读RPC显示worker实际健康，任务名称带 `[rate_limit=10/m]` 后缀，严格比对造成误判。
- 新 CLI `scripts/check_worker_readiness.py` 用真实返回格式快照先red，修复后3项正/负例全green；在回滚后的实际worker上执行返回 LIVE_WORKERS_READY。门禁保留worker数量和必需任务检查，不是删除验收。
- 最终本地测试52通过，7项MySQL在最终候选镜像上再次全通过。生产代码release为858a14b，后续文档提交不改变运行代码；首次失败的记录保留。

## 最终部署结果
- 2026-09-06 **10:46:03Z→10:46:09Z** 完成第二次Web切换，约6秒；新的worker验收返回 `LIVE_WORKERS_READY`，所有六个服务运行正常。
- 最终web image：`sha256:892a51169dacb03bc66549ba04546ac057f9ae77e92aa096150898b9a7e40c8f`。
- 公网 `/`、`/health`、`/auth/login`、www `/health` 全200；匿名有效CSRF的settings POST及manage/admin GET正确302到登录，无账户修改。
- 生产数据库revision `c821b4f7d901`，只读 model diff=0；物理task_type列原本正确，因此本次仅推进迁移记录，未重写用量表。
- MySQL/Redis及同机所有其他应用容器ID与发布前一致；没有重启基础服务、改Caddy、手工触发付费LLM/爬取/邮件，正常既有后台服务已恢复。
- 应用镜像实际检查不含 `/app/.env`、Git或数据库dump；用户需要重新登录一次。管理员真实密码登录/浏览器视觉E2E未代替用户执行。
- 数据备份、旧应用image tags与rollback.compose.yml保留在上述备份目录；gzip完整性已验，不声称做过生产备份全量恢复演练。
- 后续仍需M0.5 LLM可靠性、Safe Fetch、schema/Agent等开发，继续TDD。

执行细节见 [受控发布计划](../superpowers/plans/2026-09-06-ovh-m0-validation-deploy.md)。不得重跑旧 OVH 安装/dump 恢复脚本或使用 down -v。
