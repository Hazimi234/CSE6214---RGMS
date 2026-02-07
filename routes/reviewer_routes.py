import json
from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from models import db, User, Reviewer, Proposal, HOD, ResearchArea
from utils import (
    check_deadlines_and_notify,
    update_user_profile,
    send_notification,
    get_myt_date,
)

reviewer_bp = Blueprint("reviewer", __name__)


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


@reviewer_bp.route("/reviewer/dashboard")
def reviewer_dashboard():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))
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


@reviewer_bp.route("/reviewer/profile", methods=["GET", "POST"])
def reviewer_profile():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("reviewer.reviewer_profile"))
    return render_template("reviewer_profile.html", user=user)


@reviewer_bp.route("/reviewer/proposals")
def reviewer_view_proposals():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))
    user = User.query.get(session["user_id"])
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()
    if not reviewer_profile:
        flash("Error: Reviewer profile not found.", "error")
        return redirect(url_for("reviewer.reviewer_dashboard"))
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


@reviewer_bp.route("/reviewer/screen/<int:proposal_id>", methods=["GET", "POST"])
def reviewer_screen_proposal(proposal_id):
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])
    reviewer_profile = Reviewer.query.filter_by(mmu_id=user.mmu_id).first()
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
            admin = User.query.filter_by(user_role="Admin").first()
            if admin:
                msg = f"Return Alert: Reviewer {user.name} declined proposal assignment for '{proposal.title}'."
                link = url_for(
                    "admin.admin_view_proposal", proposal_id=proposal.proposal_id
                )
                send_notification(admin.mmu_id, msg, link, sender_id=user.mmu_id)
            flash("Task declined. Proposal returned to Admin for reassignment.", "info")
        db.session.commit()
        return redirect(url_for("reviewer.reviewer_view_proposals"))
    return render_template(
        "reviewer_screen_proposal.html", proposal=proposal, user=user, readonly=readonly
    )


@reviewer_bp.route("/reviewer/evaluation_list")
def reviewer_evaluation_list():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))
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


@reviewer_bp.route("/reviewer/evaluate/<int:proposal_id>", methods=["GET", "POST"])
def reviewer_evaluate_proposal(proposal_id):
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer.reviewer_login"))
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
        return redirect(url_for("reviewer.reviewer_view_proposals"))
    saved_answers = {}
    if proposal.review_draft:
        try:
            saved_answers = json.loads(proposal.review_draft)
        except:
            saved_answers = {}
    if request.method == "POST":
        if readonly:
            flash("This proposal has already been submitted.", "error")
            return redirect(url_for("reviewer.reviewer_evaluation_list"))
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
                url_for("reviewer.reviewer_evaluate_proposal", proposal_id=proposal_id)
            )
        elif action == "submit":
            if not all_answered:
                flash("Error: You must answer all 20 questions to submit.", "error")
                return redirect(
                    url_for(
                        "reviewer.reviewer_evaluate_proposal", proposal_id=proposal_id
                    )
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
                        link = url_for("hod.hod_dashboard")
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
                link = url_for("researcher.researcher_my_proposals")
                send_notification(
                    proposal.researcher.user_info.mmu_id,
                    msg,
                    link,
                    sender_id=user.mmu_id,
                )
            db.session.commit()
            return redirect(url_for("reviewer.reviewer_evaluation_list"))
    return render_template(
        "reviewer_evaluate_proposal.html",
        proposal=proposal,
        user=user,
        saved_answers=saved_answers,
        readonly=readonly,
    )
