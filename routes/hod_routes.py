from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from sqlalchemy import func
from models import (
    db,
    User,
    HOD,
    Proposal,
    Grant,
    Researcher,
    Budget,
    ProgressReport,
    Faculty,
)
from utils import update_user_profile, send_notification

hod_bp = Blueprint("hod", __name__)


@hod_bp.route("/hod/login", methods=["POST", "GET"])
def hod_login():
    if request.method == "POST":
        user = User.query.filter_by(
            mmu_id=request.form["mmu_id"], user_role="HOD"
        ).first()
        if user and user.check_password(request.form["password"]):
            session["user_id"] = user.mmu_id
            session["role"] = "HOD"
            return redirect(url_for("hod.hod_dashboard"))
        else:
            flash("Invalid credentials.", "error")
    return render_template("hod_login.html")


@hod_bp.route("/hod/dashboard")
def hod_dashboard():
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
    return render_template(
        "hod_dashboard.html",
        stats={"approvals_pending": 8},
        user=User.query.get(session["user_id"]),
    )


@hod_bp.route("/hod/profile", methods=["GET", "POST"])
def hod_profile():
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("hod.hod_profile"))
    return render_template("hod_profile.html", user=user)


@hod_bp.route("/hod/proposals")
def hod_assigned_proposals():
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
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


@hod_bp.route("/hod/proposals/view/<int:proposal_id>")
def hod_view_proposal(proposal_id):
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    return render_template(
        "hod_view_proposal.html",
        proposal=proposal,
        user=User.query.get(session["user_id"]),
    )


@hod_bp.route("/hod/proposals/decision/<int:proposal_id>", methods=["POST"])
def hod_proposal_decision(proposal_id):
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])
    current_hod = HOD.query.filter_by(mmu_id=user.mmu_id).first()
    if not current_hod or proposal.assigned_hod_id != current_hod.hod_id:
        flash(
            "Error: You are not authorized to make decisions on this proposal.", "error"
        )
        return redirect(url_for("hod.hod_assigned_proposals"))
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
            url_for("researcher.researcher_my_proposals"),
            sender_id=user.mmu_id,
        )
        admin = User.query.filter_by(user_role="Admin").first()
        if admin:
            msg = f"Update: Proposal '{proposal.title}' was REJECTED by the HOD."
            link = url_for(
                "admin.admin_view_proposal", proposal_id=proposal.proposal_id
            )
            send_notification(admin.mmu_id, msg, link, sender_id=user.mmu_id)
    db.session.commit()
    return redirect(url_for("hod.hod_view_proposal", proposal_id=proposal.proposal_id))


@hod_bp.route("/hod/grant_allocation")
def hod_grant_allocation():
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
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


@hod_bp.route("/hod/grant_allocation/update", methods=["POST"])
def hod_update_grant():
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
    proposal_id = request.form.get("proposal_id")
    new_amount = float(request.form.get("amount"))
    if new_amount < 0:
        flash("Error: Grant amount cannot be negative.", "error")
        return redirect(url_for("hod.hod_grant_allocation"))
    proposal = Proposal.query.get_or_404(proposal_id)
    grant = Grant.query.filter_by(proposal_id=proposal.proposal_id).first()
    user = User.query.get(session["user_id"])
    if not grant:
        flash("Error: Grant record not found.", "error")
        return redirect(url_for("hod.hod_grant_allocation"))
    grant.grant_amount = new_amount
    if proposal.status == "Pending Grant":
        proposal.status = "Approved"
    db.session.commit()
    flash(f"Grant allocated successfully: RM {new_amount:,.2f}", "success")
    send_notification(
        proposal.researcher.user_info.mmu_id,
        f"Update: Your proposal '{proposal.title}' has been APPROVED.",
        url_for("researcher.researcher_my_proposals"),
        sender_id=user.mmu_id,
    )
    admin = User.query.filter_by(user_role="Admin").first()
    if admin:
        msg = f"Action Required: Proposal '{proposal.title}' is fully APPROVED. Please set the Final Deadline."
        link = url_for("admin.admin_view_proposal", proposal_id=proposal.proposal_id)
        send_notification(admin.mmu_id, msg, link, sender_id=user.mmu_id)
    return redirect(url_for("hod.hod_grant_allocation"))


@hod_bp.route("/hod/grant_budget")
def hod_grant_budget():
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
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


@hod_bp.route("/hod/assigned_research")
def hod_assigned_research():
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
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


@hod_bp.route("/hod/project/update_status", methods=["POST"])
def hod_update_project_status():
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
    proposal_id = request.form.get("proposal_id")
    new_status = request.form.get("status")
    proposal = Proposal.query.get_or_404(proposal_id)
    current_hod = HOD.query.filter_by(mmu_id=session["user_id"]).first()
    if not current_hod or proposal.assigned_hod_id != current_hod.hod_id:
        flash("Error: Permission denied.", "error")
        return redirect(url_for("hod.hod_assigned_research"))
    if new_status:
        proposal.status = new_status
        db.session.commit()
        flash(f"Project '{proposal.title}' status updated to {new_status}.", "success")
    next_page = request.form.get("next_page")
    if next_page:
        return redirect(next_page)
    return redirect(url_for("hod.hod_assigned_research"))


@hod_bp.route("/hod/assigned_research/progress/<int:proposal_id>")
def hod_view_progress_reports(proposal_id):
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])
    current_hod = HOD.query.filter_by(mmu_id=user.mmu_id).first()
    if not current_hod or proposal.assigned_hod_id != current_hod.hod_id:
        flash("Error: Access Denied.", "error")
        return redirect(url_for("hod.hod_assigned_research"))
    reports = (
        ProgressReport.query.filter_by(proposal_id=proposal_id)
        .order_by(ProgressReport.submission_date.desc())
        .all()
    )
    return render_template(
        "hod_view_progress_reports.html", proposal=proposal, reports=reports, user=user
    )


@hod_bp.route("/hod/progress_report/decision", methods=["POST"])
def hod_progress_report_decision():
    if session.get("role") != "HOD":
        return redirect(url_for("hod.hod_login"))
    report_id = request.form.get("report_id")
    decision = request.form.get("decision")
    feedback = request.form.get("feedback")
    report = ProgressReport.query.get_or_404(report_id)
    current_hod = HOD.query.filter_by(mmu_id=session["user_id"]).first()
    if not current_hod or report.proposal.assigned_hod_id != current_hod.hod_id:
        flash("Error: Access Denied.", "error")
        return redirect(url_for("hod.hod_dashboard"))
    report.hod_feedback = feedback
    if decision == "validate":
        report.status = "Validated"
        flash("Progress report validated successfully.", "success")
        send_notification(
            report.proposal.researcher.user_info.mmu_id,
            f"Your progress report '{report.title}' has been VALIDATED.",
            url_for("researcher.researcher_my_proposals"),
            sender_id=session["user_id"],
        )
    elif decision == "revision":
        report.status = "Requires Revision"
        flash("Progress report returned for revision.", "info")
        send_notification(
            report.proposal.researcher.user_info.mmu_id,
            f"Action Required: Revision requested for report '{report.title}'.",
            url_for("researcher.researcher_my_proposals"),
            sender_id=session["user_id"],
        )
    db.session.commit()
    return redirect(
        url_for("hod.hod_view_progress_reports", proposal_id=report.proposal_id)
    )
