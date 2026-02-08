from main import app, db
from models import User, Reviewer

def seed_data():
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(mmu_id="242UC244J1").first():
            u = User(mmu_id="242UC244J1", name="Mohd Khairul", email="mohdkhairul@mmu.edu.my", password="", faculty="FOE", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244J1"))
        
        if not User.query.filter_by(mmu_id="242UC244K2").first():
            u = User(mmu_id="242UC244K2", name="Laxmi", email="laxmi@mmu.edu.my", password="", faculty="FCM", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244K2"))

        if not User.query.filter_by(mmu_id="242UC244L3").first():
            u = User(mmu_id="242UC244L3", name="Lim Wei Jun", email="limweijun@mmu.edu.my", password="", faculty="FOM", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244L3"))

        if not User.query.filter_by(mmu_id="242UC244M4").first():
            u = User(mmu_id="242UC244M4", name="Rentap Anak Libau", email="rentap@mmu.edu.my", password="", faculty="FAC", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244M4"))

        if not User.query.filter_by(mmu_id="242UC244N5").first():
            u = User(mmu_id="242UC244N5", name="Nurul Izzah", email="nurulizzah@mmu.edu.my", password="", faculty="FCA", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244N5"))


        if not User.query.filter_by(mmu_id="242UC244O6").first():
            u = User(mmu_id="242UC244O6", name="Sanjeev", email="sanjeev@mmu.edu.my", password="", faculty="FIST", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244O6"))

        if not User.query.filter_by(mmu_id="242UC244P7").first():
            u = User(mmu_id="242UC244P7", name="Ng Xin Yi", email="ngxinyi@mmu.edu.my", password="", faculty="FET", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244P7"))

        if not User.query.filter_by(mmu_id="242UC244Q8").first():
            u = User(mmu_id="242UC244Q8", name="Zul Ariffin", email="zulariffin@mmu.edu.my", password="", faculty="FOB", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244Q8"))

        if not User.query.filter_by(mmu_id="242UC244R9").first():
            u = User(mmu_id="242UC244R9", name="Kavitha", email="kavitha@mmu.edu.my", password="", faculty="FOL", user_role="Reviewer")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Reviewer(mmu_id="242UC244R9"))

        db.session.commit()
        print("Reviewers created!")

if __name__ == "__main__":
    seed_data()