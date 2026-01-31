from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime

db = SQLAlchemy()
bcrypt = Bcrypt()

# --- EXISTING USER TABLES (Do not change) ---
class User(db.Model):
    __tablename__ = 'user'
    mmu_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    faculty = db.Column(db.String(100), nullable=False)
    user_role = db.Column(db.String(25), nullable=False)
    profile_image = db.Column(db.String(20), nullable=False, default='default.jpg')
    phone_number = db.Column(db.String(20), nullable=True)

    # Relationships
    admin_profile = db.relationship('Admin', backref='user_info', uselist=False, cascade="all, delete-orphan")
    researcher_profile = db.relationship('Researcher', backref='user_info', uselist=False, cascade="all, delete-orphan")
    reviewer_profile = db.relationship('Reviewer', backref='user_info', uselist=False, cascade="all, delete-orphan")
    hod_profile = db.relationship('HOD', backref='user_info', uselist=False, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

class Admin(db.Model):
    __tablename__ = 'admin'
    admin_id = db.Column(db.Integer, primary_key=True)
    mmu_id = db.Column(db.Integer, db.ForeignKey('user.mmu_id'), nullable=False)

class Researcher(db.Model):
    __tablename__ = 'researcher'
    researcher_id = db.Column(db.Integer, primary_key=True)
    mmu_id = db.Column(db.Integer, db.ForeignKey('user.mmu_id'), nullable=False)
    # Link to proposals
    proposals = db.relationship('Proposal', backref='researcher', lazy=True)

class Reviewer(db.Model):
    __tablename__ = 'reviewer'
    reviewer_id = db.Column(db.Integer, primary_key=True)
    mmu_id = db.Column(db.Integer, db.ForeignKey('user.mmu_id'), nullable=False)

class HOD(db.Model):
    __tablename__ = 'hod'
    hod_id = db.Column(db.Integer, primary_key=True)
    mmu_id = db.Column(db.Integer, db.ForeignKey('user.mmu_id'), nullable=False)

# --- NEW TABLES FOR PROPOSAL MANAGEMENT ---

# Based on Data Dictionary 3.2.13
class GrantCycle(db.Model):
    __tablename__ = 'grant_cycle'
    cycle_id = db.Column(db.Integer, primary_key=True)
    cycle_name = db.Column(db.String(50), nullable=False)
    faculty = db.Column(db.String(100), nullable=False) # You requested filtering by faculty
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_open = db.Column(db.Boolean, default=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.admin_id'), nullable=False)
    
    # Relationship to proposals submitted in this cycle
    proposals = db.relationship('Proposal', backref='cycle', lazy=True)

# Based on Data Dictionary 3.2.6 (Expanded for Assignment logic)
class Proposal(db.Model):
    __tablename__ = 'proposal'
    proposal_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    requested_budget = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Submitted") # Submitted, Under Review, Approved, Rejected
    submission_date = db.Column(db.Date, default=datetime.utcnow)
    document_file = db.Column(db.String(255), nullable=True) # To store the PDF filename
    
    # Keys
    researcher_id = db.Column(db.Integer, db.ForeignKey('researcher.researcher_id'), nullable=False)
    cycle_id = db.Column(db.Integer, db.ForeignKey('grant_cycle.cycle_id'), nullable=False)
    
    # Assignments (Directly linking for simpler "Assign Evaluators" logic)
    assigned_reviewer_id = db.Column(db.Integer, db.ForeignKey('reviewer.reviewer_id'), nullable=True)
    assigned_hod_id = db.Column(db.Integer, db.ForeignKey('hod.hod_id'), nullable=True)

    # Relationships for accessing details
    reviewer = db.relationship('Reviewer', foreign_keys=[assigned_reviewer_id])
    hod = db.relationship('HOD', foreign_keys=[assigned_hod_id])
    deadlines = db.relationship('Deadline', backref='proposal', cascade="all, delete-orphan")

# Based on Data Dictionary 3.2.11
class Deadline(db.Model):
    __tablename__ = 'deadline'
    deadline_id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('proposal.proposal_id'), nullable=False)
    deadline_type = db.Column(db.String(30), nullable=False) # "Reviewer", "HOD", "Final Submission"
    due_date = db.Column(db.Date, nullable=False)