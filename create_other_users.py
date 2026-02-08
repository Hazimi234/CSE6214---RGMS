import random
from main import app, db
from models import User, Admin, HOD, Researcher, Reviewer

def seed_data():
    # Define the data in a list of dictionaries for easy management
    users_to_create = [
        # Admins
        {"mmu_id": "242UC24411", "name": "Vignes", "email": "vignes@mmu.edu.my", "faculty": "FOE", "role": "Admin", "model": Admin},
        {"mmu_id": "242UC24422", "name": "Chan Chun Sing", "email": "chanchunsing@mmu.edu.my", "faculty": "FCM", "role": "Admin", "model": Admin},
        {"mmu_id": "242UC24433", "name": "Aisyah Humaira", "email": "aisyahhumaira@mmu.edu.my", "faculty": "FOM", "role": "Admin", "model": Admin},
        {"mmu_id": "242UC24444", "name": "Divya", "email": "divya@mmu.edu.my", "faculty": "FAC", "role": "Admin", "model": Admin},
        {"mmu_id": "242UC24455", "name": "Teoh Beng Hock", "email": "teohbenghock@mmu.edu.my", "faculty": "FCA", "role": "Admin", "model": Admin},
        {"mmu_id": "242UC24466", "name": "Krishnan", "email": "krishnan@mmu.edu.my", "faculty": "FIST", "role": "Admin", "model": Admin},
        {"mmu_id": "242UC24477", "name": "Yip Sook Yee", "email": "yipsookyee@mmu.edu.my", "faculty": "FET", "role": "Admin", "model": Admin},
        {"mmu_id": "242UC24488", "name": "Joanne Marsha", "email": "joannemarsha@mmu.edu.my", "faculty": "FOB", "role": "Admin", "model": Admin},
        {"mmu_id": "242UC24499", "name": "Badrul Hisham", "email": "badrulhisham@mmu.edu.my", "faculty": "FOL", "role": "Admin", "model": Admin},
        
        # HODs
        {"mmu_id": "242UC244S1", "name": "Lee Kah Seng", "email": "leekahseng@mmu.edu.my", "faculty": "FOE", "role": "HOD", "model": HOD},
        {"mmu_id": "242UC244T2", "name": "Puteri Balqis", "email": "puteribalqis@mmu.edu.my", "faculty": "FCM", "role": "HOD", "model": HOD},
        {"mmu_id": "242UC244U3", "name": "Thivagar", "email": "thivagar@mmu.edu.my", "faculty": "FOM", "role": "HOD", "model": HOD},
        {"mmu_id": "242UC244V4", "name": "Chong Sau Fun", "email": "chongsaufun@mmu.edu.my", "faculty": "FAC", "role": "HOD", "model": HOD},
        {"mmu_id": "242UC244W5", "name": "Hafiz Suip", "email": "hafizsuip@mmu.edu.my", "faculty": "FCA", "role": "HOD", "model": HOD},
        {"mmu_id": "242UC244X6", "name": "Anusha", "email": "anusha@mmu.edu.my", "faculty": "FIST", "role": "HOD", "model": HOD},
        {"mmu_id": "242UC244Y7", "name": "Low Yee Zi", "email": "lowyeezi@mmu.edu.my", "faculty": "FET", "role": "HOD", "model": HOD},
        {"mmu_id": "242UC244Z8", "name": "Sugun Balang", "email": "sugunbalang@mmu.edu.my", "faculty": "FOB", "role": "HOD", "model": HOD},
        {"mmu_id": "242UC24419", "name": "Farrah", "email": "farrah@mmu.edu.my", "faculty": "FOL", "role": "HOD", "model": HOD},

        # Researchers
        {"mmu_id": "242UC244A1", "name": "Yap Shu Ming", "email": "yapshuming@mmu.edu.my", "faculty": "FOE", "role": "Researcher", "model": Researcher},
        {"mmu_id": "242UC244B2", "name": "Tan Mei Ling", "email": "tanmeiling@mmu.edu.my", "faculty": "FCM", "role": "Researcher", "model": Researcher},
        {"mmu_id": "242UC244C3", "name": "Siti Nurhaliza", "email": "sitinurhaliza@mmu.edu.my", "faculty": "FOM", "role": "Researcher", "model": Researcher},
        {"mmu_id": "242UC244D4", "name": "Ravi", "email": "ravi@mmu.edu.my", "faculty": "FAC", "role": "Researcher", "model": Researcher},
        {"mmu_id": "242UC244E5", "name": "Awang Tengah", "email": "awangtengah@mmu.edu.my", "faculty": "FCA", "role": "Researcher", "model": Researcher},
        {"mmu_id": "242UC244F6", "name": "Ahmad Irfan", "email": "ahmadirfan@mmu.edu.my", "faculty": "FIST", "role": "Researcher", "model": Researcher},
        {"mmu_id": "242UC244G7", "name": "Priya", "email": "priya@mmu.edu.my", "faculty": "FET", "role": "Researcher", "model": Researcher},
        {"mmu_id": "242UC244H8", "name": "Wong Jia Yi", "email": "wongjiayi@mmu.edu.my", "faculty": "FOB", "role": "Researcher", "model": Researcher},
        {"mmu_id": "242UC244I9", "name": "Dayang Nurfaizah", "email": "alif@mmu.edu.my", "faculty": "FOL", "role": "Researcher", "model": Researcher},

        # Reviewers
        {"mmu_id": "242UC244J1", "name": "Mohd Khairul", "email": "mohdkhairul@mmu.edu.my", "faculty": "FOE", "role": "Reviewer", "model": Reviewer},
        {"mmu_id": "242UC244K2", "name": "Laxmi", "email": "laxmi@mmu.edu.my", "faculty": "FCM", "role": "Reviewer", "model": Reviewer},
        {"mmu_id": "242UC244L3", "name": "Lim Wei Jun", "email": "limweijun@mmu.edu.my", "faculty": "FOM", "role": "Reviewer", "model": Reviewer},
        {"mmu_id": "242UC244M4", "name": "Rentap Anak Libau", "email": "rentap@mmu.edu.my", "faculty": "FAC", "role": "Reviewer", "model": Reviewer},
        {"mmu_id": "242UC244N5", "name": "Nurul Izzah", "email": "nurulizzah@mmu.edu.my", "faculty": "FCA", "role": "Reviewer", "model": Reviewer},
        {"mmu_id": "242UC244O6", "name": "Sanjeev", "email": "sanjeev@mmu.edu.my", "faculty": "FIST", "role": "Reviewer", "model": Reviewer},
        {"mmu_id": "242UC244P7", "name": "Ng Xin Yi", "email": "ngxinyi@mmu.edu.my", "faculty": "FET", "role": "Reviewer", "model": Reviewer},
        {"mmu_id": "242UC244Q8", "name": "Zul Ariffin", "email": "zulariffin@mmu.edu.my", "faculty": "FOB", "role": "Reviewer", "model": Reviewer},
        {"mmu_id": "242UC244R9", "name": "Kavitha", "email": "kavitha@mmu.edu.my", "faculty": "FOL", "role": "Reviewer", "model": Reviewer},
    ]

    # SHUFFLE THE DATA
    random.shuffle(users_to_create)

    with app.app_context():
        db.create_all()

        for data in users_to_create:
            # Check if user exists
            if not User.query.filter_by(mmu_id=data["mmu_id"]).first():
                # Create the Base User
                u = User(
                    mmu_id=data["mmu_id"], 
                    name=data["name"], 
                    email=data["email"], 
                    password="", 
                    faculty=data["faculty"], 
                    user_role=data["role"]
                )
                u.set_password("123")
                db.session.add(u)
                
                # Create the Role-specific entry
                role_entry = data["model"](mmu_id=data["mmu_id"])
                db.session.add(role_entry)
                
                print(f"Created {data['role']}: {data['name']}")

        db.session.commit()
        print("--- All users seeded and randomized! ---")

if __name__ == "__main__":
    seed_data()