import logging
from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..core import security
from ..core.config import settings
from ..models import database as models
from ..schemas.token import TokenPayload

logger = logging.getLogger(__name__)

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db() -> Generator:
    try:
        db = models.SessionLocal()
        yield db
    finally:
        db.close()


def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> models.User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        token_data = TokenPayload(**payload)
    except (jwt.JWTError, ValidationError):
        logger.warning("Token validation failed")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = db.query(models.User).filter(models.User.user_id == int(token_data.sub)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status not in ("approved", "active"):
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


def get_current_active_admin(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if current_user.role not in ("admin", "executive"):
        raise HTTPException(status_code=403, detail="The user doesn't have enough privileges")
    return current_user


def get_current_pm_or_admin(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if current_user.role not in ("admin", "executive", "pm"):
        raise HTTPException(status_code=403, detail="PM or admin role required")
    return current_user


def require_project_access(project_id: int, db: Session, user: models.User) -> models.Project:
    """
    Returns the project if the user is allowed to access it, else raises 403/404.

    Access rules:
      - admin / executive: any project
      - pm: project they manage OR are assigned to
      - team: project they are assigned to
    """
    project = db.query(models.Project).filter(models.Project.project_id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if user.role in ("admin", "executive"):
        return project

    if project.pm_user_id == user.user_id:
        return project

    assignment = (
        db.query(models.ProjectAssignment)
        .filter(
            models.ProjectAssignment.project_id == project_id,
            models.ProjectAssignment.user_id == user.user_id,
        )
        .first()
    )
    if assignment:
        return project

    raise HTTPException(status_code=403, detail="No access to this project")


def list_accessible_project_ids(db: Session, user: models.User):
    """Returns a list of project_ids the user can access, or None for admin/exec (= all)."""
    if user.role in ("admin", "executive"):
        return None

    managed = db.query(models.Project.project_id).filter(models.Project.pm_user_id == user.user_id).all()
    assigned = (
        db.query(models.ProjectAssignment.project_id)
        .filter(models.ProjectAssignment.user_id == user.user_id)
        .all()
    )
    return list({pid for (pid,) in managed} | {pid for (pid,) in assigned})
