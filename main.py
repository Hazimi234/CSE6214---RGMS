import os
import secrets
import json
from datetime import datetime, date, timedelta, timezone
from flask import Flask, redirect, url_for, render_template, request, session, flash
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from sqlalchemy import func

# Import Database Models
from models import (
    ProposalVersion,
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
    ProgressReport,
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


# =====================================================================
#                       TIMEZONE HELPERS (Malaysia UTC+8)
# =====================================================================
def get_myt_time():
    """Returns the current datetime in Malaysia Time (UTC+8)"""
    return datetime.now(timezone(timedelta(hours=8)))


def get_myt_date():
    """Returns the current DATE in Malaysia Time"""
    return get_myt_time().date()


# =====================================================================
#                       NOTIFICATION HELPER
# =====================================================================
def check_deadlines_and_notify(user):
    """
    Checks if the Final Submission Deadline is approaching for Researchers.
    Uses Malaysia Time for date comparisons.
    """
    if user.user_role == "Researcher":
        researcher = Researcher.query.filter_by(mmu_id=user.mmu_id).first()
        if not researcher:
            return

        # Check Active Proposals with a Final Deadline Set
        active_proposals = Proposal.query.filter_by(
            researcher_id=researcher.researcher_id, status="Approved"
        ).all()

        for prop in active_proposals:
            deadline = Deadline.query.filter_by(
                proposal_id=prop.proposal_id, deadline_type="Final Submission"
            ).first()

            if deadline and deadline.due_date:
                # Use Malaysia Date
                days_left = (deadline.due_date - get_myt_date()).days
                msg = None

                if days_left < 0:
                    msg = f"URGENT: Final submission for '{prop.title}' is OVERDUE (Due: {deadline.due_date})."
                elif 0 <= days_left <= 7:  # Notify 1 week before
                    msg = f"Reminder: Final submission for '{prop.title}' is due in {days_left} days."

                if msg:
                    # Avoid duplicate notifications
                    if not Notification.query.filter_by(
                        recipient_id=user.mmu_id, message=msg
                    ).first():
                        send_notification(
                            user.mmu_id,
                            msg,
                            url_for(
                                "researcher_submit_form",
                                cycle_id=prop.cycle_id,
                                proposal_id=prop.proposal_id,
                            ),
                            "System",
                        )


# ========================================================================
#                            HELPER FUNCTIONS
# ========================================================================


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


def save_document(form_file):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_file.filename)
    doc_fn = random_hex + f_ext
    doc_path = os.path.join(app.config["UPLOAD_FOLDER_DOCS"], doc_fn)
    form_file.save(doc_path)
    return doc_fn


def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.config["UPLOAD_FOLDER"], picture_fn)
    form_picture.save(picture_path)
    return picture_fn


def update_user_profile(user, form, files):
    user.name = form["name"]
    user.email = form["email"]
    user.phone_number = form["phone_number"]

    if "profile_pic" in files:
        file = files["profile_pic"]
        if file.filename != "":
            picture_file = save_picture(file)
            user.profile_image = picture_file

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
    # Timestamp handles itself via Models default=malaysia_now
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
    return render_template("main_login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main_login"))


@app.route("/notifications")
def view_notifications():
    if "user_id" not in session:
        return redirect(url_for("main_login"))
    user_id = session["user_id"]
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
    if "user_id" not in session:
        return redirect(url_for("main_login"))
    notif = Notification.query.get_or_404(notif_id)
    if notif.recipient_id != session["user_id"]:
        return redirect(url_for("view_notifications"))
    notif.is_read = True
    db.session.commit()
    return (
        redirect(notif.link) if notif.link else redirect(url_for("view_notifications"))
    )


@app.route("/notifications/mark_all_read")
def mark_all_notifications_read():
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
@app.route("/admin/login", methods=["POST", "GET"])
def admin_login():
    if request.method == "POST":
        user = User.query.filter_by(
            mmu_id=request.form["mmu_id"], user_role="Admin"
        ).first()
        if user and user.check_password(request.form["password"]):
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

    try:
        total_fund_capacity = db.session.query(db.func.sum(Budget.amount)).scalar() or 0
    except:
        total_fund_capacity = 0

    awarded_proposals = Proposal.query.filter_by(status="Approved").all()
    funds_utilized = (
        sum(p.requested_budget for p in awarded_proposals) if awarded_proposals else 0
    )

    funds_utilized_percent = 0
    if total_fund_capacity > 0:
        funds_utilized_percent = round((funds_utilized / total_fund_capacity) * 100, 1)

    # Use Malaysia Date
    today = get_myt_date()
    next_30_days = today + timedelta(days=30)

    closing_soon = (
        GrantCycle.query.filter(
            GrantCycle.end_date >= today,
            GrantCycle.end_date <= next_30_days,
            GrantCycle.is_open == True,
        )
        .order_by(GrantCycle.end_date.asc())
        .all()
    )

    recent_proposals = (
        Proposal.query.order_by(Proposal.submission_date.desc()).limit(5).all()
    )

    stats = {
        "open_cycles": GrantCycle.query.filter_by(is_open=True).count(),
        "total_cycles": GrantCycle.query.count(),
        "new_proposals": Proposal.query.filter_by(status="Submitted").count(),
        "under_review": Proposal.query.filter(
            Proposal.status.in_(
                ["Under Review", "Screening Passed", "Pending HOD Approval"]
            )
        ).count(),
        "awarded": Proposal.query.filter_by(status="Approved").count(),
    }

    return render_template(
        "admin_dashboard.html",
        user=user,
        total_fund_capacity=total_fund_capacity,
        funds_utilized_percent=funds_utilized_percent,
        closing_soon=closing_soon,
        recent_proposals=recent_proposals,
        open_cycles=stats["open_cycles"],
        total_cycles=stats["total_cycles"],
        new_proposals=stats["new_proposals"],
        under_review=stats["under_review"],
        awarded=stats["awarded"],
    )


@app.route("/admin/profile", methods=["GET", "POST"])
def admin_profile():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("admin_profile"))
    return render_template("admin_profile.html", user=user)


@app.route("/admin/users")
def admin_user_management():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
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
        faculties=Faculty.query.all(),
    )


@app.route("/admin/users/create", methods=["GET", "POST"])
def admin_create_user():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        role = request.form["role"]
        if User.query.filter_by(mmu_id=mmu_id).first():
            flash(f"Error: User with MMU ID {mmu_id} already exists.", "error")
            return redirect(url_for("admin_create_user"))
        if User.query.filter_by(email=request.form["email"]).first():
            flash(f"Error: Email is already taken.", "error")
            return redirect(url_for("admin_create_user"))
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


@app.route("/admin/proposals")
def admin_proposal_management():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    search_query = request.args.get("search", "")
    filter_faculty = request.args.get("faculty", "")
    page = request.args.get("page", 1, type=int)
    per_page = 6
    query = GrantCycle.query
    if search_query:
        query = query.filter(GrantCycle.cycle_name.ilike(f"%{search_query}%"))
    if filter_faculty:
        query = query.filter(GrantCycle.faculty == filter_faculty)
    pagination = query.order_by(GrantCycle.start_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Pass Malaysia Date for correct status display
    return render_template(
        "admin_proposal_management.html",
        cycles=pagination.items,
        pagination=pagination,
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
        today=get_myt_date(),
    )


@app.route("/admin/proposals/cycle/<int:cycle_id>")
def admin_view_cycle_proposals(cycle_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    cycle = GrantCycle.query.get_or_404(cycle_id)
    search_proposal = request.args.get("search", "")
    filter_area = request.args.get("area", "")
    page = request.args.get("page", 1, type=int)
    per_page = 8
    query = Proposal.query.filter_by(cycle_id=cycle.cycle_id)
    if search_proposal:
        query = query.filter(Proposal.title.ilike(f"%{search_proposal}%"))
    if filter_area:
        query = query.filter(Proposal.research_area == filter_area)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "admin_cycle_proposals.html",
        cycle=cycle,
        proposals=pagination.items,
        pagination=pagination,
        user=User.query.get(session["user_id"]),
        research_areas=ResearchArea.query.all(),
    )


@app.route("/admin/proposals/open", methods=["GET", "POST"])
def admin_open_cycle():
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
    final_deadline = Deadline.query.filter_by(
        proposal_id=proposal.proposal_id, deadline_type="Final Submission"
    ).first()
    return render_template(
        "admin_view_proposal.html",
        proposal=proposal,
        user=User.query.get(session["user_id"]),
        final_deadline=final_deadline,
    )


@app.route("/admin/proposals/assign/<int:proposal_id>", methods=["GET", "POST"])
def admin_assign_evaluators(proposal_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    researcher_faculty = proposal.researcher.user_info.faculty
    if request.method == "POST":
        reviewer_id = request.form.get("reviewer_id")
        if reviewer_id:
            proposal.assigned_reviewer_id = reviewer_id
            reviewer_user = Reviewer.query.get(reviewer_id).user_info
            send_notification(
                reviewer_user.mmu_id,
                f"Assignment: Screen '{proposal.title}'",
                url_for("reviewer_view_proposals"),
                session["user_id"],
            )
        hod_id = request.form.get("hod_id")
        if hod_id:
            proposal.assigned_hod_id = hod_id
        proposal.status = "Under Review"
        db.session.commit()
        flash("Evaluators assigned successfully.", "success")
        return redirect(
            url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
        )
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


@app.route("/admin/proposals/final_deadline/<int:proposal_id>", methods=["GET", "POST"])
def admin_set_final_deadline(proposal_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    if proposal.status != "Approved":
        flash(
            "Action Locked: You cannot set a final deadline until the HOD approves the grant.",
            "error",
        )
        return redirect(url_for("admin_view_proposal", proposal_id=proposal_id))
    if request.method == "POST":
        final_date = request.form.get("final_deadline")
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
            msg = f"Project Update: Final submission deadline set for '{proposal.title}' to {final_date}."
            link = url_for("researcher_my_proposals")
            send_notification(
                proposal.researcher.user_info.mmu_id,
                msg,
                link,
                sender_id=session["user_id"],
            )
            flash("Final Submission Deadline Set!", "success")
            return redirect(
                url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
            )
    return render_template(
        "admin_set_final_deadline.html",
        proposal=proposal,
        user=User.query.get(session["user_id"]),
    )


@app.route("/admin/budget", methods=["GET", "POST"])
def admin_budget_tracking():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    if request.method == "POST":
        try:
            amount = float(request.form["amount"])
            description = request.form["description"]
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
    total_budget_in = db.session.query(func.sum(Budget.amount)).scalar() or 0.0
    total_grants_out = db.session.query(func.sum(Grant.grant_amount)).scalar() or 0.0
    current_balance = total_budget_in - total_grants_out
    budget_history = Budget.query.order_by(Budget.created_at.desc()).all()
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


@app.route("/admin/budget/edit/<int:budget_id>", methods=["POST"])
def admin_edit_budget(budget_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    budget = Budget.query.get_or_404(budget_id)
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


@app.route("/admin/budget/delete/<int:budget_id>", methods=["POST"])
def admin_delete_budget(budget_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    budget = Budget.query.get_or_404(budget_id)
    db.session.delete(budget)
    db.session.commit()
    flash("Budget entry deleted.", "success")
    return redirect(url_for("admin_budget_tracking"))


@app.route("/admin/system_data", methods=["GET", "POST"])
def admin_system_data():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    if request.method == "POST":
        type_added = request.form.get("type")
        name_added = request.form.get("name").strip()
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
    user = User.query.get(session["user_id"])
    researcher = Researcher.query.filter_by(mmu_id=user.mmu_id).first()
    approved_count = Proposal.query.filter_by(
        researcher_id=researcher.researcher_id, status="Approved"
    ).count()
    stats = {
        "my_proposals": Proposal.query.filter_by(
            researcher_id=researcher.researcher_id
        ).count(),
        "approved": approved_count,
        "active_grants": Grant.query.join(Proposal)
        .filter(Proposal.researcher_id == researcher.researcher_id)
        .count(),
        "unread_notifs": Notification.query.filter_by(
            recipient_id=user.mmu_id, is_read=False
        ).count(),
    }
    recent_proposals = (
        Proposal.query.filter_by(researcher_id=researcher.researcher_id)
        .order_by(Proposal.submission_date.desc())
        .limit(3)
        .all()
    )
    return render_template(
        "researcher_dashboard.html",
        stats=stats,
        user=user,
        researcher=researcher,
        recent_proposals=recent_proposals,
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
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))

    # Use Malaysia Date
    today = get_myt_date()
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
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))

    cycle = GrantCycle.query.get_or_404(cycle_id)
    user = User.query.get(session["user_id"])
    researcher = Researcher.query.filter_by(mmu_id=user.mmu_id).first()

    # Eligibility Check
    if user.faculty != cycle.faculty:
        flash(f"Access Denied: Ineligible for {cycle.faculty} grants.", "error")
        return redirect(url_for("researcher_apply_list"))

    # Cycle Deadline Check
    cycle_closed = cycle.end_date < get_myt_date() or not cycle.is_open

    proposal_id = request.args.get("proposal_id") or request.form.get("proposal_id")
    proposal = Proposal.query.get(proposal_id) if proposal_id else None

    if request.method == "POST":
        if cycle_closed:
            flash("Error: This grant cycle is closed.", "error")
            return redirect(url_for("researcher_apply_list"))

        current_status = (
            "Draft" if request.form.get("action") == "draft" else "Submitted"
        )
        file = request.files.get("proposal_file")
        doc_filename = None
        if file and allowed_file(file.filename):
            doc_filename = save_document(file)

        if proposal:
            has_changed = any(
                [
                    doc_filename is not None,
                    proposal.title != request.form.get("title"),
                    proposal.research_area != request.form.get("research_area"),
                    proposal.requested_budget != float(request.form.get("budget", 0)),
                ]
            )
            proposal.title = request.form.get("title")
            proposal.research_area = request.form.get("research_area")
            proposal.requested_budget = float(request.form.get("budget", 0))
            proposal.status = current_status
            if doc_filename:
                proposal.document_file = doc_filename
        else:
            has_changed = True
            proposal = Proposal(
                title=request.form.get("title"),
                research_area=request.form.get("research_area"),
                requested_budget=float(request.form.get("budget", 0)),
                status=current_status,
                researcher_id=researcher.researcher_id,
                cycle_id=cycle.cycle_id,
                document_file=doc_filename,
            )
            db.session.add(proposal)

        db.session.flush()

        if has_changed:
            version_count = ProposalVersion.query.filter_by(
                proposal_id=proposal.proposal_id
            ).count()
            note = (
                "Initial submission"
                if (version_count == 0 and current_status == "Submitted")
                else "Updated proposal"
            )
            new_version = ProposalVersion(
                proposal_id=proposal.proposal_id,
                version_number=version_count + 1,
                document_file=proposal.document_file,
                upload_date=get_myt_time(),
                title_snapshot=proposal.title,
                research_area_snapshot=proposal.research_area,
                budget_snapshot=proposal.requested_budget,
                version_note=note,
            )
            db.session.add(new_version)

        db.session.commit()
        if current_status == "Submitted":
            admin = User.query.filter_by(user_role="Admin").first()
            if admin:
                msg = f"New Proposal: '{proposal.title}' by {user.name}."
                send_notification(
                    admin.mmu_id,
                    msg,
                    url_for("admin_view_proposal", proposal_id=proposal.proposal_id),
                    session["user_id"],
                )
        flash(f"Proposal {current_status.lower()}ed successfully!", "success")
        return redirect(url_for("researcher_my_proposals"))

    return render_template(
        "researcher_submit_form.html",
        cycle=cycle,
        user=user,
        proposal=proposal,
        research_areas=ResearchArea.query.all(),
        cycle_closed=cycle_closed,
    )


@app.route("/researcher/revert/<int:proposal_id>/<int:version_id>")
def researcher_revert_proposal(proposal_id, version_id):
    v = ProposalVersion.query.get_or_404(version_id)
    proposal = Proposal.query.get_or_404(proposal_id)
    proposal.document_file = v.document_file
    proposal.title = v.title_snapshot
    proposal.research_area = v.research_area_snapshot
    proposal.requested_budget = v.budget_snapshot
    new_v_num = (
        ProposalVersion.query.filter_by(proposal_id=proposal.proposal_id).count() + 1
    )
    revert_log = ProposalVersion(
        proposal_id=proposal.proposal_id,
        version_number=new_v_num,
        document_file=v.document_file,
        title_snapshot=v.title_snapshot,
        research_area_snapshot=v.research_area_snapshot,
        budget_snapshot=v.budget_snapshot,
        version_note=f"Reverted to Version {v.version_number}",
        upload_date=get_myt_time(),
    )
    db.session.add(revert_log)
    db.session.commit()
    flash(f"Reverted to Version {v.version_number}", "success")
    return redirect(
        url_for(
            "researcher_submit_form",
            cycle_id=proposal.cycle_id,
            proposal_id=proposal.proposal_id,
        )
    )


@app.route("/researcher/proposal_status")
def researcher_my_proposals():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))
    user = User.query.get(session["user_id"])
    researcher = (
        Researcher.query.filter_by(mmu_id=user.mmu_id)
        .order_by(Researcher.researcher_id.desc())
        .first()
    )
    if not researcher:
        flash("Error: Researcher profile not found.", "error")
        return redirect(url_for("researcher_dashboard"))
    stats = {
        "my_proposals": Proposal.query.filter_by(
            researcher_id=researcher.researcher_id
        ).count(),
        "active_grants": Grant.query.join(Proposal)
        .filter(Proposal.researcher_id == researcher.researcher_id)
        .count(),
        "pending_reports": 0,
    }
    proposals = (
        Proposal.query.filter_by(researcher_id=researcher.researcher_id)
        .order_by(Proposal.proposal_id)
        .all()
    )
    return render_template(
        "researcher_my_proposals.html", proposals=proposals, user=user, stats=stats
    )


@app.route("/researcher/withdraw/<int:proposal_id>", methods=["POST"])
def researcher_withdraw_proposal(proposal_id):
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])
    proposal.status = "Withdrawn"
    db.session.commit()
    admin = User.query.filter_by(user_role="Admin").first()
    if admin:
        msg = f"Proposal Withdrawn: '{proposal.title}' by {user.name}."
        link = url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
        send_notification(
            recipient_id=admin.mmu_id, message=msg, link=link, sender_id=user.mmu_id
        )
    flash("Proposal withdrawn successfully.", "success")
    return redirect(url_for("researcher_my_proposals"))


@app.route("/researcher/update_progress/<int:proposal_id>", methods=["GET", "POST"])
def researcher_update_progress(proposal_id):
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])

    # 1. CHECK FINAL DEADLINE (Malaysia Time)
    final_deadline = Deadline.query.filter_by(
        proposal_id=proposal.proposal_id, deadline_type="Final Submission"
    ).first()
    deadline_passed = False
    if final_deadline and final_deadline.due_date < get_myt_date():
        deadline_passed = True

    if request.method == "POST":
        if deadline_passed:
            flash(
                f"Error: The deadline ({final_deadline.due_date}) has passed.", "error"
            )
            return redirect(
                url_for("researcher_update_progress", proposal_id=proposal.proposal_id)
            )

        file = request.files.get("report_file")
        report_title = request.form["report_title"]
        financial_usage = request.form.get("financial_usage")
        content = request.form.get("description")
        if file and allowed_file(file.filename):
            filename = save_document(file)
            new_report = ProgressReport(
                proposal_id=proposal.proposal_id,
                title=report_title,
                document_file=filename,
                content=content,
                financial_usage=float(financial_usage) if financial_usage else 0.0,
                submission_date=get_myt_time(),
                status="Submitted",
            )
            db.session.add(new_report)
            db.session.commit()
            if proposal.assigned_hod_id:
                hod = HOD.query.get(proposal.assigned_hod_id)
                msg = f"New Progress Report: '{report_title}' for project '{proposal.title}'."
                link = url_for(
                    "hod_view_progress_reports", proposal_id=proposal.proposal_id
                )
                send_notification(
                    hod.user_info.mmu_id, msg, link, sender_id=user.mmu_id
                )
            flash("Progress report submitted successfully.", "success")
            return redirect(url_for("researcher_my_proposals"))
        else:
            flash("Error: Valid report file required.", "error")
    return render_template(
        "researcher_update_progress.html",
        proposal=proposal,
        user=user,
        deadline_passed=deadline_passed,
        final_deadline=final_deadline,
    )


@app.route("/researcher/request_extension/<int:proposal_id>", methods=["POST"])
def researcher_request_extension(proposal_id):
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    reason = request.form.get("extension_reason")
    user = User.query.get(session["user_id"])
    admin = User.query.filter_by(user_role="Admin").first()
    if admin:
        msg = f"Extension Request: {user.name} requests time for '{proposal.title}'. Reason: {reason}"
        link = url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
        send_notification(admin.mmu_id, msg, link, sender_id=session["user_id"])
    flash("Extension request sent to Admin successfully.", "success")
    return redirect(url_for("researcher_my_proposals"))


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
    user = User.query.get(session["user_id"])
    check_deadlines_and_notify(user)
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()
    stats = {"pending_screenings": 0, "pending_reviews": 0}
    if reviewer_profile:
        stats["pending_screenings"] = Proposal.query.filter(
            Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
            Proposal.status.in_(["Submitted", "Under Review", "Under Screening"]),
        ).count()
        stats["pending_reviews"] = Proposal.query.filter(
            Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
            Proposal.status == "Passed Screening",
            Proposal.review_score == None,
        ).count()
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


@app.route("/reviewer/proposals")
def reviewer_view_proposals():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer_login"))
    user = User.query.get(session["user_id"])
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()
    if not reviewer_profile:
        flash("Error: Reviewer profile not found.", "error")
        return redirect(url_for("reviewer_dashboard"))
    all_assigned = (
        Proposal.query.filter_by(assigned_reviewer_id=reviewer_profile.reviewer_id)
        .order_by(Proposal.submission_date.desc())
        .all()
    )
    pending_screening = [
        p
        for p in all_assigned
        if p.status in ["Submitted", "Under Review", "Under Screening"]
    ]
    screening_history = [
        p
        for p in all_assigned
        if p.status not in ["Submitted", "Under Review", "Under Screening"]
    ]
    return render_template(
        "reviewer_proposals.html",
        pending_proposals=pending_screening,
        history_proposals=screening_history,
        user=user,
    )


@app.route("/reviewer/screen/<int:proposal_id>", methods=["GET", "POST"])
def reviewer_screen_proposal(proposal_id):
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()
    if (
        not reviewer_profile
        or proposal.assigned_reviewer_id != reviewer_profile.reviewer_id
    ):
        flash("Access Denied.", "error")
        return redirect(url_for("reviewer_dashboard"))
    active_statuses = ["Submitted", "Under Review", "Under Screening"]
    readonly = proposal.status not in active_statuses
    if request.method == "POST":
        if readonly:
            flash(
                "Action not allowed. This proposal has already been screened.", "error"
            )
            return redirect(url_for("reviewer_view_proposals"))
        decision = request.form.get("decision")
        if decision == "eligible":
            proposal.status = "Passed Screening"
            flash(
                "Proposal Passed Screening. You may now proceed to evaluation.",
                "success",
            )
        elif decision == "not_eligible":
            proposal.status = "Failed Screening"
            # Using Malaysia Date Check
            if proposal.cycle and proposal.cycle.end_date >= get_myt_date():
                msg = f"Screening Update: Your proposal '{proposal.title}' Failed Screening. Cycle OPEN."
                flash(
                    "Proposal marked as Failed Screening. Researcher notified.",
                    "warning",
                )
            else:
                msg = f"Screening Update: Your proposal '{proposal.title}' Failed Screening. Cycle CLOSED."
                flash("Proposal marked as Failed Screening. Cycle is closed.", "error")
            link = url_for("researcher_my_proposals")
            if proposal.researcher:
                send_notification(
                    proposal.researcher.user_info.mmu_id,
                    msg,
                    link,
                    sender_id=user.mmu_id,
                )
        elif decision == "not_interested":
            proposal.status = "Return for Reassignment"
            admin = User.query.filter_by(user_role="Admin").first()
            if admin:
                msg = f"Return Alert: Reviewer {user.name} declined proposal assignment for '{proposal.title}'."
                link = url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
                send_notification(admin.mmu_id, msg, link, sender_id=user.mmu_id)
            flash("Task declined. Proposal returned to Admin for reassignment.", "info")
        db.session.commit()
        return redirect(url_for("reviewer_view_proposals"))
    return render_template(
        "reviewer_screen_proposal.html", proposal=proposal, user=user, readonly=readonly
    )


@app.route("/reviewer/evaluation_list")
def reviewer_evaluation_list():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer_login"))
    user = User.query.get(session["user_id"])
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "")
    query_pending = Proposal.query.filter(
        Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
        Proposal.status == "Passed Screening",
        Proposal.review_score == None,
    )
    if search:
        query_pending = query_pending.filter(Proposal.title.ilike(f"%{search}%"))
    pagination = query_pending.paginate(page=page, per_page=8, error_out=False)
    history_proposals = (
        Proposal.query.filter(
            Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
            Proposal.review_score != None,
        )
        .order_by(Proposal.submission_date.desc())
        .all()
    )
    return render_template(
        "reviewer_evaluation_list.html",
        proposals=pagination.items,
        pagination=pagination,
        history=history_proposals,
        user=user,
        research_areas=ResearchArea.query.all(),
    )


@app.route("/reviewer/evaluate/<int:proposal_id>", methods=["GET", "POST"])
def reviewer_evaluate_proposal(proposal_id):
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])
    if proposal.status == "Passed Screening":
        readonly = False
    elif proposal.review_score is not None:
        readonly = True
    else:
        flash(
            f"Error: This proposal cannot be evaluated. Current status: {proposal.status}",
            "error",
        )
        return redirect(url_for("reviewer_view_proposals"))
    saved_answers = {}
    if proposal.review_draft:
        try:
            saved_answers = json.loads(proposal.review_draft)
        except:
            saved_answers = {}
    if request.method == "POST":
        if readonly:
            flash("This proposal has already been submitted.", "error")
            return redirect(url_for("reviewer_evaluation_list"))
        action = request.form.get("action")
        data = {}
        total_score = 0
        all_answered = True
        for i in range(1, 21):
            val = request.form.get(f"q{i}")
            data[f"q{i}"] = val
            if val:
                total_score += int(val)
            else:
                all_answered = False
        feedback = request.form.get("feedback")
        data["feedback"] = feedback
        if action == "save_draft":
            proposal.review_draft = json.dumps(data)
            db.session.commit()
            flash("Draft saved successfully.", "info")
            return redirect(
                url_for("reviewer_evaluate_proposal", proposal_id=proposal_id)
            )
        elif action == "submit":
            if not all_answered:
                flash("Error: You must answer all 20 questions to submit.", "error")
                return redirect(
                    url_for("reviewer_evaluate_proposal", proposal_id=proposal_id)
                )
            proposal.review_score = total_score
            proposal.review_feedback = feedback
            proposal.review_draft = json.dumps(data)
            if total_score >= 75:
                proposal.status = "Pending HOD Approval"
                flash(
                    f"Review Submitted (Score: {total_score}). Forwarded to HOD.",
                    "success",
                )
                if proposal.assigned_hod_id:
                    hod = HOD.query.get(proposal.assigned_hod_id)
                    if hod:
                        msg = f"Action Required: Proposal '{proposal.title}' passed review ({total_score}/100)."
                        link = url_for("hod_dashboard")
                        send_notification(
                            hod.user_info.mmu_id, msg, link, sender_id=user.mmu_id
                        )
            else:
                proposal.status = "Rejected"
                flash(
                    f"Review Submitted (Score: {total_score}). Proposal Rejected.",
                    "warning",
                )
                msg = f"Update: Your proposal '{proposal.title}' was rejected (Score: {total_score}/100). Reviewer Feedback: {feedback}"
                link = url_for("researcher_my_proposals")
                send_notification(
                    proposal.researcher.user_info.mmu_id,
                    msg,
                    link,
                    sender_id=user.mmu_id,
                )
            db.session.commit()
            return redirect(url_for("reviewer_evaluation_list"))
    return render_template(
        "reviewer_evaluate_proposal.html",
        proposal=proposal,
        user=user,
        saved_answers=saved_answers,
        readonly=readonly,
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
    search_query = request.args.get("search", "")
    filter_faculty = request.args.get("faculty", "")
    page = request.args.get("page", 1, type=int)
    per_page = 8
    query = (
        Proposal.query.filter_by(assigned_hod_id=current_hod.hod_id)
        .join(Researcher)
        .join(User)
    )
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
    return render_template(
        "hod_view_proposal.html",
        proposal=proposal,
        user=User.query.get(session["user_id"]),
    )


@app.route("/hod/proposals/decision/<int:proposal_id>", methods=["POST"])
def hod_proposal_decision(proposal_id):
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])
    current_hod = HOD.query.filter_by(mmu_id=user.mmu_id).first()
    if not current_hod or proposal.assigned_hod_id != current_hod.hod_id:
        flash(
            "Error: You are not authorized to make decisions on this proposal.", "error"
        )
        return redirect(url_for("hod_assigned_proposals"))
    decision = request.form.get("decision")
    if decision == "approve":
        proposal.status = "Pending Grant"
        if not Grant.query.filter_by(proposal_id=proposal.proposal_id).first():
            new_grant = Grant(
                grant_amount=proposal.requested_budget, proposal_id=proposal.proposal_id
            )
            db.session.add(new_grant)
        flash(
            f"Proposal '{proposal.title}' Approved! You may allocate the grant amount now to finish the approval process.",
            "success",
        )
    elif decision == "reject":
        proposal.status = "Rejected"
        flash(f"Proposal '{proposal.title}' Rejected.", "error")
        send_notification(
            proposal.researcher.user_info.mmu_id,
            f"Update: Your proposal '{proposal.title}' has been REJECTED.",
            url_for("researcher_my_proposals"),
            sender_id=user.mmu_id,
        )
        admin = User.query.filter_by(user_role="Admin").first()
        if admin:
            msg = f"Update: Proposal '{proposal.title}' was REJECTED by the HOD."
            link = url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
            send_notification(admin.mmu_id, msg, link, sender_id=user.mmu_id)
    db.session.commit()
    return redirect(url_for("hod_view_proposal", proposal_id=proposal.proposal_id))


@app.route("/hod/grant_allocation")
def hod_grant_allocation():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    user = User.query.get(session["user_id"])
    current_hod = HOD.query.filter_by(mmu_id=user.mmu_id).first()
    proposals = Proposal.query.filter(
        Proposal.assigned_hod_id == current_hod.hod_id,
        Proposal.status.in_(["Pending Grant", "Approved"]),
    ).all()
    total_budget_in = db.session.query(func.sum(Budget.amount)).scalar() or 0.0
    total_grants_out = db.session.query(func.sum(Grant.grant_amount)).scalar() or 0.0
    remaining_balance = total_budget_in - total_grants_out
    return render_template(
        "hod_grant_allocation.html",
        proposals=proposals,
        user=user,
        remaining_balance=remaining_balance,
    )


@app.route("/hod/grant_allocation/update", methods=["POST"])
def hod_update_grant():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    proposal_id = request.form.get("proposal_id")
    new_amount = float(request.form.get("amount"))
    if new_amount < 0:
        flash("Error: Grant amount cannot be negative.", "error")
        return redirect(url_for("hod_grant_allocation"))
    proposal = Proposal.query.get_or_404(proposal_id)
    grant = Grant.query.filter_by(proposal_id=proposal.proposal_id).first()
    user = User.query.get(session["user_id"])
    if not grant:
        flash("Error: Grant record not found.", "error")
        return redirect(url_for("hod_grant_allocation"))
    grant.grant_amount = new_amount
    if proposal.status == "Pending Grant":
        proposal.status = "Approved"
    db.session.commit()
    flash(f"Grant allocated successfully: RM {new_amount:,.2f}", "success")
    send_notification(
        proposal.researcher.user_info.mmu_id,
        f"Update: Your proposal '{proposal.title}' has been APPROVED.",
        url_for("researcher_my_proposals"),
        sender_id=user.mmu_id,
    )
    admin = User.query.filter_by(user_role="Admin").first()
    if admin:
        msg = f"Action Required: Proposal '{proposal.title}' is fully APPROVED. Please set the Final Deadline."
        link = url_for("admin_view_proposal", proposal_id=proposal.proposal_id)
        send_notification(admin.mmu_id, msg, link, sender_id=user.mmu_id)
    return redirect(url_for("hod_grant_allocation"))


@app.route("/hod/grant_budget")
def hod_grant_budget():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    user = User.query.get(session["user_id"])
    current_hod = HOD.query.filter_by(mmu_id=user.mmu_id).first()
    total_budget_in = db.session.query(func.sum(Budget.amount)).scalar() or 0.0
    total_grants_out = db.session.query(func.sum(Grant.grant_amount)).scalar() or 0.0
    remaining_balance = total_budget_in - total_grants_out
    search_query = request.args.get("search", "")
    filter_faculty = request.args.get("faculty", "")
    page = request.args.get("page", 1, type=int)
    per_page = 8
    query = (
        Proposal.query.join(Grant)
        .filter(Proposal.assigned_hod_id == current_hod.hod_id)
        .join(Researcher)
        .join(User)
    )
    if search_query:
        query = query.filter(Proposal.title.ilike(f"%{search_query}%"))
    if filter_faculty:
        query = query.filter(User.faculty == filter_faculty)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    proposal_data = []
    for p in pagination.items:
        spent = (
            db.session.query(func.sum(ProgressReport.financial_usage))
            .filter_by(proposal_id=p.proposal_id)
            .scalar()
            or 0.0
        )
        grant_amount = p.grant_award.grant_amount
        proposal_data.append(
            {
                "proposal": p,
                "spent": spent,
                "grant_amount": grant_amount,
                "balance": grant_amount - spent,
                "utilization": (spent / grant_amount * 100) if grant_amount > 0 else 0,
            }
        )
    return render_template(
        "hod_grant_budget.html",
        user=user,
        total_fund=total_budget_in,
        total_allocated=total_grants_out,
        current_balance=remaining_balance,
        proposal_data=proposal_data,
        pagination=pagination,
        faculties=Faculty.query.all(),
    )


@app.route("/hod/assigned_research")
def hod_assigned_research():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    user = User.query.get(session["user_id"])
    current_hod = HOD.query.filter_by(mmu_id=user.mmu_id).first()
    page = request.args.get("page", 1, type=int)
    search_query = request.args.get("search", "")
    filter_faculty = request.args.get("faculty", "")
    per_page = 8
    query = (
        Proposal.query.filter(
            Proposal.assigned_hod_id == current_hod.hod_id,
            Proposal.status.in_(["Approved", "Completed", "Terminated"]),
        )
        .join(Researcher)
        .join(User)
    )
    if search_query:
        query = query.filter(Proposal.title.ilike(f"%{search_query}%"))
    if filter_faculty:
        query = query.filter(User.faculty == filter_faculty)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "hod_assigned_research.html",
        proposals=pagination.items,
        pagination=pagination,
        user=user,
        faculties=Faculty.query.all(),
    )


@app.route("/hod/project/update_status", methods=["POST"])
def hod_update_project_status():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    proposal_id = request.form.get("proposal_id")
    new_status = request.form.get("status")
    proposal = Proposal.query.get_or_404(proposal_id)
    current_hod = HOD.query.filter_by(mmu_id=session["user_id"]).first()
    if not current_hod or proposal.assigned_hod_id != current_hod.hod_id:
        flash("Error: Permission denied.", "error")
        return redirect(url_for("hod_assigned_research"))
    if new_status:
        proposal.status = new_status
        db.session.commit()
        flash(f"Project '{proposal.title}' status updated to {new_status}.", "success")
    next_page = request.form.get("next_page")
    if next_page:
        return redirect(next_page)
    return redirect(url_for("hod_assigned_research"))


@app.route("/hod/assigned_research/progress/<int:proposal_id>")
def hod_view_progress_reports(proposal_id):
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])
    current_hod = HOD.query.filter_by(mmu_id=user.mmu_id).first()
    if not current_hod or proposal.assigned_hod_id != current_hod.hod_id:
        flash("Error: Access Denied.", "error")
        return redirect(url_for("hod_assigned_research"))
    reports = (
        ProgressReport.query.filter_by(proposal_id=proposal_id)
        .order_by(ProgressReport.submission_date.desc())
        .all()
    )
    return render_template(
        "hod_view_progress_reports.html", proposal=proposal, reports=reports, user=user
    )


@app.route("/hod/progress_report/decision", methods=["POST"])
def hod_progress_report_decision():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))
    report_id = request.form.get("report_id")
    decision = request.form.get("decision")
    feedback = request.form.get("feedback")
    report = ProgressReport.query.get_or_404(report_id)
    current_hod = HOD.query.filter_by(mmu_id=session["user_id"]).first()
    if not current_hod or report.proposal.assigned_hod_id != current_hod.hod_id:
        flash("Error: Access Denied.", "error")
        return redirect(url_for("hod_dashboard"))
    report.hod_feedback = feedback
    if decision == "validate":
        report.status = "Validated"
        flash("Progress report validated successfully.", "success")
        send_notification(
            report.proposal.researcher.user_info.mmu_id,
            f"Your progress report '{report.title}' has been VALIDATED.",
            url_for("researcher_my_proposals"),
            sender_id=session["user_id"],
        )
    elif decision == "revision":
        report.status = "Requires Revision"
        flash("Progress report returned for revision.", "info")
        send_notification(
            report.proposal.researcher.user_info.mmu_id,
            f"Action Required: Revision requested for report '{report.title}'.",
            url_for("researcher_my_proposals"),
            sender_id=session["user_id"],
        )
    db.session.commit()
    return redirect(
        url_for("hod_view_progress_reports", proposal_id=report.proposal_id)
    )


# ==================================================================
#                          MAIN EXECUTION
# ==================================================================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
