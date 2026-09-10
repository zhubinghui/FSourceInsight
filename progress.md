# Progress

## M2-B2b.1发布与远程MySQL（2026-09-10，完成）
- 27文件正常提交/推送14dc6f1，CI34443459274两jobsuccess。备份mp-20260910060307（19,044,026 bytes/600/gzip与SHA256），旧镜像/ref保留；四候选web/worker各15/15，29.948/30.100秒，45模板/基础prefork与实际跨容器策略/证据/回放/撤权门禁通过。
- 06:15:19Z→06:15:25Z四应用切换、b6→c9/model diff0/旧计数与M2 hash/4模型配置不变，policy0；不自动授予许可或接管日常链。公网/匿名policy+revoke/本站TLS、worker/镜像/私有卷检查通过。
- **部署后**实际已部署web/worker镜像再各15/15（29.793/28.861秒），独立MySQL无生产凭据；随后临时容器/网络/三卷/生成凭据清理，helper归档600并移除执行入口，MP_FINALIZED。仅四应用改变，其他项目/MySQL/Redis/Caddy与原卷不变。
- fast实际1GiB/beat384MiB，06:20Z新四应用OOM false/restart0、fast cgroup事件0，短期健康不代表长期容量修复。报告 docs/audits/2026-09-10-m2-policy-release.md。收尾文档另提交/CI，服务器只同步checkout不重建14dc6f1镜像。
- 工具偏差：合成smoke脚本误设600导致cap-drop root读取失败，只改这两个无敏感脚本644；SFTP不展开远端花括号，改明确文件参数。均先记计划，不削弱业务/权限断言。以下保留开始记录。
- 用户新授权提交/部署/部署后远程MySQL；计划 docs/superpowers/plans/2026-09-10-m2-policy-release.md。生产e98 checkout/22应用/b6，旧三张M2表0、原始证据卷空/0700，模型4项指纹不变。
- 预检发现fast昨晚MEMCG杀过1个子进程，父进程仍活/restart0；内核及memory.events确认，不能借旧健康记录掩盖。按新计划fast上限1GiB、beat384MiB，既有Compose seam先观察尺寸格式fixture错误，再容量契约red→green；这是缓解非根因/压力验收。
- 修改后本地639 passed/15 MySQL专用skip/4367 warnings，182.25秒。只读预检不停止生产，待提交/准确CI及新候选远程15项后切换；部署后再跑独立MySQL，不触碰生产fixture。

## M2-B2b.1 本地完成（2026-09-09）
- 持久策略/质量、不可变grant/revoke、当前决定标记与最新历史交叉核验、source_generation/总generation、实际preview/旧回放撤权、历史diff完成；旧日常registry/CLI不受本切片控制，不声称规则批准。
- 实际red还覆盖当前撤权记录/标记缺失或回退、报告引用损坏/系统限额变化仍ready、历史误标effective、停用源grant、IDNA规范化膨胀及8KiB界限；逐条最小修复。权限/CSRF/SQL失败/写边界竞争/回放中变化等已有实现直接通过，不冒称red。
- 60项新HTTP+2迁移，全套638 passed/15 MySQL专用skip/4367 warnings，178.84秒，日志/tmp/fsi-m2b2b-policy-tests-final.log。166 AST/45模板/指定flake8/单head c9通过；静态脚本CliRunner.stdout观察错误改ScriptDirectory后通过，非业务失败。
- 迁移c9只扩展profile两列及policy表，旧数据/JSON保留、无权限回填、拒破坏降级。MySQL新增真实HTTP用例并HEAD=c9，本轮15项未实跑，本地socket仍不存在/无mysqld，不SSH或借旧CI证据。
- 未提交/推送/部署、无真实新闻/模型/邮件，生产仍最后验证22c098c/b6。报告 docs/audits/2026-09-09-m2b2b-policy.md；后续B2b.2独立验证/审批及可靠run/调度未实现。
- 用户发布后继续，从clean e98af16起步，先写 docs/superpowers/plans/2026-09-09-m2b2b-policy.md，沿用真实Admin HTTP/运维seam，不重复审批内部helper。
- 本切片是持久策略/质量、实际preview受控、撤权/源变化阻断回放、不可变历史；独立留出验证/人工发布仍后续。不提交/SSH/部署或真实来源/模型/邮件，单写者不用子代理。

## M2当前成果生产发布（2026-09-09，完成）
- 用户新授权部署，先记录 docs/superpowers/plans/2026-09-09-m2-partial-release.md；只部署A/B1/B2a，取代旧“完整M2后上线”安排，不把审批/路由/可靠调度标成已实现。
- ae1fb87起点clean；TDD增加可选仅web持久卷，新ref22c098c、本地576/14/154.31秒、CI34367023823两job通过。真正web/worker各14 MySQL/26.715与26.538秒，四镜像43模板及基础prefork通过；Docker卷真实HTTP捕获/跨容器flock忙503/重建后离线回放200、不入库不批准。
- 备份m2-20260909145831：18,992,013 bytes/mode600/gzip与SHA256通过；旧四镜像保留。排空worker，e6→b6扩展迁移/model diff0/旧计数与4模型配置不变，15:25:00Z→15:25:06Z切换健康，无回滚触发。
- 公网/有效CSRF匿名拒绝/本站SafeFetch真实TLS/worker/image/私有卷门禁通过；仅四应用改变，MySQL/Redis/Caddy及其他项目未变，测试资源/凭据已精确清理。无额外新闻/付费模型/邮件。beat245/256MiB余量较小、无OOM/重启，长期容量/压力仍未验证。
- 详见 docs/audits/2026-09-09-m2-partial-release.md；以下保留之前各阶段原始记录。

## 当前M2成果合入主干（2026-09-09，完成）
- 34文件明确allowlist提交90c94b6f441ae39e22d15ad1f34f320b3469f224并正常推送master；远端SHA一致、首次提交后工作区clean，无强推/merge冲突。
- 本轮复验574 passed/14 MySQL专用skip，162.03秒；158 AST/43模板/指定flake8/96文档链接与围栏、暂存diff及常见凭据标记检查通过。
- 本提交CI34356717036两job成功：离线574/14/195.67秒；真正独立MySQL14/14/18.443秒，含候选与preview/evidence回放。13:27:05Z全部完成。不能扩展为部署候选/压力/完整可靠运行验收。
- 合入结果及当前状态文档另行收尾提交；生产不动，B2b审批/CAS与后续M2/M3/M4仍未完成。

### 本轮授权与开始记录
- 用户已授权把当前所有成果提交并合入主干；不包含部署。新增 docs/superpowers/plans/2026-09-08-m2-mainline-integration.md。
- master@4477cfd；fetch后与origin/master一致，暂存区空，保留全部M2-A/B1/B2a与文档。按明确allowlist提交，CI仅离线/一次性MySQL，没有部署步骤；不使用子代理、不SSH/真实源/付费/邮件。

## M2-B2a 本地完成（2026-09-08）
- 显式保留私有快照/只读回放/过期清理完成，默认不保留；0700目录/0600随机文件、6文档/2MiB body/3MiB bundle/32文件/64MiB总额/24h有效性、非阻塞flock，失败固定码。JSON引用含独立capture_id绑定，不能把同候选的不同捕获互换；整体hash不取代单页/URL/权限验证。
- 真实red包括缺保存/回放/清理控件、满额仍保存、不安全文件仍available、引用串换/路径穿越、空证据、损坏结构/checksum不充分、symlink loop；修复后通过。源码/期限变化与partial缺页回放不联网，fsync/SQL失败孤儿可清理，权限/CSRF保持。
- 新增49 HTTP；全套574 passed/14 MySQL专用skip/3453 warnings，147.67秒；158 AST/43模板/指定flake8/diff通过。无新DDL/head仍b6；原MySQL HTTP扩展引用/回放但14项未本轮实跑。
- 报告 docs/audits/2026-09-08-m2b2a-private-evidence.md。不存DB原文、不写Article/派LLM/发布；B2b持久policy、独立验证、审批/CAS仍后续。无提交/SSH/真实源/费用/邮件/部署，也未改Compose或创建生产目录。

### 本切片开始记录
- 用户继续；先读计划/代码并记录 docs/superpowers/plans/2026-09-08-m2b2-evidence.md。先实现显式保存私有证据/回放/生命周期，再B2b持久policy与人工审批/CAS；不提前声称完整B2。
- 保留4477cfd上的所有dirty；不提交/SSH/外网/付费/邮件，不使用子代理。真实HTTP seam不重复要求批准。CLI单文件快照没有后台所需的全局容量/TTL，不能直接当完整证据库。

## M2-B1：后台预览本地完成（2026-09-08）
- 新增真实HTTP预览/报告：独立主机许可、news/bulletin标准、实际M1引擎、限5样本/1000字符/64KiB JSON、每候选20报告，无原始HTML/Article/LLM/审批。新增b6表，旧候选/来源数据不迁移回填。
- 真正red：缺表单、伪造控制数据、旧输入仍执行、source ABA、中途/事后变化仍ready、报告未裁剪、私有执行异常外泄、迁移无表；修复后通过。源码输入变化走Admin路径递增generation，抓取前释放session，结束复查/保存/修剪同事务。
- 36 HTTP+2迁移新增离线通过；全套最终525 passed/14 MySQL专用skip/2715 warnings，107.31秒（首轮107.88秒）。新增MySQL HTTP预览用例待实跑，不能借M1结果背书。
- 156 AST/43模板、指定flake8/diff/单head通过。测试fixture旧ORM因正确释放session而detached，改真实登录HTTP；fixture import触发F811改模块注册，未关检查/未改产品行为。
- 报告 docs/audits/2026-09-08-m2b1-admin-preview.md。未提交/推送/SSH/真实来源/付费/邮件/部署；B2原始证据/完整policy/审批及C/D可靠运行仍后续。

### 本切片开始记录
- 用户“好，继续”确认已说明的后台预览流程；先记录 docs/superpowers/plans/2026-09-08-m2b1-admin-preview.md，再按同一HTTP验收面TDD。
- B1把管理员明确的本次host/质量选择固化到有限报告，暂不先做全局policy发布API；最多5条样本/64KiB报告、20份每版本，不存原始HTML，不准据此直接批准。B2完整证据/发布与C/D仍后续。
- 继续保留未提交M2-A和文档，零真实来源/模型/SSH/部署，复用跨exec合成HTTP fixture，主会话单写者。

## M2-A：后台HTTP候选保存（本地完成，2026-09-08）
- 后续真实red覆盖服务端元数据/重复表单值被忽略、缺私有响应头、SQL trigger失败泄露异常参数、commit后ORM读取造成误报失败；均最小修复后通过。SQL异常固定503/日志码并rollback；返回ID在commit前取出。
- 26项HTTP+2项迁移，全套487 passed/13 MySQL专用skip/2214 warnings，143.57秒。新MySQL HTTP/UTF8用例仅追加未运行；HEAD更新a731，历史M1质量迁移用例固定e6。
- SQLite迁移用例误读CLI SystemExit文本，记录后改看output；非业务red。152 AST/42模板、指定flake8、diff检查和单head通过。
- 报告 docs/audits/2026-09-08-m2a-candidate-http.md。仅候选保存/列表/详情，无policy编辑/预览/审批/active路由/lease/outbox；保留全部未提交文档与代码，无部署/SSH/外网/付费/邮件。

### 本切片早期过程
- 用户选择后台HTTP为主要验收入口。不是新建测试API；以真实来源管理和候选页操作观察，迁移保留既有运维验收。
- 首条保存/独立请求重读测试真实404 red；新增嵌套Admin blueprint、最小profile/version模型、候选列表/详情后green。第二条来源列表缺入口链接red，加入Crawl config链接后green。
- 匿名/普通用户的GET/POST和缺CSRF负例直接通过既有父Admin/CSRF保护，不冒称新red。当前5项通过；无Article、无外部网络/模型或任务派发。迁移及输入/事务等负例仍在进行，未提交部署。

## M2本地准备（2026-09-07）
- 用户要求继续，核对HEAD4477cfd及已有架构导览文档改动，全部保留；仍单写者，不使用子代理。
- 新增 docs/superpowers/plans/2026-09-07-m2-versioned-runtime.md 和领域术语CONTEXT.md；主计划记录2.1+2.4最小HTTP入口先组成纵向切片，不提前部署缺少lease/outbox/调度的中间状态。
- 发现source.updated_at混合配置与运行更新、ABA发布风险、历史M1简化迁移fixture将不适配M2 head，已在行动前记录处理方式。
- 当前只完成准备。M2新增Admin HTTP/Celery验收面待一次确认；未写测试/业务代码，未跑pytest/迁移/采集/SSH，没有提交或部署。

## 动态爬虫架构与代码导览（2026-09-07）
- 用户要求把架构与代码逻辑结合展示。静态核对4477cfd：旧自动链与M1手工入口并存，JSON-LD为详情读取方式，两个helper按需启动，只有新引擎具备全套门禁/解析监督；当前无Agent/active版本/lease/outbox/browser实现。
- 输出 docs/architecture/2026-09-07-dynamic-crawler-code-map.md，含当前/目标图、入口/模块映射、preview/run事务、状态/字段证据、LLM质量保护及阅读顺序；47个链接/行号锚点和围栏复核通过。
- 本轮仅文档与规划记录，无业务修改、测试重跑、子代理、网络采集、SSH、提交或部署。

## M1生产发布完成（2026-09-07）
- 应用1052edf/schema e6已上线；本地459/12，修正fixture后CI34091467749两job成功，最终真正web/worker各12/12（20.674/20.175s）。四镜像40模板/CSRF/Admin/HTTP/回放/billiard smoke、本站SafeFetcher真实TLS成功。
- 06:47:58Z→06:48:03Z切换，仅四应用变化，无源码挂载；公网、有效CSRF匿名拒绝、unknown标记、model diff0、配置指纹不变及LIVE_WORKERS_READY通过。HTTP探针误POST manage得405已按实际GET纠正，无业务改动。
- 备份/旧镜像m1-20260907062543保留；全部本轮临时MySQL/runner/网络/卷/凭据精确清理，helper归档。未额外抓新闻/调用付费模型/发邮件，不发布recipe；下一步M2，M3/M4及可选M5后续。详见 docs/audits/2026-09-07-m1-release.md。

## M1直接发布新授权（历史过程，2026-09-07）
- 297be85已提交推送并构建四候选；备份m1-20260907062543成功，生产未停机。首次CI的MySQL新用例失败，候选复现发现调用者RR旧读快照（fresh_rows1/caller_rows0），不是引擎入库失败；修测试观察事务后真正web/worker各12/12通过，业务代码不变，继续新CI门禁。
- 用户要求直接切生产并询问剩余任务；已说明M2版本/路由/可靠交付、M3有界学习硬预算、M4浏览器与源迁移、M5可选目录/自动发布。
- 先新增m1-release计划，取代独立部署测试阶段：允许本轮提交推送/SSH/备份/候选门禁/增量迁移/四应用切换；不省略回滚，不触发额外真实源/LLM/邮件或发布recipe。正进行只读预检。

## M1 整体本地完成（2026-09-07）
- 用户“同意”确认preview/run；在保留M1.1/M1.2 dirty工作区的前提下连续单写者TDD，未使用子代理、SSH、真实源/LLM/邮件，也未提交推送或部署。
- M1.3/M1.4落地HTML/RSS/Atom/JSON-LD、共享分页候选预算、独立解析监督、显式回放、受限基础Adapter、手工CLI、质量/身份/原子应用、Article标记与LLM/HTTP闭环。
- 真实red包含：缺模块/字段/CLI、摘要冒充full、错题/噪声/隐藏/付费正文、重放错绑、200候选跨页绕过、后页空却ready、错误数组超限且业务先提交、完成日志失败未回滚、新旧爬虫再次插入、保留字段证据不实、解析基础设施误归因等；逐项修复见细化计划。
- 首轮418/10，后445/12、458/12；最后发现开始日志晚于HTTP，外部边界读不到running日志，先red再前置独立日志。最终全套459 passed/12 MySQL专用skip，71.95秒/1919 warnings。新增85=引擎/CLI75+LLM6+迁移1+HTTP3；12skip含新MySQL2项，均未本轮实跑。
- 147 Python AST、40模板编译、shell语法及flake8指定错误集通过；12份文档链接/围栏、JSON样例validate_recipe及e6的3个MySQL离线ADD COLUMN通过，无Article UPDATE/DROP。临时venv无ruff，已记录工具误选后使用项目既有flake8。fixture/命令小错误与已有防护的直接通过均分开记录，不冒充业务red。
- 交付 docs/audits/2026-09-07-m1-local-completion.md；样例 docs/examples/news-recipe.json。整个M1仅本地完成，不代表全部来源/Agent上线；15个自定义source与startup_discovery、M2版本/审批/lease/outbox、M3/M4仍后续。
- HEAD仍master@f3644ca，全部M1未暂存/提交。后续隔离部署测试准备在 docs/superpowers/plans/2026-09-07-m1-deployment-validation.md；本轮未启动，不自动切生产。

## 本轮
- 已读取用户流程图和项目级约束，确认初始 Git 基线与目录结构。
- 已向用户说明先审查与设计、再确认关键决策的执行方式。
- 已完成子代理能力发现；计划只读审查并行、主代理汇总和本地验证。
- 已运行 planning-with-files session-catchup，没有返回待恢复上下文。
- 主会话已初步阅读爬虫 base/rss/html/tasks/registry/source model、测试 fixture 与依赖配置，尚未执行测试。
- 并行审查工作流 9a58ff2f-f6ae-4ffc-ac1b-593d81f7b190 的 3 个子启动全部失败：原生后台依赖 @earendil-works/pi-server、pi-server/unix、pi-client/unix 不可用。工作流包装层 completed 不能视为审查成功；子状态均 failed。
- 已先更新 task_plan.md 记录偏差并暂停，不切换执行模式。待用户批准主会话直接继续或修复子代理依赖后重试。
- 用户已批准主会话直接继续，已先更新计划，后续不再使用子代理。
- 已阅读 app factory、LLM 全链路、Celery、登录/订阅/企业/API、主要模型及官网抓取；发现匿名改密码高优先级风险并已提示用户。
- 已审查全部后端模块、25 个站点爬虫文件（29 个注册类）、35 个新闻 seed 配置、21 个发现源配置、部署及迁移路径；模板全体扫描与编译 40 个。
- 本地隔离依赖安装成功；pytest --collect-only exit 5（0 tests）；103 个 Python AST 与 shell bash -n 通过。
- 18/18 缺陷探针成功复现；额外测得 25 家企业地图 28 次 SQL，其中 26 次重复分组查询；带 +02:00 时间丢 UTC 归一化；同一周不同 sentiment 分裂为不同日期桶。
- 13 个迁移可生成 MySQL 离线 SQL，但 task_type 仍为旧 Enum，缺 digest/insight。未连接真实 MySQL。
- 已完成 docs/audits/2026-09-06-project-audit.md、2026-09-06-validation.md、2026-09-06/probes.py 和 probe-results.json。
- 已完成 docs/superpowers/specs/2026-09-06-dynamic-crawler-agent-design.md 和 plans/2026-09-06-dynamic-crawler-agent.md。
- 最终复核：保存后的探针重新执行 exit 0，18 项缺陷复现结果与已存 JSON 一致；文档本地链接/引用行号范围/代码块/空白检查通过。
- Git 仍 master@bf9cc61，无 tracked/staged diff；仅新增本轮审查/设计/计划资料。无业务修改、提交、推送、生产访问。
- 审查轮完成。随后用户已确认默认建议并授权开始实施。

## 实施首批（2026-09-06）
- 先更新设计/计划确认 5 项默认决策；始终主会话单写者，无子代理、生产访问、真实爬取/SMTP/LLM、提交或推送。
- 0.1：先复现匿名改管理员密码，再修登录/本人归属、旧密码校验、输入验证、next 安全校验、凭证版本会话失效；29 项 HTTP 回归通过。
- 0.2：文章详情 XSS 用例先失败，再转义后引入固定 Markdown 标签；回归通过。
- 0.3：base+prod 端口继承用例先失败、Caddy 组合原本通过；两层统一 !override，新增 deny-by-default .dockerignore、明确 Dockerfile COPY、新建 GitHub 离线测试流程；3 项本地测试通过，CI 远端未运行。
- 0.4：迁移测试先失败缺少 ALTER；新增 expand-only c821b4f7d901，MySQL 全链路离线 SQL 通过。无可用 Docker daemon/mysqld，真实迁移仍阻塞。
- 0.6：批内去重、savepoint 冲突隔离、异常 rollback、独立日志事务、空 RSS/未知空结果区分、HTTP 429/5xx 重试与 403 不重试、URL/UTC 修复；13 项通过。
- 0.7：两类邮件模板路径与高亮-only 正文/preview 修复；SMTP 仅 mock，失败记录回归通过。
- 测试环境：临时 venv，独立 SQLite 文件而非共享内存连接；socket/DNS 阻断。测试 fixture 修正跨请求 Flask-Login/CSRF 的 g 缓存泄漏；测试数据补齐必填 source.category；HTML 断言改为 DOM 文本而非空白敏感字符串。
- SQLite legacy SAVEPOINT 的批次部分提交在新增晚期失败测试中复现，已先记录计划偏差，再显式 BEGIN 修复；未用 SQLite 冒充 MySQL 并发验证。
- 一次多处 edit 因重复 oldText 拒绝（无部分改动），改用 mysql/redis 上下文后成功。
- 最近整套命令：`env -i PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin HOME=... PYTHONDONTWRITEBYTECODE=1 /tmp/fsource-audit-1XQuAg/venv/bin/python -m pytest tests/ -q --disable-warnings -p no:cacheprovider` → 49 passed（251 条主要为既有 datetime.utcnow/legacy Query 警告），无 skip。
- 最终复核：110 个 Python AST、40 个 Jinja 模板、shell 语法、文档链接/围栏、git diff --check、flake8 E9/F63/F7/F82 均通过。当前 Docker context 被动检查也指向不可用本地 Unix socket；未连接 daemon。
- 首批实现文档：docs/audits/2026-09-06-m0-implementation.md。18 个原有 tracked 文件修改及新增测试/迁移/构建/CI/文档；HEAD 未变、无暂存修改。
- 下一项是 0.5 LLM 事务/幂等/严格结构化输出/缓存与显式路由。M0 总状态保持进行中，M1–M4 尚未实施；该首批交付时尚未部署。

## M0.5 本地开发（首批发布后，进行中）
- HEAD d91863f，未提交/部署；本轮不访问 OVH，沿用离线环境和 mock provider/cache。
- 用量回归先 2 failed（成功和失败调用均提前提交文章），独立配置/预算读取和用量 Session 后 2 passed。
- pipeline 晚期失败回归真实复现 SQLite `database is locked`：单独换账本仍被旧 company flush 阻塞。新增 pipeline.py，只读快照→收集→独立事务应用；Celery/CLI 共用，关系去重、已有结果在 force 失败时保留。12 个模型调用阶段逐项中断重试及最终分类写入失败回滚通过。
- JSON 契约先 16 failed/3 passed；严格对象/字段/类型/范围/日期/空文本校验后通过，格式错误照样记录 token/费用，绝不伪造空结果缓存。公司分析独立 task_type。
- fallback 两项先失败（11次循环、预算未复查），加入 visited/最多3次/每次预算检查后通过；账本故障不重试付费。当前 LLM 子集 39 passed；尚待缓存完整性、显式路由和全套/迁移验证。
- 工具/fixture 小错误：两次非唯一 oldText edit 被拒绝且无部分改动，改唯一上下文；Category fixture 的 name_fr 应为 name，修正后才得到真实锁失败。CLI 暂时引用被删除私有 helper 的 ImportError 已用共享 pipeline 修复并回归。MySQL离线DDL对保留字role加反引号，断言修正，不修改合法DDL。
- 缓存先17 failed/2 passed，再改完整有效messages/版本/config/参数和实际fallback归属；坏缓存/响应缓存Redis故障允许miss，temperature=0保留。路由先6 failed/1 passed，再共享primary→fallback/priority/cost/id，Admin表单、矩阵与新seed同步，旧配置不覆盖。
- 新增迁移d472只加role/priority，SQLite旧数据保持+MySQL离线DDL通过。原MySQL旧Enum fixture改用旧列SQL避免新ORM访问不存在列；新增3项LLM实机测试（独立用量/FK、晚期回滚、双消费者），当前10项均未实跑。
- SDK隐藏重试/非stop结束4项先失败再修；元数据only含空白/空HTML无深度洞察，force无正文清理旧digest。实际provider归属、legacy关系恢复/人工情感保留、源输入中途变化拒绝覆盖均回归。
- 本地最终131 passed / 10 skipped；LLM77、迁移2、既有52。123 AST、40模板、shell、flake8 E9/F63/F7/F82、git diff --check通过。文档：docs/audits/2026-09-06-m05-implementation.md。M0仍待隔离MySQL新代码验证，不部署，不宣称CI已运行。

## M0.5 隔离验收续轮（2026-09-06）
- 用户在下一步隔离MySQL验收后确认“OK，继续”。新计划 docs/superpowers/plans/2026-09-06-m05-mysql-validation.md；仅隔离验收，不部署/提交、不迁移生产库。
- SSH france-vps只读盘点：d91863f干净，MySQL/web现有镜像可用；可用RAM3981MiB/磁盘22GiB。源快照156文件，SHA256 6dacabbfd75b7174dfd21505765b62e02db9c663f355fa528438d1a1c50981ba。
- 资源fsi-m05-20260906131354：独立internal网络/卷/MySQL8.0.46，无宿主端口；MySQL768MiB/1CPU，runner512MiB/1CPU，只读/cap-drop/无生产凭据。
- 初次runner收集前exit1：Start directory is not importable。先记录计划偏差，核实目录700归ubuntu、cap-drop root无DAC覆盖，改runner为1000:1000（不放宽权限/隔离）后10/10通过15.672秒，再完整复跑10/10通过15.639秒。业务代码/断言未修改。
- 新head d472迁移model diff0、旧任务费用/FK/配置保持、爬虫基础/并发、LLM独立账本父行锁/最终失败回滚/重复消费者均通过。依赖Python3.12.14/Flask3.1.3/SQLAlchemy2.0.52/Alembic1.19.2/PyMySQL1.2.0/LiteLLM1.100.0。
- 已核对所有原有容器ID/StartedAt/RestartCount逐行相同，health正常；13:18UTC精确清理测试容器/卷/internal网络/凭据，服务器checkout仍干净d91863f。未读取生产env/备份，未付费/爬取/邮件。
- 无敏感信息源快照/日志归档至 /home/ubuntu/fsourceinsight-validation/m05-20260906131354；完整报告 docs/audits/2026-09-06-m05-mysql-validation.md。M0批准基础切片已完成代码与验收，0.5尚未部署，下一阶段M1.1；未来新构建候选仍需复验。
- 清理后本地全套131 passed/10 skipped（20.59秒），156个源文件哈希与实跑快照逐一相同、下载日志哈希/文档链接围栏/diff check通过；无暂存，HEAD仍d91863f。本轮只有计划/验收文档改动，未改变被验收的业务代码。

## M1.1 开发准备（2026-09-06）
- 用户在确认M0.5已上线后要求继续开发。核对本地master@f3644ca且工作区干净，临时Python3.12测试环境仍可用；未访问服务器。
- 重读CLAUDE/TDD、主计划及完整架构、RawArticle/Article模型和离线fixture。新增细化计划 docs/superpowers/plans/2026-09-06-m11-contracts.md。
- 本阶段有新的配置输入与标准结果输出接口，按既定TDD纪律先请用户确认；尚未写测试/业务实现，不把静态准备称作M1.1完成。
- 旧RawArticle没有语言/内容级别/证据，Article TEXT按字节限制；后续不能从旧数据自动推定全文/法语或把未知日期填现在。

## M1.1 TDD实施（2026-09-06）
- 用户回复“可以”，确认validate_recipe与标准结果两个公共接口；无子代理、无SSH/真实网络/LLM/邮件、未提交推送部署。
- schema首个模块缺口1失败后最小快照/指纹通过；扩权字段13失败→14通过，严格值25失败→39，CSS10失败→50，JSON/聚合上限7失败→67，RSS/JSON-LD各1失败→69。没有私有helper/mock测试。
- 标准新闻先类型缺口；不变量22失败→23通过，证据6失败→30，Fetch类型缺口→31，传输反例16失败→47，Outcome类型缺口→48，计数/可变ID/状态21失败→69。
- 补空详情规则、403误标timeout、success漏记valid三项失败再修；大字典中间JSON内存回归峰值2,997,058 bytes先失败，加入总序列化前累计容量后通过；5000位JSON整数原始ValueError先失败，再转结构化InvalidRecipe。未提高解释器限制。
- 一次测试edit非唯一oldText被拒，未部分修改；修正唯一上下文重试，不计业务red。
- 最终两个新接口144 passed；全套275 passed/10 MySQL专用skipped，19.78秒，1532 warnings。126个Python AST和新文件flake8 E9/F/diff检查通过；没有新CI/实机/镜像验收声明。
- 新增app/crawlers/schema.py、contracts.py和两份test_crawlers测试；接口/限制/状态语义详见docs/audits/2026-09-06-m11-contracts.md。旧爬虫/LLM/模型/迁移/依赖未改。
- M1.1完成本地交付，尚未接入旧爬虫、未提交部署；M1.2 Safe Fetch接续，完整Agent/硬预算仍未实现。

## M1收尾准备（2026-09-06）
- 用户要求整个M1完成之后再部署测试；维持单写者/离线TDD，不提交推送、不SSH/真实网络或生产切换。
- 核对HEAD仍master@f3644ca，M1.1/M1.2所有dirty文件保留，无reset/stash或暂存。重读schema/contracts、BaseCrawler/Article、registry/CLI与设计。
- 新细化计划 docs/superpowers/plans/2026-09-06-m13-m14-engine-quality.md：剩余M1统一preview/run两个公共验收入口待确认；本次尚无M1.3/M1.4测试或业务修改，不借上轮374/10冒充新结果。
- 关键前置差异已记录：preview不能伪造CrawlOutcome成功ID；旧run已写库，Adapter应只接fetch；Article缺内容级别/语言，直接桥接会丢语义并让excerpt触发深度分析。若需最小存储标记前移M1，先更新计划再实施，版本/审批/lease/outbox仍属M2。

## M1.2 本地实施（2026-09-06）
- 用户回复“确认”，按批准的SafeFetcher及RSS/HTML/官网公共接口分片TDD；不使用子代理，没有SSH/真实网络/付费LLM/邮件、提交、推送或部署。
- 专属HTTP helper由父selector与子POSIX SIGALRM共同限时；逐DNS检查、数值IP绑定、原Host/SNI/证书检查、手动逐跳、禁隐式Response.next读取。冻结policy、共享请求/实体/协议/解压预算、robots及Retry-After/间隔实现。
- 核心逐步1→26→35→45→52→59→65通过；源入口迁移保留UTC/ID/空RSS/事务语义，真实先复现私网RSS误入库和私网官网ok。Retry-After丢失/无缓存304误no_change三个失败修复。
- 扩展失败→修复：helper自身DNS截止、耗尽配额再请求、32×4KiB trailer空实体、畸形MIME、robots dot-segment偏差及错误文件放行、旧adapter缺能力、raw socket timeout/peer误分类、policy替换、转义后超长URL、慢DNS使50ms间隔缩为约5ms。最终巨型policy整数2项先OverflowError，再在isfinite前检查范围。
- 单独记录fixture/工具偏差：1000条trailer先触发已有Python数量防护；改32条大trailer才复现协议字节绕过。3项MIME正例漏body是fixture错误。若edit上下文不唯一/不存在则未部分修改，read后修正。不将这些算业务red。
- 初次全套372 passed/10 MySQL专用skip，50.56秒/1558 warnings；随后新增两项policy边界。最终复验374 passed/10专用MySQL skip，50.87秒/1558 warnings；M1.2新增99项。135 Python AST、新fetch文件E9/F、旧入口关键静态错误/shell语法、9份修改文档链接围栏与diff均通过。HEAD仍master@f3644ca，无暂存，M1.1/M1.2改动完整保留；本轮本地交付完成。
- 全局网络fixture补充拒绝真实helper exec，只有合成DNS/socket/TLS bootstrap可运行；16MiB gzip的helper Python分配峰值<2MiB，不冒充总RSS。无真实TLS握手或生产Linux/Celery进程验收。
- 新交付报告 docs/audits/2026-09-06-m12-safe-fetch.md 列出接口/额度/隐私/依赖和15个仍直连的source模块（及调用者）、startup_discovery；不是全来源完成。M1.3/1.4执行/质量、M2–M4仍待做。

## M1.2 开发准备（2026-09-06）
- 用户要求继续开发；工作区仍master@f3644ca，全部M1.1代码/测试/文档未提交且保留。没有SSH或真实网站调用。
- 核对M1.1 FetchObservation/CrawlError、RSS/HTML/website_fetcher及旧测试，新增 docs/superpowers/plans/2026-09-06-m12-safe-fetch.md。新公共SafeFetcher.fetch及渐进接入的验收范围待确认；尚未写M1.2测试/实现。
- 已明确设计风险：DNS预查不等于实际连接安全，必须绑定地址并保留TLS原域名验证；connect/read timeout不能冒充含DNS/慢响应的总deadline。非法原始URL在新fetch入口结构化拒绝，不放宽M1.1正常观测契约。

## M0.5 提交部署（2026-09-06）
- 用户要求优先提交部署。新增受控计划m05-deploy；fetch确认无上游变化，服务器d91863f干净，配置4个/指纹e33b89e8…，生产c821无role/priority。
- 本地131 passed/10远程skip、静态/diff通过；30文件allowlist提交6451b36并推送。CI34036731442两job成功。
- 备份 /home/ubuntu/fsourceinsight-backups/m05-20260906134051：18,613,221 bytes/mode600/gzip通过，SHA256 b717eaf749f4e1485c496974db34b1608a2bb647b0c589309e3228c09597f7fa。旧四镜像tag/ref/rollback overlay保留，未读数据/恢复备份。
- 新镜像首轮UID1000读不到root拥有的600源码，exit5/0tests；先记录计划，核对umask077/COPY权限原因后按生产UID0复验，保留cap-drop/只读/网络隔离，测试副本644可读且不覆盖app源码。web/worker各10项MySQL通过15.977/15.880秒；四镜像40模板/匿名CSRF/合成Admin路由/无env-Git-dump均通过。
- 临时MySQL/卷/internal网络/runner/凭据先精确清理，所有原容器未变。两worker空闲，停beat复查active/reserved/scheduled0，以-t -1 warm-stop正常退出。
- 文件脚本+显式stdin升级d472，lock_wait_timeout10秒，model diff0/原配置指纹不变。13:53:46Z→13:53:51Z四应用切换成功，Web5秒恢复、LIVE_WORKERS_READY，无应用回滚。
- 后续公网smoke把/admin直接预期302但实际308补斜线；先记偏差后分别校验308位置及/admin/的302登录拒绝，未改业务权限。首页/health/login/www均200，匿名有效CSRF/settings/manage/Admin均正确拒绝。
- MySQL/Redis/其他原容器ID/StartedAt/RestartCount不变，Caddy active；没有真实爬取/LLM/邮件手工调用。辅助脚本和日志归档至备份目录，临时文件清理。发布记录 docs/audits/2026-09-06-m05-release.md；随后仅提交/同步文档，不重建镜像。

## OVH 验证/发布授权后
- 用户允许登录 OVH 验证 SQL，验证后提交部署；后续明确 TDD，规则已加入 CLAUDE.md。新维护计划 2026-09-06-ovh-m0-validation-deploy.md，不重跑旧安装/dump流程。
- IP SSH 首次 publickey 拒绝；被动配置发现 france-vps 指向同一服务器和专用身份，按别名成功登录，无私钥/密钥值读取。
- 生产 master@bf9cc61，干净；MySQL8.0.46/rev fd3132082a6b，task_type 已 VARCHAR(50)，只读 model diff=0。先记录计划差异再调整测试。
- 独立 internal network、专用卷/容器（fsi-m0-20260906100910），测试目录 /home/ubuntu/fsi-m0-verify.EYVS00；限资源，无业务数据/网络/凭据接入。
- 新增 MySQL unittest：已正确VARCHAR不ALTER先red后green，修改c821迁移在线类型检查；7项真实MySQL迁移/数据保持/回填/事务/并发测试全通过。本地49 passed+7远程专用skipped；CI增加独立MySQL job。
- 初次类型字符串断言因数据库返回COLLATE信息失败，改断言类型/长度/nullable，model diff 原本通过；不改变迁移语义掩盖差异。
- 源tar跨系统xattr提示不影响结果，后续使用无扩展元数据归档。
- 随后复核远端有README署名提交9383019，无业务变化；ff-only保留，提交推送ea96dde。CI run34027261828两job通过。
- 建立服务器备份/回滚目录 /home/ubuntu/fsourceinsight-backups/m0-20260906100910，gzip约21.6MB/mode600/gzip校验通过；旧四应用镜像保留。未读数据内容。
- 新候选依赖SQLAlchemy2.0.52/Alembic1.19.2，真实image再次跑7项MySQL通过，40模板/匿名权限/打包检查通过。
- 首次发布docker compose run默认interactive吞SSH脚本剩余stdin；未误报成功，及时核对迁移已完成/旧web健康/后台exit0，改用保存到服务器的脚本文件。
- 第一次切换Web5秒恢复，但任务注册字符串带rate_limit后缀导致gate误判；保护脚本自动回滚四个旧image。只读RPC确认worker健康。
- TDD补scripts/check_worker_readiness.py及3项CLI真实格式正/负例，先red后green，线上旧worker复验LIVE_WORKERS_READY；提交858a14b，CI run34028232722两job通过。
- 最终候选7项MySQL再次通过；2026-09-06 10:46:03Z→10:46:09Z第二次切换成功，web6秒恢复，LIVE_WORKERS_READY。公网首页/health/login/www health均200，匿名有效CSRF设置POST及manage/admin正确302拒绝。
- 生产revision c821/model diff0，真实镜像无env/Git/dump；MySQL/Redis及所有同机其他应用ID未变。无手工触发真实爬取/付费LLM/邮件，原后台服务正常恢复。
- label核对后精确删除fsi-m0-20260906100910临时容器/卷/internal网络及EYVS00测试密码目录；日志转存备份目录，旧镜像/数据库备份保留。
- 最终代码release858a14b（首批功能ea96dde），本地52通过/7远程专用skip，远端最终镜像7项MySQL均实跑通过。后续仅提交/同步发布文档，不重建镜像。M0.5与Agent继续TDD，未宣称全项目改造完成。
