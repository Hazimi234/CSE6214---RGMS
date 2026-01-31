import os
import secrets
from flask import Flask, redirect, url_for, render_template, request, session, flash
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from datetime import datetime
from models import (
    db,
    User,
    Admin,
    Researcher,
    Reviewer,
    HOD,
    GrantCycle,
    Proposal,
    Deadline,
    Notification,
    Faculty,
    ResearchArea,
)

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# Database & Upload Config
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
    basedir, "database.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Folder to save images
app.config["UPLOAD_FOLDER"] = os.path.join(basedir, "static/profile_pics")

# Folder for Proposal Documents (PDFs)
app.config["UPLOAD_FOLDER_DOCS"] = os.path.join(basedir, "static/proposal_docs")
app.config["ALLOWED_EXTENSIONS"] = {"pdf", "docx", "doc"}


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


def save_document(form_file):
    # Generates a random name for the document to avoid clashes
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_file.filename)
    doc_fn = random_hex + f_ext
    doc_path = os.path.join(app.config["UPLOAD_FOLDER_DOCS"], doc_fn)
    form_file.save(doc_path)
    return doc_fn


db.init_app(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)


# --- Helper Function to Save Images ---
def save_picture(form_picture):
    # Create a random hex name to prevent duplicate filenames
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.config["UPLOAD_FOLDER"], picture_fn)

    # Save the file
    form_picture.save(picture_path)
    return picture_fn


# --- Helper Function for Profile Updates (Reduces code repetition) ---
def update_user_profile(user, form, files):
    # 1. Update Basic Info
    user.name = form["name"]
    user.email = form["email"]
    user.phone_number = form["phone_number"]

    # 2. Handle Image Upload
    if "profile_pic" in files:
        file = files["profile_pic"]
        if file.filename != "":
            picture_file = save_picture(file)
            user.profile_image = picture_file

    # 3. Handle Password Change
    new_password = form["new_password"]
    confirm_password = form["confirm_password"]

    if new_password:
        if new_password != confirm_password:
            flash("Error: New password and Confirmation do not match!", "error")
            return False  # Failed
        elif user.check_password(new_password):
            flash(
                "Error: New password cannot be the same as your current password.",
                "error",
            )
            return False  # Failed
        else:
            user.set_password(new_password)
            flash("Password successfully changed.", "success")

    try:
        db.session.commit()
        flash("Profile details updated successfully!", "success")
        return True
    except:
        db.session.rollback()
        flash("Error updating profile. Email might be taken.", "error")
        return False


# --- HELPER: Send Notification ---
def send_notification(recipient_id, message, link=None, sender_id=None):
    notif = Notification(
        recipient_id=recipient_id, sender_id=sender_id, message=message, link=link
    )
    db.session.add(notif)
    db.session.commit()


# --- CONTEXT PROCESSOR ---
# This makes the 'unread_count' variable available in ALL templates (for the Bell icon)
@app.context_processor
def inject_notifications():
    if "user_id" in session:
        unread = Notification.query.filter_by(
            recipient_id=session["user_id"], is_read=False
        ).count()
        return dict(unread_notifications=unread)
    return dict(unread_notifications=0)


# --- Routes ---


@app.route("/")
def main_login():
    return render_template("main_login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main_login"))


# ==========================================
# NEW: NOTIFICATION ROUTES
# ==========================================
# 1. UPDATE: View List (Do NOT mark as read automatically anymore)
@app.route("/notifications")
def view_notifications():
    if "user_id" not in session:
        return redirect(url_for("main_login"))

    user_id = session["user_id"]

    # Get notifications (Newest first)
    notifs = (
        Notification.query.filter_by(recipient_id=user_id)
        .order_by(Notification.timestamp.desc())
        .all()
    )

    # NOTE: I removed the code that set n.is_read = True here.
    # Now they stay unread until clicked.

    return render_template(
        "notifications.html", notifications=notifs, user=User.query.get(user_id)
    )


# 2. NEW: Handle Click (Mark ONE as Read -> Redirect)
@app.route("/notifications/click/<int:notif_id>")
def click_notification(notif_id):
    if "user_id" not in session:
        return redirect(url_for("main_login"))

    notif = Notification.query.get_or_404(notif_id)

    # Security Check
    if notif.recipient_id != session["user_id"]:
        return redirect(url_for("view_notifications"))

    # Mark specific notification as read
    notif.is_read = True
    db.session.commit()

    # Redirect to the target link (e.g., Proposal Details)
    if notif.link:
        return redirect(notif.link)
    else:
        return redirect(url_for("view_notifications"))


# 3. NEW: Mark ALL as Read button logic
@app.route("/notifications/mark_all_read")
def mark_all_notifications_read():
    if "user_id" not in session:
        return redirect(url_for("main_login"))

    user_id = session["user_id"]

    # Find all unread messages for this user
    unread = Notification.query.filter_by(recipient_id=user_id, is_read=False).all()
    for n in unread:
        n.is_read = True

    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("view_notifications"))


# ==========================================
# 1. ADMIN ROUTES
# ==========================================
@app.route("/admin/login", methods=["POST", "GET"])
def admin_login():
    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        password = request.form["password"]
        user = User.query.filter_by(mmu_id=mmu_id, user_role="Admin").first()

        if user and user.check_password(password):
            session["user_id"] = user.mmu_id
            session["role"] = "Admin"
            session["name"] = user.name
            # Store profile pic in session for easy access
            session["profile_image"] = user.profile_image
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid Admin credentials.", "error")

    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    # Refresh user data from DB to get the latest image
    user = User.query.get(session["user_id"])

    stats = {"pending_proposals": 12, "active_grants": 45, "total_users": 150}
    return render_template("admin_dashboard.html", stats=stats, user=user)


@app.route("/admin/profile", methods=["GET", "POST"])
def admin_profile():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    user = User.query.get(session["user_id"])

    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("admin_profile"))

    return render_template("admin_profile.html", user=user)


# ==========================================
# USER MANAGEMENT (ADMIN ONLY)
# ==========================================


# 1. VIEW & FILTER USERS
@app.route("/admin/users")
def admin_user_management():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    # Get Filter Parameters
    search_query = request.args.get("search", "")
    filter_role = request.args.get("role", "")
    filter_faculty = request.args.get("faculty", "")

    # Pagination Parameters (Default to Page 1, 8 items per page)
    page = request.args.get("page", 1, type=int)
    per_page = 8

    # Start Query
    query = User.query
    faculties_list = Faculty.query.all()

    # Apply Filters
    if search_query:
        query = query.filter(User.name.ilike(f"%{search_query}%"))
    if filter_role:
        query = query.filter_by(user_role=filter_role)
    if filter_faculty:
        query = query.filter_by(faculty=filter_faculty)

    # Execute Query with Pagination
    # error_out=False means if we go to a page that doesn't exist, it returns empty list instead of 404
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items  # Get the list of users for the current page

    return render_template(
        "admin_user_management.html",
        users=users,
        pagination=pagination,
        user=User.query.get(session["user_id"]),
        faculties=faculties_list,
    )


# 2. CREATE NEW USER
@app.route("/admin/users/create", methods=["GET", "POST"])
def admin_create_user():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        faculty = request.form["faculty"]
        role = request.form["role"]

        # Check if user exists
        if User.query.filter_by(mmu_id=mmu_id).first():
            flash(f"Error: User with MMU ID {mmu_id} already exists.", "error")
            return redirect(url_for("admin_create_user"))

        if User.query.filter_by(email=email).first():
            flash(f"Error: Email {email} is already taken.", "error")
            return redirect(url_for("admin_create_user"))

        # Create User Object
        new_user = User(
            mmu_id=mmu_id, name=name, email=email, faculty=faculty, user_role=role
        )
        new_user.set_password(password)
        db.session.add(new_user)

        # Create Child Table Entry based on Role
        if role == "Researcher":
            db.session.add(Researcher(mmu_id=mmu_id))
        elif role == "Reviewer":
            db.session.add(Reviewer(mmu_id=mmu_id))
        elif role == "HOD":
            db.session.add(HOD(mmu_id=mmu_id))

        try:
            db.session.commit()
            flash(f"User {name} ({role}) created successfully!", "success")
            return redirect(url_for("admin_user_management"))
        except:
            db.session.rollback()
            flash("Database Error: Could not create user.", "error")

    return render_template(
        "admin_create_user.html",
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )


# 3. EDIT USER
@app.route("/admin/users/edit/<int:user_id>", methods=["GET", "POST"])
def admin_edit_user(user_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    target_user = User.query.get_or_404(user_id)

    # Restriction: Admin cannot edit other Admins (or themselves via this route)
    if target_user.user_role == "Admin":
        flash("Action Not Allowed: You cannot edit Admin accounts.", "error")
        return redirect(url_for("admin_user_management"))

    if request.method == "POST":
        target_user.name = request.form["name"]
        target_user.email = request.form["email"]
        target_user.phone_number = request.form["phone_number"]
        target_user.faculty = request.form["faculty"]  # Admin allowed to change this

        # Password update (optional)
        new_password = request.form["password"]
        if new_password:
            target_user.set_password(new_password)

        try:
            db.session.commit()
            flash("User details updated successfully.", "success")
            return redirect(url_for("admin_user_management"))
        except:
            flash("Error updating user. Email might be duplicate.", "error")

    return render_template(
        "admin_edit_user.html",
        target_user=target_user,
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )


# 4. DELETE USER
@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    user_to_delete = User.query.get_or_404(user_id)

    # Restriction: Cannot delete Admins
    if user_to_delete.user_role == "Admin":
        flash("Critical Error: You cannot delete an Admin account.", "error")
    else:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash("User deleted successfully.", "success")

    return redirect(url_for("admin_user_management"))


# ==========================================
# PROPOSAL MANAGEMENT (ADMIN)
# ==========================================


# 1. LIST ALL PROPOSALS
@app.route("/admin/proposals")
def admin_proposal_management():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    # Filters
    search_query = request.args.get("search", "")
    filter_faculty = request.args.get("faculty", "")

    page = request.args.get("page", 1, type=int)
    per_page = 8

    query = Proposal.query.join(Researcher).join(
        User
    )  # Join to access User.name and User.faculty

    if search_query:
        query = query.filter(Proposal.title.ilike(f"%{search_query}%"))
    if filter_faculty:
        query = query.filter(User.faculty == filter_faculty)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    proposals = pagination.items

    return render_template(
        "admin_proposal_management.html",
        proposals=proposals,
        pagination=pagination,
        user=User.query.get(session["user_id"]),
    )


# 2. OPEN PROPOSAL SUBMISSION (Create Cycle)
@app.route("/admin/proposals/open", methods=["GET", "POST"])
def admin_open_cycle():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        cycle_name = request.form["cycle_name"]
        faculty = request.form["faculty"]
        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()

        # Validation
        if end_date <= start_date:
            flash("Error: End Date must be after Start Date.", "error")
        else:
            # Create Cycle
            # Need Admin ID
            admin = Admin.query.filter_by(mmu_id=session["user_id"]).first()
            new_cycle = GrantCycle(
                cycle_name=cycle_name,
                faculty=faculty,
                start_date=start_date,
                end_date=end_date,
                admin_id=admin.admin_id,
            )
            db.session.add(new_cycle)
            db.session.commit()
            flash(f"Submission Cycle '{cycle_name}' Opened for {faculty}!", "success")
            return redirect(url_for("admin_proposal_management"))

    return render_template(
        "admin_open_cycle.html",
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )


# 3. VIEW PROPOSAL DETAILS
@app.route("/admin/proposals/view/<int:proposal_id>")
def admin_view_proposal(proposal_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    proposal = Proposal.query.get_or_404(proposal_id)

    # Fetch existing deadlines if any
    reviewer_deadline = Deadline.query.filter_by(
        proposal_id=proposal.proposal_id, deadline_type="Reviewer"
    ).first()
    hod_deadline = Deadline.query.filter_by(
        proposal_id=proposal.proposal_id, deadline_type="HOD"
    ).first()
    final_deadline = Deadline.query.filter_by(
        proposal_id=proposal.proposal_id, deadline_type="Final Submission"
    ).first()

    return render_template(
        "admin_view_proposal.html",
        proposal=proposal,
        user=User.query.get(session["user_id"]),
        reviewer_deadline=reviewer_deadline,
        hod_deadline=hod_deadline,
        final_deadline=final_deadline,
    )


# 4. ASSIGN EVALUATORS & SET DEADLINES
@app.route("/admin/proposals/assign/<int:proposal_id>", methods=["GET", "POST"])
def admin_assign_evaluators(proposal_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    proposal = Proposal.query.get_or_404(proposal_id)
    researcher_faculty = proposal.researcher.user_info.faculty

    if request.method == "POST":
        # 1. Assign Reviewer
        reviewer_id = request.form.get("reviewer_id")
        if reviewer_id:
            proposal.assigned_reviewer_id = reviewer_id

        # 2. Assign HOD
        hod_id = request.form.get("hod_id")
        if hod_id:
            proposal.assigned_hod_id = hod_id

        # 3. Set Deadlines
        rev_date = request.form.get("reviewer_deadline")
        hod_date = request.form.get("hod_deadline")

        if rev_date:
            # Update or Create Deadline entry
            dl = Deadline.query.filter_by(
                proposal_id=proposal.proposal_id, deadline_type="Reviewer"
            ).first()
            if not dl:
                dl = Deadline(
                    proposal_id=proposal.proposal_id, deadline_type="Reviewer"
                )
            dl.due_date = datetime.strptime(rev_date, "%Y-%m-%d").date()
            db.session.add(dl)

        if hod_date:
            dl = Deadline.query.filter_by(
                proposal_id=proposal.proposal_id, deadline_type="HOD"
            ).first()
            if not dl:
                dl = Deadline(proposal_id=proposal.proposal_id, deadline_type="HOD")
            dl.due_date = datetime.strptime(hod_date, "%Y-%m-%d").date()
            db.session.add(dl)

        proposal.status = "Under Review"
        db.session.commit()
        flash("Evaluators assigned and deadlines set successfully.", "success")
        return redirect(
            url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
        )

    # GET: Fetch potential reviewers/HODs from the SAME faculty
    # Using a join to filter by User.faculty
    reviewers = (
        Reviewer.query.join(User).filter(User.faculty == researcher_faculty).all()
    )
    hods = HOD.query.join(User).filter(User.faculty == researcher_faculty).all()

    return render_template(
        "admin_assign_evaluators.html",
        proposal=proposal,
        reviewers=reviewers,
        hods=hods,
        user=User.query.get(session["user_id"]),
    )


# 5. SET FINAL RESEARCH DEADLINE
@app.route("/admin/proposals/final_deadline/<int:proposal_id>", methods=["POST"])
def admin_set_final_deadline(proposal_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    proposal = Proposal.query.get_or_404(proposal_id)

    # Requirement: Cannot set final deadline if evaluators not assigned
    if not proposal.assigned_reviewer_id or not proposal.assigned_hod_id:
        flash(
            "Error: You must assign Evaluators before setting the Final Research Deadline.",
            "error",
        )
        return redirect(
            url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
        )

    final_date = request.form["final_deadline"]
    if final_date:
        dl = Deadline.query.filter_by(
            proposal_id=proposal.proposal_id, deadline_type="Final Submission"
        ).first()
        if not dl:
            dl = Deadline(
                proposal_id=proposal.proposal_id, deadline_type="Final Submission"
            )
        dl.due_date = datetime.strptime(final_date, "%Y-%m-%d").date()
        db.session.add(dl)
        db.session.commit()
        flash("Final Research Submission Deadline Set!", "success")

    return redirect(url_for("admin_view_proposal", proposal_id=proposal.proposal_id))


# ==========================================
# MAINTAIN SYSTEM DATA (Faculties & Research Areas)
# ==========================================


@app.route("/admin/system_data", methods=["GET", "POST"])
def admin_system_data():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        # Handle Adding New Data
        type_added = request.form.get("type")  # 'faculty' or 'area'
        name_added = request.form.get("name").strip()

        if type_added == "faculty":
            if Faculty.query.filter_by(name=name_added).first():
                flash(f"Error: Faculty '{name_added}' already exists.", "error")
            else:
                db.session.add(Faculty(name=name_added))
                db.session.commit()
                flash(f"Faculty '{name_added}' added successfully.", "success")

        elif type_added == "area":
            if ResearchArea.query.filter_by(name=name_added).first():
                flash(f"Error: Research Area '{name_added}' already exists.", "error")
            else:
                db.session.add(ResearchArea(name=name_added))
                db.session.commit()
                flash(f"Research Area '{name_added}' added successfully.", "success")

        return redirect(url_for("admin_system_data"))

    # Fetch lists to display
    faculties = Faculty.query.all()
    areas = ResearchArea.query.all()

    return render_template(
        "admin_system_data.html",
        faculties=faculties,
        areas=areas,
        user=User.query.get(session["user_id"]),
    )


@app.route("/admin/system_data/edit", methods=["POST"])
def admin_edit_system_data():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    item_type = request.form.get("type")
    item_id = request.form.get("id")
    new_name = request.form.get("name").strip()

    if item_type == "faculty":
        item = Faculty.query.get(item_id)
        item.name = new_name
    elif item_type == "area":
        item = ResearchArea.query.get(item_id)
        item.name = new_name

    db.session.commit()
    flash("Item updated successfully.", "success")
    return redirect(url_for("admin_system_data"))


# ==========================================
# 2. RESEARCHER ROUTES
# ==========================================
@app.route("/researcher/login", methods=["POST", "GET"])
def researcher_login():
    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        password = request.form["password"]
        user = User.query.filter_by(mmu_id=mmu_id, user_role="Researcher").first()

        if user and user.check_password(password):
            session["user_id"] = user.mmu_id
            session["role"] = "Researcher"
            session["name"] = user.name
            return redirect(url_for("researcher_dashboard"))
        else:
            flash("Invalid Researcher credentials.", "error")

    return render_template("researcher_login.html")


@app.route("/researcher/dashboard")
def researcher_dashboard():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))

    user = User.query.get(session["user_id"])  # Get latest user data
    stats = {"my_proposals": 3, "active_grants": 1, "pending_reports": 2}
    return render_template("researcher_dashboard.html", stats=stats, user=user)


@app.route("/researcher/profile", methods=["GET", "POST"])
def researcher_profile():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))

    user = User.query.get(session["user_id"])

    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("researcher_profile"))

    return render_template("researcher_profile.html", user=user)


# ==========================================
# RESEARCHER: SUBMIT PROPOSAL
# ==========================================


# 1. LIST OPEN CYCLES (Where Researcher chooses what to apply for)
@app.route("/researcher/apply")
def researcher_apply_list():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))

    today = datetime.now().date()
    user = User.query.get(session["user_id"])

    # Filter Logic
    filter_faculty = request.args.get("faculty", "")

    query = GrantCycle.query.filter(
        GrantCycle.start_date <= today,
        GrantCycle.end_date >= today,
        GrantCycle.is_open == True,
    )

    # If user selects a specific faculty, apply filter. Otherwise, show ALL.
    if filter_faculty:
        query = query.filter(GrantCycle.faculty == filter_faculty)

    active_cycles = query.all()

    return render_template(
        "researcher_apply_list.html",
        cycles=active_cycles,
        user=user,
        faculties=Faculty.query.all(),
    )


# 2. SUBMISSION FORM
@app.route("/researcher/apply/<int:cycle_id>", methods=["GET", "POST"])
def researcher_submit_form(cycle_id):
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))

    cycle = GrantCycle.query.get_or_404(cycle_id)
    user = User.query.get(session["user_id"])
    researcher = Researcher.query.filter_by(mmu_id=user.mmu_id).first()

    if request.method == "POST":
        title = request.form["title"]
        research_area = request.form["research_area"]
        budget = request.form["budget"]

        # FILE UPLOAD LOGIC
        document_filename = None
        if "proposal_file" in request.files:
            file = request.files["proposal_file"]
            if file and allowed_file(file.filename):
                document_filename = save_document(file)
            else:
                flash("Error: Invalid file type. Please upload PDF or DOCX.", "error")
                return redirect(request.url)
        else:
            flash("Error: You must upload a proposal document.", "error")
            return redirect(request.url)

        # Create Proposal Record
        new_proposal = Proposal(
            title=request.form["title"],
            research_area=request.form["research_area"],
            requested_budget=request.form["budget"],
            status="Submitted",
            researcher_id=Researcher.query.filter_by(mmu_id=session["user_id"])
            .first()
            .researcher_id,
            cycle_id=cycle.cycle_id,
            document_file=document_filename,
        )
        db.session.add(new_proposal)
        db.session.commit()

        # --- NEW: NOTIFY ADMIN ---
        # Find the Admin who created this cycle (or just the first super admin)
        admin_recipient = User.query.filter_by(user_role="Admin").first()
        if admin_recipient:
            msg = f"New Proposal Submitted: '{new_proposal.title}' by {user.name}."
            link = url_for("admin_view_proposal", proposal_id=new_proposal.proposal_id)
            send_notification(admin_recipient.mmu_id, msg, link, sender_id=user.mmu_id)

        flash("Proposal submitted! Admin has been notified.", "success")
        return redirect(url_for("researcher_dashboard"))

    return render_template(
        "researcher_submit_form.html",
        cycle=cycle,
        user=user,
        research_areas=ResearchArea.query.all(),
    )


# ==========================================
# 3. REVIEWER ROUTES
# ==========================================
@app.route("/reviewer/login", methods=["POST", "GET"])
def reviewer_login():
    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        password = request.form["password"]
        user = User.query.filter_by(mmu_id=mmu_id, user_role="Reviewer").first()

        if user and user.check_password(password):
            session["user_id"] = user.mmu_id
            session["role"] = "Reviewer"
            session["name"] = user.name
            return redirect(url_for("reviewer_dashboard"))
        else:
            flash("Invalid Reviewer credentials.", "error")

    return render_template("reviewer_login.html")


@app.route("/reviewer/dashboard")
def reviewer_dashboard():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer_login"))

    user = User.query.get(session["user_id"])
    stats = {"pending_reviews": 5, "completed_reviews": 12}
    return render_template("reviewer_dashboard.html", stats=stats, user=user)


@app.route("/reviewer/profile", methods=["GET", "POST"])
def reviewer_profile():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer_login"))

    user = User.query.get(session["user_id"])

    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("reviewer_profile"))

    return render_template("reviewer_profile.html", user=user)


# ==========================================
# 4. HOD ROUTES
# ==========================================
@app.route("/hod/login", methods=["POST", "GET"])
def hod_login():
    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        password = request.form["password"]
        user = User.query.filter_by(mmu_id=mmu_id, user_role="HOD").first()

        if user and user.check_password(password):
            session["user_id"] = user.mmu_id
            session["role"] = "HOD"
            session["name"] = user.name
            return redirect(url_for("hod_dashboard"))
        else:
            flash("Invalid HOD credentials.", "error")

    return render_template("hod_login.html")


@app.route("/hod/dashboard")
def hod_dashboard():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))

    user = User.query.get(session["user_id"])
    stats = {"approvals_pending": 8, "budget_allocated": "RM 50,000"}
    return render_template("hod_dashboard.html", stats=stats, user=user)


@app.route("/hod/profile", methods=["GET", "POST"])
def hod_profile():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))

    user = User.query.get(session["user_id"])

    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("hod_profile"))

    return render_template("hod_profile.html", user=user)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
