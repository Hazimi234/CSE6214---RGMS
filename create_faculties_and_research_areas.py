from main import app, db
from models import Faculty, ResearchArea


def seed_data():
    with app.app_context():
        db.create_all()

        # 1. Seed Faculties
        initial_faculties = ["FCI", "FOE", "FCM", "FOM", "FAC", "FCA", "FIST", "FET","FOB","FOL"]
        for f_name in initial_faculties:
            if not Faculty.query.filter_by(name=f_name).first():
                db.session.add(Faculty(name=f_name))

        # 2. Seed Research Areas
        initial_areas = ["Artificial Intelligence", "Cyber Security", "Data Science", "Software Engineering", 
                         "Game Development", "Information Systems", "Bioinformatics", "Nanotechnology", 
                         "Telecommunications", "Robotics & Automation", "Optical Engineering", "Renewable Energy", 
                         "Advanced Signal Processing", "VR & AR", "Interface Design", "Visual Effects", "Digital Education", 
                         "Animation", "Sound & Music Communication", "Digital Enterprise Management", "Financial Technology",
                         "Knowledge Management", "Analytical Economics", "Strategic Communication", "Media Culture", "Human-Computer Interaction",
                         "Digital Literacy", "Cinematography", "Screenwriting", "Film Production Technologies", "New Wave Media",
                         "Security Technology", "Business Intelligence", "Medical Informatics", "Networking Technology", "Mechanical Engineering",
                         "Electronic Engineering", "Robotics & Sensing", "Green Technology", "Marketing Management", "E-Commerce", "Business Analytics"
                         "Accounting Information Systems", "Finance & Banking", "Cyber Law", "Intellectual Property Law", "Corporate Law",
                         "Alternative Dispute Resolution", "Media Law"]
        for a_name in initial_areas:
            if not ResearchArea.query.filter_by(name=a_name).first():
                db.session.add(ResearchArea(name=a_name))


        db.session.commit()
        print("Database seeded with System Data@")

if __name__ == "__main__":
    seed_data()