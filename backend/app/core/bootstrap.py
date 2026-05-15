import logging
import os

from ..models.database import Base, SessionLocal, User, engine
from .security import get_password_hash

logger = logging.getLogger(__name__)


def bootstrap_db(create_admin: bool = True) -> None:
    """
    Idempotent database bootstrap, safe to run on every startup.

    - Creates any missing tables (no-op if they already exist).
    - Creates the initial admin user if one doesn't exist and
      ADMIN_INITIAL_PASSWORD is set.

    This exists so the app works on hosts (e.g. Render free tier) that have
    no shell access to run init_db.py manually.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured.")
    except Exception:
        logger.exception("Could not create database tables")
        raise

    if not create_admin:
        return

    admin_password = os.getenv("ADMIN_INITIAL_PASSWORD")
    if not admin_password:
        logger.warning(
            "ADMIN_INITIAL_PASSWORD not set — skipping admin bootstrap. "
            "Set it and redeploy to create the initial admin user."
        )
        return

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == "admin").first()
        if existing:
            return
        db.add(
            User(
                username="admin",
                full_name="System Administrator",
                email=os.getenv("ADMIN_EMAIL", "admin@3core.com"),
                password_hash=get_password_hash(admin_password),
                role="admin",
                status="active",
            )
        )
        db.commit()
        logger.info("Created initial admin user.")
    except Exception:
        logger.exception("Could not create initial admin user")
        db.rollback()
    finally:
        db.close()
