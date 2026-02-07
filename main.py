import os
from flask import Flask, session
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from models import db, Notification

# 1. SETUP APP
app = Flask(__name__)
app.secret_key = "your_secret_key_here" # Change this in production

basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "database.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(basedir, "static/profile_pics")
app.config["UPLOAD_FOLDER_DOCS"] = os.path.join(basedir, "static/proposal_docs")
app.config["ALLOWED_EXTENSIONS"] = {"pdf", "docx", "doc"}

db.init_app(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)

# 2. REGISTER BLUEPRINTS
from routes.auth_routes import auth_bp
from routes.admin_routes import admin_bp
from routes.researcher_routes import researcher_bp
from routes.reviewer_routes import reviewer_bp
from routes.hod_routes import hod_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(researcher_bp)
app.register_blueprint(reviewer_bp)
app.register_blueprint(hod_bp)

# 3. GLOBAL CONTEXT PROCESSOR (Notifications)
@app.context_processor
def inject_notifications():
    if "user_id" in session:
        unread = Notification.query.filter_by(recipient_id=session["user_id"], is_read=False).count()
        return dict(unread_notifications=unread)
    return dict(unread_notifications=0)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)