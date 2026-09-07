# M1 收尾：确定性执行、旧适配与质量门禁

## 授权与基线

- 用户要求：继续开发，整个M1完成之后再进行部署测试。不逐个小切片发布。
- 本地master@f3644ca；M1.1/M1.2全部未提交修改保留，不reset/stash覆盖；无暂存。上一轮全套374 passed/10 MySQL专用skip是基线，不是本轮新验收。
- 主会话单写者、TDD、仅离线合成数据；本阶段不SSH/真实来源/付费LLM/邮件，不提交、推送或部署。整个M1本地完成后另列部署测试与回滚步骤，不把部署测试自动等同生产切换授权。
- 依据：[主计划](2026-09-06-dynamic-crawler-agent.md)、[设计](../specs/2026-09-06-dynamic-crawler-agent-design.md)、[M1.1](../../audits/2026-09-06-m11-contracts.md)、[M1.2](../../audits/2026-09-06-m12-safe-fetch.md)。

## 剩余M1的统一公共验收入口（已确认）

拟定以下两个应用入口覆盖M1.3/M1.4，不再为CSS、日期、质量计算等内部helper逐个建立测试接口：

- `CrawlEngine(...).preview()`：根据明确的source/recipe、系统fetch policy及quality profile，执行抓取或显式快照回放，返回规范化文章、质量报告、观测及结构化错误；不写文章、不派发LLM、不发布配置。
- `CrawlEngine(...).run()`：沿同一执行/质量流程，仅应用通过门禁的数据，返回既有`CrawlOutcome`；保留原有CLI/Celery和Crawler.run的兼容接口。

构造输入与preview结果类型随首条垂直切片明确；recipe、policy/profile、回放快照分别传入，网页/recipe不得覆盖权限或门槛。快照模式缺页只能报告证据不足，不偷偷联网补齐。有效recipe不等于发布批准；run只由受信任应用/明确的人工单次执行调用，候选检查只可preview。

既有已确认接口继续使用：`validate_recipe`、标准结果契约、SafeFetcher.fetch、Crawler.run、LLM公共任务、运维CLI/Alembic。用户回复“同意”，已确认两个入口；按下述切片连续完成剩余M1，不为内部模块拆分反复询问。

首条切片明确构造：`CrawlEngine(source_id, recipe=..., fetch_policy=...).preview()`，source_id必须与重新验证的recipe一致。后续同一入口增加系统profile与显式快照输入；preview不需要数据库session，不使用私有helper作测试入口。

## 1.3 执行器

1. 首条HTML列表：经Safe Fetch获取，执行已有声明式CSS读取，输出标题/URL/证据，证明preview不写库；一条red→最小green后再增加行为。
2. 分页、多列表和候选去重：同一run复用SafeFetcher预算，固定访问顺序和visited集合；链接按真实最终URL解析，不能由base标签/远程canonical扩权。最大页数、候选数、DOM节点/深度及输出容量有界。
3. 详情模板：明确host/path匹配、字段优先级、列表/详情一致性；模板歧义不任意拼接不同文章。脚本/导航/推荐/广告清洗；移除规则不能删除真实性判断所需原始证据。
4. RSS/Atom：GUID与legacy外部身份兼容；摘要不自报全文。原始日期解析失败保留unknown，合法时区转UTC，不用抓取时间代替发布日期。
5. JSON-LD：仅约定类型和固定路径，覆盖数组/有限graph；限定同一文章实体，拒绝畸形/超限/有歧义的数据，不执行脚本或扩展JSONPath。
6. 显式快照回放：同recipe/同快照/同profile的文章和质量结果一致；观测时间使用快照中的时间，不靠当前时钟伪造新证据。快照ID核对内容，但不把合成/调用方提供快照当成真实来源事实保证。
7. 旧Adapter：已收紧为把确切基础RSS/HTML配置转recipe，既不调用旧run，也不执行自定义fetch/parser。保留外部ID/UTC兼容；被保留的历史字段证据明确legacy/unknown，不自动宣称full或伪造快照。未收口的自定义出口不得借Adapter进入新安全路径，也不得在安全拒绝后回退直连。

身份/未变详情优化要区分：同轮URL去重与持久化内容版本不同。没有可靠旧快照/内容指纹时不能仅因external_id存在就跳过全部验证。旧版本/完整性状态只接受系统提供的已验证证据，M2持久化实现之前明确能力边界。

## 1.4 质量门禁与应用

- 列表与正文分别判定：必需字段/有效链接率、证据可定位、正文段落/长度/链接噪声、标题一致性；长导航或重复推荐不因字符多就合格。
- 系统profile区分完整新闻、短讯/活动；默认值是启动假设，不用固定条数要求覆盖所有来源，不让recipe修改阈值。
- HTTP/robots/登录/付费墙/验证码归为传输或受限状态；不因这些错误、零新增或全重复建议修selector。M1不派发repair；`repair_dispatched`保持false，M3才接学习。
- 合法空RSS、有可靠验证器的未改内容、全重复和首次未知空列表区分；计数满足M1.1不变量，不能漏掉valid条目的去向。
- 一页好一页坏保留可验证的合格部分；受限详情不得绕过限制取得隐藏正文。只允许真实已获证据支持的metadata/excerpt降级，不能靠填字段冒充全文。
- 应用前去重、身份兼容、晚期失败回滚、元数据升级、保护既有更好正文；不把未知语言写成“已确认法语”，不清掉人工/已有成功结果。并发租约、outbox及跨重启一致性仍是M2，不提前声称已具备。

### 实施前必须解决的现状差异

- Article当前没有content_level/source_language/证据字段，BaseCrawler.save会丢掉新契约信息；直接把excerpt塞入content_fr还可能触发既有LLM深度洞察。不能通过这种有损桥接宣称M1门禁完成。
- M2原计划承接存储扩展。如果M1的安全应用需要最小Article标记提前加入，先在本计划和主计划记录范围/理由，再按既有Alembic与LLM公共接口TDD实施；历史未知值不得回填为full/fr。版本审批/快照持久化/lease/outbox表仍留M2。
- CrawlOutcome是应用结果，success需要真实article_ids；preview不能伪造ID或借用CrawlOutcome成功状态。Preview需独立的只读结果形状。
- RawArticle没有完整来源证据，旧BaseCrawler.run在质量门禁前写库。Adapter必须位于fetch与应用之间，不能只包住旧run的返回值。
- M1.2只约束HTTP生命周期，不能将其deadline称作HTML/CSS/JSON解析总时限。解析的节点/深度/容量/执行上界需单独定义并验证；若需要隔离解析进程，先记录方案后实现。

## 验证方式与完成门槛

- 测试只穿过上述确认后的应用入口及既有公共接口；内部quality/extractor/identity模块不mock、不单测私有helper。
- 外部DNS/socket/TLS用已有fetch_network合成边界，SQLite使用独立测试库。显式回放不打开网络；缺fixture仍由全局guard拒绝真实helper exec。
- 每小步失败→最小修复→局部通过；每阶段全套回归。偏差、fixture错误、收集失败与真实业务red分别记录。
- 覆盖HTML/RSS/JSON-LD黄金样本、多模板/分页、双语/未知日期、metadata/excerpt/full、噪声/漂移、权限/超限、重复/升级/晚期失败与旧入口兼容。
- 未迁移来源和M2能力列出清单。M1本地完成须有可运行的手工recipe入口、可复现输出、门禁先于新引擎入库/下游分析，以及旧入口兼容证据；不能只交几个孤立解析函数。
- 最后统一统计全部M1测试、静态/文档检查与残余风险。现在12项MySQL专用skip（原10+新2）不算通过；部署测试、候选镜像、真实MySQL/网络、生产切换分别记录，整个M1本地完成之前不启动。

## TDD执行记录与范围落实

- 首条HTML公共preview模块缺口→1通过；坏卡片/越权URL/未知空列表/403五项失败→6通过；回放与分页三项失败→9通过；详情清洗/UTC/错配及属性身份三项失败→12通过；RSS/GUID/摘要级别/合法空feed与JSON-LD三项失败→15通过。以上不代表最终M1验收。
- 最小存储标记决定前移M1：Article新增可空content_level/source_language/crawl_provenance三列，历史NULL不回填full/fr。新引擎保存级别/声明语言/recipe与证据引用，元数据升级沿用原external_id；原始快照持久化/版本审批仍M2。
- 下游保护：已标记metadata/excerpt不生成digest/insight，旧NULL保持既有行为；翻译/摘要/改写prompt改为源文本而不是无条件French，保留实际source_language/unknown、不通过模型猜测回填。缓存prompt版本随语义更新，不清库、不跑付费验证。
- 本地迁移fixture原只创建llm_config/usage两表却upgrade到head；新Article迁移要求真实article表。该历史路由fixture应明确升到d472，新增独立Article迁移fixture负责后续head，不让不存在的表成为迁移兼容承诺。

- 进度：详情噪声/profile/回放篡改/JSON重复键4失败→19通过；run首个方法缺口与metadata/GUID升级、晚期SQL回滚2失败修复后22通过。新增Article迁移缺列先失败→ops10通过；LLM级别/语言3失败→LLM80通过。一次edit非唯一块被拒且无部分修改；大payload测试ID首次输出过长，补简短ID不改断言。
- 解析隔离方案已决定：专属只读parse helper（禁socket，无app/DB密钥、无shell），父communicate有界输入/输出且超时kill/reap，子POSIX内核alarm；单文档512KiB、DOM 20k节点/64深度、JSON 4096节点/32深度、最多200候选、字段/聚合输出限制。整个preview共享绝对期限，单parse默认3秒、系统profile可收紧。现有3项资源反例先失败后再实施；不是浏览器/内存OS沙箱。

- 解析helper首轮19项失败：在导入feedparser/ssl前把socket.socket类换成函数，导致ssl子类定义TypeError（独立标准库导入已复现）；不是HTML坏或安全规则过严。先记录后改为保留socket类型、阻断connect/connect_ex/send/sendall/sendto与DNS/create_connection；不放开真实网络、不切回无时限的进程内解析。

- 25项解析预算/回收通过后，日期时区/JSON-LD description冒充full/详情漂移/历史基线4失败→31通过；访问墙/冲突模板/错绑回放5失败修复。新增trace断言误用fixture.trace/path（实际events/url），此后出现的是fixture错误，不记业务red，已仅改fixture读取。
- Legacy方案收紧（先记录再实现）：新引擎只接受确切的基础RSSCrawler/HTMLCrawler配置并转换声明式recipe，不执行旧run，也不执行任何自定义fetch/parser；共享SafeFetch/隔离parser/门禁。RSS兼容GUID/URL与summary，未知语言保留unknown，绝不标full；自定义子类及content-only feed/自定义日期/image fallback不冒充完全兼容，继续留在旧入口，需手工recipe迁移。此收紧避免把任意Python直连包装成“安全Adapter”。

- Legacy公共入口2项真实缺参red修复后执行器38通过。手工CLI拟为scripts/run_recipe.py：默认preview，显式--allow-host（不从recipe扩权），--apply才一次写入，不发布active、不主动派LLM。显式--save-snapshots写新建0600本地原始证据文件（含正文/精确URL，敏感），--replay仅只读且不联网；run禁止回放应用，避免把任意调用方合成快照当在线采集。快照保存不是M2 DB快照生命周期管理。

- 手工CLI文件缺失/回放可run两项red修复；CLI正例未配置card导致inconclusive/exit1，是fixture偏差，补合成card后首轮全套418通过/10 MySQL skip（61.34秒），不当最终M1验收。
- 新的跨切片反例3失败：180坏card让CrawlOutcome错误数组超100且业务已提交；300候选跨页未共享200上限；最终CrawlLog写失败未回滚Article。修复方案先记录：分离discovered/extracted，所有列表共享候选上限；按错误类别合并，计数不丢；构造最终Outcome和完成日志都在业务提交前同事务，失败后独立记录失败（首次无法建立run记录仍抛持久化异常，不能伪造run_id）。

- 聚合候选/错误与最终日志事务3项修复→执行器43通过。收尾补HTTP可见语义：新闻详情展示content level与source language，API仅添加这两个标记（不暴露原始provenance/快照）；不再把第三个源文tab一律标French，NULL显示unknown。此为最小存储标记前移的闭环，不改UI布局/视觉设计。

- HTTP标记3项red→web+ops43通过；重复/错题正文、详情相对图、Atom全文跳详情4项red→engine47；隐藏正文/显式付费JSON-LD/未知304证据4项red→51。仅识别有限显式墙/隐藏标记，不宣称计算CSS/浏览器可见性或普遍识别所有限制。
- 同标题升级清了成功翻译1项red修复；full/历史unknown正文保护两项直接通过；LLM级别/语言中途变更、force+skip-translate三项直接通过，不冒充新red。
- 交替新旧入口确实再次插入的2项red修复：未映射ID的RSS仍自动保留GUID，默认URL身份在规范化前按legacy解析URL计算SHA256；规范化仅用于权限/存储/同轮URL去重。旧自定义ID策略仍需显式映射，历史重复URL不批量清洗。
- 升级不能把新GUID证据冒充保留旧GUID、也不清缺失的旧author/image/date：先失败后修复，保留字段标legacy/unknown。解析启动/缺依赖2项red→独立parser_unavailable，不当selector失败且不回退进程内解析。
- 分页字段定位原用了全局item索引，公开provenance反例先失败；改用文档URL哈希+列表/页/本页item位置，原始URL不进locator。执行版本与quality profile需一起保存到运行的最小provenance，避免只有recipe指纹无法解释不同系统门槛。
- MySQL后续验收适配（仅编写，不运行）：旧PREVIOUS迁移fixture仍用今日Article ORM，会引用新增列。改为显式旧列SQL，并在升级后断言三标记NULL；补新引擎真实MySQL JSON/最终日志回滚用例。没有本地mysqld/Docker，不把它们记作red→green；新增专用skip单列，整个M1完成前仍不SSH。

- 回放shape/重复/总量与policy/profile类型6项red、后续空页/预算前停2项red、CLI bulletin参数red、执行版本/profile缺失red、JSON-LD内嵌HTML清洗red均已修复；定位索引red也通过。CLI partial明确exit1但可已提交可信部分，不能把非0误当零写入。
- CLI恶意深JSON：2000层在本环境先按根类型正常拒绝（直接通过），20000层才复现未捕获RecursionError，随后转为固定输入错误。RSS内部ENTITY样例已被现有解析器拒绝，直接通过，不冒充新XXE修复或普遍安全证明。执行器现73通过，非最终全套。
- 静态工具偏差：误用venv的ruff，报No module named ruff；项目dev依赖是flake8。先记录，改用已有flake8做同一E9/F检查，不安装包，不算业务red。

- 全套阶段复验458 passed/12 MySQL专用skip（71.41秒，1910 warnings），147 Python AST/40模板/shell/flake8指定错误集/diff通过。最后审阅发现run的开始日志在preview之后才创建，会漏掉HTTP/解析耗时；先记录，新增公共run反例后移到网络之前独立提交，不在抓取期间持有数据库事务。
- 截止边界说明：重型网页解析由父/子硬监督；主进程的有界规范化/≤65,535字节契约非空检查与收尾是动作前/后时钟检查，不宣称整个Python调用是零误差OS硬截止。模拟外部时钟在解析返回后耗尽曾仍ready，已修为resource_limit，不报告越时成功。全阶段未进行SSH/真实源/付费LLM/邮件或提交部署。

- 最后开始日志反例在正确环境重跑仍观察到None，前置独立日志后全套**459 passed/12 MySQL专用skip，71.95秒/1919 warnings**；新增M1.3/M1.4共85项。整个M1本地交付见[完成报告](../../audits/2026-09-07-m1-local-completion.md)，后续[部署测试准备](2026-09-07-m1-deployment-validation.md)仅计划、尚未执行。

## 当前步骤

1. [complete] 核对dirty工作区、M1.1/1.2接口、已有存储与入口，记录现状差异。
2. [complete] 用户已确认剩余M1统一preview/run公共验收接口。
3. [complete] 1.3列表→详情→RSS/JSON-LD→回放及基础旧Adapter垂直切片、手工CLI。
4. [complete] 1.4列表/正文门禁、可信部分应用、身份/升级及下游保护，局部与全套验证完成。
5. [complete] 整个M1本地全套验收、交付报告和部署测试准备清单；本轮不发布，后续实机测试仍pending。
