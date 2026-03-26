"""Seed the database with known Grenoble-area tech companies."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slugify import slugify
from app import create_app
from app.extensions import db
from app.models.company import Company

COMPANIES = [
    {
        'name': 'STMicroelectronics',
        'aliases': ['STMicro', 'ST Microelectronics', 'ST'],
        'website': 'https://www.st.com',
        'headquarters': 'Geneva / Crolles',
        'sector': 'Semiconductor',
        'is_grenoble': True,
        'description': 'Major semiconductor company with large fabrication facility in Crolles near Grenoble.',
    },
    {
        'name': 'Schneider Electric',
        'aliases': ['Schneider'],
        'website': 'https://www.se.com',
        'headquarters': 'Rueil-Malmaison / Grenoble',
        'sector': 'Energy Management / IoT',
        'is_grenoble': True,
        'description': 'Global energy management and automation company, historically headquartered in Grenoble.',
    },
    {
        'name': 'Soitec',
        'aliases': [],
        'website': 'https://www.soitec.com',
        'headquarters': 'Bernin (Grenoble)',
        'sector': 'Semiconductor Materials',
        'is_grenoble': True,
        'description': 'SOI wafer and advanced semiconductor substrate manufacturer based near Grenoble.',
    },
    {
        'name': 'Lynred',
        'aliases': ['Sofradir'],
        'website': 'https://www.lynred.com',
        'headquarters': 'Grenoble',
        'sector': 'Infrared Detectors',
        'is_grenoble': True,
        'description': 'Infrared detector manufacturer for defense, space, and industrial applications.',
    },
    {
        'name': 'CEA-Leti',
        'aliases': ['CEA Leti', 'Leti', 'CEA'],
        'website': 'https://www.leti-cea.com',
        'headquarters': 'Grenoble',
        'sector': 'Research Institute',
        'is_grenoble': True,
        'description': 'Applied research institute for microelectronics and nanotechnology.',
    },
    {
        'name': 'Minalogic',
        'aliases': [],
        'website': 'https://www.minalogic.com',
        'headquarters': 'Grenoble',
        'sector': 'Tech Cluster',
        'is_grenoble': True,
        'description': 'Digital technology and semiconductor cluster in the Grenoble area.',
    },
    {
        'name': 'ESRF',
        'aliases': ['European Synchrotron'],
        'website': 'https://www.esrf.fr',
        'headquarters': 'Grenoble',
        'sector': 'Research Facility',
        'is_grenoble': True,
        'description': 'European Synchrotron Radiation Facility, world-leading light source.',
    },
    {
        'name': 'Inria',
        'aliases': ['INRIA'],
        'website': 'https://www.inria.fr',
        'headquarters': 'Grenoble (center)',
        'sector': 'Research Institute',
        'is_grenoble': True,
        'description': 'French national research institute for computer science and applied mathematics.',
    },
    {
        'name': 'ILL',
        'aliases': ['Institut Laue-Langevin'],
        'website': 'https://www.ill.eu',
        'headquarters': 'Grenoble',
        'sector': 'Research Facility',
        'is_grenoble': True,
        'description': 'International neutron research facility.',
    },
    {
        'name': 'Grenoble INP - UGA',
        'aliases': ['Grenoble INP', 'UGA'],
        'website': 'https://www.grenoble-inp.fr',
        'headquarters': 'Grenoble',
        'sector': 'University',
        'is_grenoble': True,
        'description': 'Engineering school and university, part of Universit\u00e9 Grenoble Alpes.',
    },
    {
        'name': 'Capgemini',
        'aliases': [],
        'website': 'https://www.capgemini.com',
        'headquarters': 'Paris (Grenoble office)',
        'sector': 'IT Services',
        'is_grenoble': True,
        'description': 'Major IT services company with significant Grenoble presence.',
    },
    {
        'name': 'Hewlett Packard Enterprise',
        'aliases': ['HPE', 'HP'],
        'website': 'https://www.hpe.com',
        'headquarters': 'Houston (Grenoble R&D)',
        'sector': 'Enterprise IT',
        'is_grenoble': True,
        'description': 'Major tech company with R&D center in Grenoble (formerly HP Labs).',
    },
    {
        'name': 'Allegro DVT',
        'aliases': ['Allegro'],
        'website': 'https://www.allegrodvt.com',
        'headquarters': 'Grenoble',
        'sector': 'Semiconductor IP',
        'is_grenoble': True,
        'description': 'Video codec IP and semiconductor design company.',
    },
]


def seed():
    app = create_app()
    with app.app_context():
        for data in COMPANIES:
            slug = slugify(data['name'])
            existing = Company.query.filter_by(slug=slug).first()
            if existing:
                print(f'  Skipping {data["name"]} (already exists)')
                continue
            company = Company(slug=slug, **data)
            db.session.add(company)
            print(f'  Added: {data["name"]}')
        db.session.commit()
        print(f'\nDone. {Company.query.count()} companies in database.')


if __name__ == '__main__':
    seed()
