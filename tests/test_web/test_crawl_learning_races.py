"""Storage/cache boundary races, observed through real learning controls."""
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from tests.test_web import test_crawl_learning as base

source = base.source
fetch_network = base.fetch_network
evidence_dir = base.evidence_dir
learning_io = base.learning_io
model = base.model


def test_start_refreshes_profile_at_authority_lock_not_from_identity_map(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io):
    from app.models import CrawlSourceProfile
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    changed = []
    def changed_after_read(session, instance):
        # External storage fault: a cached read no longer agrees with the DB.
        # No application helper or engine is replaced.
        if isinstance(instance, CrawlSourceProfile) and not changed:
            changed.append(True)
            session.execute(text('UPDATE crawl_source_profile SET policy_generation=policy_generation+1 WHERE id=:id'),
                            {'id': instance.id})
    event.listen(Session, 'loaded_as_persistent', changed_after_read)
    try:
        response = client.post(action, data=fields)
    finally:
        event.remove(Session, 'loaded_as_persistent', changed_after_read)
    assert changed
    assert response.status_code == 409
    assert not learning_io


def test_repriced_route_is_rejected_before_provider_call(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch):
    _, (action, fields) = base.prepared(client, source, csrf_token, fetch_network)
    started = client.post(action, data=fields)
    original_get = model.cache.get
    changed = []
    def cache_lookup(key):
        # Routing has read its snapshot; external Redis I/O allows an Admin
        # price change before the final DB admission checkpoint.
        if not changed:
            changed.append(True)
            with db.engine.begin() as conn:
                conn.execute(text('UPDATE llm_config SET cost_per_1k_input=1, cost_per_1k_output=1'))
        return original_get(key)
    monkeypatch.setattr(model.cache, 'get', cache_lookup)
    base.deliver(learning_io)
    assert changed
    assert not model.provider.calls
    assert base.state(client, started.location) == 'blocked'
