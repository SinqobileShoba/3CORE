import os
import sys

from app.core.security import get_password_hash
from app.models.database import Base, SessionLocal, User, engine


def init_db():
    admin_password = os.getenv("ADMIN_INITIAL_PASSWORD")
    if not admin_password:
        print(
            "ERROR: ADMIN_INITIAL_PASSWORD env var is required to bootstrap the admin user.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        print("Creating admin user...")
        admin = User(
            username="admin",
            full_name="System Administrator",
            email=os.getenv("ADMIN_EMAIL", "admin@3core.com"),
            password_hash=get_password_hash(admin_password),
            role="admin",
            status="active",
        )
        db.add(admin)
        db.commit()
    db.close()
    print("Database initialized.")


if __name__ == "__main__":
    init_db()
