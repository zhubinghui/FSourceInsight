# M3.2d：学习派发身份与有界恢复（本地）

## 状态

仅主会话、本地合成验收，基线仍`master@8bf2563`；所有先前未暂存/未提交改动保留。没有提交、推送、SSH、生产访问、真实网页/模型/SMTP调用、启动服务或部署。**不是完整M3、可靠付费接管或实际服务验收。**

[计划](../superpowers/plans/2026-09-18-m3-bounded-learning.md)先记录范围及后续澄清；[操作说明](../ops/crawl-learning.md)同步最新迁移与消息兼容边界。延续[2c生命周期](2026-09-19-m32c-learning-lifecycle.md)，不重做已完成的初始企业分析迁队列。

## 行为

- 新增`app/crawlers/_learning_delivery.py`。`learning-delivery.v1`派发键绑定会话ID、不可变输入hash、已消耗轮次、retry审计计数；实际消息为`[session_id, delivery_key]`，显式`crawl_learn`队列。键是fingerprint/fence，**不是权限或新付费租约**。
- 原消息不能跨轮次或人工retry认领当前意图；未取得认领的旧错误也不能关闭有效新queued。已有attempt继续由预分配UUID/状态/轮次fence保护，包括claim COMMIT成功而ACK丢失。
- 一次worker仍可最多三轮，但只有自己成功提交训练拒绝后得到的continuation键才能继续。结果提交ACK丢失不猜测继续；若DB实际保留了下一轮queued，由恢复器发送该阶段的新消息。此时是原委托剩余授权轮次，不是重复已执行的付费attempt，也不是人工零准入retry。
- `dispatch_due_at`在新会话、成功拒绝进入下一轮、受控retry的业务事务内置就绪；派发槽位先提交，再调用broker。同阶段重复HTTP/恢复共享间隔，按记录UTC准入时刻floor(now)+31秒保存，避免整秒截断把30秒缩短。失败/提交ACK丢失也不热重发。
- 这是**槽位准入时间的最小间隔**，不是broker物理发送速率限制或排它publisher租约。慢COMMIT/消息RPC可越过时窗、晚到重复；消费者仍须fence。没有端到端SQL/RPC硬deadline、即时送达或exactly-once承诺。
- recover最多选择50条到期queued、过期active或缺派发状态的active；非到期running不占该选择。验证过期收敛仍保留。缺状态的旧active隔离blocked，running/终态不自动重新付费，未知预留不释放。没有新增公平调度、全局分布式lease或未知费用接管。
- 认领在证据/提示/暴露准备后再次核期限；付费在权威读取和最后配额/重复配置查询后再核期限。原180秒包含排队/派发等待，不延长。模型后、解析前与结果保存既有检查继续有效；后续SQL写/COMMIT/SDK仍非硬deadline。
- 关闭异常自身失败和recover DB失败用固定日志收敛；不抛出原私有SQL异常让任务框架打印，durable状态留待恢复。已知history损坏先隔离blocked；不能因损坏counter使键失配就一直留queued。读取失败不等于已知损坏，旧错误不得借此关闭有效新意图。
- Admin显示协议、当前queued消息指纹和派发资格时间，不称broker确认；无键/时间/计数写入表单。权限、CSRF、private headers与严格表单检查不变。无Article写入/文章LLM派发/候选激活或留出范围扩张。

## 数据与兼容

Expand-only `b5d81e6a430f`，父`a2f6d9b3107c`：仅添加可空、无默认值的`crawl_repair_session.dispatch_due_at`及`idx_repair_dispatch_due(state, dispatch_due_at)`。旧行保持NULL；旧费用、input hash、轮次/retry、期限与终态不改，不补造历史派发资格。downgrade拒绝破坏性删除。

- 新进程忽略旧单参数消息；当前代码不认领、准入或应用缺派发状态的旧active，且人工retry不能补该缺口。旧终态/候选/验证仍可读；不把历史状态改签成新执行权限。
- recipe/prompt/暴露解释未变，保持`crawl-learning.v3`/`learning-exposure.v1`；派发协议单独版本化。due不是新的暴露完整性证明。
- 旧worker/旧paid caller并不理解此fence，**不能混用或把回滚当自动兼容**。将来迁移/切换需要单独授权、备份、协调停止旧调用方；保留全部预留/暴露/审计，不清队列或重置状态解决兼容问题。
- hash不是签名；无完整DB回滚/一致性篡改保护，不声明跨系统暴露覆盖。

## TDD与验证

新增31离线测试：

- `tests/test_web/test_learning_delivery.py`
- `tests/test_web/test_learning_delivery_failures.py`
- `tests/test_ops/test_learning_delivery_migration.py`

入口为真实Admin表单、实际learn/recover、公共LLM调用链和Alembic。仅替换外部Celery传输/SDK、OS时钟与文件stat、DB故障/提交确认；没有内部授权、预算或历史helper mock。SystemExit是合成故障，不是实际OS worker kill。

独立红灯：旧消息执行新retry；重复POST/恢复连续发送；缺migration；证据/最后配额查询跨deadline仍准入（认领则错误消耗轮次）；错误收敛自身SQL失败暴露私有异常；缺派发UI。其余边界有些直接通过，不冒称全部单独红灯。旧测试只按新协议推进32秒及由真实recover取得下一轮消息，保留原费用/所有权/成功/失败断言。已知损坏history立即blocked的旧断言仍保留。

结果：

- 关联阶段169 passed /3709 warnings/292.69秒，`delivery-focused-03.log`；在最终两条保留费用/历史终态回归之前。
- 最终专门子集 **31 passed /575 warnings/33.65秒**，`delivery-focused-final.log`。
- 完整 **1019 passed /20 dedicated-MySQL skipped /10149 warnings/570.29秒**，`m32d-full-01.log`；没有30秒faulthandler超时转储。
- **223 Python AST /48 Jinja模板**，唯一head`b5d81e6a430f`；本轮文件及相关现有文件的flake8 E9/F、`git diff --check`通过，`m32d-static-01.log`。不是全仓库lint无告警；上轮记录的两项既有F401未改。
- 全套后仅完善操作/计划/审计及Admin“槽位而非物理发送速率”解释文案；该HTTP回归1 passed /22 warnings/3.14秒（`delivery-copy-final.log`），11份文档/26本地链接/围栏/48模板/最终日志检查通过（`m32d-docs-final.log`）。
- 已有MySQL学习并发门禁同步双参数消息、单槽位发布和新head；**20项仍全部未运行**，本轮未新增/冒称MySQL服务通过。真实候选worker的mount/UID/prefork/broker/ACK/软硬限时/OOM/长期容量均未验收。

日志位于`/tmp/fsi-m3-izjIZv/`；保留`delivery-fence-red.log`/`-green.log`、`delivery-spacing-red.log`/`-green.log`、`delivery-migration-red.log`、`delivery-deadline-red.log`、`delivery-storage-red.log`、`delivery-focused-01/02/03.log`及最终日志。`focused-02`为UI红、其余28通过；不改称全绿。一次精确编辑因重复匹配被工具拒绝，重试加唯一上下文，无部分写入。

## 剩余门禁

Docker socket/本地MySQL/Redis隔离服务仍不可用，未用生产替代。M3仍缺完整可靠恢复、其它公司refresh/扫描请求outbox、通用RSS/分页/多列表留出、全系统暴露范围、实际服务/资源容量门禁。M2发布/日常路由仍独立未完成。**本轮无任何启用或部署授权。**
