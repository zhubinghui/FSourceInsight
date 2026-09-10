"""Admin-owned source permissions, separate from recipe candidates."""
import difflib
import json

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user

from app.crawlers._preview import preview_policy, source_fingerprint
from app.crawlers import _source_policy
from app.extensions import db
from app.models.crawl_schema import CrawlPolicyVersion, CrawlSourceProfile
from app.models.source import NewsSource

crawl_policy_bp = Blueprint('policy', __name__, url_prefix='/policies')


@crawl_policy_bp.route('', methods=['GET', 'POST'])
def index(source_id, revoke=False):
    source_query = NewsSource.query.filter_by(id=source_id)
    profile_query = CrawlSourceProfile.query.filter_by(source_id=source_id)
    if request.method == 'POST':
        source_query = source_query.populate_existing().with_for_update()
        profile_query = profile_query.populate_existing().with_for_update()
    source = source_query.first_or_404()
    profile = profile_query.one_or_none()
    generation = profile.generation if profile else 0
    source_hash = source_fingerprint(source)
    if request.method == 'POST':
        fields = {'csrf_token', 'expected_generation', 'expected_source'}
        if not revoke:
            fields |= {'allowed_hosts', 'quality_kind'}
        if (set(request.form) != fields
                or any(len(values) != 1 for _, values in request.form.lists()) or request.files):
            abort(400, description='Invalid policy form')
        if revoke:
            document = {'format': 'source-policy.v1', 'action': 'revoke'}
        else:
            try:
                policy, quality = preview_policy(request.form['allowed_hosts'], request.form['quality_kind'])
                # Stored canonical hosts must be valid inputs too (including IDNA size).
                policy, quality = preview_policy('\n'.join(policy.allowed_hosts), request.form['quality_kind'])
                document = _source_policy.document(policy, quality, request.form['quality_kind'])
            except ValueError:
                abort(400, description='Invalid source policy')
        try:
            document_hash = _source_policy.fingerprint(document)
        except ValueError:
            abort(400, description='Invalid source policy')
        if (not revoke and not source.is_active):
            abort(409, description='Enable the source before granting policy')
        if (request.form['expected_generation'] != str(generation) or request.form['expected_source'] != source_hash):
            abort(409, description='Configuration changed; reload before saving policy')
        if profile is None:
            profile = CrawlSourceProfile(source_id=source_id)
            db.session.add(profile)
            db.session.flush()
        changed = db.session.execute(db.update(CrawlSourceProfile)
                                     .where(CrawlSourceProfile.id == profile.id, CrawlSourceProfile.generation == generation)
                                     .values(generation=generation + 1, policy_generation=generation + 1))
        if changed.rowcount != 1:
            db.session.rollback()
            abort(409, description='Configuration changed; reload before saving policy')
        record = CrawlPolicyVersion(profile_id=profile.id, generation=generation + 1, document=document,
                                    source_generation=profile.source_generation, source_fingerprint=source_hash,
                                    document_hash=document_hash, created_by_id=current_user.id)
        db.session.add(record)
        db.session.flush()
        policy_id = record.id
        db.session.commit()
        return redirect(url_for('admin.crawl_config.policy.version', source_id=source_id, policy_id=policy_id))
    history = (CrawlPolicyVersion.query.filter_by(profile_id=profile.id)
               .order_by(CrawlPolicyVersion.id.desc()).limit(50).all()) if profile else []
    state = _source_policy.state(_source_policy.latest(profile), source, profile)
    return render_template('admin/crawl_policy.html', source=source, history=history,
                           policy_state=state, generation=generation, source_hash=source_hash)


@crawl_policy_bp.route('/revoke', methods=['POST'])
def revoke(source_id):
    return index(source_id, revoke=True)


@crawl_policy_bp.route('/<int:policy_id>')
def version(source_id, policy_id):
    source = NewsSource.query.get_or_404(source_id)
    record = (CrawlPolicyVersion.query.join(CrawlSourceProfile)
              .filter(CrawlSourceProfile.source_id == source_id, CrawlPolicyVersion.id == policy_id).first_or_404())
    profile = db.session.get(CrawlSourceProfile, record.profile_id)
    previous = (CrawlPolicyVersion.query.filter(CrawlPolicyVersion.profile_id == record.profile_id,
                                               CrawlPolicyVersion.generation < record.generation)
                .order_by(CrawlPolicyVersion.generation.desc()).first())
    document_text = _display_document(record)
    diff = '\n'.join(difflib.unified_diff(
        (_display_document(previous) if previous else '{}').splitlines(), document_text.splitlines(),
        fromfile=f'policy-{previous.id}' if previous else 'no-policy', tofile=f'policy-{record.id}', lineterm=''))
    current = _source_policy.latest(profile)
    state = (_source_policy.state(current, source, profile) if current and current.id == record.id else 'superseded')
    return render_template('admin/crawl_policy_version.html', source=source, policy=record,
                           document_text=document_text, previous=previous, diff=diff, policy_state=state)


def _display_document(record):
    try:
        value = json.dumps(record.document, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
        if len(value.encode()) <= 16384:
            return value
    except (ValueError, TypeError, RecursionError):
        pass
    return 'Policy document unavailable.'
