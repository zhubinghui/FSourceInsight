# M3累计实现发布：保留付费AI（2026-09-20）

## 结果与范围

**17:39:41Z完成发布，应用`83813e2293ec32c618dc7ebe0326d281da947b9a`，schema `c7f21a9d680e`。** 既有付费AI继续可用，原每日预算$5、模型/任务/主备角色/优先级/key/温度不变。不是付费暂停上线，也没有关闭账本或提高预算。既有生态审核、地图、去重和Admin安全功能保留。

已安装累计M3代码：预留/结算/未知费用与Admin对账、审计删除保护、来源所有的新公司初始分析job及LLM队列/恢复、学习会话/暴露/限定HTML留出/冷却/安全重试/派发身份，以及可选worker脚本与配置。**学习仍关闭，未启动worker_learn或授予模型/来源许可；代码发布不等于全部M3完成。** M2自动发布/日常schema路由仍未实现。

依据：[执行计划](../superpowers/specs/2026-09-20-m3-paid-continuity.md)、[计费合同与TDD](2026-09-20-m3-paid-continuity.md)。本次不人工调用真实供应商模型、新闻源或SMTP作为验收。

## 付费连续性

显式将两活跃OpenAI配置指向全球官方`https://api.openai.com/v1`，新客户端发送`service_tier=default`并纳入缓存键，不继承未知Project Fast。固定实际LiteLLM1.101.0/OpenAI2.54.0的真实SDK合成HTTP验证总输出参数`max_completion_tokens=4096`包含reasoning；输入400000是官方完整模型上下文上界，不是tokenizer估算。

| ID/model | 每千输入/输出美元 | 完整输入/输出上界 | 单次预留美元 |
| --- | --- | --- | ---: |
| 1 / gpt-5.4-mini | 0.000750 / 0.004500 | 400000 / 4096 | 0.318432 |
| 5 / gpt-5.4-nano | 0.000200 / 0.001250 | 400000 / 4096 | 0.085120 |

迁移后、启动新调用方前，在一事务内逐行锁定并核对冻结旧配置后应用上述端点/单价/上界；不修改其他配置字段。停用DeepSeek/Claude仍停用且上界NULL。所有8类普通任务（含digest/独立company_analysis继承insight）实际路由均有审核配置；最大两槽预留0.636864，原5美元预算可容纳。生产仅计算准入/核对配置，没有构造虚假付款或预留。

当天旧28条usage账面估计0.001578、NULL cost0；旧价格不正确的历史日志不重写、不认证为最终发票，历史未入账窗口也不是新账本能追溯保证。未知/越界/预算耗尽仍会阻止相应新付款；这是预算保护而非暂停功能模式。供应商价格/合同变化仍须再审核，应用不保证违约收费、税费或另行合同的最终发票。

## 准确版本与真实镜像证据

- 应用83813e2：新8离线/1实库回归，真实请求/缓存/UI先red后最小改动。关联161通过/23专用skip；244 AST、选定静态/diff检查通过。
- 本地完整：**1083 passed /23 dedicated-MySQL skipped /10825 warnings /606.79s**。
- 准确CI **35523984792 success**：1083/23skip/798.08s；**23实际MySQL /42.057s**；100真实Admin任务完成回收、RSS452700KiB任务后回收、父进程/下一任务正常。
- 两实际候选各**23 MySQL**：web80.377s、worker78.220s；各49模板与真实合成Admin/CSRF检查通过；实际worker镜像100任务/RSS452256KiB回收/下一任务成功。
- 额外私有m0运维CLI演练：同一配置脚本b3→c7→原状态CAS→重复拒绝，没有预留/usage；同一snapshot脚本验证完整旧列投影与精确历史marker。
- 部署后原image再各**23 MySQL**：web78.106s、worker76.745s；没有把本地skip/CI/旧Admin的16项相互替代。

最终不可变image：

```text
web               sha256:a0e22f6eab16f53d86b3e1516bab09ac1fdc6bb3604090de108ece9e3450c300
worker/fast/beat   sha256:987ca25d98f6d9c9a67b61245ed29b2b52b47d9074d485e67e894911c9d43a57
```

从准备时真实运行的不可变image构建，只覆盖固定源码，完整运行源manifest一致；没有浮动pip重解依赖。旧4与新2 image全部**104个Python发行包、Python和OS内容一致**（整体hash `a0a9a4131d8ea8197e2df5b7c52bf104b197d9cf04461dae960aecf312e05b45`）。Python3.12.14、LiteLLM1.101.0、OpenAI2.54.0、SQLAlchemy2.0.54、Celery5.6.3、PyMySQL1.2.3。

隔离验证：internal网络、m0-mysql/fsource_m0_validation、合成凭据/无host端口；MySQL512MiB、Redis64MiB，串行MySQL runners1536MiB/1.5CPU/192PIDs，额外CLI768MiB/1CPU/128PIDs。未把测试应用/迁移源码盖到候选之上。

## 协调与受控切换

最后发现origin/master推进cf561dc：仅CLAUDE/生态发布审计，记载另一发布者16:25再次发布e646。先改计划再核对：本轮prepare已捕获那次真实四image（web2fdd208、workere2ed903、fast7aee2b3、beat148ce5c），直到临界区均未变化；没有误用15:59私有pin覆盖它。另一工作树clean、不修改它；发布后合入其两文档，固定应用候选不变。

持有非阻塞发布flock，并重复核对refs/容器/完整argv/.env哈希/配置旧值。只读preflight17:30通过；没有把flock当所有发布者都会合作的保证。

```text
17:37:27.090913Z  PRE_SWITCH_GATES_OK
17:37:29.217656Z  BEAT_PAUSED
17:37:46.827376Z  WORKERS_DRAINED
17:37:52.175915Z  ALL_OLD_APPLICATIONS_STOPPED
17:38:19.961417Z  FRESH_BACKUP_VERIFIED
17:38:19.984445Z  MIGRATION_STARTED
17:38:51.984462Z  MIGRATION_AND_REVIEWED_PAID_TERMS_OK
17:38:55.506749Z  NEW_WEB_HEALTHY
17:39:40.747897Z  LIVE_ACCEPTANCE_OK
17:39:41.312620Z  BEAT_RESTORED_LAST
```

旧worker active/reserved/scheduled/五队列各优先级/unacked全0；TERM温停，无超时KILL。web冻结后再次验证空broker。服务器正常从master/e646切至release分支838；不推共享master。b3→c7扩展迁移有10s会话DDL/行锁等待限制，不是总迁移硬期限。无seed/降级/整库恢复/旧新付费混跑/自动回滚。

全停至观察到新web健康约63.3s，**不是精确测量的HTTP停机时长**。恢复web后允许正常新写入；冻结投影的保留断言在任何新调用方启动前完成。

## 数据、备份与运行保护

- 20个旧表的全部旧列流式hash/计数保留，只排除明确更改的LLM端点/两价格列，新增cap和所有原配置字段另作逐行核对。Article10822、Company7836、NewsSource38、StartupSource26、User3、LLMConfig4、usage177657；Company/StartupSource新代次均0，不编造旧job。
- 9新表中只有迁移规定的学习history单行：三个generation0、complete1（该受控学习历史确实为空）。其他8表在新调用方启动前0行；没有捏造暴露/usage/付款/候选。
- helper静态复核发现原“所有新表0”的假设不准确，**在生产DDL前先修计划和运维断言，并额外实库演练**；未改产品迁移、未发生这类生产失败。
- 实际schema/model diff0，公私health、公司/新闻API、匿名Admin拒绝、两普通worker就绪及新增M3任务注册通过。
- web512MiB、普通worker各1GiB、beat384MiB；原完整argv/环境/worker2并发、50任务、393216KiB回收不变。私有证据卷仍仅web RW、UID0/0700，其他普通worker/beat不挂载。
- 非目标容器（含MySQL/Redis）image/start/restart及Caddy PID/start不变。17:41:52Z四应用restart0/OOMfalse、memory.events全0、启动日志traceback/error marker0，公网站点health全ok；仅短期观察，不是长期容量证明。

私有目录：`/home/ubuntu/fsourceinsight-backups/m3-20260920-1700`。

```text
backup: database.sql.gz (0600, 19930641 bytes)
sha256: 0fa61fb795e6b02b4df8554d4be7514ef5e3a01fd187c99bba4fd3e36393c890
```

gzip CRC/完整dump尾标/SHA验证通过，未取回或提交dump。保留原镜像/完整命令、源码bundle、config CAS/snapshot、各阶段和失败诊断日志。**当前重建必须保留base→prod→caddy→evidence之后的本目录`candidate.compose.json`不可变image pin。** 较早Admin pin已经不是当前版本。`rollback.compose.json`只是旧image证据，迁移后不能据它自动启动不受账本约束的旧调用方；保留ledger/费用/历史，不恢复备份抹掉不确定性。

17:43:47Z后验完成，精确清理本轮**11容器、1 internal网络、2专属卷**（含验证独占引用的Redis匿名卷）和两合成凭据文件；无global prune/生产卷删除。清理后MemAvailable4431788KiB，health全ok。

## 未完成与限制

学习未授权/未启动；当前400000完整输入界不符合学习20000累计token预算，不能为了让它执行而随意缩小上界。专用学习worker真实RO/进程丢失/时限/容量、完整恢复/lease、其他企业refresh及扫描outbox、公平调度、通用RSS/分页留出/更广暴露、M2审批/自动路由仍后续。旧/原始SQL写者与整库回滚不受新ORM代次保证。既有备份cron问题未修，新全备份不是持续备份恢复演练。
