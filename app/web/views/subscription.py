from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.user import User, KeywordSubscription
from app.models.company import Company

subscription_bp = Blueprint('subscription', __name__)


@subscription_bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        keywords_raw = request.form.get('keywords', '').strip()
        company_id = request.form.get('company_id', type=int)

        if not email:
            flash('Email is required.', 'error')
            return redirect(url_for('subscription.index'))

        # Get or create user
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email, receive_daily_digest=True)
            db.session.add(user)
            db.session.flush()

        added = 0

        # Add keyword subscriptions (comma-separated)
        if keywords_raw:
            for kw in keywords_raw.split(','):
                kw = kw.strip()
                if not kw:
                    continue
                existing = KeywordSubscription.query.filter_by(
                    user_id=user.id, keyword=kw
                ).first()
                if not existing:
                    db.session.add(KeywordSubscription(user_id=user.id, keyword=kw))
                    added += 1

        # Add company name as keyword subscription
        if company_id:
            company = Company.query.get(company_id)
            if company:
                existing = KeywordSubscription.query.filter_by(
                    user_id=user.id, keyword=company.name
                ).first()
                if not existing:
                    db.session.add(KeywordSubscription(
                        user_id=user.id, keyword=company.name
                    ))
                    added += 1

        db.session.commit()

        if added:
            flash(f'{added} subscription(s) added successfully.', 'success')
        else:
            flash('No new subscriptions added (may already exist).', 'info')

        return redirect(url_for('subscription.manage', email=email))

    companies = Company.query.order_by(Company.name).all()
    return render_template('subscription/index.html', companies=companies)


@subscription_bp.route('/manage')
def manage():
    email = request.args.get('email', '').strip()
    if not email:
        return render_template('subscription/manage.html', user=None, subscriptions=[])

    user = User.query.filter_by(email=email).first()
    subscriptions = []
    if user:
        subscriptions = user.subscriptions.filter_by(is_active=True).all()

    return render_template('subscription/manage.html', user=user, subscriptions=subscriptions)


@subscription_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    """User preference settings (language, digest toggle)."""
    email = request.args.get('email', '').strip()
    if request.method == 'POST':
        email = request.form.get('email', '').strip()

    user = User.query.filter_by(email=email).first() if email else None

    if request.method == 'POST' and user:
        user.preferred_language = request.form.get('preferred_language', 'zh')
        user.receive_daily_digest = request.form.get('receive_daily_digest') == 'on'
        user.name = request.form.get('name', '').strip() or user.name

        # Set password if provided (for first-time or change)
        new_password = request.form.get('password', '').strip()
        if new_password:
            user.password_hash = generate_password_hash(new_password)

        db.session.commit()
        flash('Settings updated.', 'success')
        return redirect(url_for('subscription.settings', email=email))

    return render_template('subscription/settings.html', user=user, email=email)


@subscription_bp.route('/<int:sub_id>/delete', methods=['POST'])
def delete(sub_id):
    sub = KeywordSubscription.query.get_or_404(sub_id)
    email = sub.user.email
    db.session.delete(sub)
    db.session.commit()
    flash('Subscription removed.', 'success')
    return redirect(url_for('subscription.manage', email=email))


@subscription_bp.route('/<int:sub_id>/toggle', methods=['POST'])
def toggle(sub_id):
    sub = KeywordSubscription.query.get_or_404(sub_id)
    sub.is_active = not sub.is_active
    db.session.commit()
    status = 'activated' if sub.is_active else 'paused'
    flash(f'Subscription "{sub.keyword}" {status}.', 'success')
    return redirect(url_for('subscription.manage', email=sub.user.email))
