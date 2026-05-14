import os
import sys

from app.models.database import Base, engine, User, Project, Task, Expenditure, Risk, DailyProgress, SessionLocal
from app.core.security import get_password_hash
import datetime

def seed_db():
    admin_password = os.getenv("ADMIN_INITIAL_PASSWORD")
    pm_password = os.getenv("SEED_PM_PASSWORD")
    if not admin_password or not pm_password:
        print(
            "ERROR: ADMIN_INITIAL_PASSWORD and SEED_PM_PASSWORD env vars are required to seed example users.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Seeding database with working project example...")
    db = SessionLocal()

    # 1. Create Users
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            full_name="System Administrator",
            email=os.getenv("ADMIN_EMAIL", "admin@3core.com"),
            password_hash=get_password_hash(admin_password),
            role="admin",
            status="active"
        )
        db.add(admin)

    pm = User(
        username="ayanda",
        full_name="Ayanda Phaketsi",
        email="ayanda@3core.com",
        password_hash=get_password_hash(pm_password),
        role="pm",
        status="active"
    )
    db.add(pm)
    db.commit()
    db.refresh(pm)
    
    # 2. Create Project
    project = Project(
        project_name="3CORE Bridge Construction",
        project_number="SEB-2026-001",
        client="City of Johannesburg",
        pm_user_id=pm.user_id,
        total_budget=5000000.00,
        start_date=datetime.date(2026, 1, 1),
        target_end_date=datetime.date(2026, 12, 31),
        status="active",
        created_by=admin.user_id if admin else None
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    
    # 3. Create Tasks (Baseline Schedule)
    tasks_data = [
        {
            "activity_name": "Site Preparation & Mobilization",
            "status": "Complete",
            "planned_start": datetime.date(2026, 1, 1),
            "planned_finish": datetime.date(2026, 1, 31),
            "budgeted_cost": 500000.00,
            "unit_of_measure": "LS",
            "total_quantity": 1.0,
            "completed_quantity": 1.0
        },
        {
            "activity_name": "Earthworks & Excavation",
            "status": "Active",
            "planned_start": datetime.date(2026, 2, 1),
            "planned_finish": datetime.date(2026, 3, 31),
            "budgeted_cost": 1200000.00,
            "unit_of_measure": "m3",
            "total_quantity": 5000.0,
            "completed_quantity": 3200.0,
            "depends_on": 1 # Site Prep
        },
        {
            "activity_name": "Foundation Piling",
            "status": "Active",
            "planned_start": datetime.date(2026, 3, 1),
            "planned_finish": datetime.date(2026, 5, 15),
            "budgeted_cost": 1800000.00,
            "unit_of_measure": "piles",
            "total_quantity": 48.0,
            "completed_quantity": 12.0,
            "depends_on": 2 # Earthworks
        },
        {
            "activity_name": "Concrete Superstructure",
            "status": "Not Started",
            "planned_start": datetime.date(2026, 5, 16),
            "planned_finish": datetime.date(2026, 9, 30),
            "budgeted_cost": 1500000.00,
            "unit_of_measure": "m3",
            "total_quantity": 2500.0,
            "completed_quantity": 0.0,
            "depends_on": 3 # Foundation
        }
    ]
    
    created_tasks = []
    for t_data in tasks_data:
        task = Task(
            project_id=project.project_id,
            responsible_user_id=pm.user_id,
            **t_data
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        created_tasks.append(task)
        
    # 4. Add Expenditures
    expenditures = [
        Expenditure(
            project_id=project.project_id,
            activity_id=created_tasks[0].activity_id,
            category="Labor",
            description="Mobilization Crew Week 1-4",
            amount=150000.00,
            spend_date=datetime.date(2026, 1, 15),
            recorded_by=pm.user_id
        ),
        Expenditure(
            project_id=project.project_id,
            activity_id=created_tasks[0].activity_id,
            category="Equipment",
            description="TLB & Crane Rental",
            amount=300000.00,
            spend_date=datetime.date(2026, 1, 20),
            recorded_by=pm.user_id
        ),
        Expenditure(
            project_id=project.project_id,
            activity_id=created_tasks[1].activity_id,
            category="Materials",
            description="Fill Material Supply",
            amount=450000.00,
            spend_date=datetime.date(2026, 2, 10),
            recorded_by=pm.user_id
        )
    ]
    for exp in expenditures:
        db.add(exp)
        
    # 5. Add Risks
    risks = [
        Risk(
            project_id=project.project_id,
            description="Unexpected bedrock found during excavation",
            impact="H",
            status="Open",
            mitigation_action="Utilize specialized drilling equipment",
            date_identified=datetime.date(2026, 2, 5),
            recorded_by=pm.user_id
        ),
        Risk(
            project_id=project.project_id,
            description="Heavy seasonal rains affecting site access",
            impact="M",
            status="Monitoring",
            mitigation_action="Improve drainage and install temporary access roads",
            date_identified=datetime.date(2026, 2, 15),
            recorded_by=pm.user_id
        )
    ]
    for r in risks:
        db.add(r)
        
    # 6. Add Daily Progress
    progress = [
        DailyProgress(
            activity_id=created_tasks[1].activity_id,
            quantity=500.0,
            progress_date=datetime.date(2026, 2, 1),
            notes="Initial earthworks started.",
            recorded_by=pm.user_id
        ),
        DailyProgress(
            activity_id=created_tasks[1].activity_id,
            quantity=600.0,
            progress_date=datetime.date(2026, 2, 2),
            notes="Excavation continuing smoothly.",
            recorded_by=pm.user_id
        )
    ]
    for p in progress:
        db.add(p)
    
    db.commit()
    db.close()
    print("Database seeded with working example.")

if __name__ == "__main__":
    seed_db()
