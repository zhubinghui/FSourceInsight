"""NER may report where a company sits; Isère candidates queue for review, never publish."""
import pytest

from app.llm import prompts
from app.llm.contracts import InvalidLLMResponse, validate_response
from app.llm.tasks import process_article_llm
from app.models.company import Company


def _ner(entries):
    def reply(call):
        system = call['messages'][0]['content']
        if 'Named Entity Recognition' in system:
            return {'companies': entries}
        if 'sentiment analysis specialist' in system:
            return {'sentiment': 'neutral', 'score': 0.0, 'reason': 'factual'}
        if 'tech news classifier' in system:
            return {'categories': [{'category': 'research', 'confidence': 0.9}],
                    'highlights': [], 'event_date': None}
        return 'Synthetic text'
    return reply


def _entry(name, **extra):
    return {'name': name, 'mentions': 1, 'is_primary': True, **extra}


def test_contract_accepts_an_optional_location_and_rejects_bad_ones():
    ok = validate_response('ner', '{"companies": [{"name": "Verkor", "mentions": 1, "is_primary": true, '
                               '"location": {"city": "Grenoble", "postcode": "38000", "in_isere": true}}]}')
    assert ok['companies'][0]['location'] == {'city': 'Grenoble', 'postcode': '38000', 'in_isere': True}
    # Absent location stays valid: existing prompts and cached replies must keep working.
    assert 'location' not in validate_response(
        'ner', '{"companies": [{"name": "Soitec", "mentions": 1, "is_primary": true}]}')['companies'][0]

    for bad in ['{"city": "Grenoble", "in_isere": "yes"}', '{"in_isere": true, "surprise": 1}',
                '{"city": "' + 'x' * 200 + '", "in_isere": true}']:
        with pytest.raises(InvalidLLMResponse):
            validate_response('ner', '{"companies": [{"name": "X", "mentions": 1, "is_primary": true, '
                                  f'"location": {bad}}}]}}')


def test_ner_prompt_asks_for_the_location_and_is_versioned():
    assert 'in_isere' in prompts.NER_SYSTEM and 'Isère' in prompts.NER_SYSTEM
    assert prompts.PROMPT_VERSION > '2026-09-06.2'


def test_isere_company_is_created_pending_and_stays_off_the_map(db, llm_env):
    llm_env.provider.reply = _ner([_entry('Verkor', location={'city': 'Grenoble', 'in_isere': True}),
                                   _entry('Global Corp', location={'city': 'Paris', 'in_isere': False}),
                                   _entry('Unknown Place')])

    process_article_llm.run(llm_env.article.id)

    db.session.expire_all()
    created = {c.name: (c.is_grenoble, c.review_status, c.city) for c in Company.query.all()}
    assert created == {'Verkor': (True, 'pending', 'Grenoble'),
                       'Global Corp': (False, 'approved', 'Paris'),
                       'Unknown Place': (False, 'approved', None)}


def test_existing_companies_keep_their_review_decisions(db, llm_env):
    db.session.add_all([
        Company(name='Rejected Junk', slug='rejected-junk', review_status='rejected'),
        Company(name='Known Local', slug='known-local', is_grenoble=False, review_status='approved', city='Voiron'),
    ])
    db.session.commit()
    llm_env.provider.reply = _ner([_entry('Rejected Junk', location={'city': 'Grenoble', 'in_isere': True}),
                                   _entry('Known Local', location={'city': 'Grenoble', 'in_isere': True})])

    process_article_llm.run(llm_env.article.id)

    db.session.expire_all()
    rejected = Company.query.filter_by(slug='rejected-junk').one()
    known = Company.query.filter_by(slug='known-local').one()
    assert (rejected.review_status, rejected.is_grenoble) == ('rejected', False)
    assert (known.review_status, known.is_grenoble, known.city) == ('approved', False, 'Voiron')
