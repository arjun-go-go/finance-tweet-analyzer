"""User profile CRUD — 客观事实存储 (name/nickname/occupation/birthday/location)。"""
from datetime import date

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.user_profile import UserProfile


PROFILE_FIELDS = {"name", "nickname", "occupation", "birthday", "location"}


def get_profile(db: Session, user_id: str = "default") -> dict:
    row = db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        return {}
    return {
        "name": row.name,
        "nickname": row.nickname,
        "occupation": row.occupation,
        "birthday": row.birthday.isoformat() if row.birthday else None,
        "location": row.location,
    }


def upsert_profile(db: Session, user_id: str, fields: dict) -> None:
    """只更新非空字段；ON CONFLICT 按 user_id 唯一约束 upsert。"""
    clean: dict = {}
    for k, v in fields.items():
        if k not in PROFILE_FIELDS:
            continue
        if v is None or v == "":
            continue
        if k == "birthday" and isinstance(v, str):
            try:
                v = date.fromisoformat(v)
            except ValueError:
                logger.warning("[Profile] invalid birthday: {}", v)
                continue
        clean[k] = v

    if not clean:
        return

    stmt = pg_insert(UserProfile).values(user_id=user_id, **clean)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_user_profile_user_id",
        set_=clean,
    )
    db.execute(stmt)
    logger.info("[Profile] upsert user_id={} fields={}", user_id, list(clean))
