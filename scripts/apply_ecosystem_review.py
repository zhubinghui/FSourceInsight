"""Apply a reviewed ecosystem CSV (slug,name,action,entity_type,postcode,city,local_site).

Default is a dry run. Take a database backup before --apply.
    python scripts/apply_ecosystem_review.py review.csv
    python scripts/apply_ecosystem_review.py review.csv --apply
"""
import argparse
import csv
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.ecosystem_review import apply_review


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('csv_path')
    parser.add_argument('--apply', action='store_true', help='write changes (default: dry run)')
    parser.add_argument('--verbose', action='store_true', help='list every change')
    args = parser.parse_args()
    with open(args.csv_path, encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    with create_app().app_context():
        report = apply_review(rows, apply=args.apply)
    print(f'{"APPLIED" if report.applied else "DRY RUN"}: {report.counts or "no changes"}; '
          f'unchanged {report.unchanged}; skipped {len(report.skipped)}')
    for skipped in report.skipped:
        print(f'  skipped {skipped.slug}: {skipped.reason}')
    if args.verbose:
        for slug, action, changes in report.changes:
            print(f'  {action} {slug}: {changes}')


if __name__ == '__main__':
    main()
