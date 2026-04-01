"""Seed ecosystem discovery sources, sector groups, and system settings.

Run after seed_sources.py and seed_companies.py:
    python scripts/seed_ecosystem.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.startup_source import StartupSource
from app.models.sector_group import SectorGroup
from app.models.setting import SystemSetting


# ── Ecosystem Discovery Sources ─────────────────────────────────
ECOSYSTEM_SOURCES = [
    # Startup directories
    {'name': 'Linksium Portfolio', 'url': 'https://www.linksium.fr/nos-startups', 'source_type': 'startup',
     'description': 'Grenoble tech transfer office — startup portfolio'},
    {'name': 'CEA-Leti Startup Program', 'url': 'https://www.leti-cea.fr/cea-tech/leti/Pages/innovation-industrielle/innover-avec-le-Leti/programme-startup.aspx',
     'source_type': 'startup', 'description': 'CEA-Leti spin-off program (31 startups)'},
    {'name': 'Minalogic Member Directory', 'url': 'https://www.minalogic.com/en/member-directory/',
     'source_type': 'startup', 'description': 'Minalogic tech cluster — 400+ member companies'},
    # Research labs
    {'name': 'TIMA Lab', 'url': 'https://tima.univ-grenoble-alpes.fr/laboratory', 'source_type': 'research_lab',
     'description': 'Techniques of Informatics and Microelectronics for integrated systems Architecture'},
    {'name': 'LIG Lab', 'url': 'https://www.liglab.fr/fr', 'source_type': 'research_lab',
     'description': "Laboratoire d'Informatique de Grenoble"},
    {'name': 'Spintec', 'url': 'https://www.spintec.fr/', 'source_type': 'research_lab',
     'description': 'Spintronics and Technology of Components'},
    {'name': 'GIPSA-lab', 'url': 'https://www.gipsa-lab.grenoble-inp.fr/', 'source_type': 'research_lab',
     'description': 'Signal, Image, Speech, Automation'},
    {'name': 'G2Elab', 'url': 'https://g2elab.grenoble-inp.fr/', 'source_type': 'research_lab',
     'description': 'Grenoble Electrical Engineering Lab'},
    {'name': 'Clinatec', 'url': 'https://fonds-clinatec.fr/', 'source_type': 'research_lab',
     'description': 'Biomedical research center — brain-computer interfaces'},
    {'name': 'EMBL Grenoble', 'url': 'https://www.embl.org/', 'source_type': 'research_lab',
     'description': 'European Molecular Biology Laboratory'},
    {'name': 'TIMC', 'url': 'https://www.timc.fr/', 'source_type': 'research_lab',
     'description': 'Translational and Integrative Medicine'},
    {'name': 'VERIMAG', 'url': 'https://www-verimag.imag.fr/?lang=fr', 'source_type': 'research_lab',
     'description': 'Verification, Modeling and Analysis of real-time systems'},
    {'name': 'AMIES', 'url': 'https://www.agence-maths-entreprises.fr/public/pages/index.html', 'source_type': 'research_lab',
     'description': 'Agency for Math-Enterprise Interaction'},
    {'name': 'LJK', 'url': 'https://www-ljk.imag.fr/', 'source_type': 'research_lab',
     'description': 'Laboratoire Jean Kuntzmann — applied math'},
    {'name': 'MaiMoSiNE', 'url': 'https://maimosine.fr/', 'source_type': 'research_lab',
     'description': 'Multi-scale Molecular Structure Modeling'},
    {'name': 'ILL', 'url': 'https://www.ill.eu/fr/', 'source_type': 'research_lab',
     'description': 'Institut Laue-Langevin — neutron science'},
    {'name': 'Institut Neel', 'url': 'https://neel.cnrs.fr/', 'source_type': 'research_lab',
     'description': 'CNRS condensed matter physics'},
    {'name': 'LEGI', 'url': 'https://www.legi.grenoble-inp.fr/web/?lang=fr', 'source_type': 'research_lab',
     'description': 'Geophysical & Industrial Flows'},
    {'name': 'IPAG', 'url': 'https://ipag.osug.fr/', 'source_type': 'research_lab',
     'description': 'Planetary Sciences and Astrophysics'},
    {'name': 'IGE', 'url': 'https://ige-grenoble.fr', 'source_type': 'research_lab',
     'description': 'Environmental Geosciences'},
    {'name': 'CEA-IRIG', 'url': 'https://irig.cea.fr/drf/irig/Pages/Presentation.aspx', 'source_type': 'research_lab',
     'description': 'Interdisciplinary Research Institute of Grenoble'},
]

# ── Sector Groups ────────────────────────────────────────────────
SECTOR_GROUPS = [
    ('Semiconductor', 'cpu', '#2563EB', ['semiconductor', 'chip', 'wafer', 'mems', 'ic design', 'fabricat', 'silicon'], 1),
    ('AI & Computing', 'robot', '#7C3AED', ['ai', 'machine learning', 'computing', 'processor', 'neuromorphic', 'quantum', 'digital system'], 2),
    ('Photonics & Sensors', 'eye', '#0891B2', ['photonic', 'sensor', 'lidar', 'infrared', 'optic', 'vision', 'display', 'oled', 'micro-led', 'led', 'laser', 'camera'], 3),
    ('MedTech & Health', 'heart-pulse', '#DC2626', ['medtech', 'health', 'biotech', 'medical', 'diagnostic', 'pharma', 'implant', 'therapeut'], 4),
    ('Energy & CleanTech', 'lightning-charge', '#059669', ['energy', 'cleantech', 'power', 'battery', 'climat', 'solar', 'hydrogen', 'recycl'], 5),
    ('IoT & Connectivity', 'wifi', '#F97316', ['iot', 'connected', 'rfid', 'smart city', 'telecom', 'wearable'], 6),
    ('Software & Digital', 'code-slash', '#6366F1', ['software', 'saas', 'digital', 'fintech', 'cyber', 'data', 'blockchain', 'platform', 'algorithm'], 7),
    ('Materials & Chemistry', 'droplet-half', '#A16207', ['material', 'chemistry', 'nano', 'coating', 'polymer', 'ceramic', 'glass'], 8),
    ('Research & Ecosystem', 'mortarboard', '#64748B', ['research', 'university', 'cluster', 'incubator', 'transfer', 'facilit'], 9),
]

# ── System Settings ──────────────────────────────────────────────
SETTINGS = [
    ('highlight_breakthrough_days', '7', 'Tech Breakthrough display period (days)'),
    ('highlight_research_days', '7', 'Local Research display period (days)'),
    ('highlight_investment_days', '7', 'Investment display period (days)'),
    ('highlight_event_days', '14', 'Local Event display period (days)'),
    ('crawl_daily_hour', '1', 'Daily crawl start hour (0-23)'),
    ('crawl_check_interval_hours', '6', 'Frequency check interval (hours)'),
    ('crawl_timezone', 'Europe/Paris', 'Timezone for daily crawl schedule'),
]


def seed():
    app = create_app()
    with app.app_context():
        # Ecosystem sources
        print('Ecosystem Discovery Sources:')
        for data in ECOSYSTEM_SOURCES:
            if not StartupSource.query.filter_by(url=data['url']).first():
                db.session.add(StartupSource(**data))
                print(f'  Added: {data["name"]}')
            else:
                # Fix source_type if NULL
                existing = StartupSource.query.filter_by(url=data['url']).first()
                if not existing.source_type:
                    existing.source_type = data['source_type']
                    print(f'  Fixed type: {data["name"]} -> {data["source_type"]}')
                else:
                    print(f'  Exists: {data["name"]}')

        # Sector groups
        print('\nSector Groups:')
        for name, icon, color, keywords, order in SECTOR_GROUPS:
            if not SectorGroup.query.filter_by(name=name).first():
                db.session.add(SectorGroup(name=name, icon=icon, color=color, keywords=keywords, sort_order=order))
                print(f'  Added: {name}')
            else:
                print(f'  Exists: {name}')

        # System settings
        print('\nSystem Settings:')
        for key, value, desc in SETTINGS:
            if not SystemSetting.get(key):
                SystemSetting.set(key, value, desc)
                print(f'  Added: {key} = {value}')
            else:
                print(f'  Exists: {key} = {SystemSetting.get(key)}')

        db.session.commit()
        print(f'\nDone. {StartupSource.query.count()} eco sources, '
              f'{SectorGroup.query.count()} sector groups, '
              f'{SystemSetting.query.count()} settings.')


if __name__ == '__main__':
    seed()
