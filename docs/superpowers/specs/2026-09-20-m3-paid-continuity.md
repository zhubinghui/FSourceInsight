# M3剩余内容发布：付费LLM继续支持（2026-09-20）

## 用户约束与基线

用户明确要求“暂时不要暂停付费LLM，需要支持。其他部分也需要部署”。这不是允许跳过预算或把旧NULL上界当已审核；但**付费暂停不再是本轮可选上线方案**。目标是在既有付费功能可用的配置下发布剩余累计内容，而不是只重复报告阻断。

基线：主会话/无子代理，release分支5271c84（应用1becae8，已通过1075离线/22实际MySQL/真实broker）；生产刚发布e6469ba/schema b3，实际SDK LiteLLM1.101.0/OpenAI2.54.0；学习仍不启用。其他工作树当前clean，主干e646。沿用[总发布计划](2026-09-19-m3-current-release.md)安全边界与[独立Admin发布](../../audits/2026-09-20-admin-safety-release.md)保护范围。

## 执行步骤

1. [complete] 16:28Z只读clean e646/b3，活跃mini/nano、max_tokens4096、日预算5、无端点/HTTP代理覆盖；当日未知费用0。旧费率不等于官方现价，详见findings.md；未输出key/原始敏感URL/个人数据。
2. [complete local] 官方固定SDK2.54合同/实际LiteLLM1.101 HTTP映射已核对；两个模型真实SDK合成传输验证含reasoning的4096输出界及default层。先red后最小请求/缓存/UI补齐，不调用真实模型；审计docs/audits/2026-09-20-m3-paid-continuity.md。
3. [complete local] 已确定下述官方端点/标准层/上界与价格，活跃模型及路由不变、不加预算；隐藏reasoning计费/付款前预留及既有未知收费/备用路由关联161通过。当前生产仍旧配置，实际候选/迁移时必须复核并CAS应用。
4. [in_progress] 8个新增离线、一个新增MySQL升级→Admin审核→SDK连续性门禁，总实际MySQL23；关联161/23skip，244 AST/指定静态/diff通过。全套与准确CI将并行验证固定应用候选，未全部通过前不改生产；冻结依赖构建完整M3真实候选，自己23项/MySQL+服务+卷验收，不借e646的16项替代。
5. [pending] 全部门禁后新备份、drain/TERM旧调用方及Admin冻结、b3→c7扩展迁移、一次性应用审核配置、切换一致版本并验收、最后恢复beat。不留未审核NULL导致业务长期停摆；短暂受控维护与停用功能不同。
6. [pending] 部署后隔离复验/清理/审计及提交。无真实新闻/模型/SMTP验收，不恢复整库/seed/删ledger，不自动激活学习、规则或额外供应商。

## 请求约束最小补齐（实施前决定）

- 为不再依赖未知的Project默认服务层，**仅对显式配置全球官方`https://api.openai.com/v1`的OpenAI路由**请求`service_tier=default`，并把该有效参数纳入响应缓存键。自定义网关/其他provider保留原协议，不擅自新增不支持的参数。不增加DDL或通用服务层选项。
- 先经公共LLMClient+真实LiteLLM/OpenAI SDK、仅替换httpx出站HTTP验证mini/nano实际URL、max_completion_tokens=4096（含reasoning）、default层、付费前预留和独立结算；现有预算/权限/无重复收费约束继续生效。
- 待合成验证通过再采用审核配置：现有活跃模型/任务/role/priority不变，显式全球官方端点、官方标准文本价，input完整模型上界400000；output使用经实际SDK/官方参数合同确认的4096总生成上界。每次保守预留mini $0.318432、nano $0.085120，原$5日预算不提高、不设无限；不是tokenizer猜测。上下文/费率变化仍须重新审核，供应商违约不是应用能保证的发票上界。
- 输入不含付费工具/音频/图片；停用的模型继续NULL/停用。学习默认关闭、无crawl_schema显式授权；普通付费连续性不等于学习授权/完整M3完成。
- 旧usage保持原始日志，不认证为最终账单；明确保留旧费率估算的历史局限，不伪造供应商发票或新旧关联。

## 证据与偏差

- 重新fetch：origin/master仍e646，release工作树开始clean，另一工作树clean；没有新生产写入。
- 既定公共验收seam保持真实Admin HTTP、LLMClient、实际任务、Alembic及运维CLI/Compose；不另要求用户批准内部helper测试。
