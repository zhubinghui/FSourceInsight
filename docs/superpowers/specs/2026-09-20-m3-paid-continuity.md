# M3剩余内容发布：付费LLM继续支持（2026-09-20）

## 用户约束与基线

用户明确要求“暂时不要暂停付费LLM，需要支持。其他部分也需要部署”。这不是允许跳过预算或把旧NULL上界当已审核；但**付费暂停不再是本轮可选上线方案**。目标是在既有付费功能可用的配置下发布剩余累计内容，而不是只重复报告阻断。

基线：主会话/无子代理，release分支5271c84（应用1becae8，已通过1075离线/22实际MySQL/真实broker）；生产刚发布e6469ba/schema b3，实际SDK LiteLLM1.101.0/OpenAI2.54.0；学习仍不启用。其他工作树当前clean，主干e646。沿用[总发布计划](2026-09-19-m3-current-release.md)安全边界与[独立Admin发布](../../audits/2026-09-20-admin-safety-release.md)保护范围。

## 执行步骤

1. [complete] 16:28Z只读clean e646/b3，活跃mini/nano、max_tokens4096、日预算5、无端点/HTTP代理覆盖；当日未知费用0。旧费率不等于官方现价，详见findings.md；未输出key/原始敏感URL/个人数据。
2. [complete local] 官方固定SDK2.54合同/实际LiteLLM1.101 HTTP映射已核对；两个模型真实SDK合成传输验证含reasoning的4096输出界及default层。先red后最小请求/缓存/UI补齐，不调用真实模型；审计docs/audits/2026-09-20-m3-paid-continuity.md。
3. [complete local] 已确定下述官方端点/标准层/上界与价格，活跃模型及路由不变、不加预算；隐藏reasoning计费/付款前预留及既有未知收费/备用路由关联161通过。当前生产仍旧配置，实际候选/迁移时必须复核并CAS应用。
4. [complete] 8个新增离线、一个新增MySQL门禁，总23；关联161/23skip、244 AST/静态/diff，本地完整1083/23skip、准确CI35523984792成功，两实际候选各23项MySQL/49模板/Admin/服务门禁，额外部署terms CLI原样CAS及重复拒绝通过。
5. [complete] 17:37:29Z暂停beat、drain/TERM、冻结新备份；b3→c7及两配置CAS审核完成，17:38:55Z新web健康、17:39:41Z验收后beat最后恢复。普通付费保留；20旧表投影/环境/私有卷/非目标服务不变，无回滚。
6. [complete runtime] 部署后两image各23 MySQL复验78.106/76.745s，17:43:47Z准确清理11容器/1网络/2卷及合成凭据；health全ok。审计docs/audits/2026-09-20-m3-paid-release.md，收尾正常提交文档并合入cf561，不重建已验收应用。

## 请求约束最小补齐（实施前决定）

- 为不再依赖未知的Project默认服务层，**仅对显式配置全球官方`https://api.openai.com/v1`的OpenAI路由**请求`service_tier=default`，并把该有效参数纳入响应缓存键。自定义网关/其他provider保留原协议，不擅自新增不支持的参数。不增加DDL或通用服务层选项。
- 先经公共LLMClient+真实LiteLLM/OpenAI SDK、仅替换httpx出站HTTP验证mini/nano实际URL、max_completion_tokens=4096（含reasoning）、default层、付费前预留和独立结算；现有预算/权限/无重复收费约束继续生效。
- 待合成验证通过再采用审核配置：现有活跃模型/任务/role/priority不变，显式全球官方端点、官方标准文本价，input完整模型上界400000；output使用经实际SDK/官方参数合同确认的4096总生成上界。每次保守预留mini $0.318432、nano $0.085120，原$5日预算不提高、不设无限；不是tokenizer猜测。上下文/费率变化仍须重新审核，供应商违约不是应用能保证的发票上界。
- 输入不含付费工具/音频/图片；停用的模型继续NULL/停用。学习默认关闭、无crawl_schema显式授权；普通付费连续性不等于学习授权/完整M3完成。
- 旧usage保持原始日志，不认证为最终账单；明确保留旧费率估算的历史局限，不伪造供应商发票或新旧关联。

## 实际镜像与切换实施细则

- 固定应用候选83813e2293ec32c618dc7ebe0326d281da947b9a，准确CI35523984792；本地全套同步进行，应用内容不再边测边改。
- 独立私有目录`/home/ubuntu/fsourceinsight-backups/m3-20260920-1700`，固定git archive/bundle；以当前不可变e646 image作runtime基础，仅覆盖完整固定源，逐文件manifest和SDK版本核对。
- 沿用已验证资源限额：单internal网络/无host端口，m0-mysql512MiB、Redis64MiB、串行runner1536MiB/1.5CPU/192PIDs；独立合成凭据，不混用生产网络/env。两实际image各23项MySQL（含新增SDK合成HTTP），普通worker真实broker回收、49模板/Admin合成HTTP。
- 学习不开启；实际只更新web/worker/worker_fast/beat，base→prod→caddy→evidence→image pin，保留UID0/0700私有卷和原普通worker限制。MySQL/Redis/Caddy/其他9容器不重启。
- 最终临界区要重新核refs/原容器/源配置hash/endpoint环境及活跃路由，确认无旧CLI调用方，准确CI+本地+实际镜像全部通过后才暂停beat/drain/TERM workers/web。
- 冻结后新600全备份/CRC/trailer/hash；保留旧LLM配置安全投影和所有旧业务投影，不输出key。独立迁移进程的MySQL DDL锁等待限10秒，应用b3→c7，不做seed/downgrade。
- 迁移后、启动任何新paid caller之前，在同一DB事务按冻结配置逐行CAS，仅更新两活跃配置的api_base/标准价格/输入输出上界；模型/路由/active/default/key/生成参数不变。验证所有付费任务候选均有审核terms、每次预留和并发容纳原5美元预算；生产只做准入计算，不测试真实付款/创建虚构预留。
- 新应用恢复前验证保留数据投影/实际model diff0/空新历史未伪造；新web、两worker就绪及付费配置门禁/私有卷通过后最后恢复beat。迁移/配置任一步不明时停新业务，不自动启动旧绕账本caller，不恢复整库；保留维护状态并报告准确阻断。
- 部署后同两个image各23 MySQL复验，清理本轮准确label资源及其独占Redis匿名卷/凭据；旧备份/image保留。此验证不证明专用学习worker RO/容量/故障门禁已完成。

## 当前门禁记录

- 应用83813e2：本地完整1083通过/23专用MySQL skip/10825 warnings/606.79s。没有测试中修改应用；准确CI随后success，详见下方记录。
- 实际候选web a0e22f6eab16、worker 987ca25d98f6，均源manifest一致/SDK1.101.0/2.54.0；各23实际MySQL通过80.377/78.220s（新增标准付费连续性已实跑），各49模板/Admin通过；真实broker100任务、RSS452256KiB任务后回收/下一任务成功。
- 额外执行同一部署terms CLI文件的隔离b3→c7配置CAS门禁：合成四配置/无真实key，原样校验并一次应用两行、重复应用拒绝且不增预留/usage。仅测试私有m0数据库；生产迁移脚本的mysql/fsourceinsight硬目标不为测试放宽。多一个本轮label容器，最终精确清理数随实测清单调整。
- 切换时保留所有旧表旧列流式投影hash（不在内存/日志存原文），仅明确允许LLM端点/价格变化，新增caps另核；schema/head/new-history空值及原Company/Source代次0另外核对。服务器从master/e646正常切到release分支838，不把未协调的M3推至共享master。

## 最终协调复核变化（切换前）

- 准确CI35523984792已success：1083/23skip/798.08s，23实库42.057s，100任务/RSS452700KiB回收成功；额外terms CLI隔离CAS门禁成功，无虚构预留/usage。
- 17:25Z后最终复核发现master推进cf561dc（另工作树clean）。先停在只读阶段检查：仅CLAUDE/生态发布审计两文档，无应用变化。该文档记录另一发布者16:25的e646再次发布；不能将15:59的镜像pin当当前基线。
- 已确认本轮prepare是在16:25之后捕获实际四容器/镜像（web 2fdd208、worker e2ed903、fast7aee2b3、beat148ce5c），17:30仍同身份/e646 clean；候选确实由这些当前不可变运行镜像构建并验证，不是用过时pin重建。6关键版本一致，另补全量Python发行包/OS指纹核对，实际切换前再次全身份/配置核对。
- 因仅文档变化且实际基线未变，维持已全验收83813e2应用候选，不重新构建；cf561两文档在发布收尾正常合入保留，未推master/未改别人的工作树。
- 增加同一switch helper的`--preflight-only`模式，先完整读取投影/确认配置hash与DB硬目标、环境/现存调用方/身份/锁，退出而不暂停进程或修改生产DB；通过后原脚本再次完整核验再切换。

## 部署helper静态校正（尚未切换）

- preflight-only已于17:30:08Z成功；全量6 image的104个Python发行包、Python及OS内容完全相同，hash a0a9a4131d8ea8197e2df5b7c52bf104b197d9cf04461dae960aecf312e05b45。
- 最终逐条复核DDL发现helper原“全部新表0行”的验收假设不准确：既有d9迁移明确创建一个学习历史marker，三个generation为0，仅在原受控学习session/attempt/reservation/usage均空时complete=1。不是产品错误，也没有发生生产迁移失败。
- **先更正本计划**：除该单行marker外新业务/费用/暴露/验证表仍应0；marker必须逐字段符合旧受控usage存在性，不伪造exposure或全系统完整性。将同一snapshot/保护检查纳入额外私有m0的b3→c7/terms CLI演练再切换，不改迁移或削弱业务断言。

- 追加snapshot迁移/配置CLI演练已经通过：所有旧表旧列投影一致、精确零代次marker；新增验证容器纳入精确清理（预期11个）。初次只读门禁和额外演练均无生产写入。
- 维护边界补强：web/worker全停后再查所有队列（含celery/crawl_learn）及unacked为空，冻结配置与最初审核值相同，.env内容hash重核；不是只依赖较早的inspect快照。检查旧web无直接LLM调用入口。
- 全数据保留比较在新调用方启动**之前**完成；恢复web后正常用户写入合法，不把这种新流量误判为迁移篡改。上线后再核schema/配置/私有卷/model/两worker真实队列与任务注册/健康，不要求新流量永久为空。

## 文档收尾合并

- 发布证据先提交0ecbd20，随后正常merge cf561仅文档时，CLAUDE生态段落与本分支相邻M3说明产生一个冲突块。应用/迁移/镜像没有冲突或变化，生产已稳定完成。
- 先记录处理原则：保留本分支所有M3协议边界，保留上游生态/Admin发布说明与独立审计；同步当前838/c7/实际pin状态，旧阶段测试标为历史。检查Markdown/链接/冲突标记及与838应用树完全相同后完成merge，不用ours/theirs整文件覆盖，不改另一工作树或重新部署。

## 证据与偏差

- 重新fetch：origin/master仍e646，release工作树开始clean，另一工作树clean；没有新生产写入。
- 既定公共验收seam保持真实Admin HTTP、LLMClient、实际任务、Alembic及运维CLI/Compose；不另要求用户批准内部helper测试。
