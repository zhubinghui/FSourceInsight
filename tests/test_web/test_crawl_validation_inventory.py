"""General holdout inventories (pagination, several lists, RSS) through real Admin actions."""
from copy import deepcopy
import json
from types import SimpleNamespace


from tests.test_web import test_crawl_config as config
from tests.test_web import test_crawl_learning as learning
from tests.test_web import test_crawl_preview as preview
from tests.test_web import test_crawl_validation as validation

source = learning.source
fetch_network = learning.fetch_network
evidence_dir = learning.evidence_dir
learning_io = learning.learning_io
model = learning.model

NEWS = 'https://news.test.invalid/news'
PAGE_TWO = 'https://news.test.invalid/news?page=2'
EVENTS = 'https://news.test.invalid/events'
FEED = 'https://news.test.invalid/feed'


def details(label, indices):
    pages = validation.routes(label, max(indices) + 1)
    return {url: page for url, page in pages.items() if url != NEWS and int(url.rsplit('-', 1)[1]) in indices}


def cards(label, indices, next_url=None):
    body = ''.join(f'<article><a href="https://news.test.invalid/articles/{label}-{i}">Grenoble sensor {label} {i}</a></article>'
                   for i in indices)
    return {'body': body + (f'<a class="next" href="{next_url}">Next</a>' if next_url else '')}


def feed(label, indices, content=False):
    items = []
    for i in indices:
        title = f'Grenoble sensor {label} {i}'
        text = ''
        if content:
            paragraph = (f'The Grenoble sensor {label} {i} project studies precision measurement in local laboratories '
                         'and reports reproducible observations, funding and limitations for technical review. ')
            other = (f'For the {label} {i} prototype the team describes improved energy efficiency, the equipment '
                     'used and the remaining limitations before any industrial application can be assessed. ')
            text = f'<content:encoded><![CDATA[<p>{paragraph * 2}</p><p>{other * 2}</p>]]></content:encoded>'
        items.append(f'<item><guid isPermaLink="false">{label}-{i}</guid><title>{title}</title>'
                     f'<link>https://news.test.invalid/articles/{label}-{i}</link>{text}</item>')
    return {'body': '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>'
                    f'<title>News</title>{"".join(items)}</channel></rss>',
            'headers': {'Content-Type': 'application/rss+xml'}}


def paginated(source_id):
    recipe = validation.recipe_for(source_id)
    recipe['list_pages'][0]['pagination'] = {'kind': 'next_link', 'selector': 'a.next', 'max_pages': 2}
    return recipe


def two_lists(source_id):
    recipe = validation.recipe_for(source_id)
    events = deepcopy(recipe['list_pages'][0])
    events['url'] = EVENTS
    recipe['list_pages'].append(events)
    return recipe


def rss(source_id, content=False):
    recipe = config.recipe_for(source_id)
    if content:
        recipe['feed']['fields']['content'] = 'content'
    else:
        recipe['detail_templates'] = deepcopy(validation.recipe_for(source_id)['detail_templates'])
    return recipe


def learned(client, source_id, csrf_token, fetch_network, learning_io, model, recipe, training):
    learning.policy.save_policy(client, source_id)
    version = preview.save_candidate(client, source_id, csrf_token, recipe)
    report = validation.capture(client, version, fetch_network, 'training', supplied=training)
    action, fields = learning.form_at(client, report, 'form[data-learning-start]')
    started = client.post(action, data=fields)
    assert started.status_code == 302
    model.provider.reply = deepcopy(recipe)
    learning.deliver(learning_io)
    assert learning.state(client, started.location) == 'awaiting_validation'
    return SimpleNamespace(location=started.location, base=version, recipe=recipe)


def outcome(client, item, fetch_network, holdout):
    validation.capture(client, item.base, fetch_network, 'holdout', supplied=holdout)
    page, _, _ = validation.check(client, item)
    return (page.select_one('[data-validation-status]').get_text(strip=True),
            json.loads(page.select_one('[data-validation-result]').get_text()))


def test_paginated_list_passes_although_page_two_url_was_seen_in_training(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    training = {NEWS: cards('training', [0], PAGE_TWO), PAGE_TWO: cards('training', [1]), **details('training', [0, 1])}
    item = learned(client, source, csrf_token, fetch_network, learning_io, model, paginated(source), training)
    holdout = {NEWS: cards('holdout', [0, 1], PAGE_TWO), PAGE_TWO: cards('holdout', [2]), **details('holdout', [0, 1, 2])}
    status, result = outcome(client, item, fetch_network, holdout)
    assert (status, result['reason']) == ('passed', 'controlled_holdout_checks_passed')
    assert result['lists'] == 2 and result['details'] == 3 and len(result['inventory']) == 2
    assert client.get('/api/v1/news').json['total'] == 0


def test_declared_pagination_must_be_exercised_by_the_holdout(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    training = {NEWS: cards('training', [0], PAGE_TWO), PAGE_TWO: cards('training', [1]), **details('training', [0, 1])}
    item = learned(client, source, csrf_token, fetch_network, learning_io, model, paginated(source), training)
    holdout = {NEWS: cards('holdout', [0, 1, 2]), **details('holdout', [0, 1, 2])}
    status, result = outcome(client, item, fetch_network, holdout)
    assert (status, result['reason']) == ('inconclusive', 'insufficient_list_coverage')


def test_each_of_several_lists_contributes_to_a_pass(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    training = {NEWS: cards('training', [0]), EVENTS: cards('training', [1]), **details('training', [0, 1])}
    item = learned(client, source, csrf_token, fetch_network, learning_io, model, two_lists(source), training)
    holdout = {NEWS: cards('holdout', [0, 1]), EVENTS: cards('holdout', [2]), **details('holdout', [0, 1, 2])}
    status, result = outcome(client, item, fetch_network, holdout)
    assert (status, result['lists'], result['details']) == ('passed', 2, 3)


def test_rss_inventory_with_detail_pages_passes(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    training = {FEED: feed('training', [0]), **details('training', [0])}
    item = learned(client, source, csrf_token, fetch_network, learning_io, model, rss(source), training)
    holdout = {FEED: feed('holdout', [0, 1, 2]), **details('holdout', [0, 1, 2])}
    status, result = outcome(client, item, fetch_network, holdout)
    assert (status, result['lists'], result['details'], result['templates']) == ('passed', 1, 3, [0])


def test_feed_supplied_bodies_are_not_certified_as_independent(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model):
    item = learned(client, source, csrf_token, fetch_network, learning_io, model, rss(source, content=True),
                   {FEED: feed('training', [0], content=True)})
    status, result = outcome(client, item, fetch_network, {FEED: feed('holdout', [0, 1, 2], content=True)})
    assert (status, result['reason']) == ('inconclusive', 'feed_content_not_independently_sampled')


def test_reports_frozen_under_v1_keep_the_single_list_rules(
        client, source, csrf_token, fetch_network, evidence_dir, learning_io, model, monkeypatch):
    from app.crawlers import validation as protocol
    training = {NEWS: cards('training', [0], PAGE_TWO), PAGE_TWO: cards('training', [1]), **details('training', [0, 1])}
    with monkeypatch.context() as legacy:
        legacy.setattr(protocol, 'VERSION', protocol.LEGACY)  # Simulates a record frozen by the previous release.
        item = learned(client, source, csrf_token, fetch_network, learning_io, model, paginated(source), training)
    holdout = {NEWS: cards('holdout', [0, 1], PAGE_TWO), PAGE_TWO: cards('holdout', [2]), **details('holdout', [0, 1, 2])}
    status, result = outcome(client, item, fetch_network, holdout)
    assert status == 'inconclusive' and 'inventory' not in result
