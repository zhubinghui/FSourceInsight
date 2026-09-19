# 遗留工作复核（2026-09-18）

## 2026-09-19后续本地状态

下文保留09-18盘点，不把后来实现的切片继续当成完全未实现。M3全局账本、学习会话/暴露历史、受限HTML留出、冷却/安全重试、可选worker配置及企业**初始分析**迁队列已本地完成，见[M3当前计划](../superpowers/plans/2026-09-18-m3-bounded-learning.md)与[4b审计](2026-09-19-m34b-startup-analysis.md)。随后[2d派发身份/恢复](2026-09-19-m32d-learning-dispatch.md)补齐本地轮次/retry消息fence、持久派发间隔和晚期deadline检查；最新1019离线通过/20真实MySQL跳过；未提交/部署，也没有新的生产证据。目录出口已在4b复用SafeFetcher，但其它自有requests来源、完整恢复/所有公司refresh、实际服务/容量、通用留出及M2审批/日常路由仍未完成。

## 基线与结论

- 本地 `master@8bf2563`，审阅开始时工作区干净。
- 最新**已记录**发布为应用 `330d50b` / schema `f2a67b904d31`，见[09-11发布记录](2026-09-11-capture-ledger-release.md)。本轮未连接生产，不能据此声称09-18实时运行状态。
- 本轮核对现有源码、里程碑计划与发布报告；不修改业务、不跑真实抓取/LLM/SMTP、不部署或使用子代理。未重跑测试；673项离线、16项MySQL与真实broker回收是最近发布的历史证据。
- 核心结论：**基础修复和确定性引擎已交付，M2仅完成候选/预览/证据/策略/采样审计；规则发布和可靠日常运行没有闭环，Agent与隔离浏览器未实现。** 还有独立于Agent的现有产品与运维遗留。

## 1. 已完成，不应重复列为待办

| 范围 | 当前已交付 |
|---|---|
| M0/M0.5 | 账户归属/改密安全、Insight转义、镜像与生产端口收口、用量迁移；文章LLM只读收集/原子应用、严格响应契约、版本缓存、显式主备路由 |
| M1 | 声明式recipe、SafeFetcher、RSS/HTML/JSON-LD抽取、质量门禁、CLI预览/应用、内容级别与下游保护 |
| M2部分 | Admin不可变候选、受控预览、可选私有快照/离线回放、持久policy与撤权、长期采样指纹台账 |
| 运维/验证 | 多次真实候选MySQL验证；生产worker并发2、50次尝试/393216KiB任务后回收；CI已含真实broker回收门禁 |

不能将“预览ready”“台账tracked”“policy grant”视为规则已通过独立验证或已发布。当前policy仅约束Admin preview/replay，并非旧爬虫/CLI的全局停源开关。

## 2. 主线未实现工作

### A. M2-B2b.2b：独立留出验证（下一功能切片）

- 验证器选择未用于调试的留出页面；结合采样台账判定暴露历史，而非由候选提交者自报通过。
- 覆盖列表/详情和不同模板、不同URL相同正文、证据缺失/过期、旧档案历史不完整、source/policy变化。
- 持久化独立验证结果及输入/引擎/质量版本，拒绝把回放一致性当独立泛化证据。
- 验收：真实Admin HTTP验证，好候选通过、单页过拟合/坏证据拒绝，仍不入库、不派LLM、不激活。

### B. M2-B2b.2c：人工规则发布

- 规则diff、人工批准/拒绝/回滚、长期审批审计。
- active/previous/base版本及CAS竞争控制；来源、策略、证据变化后拒绝旧审批。
- 现有 `app/models/crawl_schema.py` 无active/previous指针，`app/web/views/crawl_config.py`只有保存/查看/preview/replay/清理，无规则发布入口。

### C. M2-C：运行认领与可靠交付

- 固定每次运行的recipe/policy输入；source/profile lease、fencing，防过期worker继续提交。
- Article、终态及outbox同事务；派发重试、消费幂等、积压补偿、崩溃恢复和可审计未知结果。
- 当前 `app/crawlers/tasks.py:17`仍调用旧registry；`:39`仅有新增文章才派LLM，`:156`扫描该源所有未处理文章并直接delay。提交成功后broker失败存在未补偿窗口；并发付费调用也未被文章最终行锁阻止。
- 企业分析刷新亦是提交后的best-effort，不是可靠后续事件（`app/llm/tasks.py:25`）。

### D. M2-D：日常schema路由与统一调度

- 已批准来源自动走新引擎；未迁移源兼容旧路径，已迁移源失败不能绕回旧直连。
- 单一next_due调度，明确手动抓取与到期合并、Paris DST、停用/重启语义。
- **现存功能缺口仍在**：Beat固定Paris 01:00，DB改14点不会改Beat；每600秒检查又受默认6小时门禁限制（`celery_app.py:35`、`app/crawlers/tasks.py:62,88`）。
- 这是“后台保存配置”真正改变日常运行的必要闭环。

### E. M3：有界学习Agent

- 原子预算预留/结算、未知费用与崩溃对账；会话/来源/每日预算共享约束。
- learning session/attempt持久化、最多3轮、不因Celery重试重置、受限工具、重复候选停止、独立验证后人工审批。
- 独立学习队列/worker；企业发现里的同步LLM改走llm队列。
- 当前 `app/llm/client.py:60`仅查询已花费用后调用，是软预算；每请求3次尝试/60秒不等于整篇文章或学习会话硬上限。

### F. M4及可选M5

- M4：隔离Playwright、子请求出口控制、非root/无凭据环境、资源限额；代表性来源影子/灰度验收和回滚演练。
- M5可选：自动promotion、StartupSource独立目录契约、更多站点迁移后删除旧类。不属于当前必须立刻完成的V1范围。

主线依据：[M2细化](../superpowers/plans/2026-09-07-m2-versioned-runtime.md)、[采样台账前置设计](../superpowers/plans/2026-09-10-m2-capture-ledger.md)、[总计划M3–M5](../superpowers/plans/2026-09-06-dynamic-crawler-agent.md)。

## 3. 高优先级：现有安全/可靠性欠账

以下经本轮源码核对仍存在；不等于已证明线上发生事故。

| 项目 | 证据与影响 | 应完成的工作 |
|---|---|---|
| 旧网络出口未收口 | 15个source模块仍含requests/cloudscraper，`startup_discovery.py:41,62,100`亦直接请求；基类SafeFetcher不会自动覆盖这些实现 | 渐进迁入受控出口，按外部网络fixture验收；安全拒绝后不得直连fallback |
| Redis缓存与broker共实例 | `docker-compose.prod.yml:88`的allkeys-lru；不同DB编号不隔离内存驱逐 | 缓存与broker/control分实例，可靠侧持久化/不驱逐，满额/断连有明确行为与告警 |
| 通用部署脚本有覆盖数据风险 | `scripts/deploy.sh:179`只要tracked dump存在就恢复；没有空库/显式恢复前提 | 部署和恢复分离，重复部署不导入dump；在修正前不要把通用脚本作为现网更新入口 |
| LLM控制状态不可靠 | `app/llm/circuit_breaker.py`Redis I/O未捕获、GET后SET计数、半开不限单探针 | 明确故障策略，原子状态/计数、半开探针认领、多app依赖隔离；配合M3硬预算 |
| 新安装安全硬化 | `app/config.py:5`允许dev-secret-key；`auth.py:49`为公开先到先建管理员，登录无应用限流 | production启动校验、一次性初始化凭证/CLI、限流、安全cookie/host/proxy配置；不推断现网正在使用默认密钥 |

## 4. 产品/数据正确性与性能遗留

| 项目 | 当前证据 | 待办 |
|---|---|---|
| 邮件退订与去重 | 两封邮件的偏好/退订href仍为`#`；`sender.py`先SMTP再记账，EmailLog无投递窗口唯一键 | 真实签名退订/偏好链接，固定窗口与投递幂等，失败/发送结果未知状态；补旧无密码订阅者的受控恢复/邮箱验证 |
| 企业人工内容及修订 | `llm/tasks.py:78`自动刷新全量覆盖；`:137`先原地append普通JSON历史；`admin.py:278`别名合并同类原地修改 | 明确人工字段保护与merge策略，可靠修订记录、不可变复制赋值，连续保存/重新读取回归 |
| 日期过滤 | `news.py:62`、`api/v1/routes.py:45`以当天00:00作包含式结束边界 | 改次日00:00排他上界，验证当天中午/午夜与时区 |
| 周情绪趋势 | `company.py:270`按年周+情绪聚合后用各组min(date)的MM/DD作键 | 统一年周/周一起点，避免同周拆桶及跨年错序；保留真实MySQL验收 |
| 列表查询 | `company.py:23,69`逐公司重查SectorGroup；`news.py:83`全部高亮取回Python排序；公司筛选全量读取 | 批量加载/聚合、DB排序分页及有界查询数量；按实际EXPLAIN做索引，不预先换搜索架构 |
| 企业发现占fast worker | `startup_discovery.py:242,289`在crawl链同步分析企业 | 每源任务、来源关联、LLM独立派发、旧失败补偿与事务隔离，不阻塞共用的email队列 |

前四项适合各自独立的小型TDD切片，不必等待浏览器/Agent。

## 5. 已有能力仍欠运行验收/工程收尾

- **长期容量与恢复**：worker回收已有真实broker证明，但不等于任务中内存限制、OOM可靠恢复、父进程/beat增长修复或夜间吞吐验证。09-11后的长期数据本轮未读取；需观察cgroup事件、队列延迟和整机余量。
- **备份恢复**：`scripts/backup_mysql.sh:28`仍用宿主mysqldump/localhost3306，与封闭生产端口不匹配；应统一Docker-aware流程、partial→验证→原子发布、异地/加密及隔离恢复演练。现网历史wrapper并未在本轮验证失效；gzip/hash通过不是可恢复证明。
- **敏感历史资产**：SQL dump仍被Git跟踪；内容未读取，需负责人审核脱敏/留存，不能把镜像排除当仓库历史清理。
- **日志监控**：`app/logging_config.py:13`仍手拼JSON；`/health/detail`公开且将未处理DB行数叫queue。补真实JSON、细节鉴权/脱敏、broker积压/卡死/质量/费用告警。
- **原始证据清理**：已有24h逻辑过期与手动/机会性清理，无定时物理删除。若需要按时清除敏感原文，增加明确清理任务及容量告警；不擅自扩大当前审计数据删除范围。
- **依赖/端到端**：requirements主要是范围约束而非lock；补可复现依赖、受控升级；新增功能继续真实Admin HTTP/隔离MySQL，并在授权后补真实源内容质量、SMTP、供应商输出、浏览器/移动端QA。
- **文档状态漂移**：总计划顶部仍将22c098c/b6标为当前，部分开发记录仍写“未部署”；应为历史记录加明确状态索引并指向最新release，避免把已完成的673/16与生产发布重新当待办。

## 6. 建议实施顺序

1. 在扩大自动化前先收口通用deploy恢复风险、Redis可靠性和旧网络出口；它们可作为独立修复，不必捆绑整个Agent。
2. 功能主线继续 **B2b.2b独立验证 → B2b.2c人工审批 → M2-C认领/outbox → M2-D路由/调度**。每步沿真实Admin HTTP先red再green。
3. 穿插修复日期/周趋势、企业修订和邮件退订/去重等用户可见问题。
4. 完成硬预算与可靠运行前不接自动学习；之后实施M3，最后按需求启用M4浏览器。M5另行确认。

以上是剩余工作盘点，不是新的实施、付费访问、提交或部署授权。
