"""Learning prompts provably fit the reviewed input ceiling before any payment (real Admin flow)."""
from bs4 import BeautifulSoup

from tests.test_web import test_crawl_learning as learning
from tests.test_web import test_crawl_preview as preview
from tests.test_web import test_crawl_validation as validation

source = learning.source
fetch_network = learning.fetch_network
evidence_dir = learning.evidence_dir
learning_io = learning.learning_io
model = learning.model


def bound(messages):
    """UTF-8 bytes bound tokens for byte-level BPE; per-message and fixed chat overhead."""
    return sum(len(m['content'].encode()) + len(m['role'].encode()) + 8 for m in messages) + 64


def start(client, source_id, csrf_token, fetch_network, learning_io):
    learning.policy.save_policy(client, source_id)
    version = preview.save_candidate(client, source_id, csrf_token, validation.recipe_for(source_id))
    report = validation.capture(client, version, fetch_network, 'training', count=3)
    action, fields = learning.form_at(client, report, 'form[data-learning-start]')
    started = client.post(action, data=fields)
    assert started.status_code == 302
    learning.deliver(learning_io)
    return started.location


def test_samples_are_cropped_so_the_prompt_fits_the_smallest_reviewed_ceiling(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    model.config.billing_input_limit = 2500
    db.session.commit()
    model.provider.reply = validation.recipe_for(source)
    start(client, source, csrf_token, fetch_network, learning_io)
    assert len(model.provider.calls) == 1
    messages = model.provider.calls[0]['messages']
    assert bound(messages) <= 2500
    assert '"samples": [{' in messages[1]['content'], 'Cropping keeps at least one document excerpt'


def test_a_ceiling_too_small_for_the_instructions_blocks_without_payment(
        db, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    model.config.billing_input_limit = 300
    db.session.commit()
    location = start(client, source, csrf_token, fetch_network, learning_io)
    assert not model.provider.calls
    page = BeautifulSoup(client.get(location).text, 'html.parser')
    assert page.select_one('[data-learning-state]').get_text(strip=True) == 'blocked'
    assert 'input ceiling' in page.get_text()


def test_a_provider_not_declared_byte_bounded_never_receives_learning_inputs(
        app, client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    app.config['CRAWL_LEARNING_BYTE_BOUND_PROVIDERS'] = 'openai'
    location = start(client, source, csrf_token, fetch_network, learning_io)
    assert not model.provider.calls
    assert learning.state(client, location) == 'blocked'
