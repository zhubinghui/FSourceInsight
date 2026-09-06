# Findings

## 用户架构图转录
- 起点：读取源。
- 左路：尝试基本爬虫框架，RSS → HTML → 渲染。
- 右路：已知 schema 直接爬取，直接沿用已经固化的配置。
- 合流：检查读取质量，关注 HTTP 返回、抽取条数和内容解析是否正常。
- 合格：格式化输出结果，去重 / LLM 组织 / 评分。
- 不合格：Agent 学习循环，给定 MAX_loop_num；检查网页结构 → 执行提取 → 检查提取结果 → 带反馈重试。
- 学习结果：固化 schema 并在下次读取时复用，或人工复核、记日志。

## 初步盘点
- 项目基线 bf9cc61b94556e00218af267db82bf42a3b80eef，master，初始工作区干净。
- 代码涵盖 Flask Web/API、Celery、LLM、多站点爬虫和 startup_discovery；尚需逐项审查。
- tests 下暂仅发现 conftest.py 和 __init__.py，需验证测试收集结果。
- scripts/data 存在数据库备份压缩文件：不读取内容，仅审查其跟踪/交付边界。

## 爬虫初步源码发现（尚未执行验证）
- app/crawlers/base.py：fetch_articles 返回空列表也记 success；没有质量门禁。dedup 只过滤数据库已存在 external_id，没有批内去重；异常路径缺少 rollback，提交失败后日志 commit 也可能失败。
- app/crawlers/html_crawler.py：_resolve_url 使用字符串拼接而不是 urljoin；当 source.url 带目录而 href 为根相对路径时会构造错误地址。
- app/crawlers/tasks.py：BaseCrawler.run 吞掉通常的爬取异常并返回 errors，crawl_source 的 Celery retry 只在异常外抛时才触发，网络/解析失败可能不会自动重试。
- app/crawlers/registry.py：现状为注册类或 RSS 默认类；HTML 源没有注册类时直接报错，无通用 RSS→HTML→渲染发现路径。
- app/models/source.py：无 schema 版本、学习会话、质量报告或配置发布状态模型。

## 审查基础设施状态
- 并行子代理全部在启动前失败，原因是 Pi 后台运行依赖缺失；没有子代理审查结果可引用。
- 用户已明确批准不使用子代理、由主会话直接继续；无需修复 Pi。以下继续进行静态审查和隔离验证。

## Web / LLM 初查
- 严重：subscription.settings 未登录即按 email 查用户并设置 password_hash，包括管理员；CSRF 不能验证邮箱所有权。待隔离验证。
- app/__init__.py 的 markdown_light 导入 escape 但未调用，最终 Markup 输出；文章 insight 模型文本若含 HTML 可导致存储型 XSS。paragraphs 则有转义。
- website_fetcher 和抓取 URL 未做私网/跳转限制；refresh_company_analysis 可使用模型返回的 website，构成 Agent 改造需优先收口的网络权限风险。
- LLMClient._call_llm 的用量日志 commit 与 article 更新共用 db.session，会提前提交业务中间态；_link_categories 非幂等，重试可撞复合主键。
- company_analysis 缓存键仅包含 name/sector/has_site，不含 recent_news、官网实际文本等，可能所谓刷新仍读旧缓存。
- CircuitBreaker 宣称 Redis 异常回退但没有捕获 Redis I/O 错误；半开状态不限制单探针；预算按已花费用先查询后调用，不是并发硬上限。
- seed_llm_configs 与便宜优先逻辑冲突：NER/classify 实际选 nano（不是 mini）；insight 实际选 DeepSeek。nano tasks 中没有 digest。

## 部署 / 邮件 / 验证初查
- Docker Compose 5.1.0 离线 config 合并实证：base+prod 保留 web:8001/mysql:3306/redis:6380 公共绑定及 .:/app，ports/volumes: [] 未清空；加 caddy overlay 后才正确清空并绑定 web 127.0.0.1:8800。没有读取 .env，也未连接 daemon。
- 无 .dockerignore，两个 Dockerfile COPY . .，会把本地 .env、.git 和已跟踪 SQL dump 带入镜像上下文及镜像；未读取密钥或 dump 内容。
- 生产 Redis 同时承载缓存和 broker，却使用 allkeys-lru，缓存压力可驱逐队列/控制键；DB 编号隔离不是内存隔离。
- email sender/preview 使用 email/daily_digest.html、email/keyword_alert.html，但 app loader 根为 app/email/templates，仅有 daily_digest.html/keyword_alert.html。另 sender 没有传 top_insights，修复路径后仍漏发高亮文章。
- deploy.sh 自动发现 dump 就恢复（含重复部署场景），有覆盖新增数据风险；备份依赖宿主机 mysqldump，而安装步骤未装客户端；端口收口后 localhost:3306 也不可达。
- Python 3.12.14 临时 venv /tmp/fsource-audit-1XQuAg/venv 已安装 dev 依赖，未修改项目依赖。
- pytest --collect-only：exit 5，0 tests；AST 解析 103 个 Python 文件通过；shell bash -n 全部通过。
- 已执行 18 项隔离探针，18/18 复现预期当前缺陷（不是修复后的回归测试通过）。匿名管理员改密在 CSRF 开启时成功，随后本地登录可访问 /admin/；其余包含 XSS 原始输出、邮件、爬虫 URL/空跑/重试/回滚、LLM 事务/缓存/路由/JSON、Redis、私网 URL 未拦截、日期上界、修订历史丢失、调度、日志 JSON。
- 初始迁移把 llm_usage_log.task_type 定义为不含 digest/insight 的 Enum；完整 13 个 MySQL 离线迁移已核对，后续没有改该列，当前模型却是 String(50)。这是迁移/模型漂移，不推断生产库已坏。
- 部署文档 Caddy overlay 已修复其专用路径的 ports 问题，并描述 Docker-aware 备份 wrapper；不能把通用脚本问题误报为该 VPS 当前正在发生的故障。文档状态仍 Draft，未核实实际部署。
- 补充验证：25 企业地图 28 条 SQL，26 次查询 sector_group；+02:00 日期存为 naive 原时刻而非 UTC；同一 yearweek 正/负行因不同 min(date) 被拆两桶；Jinja 模板 40 个均可编译。

## 交付方向
- 最终报告已写 docs/audits/2026-09-06-project-audit.md；验证记录与可复跑隔离探针在相邻目录。
- 架构 docs/superpowers/specs/2026-09-06-dynamic-crawler-agent-design.md：确定性主流程、两层质量门禁、声明式 recipe、有界修复、独立验证、候选/发布分离、outbox/lease、浏览器安全隔离。
- 实施计划 docs/superpowers/plans/2026-09-06-dynamic-crawler-agent.md：M0 基础修复→M1 确定性引擎→M2 版本/可靠交付→M3 有界学习→M4 渲染上线→M5 可选企业目录与自动发布。
- 用户已确认以上建议默认值并开始实施，首批修复详见 docs/audits/2026-09-06-m0-implementation.md。上面的审查和 18 项探针是 bf9cc61 历史缺陷证据，不作为新正确性测试。

## 实施中的新发现与边界
- SQLite legacy transaction 模式会让首个 SAVEPOINT/release 提前提交；后续 rollback 无法撤回。新增第二条插入失败测试已复现，BaseCrawler 的 SQLite 分支显式 BEGIN 后通过。
- 单独的 LLM usage Session 并不足以安全修复：当前 pipeline 在后续付费调用前 flush Article/Company，可能与 usage 的 Article FK 父行锁互相等待。需先收集全部 LLM 结果而不写业务表，再一次应用；MySQL 行锁行为还需实机确认。
- 本地 Docker CLI 可离线合并 Compose，但 daemon socket 目标不存在，且无 mysqld；迁移只能先提交前向代码和离线 SQL，不能声称 MySQL 上线验收。
- 账户安全修复统一使旧整数会话重新登录；无密码订阅者保留数据但停用仅邮箱管理入口，后续补邮箱所有权验证/恢复。无匿名注册绕过。
- 独立日志与 savepoint 不等于 source lease/outbox：业务提交后消息派发失败的缺口仍在，真实多进程竞争尚未测试；M2 继续处理。
