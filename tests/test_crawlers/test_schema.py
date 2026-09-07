"""Public recipe import contract; synthetic input, no fetching or execution."""
import json

import pytest


@pytest.fixture
def html_recipe():
    return {
        'format_version': 1, 'output_contract': 'article.v1', 'target_kind': 'news',
        'source_id': 42, 'locale': 'fr', 'transport': 'http',
        'list_pages': [{
            'url': 'https://news.example.invalid/actualites/',
            'item_selector': 'article.news-card',
            'fields': {
                'title': {'selector': 'h2 a', 'read': 'text'},
                'url': {'selector': 'h2 a', 'read': 'attr', 'attr': 'href'},
                'published_at': {'selector': 'time', 'read': 'attr', 'attr': 'datetime'},
            },
            'pagination': {'kind': 'next_link', 'selector': 'a[rel=next]', 'max_pages': 2},
        }],
        'detail_templates': [{
            'match': {'host': 'news.example.invalid', 'path_prefix': '/actualite/'},
            'fields': {
                'title': {'selector': 'h1', 'read': 'text'},
                'content': {'selector': 'article .article-body', 'read': 'paragraphs'},
            },
            'remove_selectors': ['.share', '.related', '.advertisement'],
        }],
        'date_policy': {'source_timezone': 'Europe/Paris'},
        'identity_policy': 'legacy-compatible-url-v1',
    }


def test_html_recipe_roundtrips_and_has_order_independent_identity(html_recipe):
    from app.crawlers.schema import validate_recipe

    recipe = validate_recipe(html_recipe)
    assert recipe.to_dict() == html_recipe
    reordered = dict(reversed(list(html_recipe.items())))
    assert validate_recipe(json.dumps(reordered)).fingerprint == recipe.fingerprint
    html_recipe['list_pages'][0]['fields']['title']['selector'] = 'h3'
    assert validate_recipe(html_recipe).fingerprint != recipe.fingerprint
    exported = recipe.to_dict()
    exported['list_pages'].clear()
    assert recipe.to_dict()['list_pages'][0]['fields']['title']['selector'] == 'h2 a'


@pytest.mark.parametrize('location, key', [
    ('root', 'active'), ('root', 'allowed_domains'), ('root', 'budget'),
    ('root', 'quality_threshold'), ('root', 'headers'), ('root', 'crawler_class'),
    ('list', 'script'), ('field', 'transform'), ('field', 'regex'),
    ('detail', 'evaluate'), ('match', 'allow_subdomains'),
    ('pagination', 'click'), ('date', 'fallback_to_now'),
])
def test_candidate_cannot_inject_operations_or_policy(html_recipe, location, key):
    from app.crawlers.schema import validate_recipe

    targets = {
        'root': html_recipe, 'list': html_recipe['list_pages'][0],
        'field': html_recipe['list_pages'][0]['fields']['title'],
        'detail': html_recipe['detail_templates'][0],
        'match': html_recipe['detail_templates'][0]['match'],
        'pagination': html_recipe['list_pages'][0]['pagination'],
        'date': html_recipe['date_policy'],
    }
    targets[location][key] = 'do-not-echo-untrusted-payload'
    with pytest.raises(ValueError) as error:
        validate_recipe(html_recipe)
    assert error.value.code == 'invalid_fields'
    assert 'do-not-echo' not in str(error.value)


@pytest.mark.parametrize('path, value', [
    (('format_version',), True), (('format_version',), 2),
    (('source_id',), True), (('source_id',), '42'), (('source_id',), 0),
    (('target_kind',), 'company'), (('output_contract',), 'article.v0'),
    (('transport',), 'browser'), (('identity_policy',), 'replace-legacy'),
    (('locale',), ''), (('locale',), ['fr']),
    (('date_policy', 'source_timezone'), 'Not/AZone'),
    (('list_pages',), {}), (('list_pages',), []),
    (('list_pages', 0, 'url'), 'file:///etc/passwd'),
    (('list_pages', 0, 'url'), 'https://user:secret@example.invalid/'),
    (('list_pages', 0, 'url'), 'https://example.invalid:bad/'),
    (('list_pages', 0, 'url'), 'https://example.invalid/\nfoo'),
    (('list_pages', 0, 'fields', 'title', 'read'), 'eval'),
    (('list_pages', 0, 'fields', 'url', 'attr'), 'onclick'),
    (('list_pages', 0, 'pagination', 'kind'), 'execute'),
    (('list_pages', 0, 'pagination', 'max_pages'), True),
    (('list_pages', 0, 'pagination', 'max_pages'), 100000),
    (('detail_templates', 0, 'match', 'host'), '*.example.invalid'),
    (('detail_templates', 0, 'match', 'path_prefix'), '//other.invalid'),
])
def test_recipe_values_use_strict_supported_types_and_operations(html_recipe, path, value):
    from app.crawlers.schema import InvalidRecipe, validate_recipe

    target = html_recipe
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(InvalidRecipe):
        validate_recipe(html_recipe)


@pytest.mark.parametrize('selector', [
    '', 'article[', 'a' * 257, ':has(:has(a))', 'a, body', r'a\:hover',
    'a:hover', 'a + a', 'a ~ a', ' '.join(['div'] * 10),
])
def test_only_bounded_simple_css_is_accepted(html_recipe, selector):
    from app.crawlers.schema import InvalidRecipe, validate_recipe

    html_recipe['list_pages'][0]['fields']['title']['selector'] = selector
    with pytest.raises(InvalidRecipe):
        validate_recipe(html_recipe)


def test_attribute_values_are_data_not_pseudo_classes(html_recipe):
    from app.crawlers.schema import validate_recipe

    html_recipe['detail_templates'][0]['fields']['title'] = {
        'selector': 'meta[property="og:title"]', 'read': 'attr', 'attr': 'content',
    }
    assert validate_recipe(html_recipe).to_dict() == html_recipe


@pytest.mark.parametrize('payload', [
    '{', '{"format_version":1,"format_version":1}', '[1]', 'null',
    '{"source_id":NaN}', '{"source_id":Infinity}', '{"source_id":' + '1' * 5000 + '}',
    ' ' * 65537 + '{}', '[' * 20 + '0' + ']' * 20,
    {'x': '\ud800'}, {1: 'not-a-json-key'}, {'x': float('nan')},
])
def test_json_input_is_bounded_and_unambiguous(payload):
    from app.crawlers.schema import InvalidRecipe, validate_recipe

    with pytest.raises(InvalidRecipe):
        validate_recipe(payload)


def test_rss_can_map_guid_and_excerpt_without_claiming_fulltext(html_recipe):
    from app.crawlers.schema import InvalidRecipe, validate_recipe

    del html_recipe['list_pages']
    html_recipe.update(extractor='rss', feed={
        'url': 'https://news.example.invalid/feed',
        'fields': {'title': 'title', 'url': 'link', 'external_id': 'id', 'content': 'summary'},
    })
    assert validate_recipe(html_recipe).to_dict() == html_recipe
    html_recipe['feed']['content_level'] = 'full'
    with pytest.raises(InvalidRecipe):
        validate_recipe(html_recipe)
    del html_recipe['feed']['content_level']
    html_recipe['feed']['fields']['external_id'] = '__import__("os")'
    with pytest.raises(InvalidRecipe):
        validate_recipe(html_recipe)


def test_jsonld_is_a_typed_field_reader_not_executable_jsonpath(html_recipe):
    from app.crawlers.schema import InvalidRecipe, validate_recipe

    template = html_recipe['detail_templates'][0]
    template['jsonld_types'] = ['NewsArticle']
    template['fields']['title'] = {'read': 'jsonld', 'path': ['headline']}
    template['fields']['content'] = {'read': 'jsonld', 'path': ['articleBody']}
    assert validate_recipe(html_recipe).to_dict() == html_recipe
    template['fields']['title']['path'] = ['$..*[?(@.exec())]']
    with pytest.raises(InvalidRecipe):
        validate_recipe(html_recipe)
    template['fields']['title']['path'] = ['headline']
    template['jsonld_types'] = ['Organization']
    with pytest.raises(InvalidRecipe):
        validate_recipe(html_recipe)
    del template['jsonld_types']
    with pytest.raises(InvalidRecipe):
        validate_recipe(html_recipe)


def test_detail_template_must_extract_at_least_one_field(html_recipe):
    from app.crawlers.schema import InvalidRecipe, validate_recipe

    html_recipe['detail_templates'][0]['fields'] = {}
    with pytest.raises(InvalidRecipe):
        validate_recipe(html_recipe)


def test_many_small_values_exhaust_the_json_budget_before_structure_validation():
    from app.crawlers.schema import InvalidRecipe, validate_recipe

    with pytest.raises(InvalidRecipe, match='limit_exceeded'):
        validate_recipe({'key' + str(i): 'é' * 500 for i in range(100)})


def test_dict_budget_does_not_build_an_oversized_intermediate_json():
    import tracemalloc
    from app.crawlers.schema import InvalidRecipe, validate_recipe

    payload = {'key' + str(i): 'a' * 8192 for i in range(300)}
    tracemalloc.start()
    try:
        with pytest.raises(InvalidRecipe, match='limit_exceeded'):
            validate_recipe(payload)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1024 * 1024


def test_duplicate_keys_in_an_otherwise_valid_recipe_are_rejected(html_recipe):
    from app.crawlers.schema import InvalidRecipe, validate_recipe

    payload = json.dumps(html_recipe).replace('"source_id": 42', '"source_id": 1, "source_id": 42')
    with pytest.raises(InvalidRecipe, match='duplicate_key'):
        validate_recipe(payload)


@pytest.mark.parametrize('kind', ['fields', 'selectors', 'nodes', 'cycle', 'bytes'])
def test_aggregate_limits_cannot_be_evaded_by_small_individual_rules(html_recipe, kind):
    from copy import deepcopy
    from app.crawlers.schema import InvalidRecipe, validate_recipe

    if kind == 'fields':
        fields = {name: {'selector': 'a', 'read': 'text'} for name in
                  ('title', 'url', 'content', 'external_id', 'published_at', 'author', 'image_url')}
        html_recipe['list_pages'][0]['fields'] = fields
        html_recipe['list_pages'] *= 4
        html_recipe['detail_templates'][0]['fields'] = fields
        html_recipe['detail_templates'][0]['remove_selectors'] = []
        html_recipe['detail_templates'] *= 8
    elif kind == 'selectors':
        html_recipe['detail_templates'][0]['remove_selectors'] = ['.share'] * 16
        html_recipe['detail_templates'] *= 8
    elif kind == 'nodes':
        html_recipe['list_pages'] = [deepcopy(html_recipe['list_pages'][0])] * 2050
    elif kind == 'cycle':
        html_recipe['list_pages'].append(html_recipe)
    else:
        html_recipe['list_pages'][0]['item_selector'] = 'é' * 40000
    with pytest.raises(InvalidRecipe, match='limit_exceeded'):
        validate_recipe(html_recipe)
