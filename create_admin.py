from main import app, db
from models import User, Admin

def create_admin_user():
    with app.app_context():
        # 1. Create the tables if they don't exist
        db.create_all()

        # 2. Check if admin already exists to avoid duplicates
        existing_admin = User.query.filter_by(mmu_id=1001).first()
        if existing_admin:
            print("Admin user already exists!")
            return

        # 3. Create the User Record
        # We use mmu_id 1001 and password 'admin123' for testing
        new_user = User(
            mmu_id=1001,
            name="Super Admin",
            email="admin@mmu.edu.my",
            password="", # Will set hash below
            faculty="Computing",
            user_role="Admin"
        )
        new_user.set_password("admin123") # Hashes the password
        
        db.session.add(new_user)
        db.session.commit()

        # 4. Create the Admin Profile Record
        new_admin_profile = Admin(mmu_id=1001)
        db.session.add(new_admin_profile)
        db.session.commit()

        print("SUCCESS: Admin user created.")
        print("Login with MMU ID: 1001")
        print("Password: admin123")

if __name__ == "__main__":
    create_admin_user()