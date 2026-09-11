"""Read-only, admin-only capture provenance, independent of preview pruning."""
import json

from flask import Blueprint, render_template

from app.crawlers import _capture
from app.models.crawl_schema import CrawlCaptureManifest, CrawlSourceProfile
from app.models.source import NewsSource

crawl_capture_bp = Blueprint('capture', __name__, url_prefix='/captures')


@crawl_capture_bp.route('')
def index(source_id):
    source = NewsSource.query.get_or_404(source_id)
    profile = CrawlSourceProfile.query.filter_by(source_id=source_id).one_or_none()
    records = (CrawlCaptureManifest.query.filter_by(profile_id=profile.id)
               .order_by(CrawlCaptureManifest.sequence.desc()).limit(50).all()) if profile else []
    state = _capture.history_state(profile)
    return render_template('admin/crawl_capture_history.html', source=source, records=records,
                           history_state=state, generation=profile.capture_generation if profile else 0)


@crawl_capture_bp.route('/<int:capture_id>')
def detail(source_id, capture_id):
    source = NewsSource.query.get_or_404(source_id)
    record = (CrawlCaptureManifest.query.join(CrawlSourceProfile)
              .filter(CrawlSourceProfile.source_id == source_id, CrawlCaptureManifest.id == capture_id)
              .first_or_404())
    try:
        _capture.checked_document(record, source_id)
        available = True
    except (ValueError, TypeError, RecursionError):
        available = False
    return render_template('admin/crawl_capture.html', source=source, record=record,
                           available=available, document=json.dumps(record.document, ensure_ascii=False, indent=2) if available else None)
