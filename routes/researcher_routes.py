from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from models import (
    db,
    User,
    Researcher,
    Grant,
    Proposal,
    GrantCycle,
    ProposalVersion,
    ProgressReport,
    HOD,
    Deadline,
    Faculty,
    ResearchArea,
    Notification,
)
from utils import (
    get_myt_date,
    get_myt_time,
    save_document,
    allowed_file,
    send_notification,
    update_user_profile,
)

researcher_bp = Blueprint("researcher", __name__)


@researcher_bp.route("/researcher/login", methods=["POST", "GET"])
def researcher_login():
    if request.method == "POST":
        user = User.query.filter_by(
            mmu_id=request.form["mmu_id"], user_role="Researcher"
        ).first()
        if user and user.check_password(request.form["password"]):
            session["user_id"] = user.mmu_id
            session["role"] = "Researcher"
            return redirect(url_for("researcher.researcher_dashboard"))
        else:
            flash("Invalid credentials.", "error")
    return render_template("researcher_login.html")


@researcher_bp.route("/researcher/dashboard")
def researcher_dashboard():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher.researcher_login"))
    user = User.query.get(session["user_id"])
    researcher = Researcher.query.filter_by(mmu_id=user.mmu_id).first()

    approved_count = Proposal.query.filter_by(
        researcher_id=researcher.researcher_id, status="Approved"
    ).count()

    # ADDED unread_notifs HERE
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


@researcher_bp.route("/researcher/profile", methods=["GET", "POST"])
def researcher_profile():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher.researcher_login"))
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("researcher.researcher_profile"))
    return render_template("researcher_profile.html", user=user)


@researcher_bp.route("/researcher/apply")
def researcher_apply_list():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher.researcher_login"))

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


@researcher_bp.route("/researcher/apply/<int:cycle_id>", methods=["GET", "POST"])
def researcher_submit_form(cycle_id):
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher.researcher_login"))

    cycle = GrantCycle.query.get_or_404(cycle_id)
    user = User.query.get(session["user_id"])
    researcher = Researcher.query.filter_by(mmu_id=user.mmu_id).first()

    # Eligibility Check
    if user.faculty != cycle.faculty:
        flash(f"Access Denied: Ineligible for {cycle.faculty} grants.", "error")
        return redirect(url_for("researcher.researcher_apply_list"))

    # Cycle Deadline Check
    cycle_closed = cycle.end_date < get_myt_date() or not cycle.is_open

    proposal_id = request.args.get("proposal_id") or request.form.get("proposal_id")
    proposal = Proposal.query.get(proposal_id) if proposal_id else None

    if request.method == "POST":
        if cycle_closed:
            flash("Error: This grant cycle is closed.", "error")
            return redirect(url_for("researcher.researcher_apply_list"))

        current_status = (
            "Draft" if request.form.get("action") == "draft" else "Submitted"
        )

        # --- FILE VALIDATION FIX ---
        file = request.files.get("proposal_file")
        doc_filename = None
        
        if file and file.filename != "":
            if allowed_file(file.filename):
                doc_filename = save_document(file)
            else:
                # STOP HERE if file is invalid (e.g., PNG)
                flash("Error: Invalid file format. Only PDF and DOCX are allowed.", "error")
                return redirect(request.url) # Reload page, do not save to DB

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
                    url_for(
                        "admin.admin_view_proposal", proposal_id=proposal.proposal_id
                    ),
                    session["user_id"],
                )
        flash(f"Proposal {current_status.lower()}ed successfully!", "success")
        return redirect(url_for("researcher.researcher_my_proposals"))

    return render_template(
        "researcher_submit_form.html",
        cycle=cycle,
        user=user,
        proposal=proposal,
        research_areas=ResearchArea.query.all(),
        cycle_closed=cycle_closed,
    )


@researcher_bp.route("/researcher/revert/<int:proposal_id>/<int:version_id>")
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
            "researcher.researcher_submit_form",
            cycle_id=proposal.cycle_id,
            proposal_id=proposal.proposal_id,
        )
    )


@researcher_bp.route("/researcher/proposal_status")
def researcher_my_proposals():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher.researcher_login"))
    user = User.query.get(session["user_id"])
    researcher = (
        Researcher.query.filter_by(mmu_id=user.mmu_id)
        .order_by(Researcher.researcher_id.desc())
        .first()
    )
    if not researcher:
        flash("Error: Researcher profile not found.", "error")
        return redirect(url_for("researcher.researcher_dashboard"))
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


@researcher_bp.route("/researcher/withdraw/<int:proposal_id>", methods=["POST"])
def researcher_withdraw_proposal(proposal_id):
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher.researcher_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    user = User.query.get(session["user_id"])
    proposal.status = "Withdrawn"
    db.session.commit()
    admin = User.query.filter_by(user_role="Admin").first()
    if admin:
        msg = f"Proposal Withdrawn: '{proposal.title}' by {user.name}."
        link = url_for("admin.admin_view_proposal", proposal_id=proposal.proposal_id)
        send_notification(
            recipient_id=admin.mmu_id, message=msg, link=link, sender_id=user.mmu_id
        )
    flash("Proposal withdrawn successfully.", "success")
    return redirect(url_for("researcher.researcher_my_proposals"))


@researcher_bp.route(
    "/researcher/update_progress/<int:proposal_id>", methods=["GET", "POST"]
)
def researcher_update_progress(proposal_id):
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher.researcher_login"))
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
                url_for(
                    "researcher.researcher_update_progress",
                    proposal_id=proposal.proposal_id,
                )
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
                    "hod.hod_view_progress_reports", proposal_id=proposal.proposal_id
                )
                send_notification(
                    hod.user_info.mmu_id, msg, link, sender_id=user.mmu_id
                )
            flash("Progress report submitted successfully.", "success")
            return redirect(url_for("researcher.researcher_my_proposals"))
        else:
            flash("Error: Valid report file required.", "error")
    return render_template(
        "researcher_update_progress.html",
        proposal=proposal,
        user=user,
        deadline_passed=deadline_passed,
        final_deadline=final_deadline,
    )


@researcher_bp.route(
    "/researcher/request_extension/<int:proposal_id>", methods=["POST"]
)
def researcher_request_extension(proposal_id):
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher.researcher_login"))
    proposal = Proposal.query.get_or_404(proposal_id)
    reason = request.form.get("extension_reason")
    user = User.query.get(session["user_id"])
    admin = User.query.filter_by(user_role="Admin").first()
    if admin:
        msg = f"Extension Request: {user.name} requests time for '{proposal.title}'. Reason: {reason}"
        link = url_for("admin.admin_view_proposal", proposal_id=proposal.proposal_id)
        send_notification(admin.mmu_id, msg, link, sender_id=session["user_id"])
    flash("Extension request sent to Admin successfully.", "success")
    return redirect(url_for("researcher.researcher_my_proposals"))
