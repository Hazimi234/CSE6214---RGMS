from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt

db = SQLAlchemy()
bcrypt = Bcrypt()

class User(db.Model):
    __tablename__ = 'user'
    mmu_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    
    # NEW: Phone Number Column
    phone_number = db.Column(db.String(20), nullable=True)
    
    password = db.Column(db.String(100), nullable=False)
    faculty = db.Column(db.String(100), nullable=False)
    user_role = db.Column(db.String(25), nullable=False)
    profile_image = db.Column(db.String(20), nullable=False, default='default.jpg')

    # Relationships
    admin_profile = db.relationship('Admin', backref='user_info', uselist=False, cascade="all, delete-orphan")
    researcher_profile = db.relationship('Researcher', backref='user_info', uselist=False, cascade="all, delete-orphan")
    reviewer_profile = db.relationship('Reviewer', backref='user_info', uselist=False, cascade="all, delete-orphan")
    hod_profile = db.relationship('HOD', backref='user_info', uselist=False, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

# (Keep Admin, Researcher, Reviewer, HOD classes exactly the same as before...)
class Admin(db.Model):
    __tablename__ = 'admin'
    admin_id = db.Column(db.Integer, primary_key=True)
    mmu_id = db.Column(db.Integer, db.ForeignKey('user.mmu_id'), nullable=False)

class Researcher(db.Model):
    __tablename__ = 'researcher'
    researcher_id = db.Column(db.Integer, primary_key=True)
    mmu_id = db.Column(db.Integer, db.ForeignKey('user.mmu_id'), nullable=False)

class Reviewer(db.Model):
    __tablename__ = 'reviewer'
    reviewer_id = db.Column(db.Integer, primary_key=True)
    mmu_id = db.Column(db.Integer, db.ForeignKey('user.mmu_id'), nullable=False)

class HOD(db.Model):
    __tablename__ = 'hod'
    hod_id = db.Column(db.Integer, primary_key=True)
    mmu_id = db.Column(db.Integer, db.ForeignKey('user.mmu_id'), nullable=False)