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
    faculty = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_open = db.Column(db.Boolean, default=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('admin.admin_id'), nullable=False)
    
    # KEEP THIS ONE: It creates the 'cycle' backref for Proposals
    proposals = db.relationship('Proposal', backref='cycle', lazy=True)

# Based on Data Dictionary 3.2.6 (Expanded for Assignment logic)
class Proposal(db.Model):
    __tablename__ = 'proposal'
    proposal_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    research_area = db.Column(db.String(100), nullable=False, default="General") # Keep this new column
    requested_budget = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="Submitted")
    submission_date = db.Column(db.Date, default=datetime.utcnow)
    document_file = db.Column(db.String(100), nullable=True)
    
    researcher_id = db.Column(db.Integer, db.ForeignKey('researcher.researcher_id'), nullable=False)
    cycle_id = db.Column(db.Integer, db.ForeignKey('grant_cycle.cycle_id'), nullable=False)
    
    assigned_reviewer_id = db.Column(db.Integer, db.ForeignKey('reviewer.reviewer_id'), nullable=True)
    assigned_hod_id = db.Column(db.Integer, db.ForeignKey('hod.hod_id'), nullable=True)

    approved_amount = db.Column(db.Float, default=0.0) # How much HOD actually gives

    # Relations
    reviewer = db.relationship('Reviewer', foreign_keys=[assigned_reviewer_id])
    hod = db.relationship('HOD', foreign_keys=[assigned_hod_id])
    deadlines = db.relationship('Deadline', backref='proposal', cascade="all, delete-orphan")

# For "Monitor and Validate Progress Reports"
class ProgressReport(db.Model):
    __tablename__ = 'progress_report'
    report_id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('proposal.proposal_id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False) # Project updates
    financial_usage = db.Column(db.Float, nullable=False) # Money spent so far
    document_file = db.Column(db.String(100), nullable=True) # PDF attachment
    status = db.Column(db.String(50), default="Submitted") # "Validated", "Requires Revision"
    submission_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    proposal = db.relationship('Proposal', backref='reports')

# Based on Data Dictionary 3.2.11
class Deadline(db.Model):
    __tablename__ = 'deadline'
    deadline_id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('proposal.proposal_id'), nullable=False)
    deadline_type = db.Column(db.String(30), nullable=False) # "Reviewer", "HOD", "Final Submission"
    due_date = db.Column(db.Date, nullable=False)

class Notification(db.Model):
    __tablename__ = 'notification'
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.mmu_id'), nullable=False) # Who gets the message
    sender_id = db.Column(db.Integer, db.ForeignKey('user.mmu_id'), nullable=True) # Who sent it (System or User)
    message = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255), nullable=True) # URL to click (e.g., view proposal)
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='notifications_received')
    sender = db.relationship('User', foreign_keys=[sender_id], backref='notifications_sent')

# NEW TABLE: List of Faculties
class Faculty(db.Model):
    __tablename__ = 'faculty_list'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return self.name

# NEW TABLE: List of Research Areas
class ResearchArea(db.Model):
    __tablename__ = 'research_area_list'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    def __repr__(self):
        return self.name