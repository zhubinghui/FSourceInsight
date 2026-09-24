"""Independent checks through Admin actions, never model-selected samples."""
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from bs4 import BeautifulSoup

from tests.test_web import test_crawl_learning as learning
from tests.test_web import test_crawl_preview as preview

source = learning.source
fetch_network = learning.fetch_network
evidence_dir = learning.evidence_dir
learning_io = learning.learning_io
model = learning.model


def recipe_for(source):
    doc = preview.recipe_for(source)
    doc.pop('feed')
    doc.update(extractor='html', list_pages=[{'url': 'https://news.test.invalid/news',
        'item_selector': 'article', 'fields': {'title': {'selector': 'a', 'read': 'text'},
        'url': {'selector': 'a', 'read': 'attr', 'attr': 'href'}}}], detail_templates=[{
        'match': {'host': 'news.test.invalid', 'path_prefix': '/articles/'},
        'fields': {'title': {'selector': 'h1', 'read': 'text'},
                   'content': {'selector': '.body', 'read': 'paragraphs'}}}])
    return doc


def routes(label, count=3):
    pages, cards = {}, []
    for index in range(count):
        title = f'Grenoble sensor {label} {index}'
        url = f'https://news.test.invalid/articles/{label}-{index}'
        cards.append(f'<article class="{"first-card" if index == 0 else "other-card"}"><a href="{url}">{title}</a></article>')
        body = (f'<p>The Grenoble sensor {label} {index} project studies precision measurement in local laboratories. '
                'Its researchers published detailed methods and reproducible experimental observations for technical review.</p>'
                f'<p>For the {label} {index} prototype the team reports improved energy efficiency and carefully describes '
                'the equipment, funding and remaining limitations before future industrial applications can be assessed.</p>')
        pages[url] = {'body': f'<h1>{title}</h1><div class="body {"training-only" if label == "training" else ""}">{body}</div>'}
    pages['https://news.test.invalid/news'] = {'body': ''.join(cards)}
    return pages


def capture(client, version, fetch_network, label, *, count=3, supplied=None, retain=True):
    fetch_network.configure(routes=supplied or routes(label, count))
    action, fields = preview.preview_form(client, version)
    if retain:
        fields['retain_evidence'] = '1'
    response = client.post(action, data=fields)
    assert response.status_code == 302
    return response.location


def learned(client, source, csrf_token, fetch_network, learning_io, model, proposed=None, initial=None, grant=True):
    if grant:
        learning.policy.save_policy(client, source)
    recipe = initial or recipe_for(source)
    version = preview.save_candidate(client, source, csrf_token, recipe)
    report = capture(client, version, fetch_network, 'training', count=1)
    action, fields = learning.form_at(client, report, 'form[data-learning-start]')
    started = client.post(action, data=fields)
    assert started.status_code == 302
    model.provider.reply = proposed or deepcopy(recipe)
    learning.deliver(learning_io)
    assert learning.state(client, started.location) == 'awaiting_validation'
    return SimpleNamespace(location=started.location, base=version, recipe=recipe)


def test_system_validates_a_frozen_candidate_on_new_list_and_three_details_without_publishing(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    item = learned(client, source, csrf_token, fetch_network, learning_io, model)
    capture(client, item.base, fetch_network, 'holdout')
    action, fields = learning.form_at(client, item.location, 'form[data-validation-start]')
    requests, dispatches = len(fetch_network.events()), len(learning_io)
    checked = client.post(action, data=fields)
    assert checked.status_code == 302
    response = client.get(checked.location)
    page = BeautifulSoup(response.text, 'html.parser')
    assert page.select_one('[data-validation-status]').get_text(strip=True) == 'passed'
    result = json.loads(page.select_one('[data-validation-result]').get_text())
    assert result['lists'] == 1 and result['details'] == 3
    assert result['templates'] == [0]
    assert 'controlled learning workflow only' in page.get_text()
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'unpublished' in page.get_text()
    assert 'precision measurement' not in response.text
    assert 'https://news.test.invalid/articles/holdout' not in response.text
    assert len(model.provider.calls) == 1
    assert len(fetch_network.events()) == requests and len(learning_io) == dispatches
    assert client.get('/api/v1/news').json['total'] == 0
    assert 'Candidate' in client.get(page.select_one('a[data-learning-candidate]')['href']).text


@pytest.mark.parametrize('reuse', ['raw', 'rewrapped_text', 'detail_url'])
def test_seen_training_material_cannot_become_a_holdout(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, reuse):
    item = learned(client, source, csrf_token, fetch_network, learning_io, model)
    pages = routes('holdout')
    target = 'https://news.test.invalid/articles/holdout-0'
    original = 'https://news.test.invalid/articles/training-0'
    if reuse == 'raw':
        pages[target] = routes('training', 1)[original]
    elif reuse == 'rewrapped_text':
        pages[target]['body'] = '<main>' + routes('training', 1)[original]['body'].replace('training-only', 'different-wrapper') + '</main><footer>Changed footer</footer>'
    else:
        pages[original] = pages.pop(target)
        pages['https://news.test.invalid/news']['body'] = pages['https://news.test.invalid/news']['body'].replace(target, original)
    capture(client, item.base, fetch_network, 'holdout', supplied=pages)
    action, fields = learning.form_at(client, item.location, 'form[data-validation-start]')
    assert client.post(action, data=fields).status_code == 302
    page = BeautifulSoup(client.get(item.location).text, 'html.parser')
    assert page.select_one('[data-validation-status]').get_text(strip=True) == 'inconclusive'
    assert json.loads(page.select_one('[data-validation-result]').get_text())['reason'] == 'previously_seen_evidence'
    assert len(model.provider.calls) == 1


def check(client, item):
    action, fields = learning.form_at(client, item.location, 'form[data-validation-start]')
    response = client.post(action, data=fields)
    assert response.status_code == 302
    return BeautifulSoup(client.get(item.location).text, 'html.parser'), action, fields


@pytest.mark.parametrize('bad_recipe', ['overfit', 'drops_cards', 'uncovered_template'])
def test_training_success_does_not_replace_independent_quality_and_coverage(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, bad_recipe):
    proposed = recipe_for(source)
    if bad_recipe == 'overfit':
        proposed['detail_templates'][0]['fields']['content']['selector'] = '.training-only'
    elif bad_recipe == 'drops_cards':
        proposed['list_pages'][0]['item_selector'] = 'article.first-card'
    else:
        other = deepcopy(proposed['detail_templates'][0])
        other['match']['path_prefix'] = '/other-template/'
        proposed['detail_templates'].append(other)
    item = learned(client, source, csrf_token, fetch_network, learning_io, model, proposed)
    capture(client, item.base, fetch_network, 'holdout')
    page, _, _ = check(client, item)
    assert page.select_one('[data-validation-status]').get_text(strip=True) == ('inconclusive' if bad_recipe == 'uncovered_template' else 'failed')
    assert 'Not independently validated' in page.get_text()
    assert client.get('/api/v1/news').json['total'] == 0


@pytest.mark.parametrize('bad_first', ['only_two', 'not_retained', 'missing_file'])
def test_first_capture_is_pinned_and_cannot_be_replaced_by_a_later_good_result(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, bad_first):
    item = learned(client, source, csrf_token, fetch_network, learning_io, model)
    capture(client, item.base, fetch_network, 'first', count=2 if bad_first == 'only_two' else 3,
            retain=bad_first != 'not_retained')
    if bad_first == 'missing_file':
        files = list(evidence_dir.glob('*.json'))
        assert files
        for file in files:
            file.unlink()
    capture(client, item.base, fetch_network, 'later-good')
    page, action, fields = check(client, item)
    assert page.select_one('[data-validation-status]').get_text(strip=True) == 'inconclusive'
    original = page.select_one('[data-validation-result]').get_text()
    capture(client, item.base, fetch_network, 'another-good')
    assert client.post(action, data=fields).status_code == 302
    page = BeautifulSoup(client.get(item.location).text, 'html.parser')
    assert page.select_one('[data-validation-result]').get_text() == original
    assert len(model.provider.calls) == 1


def test_old_previews_and_user_selected_sample_ids_cannot_supply_the_holdout(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    item = learned(client, source, csrf_token, fetch_network, learning_io, model)
    action, fields = learning.form_at(client, item.location, 'form[data-validation-start]')
    assert client.post(action, data=fields).status_code == 409
    for name in ('capture_id', 'recipe', 'quality', 'status', 'candidate_id'):
        assert client.post(action, data={**fields, name: '1'}).status_code == 400
    capture(client, item.base, fetch_network, 'holdout')
    assert client.post(action, data=fields).status_code == 302
    assert BeautifulSoup(client.get(item.location).text, 'html.parser').select_one('[data-validation-status]').get_text(strip=True) == 'passed'


def test_a_previous_validation_holdout_cannot_be_reused_for_a_later_candidate(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    first = learned(client, source, csrf_token, fetch_network, learning_io, model)
    capture(client, first.base, fetch_network, 'holdout')
    assert check(client, first)[0].select_one('[data-validation-status]').get_text(strip=True) == 'passed'
    second = learned(client, source, csrf_token, fetch_network, learning_io, model, grant=False)
    capture(client, second.base, fetch_network, 'holdout')
    page, _, _ = check(client, second)
    assert page.select_one('[data-validation-status]').get_text(strip=True) == 'inconclusive'
    assert json.loads(page.select_one('[data-validation-result]').get_text())['reason'] == 'previously_seen_evidence'
    original = BeautifulSoup(client.get(first.location).text, 'html.parser')
    assert original.select_one('[data-validation-status]').get_text(strip=True) == 'passed'


def test_a_pass_becomes_stale_when_the_holdout_is_later_exposed_to_learning(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    item = learned(client, source, csrf_token, fetch_network, learning_io, model)
    holdout = capture(client, item.base, fetch_network, 'holdout')
    assert check(client, item)[0].select_one('[data-validation-status]').get_text(strip=True) == 'passed'
    action, fields = learning.form_at(client, holdout, 'form[data-learning-start]')
    started = client.post(action, data=fields)
    assert started.status_code == 302
    model.provider.reply = item.recipe
    learning.deliver(learning_io)
    page = BeautifulSoup(client.get(item.location).text, 'html.parser')
    assert page.select_one('[data-validation-status]').get_text(strip=True) == 'stale'
    assert 'recorded state: passed' in page.get_text()
    assert 'Not independently validated' in page.get_text()


def test_a_repaired_detail_rule_can_pass_without_treating_the_broken_base_as_body_truth(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    initial = recipe_for(source)
    initial['detail_templates'][0]['fields']['content']['selector'] = '.obsolete'
    item = learned(client, source, csrf_token, fetch_network, learning_io, model,
                   proposed=recipe_for(source), initial=initial)
    report = capture(client, item.base, fetch_network, 'independent')
    assert BeautifulSoup(client.get(report).text, 'html.parser').select_one('[data-preview-status]').get_text(strip=True) == 'partial'
    page, _, _ = check(client, item)
    assert page.select_one('[data-validation-status]').get_text(strip=True) == 'passed'


@pytest.mark.parametrize('extra', ['pagination', 'another_list'])
def test_unexercised_candidate_list_branches_are_not_certified_by_single_list_evidence(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, extra):
    proposed = recipe_for(source)
    if extra == 'pagination':
        proposed['list_pages'][0]['pagination'] = {'kind': 'next_link', 'selector': 'a.next', 'max_pages': 2}
    else:
        proposed['list_pages'].append(deepcopy(proposed['list_pages'][0]))
    item = learned(client, source, csrf_token, fetch_network, learning_io, model, proposed)
    capture(client, item.base, fetch_network, 'holdout')
    page, _, _ = check(client, item)
    assert page.select_one('[data-validation-status]').get_text(strip=True) == 'inconclusive'
    assert json.loads(page.select_one('[data-validation-result]').get_text())['reason'] == 'insufficient_list_coverage'
