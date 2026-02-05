import os
import secrets
import json
from datetime import datetime
from flask import Flask, redirect, url_for, render_template, request, session, flash
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from sqlalchemy import func

# Import Database Models
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
    Budget,
    Grant,
)

# ============================================================================
#                          APP CONFIGURATION & SETUP
# ============================================================================
app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Change this in production!

# Database Configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
    basedir, "database.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# File Upload Configurations
app.config["UPLOAD_FOLDER"] = os.path.join(basedir, "static/profile_pics")
app.config["UPLOAD_FOLDER_DOCS"] = os.path.join(basedir, "static/proposal_docs")
app.config["ALLOWED_EXTENSIONS"] = {"pdf", "docx", "doc"}

# Initialize Extensions
db.init_app(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)


# ========================================================================
#                            HELPER FUNCTIONS
# ========================================================================


def allowed_file(filename):
    """Checks if a file has an allowed extension (PDF, DOCX)."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


def save_document(form_file):
    """Saves a proposal document with a random hex name to avoid filename collisions."""
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_file.filename)
    doc_fn = random_hex + f_ext
    doc_path = os.path.join(app.config["UPLOAD_FOLDER_DOCS"], doc_fn)
    form_file.save(doc_path)
    return doc_fn


def save_picture(form_picture):
    """Saves a profile picture with a random hex name."""
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.config["UPLOAD_FOLDER"], picture_fn)
    form_picture.save(picture_path)
    return picture_fn


def update_user_profile(user, form, files):
    """
    Handles common profile update logic for all user roles.
    Updates name, email, phone, profile pic, and password.
    Returns True if successful, False if failed.
    """
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
            return False
        elif user.check_password(new_password):
            flash(
                "Error: New password cannot be the same as your current password.",
                "error",
            )
            return False
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


def send_notification(recipient_id, message, link=None, sender_id=None):
    """Creates a new notification record in the database."""
    notif = Notification(
        recipient_id=recipient_id, sender_id=sender_id, message=message, link=link
    )
    db.session.add(notif)
    db.session.commit()


# =============================================================================
#                              CONTEXT PROCESSORS
# =============================================================================


@app.context_processor
def inject_notifications():
    """
    Runs before every template render.
    Makes 'unread_notifications' available globally for the bell icon badge.
    """
    if "user_id" in session:
        unread = Notification.query.filter_by(
            recipient_id=session["user_id"], is_read=False
        ).count()
        return dict(unread_notifications=unread)
    return dict(unread_notifications=0)


# ==============================================================================
#                        GENERAL ROUTES (Auth & Notifications)
# ==============================================================================


@app.route("/")
def main_login():
    """Landing page / Main Login selection."""
    return render_template("main_login.html")


@app.route("/logout")
def logout():
    """Clears session and redirects to main login."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main_login"))


# --- Notification System ---


@app.route("/notifications")
def view_notifications():
    """Lists all notifications for the logged-in user."""
    if "user_id" not in session:
        return redirect(url_for("main_login"))
    user_id = session["user_id"]

    # Fetch notifications (Newest first)
    notifs = (
        Notification.query.filter_by(recipient_id=user_id)
        .order_by(Notification.timestamp.desc())
        .all()
    )
    return render_template(
        "notifications.html", notifications=notifs, user=User.query.get(user_id)
    )


@app.route("/notifications/click/<int:notif_id>")
def click_notification(notif_id):
    """Marks a single notification as read and redirects to the link."""
    if "user_id" not in session:
        return redirect(url_for("main_login"))
    notif = Notification.query.get_or_404(notif_id)

    # Security: Ensure user owns this notification
    if notif.recipient_id != session["user_id"]:
        return redirect(url_for("view_notifications"))

    notif.is_read = True
    db.session.commit()

    return (
        redirect(notif.link) if notif.link else redirect(url_for("view_notifications"))
    )


@app.route("/notifications/mark_all_read")
def mark_all_notifications_read():
    """Marks all unread notifications as read at once."""
    if "user_id" not in session:
        return redirect(url_for("main_login"))
    user_id = session["user_id"]

    unread = Notification.query.filter_by(recipient_id=user_id, is_read=False).all()
    for n in unread:
        n.is_read = True

    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("view_notifications"))


# ================================================================================
#                                   ADMIN MODULE
# ================================================================================


# --- Admin Auth & Dashboard ---
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
            session["profile_image"] = user.profile_image
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid Admin credentials.", "error")
    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    user = User.query.get(session["user_id"])

    # 1. Budget Stats
    total_budget_in = db.session.query(func.sum(Budget.amount)).scalar() or 0.0
    total_grants_out = db.session.query(func.sum(Grant.grant_amount)).scalar() or 0.0
    remaining_balance = total_budget_in - total_grants_out

    # Avoid division by zero for progress bar
    budget_percent = (
        (total_grants_out / total_budget_in * 100) if total_budget_in > 0 else 0
    )

    # 2. Proposal Stats
    stats = {
        "total_cycles": GrantCycle.query.count(),
        "open_cycles": GrantCycle.query.filter_by(is_open=True).count(),
        "submitted": Proposal.query.filter_by(status="Submitted").count(),
        "under_review": Proposal.query.filter_by(status="Under Review").count(),
        "approved": Proposal.query.filter_by(status="Approved").count(),
        "budget_percent": round(budget_percent, 1),
        "total_budget": total_budget_in,
        "remaining": remaining_balance,
    }

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


# --- User Management ---
@app.route("/admin/users")
def admin_user_management():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    # Filtering logic
    search_query = request.args.get("search", "")
    filter_role = request.args.get("role", "")
    filter_faculty = request.args.get("faculty", "")

    page = request.args.get("page", 1, type=int)
    per_page = 8

    query = User.query
    if search_query:
        query = query.filter(User.name.ilike(f"%{search_query}%"))
    if filter_role:
        query = query.filter_by(user_role=filter_role)
    if filter_faculty:
        query = query.filter_by(faculty=filter_faculty)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "admin_user_management.html",
        users=pagination.items,
        pagination=pagination,
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),  # Pass dynamic faculty list
    )


@app.route("/admin/users/create", methods=["GET", "POST"])
def admin_create_user():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        # Extract form data
        mmu_id = request.form["mmu_id"]
        role = request.form["role"]

        # Validation: Check duplicates
        if User.query.filter_by(mmu_id=mmu_id).first():
            flash(f"Error: User with MMU ID {mmu_id} already exists.", "error")
            return redirect(url_for("admin_create_user"))
        if User.query.filter_by(email=request.form["email"]).first():
            flash(f"Error: Email is already taken.", "error")
            return redirect(url_for("admin_create_user"))

        # Create User & Child Table Entry
        new_user = User(
            mmu_id=mmu_id,
            name=request.form["name"],
            email=request.form["email"],
            faculty=request.form["faculty"],
            user_role=role,
        )
        new_user.set_password(request.form["password"])
        db.session.add(new_user)

        if role == "Researcher":
            db.session.add(Researcher(mmu_id=mmu_id))
        elif role == "Reviewer":
            db.session.add(Reviewer(mmu_id=mmu_id))
        elif role == "HOD":
            db.session.add(HOD(mmu_id=mmu_id))

        try:
            db.session.commit()
            flash(f"User {new_user.name} created!", "success")
            return redirect(url_for("admin_user_management"))
        except:
            db.session.rollback()
            flash("Database Error.", "error")

    return render_template(
        "admin_create_user.html",
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )


@app.route("/admin/users/edit/<string:user_id>", methods=["GET", "POST"])
def admin_edit_user(user_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    target_user = User.query.get_or_404(user_id)

    if target_user.user_role == "Admin":
        flash("Action Not Allowed: You cannot edit Admin accounts.", "error")
        return redirect(url_for("admin_user_management"))

    if request.method == "POST":
        # Basic Update
        target_user.name = request.form["name"]
        target_user.email = request.form["email"]
        target_user.phone_number = request.form["phone_number"]
        target_user.faculty = request.form["faculty"]

        if request.form["password"]:
            target_user.set_password(request.form["password"])

        db.session.commit()
        flash("User details updated.", "success")
        return redirect(url_for("admin_user_management"))

    return render_template(
        "admin_edit_user.html",
        target_user=target_user,
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )


@app.route("/admin/users/delete/<string:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    user_to_delete = User.query.get_or_404(user_id)

    if user_to_delete.user_role == "Admin":
        flash("Critical Error: You cannot delete an Admin account.", "error")
    else:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash("User deleted successfully.", "success")
    return redirect(url_for("admin_user_management"))


# --- Proposal Management ---
# ======================================================
# LEVEL 1: LIST ALL GRANT CYCLES (The "Folders")
# ======================================================
@app.route("/admin/proposals")
def admin_proposal_management():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    search_query = request.args.get("search", "")
    filter_faculty = request.args.get("faculty", "")

    # Pagination Setup
    page = request.args.get("page", 1, type=int)
    per_page = 6  # Show 6 cycles per page

    query = GrantCycle.query

    if search_query:
        query = query.filter(GrantCycle.cycle_name.ilike(f"%{search_query}%"))
    if filter_faculty:
        query = query.filter(GrantCycle.faculty == filter_faculty)

    # Use .paginate() instead of .all()
    pagination = query.order_by(GrantCycle.start_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    cycles = pagination.items

    return render_template(
        "admin_proposal_management.html",
        cycles=cycles,
        pagination=pagination,  # Pass pagination object
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )


# ======================================================
# LEVEL 2: LIST PROPOSALS INSIDE A CYCLE (The "Files")
# ======================================================
@app.route("/admin/proposals/cycle/<int:cycle_id>")
def admin_view_cycle_proposals(cycle_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    cycle = GrantCycle.query.get_or_404(cycle_id)

    search_proposal = request.args.get("search", "")
    filter_area = request.args.get("area", "")

    # Pagination Setup
    page = request.args.get("page", 1, type=int)
    per_page = 8  # Show 8 proposals per page

    query = Proposal.query.filter_by(cycle_id=cycle.cycle_id)

    if search_proposal:
        query = query.filter(Proposal.title.ilike(f"%{search_proposal}%"))
    if filter_area:
        query = query.filter(Proposal.research_area == filter_area)

    # Use .paginate()
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    proposals = pagination.items

    return render_template(
        "admin_cycle_proposals.html",
        cycle=cycle,
        proposals=proposals,
        pagination=pagination,  # Pass pagination object
        user=User.query.get(session["user_id"]),
        research_areas=ResearchArea.query.all(),
    )


@app.route("/admin/proposals/open", methods=["GET", "POST"])
def admin_open_cycle():
    """Route to open a new Grant Cycle for researchers to submit proposals."""
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()

        if end_date <= start_date:
            flash("Error: End Date must be after Start Date.", "error")
        else:
            admin = Admin.query.filter_by(mmu_id=session["user_id"]).first()
            new_cycle = GrantCycle(
                cycle_name=request.form["cycle_name"],
                faculty=request.form["faculty"],
                start_date=start_date,
                end_date=end_date,
                admin_id=admin.admin_id,
            )
            db.session.add(new_cycle)
            db.session.commit()
            flash("Submission Cycle Opened!", "success")
            return redirect(url_for("admin_proposal_management"))

    return render_template(
        "admin_open_cycle.html",
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )


@app.route("/admin/proposals/view/<int:proposal_id>")
def admin_view_proposal(proposal_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    proposal = Proposal.query.get_or_404(proposal_id)

    # Fetch existing deadlines for display
    deadlines = {
        "Reviewer": Deadline.query.filter_by(
            proposal_id=proposal.proposal_id, deadline_type="Reviewer"
        ).first(),
        "HOD": Deadline.query.filter_by(
            proposal_id=proposal.proposal_id, deadline_type="HOD"
        ).first(),
        "Final": Deadline.query.filter_by(
            proposal_id=proposal.proposal_id, deadline_type="Final Submission"
        ).first(),
    }

    return render_template(
        "admin_view_proposal.html",
        proposal=proposal,
        user=User.query.get(session["user_id"]),
        reviewer_deadline=deadlines["Reviewer"],
        hod_deadline=deadlines["HOD"],
        final_deadline=deadlines["Final"],
    )


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

            # --- NEW: NOTIFY REVIEWER ---
            reviewer_user = Reviewer.query.get(reviewer_id).user_info
            msg = (
                f"New Assignment: You have been assigned to screen '{proposal.title}'."
            )
            link = url_for("reviewer_view_proposals")
            send_notification(
                reviewer_user.mmu_id, msg, link, sender_id=session["user_id"]
            )
            # -----------------------------

        # 2. Assign HOD
        hod_id = request.form.get("hod_id")
        if hod_id:
            proposal.assigned_hod_id = hod_id

            # --- NEW: NOTIFY HOD ---
            hod_user = HOD.query.get(hod_id).user_info
            msg = (
                f"New Assignment: You have been assigned to approve '{proposal.title}'."
            )
            link = url_for("hod_dashboard")  # Or hod proposal list
            send_notification(hod_user.mmu_id, msg, link, sender_id=session["user_id"])
            # -----------------------------

        # 3. Set Deadlines (Keep existing code)
        rev_date = request.form.get("reviewer_deadline")
        hod_date = request.form.get("hod_deadline")

        if rev_date:
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
        flash("Evaluators assigned and notified successfully.", "success")
        return redirect(
            url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
        )

    # GET Logic (Keep existing)
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


@app.route("/admin/proposals/final_deadline/<int:proposal_id>", methods=["POST"])
def admin_set_final_deadline(proposal_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    proposal = Proposal.query.get_or_404(proposal_id)

    if not proposal.assigned_reviewer_id or not proposal.assigned_hod_id:
        flash("Error: Assign Evaluators first.", "error")
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
        flash("Final Deadline Set!", "success")

    return redirect(url_for("admin_view_proposal", proposal_id=proposal.proposal_id))


# ------------ Budget Tracking ----------------- #
@app.route("/admin/budget", methods=["GET", "POST"])
def admin_budget_tracking():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    # 1. HANDLE ADDING BUDGET (Money In)
    if request.method == "POST":
        try:
            amount = float(request.form["amount"])
            description = request.form["description"]

            # Create Budget Record
            new_budget = Budget(
                amount=amount, description=description, admin_id=session["user_id"]
            )
            db.session.add(new_budget)
            db.session.commit()
            flash(
                f"Successfully added RM {amount:,.2f} to the system budget.", "success"
            )
        except ValueError:
            flash("Error: Invalid amount entered.", "error")
        return redirect(url_for("admin_budget_tracking"))

    # 2. CALCULATE STATS
    # Sum of all Budget records (Money In)
    total_budget_in = db.session.query(func.sum(Budget.amount)).scalar() or 0.0

    # Sum of all Grant records (Money Out/Awarded)
    total_grants_out = db.session.query(func.sum(Grant.grant_amount)).scalar() or 0.0

    current_balance = total_budget_in - total_grants_out

    # 3. FETCH HISTORY
    budget_history = Budget.query.order_by(Budget.created_at.desc()).all()

    # Fetch Allocated Grants
    active_grants = Grant.query.order_by(Grant.award_date.desc()).all()

    return render_template(
        "admin_budget_tracking.html",
        user=User.query.get(session["user_id"]),
        total_fund=total_budget_in,
        total_allocated=total_grants_out,
        current_balance=current_balance,
        budget_history=budget_history,
        active_grants=active_grants,
    )


# 1. EDIT BUDGET ROUTE
@app.route("/admin/budget/edit/<int:budget_id>", methods=["POST"])
def admin_edit_budget(budget_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    budget = Budget.query.get_or_404(budget_id)

    # Secure: Check if the current admin owns this entry (Optional, but good practice)
    if budget.admin_id != session["user_id"]:
        flash("Error: You can only edit funds you added.", "error")
        return redirect(url_for("admin_budget_tracking"))

    try:
        budget.amount = float(request.form["amount"])
        budget.description = request.form["description"]
        db.session.commit()
        flash("Budget entry updated successfully.", "success")
    except ValueError:
        flash("Error: Invalid amount.", "error")

    return redirect(url_for("admin_budget_tracking"))


# 2. DELETE BUDGET ROUTE
@app.route("/admin/budget/delete/<int:budget_id>", methods=["POST"])
def admin_delete_budget(budget_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    budget = Budget.query.get_or_404(budget_id)

    db.session.delete(budget)
    db.session.commit()

    flash("Budget entry deleted.", "success")
    return redirect(url_for("admin_budget_tracking"))


# --- System Data Management ---
@app.route("/admin/system_data", methods=["GET", "POST"])
def admin_system_data():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        type_added = request.form.get("type")
        name_added = request.form.get("name").strip()

        # Check existing and Add
        if type_added == "faculty":
            if Faculty.query.filter_by(name=name_added).first():
                flash(f"Error: Faculty '{name_added}' exists.", "error")
            else:
                db.session.add(Faculty(name=name_added))
                db.session.commit()
                flash("Faculty added.", "success")
        elif type_added == "area":
            if ResearchArea.query.filter_by(name=name_added).first():
                flash(f"Error: Area '{name_added}' exists.", "error")
            else:
                db.session.add(ResearchArea(name=name_added))
                db.session.commit()
                flash("Research Area added.", "success")

        return redirect(url_for("admin_system_data"))

    return render_template(
        "admin_system_data.html",
        faculties=Faculty.query.all(),
        areas=ResearchArea.query.all(),
        user=User.query.get(session["user_id"]),
    )


@app.route("/admin/system_data/edit", methods=["POST"])
def admin_edit_system_data():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    item_id = request.form.get("id")
    new_name = request.form.get("name").strip()

    if request.form.get("type") == "faculty":
        Faculty.query.get(item_id).name = new_name
    elif request.form.get("type") == "area":
        ResearchArea.query.get(item_id).name = new_name

    db.session.commit()
    flash("Item updated.", "success")
    return redirect(url_for("admin_system_data"))


# ===============================================================================
#                                 RESEARCHER MODULE
# ===============================================================================


@app.route("/researcher/login", methods=["POST", "GET"])
def researcher_login():
    if request.method == "POST":
        user = User.query.filter_by(
            mmu_id=request.form["mmu_id"], user_role="Researcher"
        ).first()
        if user and user.check_password(request.form["password"]):
            session["user_id"] = user.mmu_id
            session["role"] = "Researcher"
            return redirect(url_for("researcher_dashboard"))
        else:
            flash("Invalid credentials.", "error")
    return render_template("researcher_login.html")


@app.route("/researcher/dashboard")
def researcher_dashboard():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))
    stats = {"my_proposals": 3, "active_grants": 1, "pending_reports": 2}
    return render_template(
        "researcher_dashboard.html",
        stats=stats,
        user=User.query.get(session["user_id"]),
    )


@app.route("/researcher/profile", methods=["GET", "POST"])
def researcher_profile():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("researcher_profile"))
    return render_template("researcher_profile.html", user=user)


@app.route("/researcher/apply")
def researcher_apply_list():
    """Lists open grant cycles available for application."""
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))
    today = datetime.now().date()

    query = GrantCycle.query.filter(
        GrantCycle.start_date <= today,
        GrantCycle.end_date >= today,
        GrantCycle.is_open == True,
    )
    if request.args.get("faculty"):
        query = query.filter(GrantCycle.faculty == request.args.get("faculty"))

    return render_template(
        "researcher_apply_list.html",
        cycles=query.all(),
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )


@app.route("/researcher/apply/<int:cycle_id>", methods=["GET", "POST"])
def researcher_submit_form(cycle_id):
    """Handles proposal submission and file upload."""
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))
    cycle = GrantCycle.query.get_or_404(cycle_id)
    user = User.query.get(session["user_id"])

    # If the researcher's faculty doesn't match the grant's faculty, block access.
    if user.faculty != cycle.faculty:
        flash(
            f"Access Denied: You are not eligible for {cycle.faculty} grants.", "error"
        )
        return redirect(url_for("researcher_apply_list"))

    if request.method == "POST":
        # Handle File Upload
        if "proposal_file" not in request.files:
            flash("Error: Document required.", "error")
            return redirect(request.url)
        file = request.files["proposal_file"]
        if not (file and allowed_file(file.filename)):
            flash("Error: Invalid file type.", "error")
            return redirect(request.url)

        doc_filename = save_document(file)

        # Create Proposal
        new_proposal = Proposal(
            title=request.form["title"],
            research_area=request.form["research_area"],
            requested_budget=request.form["budget"],
            status="Submitted",
            researcher_id=Researcher.query.filter_by(mmu_id=session["user_id"])
            .first()
            .researcher_id,
            cycle_id=cycle.cycle_id,
            document_file=doc_filename,
        )
        db.session.add(new_proposal)
        db.session.commit()

        # Notify Admin
        admin = User.query.filter_by(user_role="Admin").first()
        if admin:
            msg = f"New Proposal: '{new_proposal.title}' by {user.name}."
            link = url_for("admin_view_proposal", proposal_id=new_proposal.proposal_id)
            send_notification(admin.mmu_id, msg, link, sender_id=user.mmu_id)

        flash("Proposal submitted!", "success")
        return redirect(url_for("researcher_dashboard"))

    return render_template(
        "researcher_submit_form.html",
        cycle=cycle,
        user=user,
        research_areas=ResearchArea.query.all(),
    )


# =====================================================================
#                            REVIEWER MODULE
# =====================================================================


@app.route("/reviewer/login", methods=["POST", "GET"])
def reviewer_login():
    if request.method == "POST":
        user = User.query.filter_by(
            mmu_id=request.form["mmu_id"], user_role="Reviewer"
        ).first()
        if user and user.check_password(request.form["password"]):
            session["user_id"] = user.mmu_id
            session["role"] = "Reviewer"
            return redirect(url_for("reviewer_dashboard"))
        else:
            flash("Invalid credentials.", "error")
    return render_template("reviewer_login.html")


@app.route("/reviewer/dashboard")
def reviewer_dashboard():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer_login"))
    return render_template(
        "reviewer_dashboard.html",
        stats={"pending_reviews": 5},
        user=User.query.get(session["user_id"]),
    )


@app.route("/reviewer/profile", methods=["GET", "POST"])
def reviewer_profile():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer_login"))
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("reviewer_profile"))
    return render_template("reviewer_profile.html", user=user)


@app.route("/reviewer/proposals")
def reviewer_view_proposals():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer_login"))

    user = User.query.get(session["user_id"])
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()
    
    if not reviewer_profile:
        flash("Error: Reviewer profile not found.", "error")
        return redirect(url_for("reviewer_dashboard"))

    # Pagination & Search
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "")
    per_page = 8

    # --- FIX: Only show proposals that need SCREENING ---
    query = Proposal.query.filter(
        Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
        Proposal.status.in_(["Submitted", "Under Review"]) # <--- THIS FILTER WAS MISSING
    )

    if search:
        query = query.filter(Proposal.title.ilike(f"%{search}%"))
    if request.args.get("area"):
        query = query.filter(Proposal.research_area == request.args.get("area"))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "reviewer_proposals.html",
        proposals=pagination.items,
        pagination=pagination,
        user=user,
        research_areas=ResearchArea.query.all(),
    )


@app.route("/reviewer/screen/<int:proposal_id>", methods=["GET", "POST"])
def reviewer_screen_proposal(proposal_id):
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer_login"))

    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])

    # Security Check
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()
    if (
        not reviewer_profile
        or proposal.assigned_reviewer_id != reviewer_profile.reviewer_id
    ):
        flash("Access Denied.", "error")
        return redirect(url_for("reviewer_dashboard"))

    if request.method == "POST":
        decision = request.form.get("decision")

        # 1. ELIGIBLE -> Move to Evaluation
        if decision == "eligible":
            proposal.status = "Screening Passed"
            flash("Screening Passed. You may now evaluate the proposal.", "success")

        # 2. NOT ELIGIBLE -> STRICT REJECTION (As requested)
        elif decision == "not_eligible":
            proposal.status = "Rejected"  # Final state

            # Notify Researcher
            msg = f"Update: Your proposal '{proposal.title}' was rejected during screening."
            link = url_for("researcher_dashboard")
            send_notification(
                proposal.researcher.user_info.mmu_id, msg, link, sender_id=user.mmu_id
            )

            flash("Proposal Rejected. Researcher notified.", "error")

        # 3. NOT INTERESTED -> Decline Task
        elif decision == "not_interested":
            proposal.assigned_reviewer_id = None
            proposal.status = "Submitted"

            # Notify Admin
            admin = User.query.filter_by(user_role="Admin").first()
            if admin:
                msg = (
                    f"Task Declined: Reviewer {user.name} declined '{proposal.title}'."
                )
                link = url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
                send_notification(admin.mmu_id, msg, link, sender_id=user.mmu_id)

            flash("Task declined.", "info")

        db.session.commit()
        return redirect(url_for("reviewer_view_proposals"))

    return render_template(
        "reviewer_screen_proposal.html", proposal=proposal, user=user
    )


@app.route("/reviewer/evaluation_list")
def reviewer_evaluation_list():
    if session.get("role") != "Reviewer": return redirect(url_for("reviewer_login"))
    
    user = User.query.get(session["user_id"])
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()

    # 1. PENDING EVALUATIONS (Pagination for the main work queue)
    page = request.args.get('page', 1, type=int)
    search = request.args.get("search", "")

    query_pending = Proposal.query.filter(
        Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
        Proposal.status == "Screening Passed" 
    )

    if search:
        query_pending = query_pending.filter(Proposal.title.ilike(f"%{search}%"))

    pagination = query_pending.paginate(page=page, per_page=8, error_out=False)

    # 2. COMPLETED HISTORY (New Query)
    # Logic: Assigned to me + Has a Score (means evaluation was submitted)
    history_proposals = Proposal.query.filter(
        Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
        Proposal.review_score != None
    ).order_by(Proposal.submission_date.desc()).all()

    return render_template(
        "reviewer_evaluation_list.html",
        proposals=pagination.items,
        pagination=pagination,
        history=history_proposals, # Pass history to template
        user=user,
        research_areas=ResearchArea.query.all()
    )


@app.route("/reviewer/evaluate/<int:proposal_id>", methods=["GET", "POST"])
def reviewer_evaluate_proposal(proposal_id):
    if session.get("role") != "Reviewer": return redirect(url_for("reviewer_login"))
    
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])

    # CHECK STATUS
    # Case A: Ready for Review (Normal)
    if proposal.status == "Screening Passed":
        readonly = False
    
    # Case B: Already Reviewed (Read-Only Mode)
    elif proposal.review_score is not None:
        readonly = True
        # If accessing completed review, we strictly view it, no POST allowed unless we want to block it.
        # But let's just use the readonly flag to hide buttons in template.
    
    # Case C: Invalid Access
    else:
        flash("Error: This proposal cannot be evaluated at this stage.", "error")
        return redirect(url_for("reviewer_view_proposals"))

    # LOAD SAVED ANSWERS (From Draft OR Final Score)
    saved_answers = {}
    
    if proposal.review_draft:
        # Load draft if exists
        try: saved_answers = json.loads(proposal.review_draft)
        except: saved_answers = {}

    if request.method == "POST":
        action = request.form.get("action")  # Check which button was clicked

        # 1. COLLECT FORM DATA
        data = {}
        total_score = 0
        all_answered = True

        for i in range(1, 21):
            val = request.form.get(f"q{i}")
            data[f"q{i}"] = val  # Save the specific answer (e.g., "5")

            if val:
                total_score += int(val)
            else:
                all_answered = False  # Found a missing answer

        feedback = request.form.get("feedback")
        data["feedback"] = feedback

        # ---------------------------------------------------------
        # ACTION: SAVE DRAFT
        # ---------------------------------------------------------
        if action == "save_draft":
            proposal.review_draft = json.dumps(data)  # Save to DB as text
            db.session.commit()
            flash("Draft saved successfully. You can continue later.", "info")
            return redirect(
                url_for("reviewer_evaluate_proposal", proposal_id=proposal_id)
            )

        # ---------------------------------------------------------
        # ACTION: SUBMIT FINAL EVALUATION
        # ---------------------------------------------------------
        elif action == "submit":

            if not all_answered:
                flash("Error: You must answer all 20 questions to submit.", "error")
                return redirect(
                    url_for("reviewer_evaluate_proposal", proposal_id=proposal_id)
                )

            # Update Proposal Score
            proposal.review_score = total_score
            proposal.review_feedback = feedback
            proposal.review_draft = json.dumps(data)

            # Determine Outcome
            if total_score >= 80:
                proposal.status = "Pending HOD Approval"
                flash(
                    f"Evaluation Complete. Score: {total_score}/100. Proposal forwarded to HOD.",
                    "success",
                )

                # Notify HOD
                if proposal.assigned_hod_id:
                    hod = HOD.query.get(proposal.assigned_hod_id)
                    msg = f"Action Required: Proposal '{proposal.title}' passed review ({total_score}/100)."
                    link = url_for("hod_dashboard")
                    send_notification(
                        hod.user_info.mmu_id, msg, link, sender_id=user.mmu_id
                    )
            else:
                proposal.status = "Rejected"
                flash(
                    f"Evaluation Complete. Score: {total_score}/100. Proposal Rejected.",
                    "error",
                )

                # Notify Researcher
                msg = f"Update: Your proposal '{proposal.title}' was rejected (Score: {total_score}/100)."
                link = url_for("researcher_dashboard")
                send_notification(
                    proposal.researcher.user_info.mmu_id,
                    msg,
                    link,
                    sender_id=user.mmu_id,
                )

            db.session.commit()
            return redirect(url_for("reviewer_evaluation_list"))

    # Pass 'saved_answers' to the template
    return render_template(
        "reviewer_evaluate_proposal.html",
        proposal=proposal,
        user=user,
        saved_answers=saved_answers,
        readonly=readonly
    )


# =====================================================================
#                            HOD MODULE
# =====================================================================


@app.route("/hod/login", methods=["POST", "GET"])
def hod_login():
    if request.method == "POST":
        user = User.query.filter_by(
            mmu_id=request.form["mmu_id"], user_role="HOD"
        ).first()
        if user and user.check_password(request.form["password"]):
            session["user_id"] = user.mmu_id
            session["role"] = "HOD"
            return redirect(url_for("hod_dashboard"))
        else:
            flash("Invalid credentials.", "error")
    return render_template("hod_login.html")


@app.route("/hod/dashboard")
def hod_dashboard():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    return render_template(
        "hod_dashboard.html",
        stats={"approvals_pending": 8},
        user=User.query.get(session["user_id"]),
    )


@app.route("/hod/profile", methods=["GET", "POST"])
def hod_profile():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("hod_profile"))
    return render_template("hod_profile.html", user=user)


@app.route("/hod/proposals")
def hod_assigned_proposals():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))

    current_hod = HOD.query.filter_by(mmu_id=session["user_id"]).first()
    
    # Filter and pagination
    search_query = request.args.get("search", "")
    filter_faculty = request.args.get("faculty", "")
    page = request.args.get("page", 1, type=int)
    per_page = 8

    query = Proposal.query.filter_by(assigned_hod_id=current_hod.hod_id).join(Researcher).join(User)

    if search_query:
        query = query.filter(Proposal.title.ilike(f"%{search_query}%"))
    if filter_faculty:
        query = query.filter(User.faculty == filter_faculty)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "hod_assigned_proposals.html",
        proposals=pagination.items,
        pagination=pagination,
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )

@app.route("/hod/proposals/view/<int:proposal_id>")
def hod_view_proposal(proposal_id):
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    proposal = Proposal.query.get_or_404(proposal_id)

    # Fetch existing deadlines for display
    deadlines = {
        "Reviewer": Deadline.query.filter_by(
            proposal_id=proposal.proposal_id, deadline_type="Reviewer"
        ).first(),
        "HOD": Deadline.query.filter_by(
            proposal_id=proposal.proposal_id, deadline_type="HOD"
        ).first(),
        "Final": Deadline.query.filter_by(
            proposal_id=proposal.proposal_id, deadline_type="Final Submission"
        ).first(),
    }

    return render_template(
        "hod_view_proposal.html",
        proposal=proposal,
        user=User.query.get(session["user_id"]),
        reviewer_deadline=deadlines["Reviewer"],
        hod_deadline=deadlines["HOD"],
        final_deadline=deadlines["Final"],
    )

@app.route("/hod/proposals/decision/<int:proposal_id>", methods=["POST"])
def hod_proposal_decision(proposal_id):
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))

    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])

    # Security: Ensure HOD is assigned
    current_hod = HOD.query.filter_by(mmu_id=user.mmu_id).first()
    if not current_hod or proposal.assigned_hod_id != current_hod.hod_id:
        flash("Error: You are not authorized to make decisions on this proposal.", "error")
        return redirect(url_for("hod_assigned_proposals"))

    decision = request.form.get("decision")

    if decision == "approve":
        proposal.status = "Pending Grant"
        
        # Create Grant Record (Award Funding)
        if not Grant.query.filter_by(proposal_id=proposal.proposal_id).first():
            new_grant = Grant(
                grant_amount=proposal.requested_budget,
                proposal_id=proposal.proposal_id
            )
            db.session.add(new_grant)
        
        flash(f"Proposal '{proposal.title}' Approved! You may allocate the grant amount now to finish the approval process.", "success")

    elif decision == "reject":
        proposal.status = "Rejected"
        flash(f"Proposal '{proposal.title}' Rejected.", "error")
        send_notification(proposal.researcher.user_info.mmu_id, f"Update: Your proposal '{proposal.title}' has been REJECTED.", url_for("researcher_dashboard"), sender_id=user.mmu_id)

    db.session.commit()
    return redirect(url_for("hod_view_proposal", proposal_id=proposal.proposal_id))

@app.route("/hod/grant_allocation")
def hod_grant_allocation():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    
    user = User.query.get(session["user_id"])
    current_hod = HOD.query.filter_by(mmu_id=user.mmu_id).first()

    # Fetch proposals: Pending Grant or Approved, assigned to this HOD
    proposals = Proposal.query.filter(
        Proposal.assigned_hod_id == current_hod.hod_id,
        Proposal.status.in_(["Pending Grant", "Approved"])
    ).all()

    # Calculate Budget Info
    total_budget_in = db.session.query(func.sum(Budget.amount)).scalar() or 0.0
    total_grants_out = db.session.query(func.sum(Grant.grant_amount)).scalar() or 0.0
    remaining_balance = total_budget_in - total_grants_out

    return render_template(
        "hod_grant_allocation.html",
        proposals=proposals,
        user=user,
        remaining_balance=remaining_balance
    )

@app.route("/hod/grant_allocation/update", methods=["POST"])
def hod_update_grant():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))

    proposal_id = request.form.get("proposal_id")
    new_amount = float(request.form.get("amount"))
    
    proposal = Proposal.query.get_or_404(proposal_id)
    grant = Grant.query.filter_by(proposal_id=proposal.proposal_id).first()

    if not grant:
        flash("Error: Grant record not found.", "error")
        return redirect(url_for("hod_grant_allocation"))

    # Update
    grant.grant_amount = new_amount
    if proposal.status == "Pending Grant":
        proposal.status = "Approved"

    db.session.commit()
    flash(f"Grant allocated successfully: RM {new_amount:,.2f}", "success")
    send_notification(proposal.researcher.user_info.mmu_id, f"Update: Your proposal '{proposal.title}' has been APPROVED.", url_for("researcher_dashboard"), sender_id=user.mmu_id)
    return redirect(url_for("hod_grant_allocation"))

# ==================================================================
#                          MAIN EXECUTION
# ==================================================================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
