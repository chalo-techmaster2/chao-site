from app import create_app, db, User
from werkzeug.security import generate_password_hash

def init_database():
    app = create_app()
    with app.app_context():
        # Create all tables
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
    print("Database initialized successfully")

if __name__ == '__main__':
    init_database()
