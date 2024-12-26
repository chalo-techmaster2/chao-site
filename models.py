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
        jobs = db.relationship('RepairJob', backref='owner', lazy=True, cascade='all, delete-orphan')
        date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    class RepairJob(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        owner_id = db.Column(db.Integer, db.ForeignKey('owner.id'), nullable=False)
        device = db.Column(db.String(100), nullable=False)
        issue = db.Column(db.Text, nullable=False)
        total_amount = db.Column(db.Float, nullable=False)
        paid_amount = db.Column(db.Float, nullable=False, default=0)
        status = db.Column(db.String(20), nullable=False, default='Pending')  # Pending, In Progress, Completed
        date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        date_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
        payments = db.relationship('Payment', backref='repair_job', lazy=True, cascade='all, delete-orphan')

    class Payment(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        repair_job_id = db.Column(db.Integer, db.ForeignKey('repair_job.id'), nullable=False)
        amount = db.Column(db.Float, nullable=False)
        date_created = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    return User, Owner, RepairJob, Payment
