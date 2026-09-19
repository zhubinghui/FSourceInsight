# M3.1a：全局LLM预留与对账（本地切片）

## 状态

- 起点`master@8bf2563`；保留09-18审阅/计划文档。用户已确认M3含最小独立验证与可靠执行前置，主会话单写者/TDD。
- **只完成M3.1a的本地实现，不是整个M3完成。** Agent/来源/会话子预算、学习状态机、独立留出、可靠派发和专用worker仍未实现。
- 未提交、推送、SSH、部署或运行生产迁移；无真实新闻、LLM、邮件或子代理调用。
- 本轮新head `a8d31c5e7902`。真实MySQL/实际镜像尚未验证，旧09-11发布结果不能证明本次代码。

## 已交付

- 每次付费前提交独立预留，配置必须有可信的价格及计费input/output上界；不以tokenizer估计冒充计费上界。
- 同数据库多个客户端/线程争抢最后余额只能一笔进入供应商；结算与独立usage同事务，不提交外层Article业务。
- 未知用量、超时、崩溃或准入COMMIT确认丢失保留占用；跨日不自动释放。结算失败不fallback再付费。
- fallback重新准入；缓存有效结果不消耗新预留；Decimal向上取整，usage与reservation不重复计算。
- 固定每次provider/model/端点hash/价格/上界，后续配置修改不能改写本次审计。
- supplier usage越界记overrun，超出旧费用列精度的大额仍保留在新账本；阻断新付费。对账后旧的、已被usage推翻的上界仍不能再授权调用。
- Admin录入/确认计费上界；用量页增加未决总额/预留列表/人工最终账单对账。对账不可覆盖，原usage不修改；权限/CSRF/状态竞争、转义、SQL失败固定消息及私有响应头。
- 增量迁移只加两列/三表，不猜测旧计费权限、不改provider或费用；禁止破坏性降级。

这里的成本控制依赖管理员审核的供应商计费契约，不证明真实供应商一定履约；无可靠上界则拒绝。`LLM_DAILY_BUDGET_USD=0`仍要求合法计费契约。详见[操作与启用前置](../ops/llm-budget-accounting.md)。

## TDD与验证

真实red→green包括：
- 原软预算允许余额0.001时付费；新预留在付费前拒绝。
- 跨线程外部调用在途时第二客户端仍付费；数据库预留后拒绝，实际结算后额度释放。
- 无Admin上界控件/对账列表、路由变更后审计丢原provider/model。
- total_tokens与输入/输出不一致仍被当正常；改为未知费用，不缓存。
- 大额越界写旧NUMERIC精度失败导致审计回滚；完整异常金额现在保存在新账本。
- 对账后仍用已被实际usage推翻的旧上界再次付费；现在付费前拒绝，须明确重审兼容上界。
- 新迁移缺失、账本页面缺私有响应头。

已有实现直接通过的回归另行计数，不冒称每项都先失败：未知费用跨日、数据库写入故障、准入/结算COMMIT后丢ack、缓存免费、Decimal微额、旧用量计入、未决不可自动释放、权限/非法金额/重复对账/SQL失败原子性等。

工具/fixture偏差：最初NER默认合成响应不是JSON，调整为合法响应后明确复现未阻断付费；并发fixture最初阻塞两个请求，改为只阻塞第一请求后明确复现竞争；旧fallback测试配置无价格/上界，新增已知合成计费条件但保留原路由/次数断言。一次diff检查提示EOF多余空行已修正。

最终命令：

```sh
env -i PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin HOME="$HOME" \
  PYTHONDONTWRITEBYTECODE=1 /tmp/fsi-m3-izjIZv/venv/bin/python \
  -m pytest tests/ -q --disable-warnings -p no:cacheprovider
```

结果：**729 passed / 18 skipped，224.09秒**。18项全部是明确要求专用MySQL的测试，不是通过；其中新加2项并发余额认领/结算故障，head与合成计费配置同步更新。LLM+新迁移子集139通过。最终日志 `/tmp/fsi-m3-izjIZv/full-tests-final.log`。

静态收尾：181个Python AST、47个Jinja模板编译、指定flake8、git diff --check、新文档链接/围栏通过；Alembic单head a8d31c5e7902。

隔离依赖：Python3.12.14、Flask3.1.3、SQLAlchemy2.0.54、Alembic1.20.0、LiteLLM1.101.0、pytest9.1.1。与旧环境版本不同，未修改requirements，不拿新解析依赖冒充生产镜像。

本地Docker上下文为desktop-linux，但`/Users/zhubinghui/.docker/run/docker.sock`不存在，PATH无mysqld/redis-server；未擅自使用远端或生产服务。SQLite并发和离线MySQL DDL不替代真实MySQL行锁/隔离验证。

## 下一切片与风险

1. 在学习会话落地时，将Agent每日/会话/来源额度及持久attempt身份接入同一预留事务，避免另建软预算。
2. 然后按已确认计划实现Admin启动/状态/取消、受限学习、独立留出、可靠学习队列。仍不激活候选，不改日常legacy路由。
3. 对账确认是管理员的最终账单/执行已停止声明，系统不能自行证明外部供应商不会延迟计费。无依据不得释放。
4. 旧日志只纳入相应UTC当日预算，不伪造过去的完整预留历史；已有未定价旧日志需要部署前核账。未提供旧日志自动/批量对账。
5. 迁移后的旧配置上界NULL会阻断新的付费请求；真实部署需先审价、暂停全部付费调用方、备份/隔离门禁和受控切换。旧代码回滚不执行预算协议，不能只保留表就恢复旧付费worker。
6. 当前只验证了准入/会计行为；不保证文章/模型调用exactly-once、全文章硬期限、长时间性能或生产成本/容量。完整M3仍进行中。
