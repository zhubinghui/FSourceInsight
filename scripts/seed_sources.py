"""Seed the database with initial news sources."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.source import NewsSource

SOURCES = [
    # National - RSS
    {
        'name': "L'Usine Digitale",
        'slug': 'usine-digitale',
        'url': 'https://www.usine-digitale.fr',
        'feed_url': 'https://www.usine-digitale.fr/rss',
        'feed_type': 'rss',
        'category': 'national',
        'crawl_frequency_minutes': 60,
    },
    {
        'name': 'FrenchWeb',
        'slug': 'frenchweb',
        'url': 'https://www.frenchweb.fr',
        'feed_url': 'https://www.frenchweb.fr/feed',
        'feed_type': 'rss',
        'category': 'national',
        'crawl_frequency_minutes': 60,
    },
    {
        'name': 'Maddyness',
        'slug': 'maddyness',
        'url': 'https://www.maddyness.com',
        'feed_url': 'https://www.maddyness.com/feed',
        'feed_type': 'rss',
        'category': 'national',
        'crawl_frequency_minutes': 120,
    },
    {
        'name': 'Silicon.fr',
        'slug': 'silicon-fr',
        'url': 'https://www.silicon.fr',
        'feed_url': 'https://www.silicon.fr/feed',
        'feed_type': 'rss',
        'category': 'national',
        'crawl_frequency_minutes': 120,
    },
    {
        'name': 'Le Monde Informatique',
        'slug': 'monde-informatique',
        'url': 'https://www.lemondeinformatique.fr',
        'feed_url': 'https://www.lemondeinformatique.fr/flux-rss',
        'feed_type': 'rss',
        'category': 'national',
        'crawl_frequency_minutes': 120,
    },
    # Regional
    {
        'name': 'French Tech in the Alps',
        'slug': 'french-tech-alps',
        'url': 'https://www.ftalps.com',
        'feed_url': None,
        'feed_type': 'html_scrape',
        'crawler_class': 'sources.french_tech_alps.FrenchTechAlpsCrawler',
        'category': 'regional',
        'crawl_frequency_minutes': 360,
    },
    {
        'name': "Place Gre'net",
        'slug': 'place-grenet',
        'url': 'https://www.placegrenet.fr',
        'feed_url': None,
        'feed_type': 'html_scrape',
        'category': 'regional',
        'crawl_frequency_minutes': 360,
    },
    {
        'name': 'La Tribune AURA',
        'slug': 'tribune-aura',
        'url': 'https://www.latribune.fr/region/auvergne-rhone-alpes',
        'feed_url': None,
        'feed_type': 'html_scrape',
        'category': 'regional',
        'crawl_frequency_minutes': 360,
    },
    # Institutional
    {
        'name': 'Minalogic',
        'slug': 'minalogic',
        'url': 'https://www.minalogic.com',
        'feed_url': None,
        'feed_type': 'html_scrape',
        'crawler_class': 'sources.minalogic.MinalogicCrawler',
        'category': 'institutional',
        'crawl_frequency_minutes': 720,
    },
    {
        'name': 'CEA-Leti',
        'slug': 'cea-leti',
        'url': 'https://www.leti-cea.com',
        'feed_url': None,
        'feed_type': 'html_scrape',
        'crawler_class': 'sources.cea_leti.CeaLetiCrawler',
        'category': 'institutional',
        'crawl_frequency_minutes': 720,
    },
    {
        'name': 'STMicroelectronics Newsroom',
        'slug': 'stmicroelectronics',
        'url': 'https://newsroom.st.com',
        'feed_url': 'https://newsroom.st.com/rss',
        'feed_type': 'rss',
        'category': 'institutional',
        'crawl_frequency_minutes': 360,
    },
    {
        'name': 'ESRF',
        'slug': 'esrf',
        'url': 'https://www.esrf.fr',
        'feed_url': 'https://www.esrf.fr/rss',
        'feed_type': 'rss',
        'category': 'institutional',
        'crawl_frequency_minutes': 720,
    },
    {
        'name': 'Inria Grenoble',
        'slug': 'inria-grenoble',
        'url': 'https://www.inria.fr/fr/centre-inria-de-luniversite-grenoble-alpes',
        'feed_url': 'https://www.inria.fr/fr/flux-rss',
        'feed_type': 'rss',
        'category': 'institutional',
        'crawl_frequency_minutes': 720,
    },
    {
        'name': 'Schneider Electric Newsroom',
        'slug': 'schneider-electric',
        'url': 'https://www.se.com/ww/en/about-us/newsroom',
        'feed_url': None,
        'feed_type': 'html_scrape',
        'category': 'institutional',
        'crawl_frequency_minutes': 720,
    },
    {
        'name': 'Soitec Press Releases',
        'slug': 'soitec',
        'url': 'https://www.soitec.com/en/press-releases',
        'feed_url': None,
        'feed_type': 'html_scrape',
        'category': 'institutional',
        'crawl_frequency_minutes': 720,
    },
]


def seed():
    app = create_app()
    with app.app_context():
        for data in SOURCES:
            existing = NewsSource.query.filter_by(slug=data['slug']).first()
            if existing:
                print(f'  Skipping {data["name"]} (already exists)')
                continue
            source = NewsSource(**data)
            db.session.add(source)
            print(f'  Added: {data["name"]}')
        db.session.commit()
        print(f'\nDone. {NewsSource.query.count()} sources in database.')


if __name__ == '__main__':
    seed()
