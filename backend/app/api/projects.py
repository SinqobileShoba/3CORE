from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Any

from ..core.audit import log_event
from ..models.database import get_db, Project, User
from ..schemas.project import Project as ProjectSchema, ProjectCreate, ProjectUpdate
from ..services.import_service import ImportService
from ..services.project_service import ProjectService
from .deps import (
    get_current_active_admin,
    get_current_user,
    list_accessible_project_ids,
    require_project_access,
)

router = APIRouter()


@router.post("/import/", response_model=ProjectSchema)
async def import_project(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    content = await file.read()
    return ImportService.import_project_excel(db, content, current_user.user_id)


@router.get("/", response_model=List[Any])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    metrics = ProjectService.get_portfolio_metrics(db)
    accessible = list_accessible_project_ids(db, current_user)
    if accessible is None:
        return metrics
    accessible_set = set(accessible)
    return [m for m in metrics if m.get("project_id") in accessible_set]


@router.get("/{project_id}/", response_model=ProjectSchema)
def read_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return require_project_access(project_id, db, current_user)


@router.get("/{project_id}/metrics/")
def get_metrics(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(project_id, db, current_user)
    metrics = ProjectService.get_project_metrics(db, project_id)
    if not metrics:
        raise HTTPException(status_code=404, detail="Project not found")
    return metrics


@router.get("/{project_id}/spending-breakdown/")
def get_spending_breakdown(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(project_id, db, current_user)
    return ProjectService.get_category_spending(db, project_id)


@router.get("/{project_id}/burndown/")
def get_burndown(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(project_id, db, current_user)
    return ProjectService.get_burndown_data(db, project_id)


@router.get("/{project_id}/task-burndown/")
def get_task_burndown(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(project_id, db, current_user)
    return ProjectService.get_task_burndown_data(db, project_id)


@router.get("/{project_id}/summary/")
def get_project_summary(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(project_id, db, current_user)
    return {"summary": ProjectService.get_executive_summary(db, project_id)}


@router.get("/{project_id}/network-diagram/")
def get_network_diagram(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(project_id, db, current_user)
    return ProjectService.get_network_diagram_data(db, project_id)


@router.post("/", response_model=ProjectSchema, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    project = ProjectService.create_project(db, project_in.dict())
    log_event(
        db,
        event_type="CREATE",
        category="PROJECT",
        description=f"Created project: {project.project_name}",
        user_id=current_user.user_id,
        metadata=project_in.dict(),
    )
    return project


@router.put("/{project_id}/", response_model=ProjectSchema)
def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = project_in.dict(exclude_unset=True)
    for field in update_data:
        setattr(project, field, update_data[field])

    db.add(project)
    db.commit()
    db.refresh(project)

    log_event(
        db,
        event_type="UPDATE",
        category="PROJECT",
        description=f"Updated project: {project.project_name}",
        user_id=current_user.user_id,
        metadata=update_data,
    )
    return project


@router.delete("/{project_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    project = db.query(Project).filter(Project.project_id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()
    return None
