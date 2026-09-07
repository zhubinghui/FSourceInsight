# M1 本地完成：确定性引擎与质量门禁

## 结论与边界

- 开发窗口2026-09-06至09-07；用户已确认`CrawlEngine.preview()` / `run()`统一验收入口。主会话单写者、离线TDD，无子代理。
- **M1.1–M1.4按已记录的收紧范围完成本地实现与验收**；不是整个Agent完成，不是全部来源已迁移，也不是生产上线证明。
- 最终：**459 passed / 12 MySQL专用skipped，71.95秒，1919 warnings**。其中新M1.3/M1.4为85项：引擎/CLI75、LLM6、迁移1、HTTP3。原M1.2的374项保留通过；12项skip=原10项+新引擎MySQL2项，全部未在本轮实跑。
- 147个Python文件AST、40个Jinja模板编译、shell语法、指定flake8错误集通过；12份文档链接/围栏、JSON样例实际validate_recipe、diff/无暂存检查通过。新迁移MySQL离线SQL仅有3个ADD COLUMN，无Article UPDATE/DROP；不是实机DDL。不声称视觉/E2E、真实TLS、Linux prefork、MySQL迁移/锁或生产容量已通过。
- Git仍`master@f3644ca1fd0cb4a3324b1b1b610688cbed96b725`，全部M1改动本地未提交、无暂存。无SSH、真实来源访问、付费LLM、SMTP、推送或部署。
- 生产仍M0.5应用`6451b36`、schema `d472ac9e6102`；本轮未重新查询生产。不借历史M0.5 CI/实机结果证明新代码。

依据：[收尾计划与逐步red记录](../superpowers/plans/2026-09-06-m13-m14-engine-quality.md)、[主计划](../superpowers/plans/2026-09-06-dynamic-crawler-agent.md)、[M1.1](2026-09-06-m11-contracts.md)、[M1.2](2026-09-06-m12-safe-fetch.md)。

## 交付接口

```python
from app.crawlers.engine import CrawlEngine, QualityProfile
from app.crawlers.fetcher import FetchPolicy

engine = CrawlEngine(
    source_id=1,
    recipe=recipe_dict,
    fetch_policy=FetchPolicy(allowed_hosts=('news.test.invalid',)),
    profile=QualityProfile(),
)
preview = engine.preview()  # 不需要DB；不写文章、不派LLM、不发布配置
# outcome = engine.run()    # 已迁移DB的应用上下文中，人工选定recipe的一次应用
```

- `CrawlPreview`独立于`CrawlOutcome`，含articles/quality/observations/errors/status/snapshots；成功只读状态为`ready`，不伪造入库ID。
- 输入recipe重新验证、source_id一致；policy/profile须为冻结的系统对象。执行版本`news-engine.v1`。每次调用独立预算，不跨线程共享一次运行状态。
- `PageSnapshot(url, response)`为显式回放输入；最多16项/总正文8MiB，拒绝重复URL、错误类型/生成器、非规范或越权URL。核对正文SHA256、长度、HTTP状态和请求/最终观测URL绑定；缺页不联网。
- 回放仅可preview；`run()`拒绝回放。SHA256只证明字节一致，不认证来源或事实。观测沿用采集时间；预算足够时同数据/recipe/profile可复现；资源不足明确报错，不保证跨硬件的时间边界完全相同。
- `run()`先独立记录真实running日志，再抓取，期间不持有业务写事务；最后短事务锁定source、复查active/输入，应用Article、构造并验证Outcome、完成日志后才提交。晚期Article或完成日志失败均回滚业务，独立尝试失败日志。
- 无法创建初始run记录时抛持久化异常，不伪造run_id；崩溃或失败日志再次不可写时可能遗留running，待M2可靠运行状态处理。

## 抽取、质量与资源约束

- HTML多列表/有界next-link分页、同轮URL去重、相对地址按真实文档URL解析。详情按host/path最长匹配；同样匹配的冲突模板拒绝，不随意选一个。详情canonical不能改写列表身份。
- RSS/Atom保留GUID（即使recipe省略external_id映射）；否则默认按规范化前的legacy解析URL计算32位SHA256身份。权限/同轮去重用规范URL；不会因去fragment而换旧hash身份。
- RSS summary、JSON-LD description至多excerpt；明确的feed content通过正文门禁可为full并跳详情。JSON-LD只读有限类型/固定路径，数组/graph中只选同文章实体，拒重复key、畸形/歧义数据；内嵌HTML先清洗。
- 有时区日期转UTC；显式IANA源时区只解析可唯一确定的本地时间，DST歧义/不存在时间、无时区且无政策、坏日期保持unknown，不填现在。
- 列表有效率低于90%可标低质量；可由可信调用方提供最多30个参考计数，至少3个时用中位数的50%检测下降。**本轮没有自动读取/持久化历史基线**，合成参考计数不是真实站点历史证明。
- 正文默认至少200字符/2段；bulletin为80字符/1段。还检查链接密度、重复段落、列表/详情标题与正文词面相关性；清除脚本、导航、表单、推荐/广告指定区域及显式隐藏内容。不能仅凭长字符串标full。
- 显式password/paywall/challenge和所选JSON-LD实体的付费标记被拒绝，不启动浏览器或绕墙。仅有限特征，不计算外部CSS/脚本可见性，不宣称普遍识别所有限制。
- 合法空RSS可no_change；未知空HTML/后续空页、缺回放证据或无缓存304不冒充成功。可信好部分可partial/degraded应用；同类错误合并，拒绝计数不丢。M1始终`repair_dispatched=False`。

| 资源 | 本轮实现 |
|---|---|
| HTTP | 完整沿用M1.2 SafeFetcher的DNS/IP绑定、TLS、robots、逐跳、协议/实体/时间预算 |
| 文档解析 | 专属`-I`子进程，不导入应用/DB，不继承应用密钥，无shell；禁Python socket/DNS出口 |
| 单文档 | 512KiB；DOM 20,000节点/64深度；JSON-LD 4096节点/32深度 |
| 解析时间 | 单次默认3秒、可收紧；父超时kill/reap与子POSIX SIGALRM，不在生产worker本体安装信号 |
| 候选 | 全preview共享200个已处理候选；达到上限后不再请求下一页，未处理数量不冒充已抽取 |
| 输出 | HTML字段聚合有界；parser协议输出最多2MiB；最终正文不超过65,535 UTF-8字节、其余字段遵循M1.1 |
| 总时间 | HTTP与parser共享运行绝对预算；父进程有界规范化/契约检查/收尾为动作前后检查，不是整个调用零误差OS硬截止 |

两个helper都不是文件系统、容器、浏览器或总RSS安全沙箱；Python网络阻断不防原生库漏洞。父进程仍有至多65,535字节的契约非空HTML检查。测试只验证了合成外部边界与本机进程行为。

## 应用与下游保护

- `e6a91f4c820d`在`d472ac9e6102`之后仅新增Article可空`content_level`/`source_language`/`crawl_provenance`；历史NULL不回填full/fr，downgrade明确拒绝。
- 这三列从M2前移，避免RawArticle桥接丢掉门禁；完整schema版本、审批、DB快照、lease/outbox仍属M2。
- 新纪录保留级别、声明语言、recipe/引擎版本/profile、字段证据及内容hash。原始网页不随run持久化；hash不是可永久回放的快照库。
- 同源external_id优先，再按相同URL兼容旧GUID；仅升级更低内容级别，不覆盖同等级/更好正文，也不把已有未知legacy正文当低质量替换。不是同等级正文版本刷新或历史重复清洗。
- 升级后清理旧正文相关派生缓存、标为待LLM处理；标题未变则保留已有标题翻译，人工公司关系/情感不清除。缺失的旧author/image/date保留；保留旧ID/字段时证据标legacy/unknown，不把新快照值冒充旧字段证据。
- 已标记metadata_only/excerpt不调用digest/insight；旧NULL保持兼容。force+skip-translate仍清过时深度文本。LLM收集期间级别/语言改变也会拒绝应用旧结果，费用记录仍保留。
- 源文本prompt不再无条件称French；prompt版本升到`2026-09-06.2`，缓存自然失效而不清库。未知语言不靠模型猜测回填。
- 新闻详情与API展示内容级别/来源语言；原文tab不再一律标French，NULL展示unknown，不公开原始provenance。

## 手工使用

格式示例：[news-recipe.json](../examples/news-recipe.json)。`news.test.invalid`仅占位，不能当真实采集结果；按已审阅来源填写source_id、URL、selector和声明语言。文档样例不随生产镜像COPY，容器使用时需显式提供已审阅文件路径。

```bash
# 默认只读preview；主机权限由操作员参数提供，不从recipe/快照推导
python scripts/run_recipe.py --recipe /path/reviewed.json --allow-host news.example.org

# 短讯使用独立系统profile，而非允许recipe自行降低门槛
python scripts/run_recipe.py --recipe /path/reviewed.json --allow-host news.example.org --profile bulletin

# 显式新建0600证据文件；包含原始正文及精确URL，可能敏感，禁止提交Git/写普通日志
python scripts/run_recipe.py --recipe /path/reviewed.json --allow-host news.example.org --save-snapshots /private/run.json
python scripts/run_recipe.py --recipe /path/reviewed.json --allow-host news.example.org --replay /private/run.json

# DB已迁移、明确人工选择后的一次应用；不发布active配置，不主动派LLM
python scripts/run_recipe.py --recipe /path/reviewed.json --allow-host news.example.org --apply
```

快照记录采集引擎/profile信息，但回放文件不能替操作员改变当前profile或网络policy。普通stdout只含计数/级别/固定错误码/指纹与真实入库ID，不含正文或原始URL。

退出码0：ready/success/no_change；1：需关注的结果（partial/degraded可能已提交可信部分，**不能据非0推断零写入**）；2：参数/输入或快照文件读写问题。`--apply`不可与回放/保存快照组合。

## Legacy范围与剩余工作

- `CrawlEngine(..., legacy=RSSCrawler(source)或HTMLCrawler(source), fetch_policy=...)`只转换确切基础类配置，不调用旧run/fetch/custom parser；不自动接管注册表、CLI/Celery旧任务。
- 基础RSS适配偏保守的summary/GUID，HTML为简单selector映射；自定义子类、content-only旧feed、自定义日期/图片fallback不宣称完全兼容，需手写recipe。旧entrypoint原有回归仍通过。
- 仍直连的15个source模块及startup_discovery见[M1.2清单](2026-09-06-m12-safe-fetch.md)，未借Adapter洗成“安全”。
- 持久化not_modified/版本指纹与抽样复核、跨worker限速/冷却、完整SourceSchema发布与CAS、租约/fencing/outbox、消息恢复、Agent学习/硬费用预留、浏览器隔离均未实现。
- full只是该profile的确定性质量判定，不保证全文无缺、新闻真实性、内容授权、语言事实或绝对无噪声。候选验证通过不是发布批准。
- 下一步：[独立部署测试准备计划](../superpowers/plans/2026-09-07-m1-deployment-validation.md)。生产切换另列授权与门禁，不自动升级生产DB。

## 验证证据与诚实记录

- `tests/test_crawlers/test_engine.py`：75项通过；只穿过preview/run/CLI与旧公共入口。外部DNS/socket/TLS/Popen/时钟、SQL故障注入用于边界，不mock自己的extractor/quality/identity。
- `tests/test_llm/test_pipeline.py`新增6项、`tests/test_ops/test_article_quality_migration.py`新增1项、`tests/test_web/test_article_quality.py`新增3项通过。
- `tests/integration/test_mysql_m0.py`新增JSON/去重及完成日志失败回滚2项；旧schema fixture改显式旧列SQL，head指向e6。12项本轮全部skip，未冒充MySQL通过。
- 全套阶段曾为418/10、445/12、458/12；最后发现run开始日志晚于抓取，反例观察到None，前置独立日志后最终459/12。阶段数量不是同一版本证据。
- 模块缺口、缺列/CLI参数、正文错标、身份重复、完成日志提交后失败、错误数组越界、分页/资源/证据错绑等均有真实red；具体次序在收尾计划。
- parser初次把socket类替换成函数导致ssl导入TypeError，19项失败；先记录再保留socket类并封闭连接/发送方法，没有切回无期限解析。未装ruff的工具误选改为既有flake8，不安装依赖。
- fixture的trace/path名称、CLI正例漏card、超长pytest ID、非唯一/不存在edit、一次PATH分隔符误写分别记录；后者在正确PATH重跑仍复现同一业务red。未修改断言掩盖真实行为。
- DTD样例、两个既有正文保护、三个已实现LLM围栏等直接通过；不将既有保护伪称本轮新red或普遍安全证明。
