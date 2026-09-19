"""Operator accounting corrections. Nested under the existing Admin guard."""
from flask import Blueprint, abort, current_app, redirect, request, url_for
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.llm.budget import BudgetError, reconcile

llm_budget_bp = Blueprint('llm_budget', __name__)


@llm_budget_bp.route('/llm-usage/reservations/<permit>/reconcile', methods=['POST'])
def reconcile_reservation(permit):
    fields = {'csrf_token', 'expected_state', 'final_cost', 'evidence_note', 'confirmed_final', 'confirmed_stopped'}
    if (set(request.form) != fields or request.files
            or any(len(v) != 1 for _, v in request.form.lists())
            or request.form['confirmed_final'] != '1' or request.form['confirmed_stopped'] != '1'):
        abort(400, description='Final supplier charge and stopped execution must be confirmed')
    actor_id = current_user.id
    db.session.remove()
    try:
        reconcile(permit, request.form['expected_state'], request.form['final_cost'], request.form['evidence_note'], actor_id)
    except ValueError:
        abort(400, description='Invalid reconciliation')
    except BudgetError:
        abort(409, description='Invalid accounting input or reservation changed')
    except SQLAlchemyError:
        current_app.logger.warning('llm_reconciliation_storage_error')
        abort(503, description='Reconciliation storage unavailable')
    return redirect(url_for('admin.llm_usage'))
