import os
import secrets
from datetime import datetime
from flask import Flask, redirect, url_for, render_template, request, session, flash
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename

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
    stats = {
        "pending_proposals": 12,
        "active_grants": 45,
        "total_users": 150,
    }  # Placeholder stats
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
@app.route("/admin/proposals")
def admin_proposal_management():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    # Filter and pagination
    search_query = request.args.get("search", "")
    filter_faculty = request.args.get("faculty", "")
    page = request.args.get("page", 1, type=int)
    per_page = 8

    query = Proposal.query.join(Researcher).join(User)

    if search_query:
        query = query.filter(Proposal.title.ilike(f"%{search_query}%"))
    if filter_faculty:
        query = query.filter(User.faculty == filter_faculty)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "admin_proposal_management.html",
        proposals=pagination.items,
        pagination=pagination,
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
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
    """Assigns Reviewer & HOD and sets their specific deadlines."""
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    proposal = Proposal.query.get_or_404(proposal_id)

    if request.method == "POST":
        if request.form.get("reviewer_id"):
            proposal.assigned_reviewer_id = request.form.get("reviewer_id")
        if request.form.get("hod_id"):
            proposal.assigned_hod_id = request.form.get("hod_id")

        # Set Deadlines
        for role_type in ["Reviewer", "HOD"]:
            date_val = request.form.get(f"{role_type.lower()}_deadline")
            if date_val:
                dl = Deadline.query.filter_by(
                    proposal_id=proposal.proposal_id, deadline_type=role_type
                ).first()
                if not dl:
                    dl = Deadline(
                        proposal_id=proposal.proposal_id, deadline_type=role_type
                    )
                dl.due_date = datetime.strptime(date_val, "%Y-%m-%d").date()
                db.session.add(dl)

        proposal.status = "Under Review"
        db.session.commit()
        flash("Evaluators assigned and deadlines set.", "success")
        return redirect(
            url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
        )

    # Fetch eligible evaluators (Same Faculty)
    faculty = proposal.researcher.user_info.faculty
    reviewers = Reviewer.query.join(User).filter(User.faculty == faculty).all()
    hods = HOD.query.join(User).filter(User.faculty == faculty).all()

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


# ==================================================================
#                          MAIN EXECUTION
# ==================================================================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
