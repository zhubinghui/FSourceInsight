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
- 付费账本迁移把旧计费上界保留NULL，新代码会拒绝未审核付费；**不能当透明兼容升级**。上线前必须获得可验证的真实计费价格/全部token上界及审核，或由用户明确接受付费暂停模式。不得猜测上界/填0绕过，也不靠回滚旧调用方继续收费。这个门禁未满足时不迁移/切换生产。
- 真实来源/模型/SMTP不作为验收调用；只做本站健康/权限只读检查。恢复既有定时任务与额外手工触发业务不同，切换前须确认可安全恢复。
- 切换先暂停beat、等active/reserved/scheduled空，再TERM/warm-stop旧付费worker/CLI；web停止以冻结Admin写入，备份及固定旧images/argv后扩展迁移。超时不强杀任务、不混用旧新调用方。
- 回滚保留账本/新表/私有卷；旧程序不执行新预算/history/dispatch fence。失败时先停止新业务/付费及beat；不可自动恢复旧paid callers或整库覆盖来释放未知费用。
- 每次前置不符/命令失败先在本文件记录，再调整；准确SHA CI、实际image与服务验收分别记录，不用skip/旧证据替代。

## 阶段

1. [in_progress] 清点/敏感信息与静态核对；读取现有CI/发布规程；SSH只读核生产refs/服务/容量/schema/计费配置。
2. [pending] 正常提交全部项目内容并推送固定candidate；准确SHA CI（包括20项MySQL及已有真实broker回收）。提交不代表准许生产切换。
3. [pending] 当前计费契约/上线模式门禁；新备份、旧image/argv固定；实际候选串行构建，不改变运行服务。
4. [pending] 实际web/worker候选独立MySQL全套、真实broker/基础prefork、模板/Admin/API、私有卷隔离门禁。若要启用学习另须其RO挂载、进程限时/故障与容量验收；本次默认仍关闭，不假报这些门禁通过。
5. [pending] 门禁全通过后受控停止/迁移f2→b5（以实时schema为准）、一致切换应用；验证head/model diff/旧投影/费用/私有卷/worker命令，beat最后恢复。
6. [pending] 公网只读与实际候选复验、精确清理临时资源、发布审计与收尾提交；报告实际状态/保留风险。阻断时完成可安全完成的提交，保持生产不变并明确阻断项。

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
