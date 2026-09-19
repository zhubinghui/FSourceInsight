"""Operator-reviewed ecosystem corrections: dry-run first, guarded, repeatable."""
import importlib.util
import json
from pathlib import Path

import pytest

from app.ecosystem_review import ReviewError, apply_review
from app.models.company import Company

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def companies(db):
    rows = [
        Company(name='From Tuesday April 07', slug='from-tuesday-april-07', is_grenoble=True),
        Company(name='EURONEXT', slug='euronext', is_grenoble=True),
        Company(name='Verkor', slug='verkor', is_grenoble=False),
        Company(name='Soitec', slug='soitec', is_grenoble=True),
    ]
    db.session.add_all(rows)
    db.session.commit()


def _row(slug, name, action, **extra):
    return {'slug': slug, 'name': name, 'action': action, 'entity_type': '', 'postcode': '',
            'city': '', 'local_site': '', **extra}


REVIEW = [
    _row('from-tuesday-april-07', 'From Tuesday April 07', 'reject'),
    _row('euronext', 'EURONEXT', 'unflag', entity_type='ecosystem_support', postcode='69289', city='Lyon'),
    _row('verkor', 'Verkor', 'flag', entity_type='company', city='Grenoble'),
    _row('soitec', 'Soitec', 'keep', entity_type='corporate', postcode='38190', city='Bernin'),
]


def _state():
    return {c.slug: (c.is_grenoble, c.review_status, c.entity_type, c.postcode, c.city)
            for c in Company.query.all()}


def test_dry_run_reports_changes_and_writes_nothing(db, companies):
    before = _state()

    report = apply_review(REVIEW)

    assert report.counts == {'reject': 1, 'unflag': 1, 'flag': 1, 'keep': 1}
    assert report.applied is False
    db.session.rollback()
    assert _state() == before


def test_apply_sets_review_location_and_type(db, companies):
    apply_review(REVIEW, apply=True)

    db.session.expire_all()
    assert _state() == {
        'from-tuesday-april-07': (True, 'rejected', None, None, None),
        'euronext': (False, 'approved', 'ecosystem_support', '69289', 'Lyon'),
        'verkor': (True, 'approved', 'company', None, 'Grenoble'),
        'soitec': (True, 'approved', 'corporate', '38190', 'Bernin'),
    }


def test_second_apply_changes_nothing(db, companies):
    apply_review(REVIEW, apply=True)

    report = apply_review(REVIEW, apply=True)

    assert report.counts == {}
    assert report.unchanged == 4


def test_stale_rows_are_skipped_not_guessed(db, companies):
    rows = [_row('euronext', 'Euronext Paris SA', 'reject'), _row('no-such-company', 'Ghost', 'reject')]

    report = apply_review(rows, apply=True)

    assert [(s.slug, s.reason) for s in report.skipped] == [
        ('euronext', 'name mismatch'), ('no-such-company', 'not found')]
    assert Company.query.filter_by(slug='euronext').one().review_status == 'approved'


def test_invalid_file_is_refused_before_any_write(db, companies):
    rows = [REVIEW[0], _row('soitec', 'Soitec', 'delete')]

    with pytest.raises(ReviewError, match='delete'):
        apply_review(rows, apply=True)

    db.session.rollback()
    assert Company.query.filter_by(slug='from-tuesday-april-07').one().review_status == 'approved'


def test_fixture_seed_respects_operator_corrections(app, db, tmp_path, monkeypatch):
    db.session.add_all([
        Company(name='EURONEXT', slug='euronext', is_grenoble=False),
        Company(name='With mailing tool', slug='with-mailing-tool', is_grenoble=True, review_status='rejected'),
    ])
    db.session.commit()
    data = tmp_path / 'fixture.json'
    data.write_text(json.dumps([{'name': 'EURONEXT', 'slug': 'euronext', 'sector': 'Semiconductor'},
                                {'name': 'With mailing tool', 'slug': 'with-mailing-tool'}]))
    spec = importlib.util.spec_from_file_location('seed_fixture', ROOT / 'scripts' / 'seed_grenoble_ecosystem.py')
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    monkeypatch.setattr(seed, 'create_app', lambda: app)
    monkeypatch.setattr(seed, 'DATA_FILE', str(data))

    seed.seed()

    db.session.expire_all()
    assert Company.query.filter_by(slug='euronext').one().is_grenoble is False
    assert Company.query.filter_by(slug='with-mailing-tool').one().review_status == 'rejected'
