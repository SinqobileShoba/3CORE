import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, status, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.uploads import read_validated_upload
from ..models.database import (
    Project,
    RepositoryFile,
    RepositoryLink,
    TaskOutput,
    User,
    get_db,
)
from ..schemas.repository import (
    FileRecord,
    RelatedFile,
    RepositoryFile as RepoFileSchema,
    RepositoryFileCreate,
    SearchResult,
)
from ..services.storage_service import StorageService
from .deps import (
    get_current_user,
    list_accessible_project_ids,
    require_project_access,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class LinkEndpoint(BaseModel):
    type: str  # 'deliverable' or 'personal'
    id: int


class BatchLinkPayload(BaseModel):
    source: LinkEndpoint
    targets: List[LinkEndpoint]


class LinkPayload(BaseModel):
    source_type: str
    source_id: int
    target_type: str
    target_id: int


def _type_to_char(t: str) -> str:
    return "A" if t == "deliverable" else "R"


@router.get("/project/{project_id}/", response_model=List[FileRecord])
def list_project_files(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Consolidated Project Repository — deliverables across all tasks."""
    require_project_access(project_id, db, current_user)

    query = text(
        """
        SELECT
            o.output_id,
            o.activity_id,
            o.file_name,
            o.file_path,
            o.doc_type,
            o.uploaded_at as upload_date,
            t.activity_name as task_name,
            COALESCE(u.full_name, 'Unknown System User') as uploader_name
        FROM task_outputs o
        JOIN baseline_schedule t ON o.activity_id = t.activity_id
        LEFT JOIN users u ON o.uploaded_by = u.user_id
        WHERE t.project_id = :pid
        ORDER BY o.uploaded_at DESC
        """
    )
    results = db.execute(query, {"pid": project_id}).fetchall()
    return [dict(r._mapping) for r in results]


@router.get("/project/{project_id}/knowledge-base/", response_model=List[RepoFileSchema])
def list_knowledge_base(
    project_id: int,
    parent_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(project_id, db, current_user)
    query = db.query(RepositoryFile).filter(RepositoryFile.project_id == project_id)
    if parent_id:
        query = query.filter(RepositoryFile.parent_id == parent_id)
    else:
        query = query.filter(RepositoryFile.parent_id.is_(None))
    return query.order_by(RepositoryFile.is_folder.desc(), RepositoryFile.name).all()


@router.post("/folders/", response_model=RepoFileSchema)
def create_folder(
    folder_in: RepositoryFileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(folder_in.project_id, db, current_user)
    db_folder = RepositoryFile(
        project_id=folder_in.project_id,
        parent_id=folder_in.parent_id,
        name=folder_in.name,
        is_folder=1,
        uploaded_by=current_user.user_id,
    )
    db.add(db_folder)
    db.commit()
    db.refresh(db_folder)
    return db_folder


@router.post("/upload/", response_model=RepoFileSchema)
async def upload_personal_file(
    project_id: int = Form(...),
    parent_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_project_access(project_id, db, current_user)

    content, safe_name = await read_validated_upload(file)
    gcs_path = f"projects/{project_id}/personal/{safe_name}"

    StorageService.upload_file(
        file_content=content,
        destination_path=gcs_path,
        content_type=file.content_type,
    )

    db_file = RepositoryFile(
        project_id=project_id,
        parent_id=parent_id,
        name=safe_name,
        is_folder=0,
        file_path=gcs_path,
        uploaded_by=current_user.user_id,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file


@router.get("/search/", response_model=List[SearchResult])
def search_repository(
    project_id: int,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search deliverables + personal files. Empty q returns all."""
    require_project_access(project_id, db, current_user)

    results: List[dict] = []
    search_term = f"%{q.lower()}%" if q else "%"

    # SQLite-compatible case-insensitive match (LOWER + LIKE).
    deliv_sql = text(
        """
        SELECT o.output_id as id, o.file_name as name, t.activity_name as context
        FROM task_outputs o
        JOIN baseline_schedule t ON o.activity_id = t.activity_id
        WHERE t.project_id = :pid AND LOWER(o.file_name) LIKE :q
        LIMIT 50
        """
    )
    delivs = db.execute(deliv_sql, {"pid": project_id, "q": search_term}).fetchall()
    for d in delivs:
        results.append({"id": d.id, "name": d.name, "type": "deliverable", "context": d.context})

    # ORM .ilike() handles dialect differences portably.
    personal = (
        db.query(RepositoryFile)
        .filter(
            RepositoryFile.project_id == project_id,
            RepositoryFile.is_folder == 0,
            RepositoryFile.name.ilike(f"%{q}%" if q else "%"),
        )
        .limit(50)
        .all()
    )

    for p in personal:
        results.append({"id": p.file_id, "name": p.name, "type": "personal", "context": "Knowledge Base"})

    return results


@router.post("/links/batch/", status_code=status.HTTP_201_CREATED)
def batch_link_files(
    payload: BatchLinkPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.targets:
        raise HTTPException(status_code=400, detail="No targets provided")

    s_type = _type_to_char(payload.source.type)
    s_id = payload.source.id

    for target in payload.targets:
        t_type = _type_to_char(target.type)
        t_id = target.id

        if s_type == t_type and s_id == t_id:
            continue

        exists = (
            db.query(RepositoryLink)
            .filter(
                (
                    (RepositoryLink.source_type == s_type)
                    & (RepositoryLink.source_id == s_id)
                    & (RepositoryLink.target_type == t_type)
                    & (RepositoryLink.target_id == t_id)
                )
                | (
                    (RepositoryLink.source_type == t_type)
                    & (RepositoryLink.source_id == t_id)
                    & (RepositoryLink.target_type == s_type)
                    & (RepositoryLink.target_id == s_id)
                )
            )
            .first()
        )

        if not exists:
            link = RepositoryLink(
                source_type=s_type,
                source_id=s_id,
                target_type=t_type,
                target_id=t_id,
                created_by=current_user.user_id,
            )
            db.add(link)

    db.commit()
    return {"status": "batch linked"}


@router.post("/links/", status_code=status.HTTP_201_CREATED)
def link_files(
    link_in: LinkPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s_type = _type_to_char(link_in.source_type)
    t_type = _type_to_char(link_in.target_type)

    if s_type == t_type and link_in.source_id == link_in.target_id:
        raise HTTPException(status_code=400, detail="Cannot link file to itself")

    link = RepositoryLink(
        source_type=s_type,
        source_id=link_in.source_id,
        target_type=t_type,
        target_id=link_in.target_id,
        created_by=current_user.user_id,
    )
    db.add(link)
    db.commit()
    return {"status": "linked"}


@router.get("/related/{file_type}/{file_id}/", response_model=List[RelatedFile])
def get_related_files(
    file_type: str,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    type_char = _type_to_char(file_type)

    query = text(
        """
        SELECT
            link_id,
            CASE
                WHEN source_type = :char AND source_id = :fid THEN target_type
                ELSE source_type
            END as rel_type,
            CASE
                WHEN source_type = :char AND source_id = :fid THEN target_id
                ELSE source_id
            END as rel_id
        FROM repository_links
        WHERE (source_type = :char AND source_id = :fid)
           OR (target_type = :char AND target_id = :fid)
        """
    )

    links = db.execute(query, {"char": type_char, "fid": file_id}).fetchall()

    related = []
    for link_row in links:
        name = "Unknown File"
        if link_row.rel_type == "A":
            res = db.execute(
                text("SELECT file_name FROM task_outputs WHERE output_id = :id"),
                {"id": link_row.rel_id},
            ).fetchone()
            if res:
                name = res[0]
        else:
            res = db.execute(
                text("SELECT name FROM repository_files WHERE file_id = :id"),
                {"id": link_row.rel_id},
            ).fetchone()
            if res:
                name = res[0]

        related.append(
            {
                "id": link_row.rel_id,
                "name": name,
                "type": "deliverable" if link_row.rel_type == "A" else "personal",
                "link_id": link_row.link_id,
            }
        )

    return related


@router.delete("/files/{file_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_repo_item(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(RepositoryFile).filter(RepositoryFile.file_id == file_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    require_project_access(item.project_id, db, current_user)

    if item.is_folder == 0 and item.file_path:
        try:
            StorageService.delete_file(item.file_path)
        except Exception:
            logger.warning("Failed to delete file from storage: %s", item.file_path, exc_info=True)

    db.execute(
        text(
            "DELETE FROM repository_links "
            "WHERE (source_type = 'R' AND source_id = :id) "
            "   OR (target_type = 'R' AND target_id = :id)"
        ),
        {"id": file_id},
    )
    db.delete(item)
    db.commit()
    return None


@router.get("/files/{file_id}/blob/")
def get_personal_file_blob(
    file_id: int,
    inline: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(RepositoryFile).filter(RepositoryFile.file_id == file_id).first()
    if not item or item.is_folder == 1:
        raise HTTPException(status_code=404, detail="File not found")
    require_project_access(item.project_id, db, current_user)

    signed_url = StorageService.get_signed_url(item.file_path, inline=inline)
    return {"file_name": item.name, "signed_url": signed_url}


@router.get("/all/", response_model=List[FileRecord])
def list_all_files(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recent deliverables across all projects the caller can access."""
    accessible = list_accessible_project_ids(db, current_user)

    base_sql = """
        SELECT
            o.output_id,
            o.activity_id,
            o.file_name,
            o.file_path,
            o.doc_type,
            o.uploaded_at as upload_date,
            t.activity_name as task_name,
            COALESCE(u.full_name, 'Unknown System User') as uploader_name
        FROM task_outputs o
        JOIN baseline_schedule t ON o.activity_id = t.activity_id
        LEFT JOIN users u ON o.uploaded_by = u.user_id
    """
    params = {}
    if accessible is not None:
        if not accessible:
            return []
        # SQLAlchemy expanding bindparam for portability.
        from sqlalchemy import bindparam
        query = text(base_sql + " WHERE t.project_id IN :pids ORDER BY o.uploaded_at DESC LIMIT 100").bindparams(
            bindparam("pids", expanding=True)
        )
        params["pids"] = accessible
    else:
        query = text(base_sql + " ORDER BY o.uploaded_at DESC LIMIT 100")

    results = db.execute(query, params).fetchall()
    return [dict(r._mapping) for r in results]
