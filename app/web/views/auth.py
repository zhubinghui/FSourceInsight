from urllib.parse import unquote, urlsplit

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.user import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if (user and user.is_active and user.password_hash and len(password) <= 1024
                and check_password_hash(user.password_hash, password)):
            login_user(user)
            next_page = request.args.get('next', '')
            # Accept only local absolute paths. Reject browser-normalized slashes,
            # controls and encoded authority components as well as external URLs.
            decoded = unquote(next_page)
            if (not decoded.startswith('/') or decoded.startswith('//')
                    or '\\' in decoded or any(ord(c) < 32 or ord(c) == 127 for c in decoded)):
                next_page = ''
            elif urlsplit(decoded).netloc or urlsplit(decoded).scheme:
                next_page = ''
            flash('Logged in successfully.', 'success')
            return redirect(next_page or url_for('news.index'))
        else:
            flash('Invalid email or password.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('news.index'))


@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """First-time admin setup. Only works if no admin exists yet."""
    admin_exists = User.query.filter_by(is_admin=True).first()
    if admin_exists:
        flash('Admin already exists. Please log in.', 'info')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        name = request.form.get('name', '').strip()

        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('auth/setup.html')

        user = User(
            email=email,
            name=name,
            password_hash=generate_password_hash(password),
            is_admin=True,
            is_active_user=True,
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Admin account created! You are now logged in.', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('auth/setup.html')
