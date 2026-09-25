# M2 收尾：schema 发布生效、每日路由、租约、outbox 与统一调度

- 日期：2026-09-25
- 基线：`4731643`（生产 `7ec578c` / schema `d3e7a1c95b28`）
- 状态：**已实现于分支 `m2-activation-routing`，未部署**（设计经用户逐节确认并审阅；实施对齐见 §12）。
- 上游：[动态爬虫 Agent 设计](2026-09-06-dynamic-crawler-agent-design.md)、[主计划 M2](../plans/2026-09-06-dynamic-crawler-agent.md)、[M2 本地细化](../plans/2026-09-07-m2-versioned-runtime.md) B/C/D 中尚未完成的部分。
- 本文是动态爬虫闭环四项中的第 1 项。第 2 项（质量失败自动学习、生产开启学习）、第 3 项（无 schema 自动探测 RSS→HTML）、第 4 项（受限浏览器渲染 M4）各自另写 spec。

## 1. 目标与成功标准

学出来或手工配置的 schema，经批准后被每日抓取实际使用，闭环才算成立。

成功标准：

1. 管理员在 Admin 批准一个候选后，一分钟内该源用这份 schema 抓取一次；入库文章照常进入 LLM 流水线。
2. 可以回滚到上一版，或退回旧爬虫；每次运行的日志能看出路由（旧爬虫 / schema）和所用版本。
3. 同一个源同一时刻只有一个有效运行；租约过期后，迟到的旧 worker 不能写入任何文章或终态。
4. 文章与其 LLM 任务在同一事务中创建；派发可补偿，重复消息不重复付费。
5. 只有一套调度规则；坏掉的源不再每天空转多次。

## 2. 已确认决策

| # | 决策 | 用户选择 |
|---|---|---|
| D1 | 范围 | 完整 M2：2.4 发布 + 2.2 租约/outbox + 2.3 统一调度，全部完成后才上线路由 |
| D2 | 调度规则 | 频率 + 每日锚点（见 §5.4） |
| D3 | 批准门槛 | 按候选来源区分：学习候选要求当前留出验证 passed；手写候选要求当前 ready 预览报告（24 小时内） |
| D4 | outbox 范围 | 新旧路径都用；删除“抓完扫描未处理文章”的派发 |
| D5 | 实现方案 | 控制状态全部放 MySQL，沿用已上线的 `company_refresh_job` 持久任务/认领/恢复模式；不用 Redis 锁或 Celery 延时任务 |

继承的原设计约束：人工批准才生效；发布用 CAS 防并发与 A→B→A；没有生效 schema 的源继续走旧爬虫；已路由到 schema 的源失败时显式失败，**不静默回落旧爬虫**；不绕过 robots、WAF、登录或验证码；验证通过不等于批准。

## 3. 数据模型

全部为增量迁移，不删改旧列/旧数据。旧数据没有生效版本，上线后所有源仍走旧爬虫。

### 3.1 `crawl_source_profile` 新增列

| 列 | 说明 |
|---|---|
| `active_version_id` | FK `crawl_schema_version`，可空；非空即该源路由到 schema |
| `previous_version_id` | FK，可空；最近一次被替换的生效版本 |
| `activation_generation` | int，默认 0；每次批准/回滚/退回加 1，是发布 CAS 的比较值 |
| `active_source_generation` | int，可空；批准时的 `source_generation`，运行时比较，用于判定 `schema_stale` |

### 3.2 新表 `crawl_schema_decision`（只追加）

`id`, `profile_id`, `action`（approve / reject / rollback / retire）, `version_id`（approve/reject/rollback 的目标；retire 为空）, `from_version_id`, `activation_generation`（操作后的值；reject 记录操作时的值）, `evidence_kind`（holdout / preview / 空）, `evidence_ref`（学习会话 identity 或预览报告 id）, `evidence_hash`, `source_generation`, `policy_version_id`, `actor_id`, `reason`（≤200）, `created_at`。

生效状态以 profile 指针为准；`crawl_schema_version.status` 不再作为依据，保持原值。

### 3.3 新表 `crawl_source_state`（每个 NewsSource 一行，包括旧爬虫源）

| 列 | 说明 |
|---|---|
| `source_id` | PK，FK `news_source` |
| `next_due_at` | 下次到期（UTC，naive，与项目一致） |
| `due_reason` | schedule / retry / cooldown / manual / activation / initial |
| `consecutive_failures` | int，默认 0 |
| `attention_reason`, `attention_since` | 需要人工处理的原因码及起始时间；成功后清空 |
| `claim_id` | 当前认领号（UUID），可空 |
| `lease_expires_at` | 租约到期，可空 |
| `fence` | int，默认 0，单调递增；每次认领加 1 |
| `running_log_id` | FK `crawl_log`，可空 |

不把这些字段放在 `news_source` 上：`news_source.updated_at` 带 onupdate，而 `_ingestion.run` 和预览指纹依赖它，调度写入会让证据失效。

### 3.4 `crawl_log` 新增列（成为一次运行的完整记录）

`claim_id`, `fence`, `route`（legacy / schema）, `activation_generation`（运行开始时 profile 的值；无 profile 为 0）, `schema_version_id`, `policy_version_id`, `outcome`（success / no_change / partial / failed / blocked / stale / lease_expired）, `error_code`。旧行全部为 NULL；旧 `status` 三态保留并继续写（success/no_change/partial→success，其余→failed）。

### 3.5 新表 `article_llm_job`（outbox）

结构对齐 `company_refresh_job`：`id`（UUID）, `article_id`（FK，ondelete SET NULL）, `active_article_id`（unique，仅 queued/running 时等于 article_id）, `trigger`（crawl / upgrade / manual / backfill / legacy_message）, `crawl_log_id`, `force`, `state`（queued / running / done / failed / expired）, `reason`, `claim_id`, `created_at`, `expires_at`, `deadline_at`, `next_dispatch_at`, `finished_at`；索引 `(state, next_dispatch_at)`。

## 4. Schema 生命周期（Admin）

四个 POST 操作，均要求管理员 + CSRF，表单携带页面加载时的 `activation_generation`；与数据库不一致返回 409。每个操作在一个事务内 `SELECT … FOR UPDATE` 锁住 `news_source` 与 profile，写 decision 与指针后提交。

### 4.1 批准

前置条件（全部满足才生效）：

1. 源启用；profile 有 `effective` 的持久策略（`_source_policy.state == 'effective'`）。内联 host 的 B1 预览不能作为批准依据。
2. 候选属于该源、不是当前生效版本、没有 reject 决策；recipe 仍通过 `validate_recipe` 且指纹等于 `recipe_hash`。
3. 证据：
   - **学习候选**（存在 `crawl_repair_attempt.candidate_id` 指向它）：`validation.view(session, identity).state == 'passed'`。该函数已在证据被暴露、策略或权威变化时返回 `stale`。
   - **手写候选**：选定的一份预览报告满足 `status == 'ready'`、`report['source_policy']` 非空、`created_at` 在 24 小时内，且现有 `preview_report` 的 stale 判定为假（抽成共享函数复用，不复制条件）。
4. `expected_activation_generation` 匹配。

效果：`previous_version_id ← active_version_id`，`active_version_id ← 候选`，`active_source_generation ← source_generation`，`activation_generation + 1`；写 approve 决策（含证据引用/哈希、策略版本）；把该源 `crawl_source_state.next_due_at` 设为现在，`due_reason = activation`。

### 4.2 拒绝

写 reject 决策，不动指针。被拒候选此后不能批准；要改就提交新候选。

### 4.3 回滚到上一版

要求 `previous_version_id` 非空，其最近一次 approve 决策的 `source_generation` 等于当前值，且策略仍 effective。交换 active/previous，`activation_generation + 1`，写 rollback 决策，`next_due_at` 设为现在。不满足则 409，须重新预览并批准。

### 4.4 退回旧爬虫

随时允许（源停用时也允许）。`previous_version_id ← active_version_id`，`active_version_id ← NULL`，`activation_generation + 1`，写 retire 决策。下一次运行走旧爬虫注册表。

### 4.5 运行时失效

路由到 schema 的运行在开始时检查：`active_source_generation == source_generation`，且策略 effective；recipe 可校验且指纹一致。否则本次运行 `outcome = blocked`，`error_code` 为 `schema_stale` / `policy_unavailable` / `invalid_schema`，不回落旧爬虫。

## 5. 调度与运行

### 5.1 调度任务

新 beat 项 `dispatch-due-crawls`：每 60 秒运行 `app.crawlers.tasks.dispatch_due_crawls`（crawl 队列），取代 `daily-crawl-all` 与 `crawl-frequency-check`。`crawl_daily_hour`、`crawl_timezone` 保留为锚点设置；`crawl_check_interval_hours` 废弃（设置页移除该项，库中值保留不删）。

`crawl_all_sources`、`schedule_due_crawls` 两个任务名保留注册一个版本，收到消息只记日志并返回 skipped。

每轮：

1. 为缺少 state 行的启用源插入一行（`next_due_at = now`，`due_reason = initial`），唯一冲突忽略。
2. 选出 `next_due_at <= now` 且（无租约或租约已过期）的启用源，按 `next_due_at, source_id` 排序，最多 50 个。
3. 对每个源用短事务认领（见 5.2）；提交后发送 `crawl_source(source_id, claim_id)`。发送失败只记日志：租约过期后下一轮会重新认领。

### 5.2 认领

锁 state 行，确认仍到期且租约空或已过期。若旧租约过期且 `running_log_id` 仍为 running，把该日志终结为 `outcome = lease_expired`。然后：`fence + 1`，新 `claim_id`，`lease_expires_at = now + 15 分钟`，创建 `crawl_log(status=running, claim_id, fence)` 并写入 `running_log_id`，`next_due_at` 保持不变（租约本身阻止重复派发）。

`crawl_source` 设置 `soft_time_limit = 600`、`time_limit = 660`，小于租约，使正常超时先于租约到期。租约是逻辑租约，不是外部强制终止。

### 5.3 运行与最终提交

`crawl_source(source_id, claim_id)`：

1. 只读确认 `claim_id` 仍是当前认领且未过期，否则直接返回。
2. 路由：profile 有 `active_version_id` → 新引擎（固定该版本 recipe、当前 effective 策略的 FetchPolicy 与 QualityProfile）；否则 → `get_crawler(source)` 旧爬虫。把路由、版本和 `activation_generation` 写入本次日志。网络请求期间不持任何数据库锁。
3. 最终事务：锁 state 行与 profile，确认 `claim_id`、`fence` 均未变、租约未过期，且 `activation_generation` 与运行开始时相同（运行期间发生批准/回滚/退回，则本次结果作废：日志记 `stale`，只清除租约，不写文章、不改 `next_due_at`）；然后在**同一事务**写入文章（新建/升级）、对应 `article_llm_job`、`crawl_log` 终态（route、版本、outcome、计数、error_code）、state（清租约、更新 `next_due_at`、失败计数与 attention）。不匹配则只把本次日志记为 `stale`，不写文章。
4. 提交后立即尝试发送本次新建的 LLM 任务（快速路径，失败由恢复任务补发）。

实现要求：`CrawlEngine.run()`（`_ingestion.run`）改为接受已认领的运行，不再自建日志；旧爬虫基类 `BaseCrawler.run()/save()` 改为返回待写入数据，由同一个最终提交函数写库。两条路径共用一个最终提交实现。旧爬虫自身的抓取方式（直连 requests 等）本次不改。

`crawl_source` 不再使用 Celery `self.retry`；所有重试由 `next_due_at` 决定。

旧格式消息 `crawl_source(source_id)`（无 claim）按手动请求处理（5.6），不直接执行。

### 5.4 下次到期时间

设 `F` 为该源 `crawl_frequency_minutes`，`S` 为本次运行开始时间，`T` 为本次结束时间。

- **成功 / 无变化 / partial**：`next_due_at = min(S + F, A)`。`A` 是晚于 `S + 30 分钟` 的第一个每日锚点（避免锚点前刚抓过又立刻重抓）；清零失败计数与 attention。
- **可重试失败**（timeout、network_error、server_error、rate_limited，以及旧爬虫的 requests 超时/连接错误/5xx/429）：`next_due_at = T + min(F, 15 分钟 × 2^(n−1))`，`n` 为连续失败次数；有 Retry-After 时取其值（上限 24 小时）。
- **访问受限**（forbidden、robots_denied、robots_unavailable、unsafe_url、tls_error、login_required、paywall、captcha，旧爬虫 HTTP 4xx（408、429 除外），以及 §4.5 的 schema_stale/policy_unavailable/invalid_schema）：`next_due_at = T + 24 小时`，写 `attention_reason`。
- **抽取 / 质量失败**（空抽取、low_quality、missing_fields、invalid_article 等）：按成功规则计算下次到期，不加速重试；连续 3 次后写 `attention_reason = extraction_failed`。第 2 项会在这里接入自动学习。

outcome 对应：成功/无变化/partial 按引擎结果；可重试与抽取/质量失败记 `failed`；访问受限记 `blocked`。

运行期间若有人请求立即抓取（当前 `due_reason` 为 manual），最终提交时 `next_due_at` 取规则值与现值中较早者，请求不会被覆盖。

锚点按 `crawl_timezone` 的本地日期 + `crawl_daily_hour:00` 计算为绝对 UTC 时刻。秋季重复的小时取第一次出现（fold=0），因此只执行一次；春季不存在的本地时刻顺延到跳变之后的第一个时刻。

### 5.5 迁移时的初始值

每个现有源一行：`last_crawled_at` 为空 → `next_due_at = 迁移时刻`；否则按成功规则以 `last_crawled_at` 作为 `S` 计算，若结果早于迁移时刻则取迁移时刻。`fence = 0`，无租约。

### 5.6 手动抓取

“立即抓取”“全部立即抓取”改为把 `next_due_at` 设为现在、`due_reason = manual`；租约有效时提示“正在运行”，不排第二次。

## 6. LLM outbox

### 6.1 创建

文章新建，或内容级别升级（`_ingestion` 现有 metadata_only/excerpt → 更高级别并清空派生字段的分支）时，在最终提交事务中创建 `article_llm_job(state=queued, next_dispatch_at=now, expires_at=now+24h)`。`active_article_id` 唯一约束保证一篇文章最多一个进行中的任务；已有则不创建。

### 6.2 派发与恢复

新模块 `app.llm.article_jobs`（加入 Celery include，llm 队列）：

- `app.llm.article_jobs.process(job_id)`：消费任务。
- `app.llm.article_jobs.recover()`：beat 每 60 秒。处理到期 queued 任务最多 50 个：发送消息并把 `next_dispatch_at` 推后 120 秒；queued 超过 `expires_at` → `expired`；running 超过 `deadline_at` → `failed`（reason `interrupted`），不自动重付。

### 6.3 消费

1. 认领：`queued → running`，写 `claim_id`，`deadline_at = now + 30 分钟`。认领不到（已被别人认领或已结束）→ 直接返回，不调用模型。
2. 调用现有 `process_article(article_id, force=job.force)`。
3. 结束：认领仍匹配 → `done` 或 `failed`（reason 为错误码），清 `active_article_id`；不匹配（已被恢复任务判为 interrupted）→ 只记日志。

防重复付费靠两层：任务认领挡住并发重复消息；`process_article` 已有的“已处理且非 force 则跳过”挡住对已完成文章的重复任务。

### 6.4 其他入口

- Admin 单篇“重新处理”→ 创建 `force=True, trigger=manual` 任务；已有进行中任务时提示已排队。
- Admin 批量“LLM 重处理”→ 为未处理且无进行中任务的文章创建任务，数量沿用现有表单的 `limit`（默认 50）。
- 旧格式消息 `app.llm.tasks.process_article_llm(article_id, force)` → 只创建任务（`trigger=legacy_message`），不直接调用模型；任务名保留注册。
- `scripts/run_llm_process.py` 保持直接调用，文档注明它不经过认领、可能与任务并发。
- 删除 `app.crawlers.tasks._enqueue_llm_processing` 的扫描派发。
- 上线补偿：新脚本 `scripts/backfill_article_jobs.py`（默认 dry run，`--apply` 才写），为所有 `llm_processed = false` 且无进行中任务的文章分批创建 `trigger=backfill` 任务。

## 7. Admin 界面

- 源列表：路由（旧爬虫 / schema vN）、下次到期、attention 标记及原因。
- 源的采集配置页：当前生效版本、上一版、`activation_generation`、决策历史；“回滚到上一版”“退回旧爬虫”按钮。
- 候选版本页：“批准”“拒绝”。学习候选显示当前留出验证状态；手写候选列出可作为证据的预览报告（ready、当前、24 小时内），批准时选其一。
- 抓取日志：路由、版本、outcome、error_code 列。
- 文章详情：最新 LLM 任务状态；系统健康页：各状态任务数。

## 8. 不变量

1. 任何写入文章或运行终态的事务，都在锁住 state 行后确认 claim/fence/租约有效，且发布计数自运行开始未变。
2. 发布指针只在锁住 profile 且 `activation_generation` 匹配时改变，每次改变都有一条决策记录。
3. 路由到 schema 的源永不回落旧爬虫；只有“退回旧爬虫”决策能改变路由。
4. 文章新建/升级与其 LLM 任务同事务提交；模型调用只发生在成功认领的任务内。
5. 调度状态不写 `news_source`；Redis 不承载任何控制状态。

## 9. 测试策略

- 严格 TDD：先写失败用例，再做最小实现，然后跑相关与全量测试。
- 主要验收面：真实 Admin HTTP（批准/拒绝/回滚/退回、CSRF、权限、409 冲突、证据失效、A→B→A）、Celery 公共任务（dispatch、claim、crawl_source 新旧消息、article_jobs process/recover、旧 process_article_llm 消息）、Alembic（空库与完整旧库升级、旧行保留）。
- 下次到期规则通过 dispatch 任务在固定时间下验证：DST 秋季重复小时只执行一次、春季跳变顺延、跨日、锚点前 30 分钟内刚成功不重抓、三类失败的退避/冷却/attention。
- 真实 MySQL 集成测试（`tests/integration/`，一次性 `m0-mysql`）：并发认领只有一个成功；租约过期后旧 claim 提交被拒且不写文章；`active_article_id` 唯一；并发重复任务消息只有一个认领成功。
- HTTP 测试使用现有 `fetch_network` fixture，不 mock 我们的 fetcher。

## 10. 上线与回滚

上线（单独授权，用户以 `!` 执行受保护脚本）：

1. 备份；停止 beat；等待 crawl 与 llm 队列清空，停止旧 worker（不混跑新旧 worker）。
2. 迁移到新 head；运行 `backfill_article_jobs.py --apply`。
3. 启动新 worker，最后启动 beat。此时没有任何生效 schema，全部源仍走旧爬虫，只是换成新调度和 outbox。
4. 验收：dispatch 与 recover 周期性成功、首轮到期源被认领并完成、新文章的 LLM 任务完成。
5. 第一个 schema 由用户在 Admin 批准。

回滚：用上一版镜像 pin。新增表/列保留，旧代码忽略它们；旧调度与“扫描未处理文章”恢复工作，queued 的 `article_llm_job` 变为惰性记录。回滚同样须先停 beat、清空队列。

## 11. 不在范围与剩余风险

- 不做：第 2–4 项、自动灰度发布、删除旧爬虫类、把旧爬虫迁到 SafeFetcher、修复 2026-09-24 诊断出的四个失败源（Inria、STMicro、CEA Enterprise、CEA-List）。
- 租约与截止时间都是逻辑上的，不是对进程的强制终止；超过截止仍在运行的 worker 只会被 fence/认领挡住提交。
- `run_llm_process.py` 绕过任务认领。
- 进入付费调用后中断的文章任务不自动重跑，需要人工重新处理。
- 旧爬虫仍直连外网，没有 SafeFetcher 的安全保证。

## 12. 实施对齐（2026-09-25，写实施计划时）

1. §5.5 初始值不在 Alembic 中回填：`dispatch_due_crawls` 每轮先为缺少 state 行的启用源补一行，按同一规则计算（`last_crawled_at` 为空则为当前时刻，否则按成功规则并不早于当前时刻）。迁移保持只增不改数据。
2. §5.4 “运行期间请求立即抓取”的那一段作废，以 §5.6 为准：租约有效时请求只返回“正在运行”，不改到期时间，也不追加第二次运行（与原 M2 计划“同一次认领合并完成”一致）。
3. §6.2 的任务名改为沿用公司刷新的两模块写法：状态机在 `app.llm.article_jobs`，Celery 任务为 `app.llm.article_tasks.process` 与 `app.llm.article_tasks.recover`。
4. §9 下次到期规则是纯函数（`app.crawlers.schedule.next_due`），DST 与退避规则直接对它测试；另有经真实抓取路径的结算测试确认运行确实使用该规则。
5. `CrawlEngine.run()` 与 `BaseCrawler.run()` 改为必须传入认领（`run(claim)`），保证所有写文章的路径都经过 claim/fence 检查；`scripts/run_recipe.py --apply` 与 `scripts/run_crawl.py` 先认领再运行。
