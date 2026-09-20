# Progress

## 2026-09-19 全部现有内容提交与发布（新授权，进行中）
- 用户明确要求全部提交并部署；旧开发期禁止提交/SSH/部署不再是当前授权边界，但验收、备份和计费审核不能跳过。
- 22:06Z清点master@8bf2563，97项变更/暂存空；离线最新1019/20 MySQL skips，head b5。本地Docker无socket，gh可用；未修改生产。
- 先写 docs/superpowers/specs/2026-09-19-m3-current-release.md：正常提交/准确CI/SSH只读→审核计费与真实隔离门禁→备份/受控切换。学习不开启；若普通LLM上界无法审核，须用户明确接受暂停才切换，不能偷偷制造功能停摆。
- 只读CI路径ci.yml不存在，实际tests.yml；记录后改读。旧04月初始化含dump/删卷，不执行，采用最近增量发布纪律。
- 22:07Z发现生产刚发布生态地图b08fb8d/schema b3，origin随后又推进文档23de19e；另一工作树现clean并记录发布完成。本轮没有改生产。M3与b3为并行迁移链，需要明确合并及重验，不能用旧8bf基线覆盖。
- 只读真实模型：活跃OpenAI gpt-5.4-mini/nano，生产尚无billing上界列；当前UTC日无未知费用日志。不能在缺审核情况下透明切换。先独立release分支提交全部本地工作，整合新主干、准确CI，不强推或触另一工作树。敏感pattern检查98文件/855671 bytes无命中。

### 发布整合进展
- 751ac51已提交推送release分支；合入23de19e，保留pending/rejected墓碑/lab禁扫/详情事实与M3原子异步job。startup-analysis.v2绑定审核/地理及ORM代次；c7f21a9d680e合并b3/b5，新增2条实际MySQL方向门禁，总22。
- 合并TDD补真实详情事实/拒绝前后分析fence/1000上限/HTTP不持写锁/不扩host权限；生态测试换外部网络边界而非旧requests/helper mock。初次status字段fixture误用与实际red分开记录。
- 首轮CI35472655051（751ac51）5失败/1014通过/20skip：Compose2.38.2检查必需.env；官方同版本校验和通过并在临时目录红→绿复现。测试复制公开Compose+空.env，v2全部5通过，真实.env未读/未改。
- merge-focused-02在300s工具期限中断/35完成/无残余；下一用例独立1通过，根因未知。完整verbose merge-full-01无超时，1059通过/22skip/1个新增CLI捕获fixture失败（640.32s）；改独立真实Flask CLI后最终相关12通过（12.61s）。未把失败或skip当通过。
- 指定E9/F、相对origin/master的diff检查通过。上游原样CRLF CSV默认cached diff提示尾部空白，证据字节保留，仅另作cr-at-eol检查。生产无切换/暂停/写入，计费审核与实际候选门禁仍阻断。
- 76d0e60合并提交已推；本地最终1060通过/22skip/10601警告/623.89s，240 AST/49模板。准确CI35497160720离线成功；真实MySQL21成功/1错误，新增升级fixture缺is_auto_created等非空字段，已补全并额外断言失败计数3保留，未改产品DDL。watch曾网络no-route断开，后重新读真实结论；broker门禁未通过。
- 09-20用户继续：本地Docker仍缺；修正fixture的迁移子集3通过/22skip，不当实库绿。origin推进01bc17b仅生态发布审计1行；另一工作树有未提交Admin安全测试，本轮不修改/提交它，不默认不存在并行写者。当前普通LLM计费审核/明确暂停授权仍未解决，生产保持不变。

### 09-20后续CI与Admin安全合并
- 7f6e9f8的CI35510122656完整success：1060离线/22专用skip、实际MySQL22通过95.025s、真实broker100次任务回收/RSS450652KiB回收/下一任务正常。watch本机超时后直接查终态确认，完整日志保留；不是实际待部署web/worker镜像证明。
- 官方mini/nano/SDK/服务层资料整理到docs/audits/2026-09-20-m3-billing-review-inputs.md；Project默认Fast、区域费/网关/实际适配器仍须审核，不擅填生产上界/不默认接受付费暂停。
- 主干又推进e6469ba Admin安全，已开始合入。新增真实HTTP回归证明M3无usage的预留配置及learning创建/retry/validation/对账actor不能删除；5业务red+2外键竞争red，fixtures的detached登录/错误选样单独记录。
- 添加M3关联检查，DELETE外键拒绝回滚固定提示；不删除审计、不改DDL。上游usage history文案断言保留；关联108通过876警告39.37s。既有MySQL门禁扩展到真实Admin配置删除/对账actor保护，总数仍22，当时尚未实跑。
- 最终1becae8已推release分支，包含e6469ba及M3删除fence；本地完整1075/22skip/10768警告/613.70s，243 AST/49模板，静态无新E9/F（历史2条F401保留）。
- 准确CI35517521638全成功：1075离线789.37s；真实MySQL22/22、40.850s，真实broker完成100任务回收/RSS452980KiB回收/下一任务成功。ci-35517521638.log和本地admin-merge-full-01.log保留。
- 收尾审计docs/audits/2026-09-20-m3-release-candidate.md；后续仅文档提交，不变更已验证应用。生产无本轮写入/切换，未推master避免并行发布者误采；需要计费审核或用户明确接受暂停新付费LLM，之后才能继续实际镜像/备份/切换门禁。

## 2026-09-19 M3.2d学习派发可靠性（本地切片完成，M3仍进行中）
- 用户继续；基线8bf2563、既有累积未提交/未暂存改动保留。Docker socket仍缺，PATH无mysqld/redis-server；临时venv可用。不连服务/生产、不提交或子代理。
- 核对后先补计划：学习单session ID消息缺轮次/retry fence、重复HTTP/recover无重派间隔；旧未认领异常可能阻断新queued。拟用版本化派发键及单个可空due列，不另造付费额度/历史授权。
- 完成实际red：旧消息跨retry执行；重复POST/recover热重派；缺迁移；证据/配额查询跨deadline；收敛自身DB失败向外抛私有异常；缺派发UI。失败日志delivery-*-red保留（UI红位于focused-02）。
- 新增31离线（2迁移），最终专门子集31通过/575 warnings/33.65秒；此前关联169通过/3709 warnings/292.69秒，位于最终两条回归之前。旧恢复测试仅按新协议推进32秒/通过真实recover取得下一轮消息，原业务断言保留；既有MySQL门禁同步新head/双参数消息，仍未运行。
- 已知坏history先隔离，不能因损坏counter改变键而留在queued；SQL不可读不等价于已知损坏，旧键异常仍不能关闭有效新意图。暂无完整M3/实际MySQL/broker/容量证明。
- 全量1019 passed/20专用MySQL skipped/10149 warnings/570.29秒，`m32d-full-01.log`；无30秒faulthandler dump。223 AST/48模板，唯一head b5d81e6a430f；指定flake8 E9/F与diff检查通过，`m32d-static-01.log`。
- 30秒仅为记录UTC准入时刻的派发槽位间隔：慢COMMIT/RPC可越过时窗并晚到，非物理发送速率/排它publisher租约。全套后完善该说明文案与文档；HTTP显示回归1 passed/22 warnings/3.14秒，11文档/26本地链接/围栏/48模板/日志检查通过（delivery-copy-final.log、m32d-docs-final.log）。审计 `docs/audits/2026-09-19-m32d-learning-dispatch.md`；基线/未暂存/未提交/未部署不变。

## 2026-09-19 M3.4b企业初始分析（本地有限切片完成）
- 最终 **988 passed / 20 dedicated-MySQL skipped / 9574 warnings / 548.86秒**，`/tmp/fsi-m3-izjIZv/m34b-full-03.log`；新增64离线，最终专门子集64/53.43秒。218 AST/48模板、唯一head a2f6d9b3107c、指定flake8/diff通过。
- 收尾文档15个本地链接/围栏与最终日志核对通过；扩大flake8范围另发现两项HEAD已有F401（admin test-email的User、celery_app的db），保留未改且写入审计，不冒称全仓库lint清零。
- 企业初始分析迁到llm，持久输入/费用/派发/认领及只读Admin审计；未迁移全部手动/Article refresh。文档 docs/audits/2026-09-19-m34b-startup-analysis.md、docs/ops/startup-analysis.md。M3完整可靠性/通用留出/实际worker/MySQL/broker/容量仍未完成。
- 全套第一轮122失败/864通过/20skip，后证实为新增fixture在实例上patch Celery.send_task后的teardown残留，类边界+真实Task.delay修复，4项顺序探针通过；不改旧学习断言。第二轮986通过是最终慢查询deadline回归前结果。第三轮上述988才是最终版本。
- 真实追加red→green：JSON null别名兼容、缺账本精确job链接/坏输入标签、整秒截断提前重派、锁定读取跨deadline后仍支付或应用。回执丢失fixture误定位、非Admin账号detached、静态漏计wsgi/邮件模板与业务red分列。

以下为实施过程记录：
- 先记计划：新公司与source-owned job同事务、llm队列、queued持久重派、running/terminal不付费接管、不重置历史失败。必要差异含SafeFetcher取数和有界目录/别名扫描。
- 真实TDD reds：旧requests不能走受控合成HTTP→收口SafeFetcher；随后旧扫描实际同步调用模型（且挑历史公司）→持久队列green。新Alembic revision不存在red→expand-only迁移green，head a2f6d9b3107c。
- 实施期先补API/任务/fault回归，再全量验证。SQL提交回执故障用外部事务事件；误定位fixture已纠正，不修改业务断言来容忍重复费用。
- 全程主会话/本地合成，保留此前所有未提交未暂存改动；无SSH、daemon接入、实际网络/模型/邮件/部署。

## 2026-09-19 M3.4a学习worker（本地配置/协议完成，非实际服务完成）
- 最终 **924 passed / 19 dedicated-MySQL skipped / 8869 warnings / 481.94秒**，完整日志`/tmp/fsi-m3-izjIZv/m34a-full-01.log`。新增46离线；209 Python AST、48 Jinja模板、单head f8b64d2c901e、指定flake8/diff、Compose离线merge通过。
- 审计`docs/audits/2026-09-19-m34a-learning-worker.md`、新运维`docs/ops/learning-worker.md`及已有学习/证据/容量说明、CLAUDE/计划同步。无DDL、实际新worker build/start、RO mount/prefork/硬杀/容量证明。
- 主会话、基线8bf2563未变；所有旧/新改动未提交未暂存，无生产访问或真实调用。M3实际服务门禁、企业发现迁队列/补偿与其它余项继续后续。

以下为执行过程记录：
- 核对已有路由/Compose/证据读路径/CLI门禁，先追加实施计划；主会话本地，无真实学习/生产/提交授权。
- 新可选learning层：profile默认不消费，web/beat/学习worker开关统一默认0；独立prefork并发1/prefetch1、限额与回收、soft180/hard195，证据同外部卷RO，根只读、64MiB tmpfs、cap drop、PIDs64。不是实际容量/硬杀证明。
- 真实Compose 5.1.0要求PIDs同时在service和deploy limits中一致，先记计划再显式补64；CPU在解析JSON中为数值，修正测试协议期待，不当产品缺陷。现有两worker不变。
- 新CLI check/run：本地开关/0700同UID/RO挂载/schemahead guard；实际控制查询指定learn节点并核对注册/队列/prefork，不发业务任务；可选snapshot明确不是live。启动只接受已审查的学习命令，不做通用exec入口。
- 配置/CLI旧新相关58项通过（6.20秒）；真正的缺层/缺CLI/缺live/缺run先红后绿。随后增加真实Admin学习流程的只读文件边界兼容回归。
- Docker CLI可用但socket仍缺失，无mysqld/redis-server。真实容器挂载/进程/服务/容量未验证；本轮无DDL，head保持f8b64d2c901e。企业发现迁队列等仍后续。

## 2026-09-19 M3.2c继续（本地有限切片完成，M3仍进行中）
- 最终 **878 passed / 19 dedicated-MySQL skipped / 8807 warnings / 481.68秒**，日志`/tmp/fsi-m3-izjIZv/m32c-full-01.log`；39新增离线。205 Python AST、48 Jinja、单head f8b64d2c901e、指定flake8和diff通过。
- 139相关子集为最后认领fence修复前阶段结果，最终全量包含该修复；所有19项真实MySQL仍未运行，无真实broker/prefork/硬杀进程证明。
- 审计`docs/audits/2026-09-19-m32c-learning-lifecycle.md`，运维/领域词汇/CLAUDE/计划同步；基线8bf2563未变，保留所有原有未提交改动，未暂存/提交/部署。

以下为执行过程记录：
- 先更新计划再实现：失败/取消6小时同源冷却；blocked且从未预留、原期限/轮次内的人工重试；追加操作者/原因/轮次审计和连续计数/hash，不重置预算/期限/暴露。
- 新head f8b64d2c901e，两列一表；旧失败终态只隔离自迁移起6小时，不伪造结束时间或释放未知费用。Alembic两项通过；实际MySQL只同步head，未运行。
- 已有139项相关子集通过（254.89秒）；随后补“未认领成功的重复消息不能中止在途owner”的真实red。任务现在认领前产生attempt身份，commit-ack丢失仍能按旧身份收敛，不跨轮停止。
- 其它真实red→green：失败换capture立即启动、缺人工重试表单、模型返回后仍解析过期/取消/撤权证据、旧拒绝轮次commit-ack丢失阻断新轮、文件检查期间越过deadline仍写重试事件。其它权限/费用/SQL回归直接通过，不冒称新red。
- 用户界面提示冷却和审计；声明仅安全零准入重试，不声称付费工作接管、专用worker或完整M3完成。真实MySQL/broker仍不可用；本轮优先完成生命周期，worker配置后续。

## 2026-09-19 M3.3b继续（限定HTML路径本地完成，M3仍进行中）
- 最终 **839 passed / 19 dedicated-MySQL skipped / 8035 warnings / 436.47秒**，日志`/tmp/fsi-m3-izjIZv/m33b-full-02.log`。新增42离线；单列表HTML/三详情成功，未支持RSS/多列表/分页通用通过。
- 201 Python AST、48 Jinja模板、单head e1c73d9b502a、指定flake8/diff通过。实际MySQL门禁仅同步head，全19项仍未运行；没有真实broker/硬杀进程证据。
- 新学习协议v3同事务冻结候选；全局连续选样和报告覆盖检查、模型/较早验证暴露排除、M1覆盖/质量、当前stale判定、超时保守收敛落地。没有发布/Article/文章LLM副作用。
- 收尾red→green：旧报告丢失后阻断付费、state单列修改不能冒充通过、操作者/期限纳入绑定、模拟低精度DB舍入后时间hash稳定、候选未触发分页/额外列表分支不得通过。写入前整秒化，不延长期限、不重签旧历史。
- 第一轮836/19/428.34秒为上述精度/列表边界修复前结果，保留`m33b-full-01.log`，没有覆盖；97项相关子集是较早阶段，精度后14项另通过，最新全量以上方为准。
- 审计`docs/audits/2026-09-19-m33b-holdout-validation.md`、操作说明/领域词汇/CLAUDE/计划同步。未提交、部署或启用真实调用；M3剩余服务/通用验证前置仍明确待办。

以下是执行过程记录：
- 已核对现有输入/证据/台账/引擎，先补计划：候选冻结→base水位后首份保留采样→系统选样→真实M1列表/三详情检验→不可发布的限定范围报告；不让模型或表单选择样本，不按结果挑好样本。
- 沿用真实Admin HTTP/Alembic TDD，主会话、本地合成外部边界，无子代理或生产授权。
- 正例已跑通；同字节/换包装正文/旧详情URL被当独立样本的三项真实red后接入污染拒绝。质量回归中的:first-child不属于允许recipe CSS，先被既有契约挡住；改为合法.first-card合成标记，不当成产品缺陷。模板无样本原返回failed，已按证据不足改为inconclusive。
- 故障回归复现运行中断后无验证超时收敛，将接入既有recover。非管理员测试原期待403，但既有Admin守卫明确重定向首页；改为校验该拒绝跳转，不改权限实现。

## 2026-09-19 M3.3a受控暴露历史前置（本地完成，非独立验证）
- 先记录计划差异：逐会话计数不能发现整会话丢失；字节hash不足以识别换包装正文。仅主会话实现，无子代理/SSH/生产/真实网页或模型/提交部署。
- 新增29离线，先红后绿覆盖历史展示、缺失/回退、损坏记录、容量越界、错误控制行和迁移；原子失败/claim commit后丢ack/准入及响应后失效等为直接通过回归，未冒称新red。
- 全套 **797 passed / 19 MySQL skipped / 6972 warnings / 296.71秒**，日志`/tmp/fsi-m3-izjIZv/m33a-full-01.log`。本轮未超时，历史1b超时原因仍未知。
- 静态收尾196 Python AST、48 Jinja模板、Alembic单head、指定flake8/diff、文档链接围栏和完整日志检查通过；HEAD仍master@8bf2563，未暂存。
- 新head d9b72a6e410c；crawl-learning.v2；旧历史保持incomplete/NULL，不补认证或释放费用。每类4096元数据检查硬上限，可降低配置，满后拒绝新增而不清历史。
- 实际MySQL学习HTTP门禁已加全局计数/回退断言，但19项均未运行；本机记录的Docker socket不可用且无mysqld/redis-server，未借生产验证。
- 独立选样/验证报告、全系统暴露覆盖、冷却/完整恢复、专用worker/共享证据/容量及企业发现迁队列仍待办。审计`docs/audits/2026-09-19-m33a-exposure-history.md`，不宣称M3完成。

## 2026-09-19 M3.1b继续（本地切片完成，M3整体进行中）
- 最新全套 **768 passed/19 MySQL skipped/6330 warnings/272.63秒**，逐项完整日志`/tmp/fsi-m3-izjIZv/m31b-full-diagnostic-02.log`，30秒faulthandler未触发。新增39离线+1未跑MySQL，head c4e92f7a610b。
- 静态收尾191 Python AST（app/scripts/migrations/tests及根目录Python）、48 Jinja模板、Alembic单head、指定flake8/diff检查、新运维/审计链接围栏及最终日志校验通过；HEAD仍8bf2563。
- 收尾两项竞争回归red→green：profile锁读刷新identity-map、学习配置/报价变化拒绝。新子集39通过，实际MySQL行级竞争仍待验证。
- 一次全套420秒超时停在第704项后且无残留；旧final日志被覆盖，另存`m31b-timeout-01.log`。既有撤权单测1 passed/3.44秒及race→policy顺序探针62 passed/36.95秒均未复现，再全量得到上方768/19。根因未知，不伪称已修复确定性卡死。此前766/19与764/18只属当时历史结果。
- 已完成恢复扫描（默认关闭不排队）、迁移/学习协议绑定、公共学习缓存身份拦截、近期会话链接、预算拒绝原因及丢弃/阻断attempt状态。模型/SQL异常不记录私有正文；取消/撤权后费用仍结算。
- 已补审计/运维说明、领域词汇和CLAUDE/计划。独立留出/暴露覆盖、冷却、完整恢复门禁、专用worker Compose/共享私有卷/容量和企业发现迁队列仍待实施。全程主会话，无生产/真实LLM/子代理或提交。

以下保留开始时记录：
- 先更新M3计划：真实Admin启动/取消→持久会话/attempt→仅保留证据学习→未独立验证候选；默认关闭，不接真实网络/模型，后续独立留出/专用worker部署仍未完成。
- 新HTTP启动缺表单、任务缺失、会话0.20上界仍付费、20,000 token上界仍付费依次red→green。真实引擎训练回放已跑通，暴露只记指纹/提示hash，预算与全局同事务，现有LLM回归137项通过。
- 已有防护直接通过：policy撤权/来源ABA/证据损坏、模型返回期间取消/撤权仍结算但不写候选、重投、显式模型路由、全局/Agent/来源跨会话额度。
- 恢复测试当前red：缺recover任务。权限测试有fixture问题：移除请求Session后原users对象已detach，且logout实际是GET；改为真实HTTP固定合成邮箱登录/GET退出后继续，不将此当权限漏洞。两次无效精确编辑及一次相同内容编辑未产生文件变化。

## 2026-09-19 M3.1a全局预留/对账本地切片
- 用户确认范围后持续主会话TDD，临时Python3.12 venv `/tmp/fsi-m3-izjIZv/venv`；没有子代理/SSH/真实源/LLM/邮件或提交部署。
- 先红后绿实现预付余额阻断、跨线程在途竞争、Admin计费上界/预留/对账/固定路由审计、usage总量损坏、超旧费用列精度的越界、对账后旧失效上界仍不得付费、扩展迁移和私有响应。未知费用/SQL故障/COMMIT后丢ack/缓存免费/微额取整/权限及状态竞争等直接回归通过，未冒称全为新red。
- 全套最终729 passed/18 MySQL专用skip/5610 warnings，224.09秒；LLM+新迁移子集139通过。日志 `/tmp/fsi-m3-izjIZv/full-tests-final.log`。最初全套724/18后又加5项回归，最终已重跑。
- 新head a8d31c5e7902，两列/三表且旧配置NULL、provider/usage保持；真实MySQL增加2项（合计18），本地socket不存在/无mysqld，全部未实跑，不能借旧release背书。指定flake8与diff检查已通过（EOF多余空行已修）。
- 静态收尾181 Python AST、47 Jinja模板、单head a8d31c5e7902、指定flake8/diff/新文档链接围栏通过。
- 交付 docs/audits/2026-09-19-m31a-budget-accounting.md、docs/ops/llm-budget-accounting.md 并更新CLAUDE/计划。M3.1b学习子预算/会话及之后独立验证/可靠worker仍未实施；这是本地纵向切片，不是M3整体或生产完成。

## 2026-09-18 M3实施前置（待范围/行为确认）
- 用户要求继续完成M3。已读完整原设计、CONTEXT、TDD/tests/mocking，核对既有LLM用量/预算测试、模型及Admin预览入口。
- 原M3假设M2完成，实际缺独立验证、模型样本暴露审计和学习可靠认领/派发；先新增 docs/superpowers/plans/2026-09-18-m3-bounded-learning.md 记录差异，拟纳入最小前置，保留整个M2日常路由/调度与M4为独立范围。
- 旧临时venv路径已不存在，尚未安装新环境或运行测试。未写新测试/业务/迁移，不自动采用新的学习HTTP用户行为；向用户一次确认范围后再按公共入口TDD。无子代理/SSH/生产或付费调用。

## 2026-09-18 遗留工作复核（完成）
- 从clean master@8bf2563审阅最新release、总计划/M2分解及当前爬虫、LLM、邮件、Web/API、Compose/部署/备份源码；未使用子代理或访问生产。
- 已交付 docs/audits/2026-09-18-remaining-work.md，区分已部署成果、M2–M4功能缺口、现有安全/可靠性与产品欠账、待运行验收。确认15个source模块仍直连；不是重复旧审查里的已修复缺陷。
- 新报告链接/代码围栏、直连模块计数和git diff --check通过；两个文档源码行号核对后更正。只新增报告并更新三份规划记录，无业务/迁移/配置改动，未跑pytest/真实源/LLM/SMTP，未提交部署。673离线/16 MySQL/真实broker仅引用09-11发布历史。

## Worker并发/回收实施与发布（2026-09-10，完成）
- 配置81135d8/CI34483808675两job通过（含新增真实broker）；复用14dc6f1 images/c9。首次误比较Compose字符串/Docker argv而自动恢复旧命令与beat，修门禁保留严格断言，retry-2新备份后13:53:30Z→13:53:54Z成功。仅两worker重建，web/其他项目未重启。
- 部署后实际web/worker MySQL各15/15（29.475/28.779秒），部署worker image完整生命周期再通过RSS450672KiB。清理前host日志重名覆盖，暂停并从保留的准确Docker日志恢复15项证据，lifecycle改独立前缀；没有重跑业务或把工具错误当产品失败。
- 14:02:28Z公网健康、临时9容器/网络/测试卷/凭据全部清理、helpers归档且原入口删除。两份备份（重试19,094,088 bytes/600/gzip/SHA256）、原证据卷/旧镜像保留；可用4297MiB，LLM365.7MiB/fast378.7MiB。降幅含重启效应，夜间/长期/吞吐未验收。详见 docs/audits/2026-09-10-worker-recycling-release.md。
- 用户明确继续实现并授权合入/部署。生产overlay LLM4→2、fast2，两个prefork池50次完成尝试/393216KiB高水位任务后回收；dev不变，不修改业务代码、确认/重试或其他项目。
- Compose并发3个生产组合真实red→green，随后回收参数缺失red→green；原dev直接通过。10项运维通过，全套643/15专用skip、184.44秒，静态检查通过。
- 新Linux internal MySQL/Redis环境wr-20260910132339：实际worker image完整broker/prefork通过，实际fast image补49不提前回收后完整复跑通过。真实Admin/Redis100任务回收、fresh pool持有RSS450420/450720KiB且任务内不杀、完成后PID消失/父进程存活/后续任务成功，Article0，不新增测试任务/API、不调模型。
- 本轮实际web/worker独立MySQL候选各15通过（30.023/29.817秒）。CI已加入真实Compose commands artifact→隔离broker生命周期门禁。
- 采用配置发布：运行源码、依赖、Dockerfiles自14dc6f1无差异，复用固定image并记录配置ref，不无意义重建；此为发布前记录；后续准确commit/CI、备份、两worker切换/原beat恢复、部署后复验与清理均已完成，见本节开头。

## 服务器整体容量评估（2026-09-10，完成）
- 用户质询当前VPS是否承受提高限额；从clean de80b81起，仅SSH stdin只读/proc/cgroup/现有sar，无配置/部署/安装/付费采集。报告 docs/audits/2026-09-10-server-capacity.md。
- 4vCPU/7.57GiB/无swap/21GiB磁盘剩余；60秒三快照可用约3.78GiB，CPU忙2.84%、memory/io PSI为0。FSI工作集2.51GiB、其他两站0.73GiB；LLM834MiB/1GiB，fast437/1GiB，beat245/384MiB。
- 已有sar七完整日+当日1056样本最低可用3.38GiB，最高区间CPU忙12.97%；18个可读OOM均MEMCG，8个直接对应已知旧fast，昨晚OOM前8秒仍有3.72GiB可用。不是秒级/未来峰值保证。
- 现上限可保留、暂不需升级；FSI五个受限服务满额仍约2.40GiB余量（其他现状假设），并行维护+其他站增长则可跌到不足0.5GiB。其余站/Redis无内存硬限、全部容器无CPU quota；优先评估LLM并发/子进程回收及整机资源预算，未擅自实施。
- 收尾task_plan一次edit因标点不匹配被拒，无部分修改；重读后精确替换，非采样/业务失败。只新增本地容量文档与进度，未提交。

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

## 2026-09-10 继续开发：B2b.2a采样台账（本地完成，未提交/部署）
- 新计划先补20份preview裁剪以外的长期指纹台账，不把台账当独立验证/审批。未提交/SSH/部署。
- 已完成真实HTTP首条red（缺capture链接）→green；21次preview裁剪后的旧capture仍可读（缺历史入口red→green）。
- missing_row/reverted_marker/sequence_gap/untracked_report 四项先错误tracked，再数量/min/max/当前报告覆盖交叉验证及抓前/抓后门禁green。
- 坏hash已有保护直接通过；重hash额外原文、错version绑定、坏URL指纹三项真实red→严格字段/绑定/大小类型检查green。随后补fetch/quality指纹、跨报告引用绑定的真实red→green。
- 最终28 HTTP+2迁移新增；全套673 passed/16专用MySQLskip/5437 warnings，209.01s，日志/tmp/fsi-capture-local-final.log。175 Python AST、47应用模板、指定flake8、diff检查通过。
- f2a67b904d31只扩展capture表及profile两列；旧档案/旧程序默认incomplete，不回填未知过去、不删原审计。MySQL第16项已追加但本轮未实跑，无CI/实际镜像/生产新证据。
- 驱动实际COMMIT后丢ack返回503，文件/报告/台账/计数均保留且新请求可回放；SQL四个写入/提交前失败整体回滚，20份裁剪亦回滚。网络中另一真实HTTP采样与源变化、24h原文清理后指纹保留、Admin权限/只读等回归通过。
- 一次edit重复匹配拒绝无部分改动；owner登录fixture旧User detached发生在HTTP前，改合成账号真实HTTP登录，不改业务Session.remove。工具/fixture错误与业务red分列审计。
- 尚未实现B2b.2b/c独立留出与人工规则审批；本轮只记录已保存Admin preview，不覆盖全部采集/模型暴露。未提交/推送/SSH/部署，暂存为空；不继承既有发布授权。

## 2026-09-11 B2b.2a提交/部署（新授权完成）
- 用户要求“提交并部署”；24文件正常提交/推送330d50b，CI34580807525全成功：673/16（272.09s）、MySQL16（22.729s）、真实broker回收（RSS442648KiB）。
- 只读预检9c531e4 clean/c9，原四M2表0/Article10284/source38/log15507，MemAvailable约3.90GiB、四应用无OOM/restart；并发/回收配置不变。
- 新备份cl-20260911084734为19,177,150 bytes/600/gzip/SHA256通过；旧image及argv保留，串行四image构建时原13容器未变。实际候选web/worker各16通过33.958/33.263s；真实worker生命周期RSS450992KiB、四47模板/HTTP/prefork及跨容器证据/台账通过。
- 新回滚guard在隔离MySQL正负控制通过，不是生产恢复演练。09:04:25Z停止web、09:04:32Z健康、09:04:54Z完成，未回滚；c9→f2、model diff0、旧数据/4模型指纹保持。只四应用更新，原卷及其他项目保持。
- 部署后web/worker各16再次通过32.851/32.257s；公网匿名capture入口权限/health/实际SafeFetcher本站TLS/argv/限额/挂载通过。四应用memory.events max/oom/oom_kill均0，仅短观察。
- 09:09:25Z精确清理9测试容器/网络/3卷/临时合成凭据；归档helper600，原入口删除。可用4.30GiB，health全ok。报告docs/audits/2026-09-11-capture-ledger-release.md；收尾文档同步不重建，文档CI按准确SHA核对。
