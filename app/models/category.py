from app.extensions import db


class Category(db.Model):
    __tablename__ = 'category'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(100), nullable=False, unique=True)
    name_zh = db.Column(db.String(100))
    name_en = db.Column(db.String(100))

    def __repr__(self):
        return f'<Category {self.name}>'
