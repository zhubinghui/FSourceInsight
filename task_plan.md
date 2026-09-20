# 全项目审查与动态爬虫 Agent 改造

## 当前继续：付费LLM必须保留，推进剩余部署（2026-09-20）
- [in_progress] 用户明确不要暂停付费LLM并要求剩余内容上线。先核实际端点/参数/价格与固定SDK合同，必要时公共LLMClient/Admin TDD补齐；不再以暂停模式作为本轮选项，不绕过新预算。计划docs/superpowers/specs/2026-09-20-m3-paid-continuity.md。
- [pending] 正常付费配置可验证后，完整M3准确CI/实际22项MySQL/服务及配置连续性门禁、新备份/受控迁移切换。学习默认不开启。

## 最新分批发布：不暂停现有AI（2026-09-20）
- [complete] 用户要求其他功能尽快上线，未授权停用现有AI；独立Admin批次e6469ba/schema b3于15:59:22Z部署。账号防自锁/密码邮箱/既有历史删除保护/采集时间设置上线，LLM代码/配置/runtime不变。
- [complete] 准确CI713离线/16实际MySQL/真实broker；两实际image各16 MySQL前后复验/48模板及Admin/真实broker通过，备份/受控切换/私有卷/数据保护完成。9测试容器/1网络/2卷及合成凭据已精确清理。
- [blocked M3] 不是M3发布；完整M3已提交分支，计费审核及自己的实际镜像/迁移门禁仍待。审计docs/audits/2026-09-20-admin-safety-release.md，具体计划docs/superpowers/specs/2026-09-20-admin-safety-release.md。

## 当前追加：全部现有内容提交与发布（2026-09-19新授权）
- [in_progress] 用户要求全部提交并部署；已提交推送751ac51，生产只读发现生态新版b08fb8d/b3；正在整合23de19e，唯一候选head c7f21a9d680e、startup-analysis.v2，保留两边业务。首轮CI5个Compose环境失败和第二轮MySQL造数遗漏已修正；7f6e9f8的CI35510122656通过1060离线/22实际MySQL/真实broker回收。后续e6469ba Admin安全及M3删除防护已合入1becae8；本地1075/22skip、准确CI35517521638的1075离线/22实际MySQL/真实broker全通过。全部应用内容已推release分支，实际待部署镜像/计费门禁仍待，未推master/未部署；候选审计docs/audits/2026-09-20-m3-release-candidate.md。执行计划 docs/superpowers/specs/2026-09-19-m3-current-release.md。
- [pending] 计费上界/真实价格审核或用户明确接受付费暂停模式；不能把旧NULL配置当透明升级。学习默认关闭，不自动授予模型/来源许可。
- [pending] 门禁通过才备份/受控停止旧调用方/扩展迁移/切换一致镜像/验收与清理。主会话，无子代理；不恢复整库、不动非目标服务、不真实抓取/付费/邮件验收。

## 当前追加：M3实施前置核对（2026-09-18）
- [complete] 用户要求继续完成M3；核对原设计/源码/TDD验收接口，保留已有文档改动，不使用子代理/SSH/真实调用。
- [complete] 用户回复“确认”：将学习所需独立留出/模型样本暴露审计、会话认领/可靠派发作为M3必要前置纳入，不捆绑整个M2日常路由/调度或M4；新增Admin学习行为/LLM公共方法/Alembic验收已确认。
- [complete local slice] M3.1a全局预留/结算/未知费用/Admin对账/配置审核与迁移完成，729通过/18 MySQL跳过（新增2），head a8d31c5e7902；未提交/部署。见 docs/audits/2026-09-19-m31a-budget-accounting.md。
- [complete local slice] M3.1b子预算与Admin启动/详情/取消→持久认领/queued重派→显式模型提案→训练候选完成；3轮/$0.20会话/$1 Agent日与来源日/20,000 token，head c4e92f7a610b。新增39离线，最终768通过/19 MySQL跳过。见 docs/audits/2026-09-19-m31b-learning-sessions.md。
- [complete local prerequisite] M3.3a受控学习暴露历史：全局连续序号/计数、输入与文档hash、规范化正文指纹、Admin可见及准入检查；新增29离线，797通过/19 MySQL跳过，head d9b72a6e410c。见 docs/audits/2026-09-19-m33a-exposure-history.md。尚未选样或输出独立验证报告。
- [complete local restricted slice] M3.3b系统冻结/选样→真实M1单列表HTML/至少三详情→受限验证报告，42新增离线，839通过/19 MySQL跳过；head e1c73d9b502a。报告失效显示stale，候选始终未发布。见 docs/audits/2026-09-19-m33b-holdout-validation.md。
- [complete local bounded slice] M3.2c失败/取消6小时同源冷却；原期限和轮次内的零供应商准入人工重试、审计与历史校验、认领异常fence、模型后解析前检查点。39新增，878通过/19 MySQL跳过，head f8b64d2c901e；见 docs/audits/2026-09-19-m32c-learning-lifecycle.md。
- [complete local config/protocol] M3.4a可选worker/RO共享证据配置/启动guard与专用节点健康CLI；46新增离线，全套924/19 MySQL skips，无DDL，head f8b64d2c901e。配置不是实际mount/prefork/容量证明，见 docs/audits/2026-09-19-m34a-learning-worker.md。
- [complete local bounded slice] M3.4b企业初始分析迁LLM：原子新公司job/来源输入代次/全局账本关联/持久有界重派/无付费接管，SafeFetcher目录出口。64新增离线；最终988通过/20专用MySQL跳过，head a2f6d9b3107c。见 docs/audits/2026-09-19-m34b-startup-analysis.md；非全部refresh/实际服务完成。
- [complete local bounded slice] M3.2d学习派发键（轮次/retry fence）、持久UTC派发槽位间隔/到期恢复/晚期deadline检查。31新增离线；全套1019通过/20专用MySQL跳过，head b5d81e6a430f；223 AST/48模板。见 docs/audits/2026-09-19-m32d-learning-dispatch.md。不接管未知付费、不延长期限，也不是物理broker发送限速/完整lease或实际服务验收。
- [in_progress overall] 通用RSS/分页/多列表留出与全系统暴露覆盖、完整付费恢复、worker实际共享证据/mount/容量/服务、真实broker与MySQL门禁、全部公司refresh可靠性仍未完成。不宣称M3完成；未提交/部署。计费上界旧配置保持NULL，部署前必须显式审价、暂停旧付费进程并完成隔离门禁。
- 验证环境变化：旧临时venv已不存在，实施时需建立新的隔离环境，历史673/16不代表新代码验证。

## 当前追加：遗留工作复核（基线8bf2563）
- [complete] 核对最新发布、总计划与当前源码，区分已完成、未实现及尚待验证，输出按优先级排序的遗留清单。
- [complete] 形成 docs/audits/2026-09-18-remaining-work.md：M2独立验证/审批/可靠运行/路由调度、M3/M4及现有安全/运维/邮件/数据/性能遗留；最新发布历史673/16不当作本轮测试，未验证当前生产。
- 本轮只做本地审阅和文档记录，不修改业务、不提交/部署、不SSH、不真实爬取/调用模型/发邮件，不使用子代理；历史授权不继承。

## 目标与范围
- 用户要求：全量检查当前项目、提出具体优化点，并依照给定流程图设计动态 Agent 爬虫改造。
- 基线：master，bf9cc61b94556e00218af267db82bf42a3b80eef；初始工作区干净。
- 审查与方案已完成。用户已同意 5 项默认建议并授权开始实施：V1 仅新闻、schema 人工批准、元数据可保存但仅标题不生成深度洞察、隔离公开页面渲染、3 轮/US$0.20 每次/US$1 每日且受总预算约束。
- 已完成的M1发布授权：用户要求直接生产，已按 docs/superpowers/plans/2026-09-07-m1-release.md 完成提交/备份/CI与候选门禁/增量迁移/四应用切换，当时生产应用1052edf/schema e6；该历史发布不再有待执行阶段。
- 随后用户在架构导览后要求“继续”，推进M2本地。用户已选择后台HTTP作为M2主要验收入口，从真实页面操作逐切片TDD，不增加测试专用API；不继承上次提交/SSH/部署授权，不额外真实爬取/付费LLM/邮件，不使用子代理。

## 当前追加：B2b.2a提交与部署（2026-09-11新授权）
- [complete] 330d50b已正常提交/推送/部署，schema f2a67b904d31，CI34580807525全成功；前后真实web/worker各16 MySQL通过，真实broker回收/跨容器证据/回滚guard正负控制通过。09:04:25Z→09:04:32Z web恢复、09:04:54Z全部完成，未触发回滚。9个测试容器/3卷/网络/合成凭据精确清理，原私有卷及非目标服务不变。详见 docs/audits/2026-09-11-capture-ledger-release.md；收尾文档同步不重建。

## 当前追加：M2-B2b.2本地继续
- [complete local] 从clean 9c531e4继续完成B2b.2a长期Admin采样台账：28项新HTTP+2迁移，全文673 passed/16 MySQL skip；新head f2a67b904d31。现存20份preview不是完整调试历史，新增只保留指纹、裁剪后审计、legacy incomplete与计数CAS；未提交/推送/SSH/部署。详见 docs/audits/2026-09-10-m2-capture-ledger.md。
- [pending] B2b.2b/c独立留出验证及人工规则审批：台账只是前置，不是独立验证/批准。随后09-11按新授权已发布330d50b/f2，第16项MySQL及前后新image门禁已通过（见上方），不再待部署。

## 当前追加：Worker并发与任务后回收发布
- [complete] 配置81135d8已合入/部署，运行image仍14dc6f1/c9：LLM并发2、fast2，两worker50次完成尝试/393216KiB任务后回收。643本地/15专用skip、准确CI34483808675（含新真实Admin/Redis/prefork）、前后四轮实际image MySQL各15通过。首次门禁字符串/argv误判自动恢复旧命令，新备份后13:53:30Z→13:53:54Z重试成功。web/其他项目未重启，测试资源/凭据清理完毕，清理后可用4.20GiB。详见 docs/audits/2026-09-10-worker-recycling-release.md；文档同步不重建，长期/夜间/吞吐仍未验收。

## 当前追加：服务器整体容量评估
- [complete] 只读整机容量核算完成，报告 docs/audits/2026-09-10-server-capacity.md：4vCPU/7.57GiB RAM/无swap、当前可用3.78GiB，1056个已有sar样本最低3.38GiB。现负载可承受fast1GiB/beat384MiB，不必立即升级；其他项目无硬限、LLM834MiB、维护叠峰为风险。该只读阶段无生产修改/重启/安装/提交；后续worker调整已按新授权完成，见上方独立发布记录。

## 当前追加：M2-B2b.1提交与部署
- [complete] 用户新授权已完成：应用14dc6f1/schema c9，06:15:19Z→06:15:25Z切换；本地639/15、CI34443459274两job、真正web/worker切换前后四轮各15 MySQL通过。详见 docs/audits/2026-09-10-m2-policy-release.md。仅四应用更新，保留私有卷，测试资源/凭据清理完毕；无额外真实新闻/模型/邮件。
- 预检确认旧fast发生MEMCG子进程OOM（父进程存活/restart0），已TDD修改上限fast1GiB/beat384MiB；这是容量缓解，根因/长期峰值仍需另验收。收尾仅文档提交/准确CI与checkout同步，不重建运行镜像。

## 当前追加：M2-B2b本地继续
- [complete] 用户发布后继续，从clean e98af16完成B2b.1本地：持久策略/质量版本→真实preview约束→撤权/来源ABA使旧回放失效→历史/diff。新增60 HTTP/2迁移，全套638/15、166 AST/45模板/指定flake8及单head c9通过，见 docs/audits/2026-09-09-m2b2b-policy.md。
- [pending] B2b.2b/c独立留出验证、长期验证/审批审计、规则diff与人工批准/拒绝/回滚/CAS；B2b.2a采样台账随后已发布330d50b/f2，新16项MySQL及前后镜像验证另列于09-11记录；policy新并发/压力/恢复仍后续。
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
9. [in_progress] M3 有界学习、预算账本与候选验证。09-19本地1a/1b、3a历史和3b限定HTML留出路径完成；通用独立验证/完整恢复/专用worker尚未完成，19项MySQL未实跑。
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
