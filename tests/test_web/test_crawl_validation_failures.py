"""Authority, report durability and fault checkpoints through Admin HTTP."""
import json
import subprocess
import time
import pytest
from bs4 import BeautifulSoup
from sqlalchemy import text
from tests.test_web import test_crawl_validation as base

source = base.source
fetch_network = base.fetch_network
evidence_dir = base.evidence_dir
learning_io = base.learning_io
model = base.model


@pytest.mark.parametrize('change', ['revoke', 'source_aba', 'missing_evidence', 'expired', 'history_gap', 'capture_gap', 'binding', 'result', 'selection_counter', 'actor', 'deadline'])
def test_a_historical_pass_is_not_current_authority_after_evidence_or_binding_loss(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch, change):
    item = base.learned(client, source, csrf_token, fetch_network, learning_io, model)
    base.capture(client, item.base, fetch_network, 'holdout')
    assert base.check(client, item)[0].select_one('[data-validation-status]').get_text(strip=True) == 'passed'
    if change == 'revoke':
        action, fields = base.learning.policy.revoke_form(client, source)
        assert client.post(action, data=fields).status_code == 302
    elif change == 'source_aba':
        for _ in range(2):
            assert client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()}).status_code == 302
    elif change == 'missing_evidence':
        files = list(evidence_dir.glob('*.json'))
        assert files
        for file in files:
            file.unlink()
    elif change == 'expired':
        now = time.time()
        monkeypatch.setattr(time, 'time', lambda: now + 86401)
    else:
        statements = {'history_gap': 'DELETE FROM crawl_repair_attempt',
            'capture_gap': 'DELETE FROM crawl_capture_manifest',
            'binding': "UPDATE crawl_validation_report SET binding_hash='broken'",
            'result': 'UPDATE crawl_validation_report SET result=:result',
            'selection_counter': 'UPDATE crawl_learning_history SET selection_generation=0',
            'actor': 'UPDATE crawl_validation_report SET requested_by_id=NULL',
            'deadline': "UPDATE crawl_validation_report SET deadline_at='2099-01-01 00:00:00'"}
        with db.engine.begin() as conn:
            conn.execute(text(statements[change]), {'result': json.dumps({'secret': 'PRIVATE_REPORT_PAYLOAD<script>bad</script>'})})
    response = client.get(item.location)
    assert response.status_code == 200
    page = BeautifulSoup(response.text, 'html.parser')
    assert page.select_one('[data-validation-status]').get_text(strip=True) == 'stale'
    assert not page.select('[data-validation-result]')
    assert 'PRIVATE_REPORT_PAYLOAD' not in response.text
    assert response.headers['Cache-Control'] == 'no-store'
    assert len(model.provider.calls) == 1


@pytest.mark.parametrize('change', ['revoke', 'history', 'duplicate'])
def test_authority_is_rechecked_after_offline_parsing_and_duplicate_posts_do_not_reexecute(
        app, db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch, change):
    item = base.learned(client, source, csrf_token, fetch_network, learning_io, model)
    base.capture(client, item.base, fetch_network, 'holdout')
    action, fields = base.learning.form_at(client, item.location, 'form[data-validation-start]')
    original, changed = subprocess.Popen, []
    def spawn(*args, **kwargs):
        if not changed:
            changed.append(True)
            with app.app_context():
                if change == 'revoke':
                    revoke, form = base.learning.policy.revoke_form(client, source)
                    assert client.post(revoke, data=form).status_code == 302
                elif change == 'history':
                    with db.engine.begin() as conn:
                        conn.execute(text('UPDATE crawl_learning_history SET history_complete=0'))
                else:
                    assert client.post(action, data=fields).status_code == 302
        return original(*args, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    assert client.post(action, data=fields).status_code == 302
    page = BeautifulSoup(client.get(item.location).text, 'html.parser')
    assert changed
    assert page.select_one('[data-validation-status]').get_text(strip=True) == ('passed' if change == 'duplicate' else 'stale')
    assert 'recorded state: inconclusive' in page.get_text() if change != 'duplicate' else 'recorded state: passed' in page.get_text()
    assert len(model.provider.calls) == 1


def test_process_exit_leaves_pinned_intent_and_expiry_never_retries_or_reselects(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch):
    item = base.learned(client, source, csrf_token, fetch_network, learning_io, model)
    base.capture(client, item.base, fetch_network, 'holdout')
    action, fields = base.learning.form_at(client, item.location, 'form[data-validation-start]')
    with monkeypatch.context() as patch:
        def crash(*args, **kwargs):
            raise SystemExit('synthetic validation process exit')
        patch.setattr(subprocess, 'Popen', crash)
        with pytest.raises(SystemExit):
            client.post(action, data=fields)
    assert BeautifulSoup(client.get(item.location).text, 'html.parser').select_one('[data-validation-status]').get_text(strip=True) == 'running'
    now = time.time()
    monkeypatch.setattr(time, 'time', lambda: now + 31)
    from app.crawlers.learning_tasks import recover
    recover.run()
    page = BeautifulSoup(client.get(item.location).text, 'html.parser')
    assert page.select_one('[data-validation-status]').get_text(strip=True) == 'inconclusive'
    assert json.loads(page.select_one('[data-validation-result]').get_text())['reason'] == 'execution_expired'
    assert client.post(action, data=fields).status_code == 302
    assert len(model.provider.calls) == 1


@pytest.mark.parametrize('actor', ['anonymous', 'member', 'bad_csrf', 'wrong_source'])
def test_validation_requires_admin_csrf_and_source_ownership(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, actor):
    item = base.learned(client, source, csrf_token, fetch_network, learning_io, model)
    action, fields = base.learning.form_at(client, item.location, 'form[data-validation-start]')
    if actor == 'anonymous':
        client.get('/auth/logout')
        expected = (302, 403)
    elif actor == 'member':
        client.post('/auth/login', data={'email': 'owner@test.invalid', 'password': 'original-password', 'csrf_token': csrf_token()})
        expected = (302,)
    elif actor == 'bad_csrf':
        fields = {}
        expected = (400,)
    else:
        action = action.replace(f'/sources/{source}/', '/sources/999999/')
        expected = (404,)
    response = client.post(action, data=fields)
    assert response.status_code in expected
    if actor == 'member':
        assert response.location == '/'
    assert len(model.provider.calls) == 1


def test_lost_prior_validation_history_blocks_later_learning_before_payment(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    item = base.learned(client, source, csrf_token, fetch_network, learning_io, model)
    base.capture(client, item.base, fetch_network, 'holdout')
    base.check(client, item)
    report = base.capture(client, item.base, fetch_network, 'next-learning')
    action, fields = base.learning.form_at(client, report, 'form[data-learning-start]')
    with db.engine.begin() as conn:
        conn.execute(text('DELETE FROM crawl_validation_report'))
    assert client.post(action, data=fields).status_code == 409
    assert len(model.provider.calls) == 1


@pytest.mark.parametrize('phase', ['selection', 'result'])
def test_sql_failure_cannot_publish_partial_validation_or_leak_private_parameters(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, caplog, phase):
    item = base.learned(client, source, csrf_token, fetch_network, learning_io, model)
    base.capture(client, item.base, fetch_network, 'holdout')
    action, fields = base.learning.form_at(client, item.location, 'form[data-validation-start]')
    with db.engine.begin() as conn:
        state = 'running' if phase == 'selection' else 'passed'
        conn.exec_driver_sql(f"CREATE TRIGGER reject_validation BEFORE UPDATE ON crawl_validation_report WHEN NEW.state='{state}' BEGIN SELECT RAISE(FAIL, 'PRIVATE_VALIDATION_SQL'); END")
    response = client.post(action, data=fields)
    assert response.status_code == 503
    page = BeautifulSoup(client.get(item.location).text, 'html.parser')
    assert page.select_one('[data-validation-status]').get_text(strip=True) == ('awaiting_evidence' if phase == 'selection' else 'running')
    assert not page.select('[data-validation-result]')
    assert 'PRIVATE_VALIDATION_SQL' not in caplog.text + response.text + str(page)
    assert len(model.provider.calls) == 1


def test_editing_only_the_report_state_cannot_turn_failed_quality_into_a_pass(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    proposed = base.recipe_for(source)
    proposed['detail_templates'][0]['fields']['content']['selector'] = '.training-only'
    item = base.learned(client, source, csrf_token, fetch_network, learning_io, model, proposed)
    base.capture(client, item.base, fetch_network, 'holdout')
    assert base.check(client, item)[0].select_one('[data-validation-status]').get_text(strip=True) == 'failed'
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE crawl_validation_report SET state='passed'"))
    page = BeautifulSoup(client.get(item.location).text, 'html.parser')
    assert page.select_one('[data-validation-status]').get_text(strip=True) == 'stale'
    assert 'Not independently validated' in page.get_text()


def test_whole_second_database_precision_does_not_break_committed_input_or_selection_hashes(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch):
    # Model a DB that rounds DATETIME fractions, instead of SQLite's usual retention.
    # This is a boundary probe, not a claim that actual MySQL was exercised.
    timestamp = int(time.time()) + 0.9
    monkeypatch.setattr(time, 'time', lambda: timestamp)
    with db.engine.begin() as conn:
        conn.exec_driver_sql("""CREATE TRIGGER round_session_time AFTER INSERT ON crawl_repair_session
            BEGIN UPDATE crawl_repair_session SET created_at=datetime(NEW.created_at,'+0.5 seconds'),
                deadline_at=datetime(NEW.deadline_at,'+0.5 seconds') WHERE id=NEW.id; END""")
        conn.exec_driver_sql("""CREATE TRIGGER round_validation_time AFTER UPDATE ON crawl_validation_report
            WHEN NEW.state='running' AND OLD.state='awaiting_evidence'
            BEGIN UPDATE crawl_validation_report SET deadline_at=datetime(NEW.deadline_at,'+0.5 seconds')
                WHERE id=NEW.id; END""")
    item = base.learned(client, source, csrf_token, fetch_network, learning_io, model)
    base.capture(client, item.base, fetch_network, 'holdout')
    page, _, _ = base.check(client, item)
    assert page.select_one('[data-validation-status]').get_text(strip=True) == 'passed'
