# 当前M3累积内容提交与发布（2026-09-19新授权）

## 授权与起点

用户明确要求“当前已有的所有内容，全部提交并部署”。本轮允许正常提交/推送全部现有项目变更、SSH只读预检、备份、独立隔离验收及通过门禁后的应用发布。主会话单写者，不调用子代理。此前开发期的“未授权提交/部署”是历史状态，不再当作当前授权限制。

起点master@8bf2563，97项修改/新增，暂存空；最近完整离线1019 passed/20专用MySQL skipped，新head b5d81e6a430f。最后已记录生产为330d50b/f2，不假定仍是实时状态。

## 必须保留的边界

- 提交现有代码/测试/迁移/Compose/文档，不提交.env、私钥、数据库dump、私有原文、原始控制回复或临时运行日志。检查全部新增文件，不用force push/reset/stash/drop/prune/down -v。
- 不使用旧初始化deploy.sh，不恢复整库、seed或破坏性downgrade。不重启生产MySQL/Redis/Caddy及其他项目。
- 固定base→prod→caddy→evidence，保留已有external私有证据卷、UID/0700及两worker限制。学习开关与profile保持默认关闭；部署代码不等于给来源/模型新增许可或把未完成M3称为完成。
- 生产SQL在候选验收/备份之前只读。破坏性测试只用显式新建、独立internal网络中的m0-mysql/fsource_m0_validation及合成凭据，绝不指向生产。
- 本地Docker socket不可用；允许在已有发布基础设施上建立有严格CPU/RAM/PID限额、无host端口、label明确的短期隔离资源，先核剩余容量，串行测试/构建，精确清理本轮资源。
- 付费账本迁移把旧计费上界保留NULL，新代码会拒绝未审核付费；**不能当透明兼容升级**。上线前必须获得可验证的真实计费价格/全部token上界及审核，或由用户明确接受付费暂停模式。不得猜测上界/填0绕过，也不靠回滚旧调用方继续收费。这个门禁未满足时不迁移/切换M3；下述独立Admin批次仅在旧b3现网、不引入账本且付费实现不变的条件下另行验收发布。
- 真实来源/模型/SMTP不作为验收调用；只做本站健康/权限只读检查。恢复既有定时任务与额外手工触发业务不同，切换前须确认可安全恢复。
- 切换先暂停beat、等active/reserved/scheduled空，再TERM/warm-stop旧付费worker/CLI；web停止以冻结Admin写入，备份及固定旧images/argv后扩展迁移。超时不强杀任务、不混用旧新调用方。
- 回滚保留账本/新表/私有卷；旧程序不执行新预算/history/dispatch fence。失败时先停止新业务/付费及beat；不可自动恢复旧paid callers或整库覆盖来释放未知费用。
- 每次前置不符/命令失败先在本文件记录，再调整；准确SHA CI、实际image与服务验收分别记录，不用skip/旧证据替代。

## 09-20用户要求优先部署其他功能：分批发布

用户询问“暂停付费LLM是什么”，并要求其他功能尽快部署；已解释影响，并未得到停用现有AI的明确同意。为避免耦合阻断一切，修订执行顺序：
1. 先只读复核现网、SSH目标、资源及并行写者；确认独立Admin安全`e6469ba`尚未上线且准确CI通过。
2. 优先发布不含M3计费迁移/调用变化的`e6469ba`（schema仍b3）：账号防自锁/密码与重复邮箱/历史删除保护/每日采集小时设置。它含既有生态功能，不回退地图或审计；四应用一致版本，保持现有AI功能，不重置LLM配置。
3. 用固定提交的独立源码目录构建实际候选；隔离MySQL/Redis/候选镜像门禁、新备份、协调drain/有界warm-stop/切换/健康及数据验证后才恢复beat。主工作树M3内容和另一工作树均不回退/改写。
4. M3完整候选9baf6f3保留发布分支；真实计费审核及其实际候选门禁仍待，不能把这次独立Admin发布称作M3部署完成。若实时生产已含此修复，避免无意义重建，报告确切已上线范围。

实时复核15:19:36Z：生产仍四个eco-20260919220547镜像，MySQL/Redis未重启；可用内存4234656KiB、磁盘19239MiB。master/e6469ba准确CI35510283338成功，另一工作树clean，无新主干增量。独立发布执行细则见`docs/superpowers/specs/2026-09-20-admin-safety-release.md`；不能复用M3的22项数目，e646候选使用自己的16项MySQL。

独立批次已于09-20 **15:59:22Z部署e6469ba/schema b3**，实际两镜像各16项MySQL前后复验/真实broker/Admin通过，新备份/TERM drain/数据与配置保护/beat最后恢复均完成；AI功能和LiteLLM1.101.0不变。见[独立发布审计](../../audits/2026-09-20-admin-safety-release.md)。以下完整M3阶段仍未切换；不能用独立批次门禁替代M3门禁。

### 后续明确要求：付费必须继续支持

用户在独立Admin批次完成后明确“不暂停付费LLM，其他部分也要部署”。本轮不再提出付费暂停上线选项，按[付费连续性执行计划](2026-09-20-m3-paid-continuity.md)核实实际端点/SDK/费率与完整计费边界，必要时经公共seam TDD补齐请求约束，再完成完整M3门禁和发布。不能用估算/无限预算/旧调用旁路取代审核；历史关于可选择暂停的条目保留为经过，当前被本约束替代。

累计实现已于2026-09-20 **17:39:41Z发布83813e2/c7**，审核并保留现有付费AI/原5美元预算；实际1083/23门禁、备份/迁移/配置CAS/数据与服务保护/复验清理详见[最终发布审计](../../audits/2026-09-20-m3-paid-release.md)。学习仍关闭，M3整体仍有未完成项。以下阶段指当前累计实现的发布，不代表全部M3功能完成。

## 阶段（累计实现发布，独立Admin历史另记）

1. [complete] 清点/敏感信息与初始静态核对；读取现有CI/发布规程；SSH只读核生产refs/服务/容量/schema/计费配置。
2. [complete] 基础751ac51与生态/Admin安全增量均合入发布分支；准确应用候选1becae8、CI35517521638全成功（1075离线/22实际MySQL/真实broker回收）。提交不代表准许生产切换，未推master以免并行发布者误采未审核M3。
3. [complete] 实际计费合同经固定SDK/标准端点及default层验证，审核两活跃配置；完整runtime保留、新备份/旧image argv保存。
4. [complete] 准确83813e2的1083离线/23 MySQL/真实broker，两个真正image各23/49模板/Admin及运维配置CLI门禁通过。学习RO/故障/容量仍待，本次不开启。
5. [complete] 新备份/TERM/空broker、b3→c7、审核配置CAS、一致应用切换；head/model diff0、20表旧投影/费用/私有卷/worker验收通过，beat最后恢复。
6. [complete runtime] 公网验收/两image各23后验通过，11容器/网络/两测试卷/合成凭据准确清理。发布审计与文档收尾不改变已验收应用；保留旧账历史和未完成项，不回滚旧调用方。

## 观察与偏差

- 22:06Z：本地仍master@8bf2563，97项既有变更/暂存空，diff检查通过；Docker desktop-linux无socket。gh可用，origin为既有GitHub私有仓库路径（不打印凭据）。
- 查找CI时先假设ci.yml，实际文件为tests.yml；只读ENOENT，无修改/发布副作用，改读实际文件。
- 04月初始化spec包含旧dump/重建卷步骤，只作环境历史；本轮明确不用，采用09月增量发布纪律。
- **22:07:53Z只读预检发现计划外的新发布**：远端clean但HEAD为b08fb8d而非8bf2563/330d50b；四应用为candidate-eco-20260919220547，均刚启动25秒。可能存在另一发布写者，立即冻结本轮生产变更/备份/构建/切换，不覆盖新版本。先fetch并只读核来源提交、容器/发布状态；本地工作保留。确认无并行写者、整合新主干且重新验收前不得推送覆盖或发布。
- 当时只读资源：MemAvailable4518MiB、磁盘19GiB，Compose5.1.3，非目标服务正常；不是本轮新镜像/容量门禁通过。
- fetch确认origin/master从8bf新增7个生态地图/审核/去重提交至b08fb8d，另有FSourceInsight-ecosystem工作树；新迁移b3d5e8a1c407与本地M3链同源分支。不能直接用当前M3 candidate覆盖：必须整合已发布功能/单Alembic head并重跑完整验收。
- 22:09Z另一工作树clean、计划记录生态发布已完成；共享origin继续推进收尾文档23de19e。这确认原本地master被有意留后而非可直接覆盖的部署分支。允许先本地整合并验收，但生产切换仍须重新核对refs/容器身份、确认无其他发布写者。
- 只读真实schema为b3d5e8a1c407；活跃模型OpenAI gpt-5.4-mini/nano，尚无billing上界列；当前UTC日未知费用日志0。部署M3将需新审核，不修改价格/上界或直接暂停业务来假装兼容。
- **修订阶段2**：先将当前M3全部内容及本发布计划提交到独立release/m3-bounded-learning-20260919分支，推送取得准确CI，不强推master/不改另一工作树。确认发布单写者与上线计费模式之前，生产保持新生态版本；不会把未整合分支的CI当最终发布CI。
- 当前内容已提交推送751ac51（98文件）；CI35472655051进行中。合并origin/master@23de19e到release分支出现4个文本冲突（CLAUDE、startup_discovery、admin imports、MySQL HEAD），生产未变。
- **合并方案（先记录）**：同时保留已发布的lab不扫描、结构化目录优先、pending审核/Isère事实、拒绝墓碑与XSS修复，以及M3的SafeFetcher/原子Company+job/独立事务/持久llm派发。不恢复旧同步全表LLM、不把详情HTTP放进预算/业务写事务。
- 目录事实先在只读准备阶段取（每源最多20，新slug/alias候选且与配置来源同host），写事务再重查去重与来源代次；这些详情仍是各自15秒安全fetch，不冒称列表30秒预算覆盖整扫描。新增审核/地理字段进入初始分析输入与ORM代次，防在途审核被覆盖；首次部署前改用startup-analysis.v2，旧v1不自动重签。
- 原生产schema b3与M3 b5通过独立Alembic merge revision合成唯一head，不重写任一已存在迁移历史。公共Alembic与真实MySQL补两个方向/生产b3升级验证。
- 原生态测试替换已删除的requests/同步分析helper mock为既有外部fetch_network、SDK/broker边界，保留业务断言；原M3部分来源回滚测试的成功源改用startup（保持原原子性断言），lab不创建公司/任务由已发布拒绝用例保证。其它合并语义以已确认Admin/真实task/LLM/Alembic seam先回归再修复。
- 真实merge回归已复现lab仍被扫描/新公司approved、详情事实丢失、审核拒绝后仍付费/应用。初次审核测试误用了review_status字段，真实路由使用status；修fixture后重现业务红灯，两个日志分开保留。结构化提取早返回保留M3的1000上限是合并兼容修正，新增回归直接绿色，不冒称单独red。
- 合并相关首轮141通过/2失败：遗漏一处生态详情测试仍替换已移除requests/同步helper；新的Alembic heads/history CLI输出写到pytest捕获stdout而非Click result.output。先记录，分别迁至真实外部网络边界及同时读取真实CLI stdout；不是通过改业务断言容忍错误。merge head为c7f21a9d680e，新增两条实际MySQL方向门禁（总22）尚未执行。
- 22:25:49Z准确751ac51的CI35472655051离线job失败，MySQL job未执行；先保留日志、诊断平台差异/真实失败，不把本地1019绿当CI绿。生产仍无本轮写入/暂停。
- CI实为Compose v2.38.2报必需.env不存在（5失败/1014通过/20skip）；本机5.1.0在临时目录无.env也通过，不能声称已本地复现。拟下载官方同版本darwin-arm64及校验和到/tmp，仅跑离线config复现，再让测试只复制公开Compose文件+生成空.env，不读取/改动真实.env；保留所有队列/权限/资源断言。
- 官方v2.38.2 darwin-arm64校验和验证通过；同一临时配置无.env失败、仅新增空.env即成功（compose-v2-env-repro.log）。隔离修正后v2五项全通过1.65s，不改应用Compose。
- 后续相关组合merge-focused-02.log在300s工具期限终止，仅35个完成标记，无faulthandler输出；无残留pytest/helper进程。原因未知，保留日志，先定位顺序并verbose重跑，不跳过测试/放宽断言。收集顺序显示第36项为rejected_entry_is_not_rediscovered，单独1通过/3.43s，不能证明300s中断根因。改以verbose完整回归定位并覆盖最终合并，不加猜测性产品修复。
- 完整合并回归merge-full-01.log：1059通过/22skip/1失败，640.32s，无超时；唯一失败为新增heads测试捕获输出，capsys仍无法接住Alembic预绑定stdout。改用独立真实Flask CLI子进程（testing app、关闭dotenv、无生产环境）核唯一head/history；不mock迁移，也不改变head断言。修正后的最终相关12通过/111警告/12.61s，日志merge-final-subset.log。
- git diff --cached --check把合入上游原样CRLF CSV报作尾部空白；这些已发布审计数据保持字节不变，不为格式重写证据。对origin/master的实际新增/改动做diff检查通过；另以cr-at-eol核合入行，不宣称默认全量检查无警告。
- 合并提交76d0e60（父751ac51、23de19e）已推release分支，工作树clean；准确CI35497160720已启动。此SHA本地完整1060通过/22专用MySQL skip/10601警告/623.89s（merge-full-02.log），240 AST/49模板、指定E9/F及敏感pattern检查通过；不等于实际MySQL/镜像验收。
- 已明确向用户询问是否接受先暂停新的付费LLM调用上线；尚无回答。默认保持现网，不把“继续”自动解释为接受功能暂停。继续等待准确CI，生产无本轮改动。
- watch35497160720最后看到离线job成功（13m47s）、MySQL已进入实际unittest；随后本机到GitHub的IPv6链路报no route to host，watch退出1不是CI失败结论。保留ci-35497160720-watch.log，先重新只读获取状态，不重跑/跳过门禁。用户回复“继续”，继续安全准备，不擅自视为接受付费暂停。
- 重新获取状态确认35497160720最终failure：离线job成功，实际MySQL unittest失败，broker后置门禁未获通过。先保存真实失败细节、按公共迁移/HTTP seam诊断修复；禁止因本地1060绿而继续生产切换。
- MySQL精确结果21成功/1错误（22项、51.034s）：新增b3升级测试在升级前造数INSERT遗漏is_auto_created等无server default的非空字段。补全is_auto_created、ai_analysis_failures、created_at/updated_at，并增加原失败计数保留断言；不改DDL/不放松review及model-diff断言。首次误查不存在的迁移文件无写入，已通过实际e5初始表/49ca失败计数迁移核对。
- 09-20本轮继续后，本地Docker socket仍不可用；修正fixture的本地公共迁移子集3通过/22专用skip，不能当MySQL通过。fetch又发现origin/master已从23de19e推进01bc17b；先只读核新增内容/另一工作树状态，保留当前修正，不用过时候选覆盖主干或生产。新增01bc17b仅一行已发布生态审计文档；另工作树有未提交tests/test_web/test_admin_safety.py，本轮不修改/提交该工作树内容，也不据此宣称不存在并行写者。仅整合已提交文档，后续生产切换仍需协调冻结。
- fixture修正提交1002789、合入01bc文档为7f6e9f8，均推release；准确CI35510122656运行。等待期间只由主会话核官方模型计费资料，形成审核输入，不调用供应商模型、不改真实配置，也不把公共目录标称上界直接认作生产账户/网关完整合同。
- 官方模型/SDK资料已形成docs/audits/2026-09-20-m3-billing-review-inputs.md：标准单价并非账户/网关证明，Project默认Fast与区域10%附加费均影响审核；未写真实配置。
- watch35510122656命令达到1000s工具期限，未返回CI终态。先保留watch日志并重新读状态/当前步骤；不把工具超时判成测试失败或成功，也不无限重复watch。
- 重新查询确认35510122656于12:33:34Z已success（watch超时不代表CI卡住）：7f6e9f8离线1060/22skip，真实MySQL22/22（95.025s），真实broker完成100次任务后回收及RSS450652KiB后回收/下一任务成功，WORKER_LIFECYCLE_OK。完整ci-35510122656.log保存；这是CI镜像/服务证据，不是实际待部署web/worker候选或学习worker门禁。
- 结束查询时共享origin/master又推进e6469ba（Admin安全修复），不能用7f候选覆盖。先只读核增量；生产计费模式与并行发布冻结仍未确认，不切换生产。
- e646增量为7文件/221新增：防自锁/密码/历史删除/整点按配置时区爬取；另一工作树当前clean。先提交本轮CI/计费证据，再合入该已提交安全修复，重新验收准确SHA。
- 语义整合预先明确：上游删除防护只识别usage及crawl_schema作者；M3另有尚无usage的reservation、learning创建/retry/validation申请人和reconciliation actor外键。须通过真实Admin删除行为回归保留这些关联，不能合并后让账本/身份丢失或500；不修改已有记录/DDL，不开放删除审计。
- Admin新回归实际重现5类记录被删除（SQLite允许孤立关联，MySQL会外键拒绝）；另外两条DELETE外键竞争故障重现私有IntegrityError外抛。补读前检查及IntegrityError rollback/固定提示，不宣称真实并发/数据库故障全覆盖。初次fixture为detached User登录/错误validation selector，第二次为错误base采样；改真实HTTP登录及已确认HTML留出后取得5条业务red，分别保存日志，不弱化断言。
- Admin/账本/安全/运维关联回归首轮107通过/1失败：新提示替换了上游已测试的usage history措辞；保留原措辞并补充reservations，不改上游断言。扩展既有MySQL用量提交失败门禁，经真实Admin尝试删保留预留配置及对账actor；保留原收费/余额断言，总测试数仍22；当时尚未实跑，随后结果见下。
- 最终应用合并提交1becae8已推release；本地全套1075/22专用skip/10768警告/613.70s；243 AST/49模板，指定文件无新E9/F（保留历史2个F401），工作树应用提交后clean。
- 准确CI35517521638全成功：1075离线/22skip/789.37s；真实MySQL22/22、40.850s，扩展Admin记录删除保护通过；真实broker100次完成回收、RSS452980KiB完成回收/下一任务正常。完整ci-35517521638.log保留。
- 形成docs/audits/2026-09-20-m3-release-candidate.md。此后仅文档收尾提交，应用候选仍1becae8。仍缺实际待部署镜像/生产备份/切换验收，计费审核或明确接受新付费LLM暂停未解决；生产无本轮写入/暂停/切换。
