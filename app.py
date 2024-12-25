from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, case

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///repair_shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'
db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

class Owner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    repair_jobs = db.relationship('RepairJob', backref='owner', lazy=True, cascade='all, delete-orphan')

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    repair_job_id = db.Column(db.Integer, db.ForeignKey('repair_job.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.String(200))

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

def init_db():
    with app.app_context():
        db.create_all()
        # Create default admin user if it doesn't exist
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password_hash=generate_password_hash('admin')
            )
            db.session.add(admin)
            db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    owners = Owner.query.all()
    owners_data = []
    
    total_owners = len(owners)
    active_repairs = RepairJob.query.filter_by(is_returned=False).count()
    
    # Calculate total pending payments
    pending_payments = db.session.query(
        func.sum(
            case(
                [(RepairJob.is_paid == False, RepairJob.price - func.coalesce(
                    db.session.query(func.sum(Payment.amount))
                    .filter(Payment.repair_job_id == RepairJob.id)
                    .scalar_subquery(), 
                    0
                ))],
                else_=0
            )
        )
    ).scalar() or 0

    for owner in owners:
        active_jobs = sum(1 for job in owner.repair_jobs if not job.is_returned)
        pending_amount = sum(job.amount_remaining for job in owner.repair_jobs if not job.is_paid)
        
        owners_data.append({
            'name': owner.name,
            'active_jobs': active_jobs,
            'pending_amount': pending_amount
        })

    return render_template('index.html', 
                         owners=owners_data,
                         total_owners=total_owners,
                         active_repairs=active_repairs,
                         pending_payments=pending_payments)

@app.route('/add_owner', methods=['POST'])
@login_required
def add_owner():
    name = request.form['owner_name'].strip()
    
    if not name:
        flash('Owner name cannot be empty')
        return redirect(url_for('index'))
    
    # Check if owner already exists
    if Owner.query.filter_by(name=name).first():
        flash('Owner already exists')
        return redirect(url_for('index'))
    
    owner = Owner(name=name)
    db.session.add(owner)
    db.session.commit()
    
    flash(f'Owner {name} added successfully')
    return redirect(url_for('owner_details', owner_name=name))

@app.route('/owner/<owner_name>')
@login_required
def owner_details(owner_name):
    owner = Owner.query.filter_by(name=owner_name).first_or_404()
    repair_jobs = sorted(owner.repair_jobs, key=lambda x: x.date_received, reverse=True)
    return render_template('owner_details.html', owner_name=owner_name, repair_jobs=repair_jobs)

@app.route('/edit_owner/<owner_name>', methods=['POST'])
@login_required
def edit_owner(owner_name):
    owner = Owner.query.filter_by(name=owner_name).first_or_404()
    new_name = request.form['new_name'].strip()
    
    if not new_name:
        flash('Owner name cannot be empty')
        return redirect(url_for('owner_details', owner_name=owner_name))
    
    if new_name != owner_name:
        # Check if new name already exists
        if Owner.query.filter_by(name=new_name).first():
            flash('Owner name already exists')
            return redirect(url_for('owner_details', owner_name=owner_name))
        
        owner.name = new_name
        db.session.commit()
        flash('Owner name updated successfully')
        return redirect(url_for('owner_details', owner_name=new_name))
    
    return redirect(url_for('owner_details', owner_name=owner_name))

@app.route('/add_job_to_owner/<owner_name>', methods=['POST'])
@login_required
def add_job_to_owner(owner_name):
    owner = Owner.query.filter_by(name=owner_name).first_or_404()
    phone_model = request.form['phone_model'].strip()
    issue = request.form['issue'].strip()
    price = float(request.form['price'])

    if not phone_model or not issue:
        flash('All fields are required')
        return redirect(url_for('owner_details', owner_name=owner_name))

    if price < 0:
        flash('Price cannot be negative')
        return redirect(url_for('owner_details', owner_name=owner_name))

    new_job = RepairJob(
        owner_id=owner.id,
        phone_model=phone_model,
        issue=issue,
        price=price
    )
    db.session.add(new_job)
    db.session.commit()
    
    flash(f'New repair job added for {owner_name}')
    return redirect(url_for('owner_details', owner_name=owner_name))

@app.route('/edit_job/<int:job_id>', methods=['GET', 'POST'])
@login_required
def edit_job(job_id):
    job = RepairJob.query.get_or_404(job_id)
    
    if request.method == 'POST':
        job.phone_model = request.form['phone_model'].strip()
        job.issue = request.form['issue'].strip()
        job.price = float(request.form['price'])
        
        if job.price < 0:
            flash('Price cannot be negative')
            return redirect(url_for('edit_job', job_id=job_id))
            
        db.session.commit()
        flash('Job updated successfully')
        return redirect(url_for('owner_details', owner_name=job.owner.name))
    
    return render_template('edit_job.html', job=job)

@app.route('/delete_job/<int:job_id>', methods=['POST'])
@login_required
def delete_job(job_id):
    job = RepairJob.query.get_or_404(job_id)
    owner_name = job.owner.name
    db.session.delete(job)
    db.session.commit()
    flash('Job deleted successfully')
    return redirect(url_for('owner_details', owner_name=owner_name))

@app.route('/update_status/<int:job_id>', methods=['POST'])
@login_required
def update_status(job_id):
    job = RepairJob.query.get_or_404(job_id)
    action = request.form.get('action')
    
    if action == 'returned':
        job.is_returned = not job.is_returned
    
    db.session.commit()
    return redirect(url_for('owner_details', owner_name=job.owner.name))

@app.route('/add_payment/<int:job_id>', methods=['POST'])
@login_required
def add_payment(job_id):
    job = RepairJob.query.get_or_404(job_id)
    amount = float(request.form['amount'])
    note = request.form.get('note', '').strip()

    if amount <= 0:
        flash('Payment amount must be greater than 0')
        return redirect(url_for('owner_details', owner_name=job.owner.name))

    if amount > job.amount_remaining:
        flash('Payment amount cannot exceed remaining balance')
        return redirect(url_for('owner_details', owner_name=job.owner.name))

    payment = Payment(repair_job_id=job_id, amount=amount, note=note)
    db.session.add(payment)
    
    # Update is_paid status if fully paid
    if job.amount_remaining - amount <= 0:
        job.is_paid = True
    
    db.session.commit()
    flash('Payment added successfully')
    return redirect(url_for('owner_details', owner_name=job.owner.name))

@app.route('/delete_payment/<int:payment_id>', methods=['POST'])
@login_required
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    job = payment.repair_job
    job.is_paid = False  # Reset paid status as we're removing a payment
    db.session.delete(payment)
    db.session.commit()
    flash('Payment deleted successfully')
    return redirect(url_for('owner_details', owner_name=job.owner.name))

@app.route('/delete_owner/<owner_name>', methods=['POST'])
@login_required
def delete_owner(owner_name):
    owner = Owner.query.filter_by(name=owner_name).first_or_404()
    db.session.delete(owner)  # This will cascade delete all related jobs
    db.session.commit()
    flash('Owner and all related jobs deleted successfully')
    return redirect(url_for('index'))

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
