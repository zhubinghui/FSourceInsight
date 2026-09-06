"""Response contracts: invalid output is a failure, never an invented empty result."""
import json
import math
from datetime import date

CONTRACT_VERSION = '1'
CATEGORIES = {'semiconductor', 'ai', 'software', 'cloud', 'cybersecurity', 'iot',
              'energy', 'automotive', 'aerospace', 'biotech', 'startup', 'fintech', 'telecom', 'research'}
HIGHLIGHTS = {'tech_breakthrough', 'local_research', 'investment', 'local_event'}
COMPANY_FIELDS = {'overview', 'founders', 'spinoff_source', 'core_tech', 'competitors',
                  'cn_competitor_names', 'business_status', 'recommendation', 'recommendation_reason', 'website'}
JSON_TASKS = {'ner', 'sentiment', 'classify', 'company_analysis'}


class InvalidLLMResponse(ValueError):
    pass


def _require(condition):
    if not condition:
        # Do not include model text, news or credentials in validation errors.
        raise InvalidLLMResponse('LLM response violates the task contract')


def _object(value, required, optional=()):
    _require(isinstance(value, dict))
    _require(set(required) <= value.keys() <= set(required) | set(optional))


def _string(value, limit=4000, nonempty=False):
    _require(isinstance(value, str) and len(value) <= limit and (not nonempty or bool(value.strip())))


def _number(value, lower, upper):
    _require(type(value) in (int, float) and math.isfinite(value) and lower <= value <= upper)


def _list(value, limit):
    _require(isinstance(value, list) and len(value) <= limit)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def validate_response(task, text):
    _string(text, limit=200000, nonempty=True)
    if task not in JSON_TASKS:
        return text
    text = text.strip()
    if text.startswith('```') and text.endswith('```') and '\n' in text:
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    try:
        value = json.loads(text, object_pairs_hook=_unique_object,
                           parse_constant=lambda _: _require(False))
    except (ValueError, RecursionError) as exc:
        raise InvalidLLMResponse('LLM response is not valid JSON') from exc
    if task == 'ner':
        _object(value, {'companies'})
        _list(value['companies'], 100)
        for entry in value['companies']:
            _object(entry, {'name', 'mentions', 'is_primary'}, {'spinoff_origin', 'company_stage'})
            _string(entry['name'], 300, nonempty=True)
            _require(type(entry['mentions']) is int and 1 <= entry['mentions'] <= 100000)
            _require(type(entry['is_primary']) is bool)
            if entry.get('spinoff_origin') is not None:
                _string(entry['spinoff_origin'], 200)
            _require(entry.get('company_stage') in (None, 'startup', 'scale-up', 'mature'))
    elif task == 'sentiment':
        _object(value, {'sentiment', 'score', 'reason'})
        _require(value['sentiment'] in ('positive', 'negative', 'neutral'))
        _number(value['score'], -1, 1)
        _string(value['reason'])
    elif task == 'classify':
        _object(value, {'categories', 'highlights', 'event_date'})
        _list(value['categories'], 14)
        _list(value['highlights'], 4)
        for entry in value['categories']:
            _object(entry, {'category', 'confidence'})
            _string(entry['category'], 100)
            _require(entry['category'] in CATEGORIES)
            _number(entry['confidence'], 0, 1)
        for tag in value['highlights']:
            _string(tag, 100)
            _require(tag in HIGHLIGHTS)
        if value['event_date'] is not None:
            _string(value['event_date'], 10)
            try:
                _require(date.fromisoformat(value['event_date']).isoformat() == value['event_date'])
            except ValueError as exc:
                raise InvalidLLMResponse('Invalid event date') from exc
    elif task == 'company_analysis':
        _object(value, COMPANY_FIELDS)
        for key in COMPANY_FIELDS - {'competitors'}:
            _string(value[key], 500 if key == 'website' else 4000)
        _require(value['recommendation'] in ('', '重点关注', '持续监控', '一般了解'))
        _list(value['competitors'], 10)
        for entry in value['competitors']:
            _object(entry, {'dimension', 'company', 'cn_competitor'})
            for field in entry.values():
                _string(field)
    return value
