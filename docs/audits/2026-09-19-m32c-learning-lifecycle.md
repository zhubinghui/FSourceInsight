# M3.2c：失败冷却、安全人工重试与检查点（本地）

本轮在M3.3b之后补生命周期缺口。**不是M3完成、付费任务接管或部署就绪。** 基线仍`master@8bf2563`，所有M3切片未提交；主会话单写者，没有子代理、生产访问、SSH、真实新闻/模型/SMTP或部署操作。

## 可见行为

- 学习执行进入`blocked/exhausted/cancelled`时，同事务记录至少六小时的同来源冷却，并关闭仍为calling的轮次。换capture、重复提交、消息重投不能清除冷却。不同来源不共享这个冷却，但仍共享Agent/总预算。
- 同capture仍返回原会话，不重领轮次/金额。新capture只有当前权限/证据/历史和冷却均允许时才能开启新委托。验证failed/inconclusive/stale不是本切片自动触发的学习失败冷却；不能把候选生成视为独立验证成功。
- blocked详情可显示“Request safe retry”：仅限**整个会话从未产生任何供应商预留**、原180秒期限未过、轮次未耗尽、当前权限/证据/历史有效。即使预留已settled/reconciled或金额为零也不允许人工重试。
- POST `/admin/sources/<source_id>/crawl-config/learning/<identity>/retry`仅接受单个CSRF、预期after_round及1–300字符原因。记录操作者、时间、轮次和原因；重复同轮请求只确认原决定，不覆盖、不再次重开终态。终止后新一轮请求仍须重新检查。
- 重试保留原会话、capture、输入hash、deadline、max_rounds、费用和暴露历史；下一次实际认领追加一轮，不复用旧attempt。原冷却不因重试成功而消失。取消和耗尽不能恢复，过期不延时。
- 页面展示冷却、最多三次重试审计及当前不能重试的直接原因。表单只是请求入口，提交时重查当前权限和证据；不是付费授权。原因按HTML转义且不进入模型prompt。私有响应头和既有Admin/CSRF守卫不变。

## 原子性和历史

`CrawlRepairRetry`与会话`retry_count`、queued意图在现有DB预算互斥事务中一并提交。`(session_id,number)`和`(session_id,after_round)`唯一；事件hash绑定父输入、操作者、整秒UTC时间、轮次、原因。受控历史检查增加完整、有限的重试扫描：最多当前history limit（硬上限4096）条，计数/序号/归属/hash异常或缺失失败冷却标记均fail-closed，不能继续付费。

hash不是签名，不保护DB拥有者成套伪造、整个库一致回退或系统外操作；可变执行状态也不是外部不可抵赖审计。没有清空/重签/归档历史的在线入口。

SQL事件/计数写失败全部回滚，原blocked保留。commit成功但确认丢失，HTTP可返回503，而queued意图/事件已经存在；重试同表单不重复记录。broker发送失败保留queued，恢复器可重派，但不保证即时执行或恰好一次投递。

## 旧worker与期限

两项真实竞争修复：

1. 第一轮拒绝的提交成功但ACK丢失，同时另一消息已开始第二轮时，旧异常处理原来会把整个会话blocked。现在异常收敛带attempt身份和轮次/状态检查，不能跨轮停止。
2. 未取得认领的重复消息遇到SQL失败，原来会中止另一条已在模型内的消息。任务在认领前生成attempt身份；即使claim提交ACK丢失，也能找到自己那轮，而不是停止别人的running身份。

未认领成功的存储故障仍可保守阻断queued意图；这不是完整的调度代次/租约接管协议。已准入的模型请求不能撤回。过期恢复不付费重跑、不释放预留；现在还会把calling轮次一起关闭，并设置冷却。恢复器停用或消费者不可用时，不保证及时收敛。

模型返回后、启动解析helper之前新增当前权限/历史/所有权/期限检查；解析预算不超过当时剩余会话时间，最终落库仍重查。文件加载期间期限已过，人工重试请求拒绝，不写过期事件导致整条历史损坏。时间规范化保持整秒写入，冷却向上取整，避免缩短六小时。

以上仍是检查点，而非DB/HTTP硬deadline、进程强杀验证、供应商exactly-once或完整付费故障恢复。

## 迁移

新head **`f8b64d2c901e`**，父`e1c73d9b502a`：会话新增nullable `cooldown_until`和默认0的`retry_count`，新增重试事件表及两个唯一约束。

旧blocked/exhausted/cancelled只获得**从迁移执行时起**的六小时保守隔离；不是补造历史失败时间。使用数据库UTC并额外留一秒余量。旧queued/running不被认证为可重试，不改原期限、轮次、费用、协议、暴露或验证报告，不制造retry事件。禁止破坏性downgrade。

必须协调停止旧付费调用方再迁移/切换。旧应用不知道冷却与重试审计；保留新表不意味着混用或回滚安全。当前没有部署授权。

## 测试证据

沿用已确认的真实Admin HTTP、生产学习/recover任务和Alembic；只替换外部SDK/broker/time/存储故障，不mock自己的引擎/预算/权限模块。

新增**39项离线**：
- `tests/test_web/test_learning_lifecycle.py`：冷却/新capture、重试保留限制、取消/撤权/来源ABA/期限/证据/开关、未知/已结算/已对账资金禁止重试、轮次上限、模型后解析检查点、旧轮提交ACK竞争。
- `tests/test_web/test_learning_retry_failures.py`：事件与计数SQL原子性、ACK和broker丢失、删除/损坏审计、权限/CSRF/重复字段/跨来源、并发重复重试、无认领重复消息故障。
- `tests/test_ops/test_learning_lifecycle_migration.py`：实际Alembic旧SQLite升级/保留未知金额/隔离语义/禁止downgrade，以及离线MySQL DDL。

真实产品red：`lifecycle-cooldown-red.log`、`lifecycle-retry-red.log`、`lifecycle-checkpoint-red.log`、`lifecycle-stale-worker-red.log`、`lifecycle-migration-red.log`、`lifecycle-authority-01.log`的期限边界、`lifecycle-claim-fence-red.log`。其它保护直接通过，不冒称都由新修复产生。六小时后测试重新获取CSRF，避免把过期测试表单误当产品冷却缺陷。

相关子集139 passed / 254.89秒为最后认领fence修复前证据。**最终全套878 passed / 19 dedicated-MySQL skipped / 8807 warnings / 481.68秒**，完整日志`/tmp/fsi-m3-izjIZv/m32c-full-01.log`；30秒faulthandler未触发。

静态：205 Python AST、48 Jinja模板、单head、指定flake8、diff检查通过。MySQL集成门禁仅同步head；19项仍未运行，也没有本轮实际MySQL重试竞争/故障通过证据。SQLite线程竞争、SystemExit和提交ACK模拟不等于真实MySQL/broker/prefork/硬杀进程。

## 后续

M3仍缺专用worker及共享私有证据、资源/容量/健康门禁、实际服务故障验收、完整恢复、企业发现迁LLM队列；通用RSS/多列表/分页留出和全系统暴露覆盖亦未完成。M2审批/active/previous/日常路由仍单独待办。没有Article写入、文章LLM派发或发布能力。

见[实施计划](../superpowers/plans/2026-09-18-m3-bounded-learning.md)和[操作说明](../ops/crawl-learning.md)。
