# M0.5：LLM 可靠性本地实施记录

- 基线：`master@d91863fcc0f0a9cb3e6d0302ed834847c2ee4d5e`。
- 本地开发轮状态：代码已实现、本地回归通过；当时 MySQL 实机验收待运行。
- **后续更新：用户确认继续后，隔离MySQL两轮10/10实跑通过，见 [实机验收记录](2026-09-06-m05-mysql-validation.md)。M0.5仍未提交/部署。**
- 本地开发轮主会话单写者、TDD、未连接OVH；后续隔离验收未读取密钥/备份、未触发真实爬取、付费模型或邮件。
- 依据：[实施计划 0.5](../superpowers/plans/2026-09-06-dynamic-crawler-agent.md)。首批生产版本仍见 [OVH 发布记录](2026-09-06-ovh-sql-validation.md)。

## 实现与边界

### 1. 独立用量、原子业务应用

- `app/llm/client.py`：配置和预算读取使用独立 Session，不 autoflush 调用者；每次有响应的尝试独立记录 tokens/费用，包括非法 JSON/非正常结束。日志仅保存异常类型，不保存模型正文。
- 账本写失败会中止，不冒充供应商失败并立即再次付费。没有返回 tokens/价格时成本仍可为 NULL，不能据此声称费用完整或硬预算。
- `app/llm/pipeline.py`：短只读快照 → 无业务写入的模型结果收集 → 一次事务应用 Article/Company/关系；MySQL 应用阶段锁定 Article 并复查 processed/input/version。
- Celery 与 `scripts/run_llm_process.py` 共用同一条管线。关系去重，历史部分重试可恢复，人工公司情感不被覆盖；force 失败保留旧结果。只有标题/空白/空 HTML 正文不生成深度洞察，无正文重新处理时清理过期 digest（未使用 skip-translate 时）。
- Article 单一 provider/model 字段记录实际翻译路由（skip-translate 时为摘要）；各步骤完整归属以用量记录为准。缓存命中不伪造付费记录。
- 企业刷新仍在提交后 best-effort 执行；异常先 rollback，防止污染后续刷新。不是 durable outbox。

### 2. 严格结果、有限 fallback

- `app/llm/contracts.py`：NER/sentiment/classify/company_analysis 的对象结构、必需字段、类型、枚举、数值范围、日期、数组/字符串长度检查；允许 fenced JSON，拒绝重复 key、NaN、空文本及错误根类型。
- 合法 `companies: []`、空分类和中性情感保留，不将错误响应“修复”为正常空值。
- 仅接受 LiteLLM 规范化 `finish_reason=stop`；length/content_filter/tool_calls 不作为完整结果。
- 一次公共调用每配置最多一次，最多 **3 次供应商调用**，每次重新检查已花费用；明确 `num_retries=0`、SDK 请求 timeout=60 秒。不是文章全链路硬截止时间，也不是跨 worker 的硬预算预留。

### 3. 缓存与路由

- `llm_cache:v2:`：完整有效 messages（含标题、语言、公司资料、recent_news、官网实际文本）、prompt/contract 版本、config ID、provider/model/endpoint、temperature/max_tokens、响应格式；不含密钥。
- 缓存再次验证，损坏则 miss；响应缓存 Redis I/O 故障可降级。此结论不包含断路器 Redis 故障：该路径仍待硬化。
- fallback 结果仅属于实际 fallback 配置的缓存，不污染恢复后的主模型；temperature=0 正确保留。
- `app/llm/routing.py` 与 Admin 共享顺序：assigned → default；各组内 primary → fallback → priority（值小者先）→ input cost → ID。开放断路器连 default 也跳过。
- `company_analysis` 单独计账/校验，未显式分配才继承 insight。Admin 矩阵明确显示“配置顺序”，不是实时执行保证。
- 新 seed：DeepSeek 主批量任务；mini 主 NER/classify/insight/company_analysis；nano fallback（补 digest）。**已有配置一律 skip，不静默覆盖管理员选型。**

### 4. 迁移与上线注意

- 新 head：`d472ac9e6102`（前驱 `c821b4f7d901`），只增加 `llm_config.role VARCHAR(16) NOT NULL DEFAULT 'primary'` 和 `priority INTEGER NOT NULL DEFAULT 100`。
- 保留已有 tasks/model/active/default/用量历史；兼容默认值保留原成本/ID 排序，不会自动把既有 nano/DeepSeek 改成 mini。
- MySQL 将保留字 `role` 正确引用为反引号；SQLite 增量迁移与 MySQL 离线 DDL 已验证，不等于 MySQL ALTER 实测。
- 未来部署必须先验收隔离 MySQL、备份、执行新增迁移，再启动新应用。旧代码回滚可保留扩展列，downgrade 拒绝丢弃管理员选型。
- v2 缓存不复用旧键，首次发布会冷启动；严格契约也可能增加供应商失败率。后续发布要监测预算/失败率，不批量强制重算历史文章。

## TDD 证据

| 垂直切片 | 实现前失败 | 修复后行为 |
|---|---|---|
| 用量事务 | 2 项均提前提交文章 | 业务 rollback 与独立费用共存 |
| 管线晚期失败 | 独立账本被旧 company flush 阻塞，SQLite `database is locked` | 收集阶段无写入；12 步中断重试及最终 SQL 写失败回滚 |
| JSON | 16 failed / 3 原本合法通过 | 错误付费记录保留、无成功缓存 |
| fallback | 两供应商来回调用 11 次、预算未复查 | 有界调用、逐次预算、账本失败不 fallback |
| 缓存 | 17 failed / 2 原本通过 | 标题/所有企业输入/版本/参数/供应商完整隔离 |
| 路由 | 6 failed / 1 原本通过 | 明确主备、优先级，Admin 保存和非法值拒绝 |
| 迁移 | 缺新列/DDL | SQLite 历史记录保持、MySQL 生成扩展 SQL |
| 归属/metadata/seed | 3 项失败 | 实际 fallback 归属、无正文无深度洞察、新 seed 符合主备 |
| SDK/结束原因 | 4 项失败 | 禁止隐藏重试，截断/拒绝不缓存 |
| 空正文/过期 digest | 2+1 项失败 | 空白/空 HTML 同属无正文，清理旧翻译正文 |

Fixture 修正不算业务 red：Category `name_fr` 改为实际字段 `name` 后才得到真实锁失败；MySQL 离线断言补上 `role` 的合法标识符引用。CLI 的旧私有 helper 导入在共享管线接入中已消除。两次非唯一 oldText 编辑被工具拒绝，无部分改动，改唯一上下文后继续。

## 验证

```bash
env -i PATH='/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin' \
  HOME="$HOME" PYTHONDONTWRITEBYTECODE=1 \
  /tmp/fsource-audit-1XQuAg/venv/bin/python -m pytest tests/ \
  -q --disable-warnings -p no:cacheprovider
```

- 本地：**131 passed，10 skipped**。其中 LLM 77 项、新增迁移 2 项，既有回归 52 项。网络/DNS阻断，provider/cache为内存替身，使用独立 SQLite 文件连接而非共享内存。
- 123 Python AST、40 Jinja 模板编译、shell `bash -n`、flake8 `E9,F63,F7,F82`、`git diff --check` 通过。
- `tests/integration/test_mysql_m0.py` 现有 **10 项**：原 7 项迁移/爬虫测试适配新 head，旧 schema 用明确旧列 SQL 建数据；新增独立用量/FK、晚期应用失败、重复消费者最终仅应用一次 3 项。
- **本地开发轮这10项均skipped**；随后已在隔离MySQL8.0.46两轮实跑10/10通过，详见上述后续记录。既有CI MySQL job会运行这些用例，但尚未提交/推送，不能声称新代码CI已通过。

## 剩余风险 / 下一步

1. 后续隔离MySQL已完成10项实跑，model diff=0、父行FK、竞争消费者及回滚均通过；未来重新构建的发布候选镜像仍需复验。fixture仅接受 `m0-mysql/fsource_m0_validation` 和 `FSI_DESTRUCTIVE_TESTS=1`，严禁指向生产。
2. 并发消费者仍可能重复付费；失败/崩溃后用量持久化之前的窗口、未知费用、硬预算、lease/outbox/reconciliation 留给 M2/M3。
3. 断路器 Redis 异常与半开单探针未修；公司别名全表扫描、不同文章并发创建同 slug 仍可导致整事务重试，而不是本切片的无冲突认领保证。
4. Safe Fetch/SSRF、官网 URL、正文完整度/质量门禁仍在 M1；“非空正文”不代表已经确认全文。
5. M0已批准基础切片的代码/验收已补齐；M0.5尚未提交/部署，M1–M4未实现/上线。仍有上述后续可靠性和网络安全工作，不将本批验收视作全项目风险消除。
