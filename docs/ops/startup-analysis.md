# 企业发现初始分析：持久LLM队列

状态：**M3已提交发布分支，正在整合/验收，尚未部署，不是实际服务或完整M3验收。** 当前发布计划见[提交与发布门禁](../superpowers/specs/2026-09-19-m3-current-release.md)。

## 业务边界

- `StartupSource` 是企业目录配置，不是 `NewsSource` 或M2持久采集策略。仍沿用Admin配置的启用目录；`CRAWL_LEARNING_ENABLED`只控制学习、不关闭此普通企业工作流。没有新建recipe审批、新闻发布或浏览器路径。
- 只扫描启用的`startup`目录，不扫描`research_lab`；结构化目录优先，纯文本仅作fallback。新公司为`pending`，需要Admin审核才进入地图；rejected墓碑阻止同slug再建。
- 扫描只创建本次真正新增的Company，并在**同一独立事务**创建一个 `StartupAnalysisJob`。已有slug/别名匹配不补造来源关联，也不重置失败次数；某来源写失败不能把它的半成品和下一个来源一起提交。
- 保留原企业地图业务；公司AI分析变为异步初始分析。不存在新的Article写入、文章LLM派发或规则激活。总部缺失仍作为N/A发给模型，不再凭目录归属填“Grenoble”。目录提取/模型输出不证明实体或新闻事实为真。
- 初始分析只使用冻结的名称、行业、总部、短描述、spin-off、阶段。**不抓公司主页，不发送目录原始HTML，不访问学习私有证据卷**。
- 既有公司详情手动refresh、Article后的best-effort refresh、其它CLI调用不被本协议自动接管；这些调用仍有单独的恢复/覆盖风险。不要把这个job的防重证明推广到全部公司分析或所有实际同名实体。

## 运行路径与上限

```text
Admin Scan All Now / daily startup-discovery
  → crawl队列：scan_startup_sources
  → 每来源：安全取数 → 新Company + queued job同事务提交
  → 消息只带job ID，明确llm队列
  → app.llm.startup_tasks.analyze
  → 当前输入检查 → 持久running认领 → 全局账本准入/供应商调用
  → 再核输入/期限 → 原子保存初始分析、revision和succeeded状态
```

- 目录读取共用每来源 `SafeFetcher`：仅配置URL的host，30秒/6请求，单响应/传输512KiB、总响应/传输2MiB；遵守现有IP、TLS、robots、重定向门禁，拒绝后无直连fallback。
- 目录详情事实在业务写事务外准备：只对本次最多20个新slug/alias候选、同配置host的member-directory链接取postcode/city/entity type；每详情有独立15秒SafeFetcher边界，不属于列表30秒共享预算，不证明整个扫描的总时限。写事务重查来源代次和去重；非Isère邮编不自动标为Grenoble。结果仍pending，不构成真实性/发布批准。
- SharePoint只处理一个排序后分页参数及最多4个附加页；目录最多4个附加页，两种路径共享取数预算。分页停止/失败可能只保留之前已取得的页面，**不是完整目录覆盖证明**。
- 每轮最多50来源，按旧扫描时间/ID排序；每源提取结果最多1000项、创建最多20家公司。完整别名扫描最多4096个SQL非NULL行（JSON null兼容为空；也计入扫描上限），超限不采样式认证去重。大量永久失败来源仍可能影响后续来源调度；没有统一due调度或每源任务fan-out。
- 仍使用旧BeautifulSoup目录启发式，不是M1质量门禁或受监督解析/OS沙箱。取数上限不覆盖DB、解析和整轮全部来源的总耗时。
- queued最多24小时；认领后的逻辑窗口至多180秒且不得越过原queued期限。绑定时间先存整秒，不能靠DB时间精度延长。
- 每job最多一个被认领的执行流程，公开请求最多3个供应商尝试、同配置最多一次；每次付费重新核对当前配置与完整价格/计费token上界。普通 `company_analysis` 路由与有效缓存仍兼容（无显式assignment时沿用insight路由）；缓存前也检查持久身份/有效消息。
- 这是普通公司分析的**全局LLM预算**，不是额外获得学习会话的$0.20/$1预算。全局预算0仍表示取消全局金额帽，不代表计费审核或无限免费调用。
- 所有预留关联 `LLMReservation.startup_analysis_id`。已知用量的坏输出可有限fallback；费用/token未知、对账错误或当前配置变更会停止，不把不确定结果当免费失败。成本与公司业务写入独立提交，无业务写锁跨模型调用。

## 认领、撤权与恢复

状态为 `queued / running / succeeded / blocked / stale`。

- `startup-analysis.v2`同时绑定审核状态、entity type、postcode/city/local site；旧v1任务不自动重签。source URL/type/启用状态的ORM改变原子递增来源代次；公司模型输入/人工分析及上述审核字段的ORM改变递增公司代次。连改回原值的ABA也不复用旧输入。
- job冻结来源/公司ID、输入、代次、协议/提示/契约版本、创建/到期时间及hash。正常统计更新不撤权；禁用/删除来源、公司变更或已有人写入分析，使当前执行不能继续付费/覆盖。
- 认领身份在COMMIT前生成；异常关闭也核对身份，不因重复消息或丢失ACK中止另一执行者。已认领/终态不因新扫描或消息重投重新付款。
- 准入及最终应用在锁定读取后再次检查期限；随后SQL写入/COMMIT及SDK仍可能阻塞。这些是**检查点，不是HTTP/DB硬deadline、完整lease或远端取消机制**。
- beat每60秒将 `app.llm.startup_tasks.recover` 发往llm队列；每次最多处理50个已到期条目。queued按持久 `next_dispatch_at` 排序重派，下一次资格至少120秒后（整秒保守留裕量）。先提交派发间隔，再发消息；publication或其确认丢失仍保留意图，不能保证即刻送达。
- 过期running只转blocked，不接管或重新调用模型。进程死亡/过期不释放reserved/unknown金额；迟到成功照样记账，但不能应用到公司。
- owned执行失败最多增加自己的公司失败次数一次；旧失败不清零。撤权/输入失效不是凭空计作新的供应商失败。过期恢复不推断到底完成过多少调用。
- 此切片无终态重开/自动付费重试按钮。修复配置或服务后不会把blocked自动恢复；先核费用和人工输入，不能通过改状态/删job“修复”。旧手动refresh是不同流程，不具备这里的完整保护。

## Admin观察

`/admin/startup-sources` 显示最近50个job；使用行链接或LLM账本的Discovery job链接，可用 `?analysis_id=UUID` 精确查看更早job。不接受状态写入。所有该区域响应no-store，非Admin不能查看。

列表状态是**历史执行结果**，不认证当前公司数据、独立验证或发布许可。显示名称需通过绑定校验并限制长度；损坏记录只显示Input unavailable。DB不可读返回固定503，不打印SQL/参数/私有异常。原目录配置列表仍是既有管理界面。

`/admin/llm-usage`查看金额和保留预留；不能用job成功/失败替代供应商终账。对账仍遵循[全局账本操作](llm-budget-accounting.md)，保留原费用证据，要求停止执行和最终账单的明确确认。

## 数据、兼容与未完成验收

当前唯一head为`c7f21a9d680e`（合并生态b3与M3 b5，merge本身不改数据）。以下是job表原始Migration `a2f6d9b3107c`，父 `f8b64d2c901e`：一张job表、Company/StartupSource两个默认0代次、reservation可空关联和索引。旧公司、失败计数、目录启用状态、未知费用原样保留，不生成旧job、不授权付费。业务行删除使FK置NULL，job原始输入与费用保留；job本身无删除API。降级拒绝删除记录。

Job保留有界输入元数据和hash，而不是原始目录快照。**24小时是排队有效期，不是物理删除期限。** 不自动清理这些审计；名称/描述/公司网站等仍可能敏感，不公开存储副本或日志。hash不是签名，无法证明模型真正接收/未留存，也不抵御一致篡改/整库回滚。该流程未补齐所有模型暴露历史，不能扩大已有学习holdout的独立性声明。

现有LLM worker消费新增任务；没有增加这个队列的CPU/RAM容量或新的task级软硬限制。它不使用专用learning worker。仍需实际MySQL迁移/行锁/精度/FK、Redis/broker/ACK、prefork软硬杀/重启、积压与全局预算竞争/容量门禁；SQLite/时间和COMMIT故障模拟不能代替。

用户已授权提交部署，但门禁未满足，生产保持原版。上线先审核计费上界、备份、验证实际候选，并协调停下全部旧付费调用方/旧扫描器再迁移和切换。旧程序及bulk SQL不递增这里的ORM代次，也可能再次同步扫描全表/重置失败；保留新表并不使旧代码回滚安全。原Admin扫描消息本身不是durable outbox，只有新公司/job提交后才具有这里的持久意图。

相关：[M3计划](../superpowers/plans/2026-09-18-m3-bounded-learning.md)、[本轮审计](../audits/2026-09-19-m34b-startup-analysis.md)、[学习worker](learning-worker.md)、[worker容量](worker-capacity.md)。
