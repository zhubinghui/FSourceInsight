import os
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func

from slugify import slugify

from app.extensions import db
from app.models.source import NewsSource, CrawlLog
from app.models.article import Article, ArticleCompany
from app.models.company import Company
from app.models.llm import LLMConfig, LLMUsageLog

admin_bp = Blueprint('admin', __name__)


@admin_bp.before_request
@login_required
def require_admin():
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('news.index'))

# ── Dashboard ─────────────────────────────────────────────────────

@admin_bp.route('/')
def dashboard():
    source_count = NewsSource.query.filter_by(is_active=True).count()
    article_count = Article.query.count()
    unprocessed_count = Article.query.filter_by(llm_processed=False).count()
    company_count = Company.query.count()
    recent_crawls = CrawlLog.query.order_by(CrawlLog.started_at.desc()).limit(10).all()

    # Today's LLM cost
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_cost = db.session.query(
        func.coalesce(func.sum(LLMUsageLog.cost_usd), 0)
    ).filter(LLMUsageLog.created_at >= today).scalar()

    return render_template(
        'admin/dashboard.html',
        source_count=source_count,
        article_count=article_count,
        unprocessed_count=unprocessed_count,
        company_count=company_count,
        recent_crawls=recent_crawls,
        today_cost=float(today_cost or 0),
    )


# ── Sources CRUD ──────────────────────────────────────────────────

FEED_TYPES = ['rss', 'atom', 'html_scrape']
SOURCE_CATEGORIES = ['national', 'regional', 'institutional']

@admin_bp.route('/sources')
def sources():
    sources = NewsSource.query.order_by(NewsSource.name).all()
    return render_template('admin/sources.html', sources=sources)


@admin_bp.route('/sources/new', methods=['GET', 'POST'])
def source_new():
    if request.method == 'POST':
        source = _save_source_from_form(NewsSource())
        db.session.add(source)
        db.session.commit()
        flash(f'Source "{source.name}" created.', 'success')
        return redirect(url_for('admin.sources'))
    return render_template('admin/source_form.html', source=None,
                           feed_types=FEED_TYPES, source_categories=SOURCE_CATEGORIES)


@admin_bp.route('/sources/<int:source_id>/edit', methods=['GET', 'POST'])
def source_edit(source_id):
    source = NewsSource.query.get_or_404(source_id)
    if request.method == 'POST':
        _save_source_from_form(source)
        db.session.commit()
        flash(f'Source "{source.name}" updated.', 'success')
        return redirect(url_for('admin.sources'))
    return render_template('admin/source_form.html', source=source,
                           feed_types=FEED_TYPES, source_categories=SOURCE_CATEGORIES)


@admin_bp.route('/sources/<int:source_id>/toggle', methods=['POST'])
def source_toggle(source_id):
    source = NewsSource.query.get_or_404(source_id)
    source.is_active = not source.is_active
    db.session.commit()
    status = 'activated' if source.is_active else 'deactivated'
    flash(f'{source.name} {status}.', 'success')
    return redirect(url_for('admin.sources'))


@admin_bp.route('/sources/<int:source_id>/crawl-now', methods=['POST'])
def source_crawl_now(source_id):
    """Trigger immediate crawl for a source."""
    from app.crawlers.tasks import crawl_source
    crawl_source.delay(source_id)
    source = NewsSource.query.get_or_404(source_id)
    flash(f'Crawl queued for "{source.name}".', 'success')
    return redirect(url_for('admin.sources'))


def _save_source_from_form(source: NewsSource) -> NewsSource:
    source.name = request.form.get('name', '').strip()
    source.slug = slugify(source.name) if not request.form.get('slug') else request.form.get('slug').strip()
    source.url = request.form.get('url', '').strip()
    source.feed_url = request.form.get('feed_url', '').strip() or None
    source.feed_type = request.form.get('feed_type', 'rss')
    source.crawler_class = request.form.get('crawler_class', '').strip() or None
    source.category = request.form.get('category', 'national')
    source.crawl_frequency_minutes = int(request.form.get('crawl_frequency_minutes', 60))
    source.is_active = request.form.get('is_active') == 'on'
    return source


# ── Companies ─────────────────────────────────────────────────────

@admin_bp.route('/companies')
def companies():
    page = request.args.get('page', 1, type=int)
    companies = Company.query.order_by(Company.name).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template('admin/companies.html', companies=companies)


COMPANY_STAGES = ['startup', 'scale-up', 'mature', 'research_institute', '']


@admin_bp.route('/companies/new', methods=['GET', 'POST'])
def company_new():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Company name is required.', 'error')
            return redirect(url_for('admin.company_new'))

        slug = slugify(name)

        # Duplicate check: by slug and by alias
        existing = Company.query.filter_by(slug=slug).first()
        if existing:
            flash(f'Company "{existing.name}" already exists (same slug: {slug}).', 'error')
            return redirect(url_for('admin.company_new'))

        # Check aliases of existing companies
        name_lower = name.lower()
        for c in Company.query.all():
            if c.aliases and name_lower in [a.lower() for a in c.aliases]:
                flash(f'"{name}" matches alias of existing company "{c.name}".', 'error')
                return redirect(url_for('admin.company_new'))
            if c.name.lower() == name_lower:
                flash(f'Company "{c.name}" already exists (same name).', 'error')
                return redirect(url_for('admin.company_new'))

        company = Company(
            name=name,
            slug=slug,
            description=request.form.get('description', '').strip() or None,
            website=request.form.get('website', '').strip() or None,
            headquarters=request.form.get('headquarters', '').strip() or None,
            sector=request.form.get('sector', '').strip() or None,
            is_grenoble=request.form.get('is_grenoble') == 'on',
            company_stage=request.form.get('company_stage', '').strip() or None,
            spinoff_origin=request.form.get('spinoff_origin', '').strip() or None,
            aliases=[a.strip() for a in request.form.get('aliases', '').split(',') if a.strip()] or None,
        )
        db.session.add(company)
        db.session.commit()
        flash(f'Company "{name}" created.', 'success')
        return redirect(url_for('admin.companies'))

    return render_template('admin/company_form.html', company=None, stages=COMPANY_STAGES)


@admin_bp.route('/companies/<int:company_id>/edit', methods=['GET', 'POST'])
def edit_company(company_id):
    company = Company.query.get_or_404(company_id)
    if request.method == 'POST':
        new_name = request.form.get('name', '').strip()
        new_slug = slugify(new_name) if new_name else company.slug

        # Duplicate check on rename
        if new_slug != company.slug:
            dup = Company.query.filter_by(slug=new_slug).first()
            if dup:
                flash(f'Cannot rename: "{dup.name}" already uses slug "{new_slug}".', 'error')
                return redirect(url_for('admin.edit_company', company_id=company_id))

        company.name = new_name or company.name
        company.slug = new_slug
        company.description = request.form.get('description', '').strip() or None
        company.website = request.form.get('website', '').strip() or None
        company.headquarters = request.form.get('headquarters', '').strip() or None
        company.sector = request.form.get('sector', '').strip() or None
        company.is_grenoble = request.form.get('is_grenoble') == 'on'
        company.company_stage = request.form.get('company_stage', '').strip() or None
        company.spinoff_origin = request.form.get('spinoff_origin', '').strip() or None
        aliases_raw = request.form.get('aliases', '')
        company.aliases = [a.strip() for a in aliases_raw.split(',') if a.strip()] or None
        db.session.commit()
        flash('Company updated.', 'success')
        return redirect(url_for('admin.companies'))
    return render_template('admin/company_form.html', company=company, stages=COMPANY_STAGES)


@admin_bp.route('/companies/<int:company_id>/delete', methods=['POST'])
def delete_company(company_id):
    company = Company.query.get_or_404(company_id)
    name = company.name
    # Remove article associations first
    ArticleCompany.query.filter_by(company_id=company_id).delete()
    db.session.delete(company)
    db.session.commit()
    flash(f'Company "{name}" deleted.', 'success')
    return redirect(url_for('admin.companies'))


@admin_bp.route('/companies/merge', methods=['GET', 'POST'])
def merge_companies():
    """Merge duplicate companies: move all article associations to the target, delete the source."""
    if request.method == 'POST':
        target_id = request.form.get('target_id', type=int)
        source_id = request.form.get('source_id', type=int)

        if not target_id or not source_id or target_id == source_id:
            flash('Please select two different companies.', 'error')
            return redirect(url_for('admin.merge_companies'))

        target = Company.query.get_or_404(target_id)
        source_company = Company.query.get_or_404(source_id)

        # Move article associations
        associations = ArticleCompany.query.filter_by(company_id=source_id).all()
        moved = 0
        for ac in associations:
            # Check if target already has this article
            existing = ArticleCompany.query.filter_by(
                article_id=ac.article_id, company_id=target_id
            ).first()
            if existing:
                db.session.delete(ac)
            else:
                ac.company_id = target_id
                moved += 1

        # Add source name as alias to target
        aliases = target.aliases or []
        if source_company.name not in aliases:
            aliases.append(source_company.name)
        if source_company.aliases:
            for a in source_company.aliases:
                if a not in aliases:
                    aliases.append(a)
        target.aliases = aliases

        # Delete the source company
        db.session.delete(source_company)
        db.session.commit()

        flash(
            f'Merged "{source_company.name}" into "{target.name}". '
            f'{moved} article associations moved.',
            'success'
        )
        return redirect(url_for('admin.companies'))

    companies = Company.query.order_by(Company.name).all()
    auto_created = Company.query.filter_by(is_auto_created=True).order_by(Company.name).all()
    return render_template('admin/merge_companies.html',
                           companies=companies, auto_created=auto_created)


# ── LLM Config CRUD ──────────────────────────────────────────────

TASK_TYPES = ['translate', 'digest', 'summarize', 'ner', 'sentiment', 'classify', 'insight']

@admin_bp.route('/llm-config')
def llm_config():
    configs = LLMConfig.query.order_by(LLMConfig.provider, LLMConfig.model).all()

    # Get circuit breaker status for each provider
    try:
        from app.llm.circuit_breaker import CircuitBreaker
        breaker = CircuitBreaker()
        cb_status = {c.provider: breaker.get_status(c.provider) for c in configs}
    except Exception:
        cb_status = {}

    return render_template(
        'admin/llm_config.html', configs=configs,
        cb_status=cb_status, task_types=TASK_TYPES,
    )


@admin_bp.route('/llm-config/new', methods=['GET', 'POST'])
def llm_config_new():
    if request.method == 'POST':
        config = _save_llm_config_from_form(LLMConfig())
        db.session.add(config)
        db.session.commit()
        flash(f'LLM config {config.provider}/{config.model} created.', 'success')
        return redirect(url_for('admin.llm_config'))
    return render_template('admin/llm_config_form.html',
                           config=None, task_types=TASK_TYPES)


@admin_bp.route('/llm-config/<int:config_id>/edit', methods=['GET', 'POST'])
def llm_config_edit(config_id):
    config = LLMConfig.query.get_or_404(config_id)
    if request.method == 'POST':
        _save_llm_config_from_form(config)
        db.session.commit()
        flash(f'LLM config {config.provider}/{config.model} updated.', 'success')
        return redirect(url_for('admin.llm_config'))
    return render_template('admin/llm_config_form.html',
                           config=config, task_types=TASK_TYPES)


@admin_bp.route('/llm-config/<int:config_id>/delete', methods=['POST'])
def llm_config_delete(config_id):
    config = LLMConfig.query.get_or_404(config_id)
    name = f'{config.provider}/{config.model}'
    db.session.delete(config)
    db.session.commit()
    flash(f'LLM config {name} deleted.', 'success')
    return redirect(url_for('admin.llm_config'))


@admin_bp.route('/llm-config/<int:config_id>/toggle', methods=['POST'])
def llm_config_toggle(config_id):
    config = LLMConfig.query.get_or_404(config_id)
    config.is_active = not config.is_active
    db.session.commit()
    status = 'activated' if config.is_active else 'deactivated'
    flash(f'{config.provider}/{config.model} {status}.', 'success')
    return redirect(url_for('admin.llm_config'))


def _save_llm_config_from_form(config: LLMConfig) -> LLMConfig:
    config.provider = request.form.get('provider', '').strip()
    config.model = request.form.get('model', '').strip()
    config.api_key_env_var = request.form.get('api_key_env_var', '').strip() or None
    config.api_base_url = request.form.get('api_base_url', '').strip() or None
    config.is_default = request.form.get('is_default') == 'on'
    config.max_tokens = int(request.form.get('max_tokens', 4096))
    config.temperature = float(request.form.get('temperature', 0.3))

    cost_in = request.form.get('cost_per_1k_input', '').strip()
    config.cost_per_1k_input = float(cost_in) if cost_in else None
    cost_out = request.form.get('cost_per_1k_output', '').strip()
    config.cost_per_1k_output = float(cost_out) if cost_out else None

    # Tasks: collect checked checkboxes
    config.tasks = request.form.getlist('tasks')
    return config


# ── LLM Usage Dashboard ──────────────────────────────────────────

@admin_bp.route('/llm-usage')
def llm_usage():
    days = request.args.get('days', 7, type=int)
    since = datetime.utcnow() - timedelta(days=days)

    # Per-day cost and token stats
    daily_stats = (
        db.session.query(
            func.date(LLMUsageLog.created_at).label('day'),
            func.count(LLMUsageLog.id).label('calls'),
            func.coalesce(func.sum(LLMUsageLog.input_tokens), 0).label('input_tokens'),
            func.coalesce(func.sum(LLMUsageLog.output_tokens), 0).label('output_tokens'),
            func.coalesce(func.sum(LLMUsageLog.cost_usd), 0).label('cost'),
            func.sum(
                func.cast(LLMUsageLog.success == False, db.Integer)
            ).label('failures'),
        )
        .filter(LLMUsageLog.created_at >= since)
        .group_by(func.date(LLMUsageLog.created_at))
        .order_by(func.date(LLMUsageLog.created_at).desc())
        .all()
    )

    # Per-task breakdown
    task_stats = (
        db.session.query(
            LLMUsageLog.task_type,
            func.count(LLMUsageLog.id).label('calls'),
            func.coalesce(func.sum(LLMUsageLog.cost_usd), 0).label('cost'),
            func.coalesce(func.avg(LLMUsageLog.latency_ms), 0).label('avg_latency'),
        )
        .filter(LLMUsageLog.created_at >= since)
        .group_by(LLMUsageLog.task_type)
        .all()
    )

    # Per-provider breakdown
    provider_stats = (
        db.session.query(
            LLMConfig.provider,
            LLMConfig.model,
            func.count(LLMUsageLog.id).label('calls'),
            func.coalesce(func.sum(LLMUsageLog.cost_usd), 0).label('cost'),
        )
        .join(LLMConfig, LLMUsageLog.config_id == LLMConfig.id)
        .filter(LLMUsageLog.created_at >= since)
        .group_by(LLMConfig.provider, LLMConfig.model)
        .all()
    )

    # Totals
    total_cost = sum(float(d.cost or 0) for d in daily_stats)
    total_calls = sum(d.calls for d in daily_stats)

    return render_template(
        'admin/llm_usage.html',
        daily_stats=daily_stats,
        task_stats=task_stats,
        provider_stats=provider_stats,
        total_cost=total_cost,
        total_calls=total_calls,
        days=days,
    )


# ── LLM Reprocessing ─────────────────────────────────────────────

@admin_bp.route('/llm-reprocess', methods=['POST'])
def llm_reprocess():
    """Trigger LLM reprocessing for unprocessed articles."""
    from app.llm.tasks import process_article_llm

    limit = request.form.get('limit', 50, type=int)
    unprocessed = (
        Article.query
        .filter_by(llm_processed=False)
        .order_by(Article.crawled_at.desc())
        .limit(limit)
        .all()
    )

    for article in unprocessed:
        process_article_llm.delay(article.id)

    flash(f'Enqueued {len(unprocessed)} articles for LLM processing.', 'success')
    return redirect(url_for('admin.dashboard'))


# ── Crawl Logs ────────────────────────────────────────────────────

@admin_bp.route('/crawl-logs')
def crawl_logs():
    page = request.args.get('page', 1, type=int)
    logs = CrawlLog.query.order_by(CrawlLog.started_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template('admin/crawl_logs.html', logs=logs)


# ── Users & Email ─────────────────────────────────────────────────

LANGUAGES = [('zh', '中文'), ('en', 'English'), ('fr', 'Français')]


@admin_bp.route('/users')
def users():
    from app.models.user import User
    page = request.args.get('page', 1, type=int)
    users = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
def user_new():
    from app.models.user import User
    from werkzeug.security import generate_password_hash
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if User.query.filter_by(email=email).first():
            flash(f'User {email} already exists.', 'error')
            return redirect(url_for('admin.user_new'))
        user = User(
            email=email,
            name=request.form.get('name', '').strip(),
            password_hash=generate_password_hash(request.form.get('password', '')),
            is_admin=request.form.get('is_admin') == 'on',
            is_active_user=True,
            receive_daily_digest=request.form.get('receive_daily_digest') == 'on',
            preferred_language=request.form.get('preferred_language', 'zh'),
        )
        db.session.add(user)
        db.session.commit()
        flash(f'User "{email}" created.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=None, languages=LANGUAGES)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
def user_edit(user_id):
    from app.models.user import User
    from werkzeug.security import generate_password_hash
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.email = request.form.get('email', user.email).strip()
        user.name = request.form.get('name', '').strip()
        user.preferred_language = request.form.get('preferred_language', 'zh')
        user.receive_daily_digest = request.form.get('receive_daily_digest') == 'on'
        user.is_active_user = request.form.get('is_active_user') == 'on'
        if user.id != current_user.id:
            user.is_admin = request.form.get('is_admin') == 'on'
        new_password = request.form.get('password', '').strip()
        if new_password:
            user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash(f'User "{user.email}" updated.', 'success')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', user=user, languages=LANGUAGES)


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
def user_delete(user_id):
    from app.models.user import User
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot delete your own account.', 'error')
    else:
        email = user.email
        db.session.delete(user)
        db.session.commit()
        flash(f'User "{email}" deleted.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
def toggle_user_admin(user_id):
    from app.models.user import User
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot change your own admin status.', 'error')
    else:
        user.is_admin = not user.is_admin
        db.session.commit()
        flash(f'{user.email} admin status changed.', 'success')
    return redirect(url_for('admin.users'))


# ── LLM Task Routing Matrix ─────────────────────────────────────

@admin_bp.route('/llm-routing')
def llm_routing():
    """Visual matrix of which model handles which task."""
    configs = LLMConfig.query.filter_by(is_active=True).order_by(LLMConfig.id).all()
    all_tasks = ['translate', 'digest', 'summarize', 'ner', 'sentiment', 'classify', 'insight']

    # Build routing matrix: for each task, which config would be selected (cheapest)
    routing = {}
    for task in all_tasks:
        candidates = [c for c in configs if c.tasks and task in c.tasks]
        candidates.sort(key=lambda c: float(c.cost_per_1k_input or 999))
        routing[task] = candidates[0] if candidates else None

    # Get circuit breaker status
    try:
        from app.llm.circuit_breaker import CircuitBreaker
        breaker = CircuitBreaker()
        cb_status = {c.provider: breaker.get_status(c.provider) for c in configs}
    except Exception:
        cb_status = {}

    return render_template(
        'admin/llm_routing.html',
        configs=configs,
        all_tasks=all_tasks,
        routing=routing,
        cb_status=cb_status,
    )


# ── System Settings ──────────────────────────────────────────────

@admin_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    """System-wide settings management."""
    from flask import current_app

    if request.method == 'POST':
        # Update .env-backed settings via DB override table
        # For now, show current values from env (read-only display + editable for DB-backed)
        flash('Settings updated.', 'success')
        return redirect(url_for('admin.settings'))

    settings_data = {
        'llm_daily_budget': current_app.config.get('LLM_DAILY_BUDGET_USD', 5.0),
        'crawl_frequency': current_app.config.get('DEFAULT_CRAWL_FREQUENCY_MINUTES', 60),
        'mail_server': current_app.config.get('MAIL_SERVER', ''),
        'mail_port': current_app.config.get('MAIL_PORT', 587),
        'mail_use_tls': current_app.config.get('MAIL_USE_TLS', True),
        'mail_username': current_app.config.get('MAIL_USERNAME', ''),
        'mail_default_sender': current_app.config.get('MAIL_DEFAULT_SENDER', ''),
        'log_level': os.environ.get('LOG_LEVEL', 'INFO'),
        'log_format': os.environ.get('LOG_FORMAT', 'text'),
    }

    # LLM provider status
    llm_keys = {}
    for env_var in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY']:
        val = os.environ.get(env_var, '')
        llm_keys[env_var] = 'Configured' if val else 'Not set'

    return render_template(
        'admin/settings.html',
        settings=settings_data,
        llm_keys=llm_keys,
    )


@admin_bp.route('/email-logs')
def email_logs():
    from app.models.email_log import EmailLog
    page = request.args.get('page', 1, type=int)
    logs = EmailLog.query.order_by(EmailLog.sent_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    return render_template('admin/email_logs.html', logs=logs)


@admin_bp.route('/email-send-digest', methods=['POST'])
def send_digest_now():
    """Manually trigger daily digest emails for all subscribed users."""
    from app.email.tasks import send_daily_digest
    send_daily_digest.delay()
    flash('Daily digest job queued.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/email-preview')
def email_preview():
    """Preview today's daily digest as HTML."""
    from app.models.user import User
    from app.email.digest import build_daily_digest

    # Use first admin user or current user as preview target
    user = current_user
    digest = build_daily_digest(user)

    if not digest:
        flash('No articles in the last 24 hours for preview.', 'info')
        return redirect(url_for('admin.dashboard'))

    return render_template(
        'email/daily_digest.html',
        articles=digest['articles'],
        date=digest['date'],
        user=user,
    )
