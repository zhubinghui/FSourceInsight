# FSourceInsight 全项目审查与优化清单

- 审查日期：2026-09-06
- 基线：`master` / `bf9cc61b94556e00218af267db82bf42a3b80eef`
- 执行方式：用户批准后由主会话直接检查，没有子代理审查结果。
- 状态：**审查与改造设计已完成，以下缺陷尚未修复；未部署。**
- 相关交付：[验证记录](2026-09-06-validation.md)、[动态爬虫架构](../superpowers/specs/2026-09-06-dynamic-crawler-agent-design.md)、[实施计划](../superpowers/plans/2026-09-06-dynamic-crawler-agent.md)。

## 1. 结论

项目已有完整的新闻→分析→展示业务链，适合在现有 Flask/Celery/MySQL 上渐进改造，不需要先换框架或拆成大量微服务。

但目前不是“再接一个 Agent 就能可靠自愈”的状态：**身份校验、事务/重试、质量判定、任务交付和配置版本**都需要先补齐。否则 Agent 会把“空抓取成功”“重复任务”“只有标题”“网络封禁”等不同问题混在一起修复，放大成本和数据污染。

建议顺序：

1. **立即修复匿名管理员改密和不安全 HTML 输出。**
2. 收口镜像/端口、迁移一致性，修复事务/幂等/邮件链路。
3. 建立确定性爬虫引擎、质量门禁、版本化 schema 和离线样本测试。
4. 接入有界 Agent 学习，先影子运行和人工发布，再考虑自动灰度发布。

### 审查覆盖与限制

| 范围 | 本轮覆盖 |
|---|---|
| 后端 | 人工阅读 Flask factory、所有 views/API、LLM、爬虫、邮件、模型、工具模块 |
| 爬虫 | 25 个站点模块，29 个注册类；种子新闻源 **35** 个（不是 README 写的 34），发现源 21 个 |
| 脚本/运维 | Compose 三种组合、Dockerfile、nginx、部署/备份/恢复、seed 执行逻辑、历史部署文档 |
| 迁移 | 13 个迁移链静态检查及 MySQL 方言离线 SQL 生成 |
| 前端 | 40 个 Jinja 模板编译、全体危险输出/表单静态扫描、主要页面人工检查；无视觉/移动端/可访问性实测 |
| 验证 | 103 个 Python 文件 AST 解析；shell 语法；18 项缺陷复现探针；补充 ORM/时间/查询计数探针 |
| 未执行 | 真实站点可用率、生产配置/日志/数据、MySQL 实机迁移与并发压测、Redis 故障演练、SMTP/LLM API、浏览器 E2E |

没有读取 `.env` 值或 SQL dump 内容。依赖仅安装在临时 Python 3.12 环境。**原有 pytest 收集到 0 个测试，exit 5；不能称“全套测试通过”。**

优先级：P0=立即阻断风险；P1=Agent 上线前必须处理或显式隔离；P2=确定的正确性/性能优化；P3=后续工程优化。证据标记：`复现`=隔离探针，`配置/SQL`=离线解析，`静态`=源码可达行为；不代表生产发生过故障。

## 2. 安全与交付风险

### SEC-01 · P0 · 匿名请求可以修改管理员密码【复现】

- 位置：`app/web/views/subscription.py:84-107`；关联的订阅修改/查询入口 `:11-81,110-127`。
- `/subscribe/settings` 没有登录或邮箱所有权验证，按表单 `email` 查 `User`，直接写 `password_hash`，没有排除管理员。
- 本地 CSRF 保持开启：匿名获取自己的表单 token 后，成功修改隔离管理员密码，并用新密码访问 `/admin/` 得到 200。**CSRF 保护不是身份认证。**
- 同类问题：按邮箱查看他人订阅/资料、按 `sub_id` 删除或切换订阅，不检查归属；公开订阅入口可给他人邮箱增加订阅。
- 修复：账户设置使用 `login_required` + `current_user`；改密要求旧密码或已验证、短期、单次重置凭证；订阅操作按归属过滤。匿名邮件偏好管理只能用用途限定签名 token，不能改账户密码。增加双重确认订阅、会话撤销。
- 验收：匿名/跨用户修改均拒绝；管理员与普通用户同等保护；合法本人改密和单次重置成功。
- 若已经公网部署，先关闭相关修改入口并检查访问日志和账户变更，**不能仅凭本报告断言已被入侵**。

### SEC-02 · P1 · AI Insight 存储型 XSS 输出【复现】

- 位置：`app/__init__.py:118-174`、`app/web/templates/news/detail.html:113-116`。
- `markdown_light` 导入 `escape` 却没有使用，直接拼接模型文本并 `Markup(html)`。模型/外部内容可以包含 HTML，文章详情会原样输出事件属性。
- 探针确认 `<img ... onerror=...>` 原样进入响应；未运行浏览器脚本。相邻 `paragraphs` 过滤器有转义，不能以它安全推断另一个过滤器安全。
- 修复：先转义全部文本，再做有限 Markdown 格式化，或使用禁用原始 HTML 的渲染器加允许列表净化；URL 单独校验 scheme。CSP 是纵深防护，不替代净化。
- 验收：正文/标题/表格/列表各位置的 HTML、事件属性、危险 URL 测试，保留正常加粗/表格展示。

### SEC-03 · P1 · 网络抓取缺少 SSRF/响应大小限制【传输 mock + 静态】

- 位置：`app/utils/website_fetcher.py:19-50`、`app/llm/tasks.py:302-313`、`app/crawlers/rss_crawler.py:21-35`、各 `requests.get`。
- 公司官网既可能由管理员填写，也可能来自模型 `ai_analysis.website`；抓取直接允许重定向，不校验目标公网 IP、端口或域名。`MAX_CHARS` 在下载完之后截断，不是下载体积上限。
- 隔离传输 mock 证明 `127.0.0.1` 地址会直接交给 transport；没有实际探测内网。现有刷新主要由管理员触发，不把它误称为独立匿名 SSRF 接口。
- 修复：所有 HTTP/RSS/浏览器都经过统一安全 Fetcher：只允许 HTTP(S)、域名及端口策略、DNS/IP/跳转逐跳复检、阻断内网和 metadata 地址、DNS rebinding 防护、流式字节上限、连接/读取/总时限；结合进程网络出口约束。
- Agent 改造前必须完成；不能只靠提示词“不要访问内网”。

### OPS-01 · P1 · 构建镜像会包含本地敏感文件【静态】

- 位置：`docker/Dockerfile.web:14`、`docker/Dockerfile.worker:14`；仓库无 `.dockerignore`。
- 两个镜像 `COPY . .`，本地存在 `.env`、`.git` 和已跟踪 `scripts/data/fsourceinsight_full.sql.gz`。`.gitignore` 不影响 Docker 构建上下文。
- 修复：`.dockerignore` 排除环境、Git、备份/日志/临时文件；改为显式复制运行所需目录；镜像非 root、多阶段清理编译工具；运行时注入密钥。
- dump 是否含用户/密码哈希未读取验证；应由负责人检查脱敏与历史留存，备份改为加密存储并与源码分离。若既有镜像确实带密钥且已分发，评估轮换，不能靠新镜像覆盖旧层解决历史泄露。
- 验收：构建上下文与最终镜像不包含上述文件。

### OPS-02 · P1 · 通用生产 overlay 未关闭开发端口/挂载【配置实证】

- 位置：`docker-compose.prod.yml:9-10,23,36,46,66,74`。
- `base + prod` 实际保留 `8001:8000`、`3306:3306`、`6380:6379` 与应用源码 bind mount；nginx 还保留 8080。`ports: []` / `volumes: []` 不清空合并结果。
- **限定范围：加上 `docker-compose.caddy.yml` 后已正确清空，并将 web 绑定 `127.0.0.1:8800`。** 不推断现网使用错误组合。
- 修复：通用 prod 同样使用受支持的 `!override`/`!reset` 或独立完整生产配置；所有运行手册统一 Compose 文件集合、校验插件能力；开发端口也建议绑定 localhost。
- 验收：CI 解析每个官方支持组合，断言 DB/Redis 无 published ports，应用无源码挂载。不要把 UFW 当成 Docker published port 的唯一防线。

### OPS-03 · P1 · 重复部署默认导入 dump，可能覆盖现有数据【静态】

- 位置：`scripts/deploy.sh:78-86,179-188`；`scripts/restore_db.sh:18-32`。
- 部署脚本允许已有仓库更新，之后只要 dump 文件存在就执行完整恢复，没有“空库/首次部署/显式 restore”区分。默认 dump 受 Git 跟踪。
- 修复：部署仅升级代码和迁移；恢复是单独、显式确认的操作，先备份/暂停写入/记录目标库和快照校验和。恢复前后检查迁移 head、行数和完整性。
- 历史部署计划把 `down -v` 列为回滚，会删除持久卷；应拆为“保数据回滚”和明确确认的“彻底销毁”，不要混用。
- 验收：重复部署不执行恢复、保留新增记录；演练恢复只用隔离库。

### OPS-04 · P1 · 缓存与任务 broker 共用可驱逐 Redis【静态】

- 位置：`docker-compose.prod.yml:76`、`app/config.py:15-19`。
- 同一 Redis 实例承担 7 天 LLM 缓存、broker、result backend 和控制状态，且配置 `allkeys-lru`。Redis DB 0/1 仅分逻辑空间，共享内存/驱逐策略；缓存压力可能驱逐任务队列或锁/熔断键。
- 修复：broker/control 与 cache 分实例；broker/control 不驱逐并配置持久化，缓存独立限额/TTL；针对 OOM 显式报警与重试，不悄悄丢任务。
- 验收：缓存压力测试不影响排队任务，broker 重启/满额可恢复且有告警。未执行实际压力实验。

## 3. 爬虫与任务可靠性

### CR-01 · P1 · 无质量门禁，空跑和错误页面可能被视为成功【复现 + 静态】

- 位置：`app/crawlers/base.py:85-116`；`sources/research_lab.py:51-110`、`sources/usine_digitale.py:22-66` 等。
- `[]` 一律记 `success` 并更新 `last_crawled_at`；若各站点实现逐页捕获网络错误再返回空数组，源健康检查也看不到失败。
- 多数 HTML 源提取“链接+标题”而无正文/日期；下游 `app/llm/tasks.py:29` 仍以标题生成摘要/洞察。研究所新闻页可能把导航、目录当文章，Linksium 还把企业目录记录作为文章输出。
- 修复：Fetch/Parse/Quality 分离，返回每页状态、发现数、解析数、有效数、正文完整度和原因；区分 `no_change`、`partial`、`degraded`、`blocked`、`failed`。未满足正文契约只能保留元数据，不作为完整文章进入深度洞察。
- 验收：0 新增但已知页面健康不能触发学习；选择器失效、登录页、403、200 错误页各有不同结果；有效条目不被坏条目拖垮。

### CR-02 · P1 · 爬取失败绕过 Celery retry【复现】

- 位置：`app/crawlers/base.py:108-115`、`app/crawlers/tasks.py:28-47`。
- `run()` 把一般网络/解析异常转为 `result.errors`，任务返回正常结果；只有外抛异常走 `self.retry`。
- 修复：类型化错误，按策略重抛可重试异常；结构漂移进入 repair，403/付费墙进入人工审核，429 尊重 Retry-After。退避、抖动、总尝试次数统一计算。
- 验收：网络错误触发有限重试；解析漂移不被网络重试掩盖；失败任务和 CrawlLog 状态一致。

### CR-03 · P1 · 批内/并发重复可导致整批失败且日志卡 running【复现】

- 位置：`app/crawlers/base.py:45-60,62-83,108-115`；唯一约束 `app/models/article.py:59-63`。
- dedup 只查 DB，不消除本批相同 external_id；并发任务也可能同时“查无数据”。写入冲突后缺少 rollback，错误处理再访问 ORM 字段/提交时触发 `PendingRollbackError`。
- 探针：两个相同原始条目都通过 dedup，最后文章 0 条，日志仍 running。
- 修复：批内去重 + DB 唯一键兜底的 insert/upsert/保存点；失败先 rollback，再用独立短事务记录错误。不能仅“捕获 IntegrityError 然后继续用旧 session”。
- 验收：批内重复、两个并发 worker、单条超长字段、崩溃恢复均不损失其他合格文章。

### CR-04 · P1 · 抓取/LLM 派发缺少认领、锁与可靠交付【静态】

- 位置：`app/crawlers/tasks.py:72-75,95-111,150-164`；`app/llm/tasks.py:17-26`。
- 日调度、频率调度、手动入口可重复派发；Redis 检查是 GET→SET，不是原子 source 认领。LLM 派发扫描该源**所有未处理文章**，不只当前新增；消费端仅在开头检查一个 boolean，无法抵御同时开跑。
- “文章已提交→消息未发送”故障窗口没有 outbox。尤其本轮重试无新增时不会再次派发，既有 backlog 可能悬挂直到人工操作或后续新增。
- 修复：source/run lease + article task 原子认领；outbox 与业务记录同事务，dispatcher 可重试；run 只返回新建/需更新的 IDs；周期补偿扫描具备状态、重试上限和终态。
- 验收：同源多触发仅一有效 run；消息重复不重复付费；提交后 broker 失败最终可补偿。

### CR-05 · P2 · URL 解析不正确、身份策略不统一【复现 + 静态】

- 位置：`app/crawlers/html_crawler.py:115-122`，`sources/tribune_aura.py:39-61`、其他自定义拼接逻辑。
- `/section/` 页面上的 `/story/1` 被拼为 `/section/story/1`；协议相对、`../`、重定向后的相对地址也未统一处理。部分源直接持久化 href。
- 修复：针对最终响应 URL 使用 `urljoin`，其后再校验/规范化；URL canonicalization 与外部 ID 分开。策略切换必须兼容旧 RSS GUID/hash，不然同一篇被重新导入。
- 不能简单全局删查询参数/fragment：一些 SPA 和 Linksium 现有 fallback 用它区分记录。追踪参数规则应显式、可版本化。

### CR-06 · P1 · 管理员爬取时间设置实际不能调整 Beat【复现】

- 位置：`celery_app.py:33-41`；`app/crawlers/tasks.py:51-78,82-104`。
- Beat 固定 Paris 01:00，DB 设置仅在任务里检查时刻。设置 14 点后，01:00 任务会跳过而不是等到 14 点。频率检查虽然每 10 分钟触发，却默认 6 小时自限流，源 60/120 分钟频率达不到。
- 修复：单一周期 scheduler 计算 `next_due_at`、时区、租约；日历/周期模式明确选一或定义合并去重，不保留互相矛盾的两套时间逻辑。
- 验收：跨日、DST、14 点设置、小时级源、手工触发均按预期运行且无重复。

### CR-07 · P2 · 企业发现阻塞 crawl/email worker，失败隔离不完整【静态】

- 位置：`app/crawlers/startup_discovery.py:186-249,289-345`；`docker-compose.yml:43-58`。
- 扫描任务循环所有发现源；新发现后直接同步调用最多 20 家企业的 LLM 分析，跑在 `crawl` 队列，而 `worker_fast` 还共用 email。一个慢目录/模型可占住 fast worker。
- `_generate_analyses_for_new(source)` 没按 source 限定 pending 企业；没有新发现就不补处理旧失败；异常 catch 缺 rollback 还可能污染后续源。
- 修复：每源扫描独立任务；发现结果带来源关系；LLM 走独立 llm task；pending 修复不依赖“本轮有新企业”；状态机按失败类型重试。
- V1 动态改造先只做新闻，发现目录先复用安全 Fetcher/日志，后续用不同输出契约接入。

### CR-08 · P2 · 站点类型与运行策略脱节，改源配置不一定生效【静态】

- 位置：`app/crawlers/registry.py:23-45`、`app/crawlers/sources/cea_leti.py:12-20,39-41`、`sources/soitec.py:23`、`scripts/seed_sources.py`。
- registry 总是先按 slug 选自定义类；一些源 seed 的 feed_type=RSS，运行却是硬编码 HTML 页面。Admin 改 URL/feed_url/crawler_class 可能仍被注册类及代码常量覆盖，难以从 DB 解释实际抓取策略。
- 修复：记录 effective strategy、实际入口 URL 与配置来源；recipe 成为明确优先级的配置版本，legacy override 在 UI 中显式展示；不要靠静默 fallback 掩盖无效配置。
- 验收：编辑源后能预览生效策略/URL；schema 模式不被旧 slug 注册抢先选中，旧源迁移前行为保持可回滚。

## 4. LLM / 数据一致性

### DATA-01 · P1 · 迁移与模型不一致，新库用量表不接受 digest/insight【离线 SQL】

- 位置：`migrations/versions/e5a1e5acc4cc_initial_schema.py:186-201`、`5b8500892c32_add_insight_fields_and_insight_task_type.py:19-25`；`app/models/llm.py:32-33`。
- 模型是 `String(50)`，完整迁移仍生成 `ENUM('translate','summarize','ner','sentiment','classify')`。名字包含 insight 的迁移只新增文章字段，没有修改用量 task_type。
- 新装 MySQL 严格模式下写 digest/insight 用量会失败；非严格模式也存在值被截断/污染的风险。生产可能曾手改或由 dump 修正，**本轮未验证生产 schema**。
- 修复：新增前向迁移同步类型，旧 revision 不做静默改写；空库和带数据升级后验证模型/库无 diff。
- 同时审查 `source_type NOT NULL`、`ai_analysis_failures NOT NULL` 无 server default/backfill，以及 Text→JSON 对旧非 JSON 值的处理。后者取决于历史数据，列为升级前检查项，不断言所有 MySQL 升级都会失败。

### LLM-01 · P1 · 用量记录提交业务中间态，分类重试不幂等【复现】

- 位置：`app/llm/client.py:193-210`、`app/llm/tasks.py:157-172`。
- 每次模型调用的日志 `commit()` 提交共享 session 中所有待写字段/关联。后续任务 rollback 撤不回已提交中间态；分类再次插入撞 `(article_id, category_id)` 主键。
- 日志入库异常还会被当成供应商失败，可能错误熔断/切换提供方。
- 修复：用量 ledger 独立 session/事务，业务以 pipeline step 记录结果并幂等提交；分类做去重/upsert/原子替换；区分 transport、模型校验、存储错误。
- 验收：每个步骤后注入异常再重试；已完成关联无重复，费用记录保留，数据库错误不触发供应商 fallback。

### LLM-02 · P1 · “主模型/备用模型”实际上按价格混选【复现】

- 位置：`scripts/seed_llm_configs.py:23-81`、`app/llm/client.py:52-94`。
- 用当前 seed 配置验证：NER/classify 选 `gpt-5.4-nano`，insight 选 `deepseek-chat`，并不是文档的 mini 主模型。nano 未配置 digest；`is_default` 不是 task 主模型优先级。
- 修复：DB 中明确 `task→primary/fallback priority` 与能力需求（结构化、分析、语言）；在同一优先级/能力组内才按成本排序。Admin 展示复用真实路由 resolver。
- 模型价格是 seed 值，未外部核价；不要把本报告视为最新价目表。迁移时读取实际 DB，不用 seed 覆盖用户配置。

### LLM-03 · P2 · 缓存没有完整输入/版本身份，“刷新”可能返回旧结果【复现】

- 位置：`app/llm/client.py:126-139,315-326,388-426`。
- company 缓存忽略新闻、官网实际内容、描述、阶段等，仅有 name/sector/has_site；digest/insight key 忽略 title；所有 key 缺 prompt/schema/model/routing 版本。
- 修复：以完整规范化 messages + 输出契约 + prompt/model/参数版本计算 key；明确 force refresh 和配置版本失效策略；对企业自动刷新先比较输入 hash。
- 验收：输入变化命中不同缓存，未变输入不重复付费；调整 prompt/结构版本不会继续读 7 天旧结构。

### LLM-04 · P1 · JSON 解析失败被缓存成“无实体/中性”，缺少结构验证【复现 + 静态】

- 位置：`app/llm/client.py:248-258,289-293,328-386`、`app/llm/tasks.py:93-172,350-362`。
- 非 JSON 返回变 `[]` 或 neutral 并缓存，不能区分“合法无实体”和“解析失败”；合法 JSON 也未验证每项类型、枚举、分数、数量。company analysis 解析失败可返回 list，后续 `.items()`/`.get()` 异常。
- 修复：按任务做严格输出契约验证（例如 Pydantic），语法与业务字段分别验证；失败有限重试/降级，不进入正常结果缓存；输出不完整就标记对应步骤未完成。
- Agent schema 生成必须复用更严格契约，不能复用“解析失败返回空列表即成功”的逻辑。

### LLM-05 · P1 · 预算为软检查，无法作为 Agent 的硬成本边界【静态】

- 位置：`app/llm/client.py:103-122,143-222`；`app/llm/tasks.py:14-16`。
- 只在调用前查询已记账费用；并发任务可以同时通过，单调用可超剩余预算。fallback 不单独预留，费用字段缺失会不记 cost。`10/m` 是 worker/task 级速率，且每篇是约 `11 + 公司数` 次模型调用（有正文、未算公司刷新），不是每分钟 10 次 API 请求。
- 修复：调用前原子预留最坏 token 成本，成功结算差额，失败/超时记录未知费用并保守处理；用户全局/Agent 独立子预算/会话预算共享账本约束；限 provider 请求和并发；明确总超时、总尝试数与 visited configs。
- 验收：多个 worker 争用最后一笔预算只一个获得许可，预算/账本不可用时学习 fail-closed。账本限额仍需与供应商计费延迟区分。

### LLM-06 · P2 · Redis 异常不降级，熔断半开不止一个探针【复现 + 静态】

- 位置：`app/llm/circuit_breaker.py:38-118`；`app/llm/client.py:130-139,70-71`。
- 有 Redis 对象但 I/O 失败时异常直接传播；in-memory 分支仅处理对象不存在。故障计数 GET→SET 可丢并发更新；恢复超时后所有请求都可进入，并未限定“single test request”。默认 provider 还能绕过 open 状态。
- 修复：原子计数/状态迁移 + 半开探针 lease；共享状态失败策略明确。响应 cache 可以降级 miss，但预算/锁不能一概 fail-open。每 app 依赖从 `app.extensions` 容器获取，避免模块级 `from ... import redis_client` 在多 factory 中保留旧对象。
- 验收：Redis 断连、并发失败、半开蜂拥、多个 app 实例隔离。

### DATA-02 · P2 · JSON 修订历史可丢失、自动刷新可能覆盖人工内容【部分复现】

- 位置：`app/llm/tasks.py:175-223,239-283`、`app/web/views/admin.py:263-272`。
- `_save_revision` 对已有 list 原地 append 再切片，SQLAlchemy 非 Mutable JSON 未识别真实差异。探针确认已有历史后新增修订提交/重载丢失；aliases 合并同样使用原地 list 修改模式。
- 自动文章刷新直接用新 analysis 全量覆盖旧数据，官网刷新路径却做非空 merge；两套策略不一致。模型被提示无证据时返回空字符串，全量覆盖可能清掉有效内容。
- 修复：不可变复制后赋值（或合适的 Mutable 类型）；单独 append-only revision 表；统一 merge policy，人工确认字段/证据来源独立保存，不让空值或低质量自动结果覆盖。
- 验收：非空历史连续修改可追踪；人工字段不被自动清空。

## 5. 邮件、页面、性能和工程能力

### MAIL-01 · P1 · 邮件模板路径错误；修复路径后仍遗漏 Top Insights【复现】

- 位置：`app/__init__.py:18-24`、`app/email/sender.py:15-20,53-57`、`app/web/views/admin.py:843-848`、`app/email/digest.py:76-84`。
- loader 指向 `app/email/templates`，实际可加载 `daily_digest.html`，调用却是 `email/daily_digest.html`；两种邮件都 `TemplateNotFound`。
- sender/preview 只传常规 `articles`，没有 `top_insights`，已被 digest builder 分走的高亮文章不会出现在邮件里。
- 修复：统一模板 namespace + 一个完整 `DigestViewModel`；同时修复 preview 和实际发送，不只修模板文件名。
- 验收：混合文章、全高亮、空日报、三种语言邮件均正确；SMTP mock 验证内容而非仅是否调用。

### MAIL-02 · P2 · 缺少投递幂等和真实退订入口【静态】

- 位置：`app/email/tasks.py:10-41`、`app/email/sender.py:22-46`、`app/email/templates/daily_digest.html:113-124`。
- 每次执行扫描过去 24h，手动重复派发可重复发；无 user/type/window 唯一 delivery key。发送成功但记账失败可能重发。模板偏好/退订仍 `href="#"`。
- 修复：邮件 outbox、固定时间窗口、投递 attempt 状态、分页/批量生成；合法签名退订链接和 consent 记录。SMTP 不承诺严格 exactly-once，应明确“发送结果未知”状态与处理策略。
- 验收：重复调度不正常重发、退订有效；发送后 DB 失败可审计。未对外发送任何邮件。

### UI-01 · P2 · 企业地图和文章列表存在 N+1【查询计数 + 静态】

- 位置：`app/web/views/company.py:18-35,65-74`、`app/models/company.py:45-49`、`app/web/templates/news/_article_list.html:41-49`、`app/api/v1/routes.py:179-193`。
- 每家公司分组重新查询 SectorGroup。隔离的 **25 家公司地图请求执行 28 条 SQL，其中 26 次查 sector_group**。
- 文章卡片逐条查 categories/companies/company；API 公司列表每项 article_count 单独 count。
- 修复：每请求读一次分组映射；批量加载文章关联与 source；分页公司一次聚合 count。dynamic relationship 不能直接靠加 selectinload 魔法解决，需要列表专用批量投影。
- 验收：25/100/500 条 fixture 的查询次数有固定上界，不随每行关联数线性增长。

### UI-02 · P2 · 无界页面大小/全量扫描增加内存与响应压力【静态】

- 位置：`app/web/views/news.py:83-147,151-176`；`app/api/v1/routes.py:19-20,90-91`；`app/llm/tasks.py:107-115`；`app/email/digest.py:37-41,95-111`。
- 首页 per_page 无业务上限；高亮加载所有匹配文章后 Python 排序；筛选器读全部公司；NER 每个未直接命中的名字重扫所有公司；每用户重新查询日报/关键词全文 LIKE。
- 修复：统一参数范围（页面大小 1–100）、列表只投影所需字段；高亮可查询字段/关联表 + DB 排序分页；公司 alias 规范化可索引；新闻批量缓存按语言复用；全文检索/专用索引按实际 EXPLAIN 决定，不盲目加 Elasticsearch。
- 索引候选：article `(source_id,llm_processed,crawled_at)`、处理状态调度索引、规范化 alias 唯一索引；上线前用真实数据 EXPLAIN 验证成本。

### UI-03 · P2 · 日期边界、时区与周趋势不正确【复现】

- 位置：`app/web/views/news.py:61-65`、`app/api/v1/routes.py:44-48`、`app/crawlers/html_crawler.py:95-113`、`app/web/views/company.py:270-308`。
- date_to 使用当天 00:00 上界，排除了当天中午文章；应使用 `< 次日00:00` 的半开区间。
- +02:00 抽取日期存入 timezone=False DateTime，隔离保存 `14:00+02` 后变 naive 14:00，而不是 UTC 12:00。
- 周聚合按 yearweek+sentiment，随后用每个分组自己的 min(date) 生成键；同一周正/负情绪若日期不同会裂成两桶。标签又丢年份并按 MM/DD 排序，跨年异常。
- 修复：UTC 存储、显示时转换；保留源日期原文/时区置信度；按年周或周一日期作为主键，展示层再格式化。`yearweek` 为 MySQL 特有，SQLite 不能替代该查询集成验证。

### OPS-05 · P2 · 通用备份脚本与容器部署不匹配【静态】

- 位置：`scripts/backup_mysql.sh:10-37`、`scripts/deploy.sh:45-52,222-223`。
- 默认依赖宿主机 `mysqldump` 和 localhost:3306，部署步骤未装客户端，且安全生产配置应该不暴露 DB 端口。
- 历史 Caddy 计划已写 VPS-local 容器内备份 wrapper，**本问题针对仓库通用脚本，不声称 VPS wrapper 当前失效**。
- 修复：将 Docker-aware wrapper 纳入维护，明确 Compose 项目；失败先写 `.partial`，校验成功原子改名；加密、异地副本和恢复演练，记录备份大小/时刻与失败告警。
- 验收：在无 mysql-client、无公开 3306 的隔离主机可备份并恢复；中断产物不冒充成功备份。

### OPS-06 · P2 · JSON 日志不是合法 JSON，健康状态不代表管线正常【复现 + 静态】

- 位置：`app/logging_config.py:11-15`、`app/web/views/health.py:13-94`。
- 手工 format 拼 JSON 不转义引号/换行，探针 `json.loads` 失败；多进程共写 RotatingFileHandler 还有轮转竞争风险。
- `/health/detail` 的 `unprocessed_queue` 是 DB boolean 计数，不是 broker 队列深度；不报告运行中/卡死任务、schema 质量、学习费用；明细公开。
- 修复：真实 JSON formatter + stdout 容器日志；run/task/source/schema 关联 IDs；liveness/readiness/pipeline-health 分开；对外返回简化健康信息，内部明细鉴权并限制超时，跟踪 freshness/正文合格率而非只 HTTP 200。

### TEST-01 · P1 · 没有可执行回归测试与迁移校验【实证】

- 位置：`tests/`、`tests/conftest.py:6-25`、`requirements/*.txt`。
- 当前 tests 仅 fixture 和空包，0 个测试函数，没有 CI 配置；依赖全为下限约束，无可复现 lock。
- SQLite fixture 通过 create_all 绕过迁移，因此不会发现旧 Enum 与当前 String 不一致；nested transaction fixture 也需要验证业务 commit 后是否泄漏到下一个测试。
- 修复：优先补 SEC-01/02、CR-01/02/03、LLM-01、MAIL-01 的行为回归；无网络爬虫 golden fixtures；MySQL/Redis 集成测试和迁移前后 model diff；每官方 Compose 组合校验；依赖锁定和升级 CI。
- 本轮离线探针断言“当前缺陷存在”，只作审查证据，不应加入正常 CI 作为正确行为测试。

### SEC-04 / ENG-01 · P2/P3 · 后续硬化与模块简化【静态】

- `app/web/views/auth.py:20-22`：next 未限制同站，开放重定向；setup 公开且先到先建管理员，应改一次性初始化凭证/CLI；登录限流、密码规则、停用账户会话撤销补齐。
- `app/config.py:5,36-43`：生产允许默认 dev secret；启动 fail-fast 校验 SECRET_KEY、DB、必需配置；HTTPS cookie、trusted proxy/host、错误信息脱敏按部署路径设置。
- `app/web/views/admin.py:120-130,357-373`：表单缺少统一枚举/范围/URL 校验，错误输入可导致 500；删除已有 usage 的 LLMConfig 受非空 FK 阻止，推荐软停用保留审计。
- `app/web/views/admin.py` 达 848 行；`scripts/run_llm_process.py` 与任务重复实现 pipeline。按业务用例抽取深模块，CLI、Web、Celery 共用接口，不再复制步骤。
- 静态资源无内容 hash 却 30 天 immutable；改 fingerprint 或合理 revalidate。CDN 脚本固定版本但无 SRI/CSP，逐步自托管/加校验；模板语言与键盘可访问性需要浏览器 QA，未作合格断言。
- README/CLAUDE/部署文档对源数、6/7 个服务、调度间隔、LLM 路由存在漂移；文档应从配置/测试输出校验，不写无法验证的“当前生产统计”。

## 6. 保留的合理设计

- Flask/Jinja/HTMX 足以支撑当前产品，不需要为 Agent 更换前端框架。
- `RawArticle` 是合适的初始规范化输出 seam，可逐步扩展来源/质量，而不是直接让 LLM 写 ORM。
- source+external_id、article+company 的 DB 唯一约束有价值；要补幂等处理而非删除约束。
- LLM provider 配置在 DB、密钥只存 env var 名称是正确方向；需要补任务优先级、版本和审计。
- 已拆分 llm 与 fast worker，有利于资源隔离；但企业发现场景绕过此分工，浏览器/学习任务也应独立。
- Caddy overlay 已正确修复专用部署的端口/挂载继承问题，应把这个能力推广到通用生产路径。

## 7. 本轮没有做的事

未更改业务代码、依赖声明、数据库迁移、生产服务；未执行真实爬取/LLM/邮件；未推送或提交。架构中的发布权限、预算、浏览器范围等见设计的待确认项，用户确认后才进入实施。
