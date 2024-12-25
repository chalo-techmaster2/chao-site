import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, case
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

    # File upload settings
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', os.path.join(os.getcwd(), 'user_files'))

    # Create upload folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
        repair_jobs = sorted(owner.repair_jobs, key=lambda x: x.date_received, reverse=True)
        return render_template('owner_details.html', owner=owner, repair_jobs=repair_jobs)

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

    @app.route('/static/<path:filename>')
    def static_files(filename):
        return send_from_directory('static', filename)

    return app

# Create the Flask application instance
app = create_app()
