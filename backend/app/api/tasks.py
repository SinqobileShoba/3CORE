import logging
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, status, UploadFile
from sqlalchemy.orm import Session

from ..core.audit import log_event
from ..core.uploads import read_validated_upload
from ..models.database import DailyProgress, Task, TaskOutput, User, get_db
from ..schemas.task import (
    DailyProgress as DailyProgressSchema,
    DailyProgressCreate,
    Task as TaskSchema,
    TaskCreate,
    TaskUpdate,
)
from ..services.storage_service import StorageService
from .deps import (
    get_current_active_admin,
    get_current_pm_or_admin,
    get_current_user,
    require_project_access,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _load_task_with_access(task_id: int, db: Session, user: User) -> Task:
    task = db.query(Task).filter(Task.activity_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    require_project_access(task.project_id, db, user)
    return task


@router.get("/project/{project_id}/", response_model=List[TaskSchema])
def get_task_inventory(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(project_id, db, current_user)
    return db.query(Task).filter(Task.project_id == project_id).all()


@router.post("/", response_model=TaskSchema, status_code=status.HTTP_201_CREATED)
def create_task(
    task_in: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    db_task = Task(**task_in.dict())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    log_event(
        db,
        event_type="CREATE",
        category="ACTIVITY",
        description=f"Created task: {db_task.activity_name}",
        user_id=current_user.user_id,
        metadata=task_in.dict(),
    )
    return db_task


@router.put("/{task_id}/", response_model=TaskSchema)
def update_task(
    task_id: int,
    task_in: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_pm_or_admin),
):
    task = _load_task_with_access(task_id, db, current_user)

    update_data = task_in.dict(exclude_unset=True)
    for field in update_data:
        setattr(task, field, update_data[field])

    db.add(task)
    db.commit()
    db.refresh(task)

    log_event(
        db,
        event_type="UPDATE",
        category="ACTIVITY",
        description=f"Updated task: {task.activity_name}",
        user_id=current_user.user_id,
        metadata=update_data,
    )
    return task


@router.delete("/{task_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin),
):
    task = db.query(Task).filter(Task.activity_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    name = task.activity_name
    db.delete(task)
    db.commit()

    log_event(
        db,
        event_type="DELETE",
        category="ACTIVITY",
        description=f"Deleted task: {name}",
        user_id=current_user.user_id,
    )
    return None


@router.get("/output/{output_id}/blob/")
def get_output_blob_info(
    output_id: int,
    inline: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    output = db.query(TaskOutput).filter(TaskOutput.output_id == output_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")

    task = db.query(Task).filter(Task.activity_id == output.activity_id).first()
    if task:
        require_project_access(task.project_id, db, current_user)

    signed_url = StorageService.get_signed_url(output.file_path, inline=inline)

    log_event(
        db,
        event_type="DOWNLOAD",
        category="FILE",
        description=f"Generated signed URL for: {output.file_name}",
        user_id=current_user.user_id,
    )

    return {"file_name": output.file_name, "signed_url": signed_url}


@router.delete("/output/{output_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_output(
    output_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_pm_or_admin),
):
    output = db.query(TaskOutput).filter(TaskOutput.output_id == output_id).first()
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")

    task = db.query(Task).filter(Task.activity_id == output.activity_id).first()
    if task:
        require_project_access(task.project_id, db, current_user)

    try:
        StorageService.delete_file(output.file_path)
    except Exception:
        logger.warning("Failed to delete file from storage: %s", output.file_path, exc_info=True)

    log_event(
        db,
        event_type="DELETE",
        category="FILE",
        description=f"Permanently deleted file: {output.file_name}",
        user_id=current_user.user_id,
    )

    db.delete(output)
    db.commit()
    return None


@router.post("/{task_id}/upload/")
async def upload_task_output(
    task_id: int,
    doc_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _load_task_with_access(task_id, db, current_user)

    content, safe_name = await read_validated_upload(file)
    gcs_path = f"projects/{task.project_id}/tasks/{task_id}/{safe_name}"

    StorageService.upload_file(
        file_content=content, destination_path=gcs_path, content_type=file.content_type
    )

    db_output = TaskOutput(
        activity_id=task_id,
        file_name=safe_name,
        file_path=gcs_path,
        doc_type=doc_type,
        uploaded_by=current_user.user_id,
    )
    db.add(db_output)

    normalized_doc_type = doc_type.strip().lower()
    if normalized_doc_type == "first draft" and task.status == "Not Started":
        task.status = "Active"
    elif normalized_doc_type in ("final document", "final submission"):
        task.status = "Complete"

    db.commit()
    db.refresh(task)

    log_event(
        db,
        event_type="UPLOAD",
        category="FILE",
        description=f"Uploaded {doc_type}: {safe_name}",
        user_id=current_user.user_id,
        metadata={
            "filename": safe_name,
            "doc_type": doc_type,
            "new_status": task.status,
        },
    )

    return {"status": "success", "new_task_status": task.status}


@router.post(
    "/progress/",
    response_model=DailyProgressSchema,
    status_code=status.HTTP_201_CREATED,
)
def record_daily_progress(
    progress_in: DailyProgressCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = _load_task_with_access(progress_in.activity_id, db, current_user)

    db_progress = DailyProgress(
        activity_id=progress_in.activity_id,
        quantity=progress_in.quantity,
        progress_date=progress_in.progress_date,
        notes=progress_in.notes,
        recorded_by=current_user.user_id,
    )
    db.add(db_progress)

    task.completed_quantity = (task.completed_quantity or 0) + progress_in.quantity
    if (
        task.total_quantity
        and task.total_quantity > 0
        and task.completed_quantity >= task.total_quantity
    ):
        task.status = "Complete"
    elif task.completed_quantity > 0 and task.status == "Not Started":
        task.status = "Active"

    db.commit()
    db.refresh(db_progress)

    log_event(
        db,
        event_type="CREATE",
        category="PROGRESS",
        description=f"Recorded {progress_in.quantity} {task.unit_of_measure} for task: {task.activity_name}",
        user_id=current_user.user_id,
        metadata={
            "quantity": progress_in.quantity,
            "unit": task.unit_of_measure,
            "total_completed": task.completed_quantity,
        },
    )
    return db_progress


@router.get("/progress/{activity_id}/", response_model=List[DailyProgressSchema])
def get_task_progress(
    activity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _load_task_with_access(activity_id, db, current_user)
    return (
        db.query(DailyProgress)
        .filter(DailyProgress.activity_id == activity_id)
        .order_by(DailyProgress.progress_date.desc())
        .all()
    )
