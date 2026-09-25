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
