import os
from flask import Flask, redirect, url_for, render_template, request, session, flash
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from models import db, User, Admin  # Import models

app = Flask(__name__, template_folder="templates")
app.secret_key = "RGMS_Key"  # Change this for production

# Database Configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize Extensions
db.init_app(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)

# Main Login Page (Role Selection) - Section 6.1.1 of PDF
@app.route("/")
def main_login():
    if "user_id" in session:
        return redirect(url_for("admin_dashboard")) # Or redirect based on role
    return render_template("main_login.html")

# Admin Login Page - Section 6.5.1 of PDF
@app.route("/admin/login", methods=["POST", "GET"])
def admin_login():
    if request.method == "POST":
        session.permanent = True
        mmu_id = request.form["mmu_id"]
        password = request.form["password"]

        # Find user by MMU ID
        user = User.query.filter_by(mmu_id=mmu_id).first()

        # Check password and ensure role is Admin
        if user and user.check_password(password):
            if user.user_role == "Admin":
                session["user_id"] = user.mmu_id
                session["role"] = "Admin"
                flash("Login Successful!", "success")
                return redirect(url_for("admin_dashboard"))
            else:
                flash("Access Denied: You are not an Admin.", "error")
                return redirect(url_for("admin_login"))
        else:
            flash("Invalid MMU ID or Password.", "error")
            return redirect(url_for("admin_login"))

    # GET Request
    if "user_id" in session and session.get("role") == "Admin":
        return redirect(url_for("admin_dashboard"))
        
    return render_template("admin_login.html")

# Placeholder for Dashboard
@app.route("/admin/dashboard")
def admin_dashboard():
    if "user_id" not in session or session.get("role") != "Admin":
        return redirect(url_for("admin_login"))
    return "<h1>Welcome to Admin Dashboard</h1>" # Replace with actual dashboard template

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main_login"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Creates database tables if they don't exist
    app.run(debug=True)