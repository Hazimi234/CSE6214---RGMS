from main import app, db
from models import User, Admin

def seed_data():
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(mmu_id="242UC24411").first():
            u = User(mmu_id="242UC24411", name="Vignes", email="vignes@mmu.edu.my", password="", faculty="FOE", user_role="Admin")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Admin(mmu_id="242UC24411"))
        
        if not User.query.filter_by(mmu_id="242UC24422").first():
            u = User(mmu_id="242UC24422", name="Chan Chun Sing", email="chanchunsing@mmu.edu.my", password="", faculty="FCM", user_role="Admin")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Admin(mmu_id="242UC24422"))

        if not User.query.filter_by(mmu_id="242UC24433").first():
            u = User(mmu_id="242UC24433", name="Aisyah Humaira", email="aisyahhumaira@mmu.edu.my", password="", faculty="FOM", user_role="Admin")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Admin(mmu_id="242UC24433"))

        if not User.query.filter_by(mmu_id="242UC24444").first():
            u = User(mmu_id="242UC24444", name="Divya", email="divya@mmu.edu.my", password="", faculty="FAC", user_role="Admin")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Admin(mmu_id="242UC24444"))

        if not User.query.filter_by(mmu_id="242UC24455").first():
            u = User(mmu_id="242UC24455", name="Teoh Beng Hock", email="teohbenghock@mmu.edu.my", password="", faculty="FCA", user_role="Admin")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Admin(mmu_id="242UC24455"))


        if not User.query.filter_by(mmu_id="242UC24466").first():
            u = User(mmu_id="242UC24466", name="Krishnan", email="krishnan@mmu.edu.my", password="", faculty="FIST", user_role="Admin")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Admin(mmu_id="242UC24466"))

        if not User.query.filter_by(mmu_id="242UC24477").first():
            u = User(mmu_id="242UC24477", name="Yip Sook Yee", email="yipsookyee@mmu.edu.my", password="", faculty="FET", user_role="Admin")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Admin(mmu_id="242UC24477"))

        if not User.query.filter_by(mmu_id="242UC24488").first():
            u = User(mmu_id="242UC24488", name="Joanne Marsha", email="joannemarsha@mmu.edu.my", password="", faculty="FOB", user_role="Admin")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Admin(mmu_id="242UC24488"))

        if not User.query.filter_by(mmu_id="242UC24499").first():
            u = User(mmu_id="242UC24499", name="Badrul Hisham", email="badrulhisham@mmu.edu.my", password="", faculty="FOL", user_role="Admin")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Admin(mmu_id="242UC24499"))

        db.session.commit()
        print("Admins created!")

if __name__ == "__main__":
    seed_data()