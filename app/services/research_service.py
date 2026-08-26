from __future__ import annotations

from datetime import datetime
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.research import ResearchConclusion, ResearchEvidence, ResearchTopic
from datetime import timedelta, timezone


def create_topic(db: Session, user_id: UUID, data) -> ResearchTopic:
    topic = ResearchTopic(
        user_id=user_id,
        conversation_id=data.conversation_id,
        title=data.title,
        research_question=data.research_question,
        mode=data.mode,
        tickers=[value.upper() for value in data.tickers],
        source_scope=data.source_scope,
        time_range=data.time_range,
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


def list_topics(db: Session, user_id: UUID) -> list[ResearchTopic]:
    return list(db.execute(
        select(ResearchTopic).where(ResearchTopic.user_id == user_id, ResearchTopic.status != "deleted")
        .order_by(ResearchTopic.updated_at.desc()).limit(100)
    ).scalars())


def get_topic(db: Session, user_id: UUID, topic_id: UUID) -> ResearchTopic | None:
    return db.execute(select(ResearchTopic).where(ResearchTopic.id == topic_id, ResearchTopic.user_id == user_id)).scalar_one_or_none()


def add_evidence(db: Session, topic: ResearchTopic, data) -> ResearchEvidence:
    existing = db.execute(select(ResearchEvidence).where(
        ResearchEvidence.topic_id == topic.id,
        ResearchEvidence.evidence_key == data.evidence_key,
    )).scalar_one_or_none()
    if existing:
        return existing
    evidence = ResearchEvidence(
        topic_id=topic.id, evidence_key=data.evidence_key, source_type=data.source_type,
        source_id=data.source_id, tickers=data.tickers, author=data.author,
        published_at=data.published_at, excerpt=data.excerpt, source_url=data.source_url,
        sentiment=data.sentiment, verification_status=data.verification_status,
        relevance_score=data.relevance_score, metadata_=data.metadata,
    )
    db.add(evidence)
    topic.updated_at = datetime.now().astimezone()
    db.commit()
    db.refresh(evidence)
    return evidence


def add_conclusion(db: Session, topic: ResearchTopic, data) -> ResearchConclusion:
    version = int(db.execute(select(func.coalesce(func.max(ResearchConclusion.version), 0)).where(ResearchConclusion.topic_id == topic.id)).scalar_one()) + 1
    conclusion = ResearchConclusion(
        topic_id=topic.id, version=version, conclusion=data.conclusion,
        thesis=data.thesis, counter_evidence=data.counter_evidence, risks=data.risks,
        evidence_keys=data.evidence_keys, confidence=data.confidence,
    )
    db.add(conclusion)
    topic.current_conclusion = data.conclusion
    db.commit()
    db.refresh(conclusion)
    return conclusion


def workspace(db: Session, topic: ResearchTopic) -> tuple[list[ResearchEvidence], list[ResearchConclusion]]:
    evidence = list(db.execute(select(ResearchEvidence).where(ResearchEvidence.topic_id == topic.id).order_by(ResearchEvidence.created_at)).scalars())
    conclusions = list(db.execute(select(ResearchConclusion).where(ResearchConclusion.topic_id == topic.id).order_by(ResearchConclusion.version.desc())).scalars())
    return evidence, conclusions


def queue_run(db: Session, topic: ResearchTopic) -> None:
    from app.services.outbox_service import enqueue_outbox_event
    if topic.status in {"queued", "running"}:
        return
    topic.status = "queued"
    topic.last_error = None
    enqueue_outbox_event(db, "research.run_requested", {"topic_id": str(topic.id), "user_id": str(topic.user_id)})
    db.commit()


def update_monitor(db: Session, topic: ResearchTopic, *, enabled: bool, frequency: str) -> ResearchTopic:
    topic.monitor_enabled = enabled
    topic.monitor_frequency = frequency
    if enabled:
        delta = timedelta(days=1 if frequency == "daily" else 7)
        topic.next_run_at = datetime.now(timezone.utc) + delta
    else:
        topic.next_run_at = None
    db.commit()
    db.refresh(topic)
    return topic


def finish_run(db: Session, topic: ResearchTopic, *, error: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    topic.last_run_at = now
    topic.last_error = error
    topic.status = "failed" if error else "active"
    if topic.monitor_enabled:
        topic.next_run_at = now + timedelta(days=1 if topic.monitor_frequency == "daily" else 7)
    db.commit()
