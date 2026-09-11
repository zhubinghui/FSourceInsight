# M2-B2b.2a：长期Admin采样台账（本地完成）

## 状态与范围

用户要求继续开发；从clean `master@9c531e4`开始，主会话单写者，无子代理。本轮**未提交、推送、SSH、部署或访问真实新闻/模型/邮件**。生产没有本轮变更；此前checkout9c531e4、配置81135d8、image14dc6f1/c9的发布记录不是本轮新代码的部署证据。

原B1每候选只留20份报告、B2a原文24h且限配额。仅查询剩余报告会遗漏已裁剪的调试样本，不能据此将旧页面宣称为独立留出。按[本片计划](../superpowers/plans/2026-09-10-m2-capture-ledger.md)先交付持久采样前置，再做系统留出验证/人工规则审批。

**本片不是独立验证或审批实现**，没有active/previous、发布、Article入库、LLM派发或日常schema路由变化。

## 实现

- `CrawlCaptureManifest`：每次成功保存Admin preview，同事务追加来源/profile/candidate、原preview ID、单调sequence、actor/UTC、规范文档/hash。
- 文档仅含固定输入身份及指纹：来源/recipe/engine/generation/source_generation、持久policy ID/hash（B1为null）、临时或持久fetch/quality指纹、独立capture_id、原结果与完成状态、至多6页的requested/final URL SHA256、body SHA256、字节数与采集时间。
- **不存准确URL、网页原文、摘要、标题或host列表**。台账单文档上限8KiB；指纹不等于加密、真实性认证或授权。
- `capture_generation`与实际数量/min/max/当前保留报告的匹配台账交叉核验；抓取前/完成时检查，计数UPDATE带CAS。丢行、标记回退、sequence断裂、已跟踪档案出现旧程序漏写报告时，拒绝继续采样且不自动修复。
- `capture_history_complete`：新ORM档案True；迁移中的既有档案及旧程序省略新字段的INSERT默认False。未知过去不会因新增采样变成完整历史；incomplete档案仍可积累后续条目。
- 报告、台账、计数、20份报告裁剪同一事务。原preview ID故意不是FK，因此报告裁剪不删台账；保留profile/candidate/user FK及profile+sequence、原preview ID唯一约束。
- `GET .../crawl-config/captures`只显示最近50条，不删更早审计；`GET .../captures/<id>`可读旧ID。来源归属/Admin/no-store/no-referrer/Jinja转义，无修改或删除HTTP入口。
- 显示文档时除hash还检查确切字段、类型、大小、页面指纹、输入/行身份，重hash额外原文或错绑定不能变available。preview引用也核profile/version/原report/capture_id/hash，不能换为另一报告的条目。
- 原始证据仍需显式opt-in，24h逻辑期限/清理/配额不变；文件清理后指纹仍可读，但不能恢复原文。离线replay不追加采样条目、不变成批准。

### 三种状态不可混用

1. 历史`tracked`只表示此**已保存Admin preview链**的结构覆盖；`incomplete`保留未知过去；`unavailable`表示结构无法确认。
2. 单条文档`available`是其结构/hash/绑定校验结果。历史页不扫描并校验全部旧文档；未来验证消费历史时必须逐条检查相关记录，不能忽略坏条目继续推断“未见过”。
3. 原文available、独立验证、人工批准均是另外的条件。这里不跟踪旧爬虫、CLI、其他模型或系统外的样本暴露，也不是含robots/失败响应的完整HTTP账本。

## TDD与验证

### 真实red → 最小green

- 正常preview后缺长期capture链接；实现采样文档/存储/真实Admin详情。
- 21次preview后缺历史入口；实现独立计数、历史列表，旧报告404但旧capture仍200。
- 丢行、标记回退、序号断裂、旧程序漏写四项误报tracked；加入结构核验及抓前/抓后拒绝。
- 重hash额外原文、错version绑定、坏URL指纹三项误报available；严格schema/绑定检查，不显示敏感注入。
- 持久标准变更用例发现缺fetch/quality长期指纹；新增两种输入hash，旧capture仍保持历史值。
- 两个preview交换合法ID/hash引用被错误链接；补完整归属与capture身份复核。
- c9→f2 Alembic命令先缺revision失败；新增expand-only迁移后旧数据/默认值/FK/unique/拒降级通过。

### 已有保护直接通过（不是新增red）

坏hash、匿名/非管理员/跨源/只读/隐私、legacy incomplete不自动转正、50条只限显示、源输入变化、网络中另一次真实preview、SQL插入/计数/引用/commit前失败的整体回滚、成功后不读DB、原文清理后审计保留、replay不新增、带敏感query的重定向指纹。

数据库驱动边界还实际执行COMMIT后注入丢失ack：HTTP503，但新事务看到已提交的台账/报告/计数，原文文件未删除，replay成功。该SQLite有界故障验证不是MySQL崩溃/生产恢复演练，也未让DB与文件变成跨系统事务。

### 结果

- 新增 **28项真实Admin HTTP + 2项迁移**。
- 本地全套：**673 passed / 16 skipped / 5437 warnings，209.01s**。16项skip均为显式隔离MySQL专用用例；日志`/tmp/fsi-capture-local-final.log`。
- MySQL专用套件追加第16项：真实HTTP采样/21次裁剪/长期读取、数据库trigger拒写原子回滚/恢复、Article0/无active。head更新为`f2a67b904d31`。**本轮未实跑MySQL、CI或实际镜像门禁**，未借用此前15/15记录冒充新验证。
- 全项目 **175个Python AST / 47个应用HTML模板语法**通过；新文件flake8 E9,F、修改旧文件E9,F63,F7,F82与`git diff --check`通过。未宣称清除已有warnings或全仓style问题。
- 测试沿用真实Admin登录/CSRF/HTTP、真实CrawlEngine/SafeFetcher/parser、真实文件和SQL。只在外部DNS/socket/Popen/时间/数据库驱动或SQL触发器边界注入；无测试专用业务API，无mock自己的抽取/质量/台账实现。

### 工具/fixture问题

- 一个edit因末尾文本重复被拒，无部分修改；改用分开的基本行为/完整性测试文件。
- owner登录helper读取已过Session.remove的旧User对象导致DetachedInstanceError，尚未发出目标登录HTTP；改用相同合成账号的真实登录HTTP，不改变业务事务释放或断言。

## 迁移与后续

新增`f2a67b904d31_crawl_capture_manifests.py`，下接c9，只加profile两列及台账表，不改旧报告/候选/策略/Article/LLM数据，不回填完整历史，不允许downgrade抹掉台账。

后续发布须新授权、预检/备份、新应用镜像与独立MySQL验证；本轮有源码/迁移变化，不能沿用上次worker配置发布“不重建镜像”的结论。旧web不维护台账，回滚须限制其preview写入；保留表不代表保留追踪完整性，不能自动把漏写历史修成完整。

下一切片B2b.2b仍须系统选择独立留出、至少1列表/3不同详情、学习输入分离、完整验证审计与真实复验；原文不足/过期/撤权/源ABA/坏历史均不得假报通过。再B2b.2c实现规则diff、人工批准/拒绝/previous回滚与发布CAS。真正MySQL并发、完整消息恢复、长期FD/RSS/压力和真实源验收均未被本片替代。
