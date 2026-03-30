import os
from flask import Flask, render_template
from .config import config_map
from .extensions import db, migrate, mail, login_manager, csrf, init_redis


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(
        __name__,
        template_folder='web/templates',
        static_folder='web/static',
    )
    app.config.from_object(config_map[config_name])

    # Add email templates to Jinja search path
    import jinja2
    email_template_path = os.path.join(os.path.dirname(__file__), 'email', 'templates')
    app.jinja_loader = jinja2.ChoiceLoader([
        app.jinja_loader,
        jinja2.FileSystemLoader(email_template_path),
    ])

    # Logging and monitoring
    from .logging_config import setup_logging, init_sentry
    setup_logging(app)
    init_sentry(app)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    init_redis(app)

    # Login manager config
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        from .models.user import User
        return db.session.get(User, int(user_id))

    # Register blueprints
    from .web.views.news import news_bp
    from .web.views.company import company_bp
    from .web.views.admin import admin_bp
    from .web.views.subscription import subscription_bp
    from .web.views.auth import auth_bp
    from .web.views.health import health_bp
    from .api.v1.routes import api_bp

    app.register_blueprint(news_bp)
    app.register_blueprint(company_bp, url_prefix='/companies')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(subscription_bp, url_prefix='/subscribe')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(health_bp)
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    # Exempt API and health from CSRF
    csrf.exempt(api_bp)
    csrf.exempt(health_bp)

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    # Custom Jinja filters
    @app.template_filter('paragraphs')
    def paragraphs_filter(text):
        """Convert plain text with newlines into HTML paragraphs."""
        if not text:
            return ''
        from markupsafe import Markup, escape
        paras = [p.strip() for p in text.split('\n') if p.strip()]
        html = ''.join(f'<p>{escape(p)}</p>' for p in paras)
        return Markup(html)

    @app.template_filter('markdown_light')
    def markdown_light_filter(text):
        """Render light markdown: ## headers, **bold**, - bullets, line breaks."""
        if not text:
            return ''
        from markupsafe import Markup
        import re
        lines = text.split('\n')
        out = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # ## Header
            if line.startswith('## '):
                out.append(f'<h6 class="fw-bold mt-3 mb-1">{line[3:]}</h6>')
            # - Bullet
            elif line.startswith('- '):
                content = line[2:]
                content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
                out.append(f'<li>{content}</li>')
            else:
                content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
                out.append(f'<p class="mb-1">{content}</p>')
        # Wrap consecutive <li> in <ul>
        html = '\n'.join(out)
        html = re.sub(r'((?:<li>.*?</li>\n?)+)', r'<ul class="mb-2">\1</ul>', html)
        return Markup(html)

    # Template context
    @app.context_processor
    def inject_now():
        from datetime import datetime
        return {'now': datetime.utcnow}

    return app
