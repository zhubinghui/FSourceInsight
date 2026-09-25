"""Roll back to the previous recipe or return to the legacy crawler (spec §4.3–4.4)."""
from bs4 import BeautifulSoup

from tests.test_web import test_crawl_activation as activation
from tests.test_web import test_crawl_preview as preview

source = preview.source
fetch_network = preview.fetch_network


def config(client, source_id):
    return BeautifulSoup(client.get(f'/admin/sources/{source_id}/crawl-config').text, 'html.parser')


def post(client, source_id, selector, **extra):
    page = config(client, source_id)
    form = page.select_one(selector)
    fields = {item['name']: item.get('value', '') for item in form.select('input[name]')}
    fields.update(extra)
    return client.post(form['action'], data=fields)


def second_version(client, source_id, csrf_token, fetch_network):
    recipe = preview.recipe_for(source_id)
    recipe['feed']['fields']['content'] = 'summary'
    version = preview.save_candidate(client, source_id, csrf_token, recipe)
    action, form = preview.preview_form(client, version)
    assert client.post(action, data=form).status_code == 302
    action, fields = activation.decision_form(client, version, 'form[data-approve]')
    assert client.post(action, data=fields).status_code == 302
    return version


def test_rollback_swaps_active_and_previous_and_retire_returns_to_legacy(client, source, csrf_token, fetch_network):
    first = activation.approved(client, source, csrf_token, fetch_network)
    second = second_version(client, source, csrf_token, fetch_network)
    assert post(client, source, 'form[data-rollback]').status_code == 302
    page = config(client, source)
    assert page.select_one('[data-active-version]').get_text(strip=True) == first.rsplit('/', 1)[1]
    assert page.select_one('[data-previous-version]').get_text(strip=True) == second.rsplit('/', 1)[1]
    assert page.select_one('[data-activation-generation]').get_text(strip=True) == '3'
    assert post(client, source, 'form[data-retire]').status_code == 302
    page = config(client, source)
    assert 'No active recipe' in page.get_text()
    assert [d.get_text().split('—')[1].split()[0] for d in page.select('[data-decision]')][:3] == ['retire', 'rollback', 'approve']


def test_rollback_is_refused_after_the_source_changed(client, source, csrf_token, fetch_network):
    activation.approved(client, source, csrf_token, fetch_network)
    second_version(client, source, csrf_token, fetch_network)
    preview.edit_source(client, source, csrf_token, url='https://news.test.invalid/moved')
    assert post(client, source, 'form[data-rollback]').status_code == 409


def test_rollback_without_previous_and_retire_without_active_are_refused(client, source, csrf_token, fetch_network):
    assert post(client, source, 'form[data-retire]').status_code in (404, 409)
    activation.approved(client, source, csrf_token, fetch_network)
    assert post(client, source, 'form[data-rollback]').status_code == 409


def test_retire_is_allowed_for_a_disabled_source(client, source, csrf_token, fetch_network):
    activation.approved(client, source, csrf_token, fetch_network)
    assert client.post(f'/admin/sources/{source}/toggle', data={'csrf_token': csrf_token()}).status_code == 302
    assert post(client, source, 'form[data-retire]').status_code == 302
