# 全项目审查与动态爬虫 Agent 改造

## 目标与范围
- 用户要求：全量检查当前项目、提出具体优化点，并依照给定流程图设计动态 Agent 爬虫改造。
- 基线：master，bf9cc61b94556e00218af267db82bf42a3b80eef；初始工作区干净。
- 审查与方案已完成。用户已同意 5 项默认建议并授权开始实施：V1 仅新闻、schema 人工批准、元数据可保存但仅标题不生成深度洞察、隔离公开页面渲染、3 轮/US$0.20 每次/US$1 每日且受总预算约束。
- 已完成的M1发布授权：用户要求直接生产，已按 docs/superpowers/plans/2026-09-07-m1-release.md 完成提交/备份/CI与候选门禁/增量迁移/四应用切换，当时生产应用1052edf/schema e6；该历史发布不再有待执行阶段。
- 随后用户在架构导览后要求“继续”，推进M2本地。用户已选择后台HTTP作为M2主要验收入口，从真实页面操作逐切片TDD，不增加测试专用API；不继承上次提交/SSH/部署授权，不额外真实爬取/付费LLM/邮件，不使用子代理。

## 当前追加：Worker并发与任务后回收发布
- [in_progress] 用户明确继续实现，并保留合入/部署授权。按 docs/superpowers/plans/2026-09-10-worker-recycling-release.md：仅生产LLM并发2，两worker任务后回收，真实Compose/隔离broker与现有Admin任务验收；不改另外两个项目或触发生产付费/新闻任务。

## 当前追加：服务器整体容量评估
- [complete] 只读整机容量核算完成，报告 docs/audits/2026-09-10-server-capacity.md：4vCPU/7.57GiB RAM/无swap、当前可用3.78GiB，1056个已有sar样本最低3.38GiB。现负载可承受fast1GiB/beat384MiB，不必立即升级；其他项目无硬限、LLM834MiB、维护叠峰为风险。无生产修改/重启/安装/提交，优化建议未实施。

## 当前追加：M2-B2b.1提交与部署
- [complete] 用户新授权已完成：应用14dc6f1/schema c9，06:15:19Z→06:15:25Z切换；本地639/15、CI34443459274两job、真正web/worker切换前后四轮各15 MySQL通过。详见 docs/audits/2026-09-10-m2-policy-release.md。仅四应用更新，保留私有卷，测试资源/凭据清理完毕；无额外真实新闻/模型/邮件。
- 预检确认旧fast发生MEMCG子进程OOM（父进程存活/restart0），已TDD修改上限fast1GiB/beat384MiB；这是容量缓解，根因/长期峰值仍需另验收。收尾仅文档提交/准确CI与checkout同步，不重建运行镜像。

## 当前追加：M2-B2b本地继续
- [complete] 用户发布后继续，从clean e98af16完成B2b.1本地：持久策略/质量版本→真实preview约束→撤权/来源ABA使旧回放失效→历史/diff。新增60 HTTP/2迁移，全套638/15、166 AST/45模板/指定flake8及单head c9通过，见 docs/audits/2026-09-09-m2b2b-policy.md。
- [pending] B2b.2独立留出验证、长期验证/审批审计、规则diff与人工批准/拒绝/回滚/CAS；此前待跑的15 MySQL已在本次独立远端/CI补齐，policy新并发/压力/恢复仍后续。
- 沿用真实Admin HTTP逐条TDD；不继承上次SSH/提交/部署授权，无真实新闻/模型/邮件/子代理。独立留出验证和人工发布另一个切片，不把policy保存称作审批完成。

## 最近生产发布（已完成）
- [complete] 用户另行要求“部署一下生产”，按 docs/superpowers/plans/2026-09-09-m2-partial-release.md 完成A/B1/B2a上线：应用22c098c/schema b6，15:25:00Z→15:25:06Z切换；本地576/14、CI两job及真正web/worker各14 MySQL通过，私有Docker卷跨容器捕获/锁/回放通过。
- [complete] 专用仅web证据卷0700，仍默认不留原文；备份/回滚镜像保留，临时资源精确清理，MySQL/Redis/Caddy/其他项目未变。报告 docs/audits/2026-09-09-m2-partial-release.md。beat约245/256MiB余量小已记录，无OOM/重启；不代表压力/完整恢复验收。
- [pending] B2b持久policy/独立验证/人工审批/CAS、可靠run/outbox、统一调度及M3/M4仍后续，旧日常链未切换。

## 已完成的追加授权：主干合入
- [complete] 当前M2-A/B1/B2a及配套文档已以90c94b6提交/推送至master；CI34356717036两job成功，离线574/14、独立MySQL14/14。详见 docs/superpowers/plans/2026-09-08-m2-mainline-integration.md。没有部署或把未来功能标为完成。

## 阶段
1. [complete] 核对项目结构、现有行为和用户流程图。
2. [complete] 主会话完成全部后端模块/爬虫/模型及关键部署脚本人工审查，模板全体静态扫描/编译；不声称前端视觉全覆盖。
3. [complete] 临时 Python 3.12 环境验证：18 项缺陷探针复现；额外 ORM/SQL 查询与时间探针；103 个 Python AST、40 个模板编译、shell 语法通过；Compose 合并与 13 个 MySQL 迁移离线 SQL 核对。原有 pytest 为 0 tests (exit 5)，未做生产/MySQL 实机/真实爬取/真实 LLM/浏览器验证。
4. [complete] 已输出 docs/audits 审查/验证报告与离线探针，docs/superpowers 下架构草案和分阶段实施计划。
5. [complete] 已复跑保存后的 18 项探针并核对结果一致，文档链接/行号范围/代码块检查通过；确认 Git 基线未变、业务代码无修改。报告明确未验证范围，实施待用户确认范围/发布/内容/浏览器/预算。

## 实施阶段（用户已授权，不使用子代理）
6. [complete] M0当前已批准基础切片代码/验收/发布完成。M0.5代码6451b36、迁移d472已部署；本地131项、两候选各10项MySQL、CI两job和公网/worker门禁通过。后续硬预算/消息可靠性/网络安全等不在此完成声明内。
7. [complete] M1已部署：契约、Safe Fetch、HTML/RSS/JSON-LD执行/回放、基础Adapter、手工CLI、质量及入库/下游保护。离线459通过、CI及两真正候选各12项MySQL通过；旧自定义出口未全迁移、自动schema路由仍属M2。
8. [in_progress] M2-A候选保存、B1后台预览、B2a私有证据/回放本地完成。B2a新增49 HTTP，全套574 passed/14 MySQL专用skip，147.67秒；158 AST/43模板/指定flake8通过，无新DDL/head仍b6。报告 docs/audits/2026-09-08-m2b2a-private-evidence.md。90c94b6已合入master，本提交CI MySQL14/14也已实跑通过。A/B1/B2a随后已按独立授权发布22c098c/b6（见顶部记录）。B2b.1持久policy闭环随后已发布14dc6f1/c9（本地639/15、远端15项与CI通过）；独立验证/人工审批/CAS、路由/可靠运行仍未完成。
9. [pending] M3 有界学习、预算账本与候选验证。
10. [pending] M4 浏览器隔离及小范围上线前验证（上线/真实访问另行授权）。

## OVH SQL 验证与首批发布（新授权）
11. [complete] SSH france-vps 成功，远端工作区干净且 bf9cc61；生产MySQL8.0.46已为目标VARCHAR，readonly model diff=0。
12. [complete] 独立 MySQL8.0.46/合成数据 7项通过，包含空库/旧Enum/已有VARCHAR/JSON和counter/回滚/并发；新增迁移跳过重复ALTER，先red后green。
13. [complete] 提交ea96dde与运维门禁修复858a14b；备份、旧镜像保留，最终候选7项MySQL复验通过后部署。仅四个应用服务重建，MySQL/Redis/Caddy/其他项目未改。
14. [complete] 公网health/login/www 200，匿名有效CSRF被拒绝、worker就绪、生产model diff0；临时资源已精确清理，发布和回滚点已记录。M0.5及Agent另行按TDD继续。

## M0.5 当前交付与后续
- [complete] 先红后绿：独立用量、只读收集/原子应用、12步失败重试、关系幂等、严格JSON/结束原因、完整版本化缓存、显式主备路由与CLI/Admin兼容。
- [complete] 本地77项LLM+2项迁移+52项既有回归通过；123 AST/40模板/shell/静态错误检查通过。详见 docs/audits/2026-09-06-m05-implementation.md。
- [complete] 按 docs/superpowers/plans/2026-09-06-m05-mysql-validation.md 完成OVH独立MySQL8.0.46两轮10/10实跑；未提交/部署或迁移生产库，线上容器身份/启动时间/重启数未变。临时资源/凭据已清理，见 docs/audits/2026-09-06-m05-mysql-validation.md。
- [complete] M0.5提交6451b36/CI34036731442通过，备份m05-20260906134051，候选web/worker各10项MySQL通过；生产d472/配置指纹不变，13:53:46Z→13:53:51Z应用切换成功。仅四个应用更新，其他容器未变，临时资源已清理。详见 docs/audits/2026-09-06-m05-release.md。
- [complete] M1.1配置校验/标准结果契约按TDD完成，见 docs/audits/2026-09-06-m11-contracts.md；未接入旧爬虫、未提交部署。
- [complete] M1.2本地实现/验收/文档完成：90项Safe Fetch、官网与旧入口兼容回归，全套374 passed/10专用MySQL skip，见 docs/audits/2026-09-06-m12-safe-fetch.md；未提交部署。并发硬预算、lease/outbox、Redis断路器异常等仍未修。

- [complete] M1.3/M1.4本地交付：75项引擎/CLI、LLM6、迁移1、HTTP3新增回归；总459/12，147 AST/40模板/指定静态检查通过。最小三标记迁移e6从M2前移；历史NULL不回填，M1 run不发布配置、不派repair。
- [complete] M1直接发布：1052edf/e6，CI34091467749成功，两最终候选各12/12；06:47:58Z→06:48:03Z切换并健康。备份/旧镜像保留，临时资源精确清理。本站真实TLS与基础billiard smoke通过，真实新闻源/长期压力仍后续；见 docs/audits/2026-09-07-m1-release.md。

## 当前追加：架构与代码导览
- [complete] 基于4477cfd核对旧调度/registry、M1双helper/门禁/事务、LLM及实际存储，输出 docs/architecture/2026-09-07-dynamic-crawler-code-map.md（当前/目标两图、代码入口与执行逻辑）。47个链接/行号锚点与围栏检查通过。仅本地文档，不改业务、不提交部署、不访问生产或真实源，M2–M4未实施。

## M2 验收安排（用户已选择后台HTTP）
- Admin HTTP：来源配置/候选保存、预览、批准/拒绝/回滚与运行证据；普通用户/匿名/CSRF/XSS保护。
- Celery是由真实HTTP触发的业务链路，优先从后台操作/运行报告验收；不为测试新增任务/API，不测试内部helper。
- 沿用Alembic命令和既有Article HTTP/API观察持久化结果。管理员“抓取现在”拟不额外顺延计划时刻，到期任务同次认领合并，避免紧接着重复抓取。
- 候选保存和预览HTTP切片已本地通过；保存不抓取，预览由管理员显式许可后执行M1并保存有限报告，不写Article/不派LLM/不激活。B2a已支持显式私有原始快照/回放，但还不是可审批的完整验证证据；后续持久policy/审批/可靠运行继续同一验收面。

## 已批准的验证接口
- HTTP：登录、本人偏好/订阅、跨用户访问、文章详情、邮件预览。
- 爬虫：BaseCrawler.run / RSS、HTML fetch_articles 的规范化输出、持久化结果和任务重试。
- LLM：公共任务方法 / process_article_llm，验证输出契约、可重试数据和用量事务。
- 运维：Compose 合并配置、Docker 复制范围、Alembic 迁移至 head。
- M1.1（已确认）：validate_recipe配置校验与标准结果数据契约；只通过公开构造/输出验证，不测试私有helper。
- M1.2（新确认）：SafeFetcher(policy).fetch(url)及渐进接入的RSS/HTML/官网入口；只替换外部DNS/socket/TLS/进程/时间边界，真实执行自己的安全实现。
- M1.3/1.4（已确认并实现）：CrawlEngine.preview只读抽取/回放与质量结果；CrawlEngine.run经同一门禁应用并返回CrawlOutcome。内部extractor/quality/identity不单独mock或增加验收接口。
- 采用用户已批准计划中的这些接口做测试，不为内部实现细节建立新验收接口。

## 关键设计约束
- 确定性爬取为主路径，Agent 仅用于发现/修复配置，不在每篇文章上无界运行。
- 源读取 → 已有 schema/通用 RSS-HTML-渲染 → 质量门禁 → 格式化结果，或有界 Agent 学习 → 验证 → 固化/人工复核。
- Agent 输出声明式 schema，不执行模型生成的任意 Python/JS，不把网页内容当指令。
- 全面检查不等于生产实测，报告中区分代码证据、可执行验证和待验证推断。

## 偏差与错误
- 历史实施期本地Docker socket不可用/PATH无mysqld；后来首批和M0.5均通过OVH专用隔离MySQL实测补齐，不能将本地skip算通过。
- SQLite legacy SAVEPOINT 提前提交在“第二条插入失败”回归中复现；已先更新实施计划，再在 SQLite 路径显式 BEGIN，13 项爬虫测试通过。
- 历史首批0.5曾因提前flush/FK锁风险推迟；已消除SQLite写锁且MySQL两轮验证通过，没有机械替换Session后直接上线。隔离runner首轮因cap-drop root不能读取ubuntu的700目录在收集前失败，改为UID1000后通过，未改变业务断言。
- 本地 pytest --collect-only 返回 exit 5：仓库无实际测试函数，不是测试通过。替代验证为离线缺陷探针、AST/shell 检查、Compose 配置合并和迁移离线 SQL；不得声称完整集成测试通过。
- 本机 Python 3.14/3.12 均无 Flask/Celery/pytest 等项目依赖，无法直接执行 pytest。已先调整验证计划：临时 Python 3.12 venv，依赖版本在验证记录中注明；不将新解析版本视为生产版本。
- 工作流 9a58ff2f-f6ae-4ffc-ac1b-593d81f7b190 的三个子代理均启动失败（web-security、llm-data、ops-tests）。错误：Background children require pi installed as the npm package (@earendil-works/pi-coding-agent) with its dependencies; /opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent does not provide @earendil-works/pi-server, @earendil-works/pi-server/unix, @earendil-works/pi-client/unix, so the async runner cannot create child sessions. A standalone pi binary cannot run background children.
- 子启动标识：78a0873a-dde3-40d2-b691-e00cfc6f212d / 008349cc-0d55-4312-bbe3-a78d4ed20dc9 / 030c21a4-ac3a-4ed2-93fe-3699046b62c3；返回 child run=unavailable, status=failed，无审查产物。
- 首次失败后已暂停并征求用户同意。用户现已明确批准“不使用子代理，直接进行”；本轮按此授权改由主会话直接审查，不修复 Pi、不调用子代理/其他 CLI。业务代码仍不修改，先交付审查与架构方案。
