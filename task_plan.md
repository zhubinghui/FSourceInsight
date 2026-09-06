# 全项目审查与动态爬虫 Agent 改造

## 目标与范围
- 用户要求：全量检查当前项目、提出具体优化点，并依照给定流程图设计动态 Agent 爬虫改造。
- 基线：master，bf9cc61b94556e00218af267db82bf42a3b80eef；初始工作区干净。
- 审查与方案已完成。用户已同意 5 项默认建议并授权开始实施：V1 仅新闻、schema 人工批准、元数据可保存但仅标题不生成深度洞察、隔离公开页面渲染、3 轮/US$0.20 每次/US$1 每日且受总预算约束。
- 最新授权：允许登录 OVH 部署环境验证 SQL，验证通过后提交并部署当前首批 M0 修复；后续开发明确采用 TDD。先只读盘点，在隔离 MySQL 测试实例/库用合成数据验收，再备份与受控部署。仍不读取/输出 .env 密钥或备份内容、不触发额外真实爬取/付费 LLM/邮件，不干扰同机 ai-router。

## 阶段
1. [complete] 核对项目结构、现有行为和用户流程图。
2. [complete] 主会话完成全部后端模块/爬虫/模型及关键部署脚本人工审查，模板全体静态扫描/编译；不声称前端视觉全覆盖。
3. [complete] 临时 Python 3.12 环境验证：18 项缺陷探针复现；额外 ORM/SQL 查询与时间探针；103 个 Python AST、40 个模板编译、shell 语法通过；Compose 合并与 13 个 MySQL 迁移离线 SQL 核对。原有 pytest 为 0 tests (exit 5)，未做生产/MySQL 实机/真实爬取/真实 LLM/浏览器验证。
4. [complete] 已输出 docs/audits 审查/验证报告与离线探针，docs/superpowers 下架构草案和分阶段实施计划。
5. [complete] 已复跑保存后的 18 项探针并核对结果一致，文档链接/行号范围/代码块检查通过；确认 Git 基线未变、业务代码无修改。报告明确未验证范围，实施待用户确认范围/发布/内容/浏览器/预算。

## 实施阶段（用户已授权，不使用子代理）
6. [in_progress] M0 安全与可靠性：0.1 身份/归属、0.2 XSS、0.3 构建/Compose、0.6 爬虫基础、0.7 邮件模板已通过本地回归。0.4 已新增迁移并离线验证，MySQL 实机阻塞；0.5 LLM 事务/契约/路由待实现。当前正式测试 49 passed，M0 不标为全部完成。
7. [pending] M1 确定性 schema 引擎、Safe Fetch、质量门禁。
8. [pending] M2 配置版本/审批、认领/可靠交付、调度。
9. [pending] M3 有界学习、预算账本与候选验证。
10. [pending] M4 浏览器隔离及小范围上线前验证（上线/真实访问另行授权）。

## OVH SQL 验证与首批发布（新授权）
11. [complete] SSH france-vps 成功，远端工作区干净且 bf9cc61；生产MySQL8.0.46已为目标VARCHAR，readonly model diff=0。
12. [complete] 独立 MySQL8.0.46/合成数据 7项通过，包含空库/旧Enum/已有VARCHAR/JSON和counter/回滚/并发；新增迁移跳过重复ALTER，先red后green。
13. [in_progress] 核对 diff、提交/推送当前批次；远端备份、保留旧镜像/代码，构建候选后再验证；只更新应用服务和前向迁移，不重建基础服务。
14. [pending] 发布后健康/权限/端口/任务注册只读冒烟，记录 ref、证据、回滚点；M0.5 及 Agent 仍另行按 TDD 继续。

## 已批准的验证接口
- HTTP：登录、本人偏好/订阅、跨用户访问、文章详情、邮件预览。
- 爬虫：BaseCrawler.run / RSS、HTML fetch_articles 的规范化输出、持久化结果和任务重试。
- LLM：公共任务方法 / process_article_llm，验证输出契约、可重试数据和用量事务。
- 运维：Compose 合并配置、Docker 复制范围、Alembic 迁移至 head。
- 采用用户已批准计划中的这些接口做测试，不为内部实现细节建立新验收接口。

## 关键设计约束
- 确定性爬取为主路径，Agent 仅用于发现/修复配置，不在每篇文章上无界运行。
- 源读取 → 已有 schema/通用 RSS-HTML-渲染 → 质量门禁 → 格式化结果，或有界 Agent 学习 → 验证 → 固化/人工复核。
- Agent 输出声明式 schema，不执行模型生成的任意 Python/JS，不把网页内容当指令。
- 全面检查不等于生产实测，报告中区分代码证据、可执行验证和待验证推断。

## 偏差与错误
- 实施期：Docker socket 不存在可用目标、PATH 无 mysqld；MySQL 8 空库/旧数据迁移和并发行为仍为上线阻塞，当前只有 MySQL 离线 DDL 与 SQLite 集成测试证据。
- SQLite legacy SAVEPOINT 提前提交在“第二条插入失败”回归中复现；已先更新实施计划，再在 SQLite 路径显式 BEGIN，13 项爬虫测试通过。
- 0.5 需先消除业务提前 flush，再独立写用量账本，避免父行 FK/SQLite 写锁；不机械替换 Session。先独立完成 0.6/0.7，LLM 代码本轮未改。
- 本地 pytest --collect-only 返回 exit 5：仓库无实际测试函数，不是测试通过。替代验证为离线缺陷探针、AST/shell 检查、Compose 配置合并和迁移离线 SQL；不得声称完整集成测试通过。
- 本机 Python 3.14/3.12 均无 Flask/Celery/pytest 等项目依赖，无法直接执行 pytest。已先调整验证计划：临时 Python 3.12 venv，依赖版本在验证记录中注明；不将新解析版本视为生产版本。
- 工作流 9a58ff2f-f6ae-4ffc-ac1b-593d81f7b190 的三个子代理均启动失败（web-security、llm-data、ops-tests）。错误：Background children require pi installed as the npm package (@earendil-works/pi-coding-agent) with its dependencies; /opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent does not provide @earendil-works/pi-server, @earendil-works/pi-server/unix, @earendil-works/pi-client/unix, so the async runner cannot create child sessions. A standalone pi binary cannot run background children.
- 子启动标识：78a0873a-dde3-40d2-b691-e00cfc6f212d / 008349cc-0d55-4312-bbe3-a78d4ed20dc9 / 030c21a4-ac3a-4ed2-93fe-3699046b62c3；返回 child run=unavailable, status=failed，无审查产物。
- 首次失败后已暂停并征求用户同意。用户现已明确批准“不使用子代理，直接进行”；本轮按此授权改由主会话直接审查，不修复 Pi、不调用子代理/其他 CLI。业务代码仍不修改，先交付审查与架构方案。
