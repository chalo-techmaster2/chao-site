import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
from datetime import datetime

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///repair_shop.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-this')

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    # Import models and initialize them
    from models import init_db
    global User, Owner, RepairJob, Payment
    User, Owner, RepairJob, Payment = init_db(db)

    with app.app_context():
        # Create tables
        db.create_all()
        
        # Create default admin user if it doesn't exist
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password_hash=generate_password_hash('admin')
            )
            db.session.add(admin)
            try:
                db.session.commit()
                print("Created default admin user")
            except Exception as e:
                db.session.rollback()
                print(f"Error creating admin user: {e}")

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.route('/')
    @login_required
    def index():
        owners = Owner.query.all()
        owners_data = []
        
        total_owners = len(owners)
        active_repairs = RepairJob.query.filter_by(status='In Progress').count()
        
        # Calculate total pending payments
        pending_payments = db.session.query(
            func.sum(RepairJob.total_amount - RepairJob.paid_amount)
        ).filter(RepairJob.status != 'Completed').scalar() or 0

        for owner in owners:
            active_jobs = sum(1 for job in owner.jobs if job.status != 'Completed')
            pending_amount = sum(job.total_amount - job.paid_amount for job in owner.jobs if job.status != 'Completed')
            
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

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            user = User.query.filter_by(username=username).first()
            
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
            else:
                flash('Invalid username or password')
        
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

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
        
        # Calculate owner stats
        total_amount = sum(job.total_amount for job in owner.jobs)
        pending_amount = sum(job.total_amount - job.paid_amount for job in owner.jobs if job.status != 'Completed')
        active_jobs = sum(1 for job in owner.jobs if job.status != 'Completed')
        
        owner_data = {
            'name': owner.name,
            'jobs': owner.jobs,
            'total_amount': total_amount,
            'pending_amount': pending_amount,
            'active_jobs': active_jobs
        }
        
        return render_template('owner_details.html', owner=owner_data)

    @app.route('/add_job/<owner_name>', methods=['POST'])
    @login_required
    def add_job(owner_name):
        owner = Owner.query.filter_by(name=owner_name).first_or_404()
        device = request.form['device'].strip()
        issue = request.form['issue'].strip()
        total_amount = float(request.form['total_amount'])

        if not device or not issue:
            flash('All fields are required')
            return redirect(url_for('owner_details', owner_name=owner_name))

        if total_amount < 0:
            flash('Amount cannot be negative')
            return redirect(url_for('owner_details', owner_name=owner_name))

        new_job = RepairJob(
            owner_id=owner.id,
            device=device,
            issue=issue,
            total_amount=total_amount,
            paid_amount=0,
            status='Pending'
        )
        db.session.add(new_job)
        db.session.commit()
        
        flash(f'New repair job added for {owner_name}')
        return redirect(url_for('owner_details', owner_name=owner_name))

    @app.route('/edit_job/<owner_name>/<int:job_id>', methods=['GET', 'POST'])
    @login_required
    def edit_job(owner_name, job_id):
        owner = Owner.query.filter_by(name=owner_name).first_or_404()
        job = RepairJob.query.get_or_404(job_id)
        
        if request.method == 'POST':
            job.device = request.form['device'].strip()
            job.issue = request.form['issue'].strip()
            job.total_amount = float(request.form['total_amount'])
            job.status = request.form['status']
            
            db.session.commit()
            flash('Job updated successfully')
            return redirect(url_for('owner_details', owner_name=owner_name))
        
        return render_template('edit_job.html', owner=owner, job=job)

    @app.route('/add_payment/<owner_name>/<int:job_id>', methods=['POST'])
    @login_required
    def add_payment(owner_name, job_id):
        job = RepairJob.query.get_or_404(job_id)
        amount = float(request.form['amount'])

        if amount <= 0:
            flash('Payment amount must be greater than 0')
            return redirect(url_for('owner_details', owner_name=owner_name))

        remaining = job.total_amount - job.paid_amount
        if amount > remaining:
            flash('Payment amount cannot exceed remaining balance')
            return redirect(url_for('owner_details', owner_name=owner_name))

        job.paid_amount += amount
        
        # Update status if fully paid
        if job.paid_amount >= job.total_amount:
            job.status = 'Completed'
        
        db.session.commit()
        flash('Payment added successfully')
        return redirect(url_for('owner_details', owner_name=owner_name))

    @app.route('/delete_owner/<owner_name>', methods=['POST'])
    @login_required
    def delete_owner(owner_name):
        owner = Owner.query.filter_by(name=owner_name).first_or_404()
        db.session.delete(owner)
        db.session.commit()
        flash(f'Owner {owner_name} deleted successfully')
        return redirect(url_for('index'))

    return app

# Create the Flask application instance
app = create_app()
