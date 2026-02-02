from main import app, db
from models import User, Researcher, Reviewer, HOD

def seed_data():
    with app.app_context():
        db.create_all()

        # 1. Create Researcher
        if not User.query.filter_by(mmu_id=2001).first():
            u = User(mmu_id="242UC244L7", name="Alif Akmal", email="alif@mmu.edu.my", password="", faculty="FCI", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id=2001))

        # 2. Create Reviewer
        if not User.query.filter_by(mmu_id=3001).first():
            u = User(mmu_id="242UC244PT", name="Jasmyne Yap", email="jasmyne@mmu.edu.my", password="", faculty="FCI", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id=3001))

        # 3. Create HOD
        if not User.query.filter_by(mmu_id=4001).first():
            u = User(mmu_id="242UC244RD", name="Brian Ng", email="brian@mmu.edu.my", password="", faculty="FCI", user_role="HOD")
            u.set_password("123")
            db.session.add(u)
            db.session.add(HOD(mmu_id=4001))

        db.session.commit()
        print("Test users created!")

if __name__ == "__main__":
    seed_data()