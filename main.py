import os
import secrets
from flask import Flask, redirect, url_for, render_template, request, session, flash
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from models import db, User, Admin, Researcher, Reviewer, HOD

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# Database & Upload Config
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
    basedir, "database.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# NEW: Folder to save images
app.config["UPLOAD_FOLDER"] = os.path.join(basedir, "static/profile_pics")

db.init_app(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)


# --- Helper Function to Save Images ---
def save_picture(form_picture):
    # Create a random hex name to prevent duplicate filenames
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.config["UPLOAD_FOLDER"], picture_fn)

    # Save the file
    form_picture.save(picture_path)
    return picture_fn


# --- Helper Function for Profile Updates (Reduces code repetition) ---
def update_user_profile(user, form, files):
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
            return False  # Failed
        elif user.check_password(new_password):
            flash(
                "Error: New password cannot be the same as your current password.",
                "error",
            )
            return False  # Failed
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


# --- Routes ---


@app.route("/")
def main_login():
    return render_template("main_login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main_login"))


# ==========================================
# 1. ADMIN ROUTES
# ==========================================
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
            # Store profile pic in session for easy access
            session["profile_image"] = user.profile_image
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid Admin credentials.", "error")

    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    # Refresh user data from DB to get the latest image
    user = User.query.get(session["user_id"])

    stats = {"pending_proposals": 12, "active_grants": 45, "total_users": 150}
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


# ==========================================
# USER MANAGEMENT (ADMIN ONLY)
# ==========================================


# 1. VIEW & FILTER USERS
@app.route("/admin/users")
def admin_user_management():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    # Get Filter Parameters
    search_query = request.args.get("search", "")
    filter_role = request.args.get("role", "")
    filter_faculty = request.args.get("faculty", "")

    # Start Query
    query = User.query

    # Apply Filters
    if search_query:
        query = query.filter(User.name.ilike(f"%{search_query}%"))
    if filter_role:
        query = query.filter_by(user_role=filter_role)
    if filter_faculty:
        query = query.filter_by(faculty=filter_faculty)

    # Execute Query
    users = query.all()

    return render_template(
        "admin_user_management.html",
        users=users,
        user=User.query.get(session["user_id"]),
    )


# 2. CREATE NEW USER
@app.route("/admin/users/create", methods=["GET", "POST"])
def admin_create_user():
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        faculty = request.form["faculty"]
        role = request.form["role"]

        # Check if user exists
        if User.query.filter_by(mmu_id=mmu_id).first():
            flash(f"Error: User with MMU ID {mmu_id} already exists.", "error")
            return redirect(url_for("admin_create_user"))

        if User.query.filter_by(email=email).first():
            flash(f"Error: Email {email} is already taken.", "error")
            return redirect(url_for("admin_create_user"))

        # Create User Object
        new_user = User(
            mmu_id=mmu_id, name=name, email=email, faculty=faculty, user_role=role
        )
        new_user.set_password(password)
        db.session.add(new_user)

        # Create Child Table Entry based on Role
        if role == "Researcher":
            db.session.add(Researcher(mmu_id=mmu_id))
        elif role == "Reviewer":
            db.session.add(Reviewer(mmu_id=mmu_id))
        elif role == "HOD":
            db.session.add(HOD(mmu_id=mmu_id))

        try:
            db.session.commit()
            flash(f"User {name} ({role}) created successfully!", "success")
            return redirect(url_for("admin_user_management"))
        except:
            db.session.rollback()
            flash("Database Error: Could not create user.", "error")

    return render_template(
        "admin_create_user.html", user=User.query.get(session["user_id"])
    )


# 3. EDIT USER
@app.route("/admin/users/edit/<int:user_id>", methods=["GET", "POST"])
def admin_edit_user(user_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    target_user = User.query.get_or_404(user_id)

    # Restriction: Admin cannot edit other Admins (or themselves via this route)
    if target_user.user_role == "Admin":
        flash("Action Not Allowed: You cannot edit Admin accounts.", "error")
        return redirect(url_for("admin_user_management"))

    if request.method == "POST":
        target_user.name = request.form["name"]
        target_user.email = request.form["email"]
        target_user.phone_number = request.form["phone_number"]
        target_user.faculty = request.form["faculty"]  # Admin allowed to change this

        # Password update (optional)
        new_password = request.form["password"]
        if new_password:
            target_user.set_password(new_password)

        try:
            db.session.commit()
            flash("User details updated successfully.", "success")
            return redirect(url_for("admin_user_management"))
        except:
            flash("Error updating user. Email might be duplicate.", "error")

    return render_template(
        "admin_edit_user.html",
        target_user=target_user,
        user=User.query.get(session["user_id"]),
    )


# 4. DELETE USER
@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    if session.get("role") != "Admin":
        return redirect(url_for("admin_login"))

    user_to_delete = User.query.get_or_404(user_id)

    # Restriction: Cannot delete Admins
    if user_to_delete.user_role == "Admin":
        flash("Critical Error: You cannot delete an Admin account.", "error")
    else:
        db.session.delete(user_to_delete)
        db.session.commit()
        flash("User deleted successfully.", "success")

    return redirect(url_for("admin_user_management"))


# ==========================================
# 2. RESEARCHER ROUTES
# ==========================================
@app.route("/researcher/login", methods=["POST", "GET"])
def researcher_login():
    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        password = request.form["password"]
        user = User.query.filter_by(mmu_id=mmu_id, user_role="Researcher").first()

        if user and user.check_password(password):
            session["user_id"] = user.mmu_id
            session["role"] = "Researcher"
            session["name"] = user.name
            return redirect(url_for("researcher_dashboard"))
        else:
            flash("Invalid Researcher credentials.", "error")

    return render_template("researcher_login.html")


@app.route("/researcher/dashboard")
def researcher_dashboard():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))

    user = User.query.get(session["user_id"])  # Get latest user data
    stats = {"my_proposals": 3, "active_grants": 1, "pending_reports": 2}
    return render_template("researcher_dashboard.html", stats=stats, user=user)


@app.route("/researcher/profile", methods=["GET", "POST"])
def researcher_profile():
    if session.get("role") != "Researcher":
        return redirect(url_for("researcher_login"))

    user = User.query.get(session["user_id"])

    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("researcher_profile"))

    return render_template("researcher_profile.html", user=user)


# ==========================================
# 3. REVIEWER ROUTES
# ==========================================
@app.route("/reviewer/login", methods=["POST", "GET"])
def reviewer_login():
    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        password = request.form["password"]
        user = User.query.filter_by(mmu_id=mmu_id, user_role="Reviewer").first()

        if user and user.check_password(password):
            session["user_id"] = user.mmu_id
            session["role"] = "Reviewer"
            session["name"] = user.name
            return redirect(url_for("reviewer_dashboard"))
        else:
            flash("Invalid Reviewer credentials.", "error")

    return render_template("reviewer_login.html")


@app.route("/reviewer/dashboard")
def reviewer_dashboard():
    if session.get("role") != "Reviewer":
        return redirect(url_for("reviewer_login"))

    user = User.query.get(session["user_id"])
    stats = {"pending_reviews": 5, "completed_reviews": 12}
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


# ==========================================
# 4. HOD ROUTES
# ==========================================
@app.route("/hod/login", methods=["POST", "GET"])
def hod_login():
    if request.method == "POST":
        mmu_id = request.form["mmu_id"]
        password = request.form["password"]
        user = User.query.filter_by(mmu_id=mmu_id, user_role="HOD").first()

        if user and user.check_password(password):
            session["user_id"] = user.mmu_id
            session["role"] = "HOD"
            session["name"] = user.name
            return redirect(url_for("hod_dashboard"))
        else:
            flash("Invalid HOD credentials.", "error")

    return render_template("hod_login.html")


@app.route("/hod/dashboard")
def hod_dashboard():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))

    user = User.query.get(session["user_id"])
    stats = {"approvals_pending": 8, "budget_allocated": "RM 50,000"}
    return render_template("hod_dashboard.html", stats=stats, user=user)


@app.route("/hod/profile", methods=["GET", "POST"])
def hod_profile():
    if session.get("role") != "HOD":
        return redirect(url_for("hod_login"))

    user = User.query.get(session["user_id"])

    if request.method == "POST":
        if update_user_profile(user, request.form, request.files):
            return redirect(url_for("hod_profile"))

    return render_template("hod_profile.html", user=user)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
