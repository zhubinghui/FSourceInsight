# M2：版本化配置与可靠运行——本地实施细化

## 状态、授权与基线

- 后续本地B2b.1已完成：[策略/撤权报告](../../audits/2026-09-09-m2b2b-policy.md)。真实HTTP持久策略、preview/replay撤权、历史diff/CAS与source ABA，60新HTTP/2迁移，全套638/15、head c9；未提交部署，新MySQL15项未实跑。独立留出验证/规则审批与C–E仍后续。

- 最新发布：用户另行要求部署，A/B1/B2a已于2026-09-09上线22c098c/b6；本地576、CI34367023823及真正web/worker各14 MySQL通过，私有Docker卷捕获/锁/重建回放通过。见[发布报告](../../audits/2026-09-09-m2-partial-release.md)。B2b–E仍未完成；以下“本地/生产不动”保留为此前各阶段的授权及历史证据。

- 后续合入：2026-09-09已按新授权将A/B1/B2a提交为90c94b6并推送master；本提交CI离线574/14、独立MySQL14/14成功。见[合入记录](2026-09-08-m2-mainline-integration.md)。生产不动；下文保留各切片开发时的基线与本地验证范围。

- 状态：用户已确认**后台HTTP作为主要验收入口**；A候选保存、B1后台预览、B2a私有证据/回放本地完成，B2b–E未完成，详见[本地证据](../../audits/2026-09-08-m2a-candidate-http.md)。不是新增测试专用路由；测试复用真正的后台业务操作。迁移保留既有运维验收，运行/调度等后续优先从后台触发和观察。
- 用户在架构导览后要求“继续”，本轮推进M2；延续单写者、严格TDD，不使用子代理。
- HEAD为`4477cfda77f42c15fd1ab304bbd309a22e105397`。开始时已有上一轮架构导览和task_plan/findings/progress文档改动，全部保留，不reset/stash。
- 上次生产发布已结束；本轮不继承发布脚本、SSH、真实源、付费模型或邮件的执行授权。先本地实施，提交、实际MySQL/候选与生产切换另行确认。
- 范围依照[原设计](../specs/2026-09-06-dynamic-crawler-agent-design.md)与[主计划M2](2026-09-06-dynamic-crawler-agent.md)。不实施M3学习/M4浏览器，不把M1发布证据用于证明本轮改动。

## 1. 交付目标

管理员可为某来源维护受控采集档案，保存不可变recipe候选，在不写Article/不派LLM的条件下预览，查看质量/样本/diff；人工批准后，日常采集固定使用已批准版本。每次运行能追溯输入/证据，旧worker不能提交过期结果，入库后的消息可补偿，调度只有一套下一次执行规则。

M2不是直接把`get_crawler()`替换为`CrawlEngine()`；没有档案的旧来源继续兼容旧路径。已迁移到schema路径的来源若配置缺失、损坏或过期，应显式拒绝运行，不悄悄回落旧自定义直连。

## 2. 已确认的主要验收面

用户认为后台HTTP更适合作为验收入口，现据此实施。后续通过真实后台业务操作观察行为，不另建测试API、不为内部helper逐个确认接口。下列Celery是被HTTP驱动的运行链路，不要求用户另行审批测试技术细节。

1. **Admin HTTP**（新增）：来源的采集配置/候选页，保存、预览、批准、拒绝、回滚，以及运行证据页。所有变更用POST，沿用登录/管理员/有效CSRF保护；结果通过受保护的页面查看，普通API不暴露recipe、原始快照或准确敏感URL。
2. **Celery公共任务**（扩展）：保留`crawl_source(source_id)`兼容入口，验证版本路由、同逻辑run重投递、租约过期、outbox派发/消费、统一调度。消息仅携带标识，不传HTML/密钥；具体模块内部函数不是验收面。
3. **Alembic命令 + 既有文章接口**（沿用）：旧库到head的增量迁移、旧记录保留；通过已批准的Article详情/API及运行报告验证去重、内容级别与来源关联。MySQL专用用例可直接观察新事务下的约束/回滚，这是既有运维验收面，不借旧读快照判定成功。

首个切片建议：管理员在来源配置页保存合法候选，重新打开页面仍可看到同一候选，但active仍为空；没有Article、没有抓取、没有LLM。随后再加匿名/普通用户/CSRF/非法recipe等负例，每次一条red再最小green。

## 3. 代码核对带来的具体约束

- `NewsSource.updated_at`有ORM onupdate；普通抓取更新`last_crawled_at`也会改变它。**不可把这个时间直接当候选配置版本**，否则每次抓取都会让未审批候选过期。M2应使用明确的配置输入指纹/单调generation，排除运行统计字段。
- 仅比较active ID不够：A→B→A后旧候选不能再次通过。发布/回滚要同时比较base版本及generation，防止ABA；source/policy变化也使旧证据失效。
- `crawl_source()`当前完成Article后扫描该源全部未处理文章并直接delay，无法把这一窗口称为可靠交付。schema路径要改成Article与outbox同事务；旧路径是否扩展同等保证须逐步验收、明确范围。
- `CrawlLog`当前只有三态，保留旧字段与旧页面兼容；新增详细运行状态/证据不能把旧Enum当作完整新状态。
- `CrawlEngine.run()`当前自行创建日志；M2逻辑run复用要避免每次重试再生成一套无关run ID。原日志ID保持可追溯，不能用不同表同名ID让后台链接指向错误运行。
- M1只接受手工preview回放、拒绝回放apply。持久化快照仍是证据，不因知道hash就取得写库资格；不能为了审批复验取消这个边界。
- `tests/test_ops/test_article_quality_migration.py`当前使用简化旧表并升到head。新增M2迁移依赖真实source/log表后，该M1专用用例应固定升到e6，另建完整M2前序库升级用例，不把不完整fixture报错当业务red。
- `tests/integration/test_mysql_m0.py`当前HEAD固定e6。M2新增migration后再显式更新并新增真实MySQL约束/并发用例；离线SQL与SQLite不能代替实际行锁/隔离验收。

## 4. 纵向实施顺序

原计划按2.1存储、2.2可靠性、2.3调度、2.4后台列出。本轮先将2.4的最小HTTP入口与2.1组成可观察的纵向切片，避免先凭空写完整存储API和一批内部测试；**不提前部署缺少2.2/2.3的临时状态**。

### A. 候选保存与隔离（2.1 + 2.4最小入口）
- [complete] HTTP保存/独立请求重读首先404 red，再实现最少页面/存储/迁移；来源列表入口亦先red后green。
- [complete] 采集档案与QualityProfile概念分开。A仅存归属/generation，不创建网络授权；明确policy编辑在B实施，不能从recipe复制权限。
- [complete] 候选保存规范recipe、指纹、所属档案、base generation、创建者/时间；修改配置产生新版本，不覆盖旧内容。active/previous/base版本指针随B加入，不假装现在已有完整发布状态。
- [complete] 无激活/自动迁移、不创建Article/调用模型；非法JSON、表单元数据/重复值、权限扩张/其他source ID拒绝。
- [complete] 权限、CSRF、XSS/私有响应、同源绑定、事务失败恢复、commit后读取故障均有HTTP覆盖；26项HTTP+2项迁移通过，全套487/13。

### B. 受控验证与人工发布（2.1 + 2.4）

[B1受控预览](2026-09-08-m2b1-admin-preview.md)已本地完成：每次由管理员独立授权host/质量标准，保存有限报告，不保存原始HTML、不标validated、不提供审批；36 HTTP+2迁移，全套525/14，[证据](../../audits/2026-09-08-m2b1-admin-preview.md)。随后[B2a私有证据/回放](2026-09-08-m2b2-evidence.md)也本地完成，49个新HTTP用例，全套574/14；原文默认不保存、显式启用受限目录/额度/24h期限。持久policy/独立验证/发布仍B2b，不能把捕获/回放ready冒充可审批。

- [complete] B2b.1管理员单独编辑受限source policy/质量标准并版本化，grant/revoke/当前标记完整性、策略CAS/source ABA与预览回放受控完成；不是候选携带权限。
- [ ] B2b.2加入规则active/previous/base版本、独立验证/审批与相关发布CAS约束。
- [complete] 真正调用M1 preview，外部HTTP使用合成bootstrap；不mock引擎/抽取/门禁。
- [ ] 记录不可变验证证据：输入版本、policy/profile/engine、质量、错误、有限字段样本与快照引用。报告不能由提交者自报“通过”。
- [complete] B2a私有快照限目录/大小/数量/总容量/24h期限及显式清理，失败/丢失拒绝回放，不伪造可审批；DB仅存引用。原文不进页面/日志；实际共享卷/压力及部署验证仍E。
- [ ] Admin可看质量、级别、转义后的有限样本和规则diff；预览可保存控制证据，但不写业务Article、不派LLM。
- [ ] 人工批准、拒绝、回滚均有审计；CAS校验source/policy/active/generation。验证合格不等于已批准。
- [ ] 覆盖A/B竞争、A→B→A、停用源、策略变化、证据缺失/失效、跨源ID、历史版本不可修改。

### C. 固定运行输入、认领与可靠交付（2.1 + 2.2）
- [ ] 扩展既有运行日志，固定本次source/profile/schema/policy，不运行中热切selector。
- [ ] 数据库控制的source/profile认领、lease、单调fencing，短事务，不持锁HTTP；控制存储失败拒绝并发，不依赖可驱逐cache放行。
- [ ] 同逻辑run的消息重投递可恢复；旧worker即使继续执行，也不能在租约过期/被替换后提交业务或终态。
- [ ] Article、终态报告与outbox在同一次最终事务；先构造验证结果再commit，保留M1身份兼容和升级规则。
- [ ] dispatcher允许至少一次发送、延迟重试；消费端按逻辑事件/文章输入版本去重，已完成事件重复消费不再次付费。
- [ ] 明确崩溃期间外部LLM调用与本地账本之间仍可能不确定，不声称外部调用exactly-once或M3硬预算已完成。
- [ ] 故障验收：重复消息、发送前/后DB错误、broker故障、dispatcher崩溃、lease过期旧worker、最终日志失败；保持可补偿证据。

### D. 日常路由与统一调度（2.2 + 2.3）
- [ ] `crawl_source(source_id)`对已批准schema来源走新受控运行；未迁移源保留旧入口，失败不自动批准候选/启动repair。
- [ ] 单一next_due计算替代600秒检查+默认6小时Redis门禁+固定01:00双轨规则。遵从DB频率/日历/时区，旧设置迁移有明确映射，不静默丢弃。
- [ ] 手工“抓取现在”也需认领；建议不额外顺延计划时刻，若原计划已到期则由同一次认领合并完成，不立即再抓第二遍。此为拟定用户可见语义，接口确认时一并说明。
- [ ] Paris DST重复小时只执行一次；不存在小时按明确顺延规则，不双发；覆盖跨日、14点配置、短周期、停用/重新启用、迟到调度。
- [ ] 同步Celery include/routes/Beat/worker健康检查；不增加M3学习队列，不把新任务名字当作已有消费者。

### E. 完整本地回归与发布准备
- [ ] 每个行为先red后green，再局部/全套回归；工具或fixture错误单独记录，既有保护直接通过不伪称新red。
- [ ] Alembic空库/完整e6旧库、扩展兼容、索引/FK、离线MySQL SQL；不改历史Article身份/正文、不回填伪active、不drop旧日志。
- [ ] Python/模板/项目flake8、Compose解析与任务注册、文档链接；合成网络保持零外网。
- [ ] 后续真正MySQL并发、broker/prefork、候选镜像、压力/证据容量等独立实证；未执行标为未验证。
- [ ] 汇总实现、逐条red/green、残余风险、迁移/回滚方案，再请求提交/真实验证/发布授权。

## 执行记录与偏差

- A的HTTP保存404、来源列表缺链接、额外服务端字段/重复recipe被忽略、敏感页无缓存/Referrer限制、SQL失败抛私有参数、commit后额外读取失败，均先观察red再最小修复。
- 父Admin权限、CSRF、既有schema校验、转义、跨源绑定、旧候选不可覆盖直接通过，不算新red。
- A先只增加档案归属/generation和不可变候选内容/创建审计，不提前加入未验收的active/previous/policy/审批/运行字段；页面明确提示“仅保存候选”。这些字段与行为在B及后续切片按TDD增加。
- 新SQLite迁移用例升级/保留旧行/唯一与FK约束已通过；downgrade断言误把Flask-Migrate的SystemExit(1)当错误文本。先记录此测试观察问题，改从CLI output核对实际拒绝原因，不改迁移、不虚称业务red。

## 5. 当前结果与下一步

- A本地完成：26项HTTP/2项迁移；全套487 passed/13 MySQL专用skip，152 AST/42模板/指定flake8/单Alembic head通过。代码和迁移未提交部署，生产仍M1。
- B1也已本地完成：20秒/6请求的引擎预算、5条有限样本、每候选20报告、输入/ABA过期检测；新增b6迁移。最终525/14、156 AST/43模板通过；无原始HTML、无审批/路由/运行lease/outbox。
- B2a原始证据/回放已本地完成，574/14、158 AST/43模板通过，[报告](../../audits/2026-09-08-m2b2a-private-evidence.md)；没有新DDL，head仍b6。下一步B2b持久policy/独立验证/人工审批/CAS；继续同一HTTP验收面逐条red/green。完整MySQL/并发/候选/生产仍后续授权与验收。
