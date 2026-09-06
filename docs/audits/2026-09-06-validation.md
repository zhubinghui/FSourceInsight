# 审查验证记录

基线：`bf9cc61b94556e00218af267db82bf42a3b80eef`，2026-09-06。此记录证明当前代码行为和验证边界，**不是修复完成证明**。

## 环境与安全范围

- macOS；Python **3.12.14**，临时 venv：`/tmp/fsource-audit-1XQuAg/venv`。
- 本机默认 Python 3.14 无项目依赖，已先记录计划偏差再使用现有 Python 3.12 创建隔离环境。
- `uv pip install -r requirements/dev.txt` 安装成功，项目 requirements 未改；这些是本轮新解析版本，不推断生产使用相同版本。
- 关键版本：Flask 3.1.3、Flask-SQLAlchemy 3.1.1、SQLAlchemy 2.0.52、Flask-WTF 1.3.0、Flask-Login 0.6.3、Celery 5.6.3、Redis client 6.4.0、LiteLLM 1.100.0、Alembic 1.19.2、pytest 9.1.1、PyMySQL 1.2.0、Jinja 3.1.6。
- 动态探针使用 Flask testing + SQLite 内存库；固定虚构 `.invalid` 域名/邮箱；SMTP、LLM、HTTP transport 按场景 mock。socket connect/DNS 被阻断，Sentry 禁用；没有连接 MySQL/Redis/生产/新闻网站。
- 没有读取 `.env` 内容或数据库备份内容，没有启动/重建/停止容器。

## 执行结果

| 检查 | 结果 | 不能由此推断 |
|---|---|---|
| 原有 `pytest --collect-only` | **exit 5；0 tests** | 不能称为测试通过 |
| AST 解析 | 103 个现有 Python 文件通过 | 不能代替运行时/类型检查 |
| shell `bash -n scripts/*.sh`（逐个） | 通过 | 不代表部署/恢复安全或能成功运行 |
| Jinja 全体模板编译 | 40 个通过 | 不代表所有 render_template 路径存在；实际邮件路径确实不存在 |
| 18 项隔离缺陷探针 | 18 项均复现所检查问题 | 不是 18 个修复后的回归测试通过 |
| Compose base+prod | 合并成功，但保留开发端口和源码挂载 | 不推断当前线上使用这个组合 |
| Compose base+prod+caddy | web 仅 127.0.0.1:8800，DB/Redis 无宿主端口，应用无源码挂载；nginx 受 profile 控制 | 没有验证当前 VPS 实际运行状态 |
| Alembic MySQL 离线 SQL | 13 个 revision 到 `fd3132082a6b` 均能生成 SQL；用量 task_type 仍旧 Enum | 不代表 MySQL 执行/带数据升级通过 |
| ORM/查询补充探针 | 见下文 | 无生产规模压测 |

### 18 项缺陷探针

源码：[probes.py](2026-09-06/probes.py)。机器可读结果：[probe-results.json](2026-09-06/probe-results.json)。

| Probe | 观察 |
|---|---|
| anonymous_admin_password_reset | CSRF 开启的匿名请求修改隔离管理员密码；新密码登录后 /admin/ 返回 200 |
| stored_xss_output | Article detail 原样输出 insight 中的 img/onerror；未执行浏览器脚本 |
| email_template_paths | 两种 `email/*.html` 路径 TemplateNotFound，裸文件名可加载 |
| digest_missing_highlights | 修正模板路径的 mock 下，发送器仍未传 top_insights；没有发送邮件 |
| html_url_resolution | 根相对链接被错误拼入当前目录 |
| empty_crawl_success | 0 fetched/0 new 仍 success |
| crawl_retry_swallowed | fetch 异常转为 errors 返回，Celery retry 未调用 |
| batch_duplicates_and_rollback | 重复进入本批，提交失败后 PendingRollbackError，日志停 running |
| llm_commit_and_category_retry | 日志提交提前保存 Article/Category；再插分类 IntegrityError |
| company_cache_collision | 新闻/官网文本更新后 cache key 不变 |
| seed_routing_mismatch | NER/classify=nano，insight=DeepSeek |
| malformed_json_cached | 无效 NER JSON 变 [] 并进入正常缓存 |
| redis_failure_not_degraded | Redis 连接异常外抛，而非内存降级 |
| private_url_no_guard | 私网 URL 未校验直接到达 mock transport；未实际请求内网 |
| end_date_excludes_day | date_to 当天中午文章被排除 |
| revision_json_lost | 已有 JSON 历史列表新增修订在 commit/reload 后丢失 |
| daily_schedule_setting | Beat 固定 01:00；改 14:00 导致定时任务跳过 |
| json_logging_not_json | 引号/换行使“JSON”日志不可 json.loads |

### 补充验证

1. 创建 25 家隔离企业 + 1 个分组；监听 SQLAlchemy `before_cursor_execute`；GET `/companies/`：**28 条 SQL，其中 sector_group SELECT 26 条**。这证明重复分组查询，不是估算线上延迟。
2. SQLite 保存 `2026-09-06T14:00:00+02:00` Article.published_at 后读取为 `2026-09-06T14:00:00`；未归一化到 UTC 12:00。
3. 给 `_get_sentiment_trend` 喂同一 yearweek 中正/负情绪日期为 01/05、01/07 的查询行，结果出现两个标签 `['01/05', '01/07']`。这是分组后处理的确定性复现，非 MySQL 实机查询结果。
4. 完整迁移离线 SQL 中唯一用量列定义为：
   ```sql
   task_type ENUM('translate','summarize','ner','sentiment','classify') NOT NULL
   ```
   后续没有该列的 ALTER；当前模型为 String(50)，缺少 digest/insight 升级迁移。

## 可复跑方式

从项目根执行，使用新隔离 venv，不使用项目真实 `.env`，不跑真实 crawl/seed/restore 脚本：

```bash
AUDIT_ENV=$(mktemp -d /tmp/fsource-audit-env-XXXXXX)
uv venv --python python3.12 "$AUDIT_ENV/venv"
uv pip install --python "$AUDIT_ENV/venv/bin/python" -r requirements/dev.txt

# 当前仓库此命令返回 5（没有测试）；修复时应补正式测试。
env -i PATH=/usr/bin:/bin HOME="$HOME" PYTHONDONTWRITEBYTECODE=1 \
  FLASK_ENV=testing DATABASE_URL='sqlite:///:memory:' SENTRY_DSN='' \
  "$AUDIT_ENV/venv/bin/python" -m pytest --collect-only -q -p no:cacheprovider tests

# 断言“基线缺陷存在”的一次性审查探针，不应作为健康检查/正确性 CI。
env -i PATH=/usr/bin:/bin HOME="$HOME" PYTHONDONTWRITEBYTECODE=1 \
  "$AUDIT_ENV/venv/bin/python" docs/audits/2026-09-06/probes.py
```

probe 输出保存在新的 `/tmp/fsource-audit-probes-*`，每个场景只 create/drop SQLite 内存表。修复后部分 probe 应不再复现，脚本可能非零退出，这是审查基线变化，不代表项目回归。后续应将用例改写为期望安全行为的正式 tests。

Compose 检查（**防止 config 展开真实密钥**）：

```bash
docker compose --env-file /dev/null \
  -f docker-compose.yml -f docker-compose.prod.yml \
  config --no-env-resolution --no-interpolate --format json

docker compose --env-file /dev/null \
  -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.caddy.yml \
  config --no-env-resolution --no-interpolate --format json
```

本轮用 Docker Compose **v5.1.0**，仅解析配置不连接 daemon；结果展示时只提取 ports/volumes/profiles/command，没有输出 environment。

MySQL 离线迁移生成方式：在独立进程关闭网络，给 TestingConfig 设置虚构 MySQL URI（如 `mysql+pymysql://audit@invalid/audit`），`create_app('testing')` 后在 app context 调用 `flask_migrate.upgrade(directory='migrations', sql=True)`。**sql=True 只生成 DDL；不能直接删掉该参数转为线上执行。**

## 覆盖缺口

- 没有真实站点成功率/robots/正文样本，不能声称某个新闻源目前可用或可自动修复。
- 没有 MySQL 实机事务/锁/迁移、Redis broker 驱逐、Celery 多进程和恢复压测。
- 没有真正调用模型或核对价格、token 成本、延迟；网络/模型都被 mock。
- 没有浏览器 XSS 执行/渲染/E2E、移动端与可访问性 QA。
- 没有生产镜像取证、实际密钥轮换、数据库备份恢复或部署验证。

这些是实施阶段需要补齐的验收，不因本轮离线检查通过而豁免。
