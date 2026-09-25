# M2 收尾：schema 发布、每日路由、租约、outbox 与统一调度 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让批准过的 crawl schema 真正被每日抓取使用，同时给所有源加上单一调度规则、运行租约/fence 和文章 LLM outbox。

**Architecture:** 控制状态全部在 MySQL：`crawl_source_state`（每源调度 + 租约 + fence）、`crawl_schema_decision`（只追加审批记录）、`crawl_source_profile` 的生效指针、`article_llm_job`（outbox，沿用 `company_refresh_job` 模式）。新增 `app/crawlers/schedule.py`（纯规则）、`app/crawlers/runs.py`（认领与最终提交）、`app/crawlers/activation.py`（审批与路由）、`app/llm/article_jobs.py` + `app/llm/article_tasks.py`（outbox 与消费者）。旧爬虫与新引擎共用 `runs.lock/settle` 最终提交。

**Tech Stack:** Python 3.12、Flask、SQLAlchemy 2、Alembic、Celery 5、pytest；SQLite 离线测试 + 一次性 MySQL 集成测试。

**Spec:** `docs/superpowers/specs/2026-09-25-m2-activation-routing-design.md`（执行者必须同时读 spec 与本计划）。

## Global Constraints

- 测试命令一律用 `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest ...`（不要用 /tmp 下的 venv）。
- 迁移只增不删：新 revision `b9d4f6a2c813`，down_revision `d3e7a1c95b28`；`downgrade()` 抛 `RuntimeError`；不回填业务数据。
- 时间一律为 naive UTC；时钟入口是 `app.crawlers.schedule.now()` 与 `app.llm.article_jobs.now()`，测试只 monkeypatch 这两个。
- 租约 15 分钟；`crawl_source` 的 `soft_time_limit=600`、`time_limit=660`。
- 调度器每 60 秒一轮，每轮最多 50 个源；锚点须晚于 `S + 30 分钟`；可重试失败按 `min(F, 15 分钟 × 2^(n−1))` 退避，Retry-After 上限 24 小时；访问受限冷却 24 小时；抽取/质量失败连续 3 次写 `attention_reason = extraction_failed`；频率小于 15 分钟（含 0、负数、空）按 15 分钟。
- 文章任务：queued 最多 24 小时，running 截止 30 分钟，重发间隔 ≥ 120 秒（实现为 121 秒），恢复任务每 60 秒最多 50 条；消费者 `rate_limit='10/m'`，不自动重付。
- 手写候选的预览证据 ≤ 24 小时、`status == 'ready'`、`report['source_policy']` 非空，且当前未过期。
- 全局加锁顺序：`news_source` → `crawl_source_state` → `crawl_source_profile`。
- Redis 不承载任何控制状态；调度字段不写 `news_source`。
- 路由到 schema 的源永不回落旧爬虫；只有 retire 决策能改变路由。
- 外部 HTTP 测试只用现有 `fetch_network` fixture；模型只在 `litellm.completion` 边界替换；Celery 只在 `Celery.send_task` 边界替换。
- 每个任务结束提交一次，提交信息末尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

## Review Focus

1. **频率为 0、负数或空的源**：调度不能每分钟空转，应按 15 分钟处理 → Task 3 `test_a_missing_or_non_positive_frequency_never_busy_loops`。
2. **设置里 `crawl_daily_hour` / `crawl_timezone` 是非法值**：锚点回落到巴黎 01:00，不能让调度器抛错停摆 → Task 3 `test_anchor_settings_fall_back_to_the_default`。
3. **抓取提交成功但 broker 暂时不可用**：文章任务必须保持 queued，由恢复任务补发，不能丢 → Task 4 `test_broker_outage_after_commit_leaves_a_queued_job_for_recovery`。
4. **文章在任务执行前被删除**：任务应以 `article_unavailable` 关闭，不调用模型 → Task 2 `test_job_for_a_deleted_article_closes_without_paying`。
5. **源被停用**：不能再被认领；Admin“立即抓取”应明确提示已停用，而不是假装排队 → Task 4 `test_inactive_sources_are_never_claimed`，Task 9 `test_crawl_now_reports_running_and_disabled_sources`。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `app/models/crawl_runtime.py`（新） | `CrawlSourceState`、`CrawlSchemaDecision`、`ArticleLLMJob` |
| `app/models/crawl_schema.py` / `source.py`（改） | profile 生效指针四列；crawl_log 运行字段八列 |
| `migrations/versions/b9d4f6a2c813_crawl_activation_runtime.py`（新） | 上述 DDL |
| `app/crawlers/schedule.py`（新） | 纯规则：错误分类、锚点、下次到期、锚点设置读取、`now()` |
| `app/crawlers/runs.py`（新） | 状态行补齐、认领、当前认领校验、最终提交锁与结算、stale/abandon、手动请求、`execute` |
| `app/crawlers/activation.py`（新） | 证据判定、approve/reject/rollback/retire、版本标签、运行时路由 |
| `app/crawlers/base.py`、`_ingestion.py`、`engine.py`、`contracts.py`、`tasks.py`（改） | 两条路径接入认领与 outbox；新调度任务 |
| `app/llm/article_jobs.py`（新） | outbox 状态机：enqueue/request/publish/claim/finish/recover/latest/counts/backfill |
| `app/llm/article_tasks.py`（新） | Celery 消费者 `process`、`recover` |
| `app/llm/tasks.py`（改） | `process_article_llm` 只转成任务 |
| `app/web/views/crawl_activation.py`（新） | 四个审批 POST 路由 |
| `app/web/views/crawl_config.py`、`admin.py`、模板、`app/monitoring.py`（改） | Admin 展示与入口 |
| `celery_app.py`、`scripts/*`（改/新） | beat、include、CLI、补偿脚本、就绪检查 |
| `tests/support/runs.py`（新） | 测试用 `Clock`、`claimed()` |

---

### Task 1: 迁移、模型与 spec 对齐

**Files:**
- Modify: `docs/superpowers/specs/2026-09-25-m2-activation-routing-design.md`
- Create: `app/models/crawl_runtime.py`
- Modify: `app/models/crawl_schema.py`（`CrawlSourceProfile`）、`app/models/source.py`（`CrawlLog`）、`app/models/__init__.py`
- Create: `migrations/versions/b9d4f6a2c813_crawl_activation_runtime.py`
- Create: `tests/test_ops/test_crawl_runtime_migration.py`
- Modify: `tests/integration/test_mysql_m0.py`（`HEAD`）

**Interfaces:**
- Produces: 模型 `CrawlSourceState(source_id, next_due_at, due_reason, consecutive_failures, attention_reason, attention_since, claim_id, lease_expires_at, fence, running_log_id)`、`CrawlSchemaDecision(...)`、`ArticleLLMJob(...)`；`CrawlSourceProfile.active_version_id / previous_version_id / activation_generation / active_source_generation`；`CrawlLog.claim_id / fence / route / activation_generation / schema_version_id / policy_version_id / outcome / error_code`。

- [ ] **Step 1: 在 spec 中记录实现层面的四处对齐**（计划纪律：先改文档再动代码）

在 spec 末尾追加：

```markdown
## 12. 实施对齐（2026-09-25，写实施计划时）

1. §5.5 初始值不在 Alembic 中回填：`dispatch_due_crawls` 每轮先为缺少 state 行的启用源补一行，按同一规则计算（`last_crawled_at` 为空则为当前时刻，否则按成功规则并不早于当前时刻）。迁移保持只增不改数据。
2. §5.4 “运行期间请求立即抓取”的那一段作废，以 §5.6 为准：租约有效时请求只返回“正在运行”，不改到期时间，也不追加第二次运行（与原 M2 计划“同一次认领合并完成”一致）。
3. §6.2 的任务名改为沿用公司刷新的两模块写法：状态机在 `app.llm.article_jobs`，Celery 任务为 `app.llm.article_tasks.process` 与 `app.llm.article_tasks.recover`。
4. §9 下次到期规则是纯函数（`app.crawlers.schedule.next_due`），DST 与退避规则直接对它测试；另有经真实抓取路径的结算测试确认运行确实使用该规则。
5. `CrawlEngine.run()` 与 `BaseCrawler.run()` 改为必须传入认领（`run(claim)`），保证所有写文章的路径都经过 claim/fence 检查；`scripts/run_recipe.py --apply` 与 `scripts/run_crawl.py` 先认领再运行。
```

- [ ] **Step 2: 写失败的迁移测试** `tests/test_ops/test_crawl_runtime_migration.py`

```python
"""Expand-only crawl runtime migration through the real Alembic CLI, not create_all."""
from sqlalchemy import inspect, text

from app import create_app
from app.config import TestingConfig
from app.extensions import db

PREVIOUS = 'd3e7a1c95b28'
HEAD = 'b9d4f6a2c813'


def test_upgrade_keeps_profiles_and_logs_and_creates_empty_runtime_tables(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "legacy.db"}')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    app = create_app('testing')
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE crawl_source_profile (id INTEGER PRIMARY KEY, source_id INTEGER, generation INTEGER)')
            conn.exec_driver_sql('INSERT INTO crawl_source_profile VALUES (1, 7, 3)')
            conn.exec_driver_sql('CREATE TABLE crawl_log (id INTEGER PRIMARY KEY, source_id INTEGER, started_at DATETIME, status TEXT)')
            conn.exec_driver_sql("INSERT INTO crawl_log VALUES (5, 7, '2026-09-24 01:00:00', 'failed')")
        runner = app.test_cli_runner()
        assert runner.invoke(args=['db', 'stamp', PREVIOUS]).exit_code == 0
        result = runner.invoke(args=['db', 'upgrade', HEAD])
        assert result.exit_code == 0, result.output
        with db.engine.connect() as conn:
            assert tuple(conn.execute(text(
                'SELECT generation, active_version_id, previous_version_id, activation_generation, '
                'active_source_generation FROM crawl_source_profile')).one()) == (3, None, None, 0, None)
            assert tuple(conn.execute(text(
                'SELECT status, claim_id, fence, route, outcome, error_code FROM crawl_log')).one()) == (
                'failed', None, None, None, None, None)
            for table in ('crawl_source_state', 'crawl_schema_decision', 'article_llm_job'):
                assert conn.execute(text(f'SELECT count(*) FROM {table}')).scalar_one() == 0
        unique = {tuple(row['column_names']) for row in inspect(db.engine).get_unique_constraints('article_llm_job')}
        assert ('active_article_id',) in unique
        assert runner.invoke(args=['db', 'downgrade', PREVIOUS]).exit_code != 0
        db.session.remove()
        db.engine.dispose()


def test_mysql_ddl_is_additive_and_backfills_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'mysql+pymysql://test:test@localhost/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'migration.log'))
    result = create_app('testing').test_cli_runner().invoke(args=['db', 'upgrade', f'{PREVIOUS}:{HEAD}', '--sql'])
    assert result.exit_code == 0, result.output
    for created in ('CREATE TABLE crawl_source_state', 'CREATE TABLE crawl_schema_decision',
                    'CREATE TABLE article_llm_job', 'UNIQUE (active_article_id)'):
        assert created in result.output
    for forbidden in ('DROP TABLE', 'DELETE FROM', 'UPDATE crawl_log', 'UPDATE crawl_source_profile',
                      'INSERT INTO crawl_source_state', 'INSERT INTO article_llm_job'):
        assert forbidden not in result.output
```

- [ ] **Step 3: 运行，确认失败**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_ops/test_crawl_runtime_migration.py -q`
Expected: FAIL（`Can't locate revision identified by 'b9d4f6a2c813'`）

- [ ] **Step 4: 新建模型** `app/models/crawl_runtime.py`

```python
"""Crawl run control and the article LLM outbox (M2). Control state lives in MySQL, never Redis."""
from app.extensions import db


class CrawlSourceState(db.Model):
    """One row per news source: next due time, failure streak, attention and the run lease."""
    __tablename__ = 'crawl_source_state'

    source_id = db.Column(db.Integer, db.ForeignKey('news_source.id'), primary_key=True)
    next_due_at = db.Column(db.DateTime, nullable=False)
    due_reason = db.Column(db.String(16), nullable=False)
    consecutive_failures = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    attention_reason = db.Column(db.String(40))
    attention_since = db.Column(db.DateTime)
    claim_id = db.Column(db.String(36))
    lease_expires_at = db.Column(db.DateTime)
    # Monotonic: every claim increments it, so a late worker can never commit.
    fence = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    running_log_id = db.Column(db.Integer, db.ForeignKey('crawl_log.id'))

    __table_args__ = (db.Index('idx_crawl_state_due', 'next_due_at'),)


class CrawlSchemaDecision(db.Model):
    """Append-only human decision about which recipe scheduled crawls use."""
    __tablename__ = 'crawl_schema_decision'

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey('crawl_source_profile.id'), nullable=False)
    action = db.Column(db.String(16), nullable=False)
    version_id = db.Column(db.Integer, db.ForeignKey('crawl_schema_version.id'))
    from_version_id = db.Column(db.Integer, db.ForeignKey('crawl_schema_version.id'))
    activation_generation = db.Column(db.Integer, nullable=False)
    evidence_kind = db.Column(db.String(16))
    evidence_ref = db.Column(db.String(64))
    evidence_hash = db.Column(db.String(64))
    source_generation = db.Column(db.Integer, nullable=False)
    policy_version_id = db.Column(db.Integer, db.ForeignKey('crawl_policy_version.id'))
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, nullable=False)

    __table_args__ = (db.Index('idx_schema_decision_profile', 'profile_id', 'id'),)


class ArticleLLMJob(db.Model):
    """Durable LLM work for one article, created in the same transaction as the article."""
    __tablename__ = 'article_llm_job'

    id = db.Column(db.String(36), primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id', ondelete='SET NULL'), index=True)
    # Equals article_id only while queued/running: at most one active job per article.
    active_article_id = db.Column(db.Integer, db.ForeignKey('article.id', ondelete='SET NULL'), unique=True)
    trigger = db.Column(db.String(16), nullable=False)
    crawl_log_id = db.Column(db.Integer, db.ForeignKey('crawl_log.id'))
    force = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    state = db.Column(db.String(16), nullable=False)
    reason = db.Column(db.String(80))
    claim_id = db.Column(db.String(36))
    created_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    deadline_at = db.Column(db.DateTime)
    next_dispatch_at = db.Column(db.DateTime, nullable=False)
    finished_at = db.Column(db.DateTime)

    __table_args__ = (db.Index('idx_article_llm_job_pending', 'state', 'next_dispatch_at'),)
```

在 `app/models/crawl_schema.py` 的 `CrawlSourceProfile` 中 `capture_history_complete` 之后加：

```python
    # Pointers form a cycle with crawl_schema_version.profile_id, hence use_alter.
    active_version_id = db.Column(db.Integer, db.ForeignKey(
        'crawl_schema_version.id', use_alter=True, name='fk_profile_active_version'))
    previous_version_id = db.Column(db.Integer, db.ForeignKey(
        'crawl_schema_version.id', use_alter=True, name='fk_profile_previous_version'))
    activation_generation = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    active_source_generation = db.Column(db.Integer)
```

在 `app/models/source.py` 的 `CrawlLog` 中 `error_message` 之后加：

```python
    claim_id = db.Column(db.String(36))
    fence = db.Column(db.Integer)
    route = db.Column(db.String(16))
    activation_generation = db.Column(db.Integer)
    schema_version_id = db.Column(db.Integer, db.ForeignKey(
        'crawl_schema_version.id', name='fk_crawl_log_schema_version'))
    policy_version_id = db.Column(db.Integer, db.ForeignKey(
        'crawl_policy_version.id', name='fk_crawl_log_policy_version'))
    outcome = db.Column(db.String(24))
    error_code = db.Column(db.String(40))
```

`app/models/__init__.py` 增加 `from .crawl_runtime import CrawlSourceState, CrawlSchemaDecision, ArticleLLMJob` 并把三个名字加入 `__all__`。

- [ ] **Step 5: 新建迁移** `migrations/versions/b9d4f6a2c813_crawl_activation_runtime.py`

```python
"""Crawl activation pointers, run claims and the article LLM outbox; expand-only, no backfill.

Revision ID: b9d4f6a2c813
Revises: d3e7a1c95b28
"""
from alembic import op
import sqlalchemy as sa

revision = 'b9d4f6a2c813'
down_revision = 'd3e7a1c95b28'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('crawl_source_profile') as batch:
        batch.add_column(sa.Column('active_version_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('previous_version_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('activation_generation', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('active_source_generation', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_profile_active_version', 'crawl_schema_version', ['active_version_id'], ['id'])
        batch.create_foreign_key('fk_profile_previous_version', 'crawl_schema_version', ['previous_version_id'], ['id'])
    with op.batch_alter_table('crawl_log') as batch:
        batch.add_column(sa.Column('claim_id', sa.String(36), nullable=True))
        batch.add_column(sa.Column('fence', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('route', sa.String(16), nullable=True))
        batch.add_column(sa.Column('activation_generation', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('schema_version_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('policy_version_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('outcome', sa.String(24), nullable=True))
        batch.add_column(sa.Column('error_code', sa.String(40), nullable=True))
        batch.create_foreign_key('fk_crawl_log_schema_version', 'crawl_schema_version', ['schema_version_id'], ['id'])
        batch.create_foreign_key('fk_crawl_log_policy_version', 'crawl_policy_version', ['policy_version_id'], ['id'])
    op.create_table('crawl_schema_decision',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('profile_id', sa.Integer(), sa.ForeignKey('crawl_source_profile.id'), nullable=False),
        sa.Column('action', sa.String(16), nullable=False),
        sa.Column('version_id', sa.Integer(), sa.ForeignKey('crawl_schema_version.id')),
        sa.Column('from_version_id', sa.Integer(), sa.ForeignKey('crawl_schema_version.id')),
        sa.Column('activation_generation', sa.Integer(), nullable=False),
        sa.Column('evidence_kind', sa.String(16)),
        sa.Column('evidence_ref', sa.String(64)),
        sa.Column('evidence_hash', sa.String(64)),
        sa.Column('source_generation', sa.Integer(), nullable=False),
        sa.Column('policy_version_id', sa.Integer(), sa.ForeignKey('crawl_policy_version.id')),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('reason', sa.String(200)),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('idx_schema_decision_profile', 'crawl_schema_decision', ['profile_id', 'id'])
    op.create_table('crawl_source_state',
        sa.Column('source_id', sa.Integer(), sa.ForeignKey('news_source.id'), primary_key=True),
        sa.Column('next_due_at', sa.DateTime(), nullable=False),
        sa.Column('due_reason', sa.String(16), nullable=False),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('attention_reason', sa.String(40)),
        sa.Column('attention_since', sa.DateTime()),
        sa.Column('claim_id', sa.String(36)),
        sa.Column('lease_expires_at', sa.DateTime()),
        sa.Column('fence', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('running_log_id', sa.Integer(), sa.ForeignKey('crawl_log.id')))
    op.create_index('idx_crawl_state_due', 'crawl_source_state', ['next_due_at'])
    op.create_table('article_llm_job',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('article_id', sa.Integer(), sa.ForeignKey('article.id', ondelete='SET NULL')),
        sa.Column('active_article_id', sa.Integer(), sa.ForeignKey('article.id', ondelete='SET NULL'), unique=True),
        sa.Column('trigger', sa.String(16), nullable=False),
        sa.Column('crawl_log_id', sa.Integer(), sa.ForeignKey('crawl_log.id')),
        sa.Column('force', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('reason', sa.String(80)),
        sa.Column('claim_id', sa.String(36)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('deadline_at', sa.DateTime()),
        sa.Column('next_dispatch_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime()))
    op.create_index('ix_article_llm_job_article_id', 'article_llm_job', ['article_id'])
    op.create_index('idx_article_llm_job_pending', 'article_llm_job', ['state', 'next_dispatch_at'])


def downgrade():
    raise RuntimeError('Expand-only: retain activation decisions, run history and article LLM jobs')
```

`tests/integration/test_mysql_m0.py`：`HEAD = 'b9d4f6a2c813'`。

- [ ] **Step 6: 运行迁移测试与会走 `create_all` 的冒烟测试**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_ops/test_crawl_runtime_migration.py tests/test_ops/test_company_refresh_migration.py tests/test_web/test_crawl_config.py -q`
Expected: PASS。若 SQLite `create_all` 因 `use_alter` 报错，先确认 SQLAlchemy 在不支持 ALTER 的方言上是否把外键内联；仍失败时在 spec §12 记录并去掉两列的 `ForeignKey`（迁移同步去掉），不要静默绕过。

- [ ] **Step 7: 提交**

```bash
git add docs/superpowers/specs/2026-09-25-m2-activation-routing-design.md app/models migrations/versions/b9d4f6a2c813_crawl_activation_runtime.py tests/test_ops/test_crawl_runtime_migration.py tests/integration/test_mysql_m0.py
git commit -m "feat(db): add crawl activation, run claims and article LLM outbox tables"
```

---

### Task 2: 文章 LLM outbox（状态机、消费者、Admin 入口、旧消息转换）

**Files:**
- Create: `app/llm/article_jobs.py`、`app/llm/article_tasks.py`
- Modify: `app/llm/tasks.py`（`process_article_llm`）、`celery_app.py`（include/routes/beat）
- Modify: `app/web/views/admin.py`（`article_reprocess`、`llm_reprocess`、`article_detail`）、`app/web/templates/admin/article_detail.html`
- Modify: `app/monitoring.py`、`app/web/templates/admin/monitoring.html`
- Create: `tests/test_llm/test_article_jobs.py`
- Modify: `tests/test_llm/test_pipeline.py`

**Interfaces:**
- Consumes: `ArticleLLMJob`（Task 1）。
- Produces:
  - `article_jobs.TASK = 'app.llm.article_tasks.process'`
  - `article_jobs.now() -> datetime`
  - `article_jobs.enqueue(session, article_id: int, trigger: str, *, crawl_log_id: int | None = None, force: bool = False) -> str | None`（调用方事务内；已有进行中任务返回 None）
  - `article_jobs.request(article_id, trigger, *, force=False) -> tuple[str | None, bool]`
  - `article_jobs.publish(identity: str) -> None`、`claim(identity, claim_id) -> SimpleNamespace(article_id, force) | None`、`finish(identity, claim_id, state, reason)`、`recover(limit=50)`、`latest(article_id)`、`counts() -> dict[str, int]`、`backfill(*, apply=False, batch=500) -> int`
  - Celery：`app.llm.article_tasks.process(identity)`、`app.llm.article_tasks.recover()`

- [ ] **Step 1: 写失败测试** `tests/test_llm/test_article_jobs.py`

```python
"""Durable article LLM jobs: Admin requests, claimed consumption and recovery (spec §6)."""
from datetime import timedelta

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import update

from app.llm import article_jobs
from app.llm.article_tasks import process, recover
from app.models.article import Article
from app.models.crawl_runtime import ArticleLLMJob
from tests.test_llm.test_pipeline import article_reply

TASK = 'app.llm.article_tasks.process'


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr('celery.app.base.Celery.send_task',
                        lambda self, name, args=None, kwargs=None, **options:
                        messages.append((name, args, options.get('queue'))))
    return messages


def latest(db, article_id):
    db.session.remove()
    return (ArticleLLMJob.query.filter_by(article_id=article_id)
            .order_by(ArticleLLMJob.created_at.desc(), ArticleLLMJob.id.desc()).first())


def test_admin_reprocess_queues_one_forced_job_and_absorbs_a_repeat(db, llm_env, client, login, csrf_token, sent):
    login('admin')
    path = f'/admin/articles/{llm_env.article.id}'
    for _ in range(2):
        assert client.post(f'{path}/reprocess', data={'csrf_token': csrf_token()}).status_code == 302
    item = latest(db, llm_env.article.id)
    assert (item.state, item.trigger, item.force) == ('queued', 'manual', True)
    assert sent == [(TASK, [item.id], 'llm')]
    page = BeautifulSoup(client.get(path).text, 'html.parser')
    assert page.select_one('[data-llm-job-state]').get_text(strip=True) == 'queued'
    assert llm_env.provider.calls == []


def test_duplicate_delivery_pays_once(db, llm_env, sent):
    llm_env.provider.reply = article_reply
    identity, created = article_jobs.request(llm_env.article.id, 'manual')
    assert created
    process.run(identity)
    calls = len(llm_env.provider.calls)
    process.run(identity)
    assert calls > 0 and len(llm_env.provider.calls) == calls
    item = latest(db, llm_env.article.id)
    assert (item.state, item.reason, item.active_article_id) == ('done', 'applied', None)
    assert db.session.get(Article, llm_env.article.id).llm_processed


def test_failure_is_recorded_without_automatic_paid_retry(db, llm_env, client, login, csrf_token, sent):
    llm_env.provider.error = RuntimeError('provider down')
    identity, _ = article_jobs.request(llm_env.article.id, 'manual')
    process.run(identity)
    assert (latest(db, llm_env.article.id).state, latest(db, llm_env.article.id).reason) == ('failed', 'execution_error')
    calls = len(llm_env.provider.calls)
    recover.run()
    assert len(llm_env.provider.calls) == calls
    login('admin')
    assert client.post('/admin/llm-reprocess', data={'csrf_token': csrf_token(), 'limit': '50'}).status_code == 302
    again = latest(db, llm_env.article.id)
    assert again.id != identity and (again.state, again.trigger) == ('queued', 'manual')


def test_recovery_respects_spacing_and_expiry(db, llm_env, sent, monkeypatch):
    base = article_jobs.now()
    identity, _ = article_jobs.request(llm_env.article.id, 'manual')
    article_jobs.publish(identity)
    monkeypatch.setattr(article_jobs, 'now', lambda: base + timedelta(seconds=60))
    recover.run()
    assert len(sent) == 1
    monkeypatch.setattr(article_jobs, 'now', lambda: base + timedelta(seconds=130))
    recover.run()
    assert sent == [(TASK, [identity], 'llm')] * 2
    monkeypatch.setattr(article_jobs, 'now', lambda: base + timedelta(hours=25))
    recover.run()
    assert (latest(db, llm_env.article.id).state, latest(db, llm_env.article.id).reason) == ('expired', 'queue_expired')


def test_interrupted_running_job_is_closed_and_a_late_finish_is_ignored(db, llm_env, sent, monkeypatch):
    base = article_jobs.now()
    identity, _ = article_jobs.request(llm_env.article.id, 'manual')
    assert article_jobs.claim(identity, 'worker-1').article_id == llm_env.article.id
    assert article_jobs.claim(identity, 'worker-2') is None
    monkeypatch.setattr(article_jobs, 'now', lambda: base + timedelta(minutes=31))
    recover.run()
    article_jobs.finish(identity, 'worker-1', 'done', 'applied')
    item = latest(db, llm_env.article.id)
    assert (item.state, item.reason) == ('failed', 'interrupted')
    assert sent == []


def test_old_direct_messages_only_create_a_job(db, llm_env, sent):
    from app.llm.tasks import process_article_llm
    process_article_llm.run(llm_env.article.id, force=True)
    assert llm_env.provider.calls == []
    item = latest(db, llm_env.article.id)
    assert (item.trigger, item.force, item.state) == ('legacy_message', True, 'queued')
    assert sent == [(TASK, [item.id], 'llm')]


def test_job_for_a_deleted_article_closes_without_paying(db, llm_env, sent):
    identity, _ = article_jobs.request(llm_env.article.id, 'manual')
    # SQLite does not enforce FKs here; emulate MySQL's ON DELETE SET NULL.
    db.session.execute(update(ArticleLLMJob).where(ArticleLLMJob.id == identity).values(article_id=None))
    db.session.commit()
    process.run(identity)
    db.session.remove()
    item = db.session.get(ArticleLLMJob, identity)
    assert (item.state, item.reason, item.active_article_id) == ('failed', 'article_unavailable', None)
    assert llm_env.provider.calls == []


def test_monitoring_and_backfill_report_job_states(db, llm_env, client, login, sent):
    assert article_jobs.backfill() == 1
    assert ArticleLLMJob.query.count() == 0
    assert article_jobs.backfill(apply=True) == 1
    assert article_jobs.backfill(apply=True) == 0
    login('admin')
    page = BeautifulSoup(client.get('/admin/monitoring').text, 'html.parser')
    assert page.select_one('[data-llm-jobs="queued"]').get_text(strip=True) == '1'
```

- [ ] **Step 2: 运行，确认失败**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_llm/test_article_jobs.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.llm.article_jobs'`）

- [ ] **Step 3: 实现** `app/llm/article_jobs.py`

```python
"""Durable LLM work for articles: created with the article, claimed before any paid call (spec §6).

At most one queued/running job per article. Transitions are short row-locked
transactions; the model is only called by a consumer holding the claim.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.article import Article
from app.models.crawl_runtime import ArticleLLMJob

TASK = 'app.llm.article_tasks.process'
QUEUE_LIFETIME = timedelta(hours=24)
RUNNING_LIMIT = timedelta(minutes=30)
SPACING = timedelta(seconds=121)
logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _row(session, identity):
    return session.scalar(select(ArticleLLMJob).where(ArticleLLMJob.id == identity).with_for_update()
                          .execution_options(populate_existing=True))


def _close(item, state, reason):
    item.state, item.reason = state, reason
    item.finished_at, item.active_article_id = now(), None


def enqueue(session, article_id, trigger, *, crawl_log_id=None, force=False):
    """Create a queued job inside the caller's transaction; None if one is already active."""
    if session.scalar(select(ArticleLLMJob.id).where(ArticleLLMJob.active_article_id == article_id)):
        return None
    moment = now()
    item = ArticleLLMJob(id=str(uuid.uuid4()), article_id=article_id, active_article_id=article_id,
                         trigger=trigger, crawl_log_id=crawl_log_id, force=force, state='queued',
                         created_at=moment, next_dispatch_at=moment, expires_at=moment + QUEUE_LIFETIME)
    session.add(item)
    session.flush()
    return item.id


def request(article_id, trigger, *, force=False):
    """Own transaction (Admin, retired messages). Returns (job id, created)."""
    with Session(db.engine) as session, session.begin():
        if session.scalar(select(Article.id).where(Article.id == article_id).with_for_update()) is None:
            return None, False
        active = session.scalar(select(ArticleLLMJob.id).where(ArticleLLMJob.active_article_id == article_id))
        if active:
            return active, False
        return enqueue(session, article_id, trigger, force=force), True


def publish(identity):
    from celery_app import celery
    try:
        with Session(db.engine) as session, session.begin():
            item = _row(session, identity)
            if item is None or item.state != 'queued' or now() < item.next_dispatch_at:
                return
            if now() >= item.expires_at:
                _close(item, 'expired', 'queue_expired')
                return
            item.next_dispatch_at = now() + SPACING
        celery.send_task(TASK, args=[identity], queue='llm')
    except Exception:
        logger.warning('Article LLM dispatch unavailable; durable job retained')


def claim(identity, claim_id):
    with Session(db.engine) as session, session.begin():
        item = _row(session, identity)
        if item is None or item.state != 'queued' or item.claim_id is not None:
            return None
        if now() >= item.expires_at:
            _close(item, 'expired', 'queue_expired')
            return None
        if item.article_id is None:
            _close(item, 'failed', 'article_unavailable')
            return None
        item.state, item.claim_id, item.deadline_at = 'running', claim_id, now() + RUNNING_LIMIT
        return SimpleNamespace(article_id=item.article_id, force=item.force)


def finish(identity, claim_id, state, reason):
    with Session(db.engine) as session, session.begin():
        item = _row(session, identity)
        if item is None or item.state != 'running' or item.claim_id != claim_id:
            logger.info('Article LLM job %s finished after losing its claim', identity)
            return
        _close(item, state, reason)


def recover(limit=50):
    moment = now()
    with Session(db.engine) as session:
        ids = list(session.scalars(select(ArticleLLMJob.id).where(or_(
            and_(ArticleLLMJob.state == 'queued', ArticleLLMJob.next_dispatch_at <= moment),
            and_(ArticleLLMJob.state == 'running', ArticleLLMJob.deadline_at <= moment)))
            .order_by(ArticleLLMJob.next_dispatch_at, ArticleLLMJob.id).limit(limit)))
    for identity in ids:
        dispatch = False
        with Session(db.engine) as session, session.begin():
            item = _row(session, identity)
            if item is None:
                continue
            if item.state == 'running' and item.deadline_at is not None and item.deadline_at <= now():
                # A paid call may have happened; never pay again automatically.
                _close(item, 'failed', 'interrupted')
            elif item.state == 'queued':
                if now() >= item.expires_at:
                    _close(item, 'expired', 'queue_expired')
                else:
                    dispatch = True
        if dispatch:
            publish(identity)


def latest(article_id):
    return db.session.scalar(select(ArticleLLMJob).where(ArticleLLMJob.article_id == article_id)
                             .order_by(ArticleLLMJob.created_at.desc(), ArticleLLMJob.id.desc()).limit(1))


def counts():
    return dict(db.session.execute(select(ArticleLLMJob.state, func.count()).group_by(ArticleLLMJob.state)).all())


def backfill(*, apply=False, batch=500):
    """Jobs for unprocessed articles without an active job. Dry run by default; returns the count."""
    active = select(ArticleLLMJob.active_article_id).where(ArticleLLMJob.active_article_id.is_not(None))
    with Session(db.engine) as session:
        ids = list(session.scalars(select(Article.id).where(
            Article.llm_processed.is_(False), Article.id.not_in(active)).order_by(Article.id)))
    if not apply:
        return len(ids)
    created = 0
    for start in range(0, len(ids), batch):
        with Session(db.engine) as session, session.begin():
            created += sum(1 for article_id in ids[start:start + batch] if enqueue(session, article_id, 'backfill'))
    return created
```

`app/llm/article_tasks.py`：

```python
"""LLM-queue consumer for durable article jobs; a claim precedes every paid call (spec §6.3)."""
import logging
import uuid

from celery_app import celery
from app.llm import article_jobs as jobs

logger = logging.getLogger(__name__)


@celery.task(name=jobs.TASK, queue='llm', acks_late=True, ignore_result=True, rate_limit='10/m')
def process(identity):
    from app.llm.pipeline import process_article
    from app.llm.tasks import _queue_company_refreshes
    owner = str(uuid.uuid4())
    claimed = jobs.claim(identity, owner)
    if claimed is None:
        return
    try:
        applied = process_article(claimed.article_id, force=claimed.force)
    except Exception:
        logger.warning('Article LLM job %s failed; no automatic paid retry', identity)
        jobs.finish(identity, owner, 'failed', 'execution_error')
        return
    jobs.finish(identity, owner, 'done', 'applied' if applied else 'already_processed')
    if applied:
        _queue_company_refreshes(claimed.article_id)


@celery.task(name='app.llm.article_tasks.recover', queue='llm', ignore_result=True)
def recover():
    try:
        jobs.recover()
    except Exception:
        logger.warning('Article LLM recovery unavailable; durable state retained')
```

`app/llm/tasks.py`：把 `process_article_llm` 整个替换为：

```python
@celery.task(name='app.llm.tasks.process_article_llm', queue='llm', ignore_result=True)
def process_article_llm(article_id: int, force=False, skip_translate=False):
    """Retired direct consumer: older messages become durable jobs and never pay here."""
    from app.llm import article_jobs
    identity, created = article_jobs.request(article_id, 'legacy_message', force=force)
    if created:
        article_jobs.publish(identity)
```

（`from app.llm.pipeline import process_article` 若不再被本模块使用则删除该 import；`_queue_company_refreshes` 保留。）

`celery_app.py`：`include` 加 `'app.llm.article_tasks'`；`task_routes` 加 `'app.llm.article_tasks.*': {'queue': 'llm'}`；`beat_schedule` 加：

```python
            'recover-article-llm': {
                'task': 'app.llm.article_tasks.recover',
                'schedule': 60.0,
            },
```

`app/web/views/admin.py`：

```python
@admin_bp.route('/articles/<int:article_id>')
def article_detail(article_id):
    from app.llm import article_jobs
    article = Article.query.get_or_404(article_id)
    return render_template('admin/article_detail.html', article=article, llm_job=article_jobs.latest(article.id))


@admin_bp.route('/articles/<int:article_id>/reprocess', methods=['POST'])
def article_reprocess(article_id):
    from app.llm import article_jobs
    article = Article.query.get_or_404(article_id)
    identity, created = article_jobs.request(article.id, 'manual', force=True)
    if created:
        article_jobs.publish(identity)
        flash(f'Queued "{article.title_fr[:60]}" for LLM processing.', 'success')
    else:
        flash(f'"{article.title_fr[:60]}" already has a queued or running LLM job.', 'warning')
    return redirect(request.referrer or url_for('admin.articles'))
```

`llm_reprocess` 替换为：

```python
@admin_bp.route('/llm-reprocess', methods=['POST'])
def llm_reprocess():
    """Queue durable LLM jobs for unprocessed articles that have none active."""
    from app.llm import article_jobs
    from app.models.crawl_runtime import ArticleLLMJob
    limit = max(1, min(request.form.get('limit', 50, type=int) or 50, 500))
    active = db.session.query(ArticleLLMJob.active_article_id).filter(ArticleLLMJob.active_article_id.isnot(None))
    pending = (Article.query.filter(Article.llm_processed.is_(False), Article.id.notin_(active))
               .order_by(Article.crawled_at.desc()).limit(limit).all())
    queued = 0
    for article in pending:
        identity, created = article_jobs.request(article.id, 'manual')
        if created:
            article_jobs.publish(identity)
            queued += 1
    flash(f'Enqueued {queued} articles for LLM processing.', 'success')
    return redirect(url_for('admin.dashboard'))
```

`article_detail.html` 在重新处理表单之前加：

```html
{% if llm_job %}
<p class="small">Latest LLM job: <span data-llm-job-state>{{ llm_job.state }}</span>
    {% if llm_job.reason %}({{ llm_job.reason }}){% endif %} — trigger {{ llm_job.trigger }}</p>
{% endif %}
```

`app/monitoring.py` 的 `snapshot()` 返回字典加 `'llm_jobs': article_jobs.counts(),`（文件顶部 `from app.llm import article_jobs`）；`monitoring.html` 在 LLM 区块加：

```html
<p class="mb-1">Article LLM jobs:
{% for state in ['queued', 'running', 'done', 'failed', 'expired'] %}
    {{ state }} <span data-llm-jobs="{{ state }}">{{ llm_jobs.get(state, 0) }}</span>{% if not loop.last %} ·{% endif %}
{% endfor %}</p>
```

- [ ] **Step 4: 把 `tests/test_llm/test_pipeline.py` 迁到任务消费者**

在文件顶部把 `from app.llm.tasks import process_article_llm` 换成：

```python
from app.llm import article_jobs
from app.llm.article_tasks import process
from app.models.crawl_runtime import ArticleLLMJob


def run_pipeline(article_id, force=False):
    """Create and consume one durable job, as the llm worker does."""
    identity, created = article_jobs.request(article_id, 'manual', force=force)
    assert created
    process.run(identity)
    return identity
```

把每一处 `process_article_llm.run(x)` 改为 `run_pipeline(x)`（有 `force=True` 的照搬）。原来用 `pytest.raises(Exception, match=...)` 包住一次失败运行的测试，改为不再期待异常，而是在同一位置断言：

```python
    identity = run_pipeline(article_id)
    db.session.remove()
    assert db.session.get(ArticleLLMJob, identity).state == 'failed'
```

其余业务断言保持不变。

- [ ] **Step 5: 运行，确认通过**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_llm tests/test_web/test_admin_articles.py tests/test_web/test_admin_monitoring.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/llm app/web/views/admin.py app/web/templates/admin/article_detail.html app/web/templates/admin/monitoring.html app/monitoring.py celery_app.py tests/test_llm
git commit -m "feat(llm): durable article LLM jobs with claimed consumption and recovery"
```

---

### Task 3: 统一的下次到期规则（纯函数）

**Files:**
- Create: `app/crawlers/schedule.py`
- Create: `tests/test_crawlers/test_crawl_schedule.py`

**Interfaces:**
- Produces:
  - `schedule.now() -> datetime`（naive UTC，秒精度）
  - `schedule.LEASE = timedelta(minutes=15)`、`ANCHOR_GAP`、`COOLDOWN`、`MIN_FREQUENCY = 15`、`EXTRACTION_ATTENTION = 3`、`RETRY`、`BLOCKED`
  - `schedule.kind(error_code: str | None) -> 'ok' | 'retry' | 'blocked' | 'extraction'`
  - `schedule.anchor_settings(session) -> tuple[int, str]`
  - `schedule.anchor_after(moment, hour, zone) -> datetime`
  - `schedule.next_due(*, error_code, started, finished, frequency, failures, retry_after, hour, zone) -> datetime`

- [ ] **Step 1: 写失败测试** `tests/test_crawlers/test_crawl_schedule.py`

```python
"""The single next-due rule (spec §5.4), including Paris DST anchors."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.crawlers import schedule

PARIS = 'Europe/Paris'
START = datetime(2026, 9, 25, 10, 0)


def due(error_code=None, *, started=START, finished=None, frequency=360, failures=1, retry_after=None, hour=1, zone=PARIS):
    return schedule.next_due(error_code=error_code, started=started, finished=finished or started,
                             frequency=frequency, failures=failures, retry_after=retry_after, hour=hour, zone=zone)


def test_success_uses_the_earlier_of_frequency_and_the_daily_anchor():
    # 01:00 Paris is 23:00 UTC in September.
    assert due(started=datetime(2026, 9, 25, 18, 0), frequency=720) == datetime(2026, 9, 25, 23, 0)
    assert due(started=START, frequency=360) == datetime(2026, 9, 25, 16, 0)


def test_a_run_just_before_the_anchor_does_not_run_again_at_the_anchor():
    assert due(started=datetime(2026, 9, 25, 22, 40), frequency=1440) == datetime(2026, 9, 26, 22, 40)


def test_autumn_repeated_local_hour_is_a_single_instant():
    # 2026-10-25: Paris 02:00-03:00 happens twice; the first one is 00:00 UTC.
    assert due(started=datetime(2026, 10, 24, 12, 0), frequency=10080, hour=2) == datetime(2026, 10, 25, 0, 0)
    assert due(started=datetime(2026, 10, 25, 0, 0), frequency=10080, hour=2) == datetime(2026, 10, 26, 1, 0)


def test_spring_gap_hour_moves_to_the_first_instant_after_the_gap():
    # 2026-03-29: Paris jumps from 02:00 CET to 03:00 CEST at 01:00 UTC.
    assert due(started=datetime(2026, 3, 28, 12, 0), frequency=10080, hour=2) == datetime(2026, 3, 29, 1, 0)


@pytest.mark.parametrize('failures, wait', [(1, 15), (2, 30), (3, 60), (5, 240), (9, 360), (60, 360)])
def test_retryable_failures_back_off_up_to_the_source_frequency(failures, wait):
    finished = START + timedelta(minutes=1)
    assert due('timeout', finished=finished, failures=failures) == finished + timedelta(minutes=wait)


def test_retry_after_is_honoured_and_capped_at_a_day():
    assert due('rate_limited', retry_after=600) == START + timedelta(minutes=10)
    assert due('rate_limited', retry_after=10 ** 9) == START + timedelta(days=1)


@pytest.mark.parametrize('code', ['forbidden', 'robots_denied', 'robots_unavailable', 'unsafe_url', 'tls_error',
                                  'http_error', 'schema_stale', 'policy_unavailable', 'invalid_schema'])
def test_access_failures_cool_down_for_a_day(code):
    assert schedule.kind(code) == 'blocked'
    finished = START + timedelta(minutes=2)
    assert due(code, finished=finished) == finished + timedelta(days=1)


@pytest.mark.parametrize('code', ['empty_extraction', 'low_quality', 'missing_fields', 'crawler_error',
                                  'no_evidence', 'invalid_article'])
def test_extraction_failures_keep_the_normal_schedule(code):
    assert schedule.kind(code) == 'extraction'
    assert due(code, finished=START + timedelta(minutes=5)) == START + timedelta(minutes=360)


@pytest.mark.parametrize('frequency', [0, -5, None, 3])
def test_a_missing_or_non_positive_frequency_never_busy_loops(frequency):
    assert due(frequency=frequency) == START + timedelta(minutes=15)


@pytest.mark.parametrize('hour, zone, expected', [
    ('7', 'Europe/Paris', (7, 'Europe/Paris')),
    ('25', 'Mars/Olympus', (1, 'Europe/Paris')),
    ('x', '', (1, 'Europe/Paris')),
])
def test_anchor_settings_fall_back_to_the_default(db, hour, zone, expected):
    from app.models.setting import SystemSetting
    SystemSetting.set('crawl_daily_hour', hour)
    SystemSetting.set('crawl_timezone', zone)
    db.session.commit()
    with Session(db.engine) as session:
        assert schedule.anchor_settings(session) == expected
```

（若 `SystemSetting.set` 不接受空字符串，第三组参数改为只设置小时，时区保持缺省。）

- [ ] **Step 2: 运行，确认失败**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_crawlers/test_crawl_schedule.py -q`
Expected: FAIL（`ImportError: cannot import name 'schedule'`）

- [ ] **Step 3: 实现** `app/crawlers/schedule.py`

```python
"""One next-due rule for every source: frequency plus a daily local anchor (spec §5.4).

Pure functions apart from now() and anchor_settings(); times are naive UTC.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

RETRY = frozenset({'timeout', 'network_error', 'server_error', 'rate_limited', 'database_error',
                   'fetch_closed', 'transport_unavailable', 'budget_exceeded'})
BLOCKED = frozenset({'forbidden', 'robots_denied', 'robots_unavailable', 'unsafe_url', 'tls_error',
                     'login_required', 'paywall', 'captcha', 'http_error', 'redirect_limit',
                     'schema_stale', 'policy_unavailable', 'invalid_schema'})
LEASE = timedelta(minutes=15)
ANCHOR_GAP = timedelta(minutes=30)
COOLDOWN = timedelta(hours=24)
MIN_FREQUENCY = 15
EXTRACTION_ATTENTION = 3
DEFAULT_HOUR, DEFAULT_ZONE = 1, 'Europe/Paris'


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def kind(error_code):
    if error_code is None:
        return 'ok'
    if error_code in RETRY:
        return 'retry'
    if error_code in BLOCKED:
        return 'blocked'
    return 'extraction'


def anchor_settings(session):
    from app.models.setting import SystemSetting
    values = dict(session.execute(select(SystemSetting.key, SystemSetting.value).where(
        SystemSetting.key.in_(('crawl_daily_hour', 'crawl_timezone')))).all())
    try:
        hour = int(values.get('crawl_daily_hour', DEFAULT_HOUR))
    except (TypeError, ValueError):
        hour = DEFAULT_HOUR
    zone = values.get('crawl_timezone') or DEFAULT_ZONE
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = DEFAULT_ZONE
    return (hour if 0 <= hour <= 23 else DEFAULT_HOUR), zone


def anchor_after(moment, hour, zone):
    """First local hour:00 strictly after naive-UTC moment.

    fold=0 picks the first of a repeated autumn hour; a spring-gap hour takes the
    pre-transition offset, which is exactly the first instant after the gap.
    """
    tz = ZoneInfo(zone)
    day = moment.replace(tzinfo=timezone.utc).astimezone(tz).date()
    for offset in range(3):
        local = datetime.combine(day + timedelta(days=offset), time(hour), tz)
        candidate = local.astimezone(timezone.utc).replace(tzinfo=None)
        if candidate > moment:
            return candidate
    raise AssertionError('an anchor exists within three local days')


def next_due(*, error_code, started, finished, frequency, failures, retry_after, hour, zone):
    period = timedelta(minutes=max(frequency or 0, MIN_FREQUENCY))
    category = kind(error_code)
    if category == 'retry':
        if retry_after:
            return finished + timedelta(seconds=min(retry_after, 86400))
        return finished + min(period, timedelta(minutes=15) * 2 ** min(max(failures - 1, 0), 16))
    if category == 'blocked':
        return finished + COOLDOWN
    return min(started + period, anchor_after(started + ANCHOR_GAP, hour, zone))
```

- [ ] **Step 4: 运行，确认通过**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_crawlers/test_crawl_schedule.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/crawlers/schedule.py tests/test_crawlers/test_crawl_schedule.py
git commit -m "feat(crawl): single next-due rule with daily anchor, backoff and cooldown"
```

---

### Task 4: 认领、租约、调度任务与旧爬虫最终提交

**Files:**
- Create: `app/crawlers/runs.py`、`tests/support/runs.py`、`tests/test_crawlers/test_crawl_runs.py`
- Modify: `app/crawlers/base.py`、`app/crawlers/tasks.py`
- Modify: `tests/test_crawlers/test_legacy_pipeline.py`

**Interfaces:**
- Consumes: `schedule.*`（Task 3）、`article_jobs.enqueue/publish`（Task 2）、模型（Task 1）。
- Produces:
  - `runs.Claim(source_id, claim_id, fence, log_id, activation_generation, started_at)`（frozen dataclass）
  - `runs.RunLost`（异常）
  - `runs.ensure_states(moment)`、`runs.claim(source_id, *, due_only: bool) -> Claim | None`、`runs.claim_due(limit=50) -> list[Claim]`、`runs.current(source_id, claim_id) -> Claim | None`
  - `runs.lock(session, claim) -> CrawlSourceState`（最终事务内；失败抛 `RunLost`）
  - `runs.settle(session, state, claim, *, status, route, error_code=None, found=0, new=0, retry_after=None, message=None)`
  - `runs.abandon(claim, *, route, error_code, found=0, retry_after=None, message=None)`、`runs.mark_stale(claim)`
  - `runs.request_now(source_id) -> 'queued' | 'running' | 'inactive'`
  - `runs.execute(source_id, claim_id)`（本任务只走旧爬虫；Task 8 加 schema 路由）
  - `base.LegacyFailure(code, message)`、`base.failure_code(exc) -> (code, retry_after)`、`BaseCrawler.run(claim) -> CrawlResult`（status 可为 `success/no_change/failed/stale`）
  - Celery：`app.crawlers.tasks.dispatch_due_crawls()`、`app.crawlers.tasks.crawl_source(source_id, claim_id=None)`
  - 测试工具：`tests.support.runs.Clock`、`tests.support.runs.claimed(source_id) -> Claim`

- [ ] **Step 1: 测试工具** `tests/support/runs.py`

```python
"""Test helpers for claimed crawl runs; production code never imports this module."""
from datetime import timedelta


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, **delta):
        self.value += timedelta(**delta)


def claimed(source_id):
    """Claim a source now, as the dispatcher would, regardless of its due time."""
    from app.crawlers import runs, schedule
    runs.ensure_states(schedule.now())
    claim = runs.claim(source_id, due_only=False)
    assert claim is not None, 'source is disabled or already has a live claim'
    return claim
```

- [ ] **Step 2: 写失败测试** `tests/test_crawlers/test_crawl_runs.py`

```python
"""Claims, fencing, schedule settlement and the legacy final commit through public entry points."""
from datetime import datetime, timedelta

import pytest
import requests

from app.crawlers import runs, schedule
from app.crawlers.base import BaseCrawler, LegacyFailure, RawArticle
from app.crawlers.fetcher import FetchError
from app.llm import article_jobs
from app.models.article import Article
from app.models.crawl_runtime import ArticleLLMJob, CrawlSourceState
from app.models.source import CrawlLog, NewsSource
from tests.support.runs import Clock, claimed

ITEM = RawArticle(title='Research', url='https://test.invalid/news', external_id='guid-1')
PROCESS = 'app.llm.article_tasks.process'


@pytest.fixture
def clock(monkeypatch):
    value = Clock(datetime(2026, 9, 25, 10, 0))
    monkeypatch.setattr(schedule, 'now', value)
    return value


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr('celery.app.base.Celery.send_task',
                        lambda self, name, args=None, kwargs=None, **options:
                        messages.append((name, args, options.get('queue'))))
    return messages


@pytest.fixture
def source(db):
    item = NewsSource(name='Synthetic', slug='synthetic', url='https://test.invalid/',
                      feed_url='https://test.invalid/feed', category='national', crawl_frequency_minutes=360)
    db.session.add(item)
    db.session.commit()
    return item.id


class FixtureCrawler(BaseCrawler):
    def __init__(self, source, articles=(), error=None, during_fetch=None):
        super().__init__(source)
        self.articles, self.error, self.during_fetch = list(articles), error, during_fetch

    def fetch_articles(self):
        if self.during_fetch:
            self.during_fetch()
        if self.error:
            raise self.error
        return self.articles


def crawl(db, source_id, **kwargs):
    return FixtureCrawler(db.session.get(NewsSource, source_id), **kwargs).run(claimed(source_id))


def fresh(db, model, key):
    db.session.remove()
    return db.session.get(model, key)


def test_dispatcher_claims_each_due_source_once_and_sends_only_ids(db, source, clock, sent):
    from app.crawlers.tasks import dispatch_due_crawls
    assert dispatch_due_crawls.run() == {'dispatched': 1}
    assert dispatch_due_crawls.run() == {'dispatched': 0}
    state = fresh(db, CrawlSourceState, source)
    assert sent == [('app.crawlers.tasks.crawl_source', [source, state.claim_id], 'crawl')]
    assert state.fence == 1 and state.lease_expires_at == clock() + timedelta(minutes=15)
    assert db.session.get(CrawlLog, state.running_log_id).status == 'running'


def test_legacy_run_commits_articles_jobs_log_and_schedule_together(db, source, clock, sent):
    claim = claimed(source)
    result = FixtureCrawler(db.session.get(NewsSource, source), [ITEM, ITEM]).run(claim)
    assert (result.status, result.articles_new) == ('success', 1)
    db.session.remove()
    article, job = Article.query.one(), ArticleLLMJob.query.one()
    assert (job.article_id, job.state, job.trigger, job.crawl_log_id) == (article.id, 'queued', 'crawl', claim.log_id)
    assert sent == [(PROCESS, [job.id], 'llm')]
    log = db.session.get(CrawlLog, claim.log_id)
    assert (log.status, log.outcome, log.route, log.articles_new) == ('success', 'success', 'legacy', 1)
    state = db.session.get(CrawlSourceState, source)
    assert (state.claim_id, state.lease_expires_at, state.running_log_id) == (None, None, None)
    assert (state.next_due_at, state.due_reason) == (clock() + timedelta(minutes=360), 'schedule')
    assert db.session.get(NewsSource, source).last_crawled_at == clock()


def test_expired_claim_cannot_commit_after_another_worker_reclaims(db, source, clock, sent):
    first = claimed(source)

    def reclaimed_meanwhile():
        clock.advance(minutes=16)
        assert runs.claim(source, due_only=False) is not None

    result = FixtureCrawler(db.session.get(NewsSource, source), [ITEM], during_fetch=reclaimed_meanwhile).run(first)
    assert result.status == 'stale'
    assert Article.query.count() == 0 and ArticleLLMJob.query.count() == 0
    assert (fresh(db, CrawlLog, first.log_id).outcome) == 'lease_expired'
    state = db.session.get(CrawlSourceState, source)
    assert state.fence == 2 and state.claim_id is not None


def test_expired_lease_alone_blocks_the_commit_and_frees_the_source(db, source, clock, sent):
    claim = claimed(source)
    result = FixtureCrawler(db.session.get(NewsSource, source), [ITEM],
                            during_fetch=lambda: clock.advance(minutes=16)).run(claim)
    assert result.status == 'stale' and Article.query.count() == 0
    assert fresh(db, CrawlLog, claim.log_id).outcome == 'stale'
    assert db.session.get(CrawlSourceState, source).claim_id is None


@pytest.mark.parametrize('error, code, outcome, wait', [
    (requests.Timeout('slow'), 'timeout', 'failed', timedelta(minutes=15)),
    (FetchError('robots_unavailable'), 'robots_unavailable', 'blocked', timedelta(hours=24)),
    (FetchError('rate_limited', 3600), 'rate_limited', 'failed', timedelta(hours=1)),
])
def test_failures_are_classified_into_the_schedule(db, source, clock, sent, error, code, outcome, wait):
    claim = claimed(source)
    result = FixtureCrawler(db.session.get(NewsSource, source), error=error).run(claim)
    assert result.status == 'failed'
    log = fresh(db, CrawlLog, claim.log_id)
    assert (log.status, log.outcome, log.error_code) == ('failed', outcome, code)
    state = db.session.get(CrawlSourceState, source)
    assert state.next_due_at == clock() + wait and state.consecutive_failures == 1
    assert state.attention_reason == (code if outcome == 'blocked' else None)


def test_three_empty_extractions_ask_for_attention_and_success_clears_it(db, source, clock, sent):
    for _ in range(3):
        crawl(db, source)
        clock.advance(hours=7)
    state = fresh(db, CrawlSourceState, source)
    assert (state.attention_reason, state.consecutive_failures) == ('extraction_failed', 3)
    assert CrawlLog.query.order_by(CrawlLog.id.desc()).first().error_code == 'empty_extraction'
    crawl(db, source, articles=[ITEM])
    state = fresh(db, CrawlSourceState, source)
    assert (state.attention_reason, state.consecutive_failures) == (None, 0)


def test_old_crawl_message_is_only_a_request_and_never_runs(db, source, clock, sent):
    from app.crawlers.tasks import crawl_source
    assert crawl_source.run(source) == {'requested': 'queued'}
    assert CrawlLog.query.count() == 0 and sent == []
    state = fresh(db, CrawlSourceState, source)
    assert (state.next_due_at, state.due_reason) == (clock(), 'manual')


def test_a_request_while_running_does_not_queue_a_second_crawl(db, source, clock, sent):
    claim = claimed(source)
    before = fresh(db, CrawlSourceState, source).next_due_at
    assert runs.request_now(source) == 'running'
    assert fresh(db, CrawlSourceState, source).next_due_at == before
    FixtureCrawler(db.session.get(NewsSource, source), [ITEM]).run(claim)
    assert fresh(db, CrawlSourceState, source).due_reason == 'schedule'


def test_crawl_task_ignores_a_claim_that_is_no_longer_current(db, source, clock, sent, monkeypatch):
    claim = claimed(source)
    FixtureCrawler(db.session.get(NewsSource, source), [ITEM]).run(claim)
    fetched = []
    monkeypatch.setattr('app.crawlers.registry.get_crawler', lambda item: fetched.append(item))
    from app.crawlers.tasks import crawl_source
    assert crawl_source.run(source, claim.claim_id) is None
    assert fetched == []


def test_run_no_longer_rescans_old_unprocessed_articles(db, source, clock, sent):
    db.session.add(Article(source_id=source, external_id='old', url='https://test.invalid/old', title_fr='Old'))
    db.session.commit()
    crawl(db, source, articles=[ITEM])
    job = ArticleLLMJob.query.one()
    assert sent == [(PROCESS, [job.id], 'llm')]
    assert db.session.get(Article, job.article_id).external_id == 'guid-1'


def test_broker_outage_after_commit_leaves_a_queued_job_for_recovery(db, source, clock, monkeypatch):
    def down(self, *args, **kwargs):
        raise ConnectionError('broker down')
    monkeypatch.setattr('celery.app.base.Celery.send_task', down)
    assert crawl(db, source, articles=[ITEM]).status == 'success'
    job = ArticleLLMJob.query.one()
    assert job.state == 'queued'
    messages = []
    monkeypatch.setattr('celery.app.base.Celery.send_task',
                        lambda self, name, args=None, **options: messages.append((name, args)))
    later = article_jobs.now() + timedelta(seconds=130)
    monkeypatch.setattr(article_jobs, 'now', lambda: later)
    article_jobs.recover()
    assert messages == [(PROCESS, [job.id])]


def test_inactive_sources_are_never_claimed(db, source, clock, sent):
    item = db.session.get(NewsSource, source)
    item.is_active = False
    db.session.commit()
    from app.crawlers.tasks import dispatch_due_crawls
    assert dispatch_due_crawls.run() == {'dispatched': 0}
    assert runs.claim(source, due_only=False) is None
    assert runs.request_now(source) == 'inactive'
```

- [ ] **Step 3: 运行，确认失败**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_crawlers/test_crawl_runs.py -q`
Expected: FAIL（`ImportError: cannot import name 'runs'`）

- [ ] **Step 4: 实现** `app/crawlers/runs.py`

```python
"""Per-source run claims with fencing; the only way crawl results are written (spec §5).

Lock order everywhere: news_source -> crawl_source_state -> crawl_source_profile.
"""
from dataclasses import dataclass
from datetime import datetime
import logging
import uuid

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.crawl_runtime import CrawlSourceState
from app.models.crawl_schema import CrawlSourceProfile
from app.models.source import CrawlLog, NewsSource
from . import schedule

logger = logging.getLogger(__name__)


class RunLost(Exception):
    """The claim, fence, lease or activation changed; the caller must not write."""


@dataclass(frozen=True)
class Claim:
    source_id: int
    claim_id: str
    fence: int
    log_id: int
    activation_generation: int
    started_at: datetime


def _state(session, source_id):
    return session.scalar(select(CrawlSourceState).where(CrawlSourceState.source_id == source_id)
                          .with_for_update().execution_options(populate_existing=True))


def _activation(session, source_id):
    profile = session.scalar(select(CrawlSourceProfile).where(CrawlSourceProfile.source_id == source_id)
                             .with_for_update().execution_options(populate_existing=True))
    return profile.activation_generation if profile else 0


def _live(state, moment):
    return state.claim_id is not None and state.lease_expires_at is not None and state.lease_expires_at > moment


def _begin(session):
    # pysqlite legacy mode does not BEGIN before SELECT/SAVEPOINT; RELEASE would commit.
    connection = session.connection()
    if connection.dialect.name == 'sqlite' and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql('BEGIN')


def ensure_states(moment):
    """Give every active source a state row, computed with the normal rule (spec §12.1)."""
    try:
        with Session(db.engine) as session, session.begin():
            hour, zone = schedule.anchor_settings(session)
            rows = session.execute(
                select(NewsSource.id, NewsSource.last_crawled_at, NewsSource.crawl_frequency_minutes)
                .outerjoin(CrawlSourceState, CrawlSourceState.source_id == NewsSource.id)
                .where(NewsSource.is_active.is_(True), CrawlSourceState.source_id.is_(None))).all()
            for source_id, last, frequency in rows:
                due = moment if last is None else max(moment, schedule.next_due(
                    error_code=None, started=last, finished=last, frequency=frequency,
                    failures=0, retry_after=None, hour=hour, zone=zone))
                session.add(CrawlSourceState(source_id=source_id, next_due_at=due, due_reason='initial'))
    except IntegrityError:
        logger.info('Crawl state rows were created concurrently; retrying next round')


def claim(source_id, *, due_only):
    moment = schedule.now()
    with Session(db.engine) as session, session.begin():
        state = _state(session, source_id)
        source = session.get(NewsSource, source_id)
        if state is None or source is None or not source.is_active:
            return None
        if (due_only and state.next_due_at > moment) or _live(state, moment):
            return None
        if state.running_log_id is not None:
            old = session.get(CrawlLog, state.running_log_id)
            if old is not None and old.status == 'running':
                old.status, old.outcome, old.error_code, old.finished_at = 'failed', 'lease_expired', 'lease_expired', moment
        activation = _activation(session, source_id)
        identity = str(uuid.uuid4())
        log = CrawlLog(source_id=source_id, started_at=moment, status='running', claim_id=identity,
                       fence=state.fence + 1, activation_generation=activation)
        session.add(log)
        session.flush()
        state.fence, state.claim_id, state.due_reason = state.fence + 1, identity, 'claimed'
        state.lease_expires_at, state.running_log_id = moment + schedule.LEASE, log.id
        return Claim(source_id, identity, state.fence, log.id, activation, moment)


def claim_due(limit=50):
    moment = schedule.now()
    ensure_states(moment)
    with Session(db.engine) as session:
        ids = list(session.scalars(
            select(CrawlSourceState.source_id).join(NewsSource, NewsSource.id == CrawlSourceState.source_id)
            .where(NewsSource.is_active.is_(True), CrawlSourceState.next_due_at <= moment,
                   or_(CrawlSourceState.claim_id.is_(None), CrawlSourceState.lease_expires_at <= moment))
            .order_by(CrawlSourceState.next_due_at, CrawlSourceState.source_id).limit(limit)))
    return [item for item in (claim(source_id, due_only=True) for source_id in ids) if item is not None]


def current(source_id, claim_id):
    moment = schedule.now()
    with Session(db.engine) as session:
        state = session.get(CrawlSourceState, source_id)
        if state is None or state.claim_id != claim_id or not _live(state, moment):
            return None
        log = session.get(CrawlLog, state.running_log_id)
        return Claim(source_id, claim_id, state.fence, log.id, log.activation_generation or 0, log.started_at)


def lock(session, claim):
    """Inside the final transaction: lock rows and prove the claim is still current."""
    _begin(session)
    session.scalar(select(NewsSource.id).where(NewsSource.id == claim.source_id).with_for_update())
    state = _state(session, claim.source_id)
    if (state is None or state.claim_id != claim.claim_id or state.fence != claim.fence
            or not _live(state, schedule.now())
            or _activation(session, claim.source_id) != claim.activation_generation):
        raise RunLost()
    return state


def settle(session, state, claim, *, status, route, error_code=None, found=0, new=0, retry_after=None, message=None):
    """Finish a claimed run in the caller's final transaction: log, schedule, attention, lease."""
    moment = schedule.now()
    source = session.get(NewsSource, claim.source_id)
    category = schedule.kind(error_code)
    failures = 0 if category == 'ok' else state.consecutive_failures + 1
    hour, zone = schedule.anchor_settings(session)
    state.next_due_at = schedule.next_due(
        error_code=error_code, started=claim.started_at, finished=moment, frequency=source.crawl_frequency_minutes,
        failures=failures, retry_after=retry_after, hour=hour, zone=zone)
    state.due_reason = {'ok': 'schedule', 'retry': 'retry', 'blocked': 'cooldown', 'extraction': 'schedule'}[category]
    state.consecutive_failures = failures
    state.claim_id = state.lease_expires_at = state.running_log_id = None
    if category == 'ok':
        source.last_crawled_at = moment
        state.attention_reason = state.attention_since = None
    elif category == 'blocked' or (category == 'extraction' and failures >= schedule.EXTRACTION_ATTENTION):
        reason = error_code if category == 'blocked' else 'extraction_failed'
        if state.attention_reason != reason:
            state.attention_reason, state.attention_since = reason, moment
    log = session.get(CrawlLog, claim.log_id)
    log.status = 'success' if category == 'ok' else 'failed'
    log.outcome = status if category == 'ok' else ('blocked' if category == 'blocked' else 'failed')
    log.route, log.error_code = log.route or route, error_code
    log.articles_found, log.articles_new = found, new
    text = message or error_code
    log.error_message = text[:2000] if text else None
    log.finished_at = moment


def mark_stale(claim):
    moment = schedule.now()
    with Session(db.engine) as session, session.begin():
        state = _state(session, claim.source_id)
        log = session.get(CrawlLog, claim.log_id)
        if log is not None and log.status == 'running':
            log.status, log.outcome, log.finished_at = 'failed', 'stale', moment
        if state is not None and state.claim_id == claim.claim_id and state.fence == claim.fence:
            state.claim_id = state.lease_expires_at = state.running_log_id = None


def abandon(claim, *, route, error_code, found=0, retry_after=None, message=None):
    """Record a failed claimed run in its own transaction; a lost claim only marks its log stale."""
    try:
        with Session(db.engine) as session, session.begin():
            state = lock(session, claim)
            settle(session, state, claim, status='failed', route=route, error_code=error_code, found=found,
                   retry_after=retry_after, message=message)
    except RunLost:
        mark_stale(claim)
    except SQLAlchemyError:
        logger.warning('Crawl failure for source %s could not be recorded; the lease will expire', claim.source_id)


def request_now(source_id):
    """Admin/old-message request: due now unless a live claim is already running (spec §5.6)."""
    moment = schedule.now()
    with Session(db.engine) as session, session.begin():
        source = session.get(NewsSource, source_id)
        if source is None or not source.is_active:
            return 'inactive'
        state = _state(session, source_id)
        if state is None:
            session.add(CrawlSourceState(source_id=source_id, next_due_at=moment, due_reason='manual'))
            return 'queued'
        if _live(state, moment):
            return 'running'
        state.next_due_at, state.due_reason = min(state.next_due_at, moment), 'manual'
        return 'queued'


def execute(source_id, claim_id):
    """Run a current claim. Task 8 adds the approved-schema route before the legacy one."""
    from app.crawlers import registry
    claim = current(source_id, claim_id)
    if claim is None:
        return None
    try:
        crawler = registry.get_crawler(db.session.get(NewsSource, source_id))
    except Exception as exc:
        abandon(claim, route='legacy', error_code='crawler_error', message=str(exc))
        return None
    return crawler.run(claim)
```

- [ ] **Step 5: 改造 `app/crawlers/base.py`**

imports 增加 `from sqlalchemy import select` 与 `from sqlalchemy.exc import SQLAlchemyError`（保留 `IntegrityError`）。删除 `dedup()`、`save()` 与旧 `run()`，新增：

```python
class LegacyFailure(Exception):
    """A classified legacy failure; its code feeds the schedule (spec §5.4)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def failure_code(exc):
    """Map a legacy exception to (crawl error code, Retry-After seconds or None)."""
    from celery.exceptions import SoftTimeLimitExceeded
    if isinstance(exc, LegacyFailure):
        return exc.code, None
    if isinstance(exc, SoftTimeLimitExceeded):
        return 'timeout', None
    if isinstance(exc, FetchError):
        return exc.code, exc.retry_after
    if isinstance(exc, requests.Timeout):
        return 'timeout', None
    if isinstance(exc, requests.ConnectionError):
        return 'network_error', None
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        if status == 429:
            hint = exc.response.headers.get('Retry-After', '')
            return 'rate_limited', int(hint) if hint.isdigit() else None
        if status == 408:
            return 'timeout', None
        if status >= 500:
            return 'server_error', None
        return ('forbidden' if status in (401, 403) else 'http_error'), None
    if isinstance(exc, SQLAlchemyError):
        return 'database_error', None
    if isinstance(exc, ValueError):
        return 'invalid_article', None
    return 'crawler_error', None
```

`BaseCrawler` 内：

```python
    def _validated(self, articles):
        """Normalize entries; any invalid required field fails the whole run (as before)."""
        from app.utils.text import strip_html
        rows = []
        for raw in articles:
            title = strip_html(raw.title)
            url = urlsplit(raw.url)
            if (not title or not title.strip() or len(title) > 500
                    or url.scheme not in {'http', 'https'} or not url.hostname
                    or url.username is not None or url.password is not None
                    or len(raw.url) > 1000 or any(ord(c) < 32 for c in raw.url)
                    or not raw.external_id or len(raw.external_id) > 500):
                raise ValueError('Invalid article title, HTTP(S) URL or external identity')
            published_at = raw.published_at
            if published_at is not None and published_at.tzinfo is not None:
                published_at = published_at.astimezone(timezone.utc).replace(tzinfo=None)
            rows.append(dict(external_id=raw.external_id, url=raw.url, title_fr=title,
                             content_fr=strip_html(raw.content), author=(raw.author or '')[:200] or None,
                             image_url=(raw.image_url or '')[:1000] or None, published_at=published_at))
        return rows

    def _insert(self, session, rows):
        """Insert unseen identities; a competing insert of the same identity is tolerated."""
        seen = set(session.scalars(select(Article.external_id).where(
            Article.source_id == self.source.id, Article.external_id.in_([r['external_id'] for r in rows]))))
        ids = []
        for row in rows:
            if row['external_id'] in seen:
                continue
            seen.add(row['external_id'])
            article = Article(source_id=self.source.id, **row)
            try:
                with session.begin_nested():
                    session.add(article)
                    session.flush()
            except IntegrityError:
                # Current read on MySQL also sees a concurrent commit. Do not mask other violations.
                if session.scalar(select(Article.id).where(Article.source_id == self.source.id,
                                  Article.external_id == row['external_id']).with_for_update()) is None:
                    raise
                continue
            ids.append(article.id)
        return ids

    def run(self, claim) -> CrawlResult:
        """Fetch without locks, then write articles, LLM jobs, log and schedule in one claimed commit."""
        from app.crawlers import runs
        from app.llm import article_jobs
        result, jobs = CrawlResult(), []
        name = self.source.name
        try:
            raw_articles = self.fetch_articles()
            result.articles_found = len(raw_articles)
            if not raw_articles and not self.empty_result_is_valid:
                raise LegacyFailure('empty_extraction', 'Empty extraction without evidence of a valid empty source')
            rows = self._validated(raw_articles)
            with Session(db.engine) as session, session.begin():
                state = runs.lock(session, claim)
                ids = self._insert(session, rows) if rows else []
                jobs = [job for job in (article_jobs.enqueue(session, article_id, 'crawl', crawl_log_id=claim.log_id)
                                        for article_id in ids) if job]
                result.articles_new = len(ids)
                result.status = 'success' if ids else 'no_change'
                runs.settle(session, state, claim, status=result.status, route='legacy',
                            found=result.articles_found, new=result.articles_new)
        except runs.RunLost:
            runs.mark_stale(claim)
            result.status, result.articles_new, result.errors = 'stale', 0, ['stale_claim']
            return result
        except Exception as exc:
            code, retry_after = failure_code(exc)
            result.status, result.articles_new, result.retry_after = 'failed', 0, retry_after
            result.errors.append(str(exc))
            self.logger.error('Crawl failed for %s: %s', name, exc)
            runs.abandon(claim, route='legacy', error_code=code, found=result.articles_found,
                         retry_after=retry_after, message=str(exc))
            return result
        for identity in jobs:
            article_jobs.publish(identity)
        self.logger.info('Crawled %s: found=%s new=%s status=%s', name,
                         result.articles_found, result.articles_new, result.status)
        return result
```

先 `grep -rn "\.save(\|\.dedup(\|def save\|def dedup" app scripts` 确认没有子类或脚本依赖被删除的方法；若有，改为调用 `_validated/_insert` 或在本步骤中一并删除。

- [ ] **Step 6: 改造 `app/crawlers/tasks.py`**

把 `crawl_source` 与 `_enqueue_llm_processing` 替换为：

```python
@celery.task(name='app.crawlers.tasks.crawl_source', queue='crawl', ignore_result=True,
             soft_time_limit=600, time_limit=660)
def crawl_source(source_id: int, claim_id: str | None = None):
    """Run one claimed crawl. A message without a claim (older senders) is only a request."""
    from app.crawlers import runs
    if claim_id is None:
        return {'requested': runs.request_now(source_id)}
    result = runs.execute(source_id, claim_id)
    return None if result is None else {'status': result.status}


@celery.task(name='app.crawlers.tasks.dispatch_due_crawls', queue='crawl', ignore_result=True)
def dispatch_due_crawls():
    """Claim due sources (at most 50) and send only their IDs; lease expiry covers lost sends."""
    from app.crawlers import runs
    claims = runs.claim_due(limit=50)
    for item in claims:
        try:
            celery.send_task('app.crawlers.tasks.crawl_source', args=[item.source_id, item.claim_id], queue='crawl')
        except Exception:
            logger.warning('Crawl dispatch unavailable for source %s; the lease will expire', item.source_id)
    return {'dispatched': len(claims)}
```

删除模块顶部不再使用的 `get_crawler` import（保留 `discover_crawlers()` 调用）。`crawl_all_sources` 与 `schedule_due_crawls` 暂不动（Task 9 处理）。

- [ ] **Step 7: 迁移 `tests/test_crawlers/test_legacy_pipeline.py`**

- 顶部加 `from tests.support.runs import claimed`。
- 每处 `X.run()`（`FixtureCrawler(...)`、`HTMLCrawler(source)`、`RSSCrawler(source)`）改为 `X.run(claimed(source.id))`。`test_run_deduplicates_batch_and_repeated_crawls` 中第二次运行用新的 `claimed(source.id)`，并把 `crawler` 重建为 `FixtureCrawler(source, [item, item])`（同一对象复用也可以）。
- 删除三个依赖 Celery retry 的测试（`test_transient_http_failure_requests_celery_retry`、`test_forbidden_source_is_reported_without_learning_or_retry`、`test_celery_retry_preserves_server_retry_after`），换成：

```python
@pytest.mark.parametrize('status, code, wait', [(429, 'rate_limited', 15), (503, 'server_error', 15)])
def test_transient_http_failure_is_rescheduled_not_retried_by_celery(db, source, fetch_network, status, code, wait):
    from app.crawlers import schedule
    from app.models.crawl_runtime import CrawlSourceState
    fetch_network.configure(routes={source.feed_url: {'status': status}})
    claim = claimed(source.id)
    result = RSSCrawler(source).run(claim)
    assert result.status == 'failed'
    assert [e['url'] for e in fetch_network.events() if e['kind'] == 'http'] == ['https://test.invalid/robots.txt', source.feed_url]
    db.session.remove()
    log = CrawlLog.query.one()
    assert (log.status, log.outcome, log.error_code) == ('failed', 'failed', code)
    state = db.session.get(CrawlSourceState, source.id)
    assert timedelta(minutes=wait - 1) <= state.next_due_at - log.finished_at <= timedelta(minutes=wait)


def test_forbidden_source_is_blocked_for_a_day_with_attention(db, source, fetch_network):
    from app.models.crawl_runtime import CrawlSourceState
    fetch_network.configure(routes={source.feed_url: {'status': 403}})
    assert RSSCrawler(source).run(claimed(source.id)).errors == ['forbidden']
    db.session.remove()
    log, state = CrawlLog.query.one(), db.session.get(CrawlSourceState, source.id)
    assert (log.outcome, log.error_code, state.attention_reason) == ('blocked', 'forbidden', 'forbidden')
    assert state.next_due_at - log.finished_at == timedelta(hours=24)


def test_server_retry_after_sets_the_next_attempt(db, source, fetch_network):
    from app.models.crawl_runtime import CrawlSourceState
    fetch_network.configure(routes={source.feed_url: {'status': 429, 'headers': {'Retry-After': '3600'}}})
    RSSCrawler(source).run(claimed(source.id))
    db.session.remove()
    log, state = CrawlLog.query.one(), db.session.get(CrawlSourceState, source.id)
    assert state.next_due_at - log.finished_at == timedelta(hours=1)
```

（文件顶部 `from datetime import datetime, timedelta`。若 SafeFetcher 对 403 抛出的 FetchError code 不是 `forbidden`，以实际 code 为准并确认它属于 `schedule.BLOCKED`。）

- [ ] **Step 8: 运行相关测试**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_crawlers/test_crawl_runs.py tests/test_crawlers/test_legacy_pipeline.py tests/test_crawlers/test_crawl_schedule.py -q`
Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add app/crawlers/runs.py app/crawlers/base.py app/crawlers/tasks.py tests/support/runs.py tests/test_crawlers/test_crawl_runs.py tests/test_crawlers/test_legacy_pipeline.py
git commit -m "feat(crawl): claimed runs with fencing, unified settlement and outbox for legacy crawlers"
```

---

### Task 5: 新引擎路径接入认领与 outbox

**Files:**
- Modify: `app/crawlers/_ingestion.py`、`app/crawlers/engine.py`（`run`）、`app/crawlers/contracts.py`
- Modify: `scripts/run_recipe.py`
- Modify: `tests/test_crawlers/test_engine.py`

**Interfaces:**
- Consumes: `runs.lock/settle/abandon/mark_stale/RunLost`（Task 4）、`article_jobs.enqueue/publish`（Task 2）、`schedule.kind`（Task 3）。
- Produces: `CrawlEngine.run(claim) -> CrawlOutcome`（`run_id == claim.log_id`；丢失认领时 `status='failed'` 且 errors 含 `CrawlError(stage='persistence', code='stale_claim')`）。

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_crawlers/test_engine.py`，顶部 `from tests.support.runs import claimed`）

```python
def test_engine_run_queues_crawl_and_upgrade_jobs_in_the_same_commit(db, news_source, fetch_network, monkeypatch):
    from app.models.crawl_runtime import ArticleLLMJob
    sent = []
    monkeypatch.setattr('celery.app.base.Celery.send_task',
                        lambda self, name, args=None, **options: sent.append((name, args)))
    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'body': '<article><h2><a href="/research">Recherche</a></h2></article>'}})
    first = engine(recipe(news_source.id)).run(claimed(news_source.id))
    job = ArticleLLMJob.query.one()
    assert (first.status, job.trigger, job.article_id) == ('success', 'crawl', first.article_ids[0])
    assert sent == [('app.llm.article_tasks.process', [job.id])]


def test_engine_run_with_a_lost_claim_writes_nothing(db, news_source, fetch_network, monkeypatch):
    from datetime import timedelta
    from app.crawlers import schedule
    from app.models.article import Article
    from app.models.crawl_runtime import ArticleLLMJob
    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'body': '<article><h2><a href="/research">Recherche</a></h2></article>'}})
    claim = claimed(news_source.id)
    later = schedule.now() + timedelta(minutes=16)
    monkeypatch.setattr(schedule, 'now', lambda: later)
    outcome = engine(recipe(news_source.id)).run(claim)
    assert outcome.status == 'failed' and outcome.errors[-1].code == 'stale_claim'
    assert Article.query.count() == 0 and ArticleLLMJob.query.count() == 0
```

同时把本文件每处 `engine(...).run()`、`crawler.run()`、`RSSCrawler(news_source).run()` 改为 `.run(claimed(news_source.id))`；`test_replay_is_preview_only...` 改为 `engine(recipe(news_source.id), snapshots=()).run(claimed(news_source.id))`（仍应先抛 `ValueError`）。`test_metadata_upgrade_preserves_the_existing_guid_and_requeues_enrichment` 追加断言：升级后的文章有一个 `trigger == 'upgrade'` 的 queued 任务。

- [ ] **Step 2: 运行，确认失败**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_crawlers/test_engine.py -q`
Expected: FAIL（`run() takes 1 positional argument but 2 were given`）

- [ ] **Step 3: 实现**

`app/crawlers/contracts.py`：`CrawlError` 的 persistence 集合改为 `{'database_error', 'stale_claim'}`。

`app/crawlers/engine.py`：

```python
    def run(self, claim) -> CrawlOutcome:
        if self.snapshots is not None:
            raise ValueError('Replay is preview-only')
        from ._ingestion import run
        return run(self, claim)
```

`app/crawlers/_ingestion.py`：`run(engine)` 改为 `run(engine, claim)`，要点：
1. 开头的 source 读取与 `source_input` 保持不变；**删除**自建 `CrawlLog` 的事务，`run_id` 一律用 `claim.log_id`。
2. 最终事务第一句 `state = runs.lock(session, claim)`，其后的 `session.query(NewsSource)...with_for_update()` 保留（已被锁，读取当前行）。
3. 循环里 `session.flush()` / `ids.append(article.id)` 之后加：

```python
                job = article_jobs.enqueue(session, article.id, 'upgrade' if updated_now else 'crawl',
                                           crawl_log_id=claim.log_id)
                if job:
                    jobs.append(job)
```

   其中 `updated_now` 在进入 `if existing:` 分支时设为 True、新建分支设为 False（循环开头 `updated_now = False`）。
4. 删除循环后 `source.last_crawled_at = ...` 这一段（改由 `runs.settle` 在成功时写）。
5. `status` 计算保持不变，然后：

```python
            code = _error_code(status, errors)
            runs.settle(session, state, claim, status='partial' if status == 'degraded' else status,
                        route='schema', error_code=code, found=quality.discovered, new=new)
            outcome = CrawlOutcome(run_id=claim.log_id, status=status, quality=quality,
                                   article_ids=tuple(ids), errors=tuple(errors))
```

6. 异常处理改为：

```python
    except runs.RunLost:
        runs.mark_stale(claim)
        return CrawlOutcome(run_id=claim.log_id, status='failed',
                            quality=replace(preview.quality, no_change_reason=None),
                            errors=tuple(errors) + (CrawlError(stage='persistence', code='stale_claim'),))
    except (SQLAlchemyError, ValueError) as exc:
        code = 'database_error' if isinstance(exc, SQLAlchemyError) else 'invalid_article'
        errors.append(CrawlError(stage='persistence' if isinstance(exc, SQLAlchemyError) else 'extraction', code=code))
        runs.abandon(claim, route='schema', error_code=code, found=preview.quality.discovered)
        return CrawlOutcome(run_id=claim.log_id, status='failed',
                            quality=replace(preview.quality, no_change_reason=None), errors=tuple(errors))
    for identity in jobs:
        article_jobs.publish(identity)
    return outcome
```

7. 删除 `_finish_log`；新增：

```python
def _error_code(status, errors):
    """The error code that drives the schedule; None for results that were written."""
    if status in ('success', 'no_change', 'partial', 'degraded'):
        return None
    codes = [error.code for error in errors]
    for category in ('blocked', 'retry'):
        chosen = [code for code in codes if schedule.kind(code) == category]
        if chosen:
            return chosen[0]
    return codes[0] if codes else 'no_evidence'
```

   文件顶部 imports：`from . import runs, schedule`、`from app.llm import article_jobs`，并删除不再使用的 `CrawlLog`、`datetime` import（若仍被使用则保留）。

`scripts/run_recipe.py` 的 `--apply` 分支：在构造 engine 之后、调用 `run` 之前：

```python
        from app.crawlers import runs, schedule
        runs.ensure_states(schedule.now())
        claim = runs.claim(source_id, due_only=False)
        if claim is None:
            print('Source is disabled or already running; nothing applied')
            return 1
        outcome = engine.run(claim)
```

- [ ] **Step 4: 运行，确认通过**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_crawlers -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/crawlers/_ingestion.py app/crawlers/engine.py app/crawlers/contracts.py scripts/run_recipe.py tests/test_crawlers/test_engine.py
git commit -m "feat(crawl): schema engine runs under claims and writes the LLM outbox"
```

---

### Task 6: 批准与拒绝（证据门槛、CAS、审计、页面）

**Files:**
- Create: `app/crawlers/activation.py`、`app/web/views/crawl_activation.py`、`tests/test_web/test_crawl_activation.py`
- Modify: `app/web/views/crawl_config.py`（注册子蓝图、`index`、`version`、`preview_report` 复用 `report_is_current`）
- Modify: `app/web/templates/admin/crawl_config.html`、`crawl_schema_version.html`

**Interfaces:**
- Consumes: 模型（Task 1）、`schedule.now`（Task 3）、`validation.view(session, identity)`、`_source_policy.latest/state/matches_report`。
- Produces:
  - `activation.Refused(status, message)`
  - `activation.learning_identity(version_id) -> str | None`、`report_is_current(report, source, profile, candidate) -> bool`、`eligible_reports(source, profile, candidate) -> list`、`rejected(version_id) -> bool`、`label(profile, candidate) -> str`
  - `activation.approve(source_id, version_id, actor_id, expected: str, report_id: str | None = None)`、`activation.reject(source_id, version_id, actor_id, expected, reason='')`
  - 路由：`POST /admin/sources/<id>/crawl-config/versions/<vid>/approve`、`.../reject`（端点 `admin.crawl_config.activation.approve/reject`）
  - 页面：`form[data-approve]`、`select[data-approval-reports]`、`[data-approval-evidence]`、`form[data-reject]`；配置页 `[data-active-version]`、`[data-previous-version]`、`[data-activation-generation]`、`[data-decision]`

- [ ] **Step 1: 写失败测试** `tests/test_web/test_crawl_activation.py`

```python
"""Approval through real Admin forms: evidence, CAS and audit (spec §4.1–4.2)."""
from datetime import timedelta

import pytest
from bs4 import BeautifulSoup

from app.crawlers import schedule
from app.models.crawl_runtime import CrawlSchemaDecision, CrawlSourceState
from app.models.crawl_schema import CrawlSourceProfile
from tests.test_web import test_crawl_policy as policy
from tests.test_web import test_crawl_preview as preview
from tests.test_web import test_crawl_validation as validation

source = preview.source
fetch_network = preview.fetch_network
evidence_dir = validation.evidence_dir
learning_io = validation.learning_io
model = validation.model


def ready_report(client, source_id, csrf_token, fetch_network):
    policy.save_policy(client, source_id)
    version = preview.save_candidate(client, source_id, csrf_token)
    action, form = preview.preview_form(client, version)
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': preview.FEED, 'headers': {'Content-Type': 'application/rss+xml'}}})
    response = client.post(action, data=form)
    assert response.status_code == 302
    return version, response.location.rstrip('/').rsplit('/', 1)[1]


def decision_form(client, page_url, selector):
    page = BeautifulSoup(client.get(page_url).text, 'html.parser')
    form = page.select_one(selector)
    assert form is not None
    fields = {item['name']: item.get('value', '') for item in form.select('input[name]')}
    options = [option['value'] for option in form.select('select[name=report_id] option')]
    if options:
        fields['report_id'] = options[0]
    return form['action'], fields


def approved(client, source_id, csrf_token, fetch_network):
    version, _ = ready_report(client, source_id, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-approve]')
    assert client.post(action, data=fields).status_code == 302
    return version


def test_approving_a_current_preview_activates_it_and_schedules_it_now(app, db, client, source, csrf_token, fetch_network):
    version, report_id = ready_report(client, source, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-approve]')
    assert fields['report_id'] == report_id
    requests = len(fetch_network.events())
    assert client.post(action, data=fields).status_code == 302
    assert len(fetch_network.events()) == requests
    with app.app_context():
        page = BeautifulSoup(client.get(version).text, 'html.parser')
        assert page.select_one('[data-version-status]').get_text(strip=True) == 'Active'
        index = BeautifulSoup(client.get(f'/admin/sources/{source}/crawl-config').text, 'html.parser')
        assert index.select_one('[data-active-version]').get_text(strip=True) == version.rsplit('/', 1)[1]
        assert index.select_one('[data-activation-generation]').get_text(strip=True) == '1'
        assert f'preview {report_id}' in index.select_one('[data-decision]').get_text()
        assert client.get('/api/v1/news').json['total'] == 0
    db.session.remove()
    state = db.session.get(CrawlSourceState, source)
    assert state.due_reason == 'activation'


def test_a_second_form_loaded_before_a_decision_is_refused(db, client, source, csrf_token, fetch_network):
    version, _ = ready_report(client, source, csrf_token, fetch_network)
    first = decision_form(client, version, 'form[data-approve]')
    second = decision_form(client, version, 'form[data-reject]')
    assert client.post(first[0], data=first[1]).status_code == 302
    assert client.post(second[0], data=second[1]).status_code == 409
    assert CrawlSchemaDecision.query.count() == 1


@pytest.mark.parametrize('change', ['source_edit', 'too_old', 'policy_revoked'])
def test_stale_or_old_preview_evidence_cannot_approve(db, client, source, csrf_token, fetch_network, monkeypatch, change):
    version, report_id = ready_report(client, source, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-approve]')
    if change == 'source_edit':
        preview.edit_source(client, source, csrf_token, url='https://news.test.invalid/moved')
    elif change == 'too_old':
        later = schedule.now() + timedelta(hours=25)
        monkeypatch.setattr(schedule, 'now', lambda: later)
    else:
        revoke_action, revoke_fields = policy.revoke_form(client, source)
        assert client.post(revoke_action, data=revoke_fields).status_code == 302
    fields['report_id'] = report_id
    assert client.post(action, data=fields).status_code == 409
    db.session.remove()
    assert CrawlSourceProfile.query.filter_by(source_id=source).one().active_version_id is None


def test_a_preview_without_a_saved_policy_is_not_evidence(db, client, source, csrf_token, fetch_network):
    version = preview.save_candidate(client, source, csrf_token)
    action, form = preview.preview_form(client, version)
    form.update(allowed_hosts='news.test.invalid', quality_kind='news')
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': preview.FEED, 'headers': {'Content-Type': 'application/rss+xml'}}})
    report = client.post(action, data=form).location.rstrip('/').rsplit('/', 1)[1]
    approve_action, fields = decision_form(client, version, 'form[data-approve]')
    assert 'report_id' not in fields
    fields['report_id'] = report
    assert client.post(approve_action, data=fields).status_code == 409


def test_rejected_candidates_cannot_be_approved(db, client, source, csrf_token, fetch_network):
    version, report_id = ready_report(client, source, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-reject]')
    fields['reason'] = 'Selectors pick navigation links'
    assert client.post(action, data=fields).status_code == 302
    page = BeautifulSoup(client.get(version).text, 'html.parser')
    assert page.select_one('[data-version-status]').get_text(strip=True) == 'Rejected'
    approve_action, approve_fields = decision_form(client, version, 'form[data-approve]')
    approve_fields['report_id'] = report_id
    assert client.post(approve_action, data=approve_fields).status_code == 409


@pytest.mark.parametrize('field', ['active_version_id', 'actor_id', 'evidence_hash', 'status'])
def test_decision_forms_reject_server_owned_fields(client, source, csrf_token, fetch_network, field):
    version, _ = ready_report(client, source, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-approve]')
    fields[field] = 'untrusted'
    assert client.post(action, data=fields).status_code == 400


def test_decisions_require_admin_and_csrf(app, db, client, source, csrf_token, fetch_network):
    version, _ = ready_report(client, source, csrf_token, fetch_network)
    action, fields = decision_form(client, version, 'form[data-approve]')
    assert client.post(action, data={k: v for k, v in fields.items() if k != 'csrf_token'}).status_code == 400
    # An anonymous client is stopped by CSRF or the admin guard; either way nothing is decided.
    assert app.test_client().post(action, data=fields).status_code in (302, 400, 401, 403)
    db.session.remove()
    assert CrawlSchemaDecision.query.count() == 0


def test_learned_candidate_needs_a_passed_holdout(client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    item = validation.learned(client, source, csrf_token, fetch_network, learning_io, model)
    candidate = BeautifulSoup(client.get(item.location).text, 'html.parser').select_one('a[data-learning-candidate]')['href']
    action, fields = decision_form(client, candidate, 'form[data-approve]')
    assert client.post(action, data=fields).status_code == 409
    validation.capture(client, item.base, fetch_network, 'holdout')
    validation.check(client, item)
    action, fields = decision_form(client, candidate, 'form[data-approve]')
    assert client.post(action, data=dict(fields, report_id='1')).status_code == 400
    assert client.post(action, data=fields).status_code == 302
    page = BeautifulSoup(client.get(candidate).text, 'html.parser')
    assert page.select_one('[data-version-status]').get_text(strip=True) == 'Active'
    index = BeautifulSoup(client.get(f'/admin/sources/{source}/crawl-config').text, 'html.parser')
    assert 'holdout' in index.select_one('[data-decision]').get_text()
```

- [ ] **Step 2: 运行，确认失败**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_web/test_crawl_activation.py -q`
Expected: FAIL（找不到 `form[data-approve]`）

- [ ] **Step 3: 实现** `app/crawlers/activation.py`

```python
"""Human approval of crawl recipes: evidence, CAS on activation_generation and audit (spec §4).

Runs inside the Admin request transaction (db.session). Lock order: source -> state -> profile.
"""
from datetime import timedelta
import hashlib
import json

from sqlalchemy import select

from app.extensions import db
from app.models.crawl_learning import CrawlRepairAttempt
from app.models.crawl_runtime import CrawlSchemaDecision, CrawlSourceState
from app.models.crawl_schema import CrawlPreviewReport, CrawlSchemaVersion, CrawlSourceProfile
from app.models.source import NewsSource
from . import _source_policy, schedule
from ._preview import source_fingerprint
from .schema import validate_recipe

EVIDENCE_AGE = timedelta(hours=24)


class Refused(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def learning_identity(version_id):
    return db.session.scalar(select(CrawlRepairAttempt.session_id).where(
        CrawlRepairAttempt.candidate_id == version_id).limit(1))


def report_is_current(report, source, profile, candidate):
    from .engine import CrawlEngine
    return not (report.status == 'stale' or not source.is_active or report.generation != profile.generation
                or report.source_fingerprint != source_fingerprint(source)
                or report.recipe_hash != candidate.recipe_hash or report.engine_version != CrawlEngine.VERSION
                or not _source_policy.matches_report(_source_policy.latest(profile), source, profile, report.report))


def _usable(report, source, profile, candidate):
    return (report.status == 'ready' and report.report.get('source_policy') is not None
            and report.created_at >= schedule.now() - EVIDENCE_AGE
            and report_is_current(report, source, profile, candidate))


def eligible_reports(source, profile, candidate):
    reports = (CrawlPreviewReport.query.filter_by(version_id=candidate.id, status='ready')
               .order_by(CrawlPreviewReport.id.desc()).limit(20).all())
    return [report for report in reports if _usable(report, source, profile, candidate)]


def rejected(version_id):
    return db.session.scalar(select(CrawlSchemaDecision.id).where(
        CrawlSchemaDecision.version_id == version_id, CrawlSchemaDecision.action == 'reject').limit(1)) is not None


def label(profile, candidate):
    if candidate.id == profile.active_version_id:
        return 'Active'
    if rejected(candidate.id):
        return 'Rejected'
    if candidate.id == profile.previous_version_id:
        return 'Previous'
    return candidate.status.capitalize()


def _locked(source_id, expected):
    source = NewsSource.query.filter_by(id=source_id).populate_existing().with_for_update().first()
    if source is None:
        raise Refused(404, 'Source not found')
    state = CrawlSourceState.query.filter_by(source_id=source_id).populate_existing().with_for_update().first()
    if state is None:
        state = CrawlSourceState(source_id=source_id, next_due_at=schedule.now(), due_reason='activation')
        db.session.add(state)
    profile = CrawlSourceProfile.query.filter_by(source_id=source_id).populate_existing().with_for_update().first()
    if profile is None:
        raise Refused(404, 'No crawl profile for this source')
    if expected != str(profile.activation_generation):
        raise Refused(409, 'Activation changed; reload before deciding')
    return source, state, profile


def _candidate(profile, version_id):
    candidate = db.session.get(CrawlSchemaVersion, version_id)
    if candidate is None or candidate.profile_id != profile.id:
        raise Refused(404, 'Candidate not found')
    return candidate


def _policy(source, profile):
    record = _source_policy.latest(profile)
    if _source_policy.state(record, source, profile) != 'effective':
        raise Refused(409, 'Source policy is not effective')
    return record


def _valid_recipe(candidate):
    try:
        recipe = validate_recipe(candidate.recipe)
    except ValueError:
        raise Refused(409, 'Recipe no longer validates') from None
    if recipe.fingerprint != candidate.recipe_hash:
        raise Refused(409, 'Recipe changed')


def _decide(profile, action, actor_id, *, version_id=None, from_version_id=None, record=None,
            evidence=(None, None, None), reason=None):
    kind, ref, digest = evidence
    db.session.add(CrawlSchemaDecision(
        profile_id=profile.id, action=action, version_id=version_id, from_version_id=from_version_id,
        activation_generation=profile.activation_generation, evidence_kind=kind, evidence_ref=ref,
        evidence_hash=digest, source_generation=profile.source_generation,
        policy_version_id=record.id if record else None, actor_id=actor_id, reason=reason,
        created_at=schedule.now()))


def approve(source_id, version_id, actor_id, expected, report_id=None):
    from . import validation
    source, state, profile = _locked(source_id, expected)
    candidate = _candidate(profile, version_id)
    if not source.is_active:
        raise Refused(409, 'Source is disabled')
    record = _policy(source, profile)
    if candidate.id == profile.active_version_id:
        raise Refused(409, 'Already active')
    if rejected(candidate.id):
        raise Refused(409, 'Rejected candidates cannot be approved')
    _valid_recipe(candidate)
    identity = learning_identity(candidate.id)
    if identity:
        if report_id is not None:
            raise Refused(400, 'Learned candidates are approved on holdout validation')
        view = validation.view(db.session, identity)
        if view is None or view.state != 'passed':
            raise Refused(409, 'Holdout validation has not passed')
        evidence = ('holdout', identity, _digest(view.result))
    else:
        if report_id is None or not report_id.isdigit():
            raise Refused(400, 'Choose a preview report')
        report = db.session.get(CrawlPreviewReport, int(report_id))
        if report is None or report.version_id != candidate.id:
            raise Refused(404, 'Preview report not found')
        if not _usable(report, source, profile, candidate):
            raise Refused(409, 'Preview evidence is not current')
        evidence = ('preview', str(report.id), _digest(report.report))
    previous = profile.active_version_id
    profile.previous_version_id, profile.active_version_id = previous, candidate.id
    profile.active_source_generation = profile.source_generation
    profile.activation_generation += 1
    _decide(profile, 'approve', actor_id, version_id=candidate.id, from_version_id=previous,
            record=record, evidence=evidence)
    state.next_due_at, state.due_reason = schedule.now(), 'activation'
    db.session.commit()


def reject(source_id, version_id, actor_id, expected, reason=''):
    _, _, profile = _locked(source_id, expected)
    candidate = _candidate(profile, version_id)
    if candidate.id == profile.active_version_id:
        raise Refused(409, 'Retire or roll back the active version first')
    if rejected(candidate.id):
        raise Refused(409, 'Already rejected')
    _decide(profile, 'reject', actor_id, version_id=candidate.id, reason=(reason or '').strip()[:200] or None)
    db.session.commit()
```

`app/web/views/crawl_activation.py`：

```python
"""Approve, reject, roll back or retire crawl recipes through Admin forms (spec §4)."""
from flask import Blueprint, abort, flash, redirect, request, url_for
from flask_login import current_user

from app.crawlers import activation
from app.extensions import db

crawl_activation_bp = Blueprint('activation', __name__)
BASE = {'csrf_token', 'expected_activation'}


def _form(optional=()):
    names = set(request.form)
    if (not BASE <= names or names - BASE - set(optional) or request.files
            or any(len(values) != 1 for _, values in request.form.lists())):
        abort(400, description='Invalid decision form')
    return request.form


def _apply(operation, *args):
    try:
        operation(*args)
    except activation.Refused as refused:
        db.session.rollback()
        abort(refused.status, description=str(refused))


@crawl_activation_bp.route('/versions/<int:version_id>/approve', methods=['POST'])
def approve(source_id, version_id):
    form = _form(('report_id',))
    _apply(activation.approve, source_id, version_id, current_user.id, form['expected_activation'], form.get('report_id'))
    flash(f'Version {version_id} approved; the next crawl uses it.', 'success')
    return redirect(url_for('admin.crawl_config.index', source_id=source_id))


@crawl_activation_bp.route('/versions/<int:version_id>/reject', methods=['POST'])
def reject(source_id, version_id):
    form = _form(('reason',))
    _apply(activation.reject, source_id, version_id, current_user.id, form['expected_activation'], form.get('reason', ''))
    flash(f'Version {version_id} rejected.', 'success')
    return redirect(url_for('admin.crawl_config.version', source_id=source_id, version_id=version_id))
```

`app/web/views/crawl_config.py`：
- `from .crawl_activation import crawl_activation_bp` 并 `crawl_config_bp.register_blueprint(crawl_activation_bp)`；`from app.crawlers import activation`；`from app.models.crawl_runtime import CrawlSchemaDecision`。
- `index()` 渲染时额外传 `profile=profile` 与 `decisions=(CrawlSchemaDecision.query.filter_by(profile_id=profile.id).order_by(CrawlSchemaDecision.id.desc()).limit(50).all() if profile else [])`。
- `version()` 额外计算并传入：

```python
    from app.crawlers import validation
    identity = activation.learning_identity(candidate.id)
    view = validation.view(db.session, identity) if identity else None
    eligible = [] if identity else activation.eligible_reports(source, profile, candidate)
    version_label = activation.label(profile, candidate)
    approvable = (source.is_active and policy_state == 'effective' and version_label not in ('Active', 'Rejected')
                  and ((identity and view is not None and view.state == 'passed') or (not identity and eligible)))
```

  传入 `version_label, learning_identity=identity, validation_state=view.state if view else None, eligible_reports=eligible, approvable=approvable, activation_generation=profile.activation_generation`。
- `preview_report()` 中 `stale = (...)` 整段替换为 `stale = not activation.report_is_current(report, source, profile, candidate)`。

`crawl_schema_version.html`：
- 状态行改为 `<p>Status: <strong data-version-status>{{ version_label }}</strong></p>`。
- 把固定的 “Not approved and not used by scheduled crawling...” 提示改为 `{% if version_label != 'Active' %}...{% else %}<div class="alert alert-success">Scheduled crawls use this version.</div>{% endif %}`。
- 在 “Recent previews” 之前加：

```html
<h3>Decision</h3>
<form method="post" data-approve action="{{ url_for('admin.crawl_config.activation.approve', source_id=source.id, version_id=candidate.id) }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="hidden" name="expected_activation" value="{{ activation_generation }}">
    {% if learning_identity %}
    <p data-approval-evidence>Evidence: holdout validation of learning session {{ learning_identity }} —
        <strong>{{ validation_state or 'missing' }}</strong></p>
    {% else %}
    <label for="report_id" class="form-label">Evidence: a ready preview under the saved policy, less than 24 hours old</label>
    <select id="report_id" name="report_id" class="form-select" data-approval-reports>
        {% for report in eligible_reports %}
        <option value="{{ report.id }}">Preview {{ report.id }} — {{ report.created_at.strftime('%Y-%m-%d %H:%M UTC') }}</option>
        {% endfor %}
    </select>
    {% endif %}
    <button type="submit" class="btn btn-success my-2" {% if not approvable %}disabled{% endif %}>Approve for scheduled crawling</button>
</form>
<form method="post" data-reject action="{{ url_for('admin.crawl_config.activation.reject', source_id=source.id, version_id=candidate.id) }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="hidden" name="expected_activation" value="{{ activation_generation }}">
    <input type="text" name="reason" maxlength="200" class="form-control" placeholder="Reason (optional)">
    <button type="submit" class="btn btn-outline-danger my-2" {% if version_label in ('Active', 'Rejected') %}disabled{% endif %}>Reject</button>
</form>
```

`crawl_config.html`：把开头的 `alert alert-info` 块替换为：

```html
{% if profile and profile.active_version_id %}
<div class="alert alert-success" data-activation>
    Active recipe: version <a href="{{ url_for('admin.crawl_config.version', source_id=source.id, version_id=profile.active_version_id) }}"><span data-active-version>{{ profile.active_version_id }}</span></a>.
    Scheduled crawls use it; its failures are recorded and never sent to the legacy crawler.
</div>
{% else %}
<div class="alert alert-info">
    <strong>No active recipe.</strong> Scheduled crawls use the legacy crawler.
    Approve a candidate with current evidence to switch. Saving a candidate does not fetch pages, write articles or dispatch LLM tasks.
</div>
{% endif %}
<p>Activation generation: <span data-activation-generation>{{ profile.activation_generation if profile else 0 }}</span>
    · previous version: <span data-previous-version>{{ profile.previous_version_id if profile and profile.previous_version_id else 'none' }}</span></p>
<h3>Decisions (latest 50)</h3>
<ul>{% for decision in decisions %}
    <li data-decision>{{ decision.created_at.strftime('%Y-%m-%d %H:%M UTC') }} — {{ decision.action }}
        version {{ decision.version_id or decision.from_version_id }} by administrator #{{ decision.actor_id }}
        {% if decision.evidence_kind %}— {{ decision.evidence_kind }} {{ decision.evidence_ref }}{% endif %}
        {% if decision.reason %}— {{ decision.reason }}{% endif %}</li>
{% else %}<li>No decisions yet.</li>{% endfor %}</ul>
```

- [ ] **Step 4: 运行，确认通过**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_web/test_crawl_activation.py tests/test_web/test_crawl_config.py tests/test_web/test_crawl_preview.py tests/test_web/test_crawl_policy.py tests/test_web/test_crawl_validation.py tests/test_web/test_crawl_learning.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/crawlers/activation.py app/web/views/crawl_activation.py app/web/views/crawl_config.py app/web/templates/admin/crawl_config.html app/web/templates/admin/crawl_schema_version.html tests/test_web/test_crawl_activation.py
git commit -m "feat(admin): approve or reject crawl recipes on current evidence with CAS and audit"
```

---

### Task 7: 回滚到上一版与退回旧爬虫

**Files:**
- Modify: `app/crawlers/activation.py`、`app/web/views/crawl_activation.py`、`app/web/templates/admin/crawl_config.html`
- Create: `tests/test_web/test_crawl_rollback.py`

**Interfaces:**
- Consumes: Task 6 的 `_locked/_policy/_valid_recipe/_decide/Refused`、`approved()` 测试工具。
- Produces: `activation.rollback(source_id, actor_id, expected)`、`activation.retire(source_id, actor_id, expected)`；路由 `POST .../crawl-config/rollback`、`.../retire`；页面 `form[data-rollback]`、`form[data-retire]`。

- [ ] **Step 1: 写失败测试** `tests/test_web/test_crawl_rollback.py`

```python
"""Roll back to the previous recipe or return to the legacy crawler (spec §4.3–4.4)."""
import json

from bs4 import BeautifulSoup

from tests.test_web import test_crawl_activation as activation
from tests.test_web import test_crawl_preview as preview

source = preview.source
fetch_network = preview.fetch_network


def config(client, source_id):
    return BeautifulSoup(client.get(f'/admin/sources/{source_id}/crawl-config').text, 'html.parser')


def post(client, source_id, selector, **extra):
    page = config(client, source_id)
    form = page.select_one(selector)
    fields = {item['name']: item.get('value', '') for item in form.select('input[name]')}
    fields.update(extra)
    return client.post(form['action'], data=fields)


def second_version(client, source_id, csrf_token, fetch_network):
    recipe = preview.recipe_for(source_id)
    recipe['feed']['fields']['content'] = 'summary'
    version = preview.save_candidate(client, source_id, csrf_token, recipe)
    action, form = preview.preview_form(client, version)
    assert client.post(action, data=form).status_code == 302
    action, fields = activation.decision_form(client, version, 'form[data-approve]')
    assert client.post(action, data=fields).status_code == 302
    return version


def test_rollback_swaps_active_and_previous_and_retire_returns_to_legacy(client, source, csrf_token, fetch_network):
    first = activation.approved(client, source, csrf_token, fetch_network)
    second = second_version(client, source, csrf_token, fetch_network)
    assert post(client, source, 'form[data-rollback]').status_code == 302
    page = config(client, source)
    assert page.select_one('[data-active-version]').get_text(strip=True) == first.rsplit('/', 1)[1]
    assert page.select_one('[data-previous-version]').get_text(strip=True) == second.rsplit('/', 1)[1]
    assert page.select_one('[data-activation-generation]').get_text(strip=True) == '3'
    assert post(client, source, 'form[data-retire]').status_code == 302
    page = config(client, source)
    assert 'No active recipe' in page.get_text()
    assert [d.get_text().split('—')[1].split()[0] for d in page.select('[data-decision]')][:3] == ['retire', 'rollback', 'approve']


def test_rollback_is_refused_after_the_source_changed(client, source, csrf_token, fetch_network):
    activation.approved(client, source, csrf_token, fetch_network)
    second_version(client, source, csrf_token, fetch_network)
    preview.edit_source(client, source, csrf_token, url='https://news.test.invalid/moved')
    assert post(client, source, 'form[data-rollback]').status_code == 409


def test_rollback_without_previous_and_retire_without_active_are_refused(client, source, csrf_token, fetch_network):
    assert post(client, source, 'form[data-retire]').status_code in (404, 409)
    activation.approved(client, source, csrf_token, fetch_network)
    assert post(client, source, 'form[data-rollback]').status_code == 409


def test_retire_is_allowed_for_a_disabled_source(client, source, csrf_token, fetch_network):
    activation.approved(client, source, csrf_token, fetch_network)
    assert client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()}).status_code == 302
    assert post(client, source, 'form[data-retire]').status_code == 302
```

（`test_rollback_without_previous...` 第一条：尚无 profile 时 retire 返回 404，有 profile 无 active 时返回 409，两者都可接受。）

- [ ] **Step 2: 运行，确认失败**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_web/test_crawl_rollback.py -q`
Expected: FAIL（找不到 `form[data-rollback]`）

- [ ] **Step 3: 实现**

`activation.py` 追加：

```python
def rollback(source_id, actor_id, expected):
    source, state, profile = _locked(source_id, expected)
    target = profile.previous_version_id
    if target is None:
        raise Refused(409, 'No previous version')
    approved = db.session.scalar(select(CrawlSchemaDecision).where(
        CrawlSchemaDecision.profile_id == profile.id, CrawlSchemaDecision.version_id == target,
        CrawlSchemaDecision.action.in_(('approve', 'rollback'))).order_by(CrawlSchemaDecision.id.desc()).limit(1))
    if approved is None or approved.source_generation != profile.source_generation:
        raise Refused(409, 'The source changed since that version was approved; approve it again')
    if not source.is_active:
        raise Refused(409, 'Source is disabled')
    record = _policy(source, profile)
    _valid_recipe(db.session.get(CrawlSchemaVersion, target))
    current = profile.active_version_id
    profile.active_version_id, profile.previous_version_id = target, current
    profile.active_source_generation = profile.source_generation
    profile.activation_generation += 1
    _decide(profile, 'rollback', actor_id, version_id=target, from_version_id=current, record=record)
    state.next_due_at, state.due_reason = schedule.now(), 'activation'
    db.session.commit()


def retire(source_id, actor_id, expected):
    _, _, profile = _locked(source_id, expected)
    current = profile.active_version_id
    if current is None:
        raise Refused(409, 'Already using the legacy crawler')
    profile.previous_version_id, profile.active_version_id = current, None
    profile.active_source_generation = None
    profile.activation_generation += 1
    _decide(profile, 'retire', actor_id, from_version_id=current)
    db.session.commit()
```

`crawl_activation.py` 追加：

```python
@crawl_activation_bp.route('/rollback', methods=['POST'])
def rollback(source_id):
    form = _form()
    _apply(activation.rollback, source_id, current_user.id, form['expected_activation'])
    flash('Rolled back to the previous version; the next crawl uses it.', 'success')
    return redirect(url_for('admin.crawl_config.index', source_id=source_id))


@crawl_activation_bp.route('/retire', methods=['POST'])
def retire(source_id):
    form = _form()
    _apply(activation.retire, source_id, current_user.id, form['expected_activation'])
    flash('Returned to the legacy crawler.', 'success')
    return redirect(url_for('admin.crawl_config.index', source_id=source_id))
```

`crawl_config.html` 在 “Decisions” 标题前加：

```html
<div class="d-flex gap-2 mb-3">
    <form method="post" data-rollback action="{{ url_for('admin.crawl_config.activation.rollback', source_id=source.id) }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="expected_activation" value="{{ profile.activation_generation if profile else 0 }}">
        <button class="btn btn-outline-warning" {% if not (profile and profile.previous_version_id) %}disabled{% endif %}>Roll back to previous version</button>
    </form>
    <form method="post" data-retire action="{{ url_for('admin.crawl_config.activation.retire', source_id=source.id) }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="expected_activation" value="{{ profile.activation_generation if profile else 0 }}">
        <button class="btn btn-outline-secondary" {% if not (profile and profile.active_version_id) %}disabled{% endif %}>Return to legacy crawler</button>
    </form>
</div>
```

- [ ] **Step 4: 运行，确认通过**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_web/test_crawl_rollback.py tests/test_web/test_crawl_activation.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/crawlers/activation.py app/web/views/crawl_activation.py app/web/templates/admin/crawl_config.html tests/test_web/test_crawl_rollback.py
git commit -m "feat(admin): roll back to the previous recipe or return to the legacy crawler"
```

---

### Task 8: 运行时路由（批准的 schema 优先，失效即阻断，不回落）

**Files:**
- Modify: `app/crawlers/activation.py`（`Route`、`Blocked`、`route`）、`app/crawlers/runs.py`（`execute`、`record_route`）
- Create: `tests/test_web/test_crawl_routing.py`

**Interfaces:**
- Consumes: Task 4 `runs.*`、Task 5 `CrawlEngine.run(claim)`、Task 6/7 Admin 流程。
- Produces: `activation.Route(kind, version_id, policy_version_id, recipe, fetch_policy, quality)`、`activation.Blocked(code)`、`activation.route(claim) -> Route`（活动计数变化抛 `runs.RunLost`）、`runs.record_route(claim, route)`、完整版 `runs.execute`。

- [ ] **Step 1: 写失败测试** `tests/test_web/test_crawl_routing.py`

```python
"""Scheduled crawls follow the approved recipe; problems block instead of falling back (spec §4.5, §5.3)."""
import pytest
from bs4 import BeautifulSoup

from app.models.article import Article
from app.models.crawl_runtime import ArticleLLMJob, CrawlSourceState
from app.models.crawl_schema import CrawlSchemaVersion
from app.models.source import CrawlLog, NewsSource
from tests.support.runs import claimed
from tests.test_web import test_crawl_activation as activation
from tests.test_web import test_crawl_policy as policy
from tests.test_web import test_crawl_preview as preview
from tests.test_web import test_crawl_rollback as rollback

source = preview.source
fetch_network = preview.fetch_network


@pytest.fixture
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr('celery.app.base.Celery.send_task',
                        lambda self, name, args=None, kwargs=None, **options: messages.append((name, args)))
    return messages


def scheduled_run(db, sent):
    from app.crawlers.tasks import crawl_source, dispatch_due_crawls
    assert dispatch_due_crawls.run() == {'dispatched': 1}
    (source_id, claim_id), = [args for name, args in sent if name == 'app.crawlers.tasks.crawl_source']
    sent.clear()
    crawl_source.run(source_id, claim_id)
    db.session.remove()
    return CrawlLog.query.order_by(CrawlLog.id.desc()).first()


def test_approved_schema_is_used_by_the_next_scheduled_crawl(db, client, source, csrf_token, fetch_network, sent):
    version = activation.approved(client, source, csrf_token, fetch_network)
    version_id = int(version.rsplit('/', 1)[1])
    log = scheduled_run(db, sent)
    assert (log.route, log.schema_version_id, log.outcome) == ('schema', version_id, 'success')
    article = Article.query.one()
    assert article.crawl_provenance['recipe'] == db.session.get(CrawlSchemaVersion, version_id).recipe_hash
    job = ArticleLLMJob.query.one()
    assert job.article_id == article.id and sent == [('app.llm.article_tasks.process', [job.id])]


def test_approval_makes_a_recently_crawled_source_due_immediately(db, client, source, csrf_token, fetch_network, sent):
    from app.crawlers.rss_crawler import RSSCrawler
    fetch_network.configure(routes={'https://news.test.invalid/feed': {
        'body': preview.FEED, 'headers': {'Content-Type': 'application/rss+xml'}}})
    RSSCrawler(db.session.get(NewsSource, source)).run(claimed(source))
    db.session.remove()
    assert db.session.get(CrawlSourceState, source).next_due_at > CrawlLog.query.one().finished_at
    activation.approved(client, source, csrf_token, fetch_network)
    log = scheduled_run(db, sent)
    # Identity compatibility may make this no_change; the point is that it ran at once on the schema route.
    assert log.route == 'schema' and log.outcome in ('no_change', 'success')


@pytest.mark.parametrize('change, code', [('revoke', 'policy_unavailable'), ('edit', 'schema_stale')])
def test_broken_schema_route_blocks_without_legacy_fallback(db, client, source, csrf_token, fetch_network, sent, change, code):
    activation.approved(client, source, csrf_token, fetch_network)
    if change == 'revoke':
        action, fields = policy.revoke_form(client, source)
        assert client.post(action, data=fields).status_code == 302
    else:
        preview.edit_source(client, source, csrf_token, url='https://news.test.invalid/moved')
    requests = len(fetch_network.events())
    log = scheduled_run(db, sent)
    assert (log.route, log.outcome, log.error_code) == ('schema', 'blocked', code)
    assert len(fetch_network.events()) == requests and Article.query.count() == 0
    assert db.session.get(CrawlSourceState, source).attention_reason == code


def test_a_run_claimed_before_approval_cannot_commit_after_it(db, client, source, csrf_token, fetch_network, sent):
    from app.crawlers.rss_crawler import RSSCrawler
    version, _ = activation.ready_report(client, source, csrf_token, fetch_network)
    claim = claimed(source)
    action, fields = activation.decision_form(client, version, 'form[data-approve]')
    assert client.post(action, data=fields).status_code == 302
    result = RSSCrawler(db.session.get(NewsSource, source)).run(claim)
    assert result.status == 'stale' and Article.query.count() == 0


def test_retired_schema_returns_the_source_to_the_legacy_crawler(db, client, source, csrf_token, fetch_network, sent):
    activation.approved(client, source, csrf_token, fetch_network)
    assert rollback.post(client, source, 'form[data-retire]').status_code == 302
    from app.crawlers import runs
    runs.request_now(source)
    log = scheduled_run(db, sent)
    assert (log.route, log.schema_version_id, log.outcome) == ('legacy', None, 'success')
    assert Article.query.one().crawl_provenance is None
```

- [ ] **Step 2: 运行，确认失败**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_web/test_crawl_routing.py -q`
Expected: FAIL（第一条断言 `route == 'legacy'`，说明 execute 仍只走旧爬虫）

- [ ] **Step 3: 实现**

`activation.py` 追加：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    kind: str
    version_id: int | None = None
    policy_version_id: int | None = None
    recipe: object = None
    fetch_policy: object = None
    quality: object = None


class Blocked(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def route(claim):
    """The route pinned to this claim; activation changes since the claim make it stale."""
    from .runs import RunLost
    profile = CrawlSourceProfile.query.filter_by(source_id=claim.source_id).populate_existing().first()
    if (profile.activation_generation if profile else 0) != claim.activation_generation:
        raise RunLost()
    if profile is None or profile.active_version_id is None:
        return Route('legacy')
    if profile.active_source_generation != profile.source_generation:
        raise Blocked('schema_stale')
    source = db.session.get(NewsSource, claim.source_id)
    record = _source_policy.latest(profile)
    if _source_policy.state(record, source, profile) != 'effective':
        raise Blocked('policy_unavailable')
    fetch_policy, quality = _source_policy.inputs(record)
    version = db.session.get(CrawlSchemaVersion, profile.active_version_id)
    try:
        recipe = validate_recipe(version.recipe)
    except ValueError:
        raise Blocked('invalid_schema') from None
    if recipe.fingerprint != version.recipe_hash:
        raise Blocked('invalid_schema')
    return Route('schema', version.id, record.id, recipe, fetch_policy, quality)
```

`runs.py`：新增 `record_route` 并替换 `execute`：

```python
def record_route(claim, route):
    with Session(db.engine) as session, session.begin():
        log = session.get(CrawlLog, claim.log_id)
        if log is not None and log.status == 'running':
            log.route, log.schema_version_id, log.policy_version_id = route.kind, route.version_id, route.policy_version_id


def execute(source_id, claim_id):
    """Resolve the route for a current claim and run it; approval is enforced here (spec §4.5)."""
    from app.crawlers import activation, registry
    from app.crawlers.engine import CrawlEngine
    claim = current(source_id, claim_id)
    if claim is None:
        return None
    try:
        route = activation.route(claim)
    except RunLost:
        mark_stale(claim)
        return None
    except activation.Blocked as blocked:
        abandon(claim, route='schema', error_code=blocked.code)
        return None
    finally:
        db.session.remove()
    record_route(claim, route)
    if route.kind == 'schema':
        engine = CrawlEngine(source_id, recipe=route.recipe, fetch_policy=route.fetch_policy, profile=route.quality)
        return engine.run(claim)
    try:
        crawler = registry.get_crawler(db.session.get(NewsSource, source_id))
    except Exception as exc:
        abandon(claim, route='legacy', error_code='crawler_error', message=str(exc))
        return None
    return crawler.run(claim)
```

- [ ] **Step 4: 运行，确认通过**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_web/test_crawl_routing.py tests/test_web/test_crawl_rollback.py tests/test_web/test_crawl_activation.py tests/test_crawlers -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/crawlers/activation.py app/crawlers/runs.py tests/test_web/test_crawl_routing.py
git commit -m "feat(crawl): route scheduled crawls through the approved recipe without legacy fallback"
```

---

### Task 9: Admin 运行面、beat 切换、CLI 与补偿脚本

**Files:**
- Modify: `app/web/views/admin.py`（`sources`、`source_crawl_now`、`crawl_all_now`、`settings`）
- Modify: `app/web/templates/admin/sources.html`、`crawl_logs.html`、`settings.html`
- Modify: `app/crawlers/tasks.py`（`crawl_all_sources`、`schedule_due_crawls` 退役）、`celery_app.py`（beat）
- Modify: `scripts/run_crawl.py`、`scripts/check_worker_readiness.py`、`tests/test_ops/test_worker_readiness.py`
- Create: `scripts/backfill_article_jobs.py`、`tests/test_web/test_crawl_runtime_admin.py`
- Modify: `tests/test_web/test_admin_safety.py`（每日小时门控测试改为退役测试）

**Interfaces:**
- Consumes: `runs.request_now/claim/execute/ensure_states`、`article_jobs.backfill`、`CrawlSourceState`、`CrawlSourceProfile.active_version_id`。
- Produces: 源列表 `[data-route]`、`[data-next-due]`、`[data-attention]`；抓取日志 `[data-log-route]`、`[data-log-outcome]`、`[data-log-error]`；beat 项 `dispatch-due-crawls`、`recover-article-llm`。

- [ ] **Step 1: 写失败测试** `tests/test_web/test_crawl_runtime_admin.py`

```python
"""Operator-visible runtime: routes, due times, attention, manual requests and the beat switch."""
from bs4 import BeautifulSoup

from app.crawlers import runs
from app.models.crawl_runtime import CrawlSourceState
from app.models.source import NewsSource
from tests.support.runs import claimed
from tests.test_crawlers.test_crawl_runs import FixtureCrawler
from app.crawlers.fetcher import FetchError
from tests.test_web import test_crawl_preview as preview

source = preview.source


def test_source_list_shows_route_next_due_and_attention(db, client, source):
    FixtureCrawler(db.session.get(NewsSource, source), error=FetchError('robots_unavailable')).run(claimed(source))
    page = BeautifulSoup(client.get('/admin/sources').text, 'html.parser')
    row = page.select_one('[data-route]').find_parent('tr')
    assert row.select_one('[data-route]').get_text(strip=True) == 'Legacy'
    assert row.select_one('[data-next-due]').get_text(strip=True)
    assert row.select_one('[data-attention]').get_text(strip=True) == 'robots_unavailable'
    logs = BeautifulSoup(client.get('/admin/crawl-logs').text, 'html.parser')
    assert logs.select_one('[data-log-route]').get_text(strip=True) == 'legacy'
    assert logs.select_one('[data-log-outcome]').get_text(strip=True) == 'blocked'
    assert logs.select_one('[data-log-error]').get_text(strip=True) == 'robots_unavailable'


def test_crawl_now_reports_running_and_disabled_sources(db, client, source, csrf_token):
    path = f'/admin/sources/{source}/crawl-now'
    page = client.post(path, data={'csrf_token': csrf_token()}, follow_redirects=True).text
    assert 'starts within a minute' in page
    db.session.remove()
    assert db.session.get(CrawlSourceState, source).due_reason == 'manual'
    claimed(source)
    assert 'already running' in client.post(path, data={'csrf_token': csrf_token()}, follow_redirects=True).text
    assert client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()}).status_code == 302
    assert 'disabled' in client.post(path, data={'csrf_token': csrf_token()}, follow_redirects=True).text


def test_settings_no_longer_offer_the_retired_check_interval(client, source):
    page = client.get('/admin/settings').text
    assert 'crawl_check_interval_hours' not in page
    assert 'crawl_daily_hour' in page


def test_beat_runs_the_dispatcher_and_retired_tasks_are_harmless(db, source, monkeypatch):
    from celery_app import celery
    from app.crawlers import tasks
    schedule = celery.conf.beat_schedule
    assert schedule['dispatch-due-crawls']['task'] == 'app.crawlers.tasks.dispatch_due_crawls'
    assert schedule['recover-article-llm']['task'] == 'app.llm.article_tasks.recover'
    assert 'daily-crawl-all' not in schedule and 'crawl-frequency-check' not in schedule
    sent = []
    monkeypatch.setattr('celery.app.base.Celery.send_task', lambda self, *a, **k: sent.append(a))
    assert tasks.crawl_all_sources.run()['skipped'] is True
    assert tasks.schedule_due_crawls.run()['skipped'] is True
    assert sent == []
```

- [ ] **Step 2: 运行，确认失败**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_web/test_crawl_runtime_admin.py -q`
Expected: FAIL（源列表没有 `[data-route]`）

- [ ] **Step 3: 实现**

`admin.py`：

```python
@admin_bp.route('/sources')
def sources():
    from app.models.crawl_runtime import CrawlSourceState
    sources = NewsSource.query.order_by(NewsSource.name).all()
    states = {state.source_id: state for state in CrawlSourceState.query.all()}
    active = dict(db.session.query(CrawlSourceProfile.source_id, CrawlSourceProfile.active_version_id)
                  .filter(CrawlSourceProfile.active_version_id.isnot(None)).all())
    return render_template('admin/sources.html', sources=sources, states=states, active=active)


@admin_bp.route('/sources/<int:source_id>/crawl-now', methods=['POST'])
def source_crawl_now(source_id):
    """Make the source due now; the dispatcher claims it within a minute."""
    from app.crawlers import runs
    source = NewsSource.query.get_or_404(source_id)
    outcome = runs.request_now(source_id)
    messages = {'queued': (f'Crawl requested for "{source.name}"; it starts within a minute.', 'success'),
                'running': (f'"{source.name}" is already running; no second crawl was queued.', 'warning'),
                'inactive': (f'"{source.name}" is disabled; enable it before crawling.', 'warning')}
    flash(*messages[outcome])
    return redirect(url_for('admin.sources'))
```

`crawl_all_now` 主体改为：

```python
    from app.crawlers import runs
    outcomes = [runs.request_now(source.id) for source in NewsSource.query.filter_by(is_active=True).all()]
    flash(f'Crawl requested for {outcomes.count("queued")} sources; '
          f'{outcomes.count("running")} already running.', 'success')
    return redirect(url_for('admin.settings'))
```

`settings()` POST 中删除 `check_interval = ...` 与其 `SystemSetting.set(...)` 两段。

`sources.html`：表头在 `Last Crawled` 后加 `<th>Route</th><th>Next due (UTC)</th>`；行内对应位置加：

```html
            {% set state = states.get(source.id) %}
            <td data-route>{% if active.get(source.id) %}Schema v{{ active[source.id] }}{% else %}Legacy{% endif %}</td>
            <td><span data-next-due>{{ state.next_due_at.strftime('%m-%d %H:%M') if state else 'Not scheduled' }}</span>
                {% if state and state.attention_reason %}<span class="badge bg-danger ms-1" data-attention>{{ state.attention_reason }}</span>{% endif %}</td>
```

`crawl_logs.html`：表头在 `Status` 后加 `<th>Route</th><th>Outcome</th>`，`Error` 列前加 `<th>Code</th>`；行内：

```html
                    <td data-log-route>{{ log.route or '-' }}{% if log.schema_version_id %} v{{ log.schema_version_id }}{% endif %}</td>
                    <td data-log-outcome>{{ log.outcome or log.status }}</td>
```

以及在 Error 单元格前 `<td data-log-error>{{ log.error_code or '' }}</td>`。

`settings.html`：删除 `name="crawl_check_interval_hours"` 的整个 `<select>` 及其所在的标签/说明行（约 136–146 行，以实际文件为准）。

`tasks.py`：

```python
@celery.task(name='app.crawlers.tasks.crawl_all_sources', queue='crawl', ignore_result=True)
def crawl_all_sources():
    """Retired: dispatch_due_crawls applies the daily anchor. Kept so queued old messages are harmless."""
    return {'skipped': True, 'reason': 'retired'}


@celery.task(name='app.crawlers.tasks.schedule_due_crawls', queue='crawl', ignore_result=True)
def schedule_due_crawls():
    """Retired: dispatch_due_crawls applies source frequencies. Kept for queued old messages."""
    return {'skipped': True, 'reason': 'retired'}
```

（删除随之不再使用的 `datetime`、`SystemSetting`、`redis_client` import。）

`celery_app.py` beat：删除 `daily-crawl-all` 与 `crawl-frequency-check`，加：

```python
            'dispatch-due-crawls': {
                'task': 'app.crawlers.tasks.dispatch_due_crawls',
                'schedule': 60.0,
            },
```

`scripts/run_crawl.py` 循环体替换为：

```python
        from app.crawlers import runs, schedule
        runs.ensure_states(schedule.now())
        print(f'Crawling {len(sources)} source(s)...\n')
        for source in sources:
            print(f'--- {source.name} ({source.feed_type}) ---')
            claim = runs.claim(source.id, due_only=False)
            if claim is None:
                print('  Skipped: disabled or already running')
                continue
            result = runs.execute(source.id, claim.claim_id)
            print(f'  Status: {getattr(result, "status", "not run")}')
            print()
```

（并删除不再使用的 `get_crawler` import。）

`scripts/backfill_article_jobs.py`：

```python
"""Create durable LLM jobs for unprocessed articles (release step). Dry run unless --apply."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write the jobs; otherwise only count them')
    args = parser.parse_args(argv)
    with create_app().app_context():
        from app.llm import article_jobs
        count = article_jobs.backfill(apply=args.apply)
    print(f'{"Created" if args.apply else "Would create"} {count} article LLM jobs')


if __name__ == '__main__':
    main()
```

`scripts/check_worker_readiness.py` 的 `REQUIRED_TASKS` 加入 `'app.crawlers.tasks.dispatch_due_crawls'` 与 `'app.llm.article_tasks.process'`；`tests/test_ops/test_worker_readiness.py` 中构造的注册任务列表同步加入这两个名字（`'app.llm.article_tasks.process [rate_limit=10/m]'`）。

`tests/test_web/test_admin_safety.py`：删除按小时门控 `crawl_all_sources` 的测试（约 110–137 行），其覆盖已由 Task 3 锚点测试和本任务 beat 测试替代。

- [ ] **Step 4: 运行，确认通过**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/test_web tests/test_ops -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/web app/crawlers/tasks.py celery_app.py scripts tests/test_web tests/test_ops
git commit -m "feat(admin): show routes and due times, request crawls, switch beat to the dispatcher"
```

---

### Task 10: 真实 MySQL 集成测试

**Files:**
- Modify: `tests/integration/test_mysql_m0.py`

**Interfaces:**
- Consumes: `runs.claim/ensure_states/lock/RunLost`、`article_jobs.request/claim`、`tests.support.runs.claimed`。

- [ ] **Step 1: 更新既有用例**：本文件中 `engine.run()` → `engine.run(claimed(source_id))`，`crawler.run()` / `FixtureCrawler(...).run()` → `.run(claimed(source_id))`（`from tests.support.runs import claimed`，source_id 取各用例中已有的变量）。依赖“引擎自建日志”的断言改为读 `claim.log_id` 对应的日志。

- [ ] **Step 2: 新增四个用例**（放在类内，沿用 `self.upgrade()` 与 `self.db`）

```python
    def _source(self):
        from app.models.source import NewsSource
        self.upgrade()
        source = NewsSource(name='MySQL runtime', slug='mysql-runtime', url='https://test.invalid/',
                            category='national', crawl_frequency_minutes=60)
        self.db.session.add(source)
        self.db.session.commit()
        return source.id

    def _race(self, work):
        import threading
        barrier, results = threading.Barrier(2), []

        def run():
            with self.app.app_context():
                barrier.wait()
                results.append(work())
                self.db.session.remove()
        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        return results

    def test_mysql_concurrent_claims_have_one_owner(self):
        from app.crawlers import runs, schedule
        source_id = self._source()
        runs.ensure_states(schedule.now())
        results = self._race(lambda: runs.claim(source_id, due_only=False))
        self.assertEqual(sum(1 for item in results if item is not None), 1)

    def test_mysql_reclaimed_source_rejects_the_old_commit(self):
        from datetime import timedelta
        from unittest.mock import patch
        from app.crawlers import runs, schedule
        from app.models.article import Article
        from tests.support.runs import claimed
        source_id = self._source()
        first = claimed(source_id)
        later = schedule.now() + timedelta(minutes=16)
        with patch.object(schedule, 'now', lambda: later):
            self.assertIsNotNone(runs.claim(source_id, due_only=False))
            from sqlalchemy.orm import Session
            with self.assertRaises(runs.RunLost):
                with Session(self.db.engine) as session, session.begin():
                    runs.lock(session, first)
        self.db.session.remove()
        self.assertEqual(Article.query.count(), 0)

    def test_mysql_one_active_llm_job_per_article(self):
        from app.llm import article_jobs
        from app.models.article import Article
        from app.models.crawl_runtime import ArticleLLMJob
        source_id = self._source()
        article = Article(source_id=source_id, external_id='one', url='https://test.invalid/one', title_fr='One')
        self.db.session.add(article)
        self.db.session.commit()
        results = self._race(lambda: article_jobs.request(article.id, 'manual'))
        self.assertEqual(sum(1 for _, created in results if created), 1)
        self.db.session.remove()
        self.assertEqual(ArticleLLMJob.query.count(), 1)

    def test_mysql_duplicate_job_messages_have_one_consumer(self):
        from app.llm import article_jobs
        from app.models.article import Article
        source_id = self._source()
        article = Article(source_id=source_id, external_id='two', url='https://test.invalid/two', title_fr='Two')
        self.db.session.add(article)
        self.db.session.commit()
        identity, _ = article_jobs.request(article.id, 'manual')
        import uuid
        results = self._race(lambda: article_jobs.claim(identity, str(uuid.uuid4())))
        self.assertEqual(sum(1 for item in results if item is not None), 1)
```

- [ ] **Step 3: 本地确认这些用例在无 MySQL 时被跳过、语法无误**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/integration/test_mysql_m0.py -q`
Expected: 全部 SKIPPED（需要 `FSI_MYSQL_TEST_URL`）

- [ ] **Step 4: 提交**

```bash
git add tests/integration/test_mysql_m0.py
git commit -m "test(mysql): concurrent claims, fencing and one active LLM job per article"
```

真实 MySQL 验证在推送分支后由 CI 的 `mysql-integration` 作业执行；推送前先征得用户同意。

---

### Task 11: 文档与全量验证

**Files:**
- Create: `docs/ops/crawl-runtime.md`
- Modify: `CLAUDE.md`（Celery Configuration、Crawler System 相关段落）
- Modify: `docs/superpowers/specs/2026-09-25-m2-activation-routing-design.md`（状态行）

- [ ] **Step 1: 写运维文档** `docs/ops/crawl-runtime.md`，内容覆盖：
  - 调度规则（频率 + 每日锚点、30 分钟间隔、三类失败的处理、15 分钟最小频率、DST 行为）。
  - `attention_reason` 的含义与处理：`forbidden/robots_*/tls_error/http_error` 需人工检查站点；`extraction_failed` 需修 recipe 或旧爬虫；`schema_stale/policy_unavailable/invalid_schema` 需重新批准或退回旧爬虫。
  - 批准 / 拒绝 / 回滚 / 退回旧爬虫 的前提与效果。
  - 文章 LLM 任务状态（queued/running/done/failed/expired）、失败后用 Admin 批量重处理、`run_llm_process.py` 不经过认领。
  - 上线步骤（spec §10）与 `scripts/backfill_article_jobs.py` 的 dry run / `--apply`。
  - 回滚方式与“不混跑新旧 worker”。

- [ ] **Step 2: 更新 `CLAUDE.md`**：Celery Configuration 段落改为 beat 每 60 秒 `dispatch_due_crawls` 与 `recover-article-llm`，删除“600s + 六小时 Redis 门 + 每小时锚点检查”的描述；在 Crawler System 增加一段 “M2 activation/routing（已实现于分支 `m2-activation-routing`，未部署）”，指向 spec、本计划与 `docs/ops/crawl-runtime.md`。

- [ ] **Step 3: spec 状态行** 改为 “已实现（分支 m2-activation-routing），未部署”。

- [ ] **Step 4: 全量测试与静态检查**

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m pytest tests/ -q`
Expected: 全部通过；只有 MySQL 专用用例被跳过（记录 passed/skipped 数字）。

Run: `~/.cache/fsourceinsight-m3-venv/bin/python -m compileall -q app scripts celery_app.py`
Expected: 无输出。

Run: `git grep -n "_enqueue_llm_processing\|crawl_check_interval_hours\|\.run()$" -- app scripts`
Expected: 无残留（`.run()` 只允许出现在 Celery 任务对象上）。

- [ ] **Step 5: 提交**

```bash
git add docs/ops/crawl-runtime.md CLAUDE.md docs/superpowers/specs/2026-09-25-m2-activation-routing-design.md
git commit -m "docs: crawl runtime operations and M2 activation status"
```

之后：请求用户同意推送分支以跑 CI（含真实 MySQL 与 broker 门禁）；部署另写发布计划并单独授权。
