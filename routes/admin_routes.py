from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from sqlalchemy import func
from datetime import datetime, timedelta
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
    Budget,
    Grant,
    Faculty,
    ResearchArea,
)
from utils import get_myt_date, send_notification, update_user_profile

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/login", methods=["POST", "GET"])
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
            return redirect(url_for("admin.admin_dashboard"))
        else:
            flash("Invalid Admin credentials.", "error")
    return render_template("admin_login.html")


@admin_bp.route("/admin/dashboard")
def admin_dashboard():
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
    user = User.query.get(session["user_id"])

    try:
        total_fund_capacity = db.session.query(func.sum(Budget.amount)).scalar() or 0
    except:
        total_fund_capacity = 0

    awarded_proposals = Proposal.query.filter_by(status="Approved").all()
    funds_utilized = (
        sum(p.requested_budget for p in awarded_proposals) if awarded_proposals else 0
    )

    funds_utilized_percent = 0
    if total_fund_capacity > 0:
        funds_utilized_percent = round((funds_utilized / total_fund_capacity) * 100, 1)

    today = get_myt_date()
    next_7_days = today + timedelta(days=7)

    closing_soon = (
        GrantCycle.query.filter(
            GrantCycle.end_date >= today,
            GrantCycle.end_date <= next_7_days,
            GrantCycle.is_open == True,
        )
        .order_by(GrantCycle.end_date.asc())
        .all()
    )

    recent_proposals = (
        Proposal.query.filter(Proposal.status != "Draft")
        .order_by(Proposal.submission_date.desc())
        .limit(5)
        .all()
    )

    active_cycles_count = GrantCycle.query.filter(
        GrantCycle.is_open == True,
        GrantCycle.start_date <= today,
        GrantCycle.end_date >= today,
    ).count()

    # --- FIX START: COMPREHENSIVE UNDER REVIEW COUNT ---
    # We now include every stage between "Submitted" and "Approved/Rejected"
    under_review_statuses = [
        "Under Review",  # With Reviewer (Screening)
        "Passed Screening",  # With Reviewer (Scoring)
        "Pending HOD Approval",  # With HOD (Decision)
        "Pending Grant",  # With HOD (Allocation)
    ]

    under_review_count = Proposal.query.filter(
        Proposal.status.in_(under_review_statuses)
    ).count()
    # --- FIX END ---

    stats = {
        "open_cycles": active_cycles_count,
        "total_cycles": GrantCycle.query.count(),
        "new_proposals": Proposal.query.filter_by(status="Submitted").count(),
        "under_review": under_review_count,  # <--- Updated variable
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


@admin_bp.route("/admin/profile", methods=["GET", "POST"])
def admin_profile():
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("admin.admin_profile"))
    return render_template("admin_profile.html", user=user)


@admin_bp.route("/admin/users")
def admin_user_management():
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
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


@admin_bp.route("/admin/users/create", methods=["GET", "POST"])
def admin_create_user():
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        role = request.form["role"]
        if User.query.filter_by(mmu_id=mmu_id).first():
            flash(f"Error: User with MMU ID {mmu_id} already exists.", "error")
            return redirect(url_for("admin.admin_create_user"))
        if User.query.filter_by(email=request.form["email"]).first():
            flash(f"Error: Email is already taken.", "error")
            return redirect(url_for("admin.admin_create_user"))
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
            return redirect(url_for("admin.admin_user_management"))
        except:
            db.session.rollback()
            flash("Database Error.", "error")
    return render_template(
        "admin_create_user.html",
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )


@admin_bp.route("/admin/users/edit/<string:user_id>", methods=["GET", "POST"])
def admin_edit_user(user_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
    target_user = User.query.get_or_404(user_id)
    if target_user.user_role == "Admin":
        flash("Action Not Allowed: You cannot edit Admin accounts.", "error")
        return redirect(url_for("admin.admin_user_management"))
    if request.method == "POST":
        target_user.name = request.form["name"]
        target_user.email = request.form["email"]
        target_user.phone_number = request.form["phone_number"]
        target_user.faculty = request.form["faculty"]
        if request.form["password"]:
            target_user.set_password(request.form["password"])
        db.session.commit()
        flash("User details updated.", "success")
        return redirect(url_for("admin.admin_user_management"))
    return render_template(
        "admin_edit_user.html",
        target_user=target_user,
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )


@admin_bp.route("/admin/users/delete/<string:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
    user_to_delete = User.query.get_or_404(user_id)
    if user_to_delete.user_role == "Admin":
        flash("Critical Error: You cannot delete an Admin account.", "error")
    else:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash("User deleted successfully.", "success")
    return redirect(url_for("admin.admin_user_management"))


@admin_bp.route("/admin/proposals")
def admin_proposal_management():
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
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

    return render_template(
        "admin_proposal_management.html",
        cycles=pagination.items,
        pagination=pagination,
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
        today=get_myt_date(),
    )


@admin_bp.route("/admin/proposals/cycle/<int:cycle_id>")
def admin_view_cycle_proposals(cycle_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    cycle = GrantCycle.query.get_or_404(cycle_id)
    search_proposal = request.args.get("search", "")
    filter_area = request.args.get("area", "")
    page = request.args.get("page", 1, type=int)
    per_page = 8

    query = Proposal.query.filter(
        Proposal.cycle_id == cycle.cycle_id, Proposal.status != "Draft"
    )

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


@admin_bp.route("/admin/proposals/open", methods=["GET", "POST"])
def admin_open_cycle():
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
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
            return redirect(url_for("admin.admin_proposal_management"))
    return render_template(
        "admin_open_cycle.html",
        user=User.query.get(session["user_id"]),
        faculties=Faculty.query.all(),
    )


@admin_bp.route("/admin/proposals/view/<int:proposal_id>")
def admin_view_proposal(proposal_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])

    # --- 1. FACULTY ACCESS CHECK ---
    # Compare Admin's Faculty vs Proposal Cycle's Faculty
    if user.faculty != proposal.cycle.faculty:
        flash(
            f"Access Denied: You can only manage proposals for {user.faculty}.", "error"
        )
        return redirect(url_for("admin.admin_proposal_management"))

    # --- 2. DRAFT CHECK ---
    if proposal.status == "Draft":
        flash(
            "Error: You cannot view this proposal because it is still in Draft mode.",
            "error",
        )
        return redirect(url_for("admin.admin_dashboard"))

    final_deadline = Deadline.query.filter_by(
        proposal_id=proposal.proposal_id, deadline_type="Final Submission"
    ).first()
    return render_template(
        "admin_view_proposal.html",
        proposal=proposal,
        user=user,
        final_deadline=final_deadline,
    )


@admin_bp.route("/admin/proposals/assign/<int:proposal_id>", methods=["GET", "POST"])
def admin_assign_evaluators(proposal_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])

    # --- FACULTY ACCESS CHECK ---
    if user.faculty != proposal.cycle.faculty:
        flash(
            f"Access Denied: You cannot assign evaluators for {proposal.cycle.faculty}.",
            "error",
        )
        return redirect(url_for("admin.admin_proposal_management"))

    researcher_faculty = proposal.researcher.user_info.faculty

    if request.method == "POST":
        reviewer_id = request.form.get("reviewer_id")
        if reviewer_id:
            proposal.assigned_reviewer_id = reviewer_id
            reviewer_user = Reviewer.query.get(reviewer_id).user_info
            send_notification(
                reviewer_user.mmu_id,
                f"Assignment: Screen '{proposal.title}'",
                url_for("reviewer.reviewer_view_proposals"),
                session["user_id"],
            )

        hod_id = request.form.get("hod_id")
        if hod_id:
            proposal.assigned_hod_id = hod_id

        proposal.status = "Under Review"
        db.session.commit()
        flash("Evaluators assigned successfully.", "success")
        return redirect(
            url_for("admin.admin_view_proposal", proposal_id=proposal.proposal_id)
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
        user=user,
    )


@admin_bp.route(
    "/admin/proposals/final_deadline/<int:proposal_id>", methods=["GET", "POST"]
)
def admin_set_final_deadline(proposal_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])

    # --- FACULTY ACCESS CHECK ---
    if user.faculty != proposal.cycle.faculty:
        flash(
            f"Access Denied: You cannot manage deadlines for {proposal.cycle.faculty}.",
            "error",
        )
        return redirect(url_for("admin.admin_proposal_management"))

    if proposal.status != "Approved":
        flash(
            "Action Locked: You cannot set a final deadline until the HOD approves the grant.",
            "error",
        )
        return redirect(url_for("admin.admin_view_proposal", proposal_id=proposal_id))

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
            link = url_for("researcher.researcher_my_proposals")
            send_notification(
                proposal.researcher.user_info.mmu_id,
                msg,
                link,
                sender_id=session["user_id"],
            )
            flash("Final Submission Deadline Set!", "success")
            return redirect(
                url_for("admin.admin_view_proposal", proposal_id=proposal.proposal_id)
            )

    return render_template(
        "admin_set_final_deadline.html", proposal=proposal, user=user
    )


@admin_bp.route("/admin/budget", methods=["GET", "POST"])
def admin_budget_tracking():

    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
    
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
        return redirect(url_for("admin.admin_budget_tracking"))
    
    total_budget_in = db.session.query(func.sum(Budget.amount)).scalar() or 0.0
    total_grants_out = db.session.query(func.sum(Grant.grant_amount)).scalar() or 0.0
    current_balance = total_budget_in - total_grants_out
    budget_history = Budget.query.order_by(Budget.created_at.desc()).all()

    # --- PAGINATION LOGIC START ---
    page = request.args.get('page', 1, type=int)
    per_page = 6
    
    active_grants = Grant.query.order_by(Grant.award_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    # --- PAGINATION LOGIC END ---

    return render_template(
        "admin_budget_tracking.html",
        user=User.query.get(session["user_id"]),
        total_fund=total_budget_in,
        total_allocated=total_grants_out,
        current_balance=current_balance,
        budget_history=budget_history,
        active_grants=active_grants
    )


@admin_bp.route("/admin/budget/edit/<int:budget_id>", methods=["POST"])
def admin_edit_budget(budget_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
    budget = Budget.query.get_or_404(budget_id)
    if budget.admin_id != session["user_id"]:
        flash("Error: You can only edit funds you added.", "error")
        return redirect(url_for("admin.admin_budget_tracking"))
    try:
        budget.amount = float(request.form["amount"])
        budget.description = request.form["description"]
        db.session.commit()
        flash("Budget entry updated successfully.", "success")
    except ValueError:
        flash("Error: Invalid amount.", "error")
    return redirect(url_for("admin.admin_budget_tracking"))


@admin_bp.route("/admin/budget/delete/<int:budget_id>", methods=["POST"])
def admin_delete_budget(budget_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
    budget = Budget.query.get_or_404(budget_id)
    db.session.delete(budget)
    db.session.commit()
    flash("Budget entry deleted.", "success")
    return redirect(url_for("admin.admin_budget_tracking"))


@admin_bp.route("/admin/system_data", methods=["GET", "POST"])
def admin_system_data():
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
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
        return redirect(url_for("admin.admin_system_data"))
    return render_template(
        "admin_system_data.html",
        faculties=Faculty.query.all(),
        areas=ResearchArea.query.all(),
        user=User.query.get(session["user_id"]),
    )


@admin_bp.route("/admin/system_data/edit", methods=["POST"])
def admin_edit_system_data():
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))
    item_id = request.form.get("id")
    new_name = request.form.get("name").strip()
    if request.form.get("type") == "faculty":
        Faculty.query.get(item_id).name = new_name
    elif request.form.get("type") == "area":
        ResearchArea.query.get(item_id).name = new_name
    db.session.commit()
    flash("Item updated.", "success")
    return redirect(url_for("admin.admin_system_data"))
