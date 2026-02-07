import os
import secrets
import json
from datetime import datetime, timedelta, timezone
from flask import current_app, flash, url_for
from models import db, Notification, Researcher, Proposal, Deadline

# ==========================================
# TIMEZONE HELPERS (Malaysia UTC+8)
# ==========================================
def get_myt_time():
    return datetime.now(timezone(timedelta(hours=8)))

def get_myt_date():
    return get_myt_time().date()

# ==========================================
# FILE HELPERS
# ==========================================
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]

def save_document(form_file):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_file.filename)
    doc_fn = random_hex + f_ext
    doc_path = os.path.join(current_app.config["UPLOAD_FOLDER_DOCS"], doc_fn)
    form_file.save(doc_path)
    return doc_fn

def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(current_app.config["UPLOAD_FOLDER"], picture_fn)
    form_picture.save(picture_path)
    return picture_fn

# ==========================================
# NOTIFICATION HELPER
# ==========================================
def send_notification(recipient_id, message, link=None, sender_id=None):
    # Timestamp handles itself via Models default
    notif = Notification(recipient_id=recipient_id, sender_id=sender_id, message=message, link=link)
    db.session.add(notif)
    db.session.commit()

def check_deadlines_and_notify(user):
    """
    Checks if the Final Submission Deadline is approaching for Researchers.
    Uses Malaysia Time for date comparisons.
    """
    if user.user_role == "Researcher":
        researcher = Researcher.query.filter_by(mmu_id=user.mmu_id).first()
        if not researcher: return

        # Check Active Proposals with a Final Deadline Set
        active_proposals = Proposal.query.filter_by(researcher_id=researcher.researcher_id, status="Approved").all()

        for prop in active_proposals:
            deadline = Deadline.query.filter_by(proposal_id=prop.proposal_id, deadline_type="Final Submission").first()
            
            if deadline and deadline.due_date:
                days_left = (deadline.due_date - get_myt_date()).days
                msg = None
                
                if days_left < 0:
                    msg = f"URGENT: Final submission for '{prop.title}' is OVERDUE (Due: {deadline.due_date})."
                elif 0 <= days_left <= 7: # Notify 1 week before
                    msg = f"Reminder: Final submission for '{prop.title}' is due in {days_left} days."
                
                if msg:
                    # Avoid duplicate notifications
                    if not Notification.query.filter_by(recipient_id=user.mmu_id, message=msg).first():
                        # We need to import 'researcher_bp' endpoint names carefully or just use string
                        # Using string endpoint name 'researcher.researcher_submit_form' assuming blueprint name is 'researcher'
                        send_notification(user.mmu_id, msg, url_for('researcher.researcher_submit_form', cycle_id=prop.cycle_id, proposal_id=prop.proposal_id), "System")

# ==========================================
# PROFILE HELPER
# ==========================================
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
            flash("Error: New password cannot be the same as your current password.", "error")
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