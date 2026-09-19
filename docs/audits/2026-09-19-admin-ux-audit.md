# Admin 管理后台：逻辑与 UX 现状整理（2026-09-19）

状态：**静态只读审计**（读了全部 admin 视图和模板，未运行应用/浏览器），基于当前工作区（含未提交改动）。
`app/web/views/admin.py` 在审计期间仍在变动，行号引用前请复核。

## 1. 结构概览

- 蓝图：`admin_bp` → `/admin`；嵌套 `crawl_config_bp`（`/sources/<id>/crawl-config`，其下 policy / capture / learning）和 `llm_budget_bp`。
- 权限：唯一的 `before_request` 守卫（`admin.py:30-35`，login + `is_admin`）。单一布尔角色；付费/不可逆操作与"看日志"同权限。
  另有三个管理员动作挂在公开蓝图 `company.py:172-268`（update-sector、AI Refresh、edit-analysis），各自内联检查。
- CSRF：全局开启；新蓝图有严格字段白名单，旧 `admin.py` 路由无任何校验。
- HTMX 已加载但后台**没有任何 `hx-` 属性**，所有操作都是整页 POST → redirect → flash。
- 错误页：只有 404/500 且用公开布局；crawl-config/learning/budget 的 `abort(400/409/503)` 是裸 Werkzeug 页，表单输入丢失。
- 视觉：三代样式并存（旧 Bootstrap / 新 `card-fs` 设计 / crawl-config 系列的裸 HTML）。

侧边栏（`admin_base.html:124-177`）：Overview（Dashboard, Settings）· Content（Sector Groups, Ecosystem Sources, Sources, Companies, Merge Companies, Crawl Logs）· AI/LLM（Task Routing, Model Config, Usage & Cost）· Users & Email。

**没有后台入口的领域**：文章（列表/搜索/重处理/高亮覆盖）、分类、订阅者、队列深度/健康（只有公开未鉴权的 `/health/detail`）、熔断器复位、跨源 learning 会话列表、设置审计日志。

**侧边栏到不了的页面**：整棵 crawl-config 树（只能从 Sources 行内按钮进）、email 预览、失败的 crawl 详情（仅 `articles_new>0` 才有链接，错误被截断到 80 字符）、公司的 AI Refresh/分析编辑（只在公开页）。

**命名不一致**：Ecosystem Sources / Startup Sources / Discovery Sources；Model Config / LLM Configuration；candidate / version / recipe / crawl schema；capture / sampling history / capture ledger；模型叫 `CrawlRepairSession` 而 UI 叫 learning。UI 全英文，无 i18n。

## 2. 主要工作流的卡点

| 流程 | 现状问题 |
|---|---|
| 新增新闻源 | 需要猜 slug / feed type / `crawler_class`（自由文本 Python 路径）；允许保存永远爬不了的 `html_scrape` 源；无"测试"步骤；结果要去另一个菜单手动刷新；编辑/开关会**静默**使所有 preview/policy 失效；源不能删除 |
| crawl config → policy → preview → evidence → learning → validation | 12+ 次页面跳转，无步骤条/状态总览；recipe 和 policy 表单不回填；preview 同步阻塞约 20s 无 loading；决策页把样本埋在 7 段免责声明下；需要理解 generation / policy_generation / capture ledger / stale / 各种状态词；learning 页不自动刷新，显示原始 JSON 和 UUID |
| 公司/生态 | 列表无搜索/筛选，N+1 计数；sector 三处可改且是自由文本，与 Sector Groups 关系不可见；合并页是两个装下全部公司的 select，合并会丢 sector/描述/分析/情感；改名改 slug 无重定向；自动创建的公司没有审核队列 |
| Startup discovery | 只能全局扫描；`companies_found` 只有数字没有列表；发现即上地图无审核；job 表显示原始 state/reason/source_id |
| LLM 配置/预算 | 分散在 4 页；列表不显示 role/priority/价格/计费上限，**因上限为 NULL 被拒付的配置无任何提示**；`billing_reviewed` 每次编辑都要重勾否则裸 400；对账是行内不可逆表单、无确认、上限 100 行无分页；routing 页文案与 reservation 模型矛盾 |
| 监控 | 分散在 Dashboard / Crawl Logs / Email Logs / Usage / `/health/detail` / docker logs；无队列深度、worker/beat 状态、陈旧源列表、LLM 失败率；文章级 pipeline 失败不可见 |

## 3. 问题清单

### P0 — 有缺陷或不安全
1. **删除确认可被绕过 + 存储型 XSS**：`companies.html:36`、`sector_groups.html:43`、`startup_sources.html:65`、`users.html:55` 把名称插进内联 JS `confirm('…')`。含撇号的名称（法语常见，如 L'Oréal）会破坏处理器；公司名来自 NER/抓取文本，可构造。改用 `|tojson` 或 data 属性。
2. **"Daily Crawl Time" 设置会静默停掉每日爬取**：beat 固定 01:00 Paris（`celery_app.py:41`），任务只在配置小时 ±1h 内执行（`crawlers/tasks.py:62-75`）；设成其他时间则永不运行，且无服务端校验、描述写 UTC 而 UI 给时区。
3. 删除有用量历史的 LLM config → 500（`LLMUsageLog/LLMReservation.config_id` NOT NULL 无级联）。
4. 删除创建过 candidate/policy/capture/learning/对账记录的用户 → 500。
5. 管理员可把自己设为 inactive 自锁；无"最后一个管理员"保护。
6. 用户新建/编辑无服务端密码策略。
7. 付费/不可逆操作无确认：Start bounded learning、Record final charge、Revoke、Send Digest Now、Crawl All Now。
8. 公司合并有损且无预览/撤销（`admin.py:268-292`）。

### P1 — 主要摩擦
crawl-config 流程过长且泄漏内部术语 · 无后台风格错误页、校验失败丢输入 · LLM config 列表隐藏计费状态 · Usage 页混合分析与对账账本 · 无文章管理与 pipeline 可见性，`/health/detail` 公开 · crawl logs 无筛选、失败无详情、按时间窗推断文章 · 公司无搜索/筛选、管理入口分裂 · discovery 无审核 · 源表单允许不可爬配置 · 旧路由对非法整数/唯一冲突返回 500 · learning 页不轮询 · 大片区域无测试（companies CRUD/merge、sector groups、users、settings、logs、digest、llm-config new/delete/toggle、非管理员访问矩阵）。

### P2 — 打磨
三套视觉风格 · 面包屑不一致 · 6 张表缺 `table-responsive` · 侧边栏分组/命名/子串匹配高亮 · 死模板 `edit_company.html`、孤儿路由 `toggle_user_admin` · Logout 是 GET · 时间戳为无时区 UTC 且标注不一 · `days`/reprocess limit/crawl_log_detail 查询无上界 · 分页/表格/确认/状态徽章无共享宏。

### 代码结构
`admin.py` 926 行含 10 个不相关领域；`crawl_config.preview` 105 行把锁、策略解析、引擎运行、证据保存、账本 CAS 全放在视图里；合并算法、O(N) 去重扫描在视图里；严格表单校验手写 8 次；Flask-WTF 只用于 CSRF。

## 4. 需求（建议方向）

1. **先修 P0**（每项先写失败的 admin HTTP 回归测试，符合 CLAUDE.md 的 TDD 约定）。
2. **信息架构重组**：Monitoring（Dashboard、Crawl Logs、Queue/Health、Email Logs）/ Sources（News、Ecosystem discovery、每源 Crawl config 作为子页 + 步骤条）/ Ecosystem（Companies、Review queue、Sector Groups；Merge 变成列表动作）/ Content（Articles）/ LLM（Routing、Configs+billing 状态、Usage、Ledger 独立页）/ System（Users、Settings）。统一术语表。
3. **统一组件**：一个布局、共享宏（表格+分页+筛选、确认对话框、状态徽章、表单错误回显）、后台风格的 400/403/409/503 页。
4. **crawl-config 向导化**：状态总览卡 + 步骤条，表单回填，人话状态 + 可展开的技术细节，preview 异步/loading，learning 页轮询（HTMX）。
5. **公司管理集中到 /admin**：搜索/筛选（auto-created、Grenoble、无 sector、无分析）、审核队列、重复建议、字段级合并预览、AI Refresh 状态。与 ecosystem 校验文档的 R2/R4 共用模型改动。
6. **监控页**：队列深度、worker/beat、陈旧源、LLM 失败率、未结算 reservation、预算进度；`/health/detail` 加鉴权。
7. **拆分 `admin.py`** 为按领域的蓝图 + service 层，补齐缺失的 HTTP 测试和非管理员访问矩阵。
