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

# Define the Blueprint for Admin-related routes
admin_bp = Blueprint("admin", __name__)

# ==============================================================================
# 1. AUTHENTICATION
# ==============================================================================


@admin_bp.route("/admin/login", methods=["POST", "GET"])
def admin_login():
    """
    Handles Admin login.
    - POST: Validates MMU ID and Password. If successful, sets session variables.
    - GET: Renders the login page.
    """
    if request.method == "POST":
        # Check if user exists and has the 'Admin' role
        user = User.query.filter_by(
            mmu_id=request.form["mmu_id"], user_role="Admin"
        ).first()

        # Validate password
        if user and user.check_password(request.form["password"]):
            # Store user details in session for access control
            session["user_id"] = user.mmu_id
            session["role"] = "Admin"
            session["name"] = user.name
            session["profile_image"] = user.profile_image
            return redirect(url_for("admin.admin_dashboard"))
        else:
            flash("Invalid Admin credentials.", "error")

    return render_template("admin_login.html")


# ==============================================================================
# 2. DASHBOARD & PROFILE
# ==============================================================================


@admin_bp.route("/admin/dashboard")
def admin_dashboard():
    """
    Displays the Admin Dashboard with key statistics and upcoming deadlines.
    """
    # Security Check: Ensure user is logged in as Admin
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    user = User.query.get(session["user_id"])

    # --- 1. Budget Statistics ---
    try:
        # Sum of all funds added to the system
        total_fund_capacity = db.session.query(func.sum(Budget.amount)).scalar() or 0
    except:
        total_fund_capacity = 0

    # Calculate utilized funds (Sum of approved grants)
    awarded_proposals = Proposal.query.filter_by(status="Approved").all()
    funds_utilized = (
        sum(p.requested_budget for p in awarded_proposals) if awarded_proposals else 0
    )

    # Calculate utilization percentage for the progress bar
    funds_utilized_percent = 0
    if total_fund_capacity > 0:
        funds_utilized_percent = round((funds_utilized / total_fund_capacity) * 100, 1)

    # --- 2. Timeline & Deadlines ---
    today = get_myt_date()
    next_7_days = today + timedelta(days=7)

    # Fetch grant cycles closing within the next 7 days
    closing_soon = (
        GrantCycle.query.filter(
            GrantCycle.end_date >= today,
            GrantCycle.end_date <= next_7_days,
            GrantCycle.is_open == True,
        )
        .order_by(GrantCycle.end_date.asc())
        .all()
    )

    # --- 3. Recent Activity ---
    recent_proposals = (
        Proposal.query.filter(Proposal.status != "Draft")
        .order_by(Proposal.submission_date.desc())
        .limit(5)
        .all()
    )

    # --- 4. Counts & Metrics ---
    active_cycles_count = GrantCycle.query.filter(
        GrantCycle.is_open == True,
        GrantCycle.start_date <= today,
        GrantCycle.end_date >= today,
    ).count()

    # Define all statuses that are considered "Under Review"
    under_review_statuses = [
        "Under Review",  # With Reviewer (Screening)
        "Passed Screening",  # With Reviewer (Scoring)
        "Pending HOD Approval",  # With HOD (Decision)
        "Pending Grant",  # With HOD (Allocation)
    ]

    # Aggregate statistics dictionary
    stats = {
        "open_cycles": active_cycles_count,
        "total_cycles": GrantCycle.query.count(),
        "new_proposals": Proposal.query.filter_by(status="Submitted").count(),
        "under_review": Proposal.query.filter(
            Proposal.status.in_(under_review_statuses)
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


@admin_bp.route("/admin/profile", methods=["GET", "POST"])
def admin_profile():
    """
    Allows Admin to view and update their profile details (photo, password, etc.).
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    user = User.query.get(session["user_id"])

    # Handle Profile Update Form Submission
    if request.method == "POST":
        # 'update_user_profile' is a utility function that handles file uploads and DB commits
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("admin.admin_profile"))

    return render_template("admin_profile.html", user=user)


# ==============================================================================
# 3. USER MANAGEMENT
# ==============================================================================


@admin_bp.route("/admin/users")
def admin_user_management():
    """
    Lists all users with search and filtering capabilities.
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    # Retrieve filter parameters from URL (GET request)
    search_query = request.args.get("search", "")
    filter_role = request.args.get("role", "")
    filter_faculty = request.args.get("faculty", "")

    # Pagination setup
    page = request.args.get("page", 1, type=int)
    per_page = 8

    # Build the database query dynamically based on filters
    query = User.query
    if search_query:
        query = query.filter(User.name.ilike(f"%{search_query}%"))
    if filter_role:
        query = query.filter_by(user_role=filter_role)
    if filter_faculty:
        query = query.filter_by(faculty=filter_faculty)

    # Execute query with pagination
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
    """
    Creates a new user account (Researcher, Reviewer, HOD, Admin).
    Also creates the corresponding role-specific table entry (e.g., adds to 'Researcher' table).
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        role = request.form["role"]

        # Validation: Check for duplicates
        if User.query.filter_by(mmu_id=mmu_id).first():
            flash(f"Error: User with MMU ID {mmu_id} already exists.", "error")
            return redirect(url_for("admin.admin_create_user"))

        if User.query.filter_by(email=request.form["email"]).first():
            flash(f"Error: Email is already taken.", "error")
            return redirect(url_for("admin.admin_create_user"))

        # Create base User record
        new_user = User(
            mmu_id=mmu_id,
            name=request.form["name"],
            email=request.form["email"],
            faculty=request.form["faculty"],
            user_role=role,
        )
        new_user.set_password(request.form["password"])
        db.session.add(new_user)

        # Create Role-Specific record (Polymorphic association manual handling)
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
    """
    Edits an existing user's details.
    Prevents editing other Admins to avoid privilege escalation issues.
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    target_user = User.query.get_or_404(user_id)

    # Security: Prevent editing other Admin accounts
    if target_user.user_role == "Admin":
        flash("Action Not Allowed: You cannot edit Admin accounts.", "error")
        return redirect(url_for("admin.admin_user_management"))

    if request.method == "POST":
        target_user.name = request.form["name"]
        target_user.email = request.form["email"]
        target_user.phone_number = request.form["phone_number"]
        target_user.faculty = request.form["faculty"]

        # Only update password if a new one is provided
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
    """
    Deletes a user account.
    Prevents deletion of Admin accounts to ensure system access.
    """
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


# ==============================================================================
# 4. GRANT CYCLE MANAGEMENT
# ==============================================================================


@admin_bp.route("/admin/proposals")
def admin_proposal_management():
    """
    Lists all Grant Cycles (Open/Closed) with search/filter options.
    """
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


@admin_bp.route("/admin/proposals/open", methods=["GET", "POST"])
def admin_open_cycle():
    """
    Opens a new Grant Cycle.
    Required to allow Researchers to submit proposals.
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    if request.method == "POST":
        start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(request.form["end_date"], "%Y-%m-%d").date()

        # Validation
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


# ==============================================================================
# 5. PROPOSAL MANAGEMENT (VIEW, ASSIGN, DEADLINE)
# ==============================================================================


@admin_bp.route("/admin/proposals/cycle/<int:cycle_id>")
def admin_view_cycle_proposals(cycle_id):
    """
    Lists all proposals within a specific Grant Cycle.
    Includes filtering by status, research area, and sorting.
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    cycle = GrantCycle.query.get_or_404(cycle_id)

    # 1. GET FILTER PARAMETERS
    search_proposal = request.args.get("search", "")
    filter_area = request.args.get("area", "")
    filter_status = request.args.get("status", "")
    sort_option = request.args.get("sort", "newest")
    page = request.args.get("page", 1, type=int)
    per_page = 8

    # 2. BASE QUERY (Exclude Drafts - Admins should not see unfinished work)
    query = Proposal.query.filter(
        Proposal.cycle_id == cycle.cycle_id, Proposal.status != "Draft"
    )

    # 3. APPLY FILTERS
    if search_proposal:
        query = query.filter(Proposal.title.ilike(f"%{search_proposal}%"))

    if filter_area and filter_area != "all":
        query = query.filter(Proposal.research_area == filter_area)

    if filter_status and filter_status != "all":
        query = query.filter(Proposal.status == filter_status)

    # 4. APPLY SORTING
    if sort_option == "oldest":
        query = query.order_by(Proposal.proposal_id.asc())
    elif sort_option == "title_asc":
        query = query.order_by(Proposal.title.asc())
    elif sort_option == "status_asc":
        query = query.order_by(Proposal.status.asc())
    else:
        # Default: Newest (Highest ID first)
        query = query.order_by(Proposal.proposal_id.desc())

    # Execute Pagination
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "admin_cycle_proposals.html",
        cycle=cycle,
        proposals=pagination.items,
        pagination=pagination,
        user=User.query.get(session["user_id"]),
        research_areas=ResearchArea.query.all(),
        # Pass filters back to template to maintain state
        current_search=search_proposal,
        current_area=filter_area,
        current_status=filter_status,
        current_sort=sort_option,
    )


@admin_bp.route("/admin/proposals/view/<int:proposal_id>")
def admin_view_proposal(proposal_id):
    """
    View full details of a specific proposal.
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])

    # --- SECURITY: FACULTY LOCK ---
    # Ensure Admin can only view proposals from their own faculty
    if user.faculty != proposal.cycle.faculty:
        flash(
            f"Access Denied: You can only manage proposals for {user.faculty}.", "error"
        )
        return redirect(url_for("admin.admin_proposal_management"))

    # Check if proposal is still a Draft
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
    """
    Assign a Reviewer and an HOD to a proposal.
    Moves status from 'Submitted' to 'Under Review'.
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])

    # --- SECURITY: FACULTY LOCK ---
    if user.faculty != proposal.cycle.faculty:
        flash(
            f"Access Denied: You cannot assign evaluators for {proposal.cycle.faculty}.",
            "error",
        )
        return redirect(url_for("admin.admin_proposal_management"))

    # Only load evaluators from the same faculty as the researcher
    researcher_faculty = proposal.researcher.user_info.faculty

    if request.method == "POST":
        # 1. Assign Reviewer
        reviewer_id = request.form.get("reviewer_id")
        if reviewer_id:
            proposal.assigned_reviewer_id = reviewer_id
            # Notify Reviewer
            reviewer_user = Reviewer.query.get(reviewer_id).user_info
            send_notification(
                reviewer_user.mmu_id,
                f"Assignment: Screen '{proposal.title}'",
                url_for("reviewer.reviewer_view_proposals"),
                session["user_id"],
            )

        # 2. Assign HOD
        hod_id = request.form.get("hod_id")
        if hod_id:
            proposal.assigned_hod_id = hod_id

        # 3. Update Status
        proposal.status = "Under Review"
        db.session.commit()
        flash("Evaluators assigned successfully.", "success")
        return redirect(
            url_for("admin.admin_view_proposal", proposal_id=proposal.proposal_id)
        )

    # Fetch available reviewers and HODs for dropdowns
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
    """
    Set the final project submission deadline after a grant is approved.
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])

    # --- SECURITY: FACULTY LOCK ---
    if user.faculty != proposal.cycle.faculty:
        flash(
            f"Access Denied: You cannot manage deadlines for {proposal.cycle.faculty}.",
            "error",
        )
        return redirect(url_for("admin.admin_proposal_management"))

    # Ensure proposal is actually approved before setting deadlines
    if proposal.status != "Approved":
        flash(
            "Action Locked: You cannot set a final deadline until the HOD approves the grant.",
            "error",
        )
        return redirect(url_for("admin.admin_view_proposal", proposal_id=proposal_id))

    if request.method == "POST":
        final_date = request.form.get("final_deadline")
        if final_date:
            # Check if deadline entry already exists
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

            # Notify Researcher
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


# ==============================================================================
# 6. BUDGET TRACKING
# ==============================================================================


@admin_bp.route("/admin/budget", methods=["GET", "POST"])
def admin_budget_tracking():
    """
    Manages System Budget (Adding funds and viewing usage).
    Displays 'Money In' (Budget) vs 'Money Out' (Grants Awarded).
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    # --- HANDLE ADDING FUNDS ---
    if request.method == "POST":
        try:
            amount = float(request.form["amount"])
            description = request.form["description"]

            # Record the budget injection
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

    # --- CALCULATE FINANCIALS ---
    total_budget_in = db.session.query(func.sum(Budget.amount)).scalar() or 0.0
    total_grants_out = db.session.query(func.sum(Grant.grant_amount)).scalar() or 0.0
    current_balance = total_budget_in - total_grants_out

    # Get transaction history
    budget_history = Budget.query.order_by(Budget.created_at.desc()).all()

    # --- PAGINATION FOR AWARDED GRANTS ---
    page = request.args.get("page", 1, type=int)
    per_page = 6

    active_grants = Grant.query.order_by(Grant.award_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        "admin_budget_tracking.html",
        user=User.query.get(session["user_id"]),
        total_fund=total_budget_in,
        total_allocated=total_grants_out,
        current_balance=current_balance,
        budget_history=budget_history,
        active_grants=active_grants,
    )


@admin_bp.route("/admin/budget/edit/<int:budget_id>", methods=["POST"])
def admin_edit_budget(budget_id):
    """
    Edits an existing budget entry.
    Restricted to the admin who created the entry.
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    budget = Budget.query.get_or_404(budget_id)

    # Audit Check: Ensure only the creator can edit
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
    """
    Deletes a budget entry.
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    budget = Budget.query.get_or_404(budget_id)
    db.session.delete(budget)
    db.session.commit()
    flash("Budget entry deleted.", "success")

    return redirect(url_for("admin.admin_budget_tracking"))


# ==============================================================================
# 7. SYSTEM CONFIGURATION (FACULTIES & AREAS)
# ==============================================================================


@admin_bp.route("/admin/system_data", methods=["GET", "POST"])
def admin_system_data():
    """
    Manages system-wide data: Faculties and Research Areas.
    Admin can add new entries here.
    """
    if session.get("role") != "Admin":
        return redirect(url_for("admin.admin_login"))

    if request.method == "POST":
        type_added = request.form.get("type")
        name_added = request.form.get("name").strip()

        # Add Faculty
        if type_added == "faculty":
            if Faculty.query.filter_by(name=name_added).first():
                flash(f"Error: Faculty '{name_added}' exists.", "error")
            else:
                db.session.add(Faculty(name=name_added))
                db.session.commit()
                flash("Faculty added.", "success")

        # Add Research Area
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
    """
    Edits the name of an existing Faculty or Research Area.
    """
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
