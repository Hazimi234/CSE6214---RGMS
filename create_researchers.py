from main import app, db
from models import User, Researcher

def seed_data():
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(mmu_id="242UC244A1").first():
            u = User(mmu_id="242UC244A1", name="Yap Shu Ming", email="yapshuming@mmu.edu.my", password="", faculty="FOE", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244A1"))
        
        if not User.query.filter_by(mmu_id="242UC244B2").first():
            u = User(mmu_id="242UC244B2", name="Tan Mei Ling", email="tanmeiling@mmu.edu.my", password="", faculty="FCM", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244B2"))

        if not User.query.filter_by(mmu_id="242UC244C3").first():
            u = User(mmu_id="242UC244C3", name="Siti Nurhaliza", email="sitinurhaliza@mmu.edu.my", password="", faculty="FOM", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244C3"))

        if not User.query.filter_by(mmu_id="242UC244D4").first():
            u = User(mmu_id="242UC244D4", name="Ravi", email="ravi@mmu.edu.my", password="", faculty="FAC", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244D4"))

        if not User.query.filter_by(mmu_id="242UC244E5").first():
            u = User(mmu_id="242UC244E5", name="Awang Tengah", email="awangtengah@mmu.edu.my", password="", faculty="FCA", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244E5"))


        if not User.query.filter_by(mmu_id="242UC244F6").first():
            u = User(mmu_id="242UC244F6", name="Ahmad Irfan", email="ahmadirfan@mmu.edu.my", password="", faculty="FIST", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244F6"))

        if not User.query.filter_by(mmu_id="242UC244G7").first():
            u = User(mmu_id="242UC244G7", name="Priya", email="priya@mmu.edu.my", password="", faculty="FET", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244G7"))

        if not User.query.filter_by(mmu_id="242UC244H8").first():
            u = User(mmu_id="242UC244H8", name="Wong Jia Yi", email="wongjiayi@mmu.edu.my", password="", faculty="FOB", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244H8"))

        if not User.query.filter_by(mmu_id="242UC244I9").first():
            u = User(mmu_id="242UC244I9", name="Dayang Nurfaizah", email="alif@mmu.edu.my", password="", faculty="FOL", user_role="Researcher")
            u.set_password("123")
            db.session.add(u)
            db.session.add(Researcher(mmu_id="242UC244I9"))

        db.session.commit()
        print("Researchers created!")

if __name__ == "__main__":
    seed_data()