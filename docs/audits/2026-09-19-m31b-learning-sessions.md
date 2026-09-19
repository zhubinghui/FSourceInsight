# M3.1b：持久学习会话与子预算（本地切片）

## 状态与授权

- 基线仍为 `master@8bf2563`，保留之前全部未提交改动。本次无提交、推送、SSH、部署、真实采集、付费模型、SMTP或子代理。
- **完成本地学习子预算及候选生成路径，不是完整M3。** 新head `c4e92f7a610b`，父revision `a8d31c5e7902`。
- 全套 **768 passed / 19 dedicated-MySQL skipped，272.63秒**；本切片新增39项离线测试及1项尚未实跑MySQL测试。最终日志 `/tmp/fsi-m3-izjIZv/m31b-full-diagnostic-02.log`。
- 本地Docker socket仍不存在，PATH无mysqld/redis-server。SQLite并发、外部broker替身与SystemExit故障模拟不能代替真实MySQL、broker、prefork或进程硬杀门禁。

## 交付路径

1. 管理员在已有候选的私有证据预览页显式启动；默认 `CRAWL_LEARNING_ENABLED` 关闭。
2. 只接受有效持久策略、tracked采样历史、当前source/policy/generation/engine与完整证据绑定。缺文件、撤权、ABA、旧学习协议版本均拒绝。
3. 保存持久会话后派发 `app.crawlers.learning_tasks.learn`，HTTP不调用模型。一个capture最多一份会话；重复提交包括已取消会话均返回原身份。新的capture也不能绕过同源已有queued/running会话。
4. worker在DB互斥事务中认领；同一时刻只认领一个running会话。每轮暴露指纹、提示hash、轮次先提交；模型调用不持有该事务。未决学习预留还会阻止其他学习认领，保守优先于吞吐。
5. 显式分配的 `crawl_schema` 配置才能调用；不继承default模型，不改seed/provider选择。本任务不读取/写入响应缓存。公共方法缺持久attempt不能通过缓存绕过授权。
6. 仅发送裁剪后的保留文档和当前recipe；没有学习网络工具。模型输出必须符合声明式recipe契约，来源ID须一致；通过真实M1离线回放检查训练抽取，不调用`run()`。
7. 训练ready只保存普通candidate，状态 `awaiting_validation`。重复失败recipe提前结束；最多3轮。始终不激活、不写Article、不派文章LLM。
8. Admin详情和Crawl config近期列表显示持久身份、状态、轮次、反馈、费用占用/结算、候选链接和明确的“未独立验证”。支持取消；已准入的调用不能撤回，返回后结算费用但丢弃候选。

## 预算与恢复边界

- 默认每会话0.20美元、Agent合计每日1美元、来源每日1美元，同时受总LLM预算约束。后两项Flask配置可收紧，代码上限仍为1；0不是学习无限额度。
- 会话累计20,000计费token（输入+输出，含fallback），采用原设计建议值。已知usage计实际量，未知量保留原token上界，即使金额人工对账也不伪补token为0。
- 学习准入、子预算检查和全局预留在**同一个数据库互斥事务**。每轮每个provider配置最多一次、最多3个付费尝试；会话费用不会因重投、取消或新UTC日而清零。
- 金额仍依赖管理员审核的供应商完整计费上界；不是无条件供应商账单保证。取消不释放未决金额；未知费用按既有账本最终对账流程处理。
- 180秒是从Admin启动起的持久检查点期限（包含排队），不是HTTP/DB/SDK硬杀死期限。一个已准入SDK调用仍可能越过期限，结果不能在过期检查点保存。
- queued会话本身是持久派发意图；开启学习时beat每30秒派发有界recover任务，每次扫描最多50项。发送丢失/失败可以重投。默认关闭时不安排recover，避免无消费者队列持续增长。
- running会话不会被另一个worker抢走或自动重付；到期只标blocked。进程死于预留后时，费用仍保持reserved，等待人工核对。当前属于保守的认领/终止隔离，不是完整可恢复lease抢占或exactly-once。
- 本轮没有配置专用worker消费者、共享证据卷或资源限额；生产证据卷目前仅挂web，不能直接启用这些任务。见[运维边界](../ops/crawl-learning.md)。

## 存储

- `crawl_repair_session`：capture唯一身份、source/base candidate、私有证据引用、协议版本、状态、轮次、金额限额、发起人和截止时间。
- `crawl_repair_attempt`：每会话唯一轮次、调用状态、保守暴露指纹、实际提示hash、有限反馈及候选引用。
- `llm_reservation.learning_attempt_id`：可空外键，旧记录保持NULL，金额/旧用量不改写。没有历史会话、访问许可或模型任务回填。
- 原始页面仍只在现有私有证据目录，学习表不复制原文。暴露记录是“可能已发送”，不是确认模型读过，也不证明全系统历史完整。
- 迁移只扩展两表一列，禁止破坏性downgrade；旧worker不遵守新协议，保留表不能使旧代码安全参与预算。

## 验证记录

真实red→green包括：无学习表单/任务、会话上界仍付费、token超限仍付费、缺恢复任务、默认关闭仍安排beat任务、无迁移/协议字段、旧协议仍调用模型、未绑定attempt的缓存旁路、近期会话链接缺失、预算拒绝原因不可见、已丢弃结果仍显示calling、profile加锁时仍沿用identity-map旧权限、学习配置重定价后仍用旧报价付费。锁读明确刷新对象并校验配置/报价快照；这些故障注入不能代替真实MySQL并发。

已有保护直接通过的用例未冒称新red：权限/CSRF/跨源ID/重复字段、policy撤权/来源ABA、证据/采样历史损坏、在途重复投递、取消后费用结算且无候选、跨会话全局/Agent/来源预算、显式路由/未知计费拒绝、SQLite并发重复启动、SQL准入/结算失败不重复付费、重复坏recipe停机、broker故障保留意图、模拟进程退出不释放费用。

工具/fixture偏差：原users ORM对象经请求Session移除后detach，改用真实HTTP合成邮箱登录；退出原接口是GET，测试不再误用POST。缓存替身最初也返回了断路器键，限定为响应缓存键后才复现真正的缺身份缓存旁路。几次重复/相同文本精确编辑被工具拒绝或未改变文件，没有部分业务修改。

最后追加两项竞争回归后，一次全量在420秒工具期限超时，只记录704项完成，且原final日志被覆盖。超时记录另存`/tmp/fsi-m3-izjIZv/m31b-timeout-01.log`。停点后的既有撤权测试单独1 passed/3.44秒；新增race→policy顺序探针62 passed/36.95秒。逐项日志/30秒faulthandler重跑得到上方768/19，无栈转储；超时未复现、根因未知，不将扩大等待或绿跑解释为确定性卡死已修复。

新增MySQL用例使用现有外部合成网络fixture与真正Admin页面，验证并发重复启动、在途HTTP取消、独立结算、重投不重付及无Article。**仅已加入，未实跑**；现有空库升级/model diff也将检查新head，不能据此写成通过。

静态收尾：191个Python AST（app/scripts/migrations/tests及根目录Python）、48个Jinja模板、指定flake8、`git diff --check`、Alembic单head和新文档链接/围栏通过。HEAD仍`8bf2563`，工作区全部保留未提交；无生产或真实供应商验证。

## 下一阶段

1. 独立留出选择、暴露完整性证明和验证报告；不同URL同正文不能冒充未见样本。当前所有模型提供页都只是训练证据。
2. 显式冷却/受控重试策略、完整deadline/故障恢复门禁；当前6小时冷却建议尚未实现，不得宣称完整学习生命周期。
3. 专用worker Compose/证据卷/资源/健康检查、实际broker与MySQL故障门禁，以及企业发现同步LLM迁队列。
4. 后续M2人工审批/日常路由仍独立待办；本切片不能发布任何recipe。
