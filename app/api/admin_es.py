from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin
from app.core.deps import get_db
from app.models.doc_chunk import DocChunk
from app.models.index_job import IndexJob
from app.models.user import User
from app.rag.keyword_store import get_keyword_store
from app.scheduler.tasks import rebuild_elasticsearch_alias_task

router = APIRouter(prefix="/api/admin/es", tags=["admin-es"])


@router.get("/stats")
def es_stats(
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    store = get_keyword_store()
    job_rows = db.execute(
        select(IndexJob.target, IndexJob.status, func.count())
        .group_by(IndexJob.target, IndexJob.status)
    ).all()
    jobs: dict[str, dict[str, int]] = {}
    for target, status, count in job_rows:
        jobs.setdefault(target, {})[status] = int(count or 0)
    return {
        "elasticsearch": store.stats(),
        "doc_chunks": db.execute(select(func.count()).select_from(DocChunk)).scalar() or 0,
        "index_jobs": jobs,
    }


@router.get("/jobs")
def list_index_jobs(
    target: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(IndexJob)
    count_stmt = select(func.count()).select_from(IndexJob)
    if target:
        stmt = stmt.where(IndexJob.target == target)
        count_stmt = count_stmt.where(IndexJob.target == target)
    if status:
        stmt = stmt.where(IndexJob.status == status)
        count_stmt = count_stmt.where(IndexJob.status == status)
    rows = db.execute(
        stmt.order_by(IndexJob.updated_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    total = db.execute(count_stmt).scalar() or 0
    return {
        "items": [
            {
                "doc_chunk_id": str(row.doc_chunk_id),
                "target": row.target,
                "status": row.status,
                "attempts": row.attempts,
                "error_message": row.error_message,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ],
        "total": int(total),
    }


@router.get("/alias")
def es_alias_status(_admin: User = Depends(get_current_admin)) -> dict:
    store = get_keyword_store()
    return {
        "alias": store.index_name,
        "current_write_index": store.current_write_index(),
        "exists": store.index_exists(),
    }


@router.post("/alias/rebuild")
def rebuild_es_alias(
    batch_size: int = Query(default=500, ge=1, le=5000),
    target_index: str | None = Query(default=None),
    switch_alias: bool = Query(default=True),
    _admin: User = Depends(get_current_admin),
) -> dict:
    task = rebuild_elasticsearch_alias_task.delay(
        batch_size=batch_size,
        target_index=target_index,
        switch_alias=switch_alias,
    )
    return {"task_id": task.id, "status": "queued"}
