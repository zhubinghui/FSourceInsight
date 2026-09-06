# Progress

## 本轮
- 已读取用户流程图和项目级约束，确认初始 Git 基线与目录结构。
- 已向用户说明先审查与设计、再确认关键决策的执行方式。
- 已完成子代理能力发现；计划只读审查并行、主代理汇总和本地验证。
- 已运行 planning-with-files session-catchup，没有返回待恢复上下文。
- 主会话已初步阅读爬虫 base/rss/html/tasks/registry/source model、测试 fixture 与依赖配置，尚未执行测试。
- 并行审查工作流 9a58ff2f-f6ae-4ffc-ac1b-593d81f7b190 的 3 个子启动全部失败：原生后台依赖 @earendil-works/pi-server、pi-server/unix、pi-client/unix 不可用。工作流包装层 completed 不能视为审查成功；子状态均 failed。
- 已先更新 task_plan.md 记录偏差并暂停，不切换执行模式。待用户批准主会话直接继续或修复子代理依赖后重试。
- 用户已批准主会话直接继续，已先更新计划，后续不再使用子代理。
- 已阅读 app factory、LLM 全链路、Celery、登录/订阅/企业/API、主要模型及官网抓取；发现匿名改密码高优先级风险并已提示用户。
- 已审查全部后端模块、25 个站点爬虫文件（29 个注册类）、35 个新闻 seed 配置、21 个发现源配置、部署及迁移路径；模板全体扫描与编译 40 个。
- 本地隔离依赖安装成功；pytest --collect-only exit 5（0 tests）；103 个 Python AST 与 shell bash -n 通过。
- 18/18 缺陷探针成功复现；额外测得 25 家企业地图 28 次 SQL，其中 26 次重复分组查询；带 +02:00 时间丢 UTC 归一化；同一周不同 sentiment 分裂为不同日期桶。
- 13 个迁移可生成 MySQL 离线 SQL，但 task_type 仍为旧 Enum，缺 digest/insight。未连接真实 MySQL。
- 已完成 docs/audits/2026-09-06-project-audit.md、2026-09-06-validation.md、2026-09-06/probes.py 和 probe-results.json。
- 已完成 docs/superpowers/specs/2026-09-06-dynamic-crawler-agent-design.md 和 plans/2026-09-06-dynamic-crawler-agent.md。
- 最终复核：保存后的探针重新执行 exit 0，18 项缺陷复现结果与已存 JSON 一致；文档本地链接/引用行号范围/代码块/空白检查通过。
- Git 仍 master@bf9cc61，无 tracked/staged diff；仅新增本轮审查/设计/计划资料。无业务修改、提交、推送、生产访问。
- 审查轮完成。随后用户已确认默认建议并授权开始实施。

## 实施首批（2026-09-06）
- 先更新设计/计划确认 5 项默认决策；始终主会话单写者，无子代理、生产访问、真实爬取/SMTP/LLM、提交或推送。
- 0.1：先复现匿名改管理员密码，再修登录/本人归属、旧密码校验、输入验证、next 安全校验、凭证版本会话失效；29 项 HTTP 回归通过。
- 0.2：文章详情 XSS 用例先失败，再转义后引入固定 Markdown 标签；回归通过。
- 0.3：base+prod 端口继承用例先失败、Caddy 组合原本通过；两层统一 !override，新增 deny-by-default .dockerignore、明确 Dockerfile COPY、新建 GitHub 离线测试流程；3 项本地测试通过，CI 远端未运行。
- 0.4：迁移测试先失败缺少 ALTER；新增 expand-only c821b4f7d901，MySQL 全链路离线 SQL 通过。无可用 Docker daemon/mysqld，真实迁移仍阻塞。
- 0.6：批内去重、savepoint 冲突隔离、异常 rollback、独立日志事务、空 RSS/未知空结果区分、HTTP 429/5xx 重试与 403 不重试、URL/UTC 修复；13 项通过。
- 0.7：两类邮件模板路径与高亮-only 正文/preview 修复；SMTP 仅 mock，失败记录回归通过。
- 测试环境：临时 venv，独立 SQLite 文件而非共享内存连接；socket/DNS 阻断。测试 fixture 修正跨请求 Flask-Login/CSRF 的 g 缓存泄漏；测试数据补齐必填 source.category；HTML 断言改为 DOM 文本而非空白敏感字符串。
- SQLite legacy SAVEPOINT 的批次部分提交在新增晚期失败测试中复现，已先记录计划偏差，再显式 BEGIN 修复；未用 SQLite 冒充 MySQL 并发验证。
- 一次多处 edit 因重复 oldText 拒绝（无部分改动），改用 mysql/redis 上下文后成功。
- 最近整套命令：`env -i PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin HOME=... PYTHONDONTWRITEBYTECODE=1 /tmp/fsource-audit-1XQuAg/venv/bin/python -m pytest tests/ -q --disable-warnings -p no:cacheprovider` → 49 passed（251 条主要为既有 datetime.utcnow/legacy Query 警告），无 skip。
- 最终复核：110 个 Python AST、40 个 Jinja 模板、shell 语法、文档链接/围栏、git diff --check、flake8 E9/F63/F7/F82 均通过。当前 Docker context 被动检查也指向不可用本地 Unix socket；未连接 daemon。
- 首批实现文档：docs/audits/2026-09-06-m0-implementation.md。18 个原有 tracked 文件修改及新增测试/迁移/构建/CI/文档；HEAD 未变、无暂存修改。
- 下一项是 0.5 LLM 事务/幂等/严格结构化输出/缓存与显式路由。M0 总状态保持进行中，M1–M4 尚未实施；该首批交付时尚未部署。

## OVH 验证/发布授权后
- 用户允许登录 OVH 验证 SQL，验证后提交部署；后续明确 TDD，规则已加入 CLAUDE.md。新维护计划 2026-09-06-ovh-m0-validation-deploy.md，不重跑旧安装/dump流程。
- IP SSH 首次 publickey 拒绝；被动配置发现 france-vps 指向同一服务器和专用身份，按别名成功登录，无私钥/密钥值读取。
- 生产 master@bf9cc61，干净；MySQL8.0.46/rev fd3132082a6b，task_type 已 VARCHAR(50)，只读 model diff=0。先记录计划差异再调整测试。
- 独立 internal network、专用卷/容器（fsi-m0-20260906100910），测试目录 /home/ubuntu/fsi-m0-verify.EYVS00；限资源，无业务数据/网络/凭据接入。
- 新增 MySQL unittest：已正确VARCHAR不ALTER先red后green，修改c821迁移在线类型检查；7项真实MySQL迁移/数据保持/回填/事务/并发测试全通过。本地49 passed+7远程专用skipped；CI增加独立MySQL job。
- 初次类型字符串断言因数据库返回COLLATE信息失败，改断言类型/长度/nullable，model diff 原本通过；不改变迁移语义掩盖差异。
- 源tar跨系统xattr提示不影响结果，后续使用无扩展元数据归档。
- 待提交/备份/构建候选再验证/受控部署/最终冒烟，尚未改变生产业务库和运行服务。
