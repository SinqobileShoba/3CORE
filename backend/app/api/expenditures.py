from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..core.audit import log_event
from ..models.database import get_db, Expenditure, User
from ..schemas.expenditure import Expenditure as ExpenditureSchema, ExpenditureCreate
from .deps import get_current_pm_or_admin, get_current_user, require_project_access

router = APIRouter()


@router.get("/project/{project_id}/", response_model=List[ExpenditureSchema])
def list_project_expenditures(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(project_id, db, current_user)
    return db.query(Expenditure).filter(Expenditure.project_id == project_id).all()


@router.post("/", response_model=ExpenditureSchema, status_code=status.HTTP_201_CREATED)
def create_expenditure(
    exp_in: ExpenditureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_pm_or_admin),
):
    require_project_access(exp_in.project_id, db, current_user)

    db_exp = Expenditure(**exp_in.dict(), recorded_by=current_user.user_id)
    db.add(db_exp)
    db.commit()
    db.refresh(db_exp)

    log_event(
        db,
        event_type="CREATE",
        category="FINANCE",
        description=f"Logged spend: R {db_exp.amount} for ref {db_exp.reference_id}",
        user_id=current_user.user_id,
        metadata=exp_in.dict(),
    )
    return db_exp
