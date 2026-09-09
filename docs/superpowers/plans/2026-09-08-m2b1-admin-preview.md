# M2-B1：后台受控预览（HTTP纵向切片）

## 范围与状态

- 用户已理解并同意继续后台预览；沿用已确认的真实Admin HTTP验收，不新增测试API，不再询问内部helper接口。
- 基于4477cfd与未提交M2-A工作区，保留全部已有改动。主会话单写者，不用子代理、不提交/部署/SSH，不访问真实新闻或付费模型。
- **本地已完成**“候选 → 管理员明确的本次访问许可/质量标准 → M1 preview → 可重新查看的有限报告”。36 HTTP+2迁移，全套525通过/14 MySQL专用skip；[报告](../../audits/2026-09-08-m2b1-admin-preview.md)。不实现批准/拒绝/active路由，也不把预览ready标为validated。

## 对原M2-B的细化（先记录再实现）

1. 为保证当前用户操作闭环，访问许可独立于recipe，由管理员在每次预览表单中明确提交；保存进不可变预览报告的policy快照，而非本轮先引入一套未用到的全局policy编辑/发布API。后续B2再将受审policy纳入发布/CAS。
2. 候选内容不可改，但可以用新的管理员许可重新预览；每份报告绑定本次profile generation、source配置指纹、候选hash与engine/report版本。旧报告不能因再次预览而自动获得新authority。
3. **本轮不持久化原始HTML快照**：只保留最多5条有限样本、质量/错误和文档hash引用。页面明确“没有可回放原始证据、不能据此直接批准”。完整私有快照存储/容量/过期/重验仍在B2，不能拿hash充当来源认证或可回放证据。
4. 报告最多64KiB UTF-8、每版本保留最近20份；不记录原始正文/准确document_url到日志，不在普通API暴露报告。无论ready或failed都不写Article/不派LLM/不改变candidate状态。
5. 同步HTTP调用上限使用更小的系统预览policy（20秒、6请求、单body512KiB、总body2MiB、最多3次重定向）；仍遵循robots/逐跳权限、真实HTTP/parser监督。限制是每次preview，不声称全局并发lease/限速。

## TDD顺序

- [complete] 首条HTTP：管理员保存候选后，在版本页提交独立host许可和news/bulletin标准，真实M1引擎从合成HTTP提取结果；独立请求重读报告，Article零、LLM/消息零、candidate仍candidate。
- [complete] 没有明确许可、伪造结果/预算/状态、跨源、CSRF/非管理员均拒绝；只替换外部DNS/socket/TLS，使用既有fetch_network bootstrap，绝不mock自己的engine/quality/parser。
- [complete] ready/partial/blocked/inconclusive等报告真实呈现；标题、URL、日期/语言/级别、有限正文、错误码和数量，不把HTTP200当成功。
- [complete] GET报告与刷新不再次联网；样本数量/长度、转义、no-store/no-referrer、链接安全、原始证据缺失提示。
- [complete] 开始时固定输入并释放数据库session，抓取期间无业务写事务；结束时短事务复查，保存结果/修剪报告，同次commit，不依赖commit后ORM刷新。
- [complete] 旧表单/运行中source配置改变使报告过期；相关source编辑/toggle增加独立generation，普通last_crawled_at/名称/频率更新不伪装成抽取配置变更，防A→B→A。失败的预览不能洗掉旧报告的过期状态。
- [complete] SQL存储失败、执行基础设施错误、输入篡改均固定消息，不外泄recipe/页面/SQL参数，不伪造成功报告。
- [complete] 新增扩展迁移与历史兼容；Alembic SQL/SQLite与实际MySQL区分。全套离线、AST/模板/flake8/文档核对。

## 执行发现与调整

- 已有preview表单、额外控制字段、旧输入/停用源、source ABA、运行中/完成后配置变化、报告保留上限均有真实red后修复。
- 抓取前释放Session是正确产品行为；新增权限测试在preview之后复用旧`users` ORM fixture导致DetachedInstanceError。先记录，再让该测试通过真实登录HTTP提交已知合成账号，不改变产品事务释放行为，不冒充权限业务red。
- 20秒是引擎网络/解析预算，不包含DB锁等待/模板开销，不能声称整个HTTP请求的绝对硬截止。
- 首轮全套525通过/14 MySQL专用skip；静态检查发现直接import fixture后同名注入参数触发F811。改为模块引用后显式注册fixture（仍复用同一合成bootstrap），不禁用F811、不改测试/产品行为；随后复验。

## 验收安排

- HTTP通过正常登录、source与candidate操作，使用真实业务按钮/action和报告URL；不直接测试新内部函数。
- 复用tests/test_crawlers/conftest.py的fetch_network fixture到本文件测试作用域，不改变全局禁止网络边界。
- B1本地完成并已更新范围报告；全套最终525/14，107.31秒；156 AST/43模板/指定flake8通过。14个MySQL用例未本轮实跑。B2原始证据、完整policy/active审批/CAS、C/D可靠运行与调度仍未完成，之后继续同一HTTP验收面。
