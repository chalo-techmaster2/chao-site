from flask_login import UserMixin
from werkzeug.security import generate_password_hash
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
        repair_jobs = db.relationship('RepairJob', backref='owner', lazy=True, cascade='all, delete-orphan')

    class RepairJob(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        owner_id = db.Column(db.Integer, db.ForeignKey('owner.id'), nullable=False)
        phone_model = db.Column(db.String(100), nullable=False)
        issue = db.Column(db.String(200))
        price = db.Column(db.Float, nullable=False)
        is_paid = db.Column(db.Boolean, default=False)
        is_returned = db.Column(db.Boolean, default=False)
        date_received = db.Column(db.DateTime, default=datetime.utcnow)
        payments = db.relationship('Payment', backref='repair_job', lazy=True, cascade='all, delete-orphan')

        @property
        def amount_paid(self):
            return sum(payment.amount for payment in self.payments)

        @property
        def amount_remaining(self):
            return self.price - self.amount_paid

    class Payment(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        repair_job_id = db.Column(db.Integer, db.ForeignKey('repair_job.id'), nullable=False)
        amount = db.Column(db.Float, nullable=False)
        date = db.Column(db.DateTime, default=datetime.utcnow)
        note = db.Column(db.String(200))

    return User, Owner, RepairJob, Payment
