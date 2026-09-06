# 动态爬虫 Agent 分阶段实施计划

- 日期：2026-09-06；基线 `bf9cc61b94556e00218af267db82bf42a3b80eef`。
- 状态：**用户已批准执行；M0 进行中，M1–M4 待实施。未部署。**
- 设计依据：[架构草案](../specs/2026-09-06-dynamic-crawler-agent-design.md)、[审查清单](../../audits/2026-09-06-project-audit.md)。
- 工作方式：用户要求不使用子代理；后续在主会话单写者实施。需要修改范围/验证方式时先更新本计划。
- 每一小步要求“失败用例→最小实现→回归验证→记录差异”。下面的 commit 标题是建议切片，不代表已创建或授权推送。

## 前置决策

- [x] V1 仅新闻，企业/研究所目录后续复用独立输出契约。
- [x] 候选 schema 首版人工批准，自动灰度不在首版。
- [x] 元数据可保存，但仅标题不进入深度洞察。
- [x] 允许隔离 Playwright，仅公开内容，不自动绕过登录/付费墙/验证码；具体生产资源上线前测量。
- [x] 初始 3 轮、US$0.20/会话、US$1/日且受总预算约束；其余设计限额作为可配置初值。
- [x] 用户明确授权开始业务实现；后续又授权在 OVH 验证 SQL，验证通过可提交部署当前首批修复，并要求后续继续 TDD。真实付费验证和测试邮件仍不触发。
- 本轮维护采用 [OVH 验证/受控发布计划](2026-09-06-ovh-m0-validation-deploy.md)，不重跑旧首次安装流程。

## 当前执行记录

- M0 从 HTTP 身份/归属接口开始：先创建离线正式测试、验证漏洞用例失败，再实现最小安全修复。
- 0.1 安全收口：所有订阅管理仅对已登录本人开放；停止凭任意邮箱自动建账户/订阅。旧无密码订阅者的数据保留，但需后续邮箱验证/受控恢复才开放自助入口，不新增不安全的注册捷径。订阅管理 URL 不再传邮箱。
- 验证环境复用临时 Python 3.12 venv；每个测试独立 SQLite 库，阻断网络/SMTP/真实 LLM，保持 CSRF 开启。
- 测试接口沿用已批准计划：HTTP、Crawler.run、LLM 公共任务、Compose 与迁移。
- 验证偏差（先记录后执行）：本机 Docker socket 指向不存在的目标，且 PATH 无 mysqld，无法按原计划立即启动 MySQL 8 实机验证。0.4 先新增前向迁移和 MySQL 离线 SQL 回归测试；空库/带旧数据升级、JSON/NOT NULL 历史兼容和 model diff 保留为上线阻塞，不把离线 DDL 当成实机通过。
- 0.3 已有 Compose v5.1.0 CLI 可做离线合并检查。生产层统一使用 !override（最低 Compose 2.24.4），旧客户端必须升级，不提供移除安全标签的降级路径。
- 0.1 密码变更使已有登录/remember cookie 失效；首次应用修复时旧整数会话统一要求重新登录。
- 实施顺序细化：0.5 需要同时调整多阶段业务写入边界，不能机械替换日志 Session；在专门处理它前，可独立完成 0.7 的模板/预览修复与 0.6 爬虫基础回归。未完成的子项在交付时明确标注。
- 0.4 新迁移为 expand-only：禁止将新任务类型强转旧 Enum（可能截断付费用量历史）；代码回滚保留 VARCHAR(50)，不运行该 revision 的 downgrade。

## 当前验收状态（首批实现后）

| 切片 | 状态 | 证据/剩余 |
|---|---|---|
| 0.1 身份/归属 | 本地通过 | 29 项 HTTP 安全/合法操作回归，CSRF 开启，旧会话失效 |
| 0.2 Insight HTML | 本地通过 | 文章详情 HTML 安全及 Markdown 排版回归 |
| 0.3 构建/生产配置 | 已验证部署 | 3 项离线测试；两个 Compose 组合 + allowlist，实际镜像/公网绑定已检查 |
| 0.4 用量类型迁移 | 实机/部署通过 | MySQL8.0.46隔离验证通过；生产本来已VARCHAR，迁移跳过重复ALTER并推进至c821，model diff=0 |
| 0.5 LLM 可靠性 | 待实现 | 业务无写入收集阶段→独立用量→一次应用；严格契约/缓存/显式路由仍未修复 |
| 0.6 爬虫基础 | 本地/MySQL通过 | 13 项离线测试；MySQL竞争写入/晚期失败回滚已验证；进程崩溃/消息窗口仍待M2 |
| 0.7 邮件模板 | 本地通过 | 两类模板/Top Insights/预览/SMTP 失败记录共 2 项；投递幂等/真实退订仍在后续切片 |

首批后补齐运维门禁测试，合计本地 **52 passed**，另 **7项 MySQL 实机通过**，CI两个job通过；已部署代码858a14b。M0尚余0.5，M1–M4未开始，Agent未上线。详见 [实施记录](../../audits/2026-09-06-m0-implementation.md) 和 [OVH验收/发布记录](../../audits/2026-09-06-ovh-sql-validation.md)。

## M0：先消除高风险缺陷，建立验证环境

目标：系统在没有 Agent 时就具备基本安全与数据正确性。

### 0.1 `fix(auth): enforce account and subscription ownership`
- 文件：`app/web/views/subscription.py`、`auth.py`、相关模板与新增安全测试。
- 关闭匿名改密码和跨用户订阅操作；改密验证旧凭证/重置 token；订阅链接不得承载账户改密权限。
- 验证：开启 CSRF 的匿名/本人/其他用户/管理员四类请求；同站 next 校验；合法访问回归。
- 不在这一切片中同时重构整个用户模型。

### 0.2 `fix(render): escape untrusted insight content`
- 文件：`app/__init__.py` 或抽出的受控文本渲染模块、模板、安全测试。
- 修复 raw HTML/XSS，测试 Markdown 标题/表格/列表、事件属性、危险链接。
- 保持页面现有排版；CSP 作为后续硬化，不以禁用全部展示代替修复。

### 0.3 `fix(ops): isolate build context and production endpoints`
- 新增 `.dockerignore`，收窄 Dockerfile COPY；修复通用 prod 的 ports/volumes 清空。
- CI 对 base+prod 与 base+prod+caddy 两个组合做配置断言；不读取真实 `.env`、不直接 up 现有容器。
- 明确 Compose 版本/标签支持和回退路径，不将 Caddy 现有正确绑定破坏。

### 0.4 `fix(db): align usage task type migration`
- 新增前向 Alembic revision，同步 `llm_usage_log.task_type` 与模型；核对已有 NOT NULL/backfill、JSON 历史值。
- 在隔离 MySQL 8 上测试：空库到 head、已有人造旧数据到 head、升级后 model diff。
- 严禁用 drop/create 或导入生产 dump 来掩盖迁移问题。

### 0.5 `fix(llm): separate usage ledger from business transactions`
- 改 LLM 用量独立事务；分类/公司关系幂等；每步骤中断重试测试。
- 实施细化：不能只把 commit 换成独立 Session。现有 pipeline 在下一次模型调用前就 flush Article/Company，独立用量 INSERT 又含 Article FK，可能在 MySQL 等待外层尚未提交的父行锁；SQLite 也会遭遇写锁。先让 LLM 阶段收集结果且不写业务表，再单事务应用结果，最后刷新企业。这项需单独完成并验证，不能用 SQLite 内存共享连接伪造独立事务保证。
- 严格 JSON 结果校验，失败不记正常空结果缓存；补完整输入/prompt 版本缓存。
- 任务路由新增明确 priority/role，不用 seed 静默覆盖实际 DB 选型。

### 0.6 `fix(crawl): preserve failures and tolerate duplicates`
- 爬虫失败 rollback + 独立日志事务；明确 retryable 传播；批内去重、冲突隔离。
- `urljoin`、日期 UTC 归一化和必要字段验证；测试基于合成 RSS/HTML，不请求真实网站。
- 验证中发现 Python SQLite legacy transaction 模式会把首个 SAVEPOINT 当外层事务，release 后不能随后续批次失败回滚。先记录这一差异：SQLite adapter 在首个 savepoint 前显式 BEGIN；MySQL 保持其正常外层事务，新增“第二条插入失败整批回滚”用例，不修改测试来掩盖部分提交。
- 过渡状态：CrawlResult 新增 no_change/status/retryable；旧 CrawlLog Enum 暂仍用 success/failed。有效空 RSS 可为 no_change；无证据的空 HTML 记失败不盲目重试。更细质量归因在 M1/M2 增量迁移中实现。

### 0.7 `fix(email): align template context and delivery state`
- 两类模板路径、Top Insights 与 preview 一并修正；发送只 mock。
- 固定投递窗口、幂等 key、真实退订入口和失败结果记录作为后续邮件可靠性切片。

**M0 完成条件**：高风险回归用例真实通过；原来的 0 tests 状态结束；不以审查探针“缺陷仍存在”的断言充当正确性 CI。

## M1：无 Agent 的确定性引擎

目标：手写一份 recipe 就可可靠运行，Agent 以后只负责生成它。

### 1.1 `feat(crawl): define extraction and quality contracts`
- `contracts.py` / `schema.py`：FetchObservation、NormalizedArticle、QualityReport、CrawlOutcome；错误类型与状态。
- 支持 content_level、source_language、field provenance、最终 URL、时间来源。
- schema 格式版本、最大字段/selector 数、操作允许列表；业务安全策略不放进模型可改字段。
- 验证：schema 正/反例，超长/畸形/扩权字段拒绝。

### 1.2 `feat(fetch): centralize bounded safe HTTP retrieval`
- `fetcher.py`：requests Session 连接复用、stream 上限、总时限、公共 URL/跳转/DNS 校验、域名限速、robots 策略。
- feedparser 只解析已获取 bytes，不再隐式直连；抓取源码和 website_fetcher 渐进接入。
- 验证：mock DNS/redirect，包括 IPv4/IPv6 私网、DNS rebinding、gzip 膨胀、畸形 content-type、429、分页循环。
- 浏览器未实现前明确返回 render_unavailable，不能假装降级成功。

### 1.3 `feat(crawl): execute RSS HTML and JSON-LD recipes`
- 规范化列表发现→详情补全→质量；rss feed 已有全文可跳详情。
- 旧爬虫经 Adapter 接入并返回可观察结果；旧 entrypoint 继续可用。
- URL 去重前置；跳过已知未变详情的同时抽样验证模板健康。
- 验证：合成 golden fixtures，RSS/HTML/JSON-LD、多个列表/详情模板、相对 URL、双语、仅标题等。

### 1.4 `feat(crawl): gate ingestion on extraction quality`
- `quality.py` 与 source profile；区分 no_change/partial/degraded/blocked。
- transport 错误不学习；正文噪声、导航、列表误判有解释；只将合格条目提交。
- 验证：空 feed 合法无更新与坏 selector；全部重复不得误触发修复；短讯与活动有单独 profile。

**M1 完成条件**：无需 LLM 的 fixtures 全通过；同快照/同 schema 输出可复现；没有通过新增配置执行代码的路径。

## M2：版本/幂等/调度与可靠交付

### 2.1 `feat(crawl): persist versioned schemas and run evidence`
- 新增 schema/profile 表，扩展 CrawlLog；先 nullable 扩展，再回填，再约束，不丢旧日志。
- 一个源默认一个 profile，允许后续按类型/语言增多个；active/previous 指针与不可变候选。
- 每 run 固定 source policy/schema 快照；来源追踪字段支持回滚后的数据隔离。

### 2.2 `feat(tasks): add leases and transactional outbox`
- source/profile 单运行认领、lease/token/fencing；消息仅携带 IDs，不携带密钥/HTML 大包。
- Article 更新与 outbox 同事务；dispatcher 重试、消费端幂等 key、延迟/失败监控。
- 控制存储与 cache 分开；缓存可以 miss，预算/lease 故障不能放开并发。
- 验证：并发重复、worker crash、发送前/后 DB 故障、lease 过期旧 worker、相同消息重投递。

### 2.3 `fix(schedule): unify next-due calculation`
- 单周期调度器基于 next_due_at，按 DB 配置处理频率/日历时区。
- 管理员手动抓取仍要认领；明确是否重置下一轮，避免混用两种含义。
- 验证：Paris DST、跨日、调 14 点、短周期源、停用源。

### 2.4 `feat(admin): inspect and promote schema candidates`
- 样本/质量/diff 预览；人工批准/拒绝/回滚；权限+CSRF+审计。
- CAS 只激活基于当前 active 的候选；source/policy 改变使候选失效。
- 验证：竞争发布、旧候选、取消、不可变版本、审批记录。

**M2 完成条件**：手动 schema 可发布、追溯、回滚；消息丢失窗口可补偿；旧 Article 身份不被重写导致重复。

## M3：有界学习 Agent，先不自动发布

### 3.1 `feat(llm): reserve budgets for bounded repair calls`
- 添加 `crawl_schema` 独立 LLM 任务类型/能力路由和用量关联；实际 provider/model 仍在 DB 配置。
- 会话/源/日预算原子预留与结算；未知费用保守记账；全调用链总 timeout、visited config/attempt 限额。
- 验证：并发最后余额、模型失败/超时、Redis/DB 异常、fallback 也计费。

### 3.2 `feat(crawl-agent): persist bounded repair loop`
- 持久化 learning session/attempt，3 轮等限额可配置但不能由模型改变。
- 工具只有 inspect/fetch_allowed/test_recipe/submit_candidate；结构化失败反馈与重复候选提前停止。
- 缺预算/权限/样本时落 exhausted/blocked/awaiting_review；不在 Celery retry 时重置循环。
- 验证：scripted fake model 漂移修复、恶意网页指令、无效 JSON、相同候选循环、进程恢复。

### 3.3 `feat(crawl-agent): validate holdouts before candidate readiness`
- 留出样本由验证器选择；与旧已知好样本比较；不足样本进人工。
- 只保存候选和隔离结果，不激活 production schema、不直接 enqueue enriched articles。
- 验证：过拟合单页/错误详情模板候选拒绝；好候选发布后能复验并处理本轮数据。

### 3.4 `feat(worker): route crawl repair independently`
- 新增 `crawl_learn` queue/worker，更新 include/routes/Compose `-Q` 和启动健康检查。
- 企业发现中的同步 LLM 调用改派 llm，避免占 fast worker。
- 按源开关，首批 2–3 个代表性公开源影子运行；真实访问/费用测试须用户明确授权。

**M3 完成条件**：网络关闭的模拟学习链路全通过；每 session 预算/轮次可证明有上界；人工批准前零配置发布、零候选业务污染。

## M4：受限渲染与小范围上线

- [ ] 引入隔离 Playwright 执行环境，非 root/沙箱、无业务凭据/宿主挂载、网络子请求统一受控。
- [ ] recipe 仅允许受限导航、等待、滚动与预批准读操作；禁止任意 evaluate、登录/表单/下载。
- [ ] 资源/时间/请求限额包括子请求；HTTP 成功空页面且有 JS 证据才允许渲染；403 不自动绕过。
- [ ] 模拟 SPA、长轮询、无限滚动、恶意 iframe/私网子请求、render worker crash。
- [ ] 在用户批准的代表性源上对比 legacy/schema/assisted；记录完整正文率、有效条目率、延迟、实际费用。
- [ ] 明确正常/故障回滚：停 repair 开关、回退 active version、保留快照和业务数据，不执行 `down -v`。

**上线准入**：安全/契约/幂等测试、隔离 MySQL/Redis 集成测试、负载与成本阈值、人工审批路径、告警和回滚演练均通过。浏览器无法安全部署时，先发布 HTTP+人工复核能力，不能用关闭浏览器沙箱代替隔离。

## M5：可选扩展（需重新确认）

- 按源启用自动 shadow→canary→promotion，明确自动撤回规则和被污染数据的隔离流程。
- StartupSource 的公司/研究所目录独立契约，复用引擎但不写 Article。
- 更多站点规则迁移后删除冗余爬虫类；持久化别名索引、UI 查询优化、下游 LLM 步骤版本化。
- 按实测选择性能优化，不预先引入向量库、搜索集群、无限多 Agent。

## 跨阶段验收清单

- [ ] 原有页面/API/手动 CLI 兼容，测试里不直连外网。
- [ ] source/recipe/input/prompt 版本可追踪；旧外部 ID 保持或有可验证映射。
- [ ] 生产密钥不进镜像、schema、HTML 快照、日志或测试 fixture。
- [ ] 预算、锁、审批失败时 fail-closed，只有响应缓存等非关键路径允许降级。
- [ ] 合成数据的 MySQL 空库/旧库迁移、broker 重投递和恢复演练通过。
- [ ] 输出详细 changed files、命令/结果和未验证项，提交/部署另行按用户授权执行。
