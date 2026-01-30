from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()

class User(db.Model):
    __tablename__ = 'user'
    # Based on PDF Data Dictionary 3.2.1
    mmu_id = db.Column(db.Integer, primary_key=True)  # MMU ID is the Primary Key
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    faculty = db.Column(db.String(100), nullable=False)
    user_role = db.Column(db.String(25), nullable=False)  # Admin, Researcher, Reviewer, HOD
    
    # Relationships (for future use based on PDF)
    admin_profile = db.relationship('Admin', backref='user_info', uselist=False, cascade="all, delete-orphan")
    # researcher_profile = ... (to be added by teammates)

    def __repr__(self):
        return f'<User {self.name} - {self.user_role}>'

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

class Admin(db.Model):
    __tablename__ = 'admin'
    # Based on PDF Data Dictionary 3.2.5
    admin_id = db.Column(db.Integer, primary_key=True)
    mmu_id = db.Column(db.Integer, db.ForeignKey('user.mmu_id'), nullable=False)
    
    # Add other Admin specific fields here if needed later