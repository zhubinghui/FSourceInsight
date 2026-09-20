"""Apply operator-reviewed ecosystem corrections from a CSV; dry-run by default.

Rows are keyed by slug and guarded by the exact company name, so a stale file
skips rows instead of touching a different entity. Junk is rejected, never
deleted: the retained slug keeps discovery from recreating it.
"""
from collections import Counter
from dataclasses import dataclass, field

from app.extensions import db
from app.models.company import Company

ACTIONS = {'reject', 'unflag', 'flag', 'keep'}
ENTITY_TYPES = {'', 'company', 'corporate', 'research_education', 'ecosystem_support'}
COLUMNS = ['slug', 'name', 'action', 'entity_type', 'postcode', 'city', 'local_site']


class ReviewError(ValueError):
    pass


@dataclass
class Skipped:
    slug: str
    reason: str


@dataclass
class Report:
    applied: bool
    counts: dict = field(default_factory=dict)
    unchanged: int = 0
    skipped: list = field(default_factory=list)
    changes: list = field(default_factory=list)


def _validate(rows):
    seen = set()
    for number, row in enumerate(rows, start=2):
        missing = [column for column in COLUMNS if column not in row]
        if missing:
            raise ReviewError(f'line {number}: missing columns {missing}')
        if row['action'] not in ACTIONS:
            raise ReviewError(f'line {number}: unknown action {row["action"]!r}')
        if row['entity_type'] not in ENTITY_TYPES:
            raise ReviewError(f'line {number}: unknown entity_type {row["entity_type"]!r}')
        if row['local_site'] not in ('', '0', '1'):
            raise ReviewError(f'line {number}: local_site must be 0, 1 or empty')
        if not row['slug'] or row['slug'] in seen:
            raise ReviewError(f'line {number}: empty or repeated slug {row["slug"]!r}')
        seen.add(row['slug'])


def _target(company, row):
    values = {}
    if row['action'] == 'reject':
        values['review_status'] = 'rejected'
    elif row['action'] == 'unflag':
        values['is_grenoble'] = False
    elif row['action'] == 'flag':
        values.update(is_grenoble=True, review_status='approved')
    for column in ('entity_type', 'postcode', 'city'):
        if row[column]:
            values[column] = row[column]
    if row['local_site']:
        values['local_site'] = row['local_site'] == '1'
    return {key: value for key, value in values.items() if getattr(company, key) != value}


def apply_review(rows, apply=False):
    rows = list(rows)
    _validate(rows)
    report, counts = Report(applied=apply), Counter()
    for row in rows:
        company = Company.query.filter_by(slug=row['slug']).first()
        if company is None or company.name != row['name']:
            report.skipped.append(Skipped(row['slug'], 'not found' if company is None else 'name mismatch'))
            continue
        changes = _target(company, row)
        if not changes:
            report.unchanged += 1
            continue
        counts[row['action']] += 1
        report.changes.append((row['slug'], row['action'], changes))
        if apply:
            for key, value in changes.items():
                setattr(company, key, value)
    if apply:
        db.session.commit()
    report.counts = dict(counts)
    return report
