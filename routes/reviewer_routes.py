import json
from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from models import (
    Researcher,
    db,
    User,
    Reviewer,
    Proposal,
    HOD,
    ResearchArea,
    Researcher,
    Notification,
)
from utils import (
    update_user_profile,
    send_notification,
    get_myt_date,
)
from datetime import date

reviewer_bp = Blueprint("reviewer", __name__)


# Handles Reviewer login
@reviewer_bp.route("/reviewer/login", methods=["POST", "GET"])
def reviewer_login():
    if request.method == "POST":
        user = User.query.filter_by(
            mmu_id=request.form["mmu_id"], user_role="Reviewer"
        ).first()
        if user and user.check_password(request.form["password"]):
            session["user_id"] = user.mmu_id
            session["role"] = "Reviewer"
            return redirect(url_for("reviewer.reviewer_dashboard"))
        else:
            flash("Invalid credentials.", "error")
    return render_template("reviewer_login.html")


# Displays dashboard with pending task counts
@reviewer_bp.route("/reviewer/dashboard")
def reviewer_dashboard():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))
    user = User.query.get(session["user_id"])

    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()
    stats = {"pending_screenings": 0, "pending_reviews": 0}
    if reviewer_profile:
        # Count proposals waiting for initial screening
        stats["pending_screenings"] = Proposal.query.filter(
            Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
            Proposal.status.in_(["Submitted", "Under Review", "Under Screening"]),
        ).count()
        # Count proposals passed screening but not yet scored
        stats["pending_reviews"] = Proposal.query.filter(
            Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
            Proposal.status == "Passed Screening",
            Proposal.review_score == None,
        ).count()
    return render_template("reviewer_dashboard.html", stats=stats, user=user)


# Manages Reviewer profile view and updates
@reviewer_bp.route("/reviewer/profile", methods=["GET", "POST"])
def reviewer_profile():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("reviewer.reviewer_profile"))
    return render_template("reviewer_profile.html", user=user)


# Lists all assigned proposals (pending screening & history)
@reviewer_bp.route("/reviewer/proposals")
def reviewer_view_proposals():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))
    user = User.query.get(session["user_id"])
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()
    if not reviewer_profile:
        flash("Error: Reviewer profile not found.", "error")
        return redirect(url_for("reviewer.reviewer_dashboard"))

    # Get filter parameters
    search_query = request.args.get("search", "")
    filter_area = request.args.get("area", "")
    filter_status = request.args.get("status", "")
    sort_option = request.args.get("sort", "newest")
    page = request.args.get("page", 1, type=int)
    per_page = 7

    # Base Queries
    pending_query = Proposal.query.filter(
        Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
        Proposal.status.in_(["Submitted", "Under Review", "Under Screening"]),
    )

    history_query = Proposal.query.filter(
        Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
        ~Proposal.status.in_(["Submitted", "Under Review", "Under Screening"]),
    )

    # Apply Filters
    if search_query:
        pending_query = pending_query.filter(Proposal.title.ilike(f"%{search_query}%"))
        history_query = history_query.filter(Proposal.title.ilike(f"%{search_query}%"))

    if filter_area and filter_area != "all":
        pending_query = pending_query.filter(Proposal.research_area == filter_area)
        history_query = history_query.filter(Proposal.research_area == filter_area)

    if filter_status and filter_status != "all":
        pending_query = pending_query.filter(Proposal.status == filter_status)
        history_query = history_query.filter(Proposal.status == filter_status)

    # Apply Sorting
    if sort_option == "oldest":
        pending_query = pending_query.order_by(Proposal.proposal_id.asc())
        history_query = history_query.order_by(Proposal.proposal_id.asc())
    elif sort_option == "title_asc":
        pending_query = pending_query.order_by(Proposal.title.asc())
        history_query = history_query.order_by(Proposal.title.asc())
    elif sort_option == "status_asc":
        pending_query = pending_query.order_by(Proposal.status.asc())
        history_query = history_query.order_by(Proposal.status.asc())
    else:
        pending_query = pending_query.order_by(Proposal.proposal_id.desc())
        history_query = history_query.order_by(Proposal.proposal_id.desc())

    # Execute queries
    pending_proposals = pending_query.all()
    history_pagination = history_query.paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        "reviewer_proposals.html",
        pending_proposals=pending_proposals,
        history_proposals=history_pagination.items,
        history_pagination=history_pagination,
        user=user,
        research_areas=ResearchArea.query.all(),
        current_search=search_query,
        current_area=filter_area,
        current_status=filter_status,
        current_sort=sort_option,
    )


# Handles the initial screening decision (Eligible/Not Eligible/Return)
@reviewer_bp.route("/reviewer/screen/<int:proposal_id>", methods=["GET", "POST"])
def reviewer_screen_proposal(proposal_id):
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))
    
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()
    
    # Access control check
    if (
        not reviewer_profile
        or proposal.assigned_reviewer_id != reviewer_profile.reviewer_id
    ):
        flash("Access Denied.", "error")
        return redirect(url_for("reviewer.reviewer_dashboard"))
        
    active_statuses = ["Submitted", "Under Review", "Under Screening"]
    readonly = proposal.status not in active_statuses
    
    if request.method == "POST":
        if readonly:
            flash(
                "Action not allowed. This proposal has already been screened.", "error"
            )
            return redirect(url_for("reviewer.reviewer_view_proposals"))
            
        decision = request.form.get("decision")
        
        if decision == "eligible":
            proposal.status = "Passed Screening"
            flash("Proposal Passed Screening. Proceed to evaluation.", "success")
            # Notify Researcher
            if proposal.researcher:
                msg = f"Screening Update: Your proposal '{proposal.title}' Passed Screening."
                link = url_for("researcher.researcher_my_proposals")
                send_notification(
                    proposal.researcher.user_info.mmu_id,
                    msg,
                    link,
                    sender_id=user.mmu_id,
                )
                
        elif decision == "not_eligible":
            proposal.status = "Failed Screening"
            # Determine msg based on cycle status
            if proposal.cycle and proposal.cycle.end_date >= get_myt_date():
                msg = f"Screening Update: Your proposal '{proposal.title}' Failed Screening. Cycle OPEN."
                flash("Proposal marked as Failed Screening.", "warning")
            else:
                msg = f"Screening Update: Your proposal '{proposal.title}' Failed Screening. Cycle CLOSED."
                flash("Proposal marked as Failed Screening. Cycle is closed.", "error")
            
            link = url_for("researcher.researcher_my_proposals")
            if proposal.researcher:
                send_notification(
                    proposal.researcher.user_info.mmu_id,
                    msg,
                    link,
                    sender_id=user.mmu_id,
                )
                
        elif decision == "not_interested":
            proposal.status = "Return for Reassignment"
            # Notify Admin to reassign
            admin = User.query.filter_by(user_role="Admin").first()
            if admin:
                msg = f"Return Alert: Reviewer {user.name} declined proposal '{proposal.title}'."
                link = url_for(
                    "admin.admin_view_proposal", proposal_id=proposal.proposal_id
                )
                send_notification(admin.mmu_id, msg, link, sender_id=user.mmu_id)
            flash("Task declined. Returned to Admin.", "info")
            
        db.session.commit()
        return redirect(url_for("reviewer.reviewer_view_proposals"))
        
    return render_template(
        "reviewer_screen_proposal.html", proposal=proposal, user=user, readonly=readonly
    )


# Lists proposals ready for scoring (Passed Screening) and history
@reviewer_bp.route("/reviewer/evaluation_list")
def reviewer_evaluation_list():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))
    user = User.query.get(session["user_id"])
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()

    # Pagination & Filters
    page = request.args.get("page", 1, type=int) 
    history_page = request.args.get("history_page", 1, type=int) 
    search_query = request.args.get("search", "")
    filter_area = request.args.get("area", "")
    sort_option = request.args.get("sort", "newest")

    # Pending Query
    query_pending = Proposal.query.filter(
        Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
        Proposal.status == "Passed Screening",
        Proposal.review_score == None,
    )

    # History Query
    query_history = Proposal.query.filter(
        Proposal.assigned_reviewer_id == reviewer_profile.reviewer_id,
        Proposal.review_score != None,
    )

    # Filters
    if search_query:
        query_pending = query_pending.filter(Proposal.title.ilike(f"%{search_query}%"))
        query_history = query_history.filter(Proposal.title.ilike(f"%{search_query}%"))

    if filter_area and filter_area != "all":
        query_pending = query_pending.filter(Proposal.research_area == filter_area)
        query_history = query_history.filter(Proposal.research_area == filter_area)

    # Sorting
    if sort_option == "oldest":
        query_pending = query_pending.order_by(Proposal.proposal_id.asc())
        query_history = query_history.order_by(Proposal.proposal_id.asc())
    elif sort_option == "title_asc":
        query_pending = query_pending.order_by(Proposal.title.asc())
        query_history = query_history.order_by(Proposal.title.asc())
    else:
        query_pending = query_pending.order_by(Proposal.proposal_id.desc())
        query_history = query_history.order_by(Proposal.proposal_id.desc())

    # Pagination execution
    pagination = query_pending.paginate(page=page, per_page=8, error_out=False)
    history_pagination = query_history.paginate(
        page=history_page, per_page=8, error_out=False
    )

    return render_template(
        "reviewer_evaluation_list.html",
        proposals=pagination.items,
        pagination=pagination,
        history=history_pagination.items,
        history_pagination=history_pagination,
        user=user,
        research_areas=ResearchArea.query.all(),
        current_search=search_query,
        current_area=filter_area,
        current_sort=sort_option,
    )


# Handles scoring form submission (Draft/Submit)
@reviewer_bp.route("/reviewer/evaluate/<int:proposal_id>", methods=["GET", "POST"])
def reviewer_evaluate_proposal(proposal_id):
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))

    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])

    # Determine read-only status
    readonly = False
    if proposal.status == "Passed Screening":
        readonly = False
    elif proposal.review_score is not None:
        readonly = True
    else:
        flash(f"Error: Cannot evaluate. Status: {proposal.status}", "error")
        return redirect(url_for("reviewer.reviewer_view_proposals"))

    # Load draft answers if available
    saved_answers = {}
    if proposal.review_draft:
        try:
            saved_answers = json.loads(proposal.review_draft)
        except:
            saved_answers = {}

    if request.method == "POST":
        action = request.form.get("action")

        # Collect scores from form
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
                url_for("reviewer.reviewer_evaluate_proposal", proposal_id=proposal_id)
            )
            
        elif action == "submit":
            if not all_answered:
                flash("Error: Answer all 20 questions to submit.", "error")
                return redirect(
                    url_for("reviewer.reviewer_evaluate_proposal", proposal_id=proposal_id)
                )

            proposal.review_score = total_score
            proposal.review_feedback = feedback
            proposal.review_draft = json.dumps(data)

            # Determine Outcome
            if total_score >= 75:
                proposal.status = "Pending HOD Approval"
                flash(f"Review Submitted ({total_score}). Forwarded to HOD.", "success")
                
                # Notify HOD
                if proposal.assigned_hod_id:
                    hod = HOD.query.get(proposal.assigned_hod_id)
                    msg = f"Action Required: Proposal '{proposal.title}' passed review ({total_score}/100)."
                    link = url_for("hod.hod_dashboard")
                    send_notification(hod.user_info.mmu_id, msg, link, sender_id=user.mmu_id)
                    
                # Notify Researcher
                if proposal.researcher:
                    msg = f"Update: '{proposal.title}' passed review ({total_score}/100). Pending HOD."
                    link = url_for("researcher.researcher_my_proposals")
                    send_notification(proposal.researcher.user_info.mmu_id, msg, link, sender_id=user.mmu_id)
            else:
                proposal.status = "Rejected"
                flash(f"Review Submitted ({total_score}). Proposal Rejected.", "warning")
                
                if proposal.researcher:
                    msg = f"Update: '{proposal.title}' was rejected (Score: {total_score}/100)."
                    link = url_for("researcher.researcher_my_proposals")
                    send_notification(proposal.researcher.user_info.mmu_id, msg, link, sender_id=user.mmu_id)
                    
            db.session.commit()
            return redirect(url_for("reviewer.reviewer_evaluation_list"))

    return render_template(
        "reviewer_evaluate_proposal.html",
        proposal=proposal,
        user=user,
        saved_answers=saved_answers,
        readonly=readonly,
        is_overdue=False,
    )
