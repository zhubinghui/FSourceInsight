# M2-B1：后台受控预览（本地完成）

后续：[B2a私有原始证据/回放](2026-09-08-m2b2a-private-evidence.md)已本地完成；以下保留B1交付时的范围/测试，不倒写历史能力。

## 结论

已完成“后台候选 → 管理员明确许可 → 真实M1引擎预览 → 私有报告 → 独立请求重读”。这是M2的预览切片，**不是整个M2、审批系统或Agent完成**。

基于4477cfd和未提交M2-A继续开发，保留所有既有改动。未提交/推送/SSH/部署，未访问真实来源、付费模型或邮件；生产仍是M1应用1052edf/schema e6。

## 用户操作与实际代码

1. 来源列表 → Crawl config → 候选版本页。
2. 在**独立于recipe**的表单中明确输入本次允许的精确主机，选择news或bulletin质量标准。
3. 点击`Preview without ingesting`，POST候选的`/preview`业务路由。
4. 后台调用真正的`CrawlEngine.preview()`，成功完成报告保存后重定向到`/versions/<version_id>/previews/<report_id>`。
5. 页面显示引擎状态、数量、内容级别、标题/原文链接、日期/语言、有限正文摘录、错误码与字段hash引用。

规则保存与预览均不会写Article/派LLM；预览不修改候选的candidate状态，不调用旧registry/fallback，不自动批准或发布。GET报告/刷新页面只读数据库，不重新抓取。

- [业务HTTP](../../app/web/views/crawl_config.py)
- [有限报告构建](../../app/crawlers/_preview.py)
- [页面](../../app/web/templates/admin/crawl_preview_report.html)
- [模型](../../app/models/crawl_schema.py)

## 权限、预算与保留边界

- 沿用父Admin登录/管理员/CSRF保护。表单只接受明确字段且单值，拒绝伪造recipe、结果、预算、状态、快照和创建者；报告限定所属source与candidate。
- 每次许可只用于该preview，并保存到该报告；**不是持久source policy的编辑/发布，也不是对其他运行的全局授权或撤权**。
- 系统预览policy：引擎网络/解析预算20秒，6请求（含robots/重定向），最多3次重定向，单body512KiB、总body2MiB；M1网络与parser监督真实运行。DB锁等待/模板开销不包含在20秒内，不声称HTTP全链硬截止或全局限速。
- 最多保留5个样本，正文展示前1000字符；内容级别描述完整抽取结果，不是所显示摘录。重复数是本次预览内部，不检查历史Article去重。
- 报告JSON的UTF-8表示最多64KiB（非DB物理磁盘占用保证），每候选最多20份；创建和裁剪同一次事务，旧报告超过保留范围后404。没有跨全部候选的全局容量/并发控制。
- **不持久化原始HTML/准确document_url**，只保留文档hash引用及有限样本；样本的原文链接仍可能含敏感query，页面私有/no-store/no-referrer，正文与证据转义、外链noopener/noreferrer。
- `No raw snapshots retained`醒目标识：hash不认证来源、不提供原文回放。**这些B1报告不能直接作为审批依据**；B2还要原始证据生命周期、完整policy/版本发布/CAS。

## 输入固定与报告过期

开始时短事务获取当前source/profile输入、校验表单generation和source指纹、重验候选hash。复制值后释放Session，抓取期间不持有数据库事务。

结束时短事务重新读取/锁定source与profile，比较输入，写报告和修剪历史，commit前取得返回ID，不依赖commit后的ORM刷新。

- 输入在过程中变化：记录为stale，保留原引擎结果，不能冒称当前配置下有效。
- 后续GET仍会比较当前输入/engine；过期显示`Configuration changed`，不会因只是刷新而重新验证。
- 现有Admin source edit/toggle对抽取相关配置变化原子递增profile generation，URL或启停A→B→A不能复活旧表单/报告。
- name、frequency、last_crawled_at/updated_at不作为抽取输入，因此这些正常更新不会误使报告过期。
- generation保护覆盖当前Admin配置路径；不声称识别绕过业务层的直接SQL/seed改后再改回。此处不是运行lease/fencing，也不是active发布CAS。
- 未预料到的执行异常固定503/日志码，SQL错误复用固定503/rollback，不打印原网页或SQL参数。进程崩溃、DB不可达仍可能没有报告，不伪造已验证结果。

## TDD证据

| 行为 | 首轮真实观察 | 修复/结果 |
|---|---|---|
| 后台表单/预览报告 | 版本页没有预览表单 | 添加真实HTTP闭环后通过 |
| 拒绝客户端伪造控制数据 | 6类字段被忽略且继续预览 | 严格表单拒绝，零网络 |
| 输入不匹配/停用源 | 仍返回报告 | 抓取前409拒绝 |
| Source A→B→A | 旧表单仍可运行 | Admin输入变化递增generation |
| 运行中/事后输入改变 | 报告仍显示ready | 完成复查和GET过期显示 |
| 只保留20份报告 | 最旧报告仍200 | 同事务裁剪，最旧404 |
| 异常包含私有文本 | RuntimeError向外传播 | 固定执行错误503、零伪报告 |
| 增量DDL | a731→head没有新表 | 新建b6迁移后通过 |

既有Admin/CSRF/schema/网络门禁、样本限制/转义、质量标准、状态分类、普通运行字段不影响有效性、SQL失败恢复与跨源绑定直接通过真实实现；不冒充新red。

两个测试/工具问题单独记录：
- preview正确释放Session后，权限测试复用旧users ORM fixture得到DetachedInstanceError；改为真实HTTP提交已知合成账号，没有修改产品事务纪律。
- 直接import fixture再以同名参数注入触发flake8 F811；改为模块引用后显式注册同一个fixture，不禁用规则、不改变合成网络边界。

## 验证结果

- 新增**36项后台HTTP + 2项迁移**离线通过。
- 全套最终：**525 passed / 14 MySQL专用skip / 2715 warnings，107.31秒**。修fixture静态问题前首轮同样525/14，107.88秒。
- 真实SafeFetch/HTTP协议/robots与独立parser运行在合成网络bootstrap上；未mock自家引擎/抽取/质量。进程fixture检查回收，无真实新闻网络。
- 新增MySQL HTTP预览/报告JSON/过期复验用例，HEAD改为b6，**尚未在独立MySQL实跑**；不得借M1的历史成功记录证明新代码。
- 156 Python AST、43模板编译、指定flake8、diff检查通过。新Alembic单head为`b6c2a4d9e710`。
- 迁移只添加`crawl_preview_report`及FK/索引，不回填/修改来源、候选、Article、旧日志或LLM配置；SQLite最小依赖升级保留候选，downgrade明确拒绝。离线SQL/SQLite不等于完整MySQL并发/锁验收。

日志：本地`/tmp/fsi-m2b1-tests-final.log`。本轮没有部署验证/视觉浏览器E2E/完整broker或长期压力实证。

## 下一步

按[细化计划](../superpowers/plans/2026-09-08-m2b1-admin-preview.md)继续B2：私有原始证据及容量/过期/复验、持久policy与active/previous、人工批准/拒绝/回滚和CAS。之后才是日常schema路由、运行认领、outbox和统一调度。
