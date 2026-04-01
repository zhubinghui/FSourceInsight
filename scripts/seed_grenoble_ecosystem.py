"""Load the full Grenoble ecosystem data (509 companies with AI analyses).

This fixture contains all discovered companies from Linksium, CEA-Leti,
and Minalogic, with pre-generated AI analysis, sector classification,
spin-off origin, and company stage data.

Run after other seed scripts:
    python scripts/seed_grenoble_ecosystem.py
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from app import create_app
from app.extensions import db
from app.models.company import Company

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'grenoble_ecosystem.json')


def seed():
    app = create_app()
    with app.app_context():
        with open(DATA_FILE, encoding='utf-8') as f:
            data = json.load(f)

        added = 0
        updated = 0
        skipped = 0

        for entry in data:
            slug = entry['slug']
            existing = Company.query.filter_by(slug=slug).first()

            if existing:
                # Update fields if the fixture has richer data
                changed = False
                if entry.get('ai_analysis') and not existing.ai_analysis:
                    existing.ai_analysis = entry['ai_analysis']
                    existing.ai_analysis_at = datetime.utcnow()
                    changed = True
                if entry.get('sector') and not existing.sector:
                    existing.sector = entry['sector']
                    changed = True
                if entry.get('spinoff_origin') and not existing.spinoff_origin:
                    existing.spinoff_origin = entry['spinoff_origin']
                    changed = True
                if entry.get('company_stage') and not existing.company_stage:
                    existing.company_stage = entry['company_stage']
                    changed = True
                if entry.get('website') and not existing.website:
                    existing.website = entry['website']
                    changed = True
                if not existing.is_grenoble:
                    existing.is_grenoble = True
                    changed = True

                if changed:
                    updated += 1
                else:
                    skipped += 1
            else:
                company = Company(
                    name=entry['name'],
                    slug=slug,
                    aliases=entry.get('aliases'),
                    description=entry.get('description'),
                    website=entry.get('website'),
                    headquarters=entry.get('headquarters'),
                    sector=entry.get('sector'),
                    company_stage=entry.get('company_stage'),
                    spinoff_origin=entry.get('spinoff_origin'),
                    ai_analysis=entry.get('ai_analysis'),
                    ai_analysis_at=datetime.utcnow() if entry.get('ai_analysis') else None,
                    is_grenoble=True,
                    is_auto_created=True,
                )
                db.session.add(company)
                added += 1

        db.session.commit()
        total = Company.query.filter_by(is_grenoble=True).count()
        print(f'Grenoble ecosystem: {added} added, {updated} updated, {skipped} unchanged. Total: {total}')


if __name__ == '__main__':
    seed()
