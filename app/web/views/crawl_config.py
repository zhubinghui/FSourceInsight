"""Real admin draft operations, nested under the existing admin access guard."""
import json
import uuid
from dataclasses import asdict

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import SQLAlchemyError

from app.crawlers import _capture, _evidence, _source_policy
from app.crawlers.schema import validate_recipe
from app.crawlers.engine import CrawlEngine
from app.crawlers._preview import preview_policy, report_data, source_fingerprint
from app.extensions import db
from app.models.crawl_schema import CrawlSchemaVersion, CrawlSourceProfile, CrawlPreviewReport, CrawlCaptureManifest
from app.models.source import NewsSource
from .crawl_policy import crawl_policy_bp
from .crawl_capture import crawl_capture_bp

crawl_config_bp = Blueprint('crawl_config', __name__, url_prefix='/sources/<int:source_id>/crawl-config')
crawl_config_bp.register_blueprint(crawl_policy_bp)
crawl_config_bp.register_blueprint(crawl_capture_bp)


@crawl_config_bp.errorhandler(SQLAlchemyError)
def storage_error(error):
    db.session.rollback()
    # SQLAlchemy exception strings can include the full private recipe parameters.
    current_app.logger.warning('crawl_candidate_storage_error')
    return 'Candidate storage unavailable; no successful save was confirmed.', 503


@crawl_config_bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@crawl_config_bp.route('', methods=['GET', 'POST'])
def index(source_id):
    source = NewsSource.query.get_or_404(source_id)
    profile = CrawlSourceProfile.query.filter_by(source_id=source_id).one_or_none()
    if request.method == 'POST':
        if (set(request.form) - {'csrf_token', 'recipe'}
                or any(len(values) != 1 for _, values in request.form.lists())):
            abort(400, description='Invalid candidate form')
        try:
            recipe = validate_recipe(request.form.get('recipe', ''))
            if recipe.to_dict()['source_id'] != source_id:
                raise ValueError('Source mismatch')
        except ValueError:
            abort(400, description='Invalid recipe for this source')
        if profile is None:
            profile = CrawlSourceProfile(source_id=source_id)
            db.session.add(profile)
            db.session.flush()
        candidate = CrawlSchemaVersion(
            profile_id=profile.id, recipe=recipe.to_dict(), recipe_hash=recipe.fingerprint,
            base_generation=profile.generation, created_by_id=current_user.id,
        )
        db.session.add(candidate)
        db.session.flush()
        version_id = candidate.id
        db.session.commit()
        return redirect(url_for('admin.crawl_config.version', source_id=source_id, version_id=version_id))
    versions = (CrawlSchemaVersion.query.filter_by(profile_id=profile.id)
                .order_by(CrawlSchemaVersion.id.desc()).limit(50).all()) if profile else []
    return render_template('admin/crawl_config.html', source=source, versions=versions)


@crawl_config_bp.route('/evidence/cleanup', methods=['POST'])
def cleanup_evidence(source_id):
    NewsSource.query.get_or_404(source_id)
    if set(request.form) != {'csrf_token'} or len(request.form.getlist('csrf_token')) != 1 or request.files:
        abort(400, description='Invalid cleanup form')
    db.session.remove()
    try:
        count = _evidence.cleanup(current_app.config.get('CRAWL_EVIDENCE_DIR'))
    except (OSError, ValueError):
        current_app.logger.warning('crawl_evidence_cleanup_error')
        abort(503, description='Evidence cleanup unavailable')
    flash(f'Removed {count} expired evidence bundles from the configured private store.', 'success')
    return redirect(url_for('admin.crawl_config.index', source_id=source_id))


@crawl_config_bp.route('/versions/<int:version_id>')
def version(source_id, version_id):
    source = NewsSource.query.get_or_404(source_id)
    candidate = (CrawlSchemaVersion.query.join(CrawlSourceProfile)
                 .filter(CrawlSourceProfile.source_id == source_id, CrawlSchemaVersion.id == version_id)
                 .first_or_404())
    profile = db.session.get(CrawlSourceProfile, candidate.profile_id)
    policy_record = _source_policy.latest(profile)
    policy_state = _source_policy.state(policy_record, source, profile)
    reports = (CrawlPreviewReport.query.filter_by(version_id=candidate.id)
               .order_by(CrawlPreviewReport.id.desc()).limit(20).all())
    return render_template('admin/crawl_schema_version.html', source=source, candidate=candidate,
                           generation=profile.generation, source_hash=source_fingerprint(source), reports=reports,
                           recipe_text=json.dumps(candidate.recipe, ensure_ascii=False, indent=2),
                           policy_record=policy_record, policy_state=policy_state,
                           policy_configured=profile.policy_generation is not None or policy_record is not None)


@crawl_config_bp.route('/versions/<int:version_id>/preview', methods=['POST'])
def preview(source_id, version_id):
    base_fields = {'csrf_token', 'expected_generation', 'expected_source'}
    if (not base_fields <= set(request.form)
            or set(request.form) - base_fields - {'retain_evidence', 'allowed_hosts', 'quality_kind', 'expected_policy'}
            or any(len(values) != 1 for _, values in request.form.lists()) or request.files
            or request.form.get('retain_evidence') not in {None, '1'}):
        abort(400, description='Invalid preview form')
    retain = request.form.get('retain_evidence') == '1'
    if retain:
        try:
            with _evidence.root(current_app.config.get('CRAWL_EVIDENCE_DIR')):
                pass
        except (OSError, ValueError):
            abort(503, description='Evidence storage unavailable')
    source = NewsSource.query.filter_by(id=source_id).populate_existing().with_for_update().first_or_404()
    candidate = (CrawlSchemaVersion.query.join(CrawlSourceProfile)
                 .filter(CrawlSourceProfile.source_id == source_id, CrawlSchemaVersion.id == version_id)
                 .first_or_404())
    profile = CrawlSourceProfile.query.filter_by(id=candidate.profile_id).populate_existing().with_for_update().one()
    generation, source_hash, actor_id = profile.generation, source_fingerprint(source), current_user.id
    source_generation = profile.source_generation
    if (not source.is_active or request.form.get('expected_generation') != str(generation)
            or request.form.get('expected_source') != source_hash):
        abort(409, description='Source configuration changed; reload before previewing')
    policy_record = _source_policy.latest(profile)
    permission = None
    if profile.policy_generation is not None or policy_record is not None:
        if (_source_policy.state(policy_record, source, profile) != 'effective'
                or request.form.get('expected_policy') != str(policy_record.id)):
            abort(409, description='Source policy unavailable or changed; review policy before previewing')
        if set(request.form) - {'retain_evidence'} != base_fields | {'expected_policy'}:
            abort(400, description='Invalid preview form')
        policy, quality = _source_policy.inputs(policy_record)
        permission = {'id': policy_record.id, 'hash': policy_record.document_hash}
    else:
        if set(request.form) - {'retain_evidence'} != base_fields | {'allowed_hosts', 'quality_kind'}:
            abort(400, description='Invalid preview form')
        try:
            policy, quality = preview_policy(request.form['allowed_hosts'], request.form['quality_kind'])
        except ValueError:
            abort(400, description='Invalid preview input')
    try:
        recipe = validate_recipe(candidate.recipe)
        if recipe.fingerprint != candidate.recipe_hash:
            raise ValueError('Changed candidate')
    except ValueError:
        abort(400, description='Invalid preview input')
    if _capture.history_state(profile) == 'unavailable':
        abort(409, description='Capture history unavailable; review source before previewing')
    # Copy only immutable inputs, then release the request's database transaction.
    db.session.remove()
    try:
        result = CrawlEngine(source_id, recipe=recipe, fetch_policy=policy, profile=quality).preview()
        payload = report_data(result, policy, quality)
        payload['source_policy'] = permission
        payload['capture_id'] = uuid.uuid4().hex
        if retain:
            inputs = _evidence.binding(source_id, version_id, generation, source_hash,
                                       recipe.fingerprint, CrawlEngine.VERSION, policy, quality, payload['capture_id'])
            payload['evidence'] = _evidence.save(current_app.config.get('CRAWL_EVIDENCE_DIR'), result.snapshots, inputs)
            payload['raw_snapshots_retained'] = True
        if len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()) > 65536:
            raise ValueError('Preview report too large')
    except Exception:
        # Unexpected process/parser/report failures may contain private page text.
        current_app.logger.warning('crawl_preview_execution_error')
        abort(503, description='Preview could not be completed; no report was saved')
    report = CrawlPreviewReport(
        version_id=version_id, generation=generation, source_fingerprint=source_hash,
        recipe_hash=recipe.fingerprint, engine_version=CrawlEngine.VERSION,
        created_by_id=actor_id, status=result.status, report=payload,
    )
    source = NewsSource.query.filter_by(id=source_id).populate_existing().with_for_update().first_or_404()
    profile = CrawlSourceProfile.query.filter_by(source_id=source_id).populate_existing().with_for_update().one()
    if generation != profile.generation or source_hash != source_fingerprint(source):
        report.status = 'stale'
    if _capture.history_state(profile) == 'unavailable':
        abort(409, description='Capture history changed during preview; no report saved')
    db.session.add(report)
    db.session.flush()
    report_id = report.id
    manifest = _capture.document(source_id, source_generation, report, result.snapshots)
    sequence = profile.capture_generation + 1
    manifest['sequence'] = sequence
    document_hash = _capture.fingerprint(manifest)
    updated = db.session.execute(db.update(CrawlSourceProfile).where(CrawlSourceProfile.id == profile.id,
                                 CrawlSourceProfile.capture_generation == sequence - 1)
                                 .values(capture_generation=sequence).execution_options(synchronize_session=False))
    if updated.rowcount != 1:
        abort(409, description='Capture history changed; no report saved')
    capture = CrawlCaptureManifest(profile_id=profile.id, version_id=version_id, preview_report_id=report_id,
                                   sequence=sequence,
                                   document=manifest, document_hash=document_hash, created_by_id=actor_id)
    db.session.add(capture)
    db.session.flush()
    report.report = {**payload, 'capture_manifest': {'id': capture.id, 'hash': capture.document_hash}}
    if len(json.dumps(report.report, ensure_ascii=False, allow_nan=False).encode()) > 65536:
        abort(503, description='Preview report too large')
    cutoff = (db.session.query(CrawlPreviewReport.id).filter_by(version_id=version_id)
              .order_by(CrawlPreviewReport.id.desc()).offset(19).limit(1).scalar())
    if cutoff is not None:
        CrawlPreviewReport.query.filter(CrawlPreviewReport.version_id == version_id,
                                        CrawlPreviewReport.id < cutoff).delete(synchronize_session=False)
    db.session.commit()
    return redirect(url_for('admin.crawl_config.preview_report', source_id=source_id, version_id=version_id, report_id=report_id))


def _stored_inputs(source_id, candidate, report):
    data = report.report
    kind = 'bulletin' if data['quality_profile']['min_content_chars'] == 80 else 'news'
    policy, quality = preview_policy('\n'.join(data['fetch_policy']['allowed_hosts']), kind)
    recipe = validate_recipe(candidate.recipe)
    if (data['format'] != 'admin-preview.v1' or recipe.fingerprint != candidate.recipe_hash
            or recipe.fingerprint != report.recipe_hash
            or json.loads(json.dumps(asdict(policy))) != data['fetch_policy']
            or json.loads(json.dumps(asdict(quality))) != data['quality_profile']):
        raise ValueError('Incompatible preview inputs')
    inputs = _evidence.binding(source_id, candidate.id, report.generation, report.source_fingerprint,
                               report.recipe_hash, report.engine_version, policy, quality, data.get('capture_id'))
    return inputs, recipe, policy, quality


@crawl_config_bp.route('/versions/<int:version_id>/previews/<int:report_id>/replay', methods=['POST'])
def replay(source_id, version_id, report_id):
    if (set(request.form) != {'csrf_token'} or len(request.form.getlist('csrf_token')) != 1 or request.files):
        abort(400, description='Invalid replay form')
    source = NewsSource.query.get_or_404(source_id)
    report = (CrawlPreviewReport.query.join(CrawlSchemaVersion).join(CrawlSourceProfile)
              .filter(CrawlSourceProfile.source_id == source_id, CrawlPreviewReport.version_id == version_id,
                      CrawlPreviewReport.id == report_id).first_or_404())
    candidate = db.session.get(CrawlSchemaVersion, version_id)
    profile = db.session.get(CrawlSourceProfile, candidate.profile_id)
    if (not source.is_active or report.status == 'stale' or report.generation != profile.generation
            or report.source_fingerprint != source_fingerprint(source) or report.engine_version != CrawlEngine.VERSION):
        abort(409, description='Source configuration changed; create a new preview')
    if not _source_policy.matches_report(_source_policy.latest(profile), source, profile, report.report):
        abort(409, description='Source policy unavailable or changed; create a new preview')
    try:
        inputs, recipe, policy, quality = _stored_inputs(source_id, candidate, report)
        reference = dict(report.report.get('evidence') or {})
        db.session.remove()
        snapshots = _evidence.load(current_app.config.get('CRAWL_EVIDENCE_DIR'), reference, inputs)
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        abort(409, description='Evidence unavailable or expired; create a new preview')
    try:
        result = CrawlEngine(source_id, recipe=recipe, fetch_policy=policy, profile=quality, snapshots=snapshots).preview()
        data = report_data(result, policy, quality)
    except Exception:
        current_app.logger.warning('crawl_replay_execution_error')
        abort(503, description='Replay could not be completed')
    return preview_report(source_id, version_id, report_id, replay_data=data)


@crawl_config_bp.route('/versions/<int:version_id>/previews/<int:report_id>')
def preview_report(source_id, version_id, report_id, replay_data=None):
    source = NewsSource.query.get_or_404(source_id)
    report = (CrawlPreviewReport.query.join(CrawlSchemaVersion).join(CrawlSourceProfile)
              .filter(CrawlSourceProfile.source_id == source_id, CrawlPreviewReport.version_id == version_id,
                      CrawlPreviewReport.id == report_id).first_or_404())
    candidate = db.session.get(CrawlSchemaVersion, version_id)
    profile = db.session.get(CrawlSourceProfile, candidate.profile_id)
    stale = (report.status == 'stale' or not source.is_active or report.generation != profile.generation
             or report.source_fingerprint != source_fingerprint(source)
             or report.recipe_hash != candidate.recipe_hash or report.engine_version != CrawlEngine.VERSION
             or not _source_policy.matches_report(_source_policy.latest(profile), source, profile, report.report))
    try:
        inputs, _, _, _ = _stored_inputs(source_id, candidate, report)
        evidence_status = _evidence.inspect(current_app.config.get('CRAWL_EVIDENCE_DIR'), report.report.get('evidence'), inputs)
    except (ValueError, KeyError, TypeError, RecursionError):
        evidence_status, stale = 'unavailable', True
    if replay_data is not None and (stale or evidence_status != 'available'):
        abort(409, description='Inputs or evidence changed during replay')
    return render_template('admin/crawl_preview_report.html', source=source, preview=report,
                           version_id=version_id, stale=stale, evidence_status=evidence_status, replay_data=replay_data,
                           policy_reference_id=_source_policy.reference_id(report.report.get('source_policy')),
                           capture_reference_id=_capture.reference_id(report, profile))
