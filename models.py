from flask_login import UserMixin
from datetime import datetime

def init_db(db):
    class User(UserMixin, db.Model):
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(80), unique=True, nullable=False)
        password_hash = db.Column(db.String(120), nullable=False)

    class Owner(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), unique=True, nullable=False)
        date_added = db.Column(db.DateTime, default=datetime.utcnow)
        jobs = db.relationship('RepairJob', backref='owner', lazy=True, cascade='all, delete-orphan')

    class RepairJob(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        owner_id = db.Column(db.Integer, db.ForeignKey('owner.id'), nullable=False)
        device = db.Column(db.String(100), nullable=False)
        issue = db.Column(db.Text, nullable=False)
        total_amount = db.Column(db.Float, nullable=False)
        paid_amount = db.Column(db.Float, default=0.0)
        status = db.Column(db.String(20), default='Pending')  # Pending, In Progress, Completed
        date_added = db.Column(db.DateTime, default=datetime.utcnow)
        date_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    return User, Owner, RepairJob, None
