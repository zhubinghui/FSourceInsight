# M3.4b：企业发现初始分析迁LLM队列（本地）

## 状态和范围

仅主会话、本地合成数据；基线`master@8bf2563`未变，保留所有此前M3未暂存/未提交改动。没有提交、推送、SSH、生产访问、真实目录/供应商/SMTP调用或部署。**这是初始分析工作流切片，不是完整M3、实际worker验收或发布授权。**

[实施计划](../superpowers/plans/2026-09-18-m3-bounded-learning.md)先记录设计差异；操作及限制见[企业发现初始分析](../ops/startup-analysis.md)。

## 修复的旧行为

旧扫描在crawl/fast worker内同步运行模型；按“所有Grenoble未分析公司”选择目标而不是本次新增者，并在扫描时清零历史失败计数。异常路径也没有可靠的每来源事务隔离。仅把LLM调用换成delay会保留错误归属与丢任务窗口。

现路径：

1. 实际Admin扫描/定时任务仍走crawl队列；安全取数之后，在独立事务内保存真正新增的Company与来源绑定的queued job。
2. 既有slug/别名命中不新建job、不替其它来源补分析、不清零失败。SQL NULL及JSON null别名均兼容；某源第二个job写失败也整体回滚，不借下一个来源提交半成品。
3. 消息只传job ID，明确llm队列；`app.llm.startup_tasks`显式注册。状态/派发间隔先持久化，消息失败由有界扫描补派，而不是HTTP同步模型或重跑全表。
4. 认领只对queued生效，持久claim身份先于调用；重复消息、claim/result提交ACK丢失、返回迟到均不能补充一次付费执行。
5. 持久输入hash绑定source/company ID、输入代次、版本、时间和有效prompt；来源URL/type/启用或公司人工数据改变时检查点拒绝，SQL列+1防ORM陈旧对象丢失代次。正常统计变化不撤权。
6. `LLMClient.analyze_company(..., discovery_job=...)`在缓存前检查job/消息，账本在每次付费时重查当前配置与输入。全局金额/计费上界仍生效；预留独立于公司事务，供应商最多3次/每配置一次，未知用量停止fallback而保留费用。
7. 最终只填初始分析及revision，不覆盖人工数据。未知/失联工作过期blocked，不自动付费接管。终态无重开入口，普通扫描不能复位；旧手动refresh不是这个协议的安全重试。

## 网络、时限、可见性

- 新目录出口复用真实SafeFetcher及外部fetch_network测试：单配置host，30秒/6请求、单页/传输512KiB、总2MiB，robots/IP/TLS/重定向门禁；无直连fallback。旧目录解析保留，不能冒称新闻质量门禁或OS沙箱。
- 每轮最多50来源、每源1000个提取条目/20个新公司、别名完整扫描4096个SQL非NULL行。分页/来源调度并非完整或公平覆盖保证。模型只收冻结的短元数据，不抓主页或读学习证据卷；不再凭空把未知总部填为Grenoble。
- queued有效期24小时；running至多180秒并受原期限限制；beat每60秒恢复最多50个到期条目。派发资格持久化，至少间隔120秒，整秒存储保守留裕量。
- 慢DB锁定读取后也重查期限，再准入/应用；**仍没有SQL COMMIT、SDK、整轮扫描的硬deadline或远端取消**。现有LLM worker资源不增加，本切片没有新增task级软硬时限。
- Admin只读最近50条，或从账本/行链接按ID查询旧条目；no-store、角色/CSRF、固定503、转义/有界标签。损坏输入不拿原文标签冒充正常绑定；job状态只是历史执行，不是验证/发布许可。
- job保留短元数据及hash，24小时不是物理删除期限。hash不是签名或全库回滚保护；没有补齐其它模型/手动/旧代码的暴露历史，不能扩大受限holdout的独立性范围。

## 数据变更

Expand-only `a2f6d9b3107c`（父`f8b64d2c901e`）：

- `startup_analysis_job`，可空Company/StartupSource FK（业务行删除SET NULL；原ID保留在输入中）、公司唯一约束、状态/派发与来源索引。
- Company及StartupSource增加默认0的 `analysis_generation`；默认值不回填旧job或认证历史。
- `llm_reservation.startup_analysis_id`可空FK及索引，旧金额/状态/关联NULL不变。
- 降级拒绝删表/清审计。旧程序及bulk SQL不理解这些代次/准入，不可透明混跑/回滚；未来部署要另授权、审价、备份、实际候选门禁和协调停止旧付费调用方。

## TDD与故障证据

新增公共seam测试：

- `tests/test_crawlers/test_startup_analysis.py`
- `tests/test_crawlers/test_startup_reliability.py`
- `tests/test_crawlers/test_startup_boundaries.py`
- `tests/test_crawlers/test_startup_audit.py`
- `tests/test_ops/test_startup_analysis_migration.py`

全部沿实际Admin、生产scan/analyze/recover、公开LLM方法及Alembic；只在外部DNS/socket/TLS、SDK、Celery传输、OS时间和DB故障/提交确认边界替换。没有mock内部所有权/预算/抽取或新增测试业务API。

真实red→green包括：旧requests不能经过受控网络；取数收口后旧扫描确实同步调用模型并挑选历史公司；缺新迁移；合法JSON null别名被误拒；缺账本精确链接及坏JSON导致状态页崩溃；整秒截断缩短重派间隔；最后锁定读取跨deadline后仍付费或应用。其余拒绝/权限/费用回归有些直接绿色，不冒称每一项都单独复现旧缺陷。

测试装配错误单列：初次User/LLMConfig字段及CSRF假设不符合仓库；fixture模型输出须满足真实company_analysis契约；create首次遗漏prompt必填recent_news，通过仅合成异常trace定位并补None。提交ACK故障起初因ORM弱引用误命中后续dispatch提交，改在before_commit标记目标再于after_commit丢确认。非Admin切换改真实HTTP登录，避免旧ORM账号脱离session。均不通过修改业务断言掩盖问题。

第一轮全套 `m34b-full-01.log` 为**122失败/864通过/20跳过**：新增测试在Celery实例patch绑定方法，undo留下实例属性，遮蔽旧学习测试对类send_task的替换。最小顺序探针复现；改为Celery类方法外部边界，Admin scan也使用真实Task.delay，4个顺序探针绿色且teardown无残留。没有改旧学习业务/测试绕过。

第二轮 `m34b-full-02.log` **986通过/20跳过/9554 warnings，534.49秒**；这是最终慢查询deadline补强前的阶段结果，不能充作最终代码验证。随后新增两条实际DB读后时间推进回归，复现过期准入/应用，并补最后检查点。

最终验证：

- **988 passed / 20 dedicated-MySQL skipped / 9574 warnings / 548.86秒**；日志`/tmp/fsi-m3-izjIZv/m34b-full-03.log`。无30秒faulthandler超时转储。
- 新增**64离线测试**；最终专门子集64 passed /705 warnings/53.43秒，`startup-focused-final.log`。之前199项公司/LLM相关子集为最终deadline补强前阶段结果。
- 218 Python AST、48 Jinja模板、唯一Alembic head `a2f6d9b3107c`、指定flake8 E9/F和`git diff --check`通过。第一次静态统计漏根wsgi.py及2个邮件模板，已纠正口径；不是源文件丢失。
- 额外扩大静态范围时，`admin.py`末尾test-email函数的User导入和`celery_app.py`的db导入报两项F401；已核实HEAD也有相同未使用导入，本轮不改既有代码，不宣称全仓库lint零告警。`m34b-static-final.log`保留该扩大扫描结果；新增文件及其余指定核心文件检查通过。
- 一项新专用MySQL门禁加到既有19项；20项全部skip，不把新增测试存在或SQL打印算服务通过。当前再次确认Docker socket不可用、PATH无mysqld/redis-server；未启动任何服务。

日志均在`/tmp/fsi-m3-izjIZv/`：`startup-producer-red-02.log`、`startup-queue-red.log`、`startup-queue-green-02.log`、`startup-reliability-01.log`、`startup-migration-red.log`、`startup-migration-green.log`、`startup-boundaries-01.log`、`startup-audit-red.log`、`startup-spacing-red.log`、`startup-order-red.log`、`startup-order-green.log`、`startup-deadline-red.log`及上述全套日志。保留失败日志，不覆盖或改称通过。

## 未验证与后续

- `tests/integration/test_mysql_m0.py`同步新head，并新增专用MySQL下真实扫描、并发认领及来源ABA付费后fence的门禁；**全部20项尚未运行**，离线MySQL DDL/SQLite不是MySQL通过。
- Docker socket/本地MySQL与Redis服务仍不具备先前所需隔离环境；无真实broker、prefork、软硬杀、ACK网络丢包、OOM/长期容量证据。模拟SystemExit/时间/COMMIT异常不是实际进程失联测试。
- 未完成每源扫描任务拆分、扫描请求自身outbox、统一due调度、全部公司refresh迁移、完整付费恢复、学习worker实际挂载/容量或通用RSS/分页/多列表留出。
- **M3仍未完成，部署未授权。** 原学习候选仍不激活、不生成Article/文章LLM工作。
