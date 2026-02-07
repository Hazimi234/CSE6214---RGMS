from main import app, db
from models import User, HOD

def seed_data():
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(mmu_id="242UC244S1").first():
            u = User(mmu_id="242UC244S1", name="Lee Kah Seng", email="leekahseng@mmu.edu.my", password="", faculty="FOE", user_role="HOD")
            u.set_password("123")
            db.session.add(u)
            db.session.add(HOD(mmu_id="242UC244S1"))
        
        if not User.query.filter_by(mmu_id="242UC244T2").first():
            u = User(mmu_id="242UC244T2", name="Puteri Balqis", email="puteribalqis@mmu.edu.my", password="", faculty="FCM", user_role="HOD")
            u.set_password("123")
            db.session.add(u)
            db.session.add(HOD(mmu_id="242UC244T2"))

        if not User.query.filter_by(mmu_id="242UC244U3").first():
            u = User(mmu_id="242UC244U3", name="Thivagar", email="thivagar@mmu.edu.my", password="", faculty="FOM", user_role="HOD")
            u.set_password("123")
            db.session.add(u)
            db.session.add(HOD(mmu_id="242UC244U3"))

        if not User.query.filter_by(mmu_id="242UC244V4").first():
            u = User(mmu_id="242UC244V4", name="Chong Sau Fun", email="chongsaufun@mmu.edu.my", password="", faculty="FAC", user_role="HOD")
            u.set_password("123")
            db.session.add(u)
            db.session.add(HOD(mmu_id="242UC244V4"))

        if not User.query.filter_by(mmu_id="242UC244W5").first():
            u = User(mmu_id="242UC244W5", name="Hafiz Suip", email="hafizsuip@mmu.edu.my", password="", faculty="FCA", user_role="HOD")
            u.set_password("123")
            db.session.add(u)
            db.session.add(HOD(mmu_id="242UC244W5"))


        if not User.query.filter_by(mmu_id="242UC244X6").first():
            u = User(mmu_id="242UC244X6", name="Anusha", email="anusha@mmu.edu.my", password="", faculty="FIST", user_role="HOD")
            u.set_password("123")
            db.session.add(u)
            db.session.add(HOD(mmu_id="242UC244X6"))

        if not User.query.filter_by(mmu_id="242UC244Y7").first():
            u = User(mmu_id="242UC244Y7", name="Low Yee Zi", email="lowyeezi@mmu.edu.my", password="", faculty="FET", user_role="HOD")
            u.set_password("123")
            db.session.add(u)
            db.session.add(HOD(mmu_id="242UC244Y7"))

        if not User.query.filter_by(mmu_id="242UC244Z8").first():
            u = User(mmu_id="242UC244Z8", name="Sugun Balang", email="sugunbalang@mmu.edu.my", password="", faculty="FOB", user_role="HOD")
            u.set_password("123")
            db.session.add(u)
            db.session.add(HOD(mmu_id="242UC244Z8"))

        if not User.query.filter_by(mmu_id="242UC24419").first():
            u = User(mmu_id="242UC24419", name="Farrah", email="farrah@mmu.edu.my", password="", faculty="FOL", user_role="HOD")
            u.set_password("123")
            db.session.add(u)
            db.session.add(HOD(mmu_id="242UC24419"))

        db.session.commit()
        print("HODs created!")

if __name__ == "__main__":
    seed_data()