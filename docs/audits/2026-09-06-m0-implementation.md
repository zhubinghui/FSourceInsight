# M0 首批实施与验证记录

- 基线：`master@bf9cc61b94556e00218af267db82bf42a3b80eef`。
- 授权：用户接受架构默认建议并要求开始实施；主会话单写者，不使用子代理。
- 状态：**首批基础修复已实现，M0 尚未整体完成；M1–M4/动态 Agent 未实施。**
- 无 `.env`/备份内容读取、生产访问、真实网站爬取、付费模型调用、SMTP 发送、部署、commit 或 push。
- 上一轮 [审查报告](2026-09-06-project-audit.md) 和 18 项探针保留为基线缺陷证据；修复后应运行 `tests/`，不要以旧探针期望“漏洞仍存在”作为 CI。

## 已实施切片

| 切片 | 代码 | 行为 |
|---|---|---|
| 0.1 账户/订阅归属 | `app/web/views/subscription.py`、`auth.py`、`app/models/user.py`、`app/__init__.py`、3 个订阅模板 | 订阅页面/操作全部要求登录本人；管理员无跨账户例外；改密需旧密码；校验语言/长度；禁止开放 next 重定向；停用用户无法登录；改密使原会话失效 |
| 0.2 Insight XSS | `app/__init__.py` | 先转义模型文本，再插入受控 Markdown 标签，保留标题/粗体/列表/表格 |
| 0.3 构建/生产收口 | `.dockerignore`、2 个 Dockerfile、prod/caddy Compose | 默认排除整个构建上下文，只允许必要运行代码；显式 COPY，排除 env/dump/Git；prod 使用 !override 清除 dev 端口/代码挂载；nginx 仅 80/443；Caddy 保留 127.0.0.1:8800 |
| 0.4 用量类型迁移 | `migrations/versions/c821b4f7d901_widen_usage_task_type.py` | 前向修改为 String(50)，保留数据；离线 MySQL DDL 已验证，真实迁移未执行 |
| 0.6 爬虫基础 | `app/crawlers/base.py`、`rss_crawler.py`、`html_crawler.py`、`tasks.py` | 批内/历史去重，savepoint 隔离重复身份冲突，必需字段校验，异常 rollback、独立日志事务，UTC 归一化，urljoin，保留可重试失败 |
| 0.7 邮件模板 | `app/email/sender.py`、`app/web/views/admin.py` | 正确加载两类邮件模板，sender/preview 都传 Top Insights；验证只有高亮文章时也有正文，SMTP 失败可记录 |
| 测试/CI | `tests/`、`.github/workflows/tests.yml` | 原来 0 tests，现有 49 项正式回归；按 push/PR 配置离线检查，远端 CI 尚未执行 |

## 行为变化与兼容性

1. **所有用户需要重新登录一次。** 登录标识新增凭证指纹；原有整数会话不再接受。更改密码后当前和其他设备都需重新登录，remember cookie 同样失效。
2. **停止仅凭邮箱管理订阅或自动建账户。** 无密码订阅者保留所有数据库记录；后续需邮箱验证/受控恢复流程才恢复自助入口。本批不提供不安全的注册捷径，也不改变已有邮件订阅状态。
3. **运行爬虫要求 source 已提交。** 现有 CLI/Celery 读取已持久化源，兼容这一前提；独立日志事务不会替调用方提交未保存的源。
4. **无新增不再等同错误。** 已有条目全重复、可确认有效的空 RSS 为 `CrawlResult.status=no_change`；无法确认有效性的空抽取为失败。旧 CrawlLog Enum 暂仍映射 success/failed，M1/M2 再引入丰富状态和质量证据。
5. **不再在 RSS HTTP 错误后偷偷用 feedparser 直连重抓。** 429/408/5xx、连接/超时及可重试数据库失败可交 Celery 有限重试；403 或结构错误返回失败信息，不主动学习/换策略绕过。
6. **迁移是 expand-only。** 回滚代码时保留 VARCHAR(50)。该 revision 的 downgrade 显式拒绝缩回旧 Enum，以免截断 digest/insight/company_analysis 等付费用量。不得用 drop/create 替代数据兼容性验证。
7. **生产 Compose 需要至少 2.24.4。** 老客户端必须升级，不可删除 !override 标签。离线测试命令还要求 CLI 支持 `--no-env-resolution`，本机验证版本为 5.1.0。
8. nginx 的只读静态资源挂载保留；web/worker/worker_fast/beat 不再继承开发模式 `.:/app`。

## 验证证据

### 环境

- Python 3.12.14；复用 `/tmp/fsource-audit-1XQuAg/venv` 内的 dev 依赖，不修改全局/项目依赖声明。
- 每测试独立 SQLite 文件，应用上下文支持独立连接；网络连接/DNS 在测试进程被阻断。
- CSRF 始终开启；HTTP 使用 Flask test client；请求之间清理测试外层上下文中的用户/CSRF 缓存，避免跨 client 测试伪阳性。
- 外部 HTTP/SMTP 使用合成响应或故障；Celery retry 在 eager 请求上下文验证，不连接 broker。
- Compose 使用 `config --no-env-resolution --no-interpolate` 和 `--env-file /dev/null`，不读取实际 env 值、不连接 daemon。

### 正式测试

| 文件 | 用例数 |
|---|---:|
| `tests/test_web/test_account_security.py` | 29 |
| `tests/test_web/test_insight_rendering.py` | 1 |
| `tests/test_ops/test_production_config.py` | 3 |
| `tests/test_ops/test_usage_migration.py` | 1 |
| `tests/test_crawlers/test_legacy_pipeline.py` | 13 |
| `tests/test_email/test_delivery.py` | 2 |
| **合计** | **49 passed，无 skip** |

执行命令（从仓库根目录，路径可替换为安装了 dev 依赖的本地 venv）：

```bash
env -i PATH='/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin' \
  HOME="$HOME" PYTHONDONTWRITEBYTECODE=1 \
  /tmp/fsource-audit-1XQuAg/venv/bin/python -m pytest tests/ \
  -q --disable-warnings -p no:cacheprovider

git diff --check
```

本机整套结果：`49 passed, 251 warnings`，约 12 秒；警告主要来自既有 `datetime.utcnow`、SQLAlchemy legacy Query/Alembic API，不表示修复后的功能失败。另有 110 个 Python 文件 AST、40 个 Jinja 模板编译、shell 语法、文档链接/围栏、`git diff --check` 通过；`flake8 --select E9,F63,F7,F82` 无语法/未定义变量类错误，未声称完整风格 lint 零告警。

每组缺陷用例先失败再修复；过程中还新增“第二条插入失败应整批回滚”用例，发现并修复 SQLite legacy SAVEPOINT 提前提交，而不是修改断言接受部分数据残留。

## 未完成与上线阻塞

- **M0.5 未实施。** LLM 用量仍与业务共用 session，严格结构化契约/缓存完整输入与版本/明确优先路由仍待修复。下一切片应先让 LLM 阶段只收集结果，再单事务写业务，避免独立 usage INSERT 的 Article FK 等待尚未提交的父行更新。
- 本机 `/var/run/docker.sock` 指向不存在的目标，PATH 无 mysqld；被动检查当前 Docker context 也确认为本地 Unix socket 且不可用（未联系任何 daemon）；**MySQL 8 空库/人造旧数据到 head、NOT NULL/JSON 历史兼容、model diff、并发唯一键冲突与行锁均未实机验证**。SQLite 不能替代它们。
- 未构建/启动镜像或执行远端 CI；Dockerignore 测试验证明确允许列表及 COPY 边界，不冒充实际镜像层审计。
- 旧源的自定义网络实现、SSRF/跳转/下载限额还未收口。Safe Fetch 和完整正文质量门禁属于下一阶段，当前不能声称爬虫网络已安全。
- source lease、fencing、outbox、任务步骤幂等、Redis 控制存储隔离和调度统一尚未实现；文章提交后任务派发失败的消息缺口仍在。
- 邮件投递幂等、确定投递窗口、真正可用的退订链接仍待后续可靠性切片；本批只修模板与现有发送/失败记录路径。
- 未做浏览器 E2E、真实网站/LLM 成本测量或生产检查；未实现 Agent/schema 发布/Playwright。

## 下一步

1. 完成 M0.5（无业务写入的 LLM 收集阶段、独立账本、关系幂等、严格 JSON、完整缓存、明确路由）。
2. 在可用的隔离 MySQL 8/Redis 环境补齐迁移/事务/竞争测试；不能为推进进度移除准入门槛。
3. 按已批准的 [实施计划](../superpowers/plans/2026-09-06-dynamic-crawler-agent.md) 进入 M1 确定性引擎，再做版本/审批和有界学习。
