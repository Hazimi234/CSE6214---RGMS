from main import app, db
from models import User, Researcher, Reviewer, HOD, Admin

def seed_data():
    with app.app_context():
        db.create_all()

        # 1. Create Researcher
        if not User.query.filter_by(mmu_id="242UC244L7").first():
            u = User(mmu_id="242UC244L7", name="Alif Akmal", email="alifakmal@mmu.edu.my", password="", faculty="FCI", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244L7"))

        if not User.query.filter_by(mmu_id="242UC244LA").first():
            u = User(mmu_id="242UC244LA", name="Saraswathy", email="saraswathy@mmu.edu.my", password="", faculty="FCI", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244LA"))

        if not User.query.filter_by(mmu_id="242UC244LB").first():
            u = User(mmu_id="242UC244LB", name="Debbie Goh", email="debbiegoh@mmu.edu.my", password="", faculty="FCI", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244LB"))


        # 2. Create Reviewer
        if not User.query.filter_by(mmu_id="242UC244PT").first():
            u = User(mmu_id="242UC244PT", name="Jasmyne Yap", email="jasmyneyap@mmu.edu.my", password="", faculty="FCI", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244PT"))

        if not User.query.filter_by(mmu_id="242UC244PA").first():
            u = User(mmu_id="242UC244PA", name="Goh V Shem", email="gohvshem@mmu.edu.my", password="", faculty="FCI", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244PA"))

        if not User.query.filter_by(mmu_id="242UC244PB").first():
            u = User(mmu_id="242UC244PB", name="Selvam", email="selvam@mmu.edu.my", password="", faculty="FCI", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244PB"))

        # 3. Create HOD
        if not User.query.filter_by(mmu_id="242UC244RD").first():
            u = User(mmu_id="242UC244RD", name="Brian Ng", email="brianng@mmu.edu.my", password="", faculty="FCI", user_role="HOD")
            u.set_password("123")
            db.session.add(u)
            db.session.add(HOD(mmu_id="242UC244RD"))

        # 4. Create Admin
        if not User.query.filter_by(mmu_id="242UC244PU").first():
            u = User(mmu_id="242UC244PU", name="Meor Hazimi", email="meorhazimi@mmu.edu.my", password="", faculty="FCI", user_role="Admin")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Admin(mmu_id="242UC244PU"))

        db.session.commit()
        print("Users created!")

if __name__ == "__main__":
    seed_data()