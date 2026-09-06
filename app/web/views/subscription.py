from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.user import KeywordSubscription
from app.models.company import Company

subscription_bp = Blueprint('subscription', __name__)


@subscription_bp.before_request
@login_required
def require_account_owner():
    """Email is never an authentication credential, even for administrators."""
    # Reject legacy cross-account links/forms rather than silently editing self.
    emails = request.args.getlist('email') + request.form.getlist('email')
    if any(email.strip() and email.strip() != current_user.email for email in emails):
        abort(403)


@subscription_bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        keywords = [kw.strip() for kw in request.form.get('keywords', '').split(',') if kw.strip()]
        company_id = request.form.get('company_id', type=int)
        if company_id:
            company = db.get_or_404(Company, company_id)
            keywords.append(company.name)
        keywords = list(dict.fromkeys(keywords))
        if len(keywords) > 50 or any(len(kw) > 200 for kw in keywords):
            abort(400, description='Too many keywords or keyword longer than 200 characters.')

        added = 0
        for keyword in keywords:
            existing = KeywordSubscription.query.filter_by(
                user_id=current_user.id, keyword=keyword
            ).first()
            if not existing:
                db.session.add(KeywordSubscription(user_id=current_user.id, keyword=keyword))
                added += 1
        db.session.commit()
        if added:
            flash(f'{added} subscription(s) added successfully.', 'success')
        else:
            flash('No new subscriptions added (may already exist).', 'info')
        return redirect(url_for('subscription.manage'))

    companies = Company.query.order_by(Company.name).all()
    return render_template('subscription/index.html', companies=companies, user=current_user)


@subscription_bp.route('/manage')
def manage():
    # Include paused subscriptions so the owner can resume them.
    subscriptions = current_user.subscriptions.order_by(KeywordSubscription.id).all()
    return render_template('subscription/manage.html', user=current_user, subscriptions=subscriptions)


@subscription_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    """Preferences belong to the authenticated account; changing its password needs proof."""
    user = current_user
    if request.method == 'POST':
        language = request.form.get('preferred_language', user.preferred_language or 'zh')
        name = request.form.get('name', '').strip()
        new_password = request.form.get('password', '')
        if language not in {'zh', 'en', 'fr'} or len(name) > 200:
            abort(400, description='Invalid language or display name.')
        if new_password:
            old_password = request.form.get('current_password', '')
            if (not 8 <= len(new_password) <= 1024 or len(old_password) > 1024
                    or not user.password_hash
                    or not check_password_hash(user.password_hash, old_password)):
                abort(400, description='A valid current password and a new password of at least 8 characters are required.')

        # Validate the entire request before changing any preferences or credentials.
        user.preferred_language = language
        user.receive_daily_digest = request.form.get('receive_daily_digest') == 'on'
        user.name = name or user.name
        if new_password:
            user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash('Settings updated.', 'success')
        return redirect(url_for('subscription.settings'))

    return render_template('subscription/settings.html', user=user)


@subscription_bp.route('/<int:sub_id>/delete', methods=['POST'])
def delete(sub_id):
    sub = KeywordSubscription.query.filter_by(id=sub_id, user_id=current_user.id).first_or_404()
    db.session.delete(sub)
    db.session.commit()
    flash('Subscription removed.', 'success')
    return redirect(url_for('subscription.manage'))


@subscription_bp.route('/<int:sub_id>/toggle', methods=['POST'])
def toggle(sub_id):
    sub = KeywordSubscription.query.filter_by(id=sub_id, user_id=current_user.id).first_or_404()
    sub.is_active = not sub.is_active
    db.session.commit()
    status = 'activated' if sub.is_active else 'paused'
    flash(f'Subscription "{sub.keyword}" {status}.', 'success')
    return redirect(url_for('subscription.manage'))
