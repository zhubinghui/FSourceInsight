"""Seed the database with tech news categories."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slugify import slugify
from app import create_app
from app.extensions import db
from app.models.category import Category

CATEGORIES = [
    {'name': 'Semiconductor', 'slug': 'semiconductor', 'name_zh': '半导体', 'name_en': 'Semiconductor'},
    {'name': 'AI', 'slug': 'ai', 'name_zh': '人工智能', 'name_en': 'Artificial Intelligence'},
    {'name': 'Software', 'slug': 'software', 'name_zh': '软件', 'name_en': 'Software'},
    {'name': 'Cloud', 'slug': 'cloud', 'name_zh': '云计算', 'name_en': 'Cloud Computing'},
    {'name': 'Cybersecurity', 'slug': 'cybersecurity', 'name_zh': '网络安全', 'name_en': 'Cybersecurity'},
    {'name': 'IoT', 'slug': 'iot', 'name_zh': '物联网', 'name_en': 'Internet of Things'},
    {'name': 'Energy', 'slug': 'energy', 'name_zh': '能源', 'name_en': 'Energy'},
    {'name': 'Automotive', 'slug': 'automotive', 'name_zh': '汽车', 'name_en': 'Automotive'},
    {'name': 'Aerospace', 'slug': 'aerospace', 'name_zh': '航空航天', 'name_en': 'Aerospace'},
    {'name': 'Biotech', 'slug': 'biotech', 'name_zh': '生物技术', 'name_en': 'Biotechnology'},
    {'name': 'Startup', 'slug': 'startup', 'name_zh': '创业', 'name_en': 'Startup'},
    {'name': 'Fintech', 'slug': 'fintech', 'name_zh': '金融科技', 'name_en': 'Fintech'},
    {'name': 'Telecom', 'slug': 'telecom', 'name_zh': '电信', 'name_en': 'Telecommunications'},
    {'name': 'Research', 'slug': 'research', 'name_zh': '科研', 'name_en': 'Research'},
]


def seed():
    app = create_app()
    with app.app_context():
        for data in CATEGORIES:
            existing = Category.query.filter_by(slug=data['slug']).first()
            if existing:
                print(f'  Skipping {data["name"]} (already exists)')
                continue
            cat = Category(**data)
            db.session.add(cat)
            print(f'  Added: {data["name"]}')
        db.session.commit()
        print(f'\nDone. {Category.query.count()} categories in database.')


if __name__ == '__main__':
    seed()
