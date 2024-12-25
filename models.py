from flask_login import UserMixin
from werkzeug.security import generate_password_hash
from datetime import datetime

def init_db(db):
    class User(UserMixin, db.Model):
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(80), unique=True, nullable=False)
        password_hash = db.Column(db.String(120), nullable=False)

    class RepairOrder(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        customer_name = db.Column(db.String(100), nullable=False)
        phone_model = db.Column(db.String(100), nullable=False)
        issue_description = db.Column(db.Text, nullable=False)
        date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        status = db.Column(db.String(20), nullable=False, default='Pending')
        price = db.Column(db.Float, nullable=False)
        amount_paid = db.Column(db.Float, nullable=False, default=0.0)
        image_path = db.Column(db.String(200))

        @property
        def amount_remaining(self):
            return self.price - self.amount_paid

    return User, RepairOrder
