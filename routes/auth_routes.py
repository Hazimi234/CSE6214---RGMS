from flask import Blueprint, render_template, redirect, url_for, session, flash
from models import db, Notification, User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def main_login():
    return render_template("main_login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.main_login"))


@auth_bp.route("/notifications")
def view_notifications():
    if "user_id" not in session:
        return redirect(url_for("auth.main_login"))
    user_id = session["user_id"]
    notifs = (
        Notification.query.filter_by(recipient_id=user_id)
        .order_by(Notification.timestamp.desc())
        .all()
    )
    return render_template(
        "notifications.html", notifications=notifs, user=User.query.get(user_id)
    )


@auth_bp.route("/notifications/click/<int:notif_id>")
def click_notification(notif_id):
    if "user_id" not in session:
        return redirect(url_for("auth.main_login"))
    notif = Notification.query.get_or_404(notif_id)
    if notif.recipient_id != session["user_id"]:
        return redirect(url_for("auth.view_notifications"))
    notif.is_read = True
    db.session.commit()
    return (
        redirect(notif.link)
        if notif.link
        else redirect(url_for("auth.view_notifications"))
    )


@auth_bp.route("/notifications/mark_all_read")
def mark_all_notifications_read():
    if "user_id" not in session:
        return redirect(url_for("auth.main_login"))
    user_id = session["user_id"]
    unread = Notification.query.filter_by(recipient_id=user_id, is_read=False).all()
    for n in unread:
        n.is_read = True
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("auth.view_notifications"))
