from app.extensions import db


class SystemSetting(db.Model):
    """Key-value store for runtime-configurable system settings."""
    __tablename__ = 'system_setting'

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.String(500), nullable=False)
    description = db.Column(db.String(300))

    @classmethod
    def get(cls, key: str, default: str = '') -> str:
        row = db.session.get(cls, key)
        return row.value if row else default

    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        try:
            return int(cls.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    @classmethod
    def set(cls, key: str, value: str, description: str = None):
        row = db.session.get(cls, key)
        if row:
            row.value = value
            if description:
                row.description = description
        else:
            row = cls(key=key, value=value, description=description or '')
            db.session.add(row)

    def __repr__(self):
        return f'<Setting {self.key}={self.value}>'
