"""Public preview/run integration tests; only external network uses fixtures."""
import pytest

from app.crawlers.fetcher import FetchPolicy


def recipe(source_id=1):
    return {
        'format_version': 1, 'output_contract': 'article.v1', 'target_kind': 'news',
        'source_id': source_id, 'locale': 'fr', 'transport': 'http',
        'identity_policy': 'legacy-compatible-url-v1',
        'list_pages': [{'url': 'https://news.test.invalid/news', 'item_selector': 'article',
                        'fields': {'title': {'selector': 'h2 a', 'read': 'text'},
                                   'url': {'selector': 'h2 a', 'read': 'attr', 'attr': 'href'}}}],
    }


def engine(doc=None, **kwargs):
    from app.crawlers.engine import CrawlEngine
    doc = doc or recipe()
    return CrawlEngine(doc['source_id'], recipe=doc,
                       fetch_policy=FetchPolicy(allowed_hosts=('news.test.invalid',), min_interval=0), **kwargs)


def test_preview_extracts_a_news_card_without_a_database(fetch_network):
    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'body': '<article><h2><a href="/research">Recherche à Grenoble</a></h2></article>',
    }})
    result = engine().preview()
    assert result.status == 'ready' and not result.errors
    article, = result.articles
    assert article.title == 'Recherche à Grenoble'
    assert article.url == 'https://news.test.invalid/research'
    assert article.content_level == 'metadata_only' and article.published_at is None
    assert result.quality.valid == 1 and result.quality.new == 0
    assert {p.field for p in article.provenance} >= {'title', 'url'}
    assert all(p.snapshot_id for p in article.provenance)


def test_bad_card_does_not_hide_a_good_card_or_become_success(fetch_network):
    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'body': '<article><h2><a href="/good">Good research</a></h2></article><article><h2>Missing link</h2></article>'}})
    result = engine().preview()
    assert [a.title for a in result.articles] == ['Good research']
    assert result.quality.discovered == result.quality.extracted == 2
    assert result.quality.valid == result.quality.rejected == 1
    assert result.status == 'partial' and result.errors[0].code == 'missing_fields'


@pytest.mark.parametrize('target', ['http://127.0.0.1/news', 'https://other.test.invalid/news'])
def test_unauthorized_article_urls_are_not_accepted(fetch_network, target):
    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'body': f'<article><h2><a href="{target}">Research</a></h2></article>'}})
    result = engine().preview()
    assert not result.articles and result.errors[0].code == 'unsafe_url'


def test_empty_html_is_inconclusive_not_a_success(fetch_network):
    result = engine().preview()
    assert result.status == 'inconclusive' and result.quality.valid == 0


def test_forbidden_list_is_structured_and_does_not_extract(fetch_network):
    fetch_network.configure(routes={'https://news.test.invalid/news': {'status': 403}})
    result = engine().preview()
    assert result.status == 'blocked' and not result.articles
    assert result.errors[0].code == 'forbidden'


def test_live_result_can_be_replayed_without_another_network_request(fetch_network):
    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'body': '<article><h2><a href="/research">Research</a></h2></article>'}})
    first = engine().preview()
    count = len(fetch_network.processes)
    replay = engine(snapshots=first.snapshots).preview()
    assert replay == first
    assert len(fetch_network.processes) == count


def test_missing_replay_page_never_falls_back_to_network(fetch_network):
    result = engine(snapshots=()).preview()
    assert not result.articles and result.errors[0].code == 'no_evidence'
    assert not fetch_network.processes


def test_pagination_is_bounded_and_deduplicates_before_detail_work(fetch_network):
    doc = recipe()
    doc['list_pages'][0]['pagination'] = {'kind': 'next_link', 'selector': 'a.next', 'max_pages': 3}
    card = '<article><h2><a href="/research">Research</a></h2></article>'
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': card + '<a class="next" href="/page2">Next</a>'},
        'https://news.test.invalid/page2': {'body': card + '<a class="next" href="/news">Next</a>'},
    })
    result = engine(doc).preview()
    assert len(result.articles) == 1
    assert result.quality.discovered == 2 and result.quality.duplicate == 1
    assert len([e for e in fetch_network.events() if e['kind'] == 'http']) == 3
    assert any(e.code == 'redirect_limit' for e in result.errors)


def with_detail(doc=None):
    doc = doc or recipe()
    doc['detail_templates'] = [{'match': {'host': 'news.test.invalid', 'path_prefix': '/research'},
        'fields': {'title': {'selector': 'h1', 'read': 'text'},
                   'content': {'selector': '.body', 'read': 'paragraphs'},
                   'published_at': {'selector': 'time', 'read': 'attr', 'attr': 'datetime'}},
        'remove_selectors': ['.related']}]
    return doc


TEXT_A = 'Les chercheurs de Grenoble présentent un nouveau composant pour améliorer les capteurs industriels. Les essais sont publiés avec leurs résultats scientifiques.'
TEXT_B = 'Cette équipe du laboratoire travaille avec les entreprises locales sur la consommation électrique. Une seconde expérimentation doit confirmer la précision des mesures.'


def test_detail_reads_clean_paragraphs_and_an_explicit_utc_date(fetch_network):
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': f'<h1>Recherche Grenoble</h1><time datetime="2026-09-06T12:00:00+02:00"></time><div class="body"><p>{TEXT_A}</p><p>{TEXT_B}</p><script>steal()</script><p class="related">Publicité</p></div>'},
    })
    result = engine(with_detail()).preview()
    article, = result.articles
    assert article.content == TEXT_A + '\n\n' + TEXT_B
    assert article.content_level == 'full'
    assert article.published_at.isoformat() == '2026-09-06T10:00:00+00:00'
    assert article.published_at_source == 'detail'
    assert next(p for p in article.provenance if p.field == 'content').snapshot_id == result.observations[1].snapshot_id


def test_unrelated_detail_must_not_replace_the_list_article(fetch_network):
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': f'<h1>Recette chocolat vacances</h1><div class="body"><p>{TEXT_A}</p><p>{TEXT_B}</p></div>'},
    })
    result = engine(with_detail()).preview()
    assert result.articles[0].title == 'Recherche Grenoble'
    assert result.articles[0].content_level == 'metadata_only'
    assert result.status == 'degraded' and any(e.code == 'low_quality' for e in result.errors)


def test_list_attribute_title_and_relative_url_keep_external_identity(fetch_network):
    doc = recipe()
    doc['list_pages'][0]['fields']['title'] = {'selector': 'a', 'read': 'attr', 'attr': 'title'}
    doc['list_pages'][0]['fields']['external_id'] = {'selector': 'a', 'read': 'attr', 'attr': 'id'}
    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'body': '<article><h2><a href="/research" id="legacy-42" title="Science Grenoble">Link</a></h2></article>'}})
    article, = engine(doc).preview().articles
    assert article.title == 'Science Grenoble' and article.external_id == 'legacy-42'


def rss_recipe():
    doc = recipe()
    del doc['list_pages']
    doc['extractor'] = 'rss'
    doc['feed'] = {'url': 'https://news.test.invalid/feed', 'fields': {
        'title': 'title', 'url': 'link', 'external_id': 'id', 'content': 'summary', 'published_at': 'published'}}
    return doc


def test_rss_keeps_guid_and_does_not_call_a_long_summary_full_text(fetch_network):
    rss = f'<rss version="2.0"><channel><title>News</title><item><guid isPermaLink="false">old-guid-42</guid><title>Research</title><link>https://news.test.invalid/research</link><description><![CDATA[<p>{TEXT_A}</p><p>{TEXT_B}</p>]]></description><pubDate>Sun, 06 Sep 2026 12:00:00 +0200</pubDate></item></channel></rss>'
    fetch_network.configure(routes={'https://news.test.invalid/feed': {'body': rss, 'headers': {'Content-Type': 'application/rss+xml'}}})
    result = engine(rss_recipe()).preview()
    article, = result.articles
    assert article.external_id == 'old-guid-42' and article.content_level == 'excerpt'
    assert article.published_at.isoformat() == '2026-09-06T10:00:00+00:00'
    assert article.published_at_source == 'feed'
    assert all(p.method == 'feed' for p in article.provenance)


def test_a_valid_empty_feed_is_evidence_but_invalid_xml_is_not(fetch_network):
    fetch_network.configure(routes={'https://news.test.invalid/feed': {'body': '<rss version="2.0"><channel><title>Quiet source</title></channel></rss>', 'headers': {'Content-Type': 'application/rss+xml'}}})
    result = engine(rss_recipe()).preview()
    assert result.status == 'no_change' and result.quality.no_change_reason == 'confirmed_empty'
    assert result.quality.evidence_ids and not result.errors


def test_jsonld_reads_one_matching_article_not_an_unrelated_graph_node(fetch_network):
    import json
    doc = with_detail()
    template = doc['detail_templates'][0]
    template['jsonld_types'] = ['NewsArticle']
    template['fields'] = {'title': {'read': 'jsonld', 'path': ['headline']},
                          'content': {'read': 'jsonld', 'path': ['articleBody']}}
    data = {'@graph': [{'@type': 'NewsArticle', 'url': 'https://news.test.invalid/other', 'headline': 'Wrong', 'articleBody': 'Wrong'},
                      {'@type': 'NewsArticle', 'url': '/research', 'headline': 'Recherche Grenoble', 'articleBody': TEXT_A + '\n\n' + TEXT_B}]}
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': '<script type="application/ld+json">' + json.dumps(data) + '</script>'},
    })
    result = engine(doc).preview()
    assert result.articles[0].content == TEXT_A + '\n\n' + TEXT_B
    assert next(p for p in result.articles[0].provenance if p.field == 'content').method == 'jsonld'


def test_link_dense_recommendations_are_not_full_news_content(fetch_network):
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': f'<h1>Recherche Grenoble</h1><div class="body"><p><a href="/other">{TEXT_A}</a></p><p><a href="/other2">{TEXT_B}</a></p></div>'},
    })
    result = engine(with_detail()).preview()
    assert result.articles[0].content_level == 'metadata_only'
    assert result.status == 'degraded'


def test_profile_can_distinguish_a_valid_short_bulletin_from_a_full_news_profile(fetch_network):
    from app.crawlers.engine import QualityProfile
    body = '<h1>Recherche Grenoble</h1><div class="body"><p>' + TEXT_A + '</p></div>'
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': body},
    })
    normal = engine(with_detail()).preview()
    brief = engine(with_detail(), profile=QualityProfile(min_content_chars=80, min_paragraphs=1)).preview()
    assert normal.articles[0].content_level == 'excerpt'
    assert brief.articles[0].content_level == 'full'


def test_replay_rejects_changed_bytes_with_an_old_snapshot_identity(fetch_network):
    from dataclasses import replace
    first = engine().preview()
    snapshot = first.snapshots[0]
    corrupt = replace(snapshot, response=replace(snapshot.response, body=b'<article>changed</article>'))
    count = len(fetch_network.processes)
    result = engine(snapshots=(corrupt,)).preview()
    assert result.errors[0].code == 'no_evidence' and not result.articles
    assert len(fetch_network.processes) == count


def test_duplicate_jsonld_keys_cannot_silently_select_the_last_value(fetch_network):
    doc = with_detail()
    doc['detail_templates'][0].update(jsonld_types=['NewsArticle'], fields={'content': {'read': 'jsonld', 'path': ['articleBody']}})
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': '<script type="application/ld+json">{"@type":"NewsArticle","articleBody":"one","articleBody":"two"}</script>'},
    })
    result = engine(doc).preview()
    assert result.errors and result.articles[0].content_level == 'metadata_only'


@pytest.fixture
def news_source(db):
    from app.models.source import NewsSource
    source = NewsSource(name='News', slug='engine-fixture', url='https://news.test.invalid/news', category='regional')
    db.session.add(source)
    db.session.commit()
    return source


def test_run_applies_metadata_only_once_and_keeps_language_and_provenance(db, news_source, fetch_network):
    from app.models.article import Article
    fetch_network.configure(routes={'https://news.test.invalid/news': {
        'body': '<article><h2><a href="/research">Research</a></h2></article>'}})
    doc = recipe(news_source.id)
    doc['locale'] = 'en'
    first = engine(doc).run()
    assert first.status == 'success' and len(first.article_ids) == 1
    article = db.session.get(Article, first.article_ids[0])
    assert article.content_level == 'metadata_only' and article.source_language == 'en'
    assert article.crawl_provenance['recipe']
    assert article.crawl_provenance['engine'] == 'news-engine.v1'
    assert article.crawl_provenance['quality_profile']['min_content_chars'] == 200
    second = engine(doc).run()
    assert second.status == 'no_change' and second.quality.duplicate == 1
    assert not second.article_ids and not second.repair_dispatched
    assert Article.query.count() == 1


def test_metadata_upgrade_preserves_the_existing_guid_and_requeues_enrichment(db, news_source, fetch_network):
    from app.models.article import Article
    old = Article(source_id=news_source.id, external_id='historical-guid', url='https://news.test.invalid/research',
                  title_fr='Recherche Grenoble', content_level='metadata_only', source_language='fr', llm_processed=True)
    db.session.add(old)
    db.session.commit()
    article_id = old.id
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': f'<h1>Recherche Grenoble</h1><div class="body"><p>{TEXT_A}</p><p>{TEXT_B}</p></div>'},
    })
    result = engine(with_detail(recipe(news_source.id))).run()
    db.session.expire_all()
    assert result.quality.updated == 1 and result.article_ids == (article_id,)
    assert Article.query.count() == 1
    assert old.external_id == 'historical-guid' and old.content_level == 'full'
    assert not old.llm_processed


def test_late_ingestion_failure_rolls_back_all_articles_and_returns_failed_outcome(db, news_source, fetch_network):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError
    from app.models.article import Article
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body':
        '<article><h2><a href="/one">First research</a></h2></article><article><h2><a href="/two">Second research</a></h2></article>'}})
    calls = 0
    def fail_second(conn, cursor, statement, parameters, context, executemany):
        nonlocal calls
        if statement.startswith('INSERT INTO article '):
            calls += 1
            if calls == 2:
                raise OperationalError(statement, parameters, RuntimeError('Synthetic write failure'))
    event.listen(db.engine, 'before_cursor_execute', fail_second)
    try:
        result = engine(recipe(news_source.id)).run()
    finally:
        event.remove(db.engine, 'before_cursor_execute', fail_second)
    assert result.status == 'failed' and result.retryable and not result.article_ids
    assert result.errors[-1].code == 'database_error' and Article.query.count() == 0


@pytest.mark.parametrize('body', ['<div>' * 100 + 'text' + '</div>' * 100, '<p>' + 'x' * (512 * 1024) + '</p>'], ids=['depth', 'bytes'])
def test_excessive_document_depth_or_bytes_stops_before_extraction(fetch_network, body):
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': body}})
    result = engine().preview()
    assert result.status == 'failed' and result.errors[0].code == 'resource_limit'


def test_parser_has_a_separate_hard_execution_budget(fetch_network):
    from app.crawlers.engine import QualityProfile
    result = engine(profile=QualityProfile(max_parse_seconds=0.001)).preview()
    assert result.status == 'failed' and result.errors[0].code == 'resource_limit'


@pytest.mark.parametrize('date, expected', [('2026-09-06T12:00:00', '2026-09-06T10:00:00+00:00'),
                                           ('2026-10-25T02:30:00', None), ('2026-03-29T02:30:00', None)])
def test_declared_timezone_resolves_only_unambiguous_local_dates(fetch_network, date, expected):
    doc = recipe()
    doc['date_policy'] = {'source_timezone': 'Europe/Paris'}
    doc['list_pages'][0]['fields']['published_at'] = {'selector': 'time', 'read': 'attr', 'attr': 'datetime'}
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': f'<article><h2><a href="/research">Research</a></h2><time datetime="{date}"></time></article>'}})
    article, = engine(doc).preview().articles
    assert (article.published_at.isoformat() if article.published_at else None) == expected


def test_a_jsonld_description_is_only_an_excerpt_even_when_long(fetch_network):
    import json
    doc = with_detail()
    doc['detail_templates'][0].update(jsonld_types=['NewsArticle'], fields={'content': {'read': 'jsonld', 'path': ['description']}})
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': '<script type="application/ld+json">' + json.dumps({'@type': 'NewsArticle', 'description': TEXT_A + '\n\n' + TEXT_B}) + '</script>'},
    })
    assert engine(doc).preview().articles[0].content_level == 'excerpt'


def test_missing_expected_detail_content_reports_selector_drift(fetch_network):
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': '<h1>Recherche Grenoble</h1><div class="changed">Content moved</div>'},
    })
    result = engine(with_detail()).preview()
    assert result.status == 'partial' and result.articles[0].content_level == 'metadata_only'
    assert any(e.code == 'missing_fields' for e in result.errors)


def test_verified_historical_baseline_marks_a_sudden_drop_without_discarding_good_items(fetch_network):
    from app.crawlers.engine import QualityProfile
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Research</a></h2></article>'}})
    result = engine(profile=QualityProfile(recent_valid_counts=(8, 10, 12))).preview()
    assert result.status == 'degraded' and len(result.articles) == 1


@pytest.mark.parametrize('markup, code', [('<input type="password">', 'login_required'),
                                        ('<div class="paywall">Subscribe</div>', 'paywall'),
                                        ('<form id="challenge-form"></form>', 'captcha')])
def test_access_restrictions_are_not_selector_failures(fetch_network, markup, code):
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': markup}})
    result = engine().preview()
    assert result.status == 'blocked' and result.errors[0].code == code


def test_conflicting_detail_templates_do_not_choose_arbitrarily(fetch_network):
    from copy import deepcopy
    doc = with_detail()
    doc['detail_templates'].append(deepcopy(doc['detail_templates'][0]))
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Research</a></h2></article>'}})
    result = engine(doc).preview()
    assert result.errors[0].code == 'invalid_schema'
    assert not any(e['kind'] == 'http' and e['url'] == 'https://news.test.invalid/research' for e in fetch_network.events())


def test_replay_cannot_relabel_an_observation_from_a_different_page(fetch_network):
    from dataclasses import replace
    from app.crawlers.engine import PageSnapshot
    result = engine().preview()
    snap = result.snapshots[0]
    bad = replace(snap.response, observation=replace(snap.response.observation, requested_url='https://news.test.invalid/other'))
    replayed = engine(snapshots=(PageSnapshot(snap.url, bad),)).preview()
    assert replayed.errors[0].code == 'no_evidence'


def test_legacy_rss_adapter_preserves_guid_without_running_old_ingestion(db, news_source, fetch_network):
    from app.crawlers.engine import CrawlEngine
    from app.crawlers.rss_crawler import RSSCrawler
    from app.crawlers.fetcher import FetchPolicy
    from app.models.article import Article
    news_source.url = 'https://news.test.invalid/'
    news_source.feed_url = 'https://news.test.invalid/feed'
    db.session.commit()
    fetch_network.configure(routes={'https://news.test.invalid/feed': {'headers': {'Content-Type': 'application/rss+xml'}, 'body':
        '<rss version="2.0"><channel><title>News</title><link>https://news.test.invalid/</link><description>News</description><item><guid isPermaLink="false">stable-guid</guid><title>Research</title><link>https://news.test.invalid/research</link><description>Summary only</description></item></channel></rss>'}})
    crawler = CrawlEngine(news_source.id, legacy=RSSCrawler(news_source), fetch_policy=FetchPolicy(allowed_hosts=('news.test.invalid',)))
    result = crawler.preview()
    assert result.articles[0].external_id == 'stable-guid' and result.articles[0].source_language == 'unknown'
    assert result.articles[0].content_level == 'excerpt' and Article.query.count() == 0
    assert crawler.run().status == 'success'
    assert crawler.run().status == 'no_change'


def test_custom_legacy_python_cannot_enter_the_safe_adapter(db, news_source):
    from app.crawlers.engine import CrawlEngine
    from app.crawlers.html_crawler import HTMLCrawler
    from app.crawlers.fetcher import FetchPolicy
    class Custom(HTMLCrawler):
        def fetch_articles(self):
            raise AssertionError('Custom fetch must not execute')
    with pytest.raises(ValueError, match='Unsupported legacy adapter'):
        CrawlEngine(news_source.id, legacy=Custom(news_source), fetch_policy=FetchPolicy(allowed_hosts=('news.test.invalid',)))


def test_replay_is_preview_only_and_cannot_be_used_as_a_live_ingestion(db, news_source):
    with pytest.raises(ValueError, match='Replay is preview-only'):
        engine(recipe(news_source.id), snapshots=()).run()


def test_recipe_cli_previews_saves_private_snapshots_and_replays_without_http(db, news_source, fetch_network, monkeypatch, tmp_path, capsys):
    import json
    import runpy
    import stat
    import sys
    from app.models.article import Article
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Research</a></h2></article>'}})
    path = tmp_path / 'recipe.json'
    path.write_text(json.dumps(recipe(news_source.id)))
    snapshots = tmp_path / 'snapshots.json'
    command = ['scripts/run_recipe.py', '--recipe', str(path), '--allow-host', 'news.test.invalid']
    monkeypatch.setattr(sys, 'argv', command + ['--save-snapshots', str(snapshots)])
    with pytest.raises(SystemExit) as result:
        runpy.run_path('scripts/run_recipe.py', run_name='__main__')
    assert result.value.code == 0 and Article.query.count() == 0
    assert stat.S_IMODE(snapshots.stat().st_mode) == 0o600
    assert 'body' not in capsys.readouterr().out
    count = len(fetch_network.processes)
    monkeypatch.setattr(sys, 'argv', command + ['--replay', str(snapshots)])
    with pytest.raises(SystemExit) as result:
        runpy.run_path('scripts/run_recipe.py', run_name='__main__')
    assert result.value.code == 0 and len(fetch_network.processes) == count


def test_many_bad_cards_do_not_overflow_outcome_or_lose_the_committed_result(db, news_source, fetch_network):
    from app.models.article import Article
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': '<article>Missing title</article>' * 180 + '<article><h2><a href="/research">Research</a></h2></article>'}})
    result = engine(recipe(news_source.id)).run()
    assert result.status == 'partial' and result.quality.rejected == 180
    assert len(result.errors) <= 100 and len(result.article_ids) == Article.query.count() == 1


def test_candidate_budget_is_shared_by_multiple_list_pages(fetch_network):
    doc = recipe()
    from copy import deepcopy
    doc['list_pages'].append(deepcopy(doc['list_pages'][0]))
    doc['list_pages'][1]['url'] = 'https://news.test.invalid/page2'
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': ''.join(f'<article><h2><a href="/n{i}">Research {i}</a></h2></article>' for i in range(150))},
        'https://news.test.invalid/page2': {'body': ''.join(f'<article><h2><a href="/n{i}">Research {i}</a></h2></article>' for i in range(150, 300))},
    })
    result = engine(doc).preview()
    assert result.quality.discovered == 300 and result.quality.extracted == 200
    assert len(result.articles) == 200 and result.errors[-1].code == 'resource_limit'


def test_final_log_failure_also_rolls_back_business_application(db, news_source, fetch_network):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError
    from app.models.article import Article
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Research</a></h2></article>'}})
    fired = False
    def fail_log(conn, cursor, statement, parameters, context, executemany):
        nonlocal fired
        if statement.startswith('UPDATE crawl_log ') and not fired:
            fired = True
            raise OperationalError(statement, parameters, RuntimeError('Synthetic log failure'))
    event.listen(db.engine, 'before_cursor_execute', fail_log)
    try:
        result = engine(recipe(news_source.id)).run()
    finally:
        event.remove(db.engine, 'before_cursor_execute', fail_log)
    assert result.status == 'failed' and not result.article_ids and Article.query.count() == 0


@pytest.mark.parametrize('body', [TEXT_A + '\n\n' + TEXT_A,
    'Une recette au chocolat utilise du beurre et des oeufs pour obtenir une pâte bien mélangée et savoureuse.\n\nLa cuisson à chaleur tournante dure trente minutes et le gâteau refroidit avant le glaçage et la décoration.'])
def test_repeated_or_unrelated_paragraphs_cannot_pass_full_content_quality(fetch_network, body):
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': '<h1>Recherche Grenoble</h1><div class="body">' + ''.join(f'<p>{p}</p>' for p in body.split('\n\n')) + '</div>'},
    })
    result = engine(with_detail()).preview()
    assert result.articles[0].content_level != 'full' and result.status == 'degraded'


def test_detail_relative_image_uses_detail_document_base(fetch_network):
    doc = with_detail()
    doc['detail_templates'][0]['fields']['image_url'] = {'selector': 'img', 'read': 'attr', 'attr': 'src'}
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research/item">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research/item': {'body': f'<h1>Recherche Grenoble</h1><img src="chart.png"><div class="body"><p>{TEXT_A}</p><p>{TEXT_B}</p></div>'},
    })
    assert engine(doc).preview().articles[0].image_url == 'https://news.test.invalid/research/chart.png'


def test_atom_full_content_passes_quality_and_avoids_redundant_detail_fetch(fetch_network):
    from html import escape
    doc = with_detail(rss_recipe())
    doc['feed']['fields']['content'] = 'content'
    doc['feed']['fields']['published_at'] = 'updated'
    feed = f'<feed xmlns="http://www.w3.org/2005/Atom"><title>News</title><id>news</id><updated>2026-09-06T12:00:00Z</updated><entry><id>atom-guid</id><title>Recherche Grenoble</title><link href="https://news.test.invalid/research"/><updated>2026-09-06T12:00:00Z</updated><content type="html">{escape("<p>" + TEXT_A + "</p><p>" + TEXT_B + "</p>")}</content></entry></feed>'
    fetch_network.configure(routes={'https://news.test.invalid/feed': {'body': feed, 'headers': {'Content-Type': 'application/atom+xml'}}})
    result = engine(doc).preview()
    assert result.articles[0].content_level == 'full' and result.articles[0].external_id == 'atom-guid'
    assert result.status == 'ready' and not any(e['kind'] == 'http' and e['url'].endswith('/research') for e in fetch_network.events())


@pytest.mark.parametrize('restriction', ['hidden', 'style="display: none"'])
def test_explicitly_hidden_body_is_not_promoted_to_public_full_text(fetch_network, restriction):
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': f'<h1>Recherche Grenoble</h1><div class="body" {restriction}><p>{TEXT_A}</p><p>{TEXT_B}</p></div>'},
    })
    result = engine(with_detail()).preview()
    assert result.articles[0].content_level == 'metadata_only'


def test_jsonld_primary_entity_explicitly_marks_paid_access(fetch_network):
    import json
    doc = with_detail()
    doc['detail_templates'][0].update(jsonld_types=['NewsArticle'], fields={'content': {'read': 'jsonld', 'path': ['articleBody']}})
    data = {'@type': 'NewsArticle', 'isAccessibleForFree': False, 'articleBody': TEXT_A + '\n\n' + TEXT_B}
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': '<script type="application/ld+json">' + json.dumps(data) + '</script>'},
    })
    result = engine(doc).preview()
    assert result.articles[0].content_level == 'metadata_only' and result.errors[0].code == 'paywall'


def test_uncached_304_is_insufficient_evidence_not_a_selector_failure(fetch_network):
    fetch_network.configure(routes={'https://news.test.invalid/news': {'status': 304}})
    result = engine().preview()
    assert result.status == 'inconclusive' and result.errors[0].code == 'no_evidence'


def test_quality_upgrade_keeps_an_unchanged_title_translation_and_manual_relations(db, news_source, fetch_network):
    from app.models.article import Article, ArticleCompany
    from app.models.company import Company
    article = Article(source_id=news_source.id, external_id='old', url='https://news.test.invalid/research',
                      title_fr='Recherche Grenoble', title_zh='既有成功标题翻译', content_level='metadata_only')
    company = Company(name='Manual company', slug='manual-quality')
    db.session.add_all([article, company])
    db.session.flush()
    db.session.add(ArticleCompany(article_id=article.id, company_id=company.id, extracted_by='manual', sentiment='negative'))
    db.session.commit()
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': f'<h1>Recherche Grenoble</h1><div class="body"><p>{TEXT_A}</p><p>{TEXT_B}</p></div>'},
    })
    result = engine(with_detail(recipe(news_source.id))).run()
    db.session.expire_all()
    assert result.quality.updated == 1 and article.title_zh == '既有成功标题翻译'
    assert ArticleCompany.query.one().extracted_by == 'manual' and ArticleCompany.query.one().sentiment == 'negative'


@pytest.mark.parametrize('old_level', ['full', None])
def test_lower_quality_never_overwrites_a_better_or_unknown_legacy_body(db, news_source, fetch_network, old_level):
    from app.models.article import Article
    article = Article(source_id=news_source.id, external_id='old', url='https://news.test.invalid/research',
                      title_fr='Original title', content_fr='Preserved original body', insight_en='Preserved insight',
                      content_level=old_level, llm_processed=True)
    db.session.add(article)
    db.session.commit()
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Research</a></h2></article>'}})
    result = engine(recipe(news_source.id)).run()
    db.session.expire_all()
    assert result.status == 'no_change' and not result.article_ids
    assert article.content_fr == 'Preserved original body' and article.insight_en == 'Preserved insight'
    assert article.title_fr == 'Original title' and article.llm_processed


def test_implicit_rss_guid_stays_compatible_with_a_later_legacy_run(db, news_source, fetch_network):
    from app.crawlers.rss_crawler import RSSCrawler
    from app.models.article import Article
    doc = rss_recipe()
    doc['source_id'] = news_source.id
    del doc['feed']['fields']['external_id']
    news_source.feed_url = doc['feed']['url']
    db.session.commit()
    feed = '<rss version="2.0"><channel><title>News</title><item><guid isPermaLink="false">retained-guid</guid><title>Research</title><link>https://news.test.invalid/research</link></item></channel></rss>'
    fetch_network.configure(routes={doc['feed']['url']: {'body': feed, 'headers': {'Content-Type': 'application/rss+xml'}}})
    assert engine(doc).run().status == 'success'
    result = RSSCrawler(news_source).run()
    assert result.status == 'no_change' and Article.query.count() == 1
    assert Article.query.one().external_id == 'retained-guid'


def test_url_canonicalization_does_not_change_the_legacy_hash_identity(db, news_source, fetch_network):
    from app.crawlers.html_crawler import HTMLCrawler
    from app.models.article import Article
    import hashlib
    url = 'https://news.test.invalid/research#section'
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': f'<article><h2><a href="{url}">Research</a></h2></article>'}})
    assert engine(recipe(news_source.id)).run().status == 'success'
    result = HTMLCrawler(news_source).run()
    assert result.status == 'no_change' and Article.query.count() == 1
    assert Article.query.one().external_id == hashlib.sha256(url.encode()).hexdigest()[:32]


def test_upgrade_provenance_does_not_claim_new_evidence_for_a_preserved_identity(db, news_source, fetch_network):
    from app.models.article import Article
    article = Article(source_id=news_source.id, external_id='retained-guid', url='https://news.test.invalid/research',
                      title_fr='Recherche Grenoble', author='Known author', content_level='metadata_only')
    db.session.add(article)
    db.session.commit()
    doc = with_detail(recipe(news_source.id))
    doc['list_pages'][0]['fields']['external_id'] = {'selector': 'a', 'read': 'attr', 'attr': 'id'}
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a id="changed-guid" href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': f'<h1>Recherche Grenoble</h1><div class="body"><p>{TEXT_A}</p><p>{TEXT_B}</p></div>'},
    })
    assert engine(doc).run().quality.updated == 1
    db.session.expire_all()
    assert article.external_id == 'retained-guid' and article.author == 'Known author'
    provenance = {p['field']: p for p in article.crawl_provenance['fields']}
    assert provenance['external_id']['method'] == 'legacy' and provenance['external_id']['snapshot_id'] is None


@pytest.mark.parametrize('failure', ['launch', 'dependencies'])
def test_parser_infrastructure_failure_is_not_reported_as_bad_source_markup(fetch_network, monkeypatch, failure):
    from pathlib import Path
    import subprocess
    original = subprocess.Popen
    def launch(command, **kwargs):
        if Path(command[-1]).name == '_parse_worker.py':
            if failure == 'launch':
                raise OSError('Synthetic launch failure')
            command = [command[0], '-I', '-S', command[-1]]
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', launch)
    result = engine().preview()
    assert result.status == 'failed' and result.errors[0].code == 'parser_unavailable'


def test_field_locators_identify_the_list_page_and_local_item_position(fetch_network):
    from copy import deepcopy
    doc = recipe()
    doc['list_pages'].append(deepcopy(doc['list_pages'][0]))
    doc['list_pages'][1]['url'] = 'https://news.test.invalid/other'
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/one">First</a></h2></article>'},
        'https://news.test.invalid/other': {'body': '<article><h2><a href="/two">Second</a></h2></article>'},
    })
    second = engine(doc).preview().articles[1]
    assert next(p for p in second.provenance if p.field == 'title').locator.endswith('list:1:page:0:item:0:title')


def test_recipe_cli_selects_a_trusted_bulletin_profile_and_records_it(fetch_network, monkeypatch, tmp_path, capsys):
    import json
    import runpy
    import sys
    path = tmp_path / 'bulletin.json'
    path.write_text(json.dumps(with_detail()))
    snapshots = tmp_path / 'bulletin-snapshots.json'
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': f'<h1>Recherche Grenoble</h1><div class="body"><p>{TEXT_A}</p></div>'},
    })
    monkeypatch.setattr(sys, 'argv', ['scripts/run_recipe.py', '--recipe', str(path), '--allow-host', 'news.test.invalid',
                                    '--profile', 'bulletin', '--save-snapshots', str(snapshots)])
    with pytest.raises(SystemExit) as result:
        runpy.run_path('scripts/run_recipe.py', run_name='__main__')
    assert result.value.code == 0
    assert json.loads(capsys.readouterr().out)['content_levels'] == {'full': 1}
    saved = json.loads(snapshots.read_text())
    assert saved['captured_engine'] == 'news-engine.v1' and saved['captured_quality_profile']['min_paragraphs'] == 1


def test_an_unexplained_empty_second_page_is_not_overall_success(fetch_network):
    doc = recipe()
    doc['list_pages'][0]['pagination'] = {'kind': 'next_link', 'selector': 'a.next', 'max_pages': 2}
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/one">First</a></h2></article><a class="next" href="/page2">Next</a>'},
        'https://news.test.invalid/page2': {'body': '<div class="layout-changed">No matching cards</div>'},
    })
    result = engine(doc).preview()
    assert result.status == 'partial' and result.quality.valid == 1
    assert any(e.code == 'no_evidence' for e in result.errors)


def test_exhausted_candidate_budget_stops_before_requesting_another_page(fetch_network):
    doc = recipe()
    doc['list_pages'][0]['pagination'] = {'kind': 'next_link', 'selector': 'a.next', 'max_pages': 2}
    body = ''.join(f'<article><h2><a href="/n{i}">News {i}</a></h2></article>' for i in range(200)) + '<a class="next" href="/not-requested">Next</a>'
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': body}})
    result = engine(doc).preview()
    assert result.status == 'partial' and result.errors[-1].code == 'resource_limit'
    assert not any(e['kind'] == 'http' and e['url'].endswith('/not-requested') for e in fetch_network.events())


@pytest.mark.parametrize('kind', ['duplicate', 'too_many', 'non_snapshot', 'generator'])
def test_replay_inputs_are_bounded_and_unambiguous(fetch_network, kind):
    pages = engine().preview().snapshots
    bad = {'duplicate': pages * 2, 'too_many': pages * 17, 'non_snapshot': (None,), 'generator': iter(())}[kind]
    with pytest.raises(ValueError, match='Invalid snapshots'):
        engine(snapshots=bad)


@pytest.mark.parametrize('argument', ['profile', 'fetch_policy'])
def test_policy_and_profile_must_be_validated_system_objects(argument):
    from app.crawlers.engine import CrawlEngine
    kwargs = {'recipe': recipe(), 'fetch_policy': FetchPolicy(allowed_hosts=('news.test.invalid',)), argument: {}}
    with pytest.raises(ValueError):
        CrawlEngine(1, **kwargs)


def test_recipe_cli_reports_deeply_malformed_snapshots_without_traceback(monkeypatch, tmp_path):
    import json
    import runpy
    import sys
    path, replay = tmp_path / 'recipe.json', tmp_path / 'bad-snapshots.json'
    path.write_text(json.dumps(recipe()))
    replay.write_text('[' * 20000 + '0' + ']' * 20000)
    monkeypatch.setattr(sys, 'argv', ['scripts/run_recipe.py', '--recipe', str(path), '--allow-host', 'news.test.invalid', '--replay', str(replay)])
    with pytest.raises(SystemExit) as result:
        runpy.run_path('scripts/run_recipe.py', run_name='__main__')
    assert result.value.code == 2


def test_recipe_cli_apply_uses_the_same_partial_result_gate(db, news_source, fetch_network, monkeypatch, tmp_path, capsys):
    import json
    import runpy
    import sys
    from app.models.article import Article
    path = tmp_path / 'apply.json'
    path.write_text(json.dumps(recipe(news_source.id)))
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': '<article><h2><a href="/one">Research</a></h2></article><article>Bad</article>'}})
    monkeypatch.setattr(sys, 'argv', ['scripts/run_recipe.py', '--recipe', str(path), '--allow-host', 'news.test.invalid', '--apply'])
    with pytest.raises(SystemExit) as result:
        runpy.run_path('scripts/run_recipe.py', run_name='__main__')
    assert result.value.code == 1
    output = json.loads(capsys.readouterr().out)
    assert output['status'] == 'partial' and len(output['article_ids']) == Article.query.count() == 1
    assert Article.query.one().content_level == 'metadata_only'


def test_jsonld_html_body_is_cleaned_before_classification(fetch_network):
    import json
    doc = with_detail()
    doc['detail_templates'][0].update(jsonld_types=['NewsArticle'], fields={'content': {'read': 'jsonld', 'path': ['articleBody']}})
    data = {'@type': 'NewsArticle', 'articleBody': f'<p>{TEXT_A}</p><p>{TEXT_B}</p><script>trackingCode()</script>'}
    fetch_network.configure(routes={
        'https://news.test.invalid/news': {'body': '<article><h2><a href="/research">Recherche Grenoble</a></h2></article>'},
        'https://news.test.invalid/research': {'body': '<script type="application/ld+json">' + json.dumps(data).replace('</script>', '<\\/script>') + '</script>'},
    })
    article, = engine(doc).preview().articles
    assert article.content == TEXT_A + '\n\n' + TEXT_B and article.content_level == 'full'


def test_rss_does_not_expand_declared_entities(fetch_network):
    doc = rss_recipe()
    feed = '<!DOCTYPE rss [<!ENTITY extra "Research Grenoble">]><rss version="2.0"><channel><title>News</title><item><title>&extra;</title><link>https://news.test.invalid/research</link></item></channel></rss>'
    fetch_network.configure(routes={doc['feed']['url']: {'body': feed, 'headers': {'Content-Type': 'application/rss+xml'}}})
    result = engine(doc).preview()
    assert not result.articles and result.errors[0].code == 'invalid_article'


def test_preview_does_not_report_success_when_the_run_budget_expires_after_parsing(fetch_network, monkeypatch):
    from pathlib import Path
    import subprocess
    import time
    original_spawn, original_clock = subprocess.Popen, time.monotonic
    expired = False
    def launch(command, **kwargs):
        process = original_spawn(command, **kwargs)
        if Path(command[-1]).name == '_parse_worker.py':
            communicate = process.communicate
            def completed(*args, **kwargs):
                nonlocal expired
                result = communicate(*args, **kwargs)
                expired = True
                return result
            monkeypatch.setattr(process, 'communicate', completed)
        return process
    monkeypatch.setattr(subprocess, 'Popen', launch)
    monkeypatch.setattr(time, 'monotonic', lambda: original_clock() + (100 if expired else 0))
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': '<article><h2><a href="/one">Research</a></h2></article>'}})
    result = engine().preview()
    assert result.status == 'failed' and result.errors[0].code == 'resource_limit'


def test_run_start_is_durable_before_network(db, news_source, fetch_network, monkeypatch):
    from pathlib import Path
    import subprocess
    from sqlalchemy.orm import Session
    from app.models.source import CrawlLog
    original, observed = subprocess.Popen, []
    def launch(command, **kwargs):
        if Path(command[-1]).name == '_fetch_worker.py':
            with Session(db.engine) as session:
                log = session.query(CrawlLog).filter_by(source_id=news_source.id, status='running').one_or_none()
                observed.append(log.id if log else None)
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', launch)
    fetch_network.configure(routes={'https://news.test.invalid/news': {'body': '<article><h2><a href="/one">Research</a></h2></article>'}})
    result = engine(recipe(news_source.id)).run()
    assert observed == [result.run_id] and result.status == 'success'
