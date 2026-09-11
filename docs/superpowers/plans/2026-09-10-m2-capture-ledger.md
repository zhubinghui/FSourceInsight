# M2-B2b.2a：留出验证前置——长期采样台账

## 基线与本轮边界

用户在全部已开发修改合入/部署后要求继续开发。起点clean master@9c531e4；线上配置81135d8、image14dc6f1/c9。仅本地、主会话单写者；不继承提交/SSH/生产访问/部署授权，不触发真实新闻/模型/邮件。

检查发现：B1每候选只保留20份preview，B2a原文24h/32份配额。仅查询现存报告无法排除已经被裁剪的调试样本，因此不能据此作出独立留出结论。先交付完整纵向前置切片**采样→不可变指纹台账→报告裁剪后仍可查→历史完整性可判定**，再B2b.2b实现系统选择留出页/独立验证、B2b.2c实现人工规则审批/CAS。不是空壳审批API，不声称本片已验证/已批准规则。

## 设计

- 每次成功保存的Admin preview，同时追加不可变采样条目。只保存规范输入指纹、candidate/policy身份、独立capture_id、requested/final URL SHA256、页面body SHA256、长度、采集时间；不存准确URL/原文/片段/密钥，不解析/联网来查看历史。
- 一个来源档案的单调capture_generation与条目sequence/数量/min/max交叉核验；缺条目、标记缺失/回退、重复不自动修复或回落“没有历史”。当前仍保留的preview须有匹配台账（已跟踪档案）；旧程序遗漏写入可被发现。不能抵抗特权者同时重写所有控制数据。
- 新建档案capture_history_complete=True；expand-only迁移给**既有档案False**、generation0，不用现存20份报告猜测/回填完整历史。数据库server default False，旧程序新建档案也不能假装完整；旧档案仍可正常preview并追加新台账，但未知过去不会自动变完整。
- 台账保存与preview插入/20份裁剪、capture_generation推进同一事务，source→profile锁序不变。HTTP之前检查历史；完成时重新检查。网络/文件IO不持DB锁；文件/DB无跨系统原子性，不删除commit不确定时可能已提交的原文。
- preview原始证据仍须显式retain_evidence，仍24h/限额；台账不延长原文寿命。capture_id在所有preview生成，opt-in的文件绑定使用同一capture身份。
- 台账按source归属，最近50条显示但不删除旧审计，旧ID可读；Jinja转义、Admin/CSRF/no-store/no-referrer。损坏条目显示unavailable，不打印SQL/完整对象。无覆盖/删除HTTP入口。
- 采样条目记录原preview ID，但**不使用指向会被裁剪preview的FK**；保留candidate/user/profile FK及唯一profile/sequence、唯一原preview ID。仍保留的preview引用台账ID/hash；裁剪不影响台账。
- 这只是已保存Admin preview的采样记录，不覆盖旧爬虫/CLI/其他模型或系统外暴露，也不证明人工/模型从没见过网页。tracked仅描述结构覆盖，单条文档另做校验；未来消费历史必须逐条核验相关元数据，不能跳过坏条目推断未见。未来验证还须区分列表/详情、不同URL同正文、模板覆盖、当前policy/generation、原文可用与独立抽取；本轮不加active/previous或改日常registry。
- 后续回滚旧web须限制其preview写入；旧程序不维护本台账，保留表并不保留完整性保证。发现未追踪preview应fail closed，不伪补历史。

## TDD验收（沿用真实Admin HTTP/Alembic）

1. [complete] 保存真实preview→新HTTP能查看仅指纹台账，无Article/LLM/批准；无retain仍不落原文。第一条真实red后最小green。
2. [complete] 新/旧历史完整性、20份裁剪后仍可读、跨源/权限/隐私/严格不变、50条显示上限不删除审计。
3. [complete] SQL失败原子回滚、commit后不读、标记/行缺失或回退、内容损坏、运行中源/策略变化及旧程序未追踪报告。
4. [complete local; MySQL unrun] 增量迁移c9→f2a67b904d31：旧profile/report原样、legacy incomplete、FK/unique/拒降级；既有迁移用例保持历史边界。新MySQL用例只追加，本地未实跑明确skip，不复用旧15项作为新证据。
5. [complete] 28项新增HTTP+2迁移；全套673 passed/16 MySQL skip/5437 warnings/209.01s，175 Python AST/47应用模板/指定flake8/diff检查通过。报告 docs/audits/2026-09-10-m2-capture-ledger.md；未提交或部署，独立验证/审批明确未实现。

## 执行观察
- 首条capture链接、历史入口、四种丢行/标记/旧程序未追踪、三种重hash坏元数据均已真实red→green；坏hash已有保护直接通过。局部10项通过。
- 新增历史policy/quality用例发现B1临时标准缺乏长期输入指纹（真实KeyError red），补充fetch_policy_hash/quality_profile_hash；仍不保存host原文。
- 新Admin owner测试在真正发出登录HTTP前因fixture保存的User已过Session.remove而DetachedInstanceError；改为合成账号的真实登录HTTP，不改业务会话释放。
- 一次edit末尾重复文本匹配被工具拒绝，无部分修改；测试按HTTP基本行为/完整性拆为两个文件后继续，后加独立生命周期边界文件。
- 跨preview换入另一合法ID/hash引用先错误链接，核原report/profile/version/capture_id后green；旧程序/旧报告不伪造补齐。
- SQL插入/计数/引用/commit前失败与驱动COMMIT后丢ack、网络中真实HTTP交错、过期文件清理、只读/权限等新增回归直接通过已有或此前最小实现，未冒称新增red。
- 两项迁移先缺revision的真实失败，新增f2后通过离线MySQL SQL与SQLite旧数据/FK/唯一约束/拒降级。第16个MySQL真实HTTP门禁已追加但未实跑，旧15/15不可代替本轮。
