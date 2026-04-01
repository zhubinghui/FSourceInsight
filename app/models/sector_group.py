from app.extensions import db


class SectorGroup(db.Model):
    """Configurable sector groups for the ecosystem map view."""
    __tablename__ = 'sector_group'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    icon = db.Column(db.String(50), nullable=False, default='grid')  # Bootstrap icon name
    color = db.Column(db.String(20), nullable=False, default='#64748B')  # Hex color
    keywords = db.Column(db.JSON)  # ["keyword1", "keyword2"] for auto-classification
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return f'<SectorGroup {self.name}>'

    @classmethod
    def all_ordered(cls):
        return cls.query.order_by(cls.sort_order, cls.name).all()

    @classmethod
    def as_dict(cls):
        """Return {name: {icon, color, keywords}} for compatibility."""
        result = {}
        for sg in cls.all_ordered():
            result[sg.name] = {
                'icon': sg.icon,
                'color': sg.color,
                'keywords': sg.keywords or [],
            }
        return result
