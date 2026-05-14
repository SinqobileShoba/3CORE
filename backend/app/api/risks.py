import logging
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, status, UploadFile
from sqlalchemy.orm import Session

from ..core.audit import log_event
from ..core.uploads import read_validated_upload
from ..models.database import get_db, Risk, RiskProof, User
from ..schemas.risk import Risk as RiskSchema, RiskCreate, RiskUpdate
from ..services.storage_service import StorageService
from .deps import get_current_user, list_accessible_project_ids, require_project_access

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[RiskSchema])
def list_risks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    accessible = list_accessible_project_ids(db, current_user)
    query = db.query(Risk)
    if accessible is not None:
        if not accessible:
            return []
        query = query.filter(Risk.project_id.in_(accessible))
    return query.all()


@router.get("/project/{project_id}/", response_model=List[RiskSchema])
def list_project_risks(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(project_id, db, current_user)
    return db.query(Risk).filter(Risk.project_id == project_id).all()


@router.post("/", response_model=RiskSchema, status_code=status.HTTP_201_CREATED)
def create_risk(
    risk_in: RiskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(risk_in.project_id, db, current_user)

    db_risk = Risk(**risk_in.dict(), recorded_by=current_user.user_id)
    db.add(db_risk)
    db.commit()
    db.refresh(db_risk)

    log_event(
        db,
        event_type="CREATE",
        category="RISK",
        description=f"Logged risk: {db_risk.description[:50]}...",
        user_id=current_user.user_id,
        metadata=risk_in.dict(),
    )
    return db_risk


@router.put("/{risk_id}", response_model=RiskSchema)
def update_risk(
    risk_id: int,
    risk_in: RiskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    risk = db.query(Risk).filter(Risk.risk_id == risk_id).first()
    if not risk:
        raise HTTPException(status_code=404, detail="Risk not found")
    require_project_access(risk.project_id, db, current_user)

    update_data = risk_in.dict(exclude_unset=True)
    for field in update_data:
        setattr(risk, field, update_data[field])

    db.add(risk)
    db.commit()
    db.refresh(risk)

    log_event(
        db,
        event_type="UPDATE",
        category="RISK",
        description=f"Updated risk ID {risk_id}",
        user_id=current_user.user_id,
        metadata=update_data,
    )
    return risk


@router.post("/{risk_id}/proof/")
async def upload_risk_proof(
    risk_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    risk = db.query(Risk).filter(Risk.risk_id == risk_id).first()
    if not risk:
        raise HTTPException(status_code=404, detail="Risk not found")
    require_project_access(risk.project_id, db, current_user)

    content, safe_name = await read_validated_upload(file)
    gcs_path = f"projects/{risk.project_id}/risks/{risk_id}/{safe_name}"

    StorageService.upload_file(
        file_content=content,
        destination_path=gcs_path,
        content_type=file.content_type,
    )

    db_proof = RiskProof(
        risk_id=risk_id,
        file_name=safe_name,
        file_path=gcs_path,
        uploaded_by=current_user.user_id,
    )
    db.add(db_proof)

    # Uploading proof against an Open risk transitions it to Mitigated.
    # An admin can still set status back via PUT /risks/{id}.
    if risk.status == "Open":
        risk.status = "Mitigated"

    db.commit()

    log_event(
        db,
        event_type="UPLOAD",
        category="RISK",
        description=f"Uploaded proof for risk: {risk.description[:30]}",
        user_id=current_user.user_id,
        metadata={"filename": safe_name},
    )

    return {"status": "success"}
