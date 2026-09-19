"""Learning controls inherit Admin authorization, CSRF and private headers."""
from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user

from app.crawlers import learning, _learning_history, _learning_delivery, validation
from app.extensions import db
from app.models import NewsSource, CrawlRepairSession, CrawlRepairAttempt, CrawlRepairRetry, LLMReservation

crawl_learning_bp = Blueprint('learning', __name__)


def form():
    if set(request.form) != {'csrf_token'} or len(request.form.getlist('csrf_token')) != 1 or request.files:
        abort(400, description='Invalid learning form')


def location(source_id, identity):
    return url_for('admin.crawl_config.learning.detail', source_id=source_id, identity=identity)


@crawl_learning_bp.route('/versions/<int:version_id>/previews/<int:report_id>/learn', methods=['POST'])
def start(source_id, version_id, report_id):
    form()
    actor_id = current_user.id
    db.session.remove()
    try:
        identity = learning.start(source_id, version_id, report_id, actor_id)
    except LookupError:
        abort(404)
    except (ValueError, TypeError, OSError, RecursionError):
        abort(409, description='Learning disabled or current policy, history or evidence unavailable')
    # The committed intent survives broker failure; recovery may redeliver it.
    _learning_delivery.publish(identity)
    return redirect(location(source_id, identity))


@crawl_learning_bp.route('/learning/<identity>')
def detail(source_id, identity):
    source = NewsSource.query.get_or_404(source_id)
    item = CrawlRepairSession.query.filter_by(id=identity, source_id=source_id).first_or_404()
    attempts = CrawlRepairAttempt.query.filter_by(session_id=identity).order_by(CrawlRepairAttempt.number).all()
    reservations = (LLMReservation.query.join(CrawlRepairAttempt)
                    .filter(CrawlRepairAttempt.session_id == identity).all())
    spent = sum(r.actual_usd or 0 for r in reservations if r.state in ('settled', 'reconciled'))
    held = sum(r.reserved_usd for r in reservations if r.state not in ('settled', 'reconciled'))
    history = _learning_history.inspect(db.session)
    return render_template('admin/crawl_learning.html', source=source, learning=item,
                           attempts=attempts, reservations=reservations, spent=spent, held=held, history=history,
                           delivery_protocol=_learning_delivery.VERSION if item.dispatch_due_at is not None else 'unavailable',
                           delivery_key=_learning_delivery.key(item) if item.state == 'queued' and history.state == 'tracked' else None,
                           validation=validation.view(db.session, identity),
                           retry_reason=learning.retry_reason(db.session, item),
                           retry_events=CrawlRepairRetry.query.filter_by(session_id=identity)
                               .order_by(CrawlRepairRetry.number).all() if history.state == 'tracked' else [],
                           exposure_documents={a.id: _learning_history.display_documents(a)
                                               if history.state == 'tracked' else None for a in attempts})


@crawl_learning_bp.route('/learning/<identity>/retry', methods=['POST'])
def retry(source_id, identity):
    fields = {'csrf_token', 'after_round', 'note'}
    if (set(request.form) != fields or request.files
            or any(len(request.form.getlist(key)) != 1 for key in fields)
            or request.form['after_round'] not in ('0', '1', '2')
            or not 1 <= len(request.form['note'].strip()) <= 300):
        abort(400, description='Invalid retry form')
    actor_id = current_user.id
    db.session.remove()
    try:
        learning.retry(source_id, identity, int(request.form['after_round']), actor_id, request.form['note'].strip())
    except LookupError:
        abort(404)
    except (ValueError, TypeError, OSError, RecursionError):
        abort(409, description='Retry unavailable: current authority and never-admitted work required')
    _learning_delivery.publish(identity)
    return redirect(location(source_id, identity))


@crawl_learning_bp.route('/learning/<identity>/validate', methods=['POST'])
def validate(source_id, identity):
    form()
    actor_id = current_user.id
    db.session.remove()
    try:
        validation.run(source_id, identity, actor_id)
    except LookupError:
        abort(404)
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        abort(409, description='Validation unavailable: current authority and new base evidence required')
    return redirect(location(source_id, identity))


@crawl_learning_bp.route('/learning/<identity>/cancel', methods=['POST'])
def cancel(source_id, identity):
    form()
    db.session.remove()
    try:
        learning.cancel(source_id, identity)
    except LookupError:
        abort(404)
    return redirect(location(source_id, identity))
