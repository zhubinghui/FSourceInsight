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

## M0.5 本地开发（首批发布后，进行中）
- HEAD d91863f，未提交/部署；本轮不访问 OVH，沿用离线环境和 mock provider/cache。
- 用量回归先 2 failed（成功和失败调用均提前提交文章），独立配置/预算读取和用量 Session 后 2 passed。
- pipeline 晚期失败回归真实复现 SQLite `database is locked`：单独换账本仍被旧 company flush 阻塞。新增 pipeline.py，只读快照→收集→独立事务应用；Celery/CLI 共用，关系去重、已有结果在 force 失败时保留。12 个模型调用阶段逐项中断重试及最终分类写入失败回滚通过。
- JSON 契约先 16 failed/3 passed；严格对象/字段/类型/范围/日期/空文本校验后通过，格式错误照样记录 token/费用，绝不伪造空结果缓存。公司分析独立 task_type。
- fallback 两项先失败（11次循环、预算未复查），加入 visited/最多3次/每次预算检查后通过；账本故障不重试付费。当前 LLM 子集 39 passed；尚待缓存完整性、显式路由和全套/迁移验证。
- 工具/fixture 小错误：两次非唯一 oldText edit 被拒绝且无部分改动，改唯一上下文；Category fixture 的 name_fr 应为 name，修正后才得到真实锁失败。CLI 暂时引用被删除私有 helper 的 ImportError 已用共享 pipeline 修复并回归。MySQL离线DDL对保留字role加反引号，断言修正，不修改合法DDL。
- 缓存先17 failed/2 passed，再改完整有效messages/版本/config/参数和实际fallback归属；坏缓存/响应缓存Redis故障允许miss，temperature=0保留。路由先6 failed/1 passed，再共享primary→fallback/priority/cost/id，Admin表单、矩阵与新seed同步，旧配置不覆盖。
- 新增迁移d472只加role/priority，SQLite旧数据保持+MySQL离线DDL通过。原MySQL旧Enum fixture改用旧列SQL避免新ORM访问不存在列；新增3项LLM实机测试（独立用量/FK、晚期回滚、双消费者），当前10项均未实跑。
- SDK隐藏重试/非stop结束4项先失败再修；元数据only含空白/空HTML无深度洞察，force无正文清理旧digest。实际provider归属、legacy关系恢复/人工情感保留、源输入中途变化拒绝覆盖均回归。
- 本地最终131 passed / 10 skipped；LLM77、迁移2、既有52。123 AST、40模板、shell、flake8 E9/F63/F7/F82、git diff --check通过。文档：docs/audits/2026-09-06-m05-implementation.md。M0仍待隔离MySQL新代码验证，不部署，不宣称CI已运行。

## M0.5 隔离验收续轮（2026-09-06）
- 用户在下一步隔离MySQL验收后确认“OK，继续”。新计划 docs/superpowers/plans/2026-09-06-m05-mysql-validation.md；仅隔离验收，不部署/提交、不迁移生产库。
- SSH france-vps只读盘点：d91863f干净，MySQL/web现有镜像可用；可用RAM3981MiB/磁盘22GiB。源快照156文件，SHA256 6dacabbfd75b7174dfd21505765b62e02db9c663f355fa528438d1a1c50981ba。
- 资源fsi-m05-20260906131354：独立internal网络/卷/MySQL8.0.46，无宿主端口；MySQL768MiB/1CPU，runner512MiB/1CPU，只读/cap-drop/无生产凭据。
- 初次runner收集前exit1：Start directory is not importable。先记录计划偏差，核实目录700归ubuntu、cap-drop root无DAC覆盖，改runner为1000:1000（不放宽权限/隔离）后10/10通过15.672秒，再完整复跑10/10通过15.639秒。业务代码/断言未修改。
- 新head d472迁移model diff0、旧任务费用/FK/配置保持、爬虫基础/并发、LLM独立账本父行锁/最终失败回滚/重复消费者均通过。依赖Python3.12.14/Flask3.1.3/SQLAlchemy2.0.52/Alembic1.19.2/PyMySQL1.2.0/LiteLLM1.100.0。
- 已核对所有原有容器ID/StartedAt/RestartCount逐行相同，health正常；13:18UTC精确清理测试容器/卷/internal网络/凭据，服务器checkout仍干净d91863f。未读取生产env/备份，未付费/爬取/邮件。
- 无敏感信息源快照/日志归档至 /home/ubuntu/fsourceinsight-validation/m05-20260906131354；完整报告 docs/audits/2026-09-06-m05-mysql-validation.md。M0批准基础切片已完成代码与验收，0.5尚未部署，下一阶段M1.1；未来新构建候选仍需复验。
- 清理后本地全套131 passed/10 skipped（20.59秒），156个源文件哈希与实跑快照逐一相同、下载日志哈希/文档链接围栏/diff check通过；无暂存，HEAD仍d91863f。本轮只有计划/验收文档改动，未改变被验收的业务代码。

## OVH 验证/发布授权后
- 用户允许登录 OVH 验证 SQL，验证后提交部署；后续明确 TDD，规则已加入 CLAUDE.md。新维护计划 2026-09-06-ovh-m0-validation-deploy.md，不重跑旧安装/dump流程。
- IP SSH 首次 publickey 拒绝；被动配置发现 france-vps 指向同一服务器和专用身份，按别名成功登录，无私钥/密钥值读取。
- 生产 master@bf9cc61，干净；MySQL8.0.46/rev fd3132082a6b，task_type 已 VARCHAR(50)，只读 model diff=0。先记录计划差异再调整测试。
- 独立 internal network、专用卷/容器（fsi-m0-20260906100910），测试目录 /home/ubuntu/fsi-m0-verify.EYVS00；限资源，无业务数据/网络/凭据接入。
- 新增 MySQL unittest：已正确VARCHAR不ALTER先red后green，修改c821迁移在线类型检查；7项真实MySQL迁移/数据保持/回填/事务/并发测试全通过。本地49 passed+7远程专用skipped；CI增加独立MySQL job。
- 初次类型字符串断言因数据库返回COLLATE信息失败，改断言类型/长度/nullable，model diff 原本通过；不改变迁移语义掩盖差异。
- 源tar跨系统xattr提示不影响结果，后续使用无扩展元数据归档。
- 随后复核远端有README署名提交9383019，无业务变化；ff-only保留，提交推送ea96dde。CI run34027261828两job通过。
- 建立服务器备份/回滚目录 /home/ubuntu/fsourceinsight-backups/m0-20260906100910，gzip约21.6MB/mode600/gzip校验通过；旧四应用镜像保留。未读数据内容。
- 新候选依赖SQLAlchemy2.0.52/Alembic1.19.2，真实image再次跑7项MySQL通过，40模板/匿名权限/打包检查通过。
- 首次发布docker compose run默认interactive吞SSH脚本剩余stdin；未误报成功，及时核对迁移已完成/旧web健康/后台exit0，改用保存到服务器的脚本文件。
- 第一次切换Web5秒恢复，但任务注册字符串带rate_limit后缀导致gate误判；保护脚本自动回滚四个旧image。只读RPC确认worker健康。
- TDD补scripts/check_worker_readiness.py及3项CLI真实格式正/负例，先red后green，线上旧worker复验LIVE_WORKERS_READY；提交858a14b，CI run34028232722两job通过。
- 最终候选7项MySQL再次通过；2026-09-06 10:46:03Z→10:46:09Z第二次切换成功，web6秒恢复，LIVE_WORKERS_READY。公网首页/health/login/www health均200，匿名有效CSRF设置POST及manage/admin正确302拒绝。
- 生产revision c821/model diff0，真实镜像无env/Git/dump；MySQL/Redis及所有同机其他应用ID未变。无手工触发真实爬取/付费LLM/邮件，原后台服务正常恢复。
- label核对后精确删除fsi-m0-20260906100910临时容器/卷/internal网络及EYVS00测试密码目录；日志转存备份目录，旧镜像/数据库备份保留。
- 最终代码release858a14b（首批功能ea96dde），本地52通过/7远程专用skip，远端最终镜像7项MySQL均实跑通过。后续仅提交/同步发布文档，不重建镜像。M0.5与Agent继续TDD，未宣称全项目改造完成。
