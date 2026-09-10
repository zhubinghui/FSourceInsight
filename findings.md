# Findings

## Worker资源优化发布（2026-09-10 13:53Z，完成）
- 配置81135d8已部署，image仍14dc6f1/c9。LLM并发2/fast2，50任务尝试与393216KiB高水位任务后回收；真实Admin→Redis→prefork门禁已加入CI，fresh pool证明RSS触发不混同计数触发。回收不是任务中限制、父进程修复、OOM可靠交付或夜间容量保证。
- 运维实际命令比较必须把Compose字符串规范成Docker argv；首次直接比较导致误拒并自动恢复旧命令，修门禁后新备份重试成功。工具label负过滤不支持、host测试日志名冲突也独立记录并修复；不能把它们混作产品red。报告 docs/audits/2026-09-10-worker-recycling-release.md。
- 准确CI34483808675成功；643本地、前后实际web/worker四轮MySQL各15、真实broker三轮通过。所有临时资源/凭据删除；清理后可用4.20GiB、LLM365.7MiB，但降幅包含新进程效应，其他站无限额风险不因本次消失。

## 当前服务器容量复核（2026-09-10 09:10Z，完成）
- 已读取已有1056个sar样本（七完整日+当日），最低MemAvailable3462MiB/3.38GiB、无<2GiB采样，最高区间CPU忙12.97%。当前负载能承受上限提升，暂不需要为此升级。历史约10分钟分辨率，不证明秒级高峰。
- FSI五个受限服务合计3968MiB，不含无限额Redis；按当前工作集差额全部用满仍约2461MiB可用。再叠1.25GiB维护测试及其他站工作集翻倍只剩约430MiB，不能无条件并行。报告 docs/audits/2026-09-10-server-capacity.md。
- 内核7日读取18条MEMCG事件，8条直接对应已知旧fast；昨晚OOM前8秒sar仍3806MiB可用，支持容器限额过紧。其他项目没有硬限、LLM834/1024MiB更值得预算/回收评估。本轮没有改变生产。
- 只读实测4 vCPU/7.57GiB RAM/无swap/根盘剩21GiB；60秒CPU平均忙2.84%、IO等待0.01%，内存/IO PSI avg为0，MemAvailable约3.78GiB。
- 当前FSI工作集约2.51GiB，另两个项目约0.73GiB；7个其他项目容器均无内存硬上限，FSI Redis同样无cgroup硬限，全部容器无CPU quota。不能只把FSI上限加起来就宣布整机有峰值保证。
- 新FSI运行约3小时：web377MiB/512、LLM834/1024、fast437/1024、beat245/384；MySQL当前工作集665MiB，生命周期memory.peak到1GiB且max事件318但无OOM（时间未知，不等于现在故障）。PSS证实不能简单叠加Celery RSS；LLM RSS合计1413MiB、PSS832MiB。
- 发现服务器已有sar历史，无需安装监控；随后已核历史MemAvailable/CPU采样（见本节开头），不是仅凭空闲一分钟推断夜间容量。7日内内核有多次MEMCG事件，能直接对应的旧fast事件另核实，不盲归全部到当前容器。

## M2-B2b.1发布新证据（2026-09-10）
- 应用14dc6f1/c9已上线；CI34443459274成功，真正web/worker镜像部署前后四轮各15 MySQL通过，原“15项尚未实跑”只属开发阶段历史。生产policy表空，不自动批准规则。
- fast的restart0掩盖了MEMCG子进程OOM；内核与memory.events确认1次kill。fast1GiB/beat384MiB容量缓解已生效，新cgroup短时事件0，仍不能证明夜间采集峰值、增长根因或长期稳定。
- 本次回滚保护明确：先停web再锁定读取policy记录，存在或不确定时不恢复旧22 web，避免静默B1绕过；保留新列/卷，不downgrade。不曾触发此恢复分支，不能称演练成功。
- 部署后MySQL在独立服务/库跑，只有测试代码挂载，运行image与线上逐项一致；并不接生产URL。临时资源已精确清理，备份/原证据卷保留。详见 docs/audits/2026-09-10-m2-policy-release.md。

## M2-B2b.1 策略设计发现（2026-09-09）
- 只按policy最大ID取当前决定不够fail-closed：若最新revoke行丢失会重新拿旧grant。采用profile当前policy_generation标记与最新不可变版本的generation交叉核验；缺行、标记NULL或回退都不是“未配置”，不回落B1或旧grant，历史详情也不能误标effective。
- source_generation与总generation分开：源采集输入/启停变化才推进前者，策略和未来规则批准推进后者。计数从profile存在时开始，不追溯以前历史，不承诺任意直接SQL改回检测。
- 当前持续策略只控制新Admin preview/replay；旧日常registry与手工CLI不在本切片范围，不能向管理员宣称是全站停源开关。
- IDNA前的字符长度不代表规范化后的长度/JSON字节数；保存前须保证规范主机能被重读校验、policy≤8KiB。不能晚于CAS才抛原始ValueError。
- 本地最终638/15、166 AST/45模板通过；15 MySQL尚未本轮实跑。旧应用22不理解持续策略/source_generation，回滚保留数据不等于保留新授权控制；未来发布/恢复需重新审阅策略并限制旧版期间后台采集变更。

## M2当前成果生产发布实证（2026-09-09，后续新授权）
- 当前生产已更新22c098c/b6；此前“生产仍M1”的各阶段记录属于当时证据。完整报告 docs/audits/2026-09-09-m2-partial-release.md。
- 真正web/worker候选各14 MySQL通过；实际Docker卷跨容器捕获/flock/重建回放通过。外部私有卷只给web，且需显式叠evidence Compose层，默认仍不留原文；未来部署遗漏该层会使保留/回放不可用而非自动删卷。
- 上线beat约245/256MiB，重复观察稳定且OOM false/restart0，但内存余量小；短时smoke不能替代压力/长期容量验收，未擅改上限。
- 用户本轮授权发布A/B1/B2a，不意味着policy/独立验证/审批、可靠run/outbox/自动路由已经存在。

## M2主干合入后的实证（2026-09-09）
- 90c94b6已包含当前M2-A/B1/B2a全部代码/迁移/测试/文档并正常推送master；本提交CI34356717036离线574/14，独立MySQL14/14，证据不再仅为本地skip。
- CI含新模型迁移、候选UTF8、preview引用JSON/实际回放/来源变化失效；不能替代真正生产镜像、共享卷并发/压力、broker/lease和恢复测试。生产仍M1，本轮没有部署。

## M2-B2a 私有证据发现（2026-09-08）
- 相同candidate/source/policy的两次capture仍需独立身份：仅绑定配置会允许替换reference。加入服务端capture_id，文件/DB分别对应；hash只是内部一致性，不认证网页或防DB+文件特权者一起伪造。
- 文件整体digest正确不代表单页hash/URL/JSON结构正确。读取须重验单页与许可/数量/字节，拒绝重复key/未知字段；路径必须服务端随机且受限，不打开引用中的../。
- 数据库与文件系统不能假装同事务。文件/fsync/SQL失败可能留有界孤儿，按mtime过期清理；DB commit不确定时不立即删文件。过期不等于即时物理删除，需显式清理或下一次保存触发。
- 0700专用目录/0600普通单链接文件/非阻塞flock是本地POSIX保证，不是OS沙箱、分布式存储或全局运行lease。symlink loop在Path.resolve可能变为带路径RuntimeError，先lstat拒绝。
- 原M1 CLI单文件快照没有后台全局容量/TTL，保持其行为，新增内部有限存储。49新HTTP、全套574/14，158 AST/43模板通过；真实共享卷/MySQL/压力/恢复仍后续。

## M2-B1 后台预览发现（2026-09-08）
- 后台真实preview必须独立于recipe接受管理员许可；B1每次permit只固化到该报告，不冒称持久source policy已发布。report ready不改变candidate状态，有限hash/样本没有原始回放证据，审批仍不可用。
- 预览前关闭Session，避免持有事务抓网页；完成短事务复查source/generation、写报告与裁剪。同一source输入ABA须独立generation，不能用updated_at（正常爬取也会改）。Admin配置路径已接，直接SQL改回仍不是本轮保证。
- 报告保留必须真正删除超过上限的行，而不只是页面limit20；旧报告URL应404。GET还需比较当前配置，不能只显示完成时的ready。
- 20秒预算只覆盖M1引擎阶段，不涵盖DB锁等待/模板；每版本20份/64KiB JSON不等于全局并发/物理磁盘硬上限。SQL/意外执行异常要固定消息，避免sample/页面混入日志。
- 最终525/14，36 HTTP+2迁移为本轮新增；14项MySQL待环境实跑。156 AST/43模板通过；fixture detached/F811分别是测试观察/静态问题，未降产品安全保证。

## M2-A HTTP本地验收发现（2026-09-08）
- 用户选择真实后台HTTP；嵌套在现有admin blueprint的页面继承权限/CSRF。测试用独立Flask上下文重读，避免外层pytest app context复用ORM事务造成假持久化。
- SQLAlchemy错误文本可能带完整recipe参数；DB失败采用固定码日志/503与rollback。commit后的candidate.id读取会触发expired ORM刷新，读连接失败可把已成功保存误报503；真实边界red后改commit前flush/取ID。
- A目前只存档案归属/generation与候选版本，未加入active/previous/policy等未来状态；页面明示未验证/未批准，旧抓取完全不读取这些表。不可变保证限现有业务HTTP不可覆盖，不声称防DB管理员直接改写。
- 26 HTTP+2迁移本地通过，全套487/13；13个MySQL含新HTTP UTF8用例未在本轮环境执行。新迁移只建两表与约束，不改旧数据；完整MySQL并发/发布仍后续。

## M2准备核对（4477cfd，尚未实现）
- NewsSource.updated_at具有onupdate，普通last_crawled_at变化也会更新；不能拿它直接当候选配置版本。独立配置指纹/generation排除运行统计，CAS还要防A→B→A的ABA。
- M1专用质量迁移测试用简化article表升head，M2依赖source/log后须固定该历史用例到e6，并另建完整前序升级用例；MySQL专用HEAD也需随新migration更新，不能把fixture不足当业务red。
- Admin/Celery现有入口已核对，M2新增候选/审批/证据及可靠派发/调度是新验收面，严格TDD要求先一次确认。先完成计划，不写未经确认边界的测试。
- 细化计划 docs/superpowers/plans/2026-09-07-m2-versioned-runtime.md；CONTEXT.md统一采集档案、质量标准、候选与active等术语，不宣称相关能力已实现。

## 当前架构导览核对（4477cfd）
- 生产调度仍是Celery旧crawl_source→registry→BaseCrawler；新CrawlEngine经手工recipe CLI/Python调用。不能把SafeFetcher的渐进接入画成新引擎已接管所有源。
- Beat实际每600秒检查频率，并有Redis默认6小时自门禁；daily-crawl固定Paris 01:00后再核对DB小时，不是已有统一next_due调度。新CrawlLog仍是旧三值状态表，丰富Outcome并未完整持久化。
- 原设计中的Schema Registry/Agent/审批/lease/outbox/browser是目标，不是当前存在的文件或运行链；导览将标明实际Implementation与后续Seam。
- root extractor仅html/rss；JSON-LD是详情字段read=jsonld，不是第三个顶层extractor。preview的质量分类允许可信metadata部分保留；run每次独立建日志，无可靠逻辑run复用。最终CrawlLog只存running/success/failed及简化计数/错误码，完整质量/快照仍非M2持久化证据库。
- LLM门禁限于文章digest/insight；metadata/excerpt仍可能走标题翻译、summary/NER/情感/分类，任务包装还有既有公司分析刷新。CLI不主动派LLM不等于生产中的文章永不被后台选中。
- SafeFetch实例复用HTTP子进程，parser每文档独立子进程；只有新引擎走完整解析监督，旧RSS/HTML仍在worker内feedparser/BeautifulSoup。函数名下的_fetch_worker.Engine是HTTP实现，不是CrawlEngine。

## M1发布实机补充（2026-09-07）
- MySQL公共run返回success但fixture查询NoResultFound，已在CI与真正候选复现。边界probe显示新事务1行/旧调用者0行；expire_all不能清REPEATABLE READ快照。修复测试观察事务而非业务引擎，并同步修回滚负例避免旧空快照掩盖泄漏；新CI及两候选12项通过。
- 全套离线通过不能替代MySQL真实隔离语义；候选单独helper通过也不等于prefork。此次追加基础billiard→parser与本站SafeFetcher TLS smoke通过，仍不声称完整broker/长期压力/真实新闻覆盖验收。
- M1应用1052edf/schema e6已生产切换，model diff0/4模型配置未变/历史三标记NULL；既有基础爬虫SafeFetch生效，新引擎日常schema路由仍M2。实际发布证据见 docs/audits/2026-09-07-m1-release.md。

## M1.3/M1.4完成后的发现（2026-09-07）
- 新旧路径互操作是身份验收的一部分：RSS省略ID映射不能丢掉GUID，URL规范化不能改legacy hash；否则后续旧Crawler.run真实再次入库。已通过公共双入口反例修复。
- Outcome必须在业务提交前构造验证，完成日志也须同事务；否则180个错误超数组契约或最终日志失败时，调用看似失败而Article已提交。开始日志则在HTTP前独立提交，避免统计漏掉采集耗时。
- `full`不能由字数或JSON-LD字段名自报；summary/description、重复/错题正文、链接密集区域、显式隐藏/付费标记均需区分。启发式门禁仍不证明事实、完整性、实际语言或全部访问限制。
- 仅存入原有content_fr会丢级别并触发深度分析，因此将三个可空Article标记提前到M1。历史NULL未知、不回填；标记excerpt/metadata禁止digest/insight，HTTP显式显示unknown/原文语言。
- 保留旧GUID/author/date时，不得把新快照中不同值的provenance说成旧值证据；相关字段降为legacy/unknown。M1仅升级较低级别，不更新同等级版本或清洗历史重复。
- 重型parser需自己的父/子期限、候选上限要跨页共享，耗尽后不请求下页，空的后页不能被前页成功掩盖。开始/加载依赖失败为parser_unavailable，不算selector坏，不回退无限期解析。
- 页面SHA256不足以区分相同内容的不同URL基址；locator加入文档URL哈希与列表/页/局部item位置。运行provenance还需引擎版本/profile，不能只有recipe指纹。
- 明确回放只读；0600原始快照由操作员显式保存，文件可能敏感。run的hash引用不是持久化快照库；新CLI不发布active配置，旧注册表/Celery尚未自动路由新引擎。
- 本轮459/12；12为待实机MySQL用例，不是通过。原M0.5实机/发布证据仍有效于旧版本，不延伸为M1上线证明。详细边界见 docs/audits/2026-09-07-m1-local-completion.md。

## 用户架构图转录
- 起点：读取源。
- 左路：尝试基本爬虫框架，RSS → HTML → 渲染。
- 右路：已知 schema 直接爬取，直接沿用已经固化的配置。
- 合流：检查读取质量，关注 HTTP 返回、抽取条数和内容解析是否正常。
- 合格：格式化输出结果，去重 / LLM 组织 / 评分。
- 不合格：Agent 学习循环，给定 MAX_loop_num；检查网页结构 → 执行提取 → 检查提取结果 → 带反馈重试。
- 学习结果：固化 schema 并在下次读取时复用，或人工复核、记日志。

## 初步盘点
- 项目基线 bf9cc61b94556e00218af267db82bf42a3b80eef，master，初始工作区干净。
- 代码涵盖 Flask Web/API、Celery、LLM、多站点爬虫和 startup_discovery；尚需逐项审查。
- tests 下暂仅发现 conftest.py 和 __init__.py，需验证测试收集结果。
- scripts/data 存在数据库备份压缩文件：不读取内容，仅审查其跟踪/交付边界。

## 爬虫初步源码发现（尚未执行验证）
- app/crawlers/base.py：fetch_articles 返回空列表也记 success；没有质量门禁。dedup 只过滤数据库已存在 external_id，没有批内去重；异常路径缺少 rollback，提交失败后日志 commit 也可能失败。
- app/crawlers/html_crawler.py：_resolve_url 使用字符串拼接而不是 urljoin；当 source.url 带目录而 href 为根相对路径时会构造错误地址。
- app/crawlers/tasks.py：BaseCrawler.run 吞掉通常的爬取异常并返回 errors，crawl_source 的 Celery retry 只在异常外抛时才触发，网络/解析失败可能不会自动重试。
- app/crawlers/registry.py：现状为注册类或 RSS 默认类；HTML 源没有注册类时直接报错，无通用 RSS→HTML→渲染发现路径。
- app/models/source.py：无 schema 版本、学习会话、质量报告或配置发布状态模型。

## 审查基础设施状态
- 并行子代理全部在启动前失败，原因是 Pi 后台运行依赖缺失；没有子代理审查结果可引用。
- 用户已明确批准不使用子代理、由主会话直接继续；无需修复 Pi。以下继续进行静态审查和隔离验证。

## Web / LLM 初查
- 严重：subscription.settings 未登录即按 email 查用户并设置 password_hash，包括管理员；CSRF 不能验证邮箱所有权。待隔离验证。
- app/__init__.py 的 markdown_light 导入 escape 但未调用，最终 Markup 输出；文章 insight 模型文本若含 HTML 可导致存储型 XSS。paragraphs 则有转义。
- website_fetcher 和抓取 URL 未做私网/跳转限制；refresh_company_analysis 可使用模型返回的 website，构成 Agent 改造需优先收口的网络权限风险。
- LLMClient._call_llm 的用量日志 commit 与 article 更新共用 db.session，会提前提交业务中间态；_link_categories 非幂等，重试可撞复合主键。
- company_analysis 缓存键仅包含 name/sector/has_site，不含 recent_news、官网实际文本等，可能所谓刷新仍读旧缓存。
- CircuitBreaker 宣称 Redis 异常回退但没有捕获 Redis I/O 错误；半开状态不限制单探针；预算按已花费用先查询后调用，不是并发硬上限。
- seed_llm_configs 与便宜优先逻辑冲突：NER/classify 实际选 nano（不是 mini）；insight 实际选 DeepSeek。nano tasks 中没有 digest。

## 部署 / 邮件 / 验证初查
- Docker Compose 5.1.0 离线 config 合并实证：base+prod 保留 web:8001/mysql:3306/redis:6380 公共绑定及 .:/app，ports/volumes: [] 未清空；加 caddy overlay 后才正确清空并绑定 web 127.0.0.1:8800。没有读取 .env，也未连接 daemon。
- 无 .dockerignore，两个 Dockerfile COPY . .，会把本地 .env、.git 和已跟踪 SQL dump 带入镜像上下文及镜像；未读取密钥或 dump 内容。
- 生产 Redis 同时承载缓存和 broker，却使用 allkeys-lru，缓存压力可驱逐队列/控制键；DB 编号隔离不是内存隔离。
- email sender/preview 使用 email/daily_digest.html、email/keyword_alert.html，但 app loader 根为 app/email/templates，仅有 daily_digest.html/keyword_alert.html。另 sender 没有传 top_insights，修复路径后仍漏发高亮文章。
- deploy.sh 自动发现 dump 就恢复（含重复部署场景），有覆盖新增数据风险；备份依赖宿主机 mysqldump，而安装步骤未装客户端；端口收口后 localhost:3306 也不可达。
- Python 3.12.14 临时 venv /tmp/fsource-audit-1XQuAg/venv 已安装 dev 依赖，未修改项目依赖。
- pytest --collect-only：exit 5，0 tests；AST 解析 103 个 Python 文件通过；shell bash -n 全部通过。
- 已执行 18 项隔离探针，18/18 复现预期当前缺陷（不是修复后的回归测试通过）。匿名管理员改密在 CSRF 开启时成功，随后本地登录可访问 /admin/；其余包含 XSS 原始输出、邮件、爬虫 URL/空跑/重试/回滚、LLM 事务/缓存/路由/JSON、Redis、私网 URL 未拦截、日期上界、修订历史丢失、调度、日志 JSON。
- 初始迁移把 llm_usage_log.task_type 定义为不含 digest/insight 的 Enum；完整 13 个 MySQL 离线迁移已核对，后续没有改该列，当前模型却是 String(50)。这是迁移/模型漂移，不推断生产库已坏。
- 部署文档 Caddy overlay 已修复其专用路径的 ports 问题，并描述 Docker-aware 备份 wrapper；不能把通用脚本问题误报为该 VPS 当前正在发生的故障。文档状态仍 Draft，未核实实际部署。
- 补充验证：25 企业地图 28 条 SQL，26 次查询 sector_group；+02:00 日期存为 naive 原时刻而非 UTC；同一 yearweek 正/负行因不同 min(date) 被拆两桶；Jinja 模板 40 个均可编译。

## 交付方向
- 最终报告已写 docs/audits/2026-09-06-project-audit.md；验证记录与可复跑隔离探针在相邻目录。
- 架构 docs/superpowers/specs/2026-09-06-dynamic-crawler-agent-design.md：确定性主流程、两层质量门禁、声明式 recipe、有界修复、独立验证、候选/发布分离、outbox/lease、浏览器安全隔离。
- 实施计划 docs/superpowers/plans/2026-09-06-dynamic-crawler-agent.md：M0 基础修复→M1 确定性引擎→M2 版本/可靠交付→M3 有界学习→M4 渲染上线→M5 可选企业目录与自动发布。
- 用户已确认以上建议默认值并开始实施，首批修复详见 docs/audits/2026-09-06-m0-implementation.md。上面的审查和 18 项探针是 bf9cc61 历史缺陷证据，不作为新正确性测试。

## 实施中的新发现与边界
- SQLite legacy transaction 模式会让首个 SAVEPOINT/release 提前提交；后续 rollback 无法撤回。新增第二条插入失败测试已复现，BaseCrawler 的 SQLite 分支显式 BEGIN 后通过。
- 单独的 LLM usage Session 并不足以安全修复：当前 pipeline 在后续付费调用前 flush Article/Company，可能与 usage 的 Article FK 父行锁互相等待。需先收集全部 LLM 结果而不写业务表，再一次应用；MySQL 行锁行为还需实机确认。
- 本地 Docker CLI 可离线合并 Compose，但 daemon socket 目标不存在，且无 mysqld；迁移只能先提交前向代码和离线 SQL，不能声称 MySQL 上线验收。
- 账户安全修复统一使旧整数会话重新登录；无密码订阅者保留数据但停用仅邮箱管理入口，后续补邮箱所有权验证/恢复。无匿名注册绕过。
- 独立日志与 savepoint 不等于 source lease/outbox：业务提交后消息派发失败的缺口仍在；M2 继续处理。

## OVH 验证与发布的新证据
- 用户另行授权OVH SQL验证和部署，TDD写入CLAUDE。通过france-vps登录同一主机；生产MySQL8.0.46、旧revision fd313但物理task_type已VARCHAR；因此新增迁移在线幂等检查，先red后green，避免重写约16万条日志。
- 隔离同版本MySQL7项实机通过，包括空库/合法旧JSON/计数回填/旧Enum/FK和费用保持/晚期写失败回滚/双会话竞争；最终候选镜像重复通过。生产readonly model diff=0。本地MySQL不可用的旧阻塞已由这批远程验证解除。
- 发布gate曾因Celery registered字符串附带[rate_limit=10/m]误判；自动回滚后定位，CLI真实协议回归先失败再修复，负例保留。
- 858a14b最终部署成功，c821已应用；公网/匿名CSRF/worker/容器身份检查通过。52项本地测试+7项MySQL及CI通过，临时资源已清理，备份回滚点保留。
- 首批发布时M0.5未实现、Safe Fetch/schema/Agent未开始；后续本地M0.5状态见下，不代表已部署。

## M1.3/M1.4前置发现
- BaseCrawler.run调用save后才返回；在旧run外包装QualityReport不能成为入库前门禁。新Adapter需只消费fetch阶段并保留未知证据，不自动把legacy内容当full。
- Article没有content_level/source_language，新引擎若直接丢弃这些字段会使后续LLM仍把excerpt当正文。M1应用路径必须保留语义或保守阻断；若需提前最小扩展列，先记录M1/M2边界调整。
- CrawlOutcome.success要求真实article_ids、valid计数完整对账；只读preview应有独立结果，不能伪造ID/成功入库。相同快照回放也不能隐式联网补页。
- M1.2的网络deadline不等于DOM/CSS/JSON解析时限；解析资源保护需独立验收。完整M1后才启动部署测试，本轮只细化计划/待确认统一应用接口。

## M1.2 实现后的证据与边界
- Safe Fetch已接入RSS/HTML基类及官网，但15个source模块仍含直接requests/cloudscraper（包括其继承/调用者）及startup_discovery未迁移；不能据基类完成声明所有来源受保护。见 docs/audits/2026-09-06-m12-safe-fetch.md。
- DNS检查必须与数值连接绑定；robots路径必须等于真实HTTP客户端最终规范化路径，dot-segment可让预查/public路径最终请求/private。两类均经公共fetch/真实HTTP代码+外部合成网络回归。
- requests关闭自动跳转仍会为Response.next读正文；urllib3 socket timeout不涵盖DNS/慢响应总时限。专属HTTP helper关闭next预读，并以父selector+子内核alarm控制生命周期，不借业务worker信号中断，不是浏览器/文件系统沙箱。
- 实体字节限制不能约束chunk framing/trailer：32条4KiB trailer可在空body下突破期待上限；新增响应协议读限额。Python3.12.14已有trailer行数限制，最初1000行失败不是无上限证据。
- 慢DNS会吃掉从解析开始算的访问间隔，实际HTTP间隔从50ms缩到约5ms；从响应头完成后保守计时修复。Retry-After须传到Celery，否则3600被默默降回60。
- 缺缓存依据的304不证明legacy无变化；robots304/错误JSON也不能当空允许规则。Source scope只用明确配置，不自动给www/跨主机重定向授权。
- 观测URL不带query；准确document_url仅供内部解析、repr隐藏，不允许整体asdict写日志/模型。正文和内部URL不承诺秘密清洗；SHA256也不代表快照已持久化。
- 父socket网络阻断不跨exec，测试现在默认拒绝真实helper启动，显式fixture才可装配子DNS/socket/TLS边界。全程无真实网络；90项Safe Fetch、官网及旧入口回归通过；最终全套374 passed/10专用MySQL skip，无新CI/实机或部署证据。

## M1.2 准备与约束（历史准备状态）
- 通用RSS/HTML仍使用requests.get，官网入口允许自动跳转；M1.1只做静态契约，没有保护这些出口。部分子类也有独立直连，渐进接入不能声称全部已迁移。
- 当前爬虫测试替换的是外部requests.get；换出口后仍应在外部网络边界提供合成数据，不能改为mock自己的SafeFetcher绕过SSRF实现。
- FetchObservation拒绝非法URL；新fetch入口应通过结构化失败表示非法输入，不能伪造合法URL或削弱正常结果不变量。
- DNS预查/逐块时钟检查不足以证明连接绑定或硬deadline，TLS原域名校验、同步阻塞和解压上限须在实现时直接验证。

## M1.1 本地契约证据
- 新schema入口仅校验/快照声明式配置，不执行抓取或批准发布。JSON须拒绝重复key/NaN/扩权字段，并在序列化前计总容量；单字段都短仍可拼出大中间JSON，公共接口内存回归先复现再修复。
- CSS属性og:title中的冒号不是伪类，允许属性数据但禁止外层伪类/任意表达式；RSS摘要映射不授予full内容级别，JSON-LD仅固定类型/路径。
- HTTP403不能标成timeout重试，无证据零条不能等于no_change；success/partial不能丢掉valid条目的去向。这里是数据自洽检查，不替代网络/内容质量门禁。
- 新NormalizedArticle正文按MySQL TEXT的UTF-8字节数限制；未知时间/语言保留unknown，无时区时间拒绝而不猜测。字段证据引用仍需执行器验证，legacy允许明确未知，不伪造快照。
- 两接口144新测试通过，全套275 passed/10专用MySQL skip。M1.1未接入旧爬虫、未提交部署；生产仍M0.5，Safe Fetch/实际引擎/质量/Agent继续后续阶段。

## M0.5 后续本地证据
- 独立账本的首个green并未解决管线写锁：晚期LLM回归真实报SQLite database is locked，进一步改为独立只读快照/收集/原子应用后通过。12步逐一中断、最终SQL失败、历史关系重试与CLI force保护已有结果均有回归。
- malformed JSON/截断应计费但不成功缓存；温度0、标题、企业所有输入、prompt版本、实际fallback均影响缓存。旧key命名空间不再使用，未来发布会冷缓存，不应批量强制重算。
- role是MySQL需引用的标识符；Alembic正确生成反引号。新revision d472保留既有配置/费用，只加兼容默认列。旧schema测试须显式旧列INSERT，不能用增加了新属性的ORM模型。
- 本地开发轮131 passed/10 MySQL skipped；后续用户确认继续隔离验收，MySQL8.0.46两轮10/10通过，新代码FK/行锁/迁移已有直接证据。M2/M3预算与交付、M1网络/质量、断路器Redis控制仍是剩余风险。
- 隔离runner虽默认root，但cap-drop ALL移除了DAC绕过权限，不能读取ubuntu的700目录/600源码。以拥有者UID1000运行可保留全部隔离而完成验收；首轮收集失败不是业务代码red。
- 初轮10项实测使用源快照覆盖旧依赖镜像；后续用户授权发布后，真正新构建web/worker候选各10项复验通过，四镜像smoke通过，代码6451b36/生产d472已上线。原有MySQL/Redis/其他项目身份未变，临时资源已清理。
- 发布准备umask077会使git写入源码为600，Docker COPY保留权限；非root测试不能假定可读。实际生产默认root；候选复验按生产UID0并保留cap-drop/只读，测试挂载644，避免以覆盖应用源码绕过候选验证。
- /admin会308规范化到/admin/，然后302到登录；验收需检查完整权限链，不能把合法尾斜线重定向误报为鉴权失败。
- 本次发布备份/旧镜像在m05-20260906134051，应用5秒恢复，无回滚。四个模型配置指纹未变，role/priority仅加兼容默认值；缓存v2冷启动和严格契约的实际provider表现仍需运行监测，未手工付费验收。
